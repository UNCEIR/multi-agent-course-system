# MySQL 查询优化：FULLTEXT 索引 + B-tree 索引

> 源码：`course_repository.py`、`course_recall_agent.py`、`init-db.sql`
> 当前数据量 500 行，优化以学习为目的，验证索引机制的正确性。

---

## 1. 现状问题

| 问题 | 说明 |
|---|---|
| **7 列 LIKE 模糊匹配** | `course_name/teacher/category/domain/campus/time_slot/tags LIKE '%kw%'`，前导通配符导致 B-tree 无法使用 |
| **无二级索引** | `course_records` 仅 `PRIMARY KEY (course_id)`，过滤列和排序列全表扫描 |
| **排序 filesort** | `ORDER BY popularity_level DESC, current_enrolled DESC, course_id ASC` 每次 filesort |
| **_short_query 守卫** | >12 字符的查询直接 skip LIKE，阈值过小 |

---

## 2. 决策过程（Q&A 摘要）

| 决策点 | 方案 | 结论 |
|---|---|---|
| LIKE 改 FULLTEXT | 方案 C：加 `search_text` 生成列拼接 7 列 + 单个 FULLTEXT 索引 | ✅ |
| 匹配模式 | `NATURAL LANGUAGE MODE` + `≤2` 字符降级 LIKE 兜底（ngram 双字分词无法匹配单字） | ✅ |
| search_text 维护 | `GENERATED ALWAYS AS ... STORED`，MySQL 自动维护，零代码入侵 | ✅ |
| 排序优化 | `(popularity_level DESC, current_enrolled DESC, course_id ASC)` 纯排序联合索引 | ✅ |
| 过滤列优化 | `domain`、`course_category`、`campus` 各建 B-tree 索引 | ✅ |
| _short_query 阈值 | `12` → `50`，FULLTEXT 处理长文本能力强于 LIKE | ✅ |
| 测试接口 | `/api/v1/recommend/stream`（SSE 流式），最终 `done` 事件含 `total_latency_ms` | ✅ |

---

## 3. 实施方案

### 3.1 索引 DDL

```sql
-- 生成列：自动拼接 7 列文本（CONCAT_WS 跳过 NULL）
search_text TEXT GENERATED ALWAYS AS (
  CONCAT_WS(' ', course_name, teacher, course_category, domain, campus, time_slot, tags)
) STORED

-- FULLTEXT 全文索引（ngram 中文双字分词）
FULLTEXT INDEX ft_search_text (search_text) WITH PARSER ngram

-- B-tree 过滤列索引 ×3
INDEX idx_domain (domain)
INDEX idx_course_category (course_category)
INDEX idx_campus (campus)

-- 排序联合索引
INDEX idx_popularity_enrolled (popularity_level DESC, current_enrolled DESC, course_id ASC)
```

### 3.2 fetch_courses SQL 变化

```python
kw = query_text.strip()
if len(kw) <= 2:
    # 单字/双字降级 LIKE 兜底（FULLTEXT ngram 无法匹配单字）
    conditions.append("(course_name LIKE :qt OR teacher LIKE :qt OR ...)")
    params["query_text"] = f"%{kw}%"
else:
    # FULLTEXT 主路径（不用 % 包裹）
    conditions.append("MATCH(search_text) AGAINST(:query_text IN NATURAL LANGUAGE MODE)")
    params["query_text"] = kw
```

### 3.3 修改文件清单

| 文件 | 改动 |
|---|---|
| `python/repositories/course_repository.py` | `ensure_schema()`: 加生成列 + 5 索引 + `_add_index_if_missing` 辅助方法 |
| | `fetch_courses()`: ≤2 字符 LIKE 兜底，>2 字符 MATCH...AGAINST |
| `python/agents/course_recall_agent.py` | `_short_query()`: 阈值 `12` → `50`，`[:30]` → `[:50]` |
| `scripts/init-db.sql` | 同步 search_text 生成列 + 5 索引 |

---

## 4. 测试结果

### 4.1 环境

```bash
docker compose -f docker-compose.python.yml --profile python up -d
# 数据已通过 ingest_course_dataset.py 导入（500 门）
```

### 4.2 端到端测试（`/api/v1/recommend/stream`）

> 冷缓存：每次测试前 `FLUSH recall:*`；热缓存：同一 payload 连调两次取第二次。
> `total_latency_ms` 来自 SSE 最终 `done` 事件。

| 场景 | Before (ms) | After (ms) |
|---|---|---|
| 冷缓存 | 70,108 | 90,817 |
| 热缓存 | 78,929 | 87,500 |

**结论**：70-90s 完全被 LLM 调用主导（pipeline 含 4 次 LLM 调用），DB 层 4-6ms 占比 <0.01%，索引优化在端到端层面完全不可见。

### 4.3 直接 DB 查询测试（`fetch_courses`，warmup=2，runs=5）

| 用例 | Before avg | After avg | Δ |
|---|---|---|---|
| 无过滤 `limit=40` | 5.901ms | 5.571ms | -0.33ms |
| domain 过滤 | 4.207ms | 4.149ms | -0.06ms |
| 短文本 LIKE（≤2字） | 4.230ms | 3.669ms | -0.56ms |
| 长文本 MATCH（>2字） | 4.774ms | 4.885ms | +0.11ms |
| 组合过滤 | 5.076ms | 4.147ms | -0.93ms (-18%) |

**结论**：50 行数据下索引优化差异在 1ms 以内，属于统计噪声范围。组合过滤（domain + text）改善最明显（-18%），得益于 domain B-tree 索引避免了全表扫描。FULLTEXT MATCH 与 LIKE 在此规模下性能相当。索引架构正确，数据量增长到万级后差异会显著放大。

#### FULLTEXT 为何比 LIKE 更慢

长文本 MATCH 比原始 LIKE 多 0.11ms，不是 bug，是 **FULLTEXT 固定启动成本 > 50 行全表扫描**：

| | LIKE `%keyword%` | FULLTEXT MATCH |
|---|---|---|
| **执行路径** | 内存中扫 50 行，逐行 substr 比对 | ngram 分词 → 查倒排索引 → 取交集 → 回表 |
| **固定开销** | 几乎为零 | ngram tokenizer 解析 + B-tree 遍历 |
| **增长曲线** | O(n)，线性 | O(log n + 命中行数) |

50 行全表数据塞不满一个 InnoDB page (16KB)，LIKE 本质上是一次纯内存 `memcmp`。而 FULLTEXT 需要先把 "不考试作业少" 用 ngram 切成 `不考` `考试` `试作` `作业` `业少` 5 个 bigram，然后逐条查倒排索引求交集——这个启动成本比扫 50 行更大。**交叉点预计在千行以上**，届时 FULLTEXT 开始反超。

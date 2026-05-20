# 召回 Redis 缓存（读 / 写 / 类型）

> 源码：`course_recall_cache_repository.py`、`course_recall_agent.py`、`supervisor.py`  
> **画像召回** = 带 `StudentProfile` 的第二次 `run()`（日志字段仍为 `refined_recall_*`）

---

## 1. Redis 用到的类型（三个角色 + 锁）

| 角色 | Key 示例 | 类型 | 存什么 |
|------|----------|------|--------|
| **主 key** | `recall:v1:aaa` | **String** | 课 id 列表 `["GXK001",...]`（= 精确缓存本体） |
| **向量卡片** | `recall:v1:aaa:semantic` | **String** | 写入时的原话 + embedding（只给语义比对） |
| **桶** | `recall:semantic:v1:none` 或 `.../7c2e9a1b4f8d3e60` | **Set** | 成员 = 主 key 文本 `recall:v1:aaa`（目录，**不存课单**） |
| **锁** | `recall:v1:aaa:lock` | **String** | `"1"`，NX，默认 5s，防并发击穿 |

**存储原理（一句话）**

- 课单只存 **一份** → String 主 key。  
- 桶只登记 **有哪些主 key 可以拿来比语义** → Set 成员是名字，不是数据副本。  
- `:semantic` **挂在主 key 名字后面**（`主key + ":semantic"`），精确命中只 GET 主 key，不加载向量。  

默认 TTL：主 key、`:semantic`、桶 均为 **900s**（`ECOM_COURSE_RECALL_CACHE_TTL_SECONDS`）。命中**不续期**。

---

## 2. 主 key 怎么来（payload → digest）

一次 `run()` = **一个** payload 字典 → **一个** `recall:v1:{digest}`（不是每个字段一个 key）。

```text
payload = { domains, categories, campus, exam, workload, grade_friendly, group_work, grade, major }
  有 StudentProfile → 多来自画像；无 profile → 多来自 context
  若全空 → 加 prompt[:80]（宽召回常见）

digest = sha256(json.dumps(payload, sort_keys=True))[:24]
主 key  = recall:v1:{digest}

sig = 去掉 prompt 后的 payload 再 hash；全空 → "none"
桶    = recall:semantic:v1:{sig}
```

| 召回 | payload 典型 | 桶 |
|------|----------------|-----|
| 宽召回 | 常仅 `prompt[:80]` | `recall:semantic:v1:none` |
| 画像召回 | `campus/domains/exam/...`（常无 prompt） | `recall:semantic:v1:{16位hex}` |

宽、画像 **各 key 各写各读**；Supervisor `_merge_courses` 只在内存合并两路课单，**不写 Redis**。

---

## 3. 读路径

### 3.1 总顺序（一次 `run()`）

```text
精确 GET 主 key
  → hit：MySQL 拉课 → 结束
  → miss：
       语义（embed → 扫桶 → 比 :semantic → GET 赢家主 key）
         → hit：MySQL 拉课 → 结束
         → miss：抢锁 / wait → MySQL + Milvus → 写回（§4）
```

---

### 3.2 精确命中

```text
① 拼 payload → 本次 digest
② GET recall:v1:{digest}
③ 有值 → 解析 course_id → MySQL fetch_courses_by_ids → 打分返回
```

- 不读桶、不读 `:semantic`、不调 Milvus  
- 日志：`redis_recall_cache_hit`，`cache_match_type: exact`

---

### 3.3 语义命中（精确已 miss）

```text
① GET recall:v1:{本次digest}  →  miss

② embed(用户当前 prompt)  →  本次向量
   （Agent 内 query = prompt 或 context["query"]；前端只传 prompt 即可）

③ SMEMBERS recall:semantic:v1:{sig}
     → ["recall:v1:aaa", "recall:v1:bbb", ...]   ← 主 key 文本，最多 12 个

④ 对每个成员 recall:v1:aaa：
     EXISTS recall:v1:aaa
     GET recall:v1:aaa:semantic  →  历史向量
     cosine(本次向量, 历史向量)
   取最高分；≥ 0.9（默认）→ 赢家 = aaa

⑤ GET recall:v1:aaa  →  course_id 列表  →  MySQL 拉课  →  打分返回
```

- **先桶后 `:semantic`**，不是先扫全库 `:semantic`  
- 复用的是**历史**主 key 的课单（如 `aaa`），不是本次 digest  
- 日志：`redis_recall_cache_semantic_hit`，`milvus_skipped=True`

---

### 3.4 全 miss → 在线召回

```text
① 精确 miss
② 语义 miss
③ SET NX recall:v1:{digest}:lock
     失败 → sleep 重试 GET 主 key（wait_hit）→ 有则同 3.2
④ MySQL 结构化 + Milvus → merge → 打分
⑤ 写回 §4
```

---

## 4. 写路径（仅 miss 且算完候选后）

### 4.1 一定写：主 key

```text
SET recall:v1:{digest}  '["GXK001","GXK042",...]'  EX 900
```

- 有 course_id 就写；**与是否抢到锁无关**

### 4.2 条件写：向量卡片 + 桶登记

**条件**：`lock_acquired` 且 `query` 非空 且 `course_recall_cache_semantic_enabled`

```text
embed(query)

SET recall:v1:{digest}:semantic
  '{"prompt":"...","embedding":[...],...}'  EX 900

SADD recall:semantic:v1:{sig}  recall:v1:{digest}
EXPIRE recall:semantic:v1:{sig}  900
```

- `SADD` 只把 **主 key 名字** 放进 Set，**不是**再存一份课单，**不是**写 `:semantic` 进桶  
- 没抢到锁 → 可能只有主 key；`redis_recall_cache_bypass`，不进桶、不写 `:semantic`

### 4.3 写回对照表

| 步骤 | 命令 | 写到哪 | 类型 |
|------|------|--------|------|
| 课单 | SET | `recall:v1:{digest}` | String |
| 向量 | SET | `recall:v1:{digest}:semantic` | String |
| 目录 | SADD | `recall:semantic:v1:{sig}` | Set |
| 锁 | SET NX | `recall:v1:{digest}:lock` | String |

**不是写两次 `recall:v1:aaa`**：`SET` 存数据，`SADD` 只在桶里登记同名文本。

---

## 5. Phase 1（两次 run + 合并）

```text
并行：画像 Agent  ∥  宽召回(profile=None)
画像成功 → 画像召回(profile=StudentProfile)
Supervisor._merge_courses(宽课单, 画像课单)   # 先宽后画像，同课留宽
```

每次 run 各自：读 §3 → 可能写 §4。合并与 Redis hit/miss 无关。

---

## 6. 语义 vs Milvus（别混）

| | Redis 语义缓存 | Milvus |
|---|----------------|--------|
| 比什么 | 用户 **两次说法** 的向量 | 用户话 vs **课程 chunk** |
| 时机 | 精确 miss 后、**Milvus 之前** | 精确 + 语义都 miss 后 |
| 命中得到 | 历史主 key 里的 **course_id 列表** | 当场搜出的课 |

---

## 7. 易错对照

| 误解 | 事实 |
|------|------|
| 精确缓存在桶里 | 课单在 String **主 key** |
| 桶里存 `aaa:semantic` | 桶里存 `recall:v1:aaa` 文本 |
| 先扫 `:semantic` 再找桶 | **先 SMEMBERS 桶** |
| `sig=none` 无语义 | `none` 是桶名；宽召回常用 |
| 画像召回没有语义层 | 与宽召回同一 `_execute` |
| HTTP `query` 空就没有语义 | 有 **prompt** 即有 Agent 内 `query` |

---

## 8. 配置默认值

| 变量 | 默认 |
|------|------|
| `ECOM_COURSE_RECALL_CACHE_TTL_SECONDS` | 900 |
| `ECOM_COURSE_RECALL_CACHE_LOCK_TTL_SECONDS` | 5 |
| `ECOM_COURSE_RECALL_CACHE_SEMANTIC_THRESHOLD` | 0.9 |
| `ECOM_COURSE_RECALL_CACHE_SEMANTIC_MIN_PROMPT_CHARS` | 8（仅读语义） |

---

## 9. 验证

- **已做**：源码静态对照  
- **未做**：Redis CLI、`/recommend` 实测  

建议：同 prompt 连打两次 → `exact`；换同义句 → `semantic` + `SMEMBERS recall:semantic:v1:none`。

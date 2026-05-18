# Hard Constraint Filter：categories 检查误过滤 domain 匹配课程的 Bug 修复

## 背景与问题

- **本轮要解决的问题**：`HardConstraintFilter._check_violations()` 中的 categories 检查逻辑存在误过滤 bug，导致用户说"人文艺术"时，所有 `domain="人文艺术"` 的课程被全部过滤掉。
- **触发原因**：LLM（StudentProfileAgent）提取的 `categories` 硬约束往往是 domain 值，如 `["人文艺术"]`；而 `course.course_category` 是正式分类名，如 `"人文与社会科学类"`。两者不同导致所有候选课被判定违反约束。
- **影响范围**：用户指定课程类型偏好时（如"人文艺术"），若 LLM 将其提取为 categories 约束，则对应 domain 的全部课程均会被 `hard_constraint_filter` 清空，最终 `passing=0`，推荐链路返回空结果或全部被过滤。

## 总体架构方案

- **涉及模块**：`python/orchestrator/hard_constraint_filter.py`（Phase 1.5 确定性硬约束过滤器）
- **数据流**：
  ```
  supervisor → Phase 1.5 HardConstraintFilter
    → _check_violations(course, hc)
      → hc.categories vs course.course_category  ← 修复点
      → 新增：or course.domain in hc.categories
  ```
- **关键设计取舍**：采用 any-of 语义（course_category **或** domain 任意一个命中即通过），而非 all-of，符合"用户指定领域偏好即视为匹配"的业务语义。不引入 LLM 调用，保持 Phase 1.5 确定性无网络 I/O 特性。

## 细节实现

- **修改文件**：`python/orchestrator/hard_constraint_filter.py`，`_check_violations()` 静态方法，第 106-116 行

**修复前（有 bug）**：
```python
if hc.categories and course.course_category not in hc.categories:
    required = "/".join(hc.categories)
    actual = course.course_category or "unknown"
    violations.append(
        f"课程分类不符（{actual}，要求{required}）"
    )
```

**修复后**：
```python
if hc.categories:
    category_match = (
        course.course_category in hc.categories
        or course.domain in hc.categories
    )
    if not category_match:
        required = "/".join(hc.categories)
        actual = f"{course.course_category or 'unknown'}(分类)/{course.domain or 'unknown'}(领域)"
        violations.append(
            f"课程分类/领域不符（{actual}，要求{required}）"
        )
```

- **兼容性**：当 `course.domain` 为 `None` 时，`None in hc.categories` 返回 `False`，不影响已有检查逻辑；violation 消息格式升级为"分类/领域"同时展示，便于排查。

## Debug 结论

- **根因**：categories 约束字段语义存在两层抽象：LLM 提取的是面向用户的 domain 值（如"人文艺术"），数据库中的 `course_category` 是系统分类名（如"人文与社会科学类"）。原代码只做精确字符串比对，未考虑 domain 别名，导致所有 domain 匹配的课程被系统性过滤。
- **排查过程**：直接阅读 `_check_violations()` 代码，对比 Course schema 中 `course_category` 和 `domain` 两个字段的定义及样本数据（course.csv），确认两字段语义差异。
- **解决方式**：改为 `course_category in hc.categories or course.domain in hc.categories`，any-of 匹配。

## 测试与验证

**已执行**：

1. **Lint 检查**：`ReadLints` 检查 `hard_constraint_filter.py`，无 linter 错误。
2. **单元测试**（venv 环境）：
   ```
   .venv\Scripts\python.exe -m pytest python/tests/ -m "not slow" -v
   ```
   结果：**35 passed，1 deselected，0 failed**（2.87s）
3. **Docker 重建**：
   ```
   docker compose -f docker-compose.python.yml --profile python up -d --build
   ```
   结果：镜像重建成功，所有容器（redis/mysql/milvus/python-api）正常运行。
4. **端到端 curl 测试**（payload："想找不考试、作业少的人文艺术公选课，东校区优先"）：
   - `hard_constraint_filter.done`：`total_input=25, passing=14, filtered_out=11`
   - 过滤原因：`no_exam=True` 过滤掉有考试的课程，**categories=[]（本次 LLM 未生成 categories 约束）**
   - 推荐结果：3 门课程（中外名建筑赏析、基本乐理、中国古建筑文化与鉴赏），全部为 `domain="人文艺术"` 且 `campus="东校区"` ✅
   - `course_rerank.candidate_count=14`，`output_count=3` ✅
   - 无 hard_constraint_no_match 警告 ✅

**本次测试的附加观察**：
- 本次 curl 测试 Redis 缓存命中（`strategies: ["redis_recall_cache_hit"]`），未调 embedding API，召回速度极快（65ms）。
- LLM 在这次请求中并未将"人文艺术"映射为 categories 硬约束（categories=[]），而是通过 campus 和 no_exam 约束过滤，说明 StudentProfileAgent 的 prompt 已能区分"偏好"和"硬约束"。但 fix 本身依然必要——若 LLM 在某些 prompt 下确实输出 categories，原代码会触发 bug。

## 经验与后续

- **本轮经验**：
  1. 约束检查中跨越两个字段语义层（用户感知名 vs 系统分类名）时，需要 any-of 匹配，不能只匹配其中一个。
  2. violation 消息应同时呈现实际值的两个维度（分类/领域），有助于后续 debug 和用户提示。
  3. 本地 `python -m pytest` 需用 `.venv\Scripts\python.exe` 而非系统 Python，否则缺包导致 collection 失败。

- **后续建议**：
  - 可考虑在 `StudentProfileAgent` prompt 或后处理中，规范化 categories 字段：将"人文艺术"映射为 `["人文艺术", "人文与社会科学类"]` 双写，以支持精确匹配和向后兼容。
  - 若后续支持更多分类名别名（如"理工类" → "自然科学与工程技术类"），可在 `hard_constraint_filter.py` 引入分类别名映射表（`CATEGORY_ALIASES`），统一在 filter 层做规范化。

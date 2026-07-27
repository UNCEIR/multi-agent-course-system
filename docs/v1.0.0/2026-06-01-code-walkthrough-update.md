# 面试代码证据链文档更新（2026-06-01）

## 本次解决了什么问题

`docs/code-walkthrough.md` 在 5/23-5/28 迭代后有多处内容滞后于代码实际状态，包括：

1. 推荐阅读路径缺少 `react_tools.py` 和 `stream_token_markup_parser.py`。
2. Supervisor 章节未覆盖 ReAct 双模式编排（`_react_recommend()`）和 Phase 1.75 LLM 语义初筛（`_llm_semantic_filter()`）。
3. 课程召回章节未说明 `query_embedding` 统一计算优化（3 次→1 次）、`search()` 返回格式变化、`_score_candidates()` 简化。
4. 重排章节缺少 `_compute_score()` 多维偏好打分和 Top-40 预过滤说明。
5. 可行性章节缺少 `_llm_priority_advice()` 方法、规则 fallback 静默回退、`priority_advice` 数据流说明。
6. 缺少 ReAct 工具编排（`react_tools.py`）和流式 Token 解析（`stream_token_markup_parser.py`）两个独立章节。
7. 测试证据从 18 passed 增长到 39 passed，测试文件从 4 个增长到 8 个。

## 方案

### 总体架构

保持原有按执行顺序讲解的 18 节结构，在 supervisor（原第 5 节）之后插入两个新章节（第 6 节 ReAct 工具编排、第 7 节流式 Token 解析），后续章节编号顺延至 20 节。

### 细节改动

- **第 1 节**：推荐阅读路径补充 `react_tools.py`（#5）和 `stream_token_markup_parser.py`（#7）。
- **第 5 节**：补充 `_react_recommend()` A/B 路由（ReAct 10 轮工具循环）、`_llm_semantic_filter()` Phase 1.75 说明、双模式编排设计意图、新追问点。
- **新第 6 节**：基于 `react_tools.py` 源码，讲解 `REACT_TOOLS`/`ReactState`/`ReactToolExecutor` 三层结构和硬约束锁死兜底。
- **新第 7 节**：基于 `stream_token_markup_parser.py` 源码，讲解双状态机、marker 正则、三种事件类型、MAX_BUFFER 防护。
- **第 11 节**（原第 9 节）：补充 `query_embedding` 统一计算、`search()` 返回 `list[dict]`、`_score_candidates()` 只保留关键词+热度。
- **第 15 节**（原第 13 节）：补充 `_compute_score()` 多维偏好打分公式、乘法融合、Top-40 预过滤。
- **第 16 节**（原第 14 节）：补充 `_llm_priority_advice()` 12 门课限制、规则 fallback 静默回退、`priority_advice` 数据流。
- **第 19 节**（原第 17 节）：更新测试数量 39 passed、8 个测试文件及覆盖范围。
- **第 20 节**（原第 18 节）：面试自查补充双模式编排、embedding 优化、流式解析相关检查项。

## 测试

本次只修改 Markdown 文档，未修改业务代码，不需要运行测试。已通过 ReadLints 检查无 linter 错误。

## 验证

- 所有代码路径（文件名、方法名、参数名、返回格式）均对照源码确认。
- 未编造指标数据。
- 未在代码注释中写解释性文字。

## 经验

1. 面试文档更新必须对照源码验证——方法签名、返回类型、参数名容易在迭代后变化。
2. 新增章节时需要处理好编号顺延，避免引用混乱。
3. "可追问"部分如果附带简短答案（而非只列问题），面试准备效率更高。

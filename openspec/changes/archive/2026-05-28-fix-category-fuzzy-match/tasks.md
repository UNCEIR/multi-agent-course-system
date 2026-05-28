## 1. 扩展 category_rules（B 方案）

- [x] 1.1 修改 `python/agents/student_profile_agent.py` 的 `_extract_prompt_hard_constraints`：在 `category_rules` 中**保留原有 5 条**，并追加 B 方案关键词（长词优先排列）：
  - → `自然科学与工程技术类`：`理工类`、`理工科`、`工科类`、`理科类`、`理工`、`工科`
  - → `人文与社会科学类`：`文科类`、`社科类`、`文科`、`社科`
  - **不加**裸词 `理科`、艺术/体育/创新创业等第三档词
- [x] 1.2 扩展 `python/tests/test_hard_constraint_prompt_fallback.py`：为 B 方案各新增 1 条 prompt 提取用例（理工类、文科、工科类、理科类、社科类），并保留「自然科学类」回归用例

## 2. 验证

- [x] 2.1 运行 `python -m pytest tests/test_hard_constraint_prompt_fallback.py -v`

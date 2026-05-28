## Why

当 LLM 画像 JSON 未给出 `hard_constraints.categories` 时，系统回退到 `_extract_prompt_hard_constraints` 从用户 prompt 做规则提取。当前 `category_rules` 缺少「理工类」「文科类」「工科类」等高频口语，导致用户明确表达类别偏好时硬约束 categories 为空。

## What Changes

采用 **B 方案（推荐集）**：仅扩展 `_extract_prompt_hard_constraints` 内 `category_rules`，补全口语关键词 → canonical 分类映射，并补充对应单元测试。

**新增关键词（保留原有 5 条不变）：**

| 关键词 | canonical |
|--------|-----------|
| 理工、理工类、理工科、工科、工科类、理科类 | `自然科学与工程技术类` |
| 文科、文科类、社科、社科类 | `人文与社会科学类` |

**刻意不加：** 裸词 `理科`（避免「理科楼」误触）、艺术/体育/创新创业（domain 与 category 混淆或数据集无对应类）。

## Capabilities

### New Capabilities

- `prompt-category-extraction`: 从用户 prompt 规则回退提取课程分类硬约束（B 方案关键词集）

### Modified Capabilities

（无）

## Impact

- **仅修改** `python/agents/student_profile_agent.py` — `_extract_prompt_hard_constraints`
- **仅修改** `python/tests/test_hard_constraint_prompt_fallback.py` — 新增 B 方案 prompt 提取用例
- **不修改** filter、recall、rerank、共享模块、`AGENTS.md` 及其他文档

## Non-Goals

- 不改动 `_fuzzy_text_match`、MySQL 召回、`preferred_categories` 同步
- 不新增 `category_normalization` 模块
- 不纳入第三档 risky 关键词（艺术、体育、创新创业等）

## 已知局限

规则只写入 `hard_constraints.categories`；LLM 直接输出别名、或 recall 使用未归一化的 `preferred_categories` 仍可能失败——需另开 change。

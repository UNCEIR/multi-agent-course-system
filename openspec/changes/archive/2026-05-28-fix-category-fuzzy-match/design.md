## Context

### 问题位置

`StudentProfileAgent._extract_prompt_hard_constraints` → `_parse_hard_constraints` 合并 prompt 规则与 LLM JSON，写入 `HardConstraints.categories`。

现有 `category_rules` 仅覆盖「自然科学/工程技术/人文/社会科学/心理」，无法识别口语「理工类」「文科类」等。

### 数据集约束

`course_category` 仅两类：`自然科学与工程技术类`、`人文与社会科学类`。规则表所有 value 必须是上述 canonical 字符串。

### 方案选型：B 方案（推荐集）

在 explore 阶段对比三档后选定：

| 方案 | 范围 | 结论 |
|------|------|------|
| A 最小集 | 理工/文科 | 覆盖不足 |
| **B 推荐集** | +工科类、理科类、社科类 | **采用** |
| C 积极集 | +理科、艺术、创新创业 | 误触与 domain 混淆风险高 |

## Goals / Non-Goals

**Goals:**

- B 方案关键词命中 prompt 时，`hard_constraints.categories` 写入 canonical 分类
- 单文件 dict 扩展 + 测试锁定
- 保留现有 5 条规则及「自然科学类」等已可用表达

**Non-Goals:**

- filter / recall / rerank / 文档
- 裸词 `理科`、第三档 domain 型关键词

## Decisions

### 1. B 方案完整 `category_rules` 追加项

在现有 5 条之后追加（实现时建议**长词在前**，便于阅读维护）：

```python
# → 自然科学与工程技术类
"理工类": "自然科学与工程技术类",
"理工科": "自然科学与工程技术类",
"工科类": "自然科学与工程技术类",
"理科类": "自然科学与工程技术类",
"理工": "自然科学与工程技术类",
"工科": "自然科学与工程技术类",

# → 人文与社会科学类
"文科类": "人文与社会科学类",
"社科类": "人文与社会科学类",
"文科": "人文与社会科学类",
"社科": "人文与社会科学类",
```

已有项保持不变：

```python
"自然科学": "自然科学与工程技术类",
"工程技术": "自然科学与工程技术类",
"人文": "人文与社会科学类",
"社会科学": "人文与社会科学类",
"心理": "人文与社会科学类",
```

### 2. 不加裸词「理科」

**理由：** 子串匹配 `keyword in prompt` 会在「理科楼308」等地点描述误触 STEM 硬约束。

**替代：** 仅加 `理科类`，用户表达分类意图时通常带「类」。

### 3. 不加第三档关键词

| 词 | 不加原因 |
|----|----------|
| 艺术/艺术类 | 两类 bucket 均有艺术相关课 |
| 体育/体育健康 | 数据集无体育类课；SYSTEM_PROMPT 的 domain 名 ≠ category |
| 创新创业 | domain 语义；创业课在 DB 属人文 bucket，不宜作硬约束口语规则 |

### 4. 测试策略

在 `test_hard_constraint_prompt_fallback.py` 新增用例（均 empty LLM categories + prompt）：

| 用例 prompt 片段 | 断言 categories 含 |
|------------------|-------------------|
| 理工类 | 自然科学与工程技术类 |
| 文科 | 人文与社会科学类 |
| 工科类 | 自然科学与工程技术类 |
| 理科类 | 自然科学与工程技术类 |
| 社科类 | 人文与社会科学类 |
| 自然科学类（回归） | 自然科学与工程技术类 |

可选负向：prompt 仅含「理科楼」且不含 `理科类` → categories 不应因 `理科类` 以外规则误加（若未来有人加裸「理科」则失败；B 方案下可不加此测或作文档说明）。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 仅 hard_constraints 生效，recall 仍用 preferred_categories | proposal 已知局限；用户 scope 限定 |
| 「工科」在非分类语境出现 | 频率低；B 方案接受 |
| dict 条目增多 | 仍单 dict，无新模块 |

## Migration Plan

- 无 DB / 部署变更；改完跑 `pytest tests/test_hard_constraint_prompt_fallback.py`

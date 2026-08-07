# compute_weighted_grade

**状态**: `stub` — `NotImplementedError`
**Phase**: 2
**类别**: `report/*`

## 功能描述

计算加权期末总评。公式：`总评 = display_eval × 0.3 + exam_eval × 0.7 + bonus`。用于成绩单报告场景的复合统计。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `display_eval` | `float` | 是 | — | 展示性评价分数，范围 0-100 |
| `exam_eval` | `float` | 是 | — | 考试性评价分数，范围 0-100 |
| `bonus` | `float` | 否 | `0.0` | 额外加分，范围 0-20 |

## 输出

包含 `total`、`display_weighted`、`exam_weighted`、`bonus` 的字典。

## 失败兜底

- 确定性 Python 计算，不依赖 LLM（防幻觉）

## 参考

- `docs/v2.0.0/plan.md` Phase 2：报告场景
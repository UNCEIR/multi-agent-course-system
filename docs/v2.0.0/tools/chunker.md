# chunk_document

**状态**: `implemented` — 确定性本地分块
**Phase**: 1
**类别**: `documents/*`

## 功能描述

将文档文本按段落或固定字符窗口分块，支持 overlap；不依赖外部服务。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `text` | `str` | 是 | — | 文档文本内容 |
| `chunk_size` | `int` | 否 | `500` | 每块目标大小（字符数或 token 数），范围 50-2000 |
| `chunk_overlap` | `int` | 否 | `50` | 块间重叠大小，范围 0-500 |
| `strategy` | `str` | 否 | `"paragraph"` | 分块策略（paragraph、token、semantic） |

## 输出

分块列表，每块包含 `text` 和 `metadata`。

## 失败兜底

- 分块失败时返回空列表
- 大文件分块超时时降级为简单按段落分割

## 参考

- `python/tools/documents/` 子包
- `docs/v2.0.0/plan.md` 决策 6：文档流水线

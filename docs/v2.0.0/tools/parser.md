# parse_document

**状态**: `stub` — `NotImplementedError`
**Phase**: 1
**类别**: `documents/*`

## 功能描述

解析文档文件内容，支持 CSV/PDF/doc 三种格式。FastGPT KB 不可用时作为 Python 本地解析兜底。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `file_path` | `str` | 是 | — | 文件路径，1-1024 字符 |
| `file_type` | `str` | 否 | `"auto"` | 文件类型（auto、pdf、docx、csv），auto 自动检测 |

## 输出

提取的文本内容。

## 失败兜底

- 解析失败时返回错误信息，提示用户检查文件格式
- 大文件（>10MB）提示分批上传

## 参考

- `python/tools/documents/` 子包
- `docs/v2.0.0/plan.md` 决策 6：文档流水线
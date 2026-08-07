# mindmap_generator

**状态**: `stub` — `NotImplementedError`
**Phase**: 3/4
**类别**: `mindmap/*`

## 功能描述

根据主题生成思维导图，支持 Markdown/Mermaid/plantuml 等多种输出格式。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `topic` | `str` | 是 | — | 思维导图中心主题，1-200 字符 |
| `nodes` | `list[dict]` | 否 | `None` | 节点列表（可选，留空则自动生成） |
| `format` | `str` | 否 | `"markdown"` | 输出格式（markdown、json、svg 等） |

## 输出

思维导图数据（markdown 大纲或可渲染的 DSL）。

## 失败兜底

- 渲染服务不可用时返回 markdown 大纲格式
- 支持重试生成

## 参考

- `E:\Agent\OpenMAIC` — 渲染管线参考
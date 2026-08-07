# web_search

**状态**: `stub` — `NotImplementedError`
**Phase**: 3
**类别**: `chat/*`

## 功能描述

使用 tavily 搜索引擎获取实时互联网信息，用于知识库未覆盖的实时信息查询。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | `str` | 是 | — | 搜索关键词，1-500 字符 |
| `max_results` | `int` | 否 | `5` | 返回结果数量，范围 1-20 |

## 输出

搜索结果摘要文本。

## 失败兜底

- tavily 服务不可用时返回错误信息，提示用户稍后重试
- 可降级为知识库检索（`query_knowledge`）

## 参考

- `requirements.txt` — `tavily-python` 依赖已加
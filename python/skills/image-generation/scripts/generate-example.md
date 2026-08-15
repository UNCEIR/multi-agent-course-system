# Script: generate-example（图片生成调用示例）

> 调用契约示例；参数细节以工具 docstring 为准。

## 单次调用
```json
{"prompt": "夕阳下的大学图书馆，插画风格，温暖色调", "ratio": "16:9", "style": "插画", "negative_prompt": "模糊，水印"}
```

## 链路
`image_generate` → 即梦 MCP `image/*` → 产物下载落库（MinIO/本地）→ 返回链接

## 失败处理
MCP 不可达 → `{isError, code: "MCP_*", message}` → 告知用户重试（不伪造图片）。

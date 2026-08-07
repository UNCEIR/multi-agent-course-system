# image_generate

**状态**: `stub` — `NotImplementedError`
**Phase**: 3
**类别**: `image/*`

## 功能描述

根据文本描述生成图片。经 MCP 调用图片生成服务，独立 Page 组件（ImageGeneratePage）使用，需要画布/参数配置等深度交互。

## 输入参数

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `prompt` | `str` | 是 | — | 图片描述文本，1-2000 字符 |
| `style` | `str` | 否 | `"写实"` | 图片风格（写实、卡通、水彩、油画、扁平化等） |
| `width` | `int` | 否 | `1024` | 图片宽度（像素），范围 256-4096 |
| `height` | `int` | 否 | `768` | 图片高度（像素），范围 256-4096 |

## 输出

生成图片的 URL 或 base64 数据。

## 失败兜底

- MCP 服务不可用时返回错误信息
- 支持重新生成（修改 prompt 或 style）

## 参考

- `docs/v2.0.0/plan.md` 决策 16：ImageGeneratePage 独立页
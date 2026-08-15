# Command: generate-deliver（生成与交付）

## Steps
1. 确认参数：
   - `prompt`：提示词（必填，主体/场景/风格）
   - `ratio`：宽高比（1:1 / 16:9 / 9:16 / 3:4 / 4:3）
   - `style`：风格（写实/插画/动漫/水墨等，可空）
   - `negative_prompt`：负面提示词（可空）
2. 调用 `image_generate`（即梦 MCP，image/* namespace）。
3. 产物 URL 落库（MinIO/本地）→ 返回可访问链接。
4. 失败 → 结构化错误，提示稍后重试（不伪造）。

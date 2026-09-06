# 2026-09-05 图片生成交付链路修复（report 下载错配 + 前端 Markdown/图片渲染）

> 一句话：`image_generate` 链路**即梦确实被调用**（LangSmith 显示 done + 3 个真实签名 URL），
> 坏在「转存后链接生成」——工具把图片 URL 改写成了 report 下载接口的形态
> （`/api/v1/report/download?...&token=__IMG__`），而该端点只认 report 产物的 HMAC/PDF/HTML 契约；
> 前端 chat 又无 Markdown 渲染，`![alt](url)` 只能按纯文本显示。两端各修一层，并新增图片专用下载通道。

---

## 1. 排查方法

1. **LangSmith trace 时间差分析**：`image_generate_get` 工具总耗时 49.96s，而内部
   `generate_image_get`（MCP→火山）返回 done 只花 12.10s。差额 ≈ 38s = 3 张即梦 24h 签名 URL
   被 `_store_image()` 用 httpx **顺序下载再传 MinIO** 的耗时 —— 证明即梦真实生成了图，问题不在生成。
2. **返回结构抓包**：MCP 原始返回是 `{"output": [{"text": "{json}", "type": "text"}]}` 包装，
   不同 `langchain-mcp-adapters` 版本解析形态不同，`_call_mcp` 原有解析脆弱。
3. **代码走读**（纯代码，不动 docker）：
   - `python/tools/image/image_generate.py`：done 分支把 `image_urls` 逐个丢进 `_store_image(u)`，
     转存后返回自造的 `/api/v1/report/download?file_key=images/<uuid>.png&token=__IMG__`（接口错配根源）。
   - `python/api/report.py` `download`：只认 HMAC（`__IMG__` 占位必拒），且 `.png` 走
     `text/html` + `attachment`（report 产物专用契约）。
   - `frontend/src/app/(main)/chat/page.tsx`：`<div style={{whiteSpace:'pre-wrap'}}>{item.content}</div>`
     纯文本渲染，全仓库无任何 Markdown 渲染库。
4. **运行时探测**：`verify_download_token("images/x.png", "__IMG__", 0)` 实测返回 `token_expired`；
   `MCP_SERVERS` 已注册 `jimeng`（stdio）且 `VOLC_ACCESS_KEY/SECRET` 已配置（配置齐全，非缺凭据）。

## 2. 问题根源

- **根源 1（后端接口错配，确定性代码 bug）**：`_store_image()` 把「即梦 24h URL 下载→传 MinIO」后，
  丢弃原始 URL，返回 `/api/v1/report/download?file_key=images/*.png&token=__IMG__`。
  - `token=__IMG__` 是**占位符**，report/download 只做 HMAC 校验 → 必然 403/410；
  - 该端点对 `.png` 返回 `text/html` + `Content-Disposition: attachment`，`<img>` 无法渲染。
  - 即"LLM 没调用错，是工具把 report 接口形态的返回值喂给了 LLM"。
- **根源 2（转存依赖外部 24h URL + MCP 解析脆弱）**：转存靠 httpx 下载 3 张图（~38s）；
  `_call_mcp` 对 `{"output":[{text}]}` 包装无兜底，换 adapters 版本可能静默失灵。
- **根源 3（前端不渲染）**：chat 消息无 Markdown 渲染，`![alt](url)`/URL/alt 全部按字面文本显示。

## 3. 解决思想

- **图片交付走独立通道、永不过期**：`generate_image_get` 以 `need_base64=true` 请求即梦
  `binary_data_base64` → 主进程 base64 解码**直存** MinIO/本地（不再依赖外部 24h URL 下载）→
  返回新端点 `/api/v1/images/download?file_key=images/<uuid>.<ext>`（`image/*` + `inline`、无 token、无过期）。
- **report/download 保留 `images/` legacy 兼容**：旧会话历史里已落库的
  `/api/v1/report/download?...&token=__IMG__` 链接仍可打开（前一轮已加：images/ 前缀跳过 HMAC +
  按扩展名返回 image/* + inline），避免历史消息图片永久死链。
- **`_call_mcp` 加解析兜底**：递归提取 text → `json.loads`，兼容裸 dict / `{"output":[...]}` /
  list / 带 `.content` 对象。
- **前端 Markdown 渲染**：assistant 消息用 `react-markdown` 渲染（图片输出 `<img>`、链接新窗口、
  raw HTML 默认不渲染防 XSS）；user 消息保留 pre-wrap 纯文本（不吞用户换行）。

## 4. 实际编码

后端：
- `python/api/images.py`（新增）：`GET /api/v1/images/download` —— `images/` 前缀强校验（防任意
  MinIO 对象下载），按扩展名返回 `image/png|jpeg|gif|webp` + `Content-Disposition: inline`；
  对象缺失 404。无 token / 无过期。
- `python/agent/app.py`：注册 `images.router`。
- `python/tools/image/image_generate.py`：
  - 新增 `_extract_text()` + 重写 `_call_mcp()`（解析兜底）；
  - `image_generate_get` done 分支 → `_store_done_images()`：**base64 直存优先**（`images_base64`/
    `image_formats`），空则回退 `image_urls` httpx 下载；
  - `_store_image_bytes()` / `_store_image_from_url()`：字节直存 MinIO/本地，返回
    `/api/v1/images/download?...`（永不过期）；失败返回 `None` → `NO_STORAGE` isError（不伪造链接）；
  - `_image_ext()` 魔数嗅探（PNG/JPEG/GIF/WebP）；补 `import base64`。
- `python/tools/image/jimeng_mcp_server.py`：`generate_image_get` 增加 `need_base64` 参数；
  `_handle_get` 按 `need_base64` 决定火山 `return_url`（true → 回 base64）；done 时经
  `_normalize_base64_images()`（兼容 dict / 裸 base64 串）组装 `images_base64`/`image_formats`。
- `python/api/report.py`（前一轮）：download 对 `images/` 前缀直链放行 + 扩展名 content-type + inline（legacy 兼容）。

前端：
- `frontend/package.json`：新增依赖 `react-markdown`。
- `frontend/src/components/MarkdownContent.tsx`（新增）：`react-markdown` 渲染，`img` 组件输出
  `<img>`（max-width/圆角/inline 样式），链接新窗口。
- `frontend/src/app/(main)/chat/page.tsx`：assistant 消息改用 `<MarkdownContent content=... />`；
  user 消息保留原 `whiteSpace: pre-wrap` 纯文本。
- `frontend/tests/components/MarkdownContent.spec.tsx`（新增）。

## 5. 测试结果（断言式，全 mock；不连真实即梦/火山/MinIO）

后端（本机 9 passed，~5s）：
- `tests/test_image_generate.py`（5 passed）：`_extract_text` 多形态提取；`_call_mcp` 对
  `{"output":[{text:json}]}` 的解析兜底；done + base64 → 解码直存 MinIO 并返回
  `/api/v1/images/download?file_key=images/...`（断言无 `token`、无 `report/download`）；
  done 无图 → `NO_STORAGE` isError；url 兜底 → httpx 下载 + 魔数嗅探存 `.jpg`。
- `tests/test_images_api.py`（4 passed）：images/ key → 200 `image/png` + inline；非 images/ 前缀 →
  403 `invalid_key`（且不触达存储）；对象缺失 → 404；`agent/app.py` 路由注册静态校验。
- `tests/test_report_api.py` 已追加图片直链回归用例（images/ 跳过 HMAC、report pdf 仍校验 HMAC），
  TestClient 用例待容器/CI 跑（本机 import `agent.app` 收集极慢，单测已改为不依赖 app 的直调式）。

前端（三件套全绿）：
- `vitest tests/components/MarkdownContent.spec.tsx`：5 passed —— 纯文本段落 / `![alt](url)` 渲染为
  `<img src/alt>` / 单消息多图 / 不渲染 raw HTML（XSS 安全）/ 加粗+链接新窗口。
- `npm run lint`：通过。
- `npm run build`：通过（12 路由全静态）。

## 6. 部署与验收提醒

1. 后端代码改动需重建容器：`docker compose up -d --build python-api`
   （镜像源不可达时显式传 `--build-arg PYTHON_IMAGE=docker.m.daocloud.io/library/python:3.12-slim`）。
2. `image_generate_get` 现在默认请求 base64 直存；若即梦侧 `binary_data_base64` 为空会自动回退
   24h URL 下载（向后兼容），无需改 LLM/skill。
3. 前端改了 `package.json`：frontend 容器需 `--no-cache` 重建；本地调试可直接 `npm run dev`。
4. 验收路径：
   - 对话发「生成 3 张红玫瑰」→ done 回复中 `![红玫瑰](...)` 应渲染为图片；
   - 直接访问返回的 `/api/v1/images/download?file_key=images/xxx.png` → 200 `image/png` + inline；
   - 旧会话历史里的 `/api/v1/report/download?...&token=__IMG__` 链接（若对象仍在 MinIO/卷内）也能打开。

---

## 追加（2026-09-05 晚间）：LLM 拿到 image_urls 却不附图 → main prompt 强制附图

**现象**：`image_generate_get` 返回 done + 3 个可访问的 `/api/v1/images/download` 链接，后端 200、前端
MarkdownContent 就绪，但最终回复只输出 `1.\n2.\n3.` 空编号，未把 url 渲染成 Markdown 图片 → 前端无图可渲染。

**根源**：不是后端/前端，是 **LLM 行为漂移**（prompt/skill 遵循不稳定），把"图"当附件略过。

**解决**：`python/agent/main/prompt.py` 图片生成分支补硬约束——done 后**必须逐条把 image_urls 渲染成
Markdown 图片并原样保留 url**（示例 `1. ![生成图1](/api/v1/images/download?file_key=images/xxx.png)`），
禁止只写编号不放图/改写 url。已重建 python-api（容器内 grep 命中确认）。复测仍偶发再考虑工具结果附加
展示指令或终稿缺失图片链接的后校验重试。

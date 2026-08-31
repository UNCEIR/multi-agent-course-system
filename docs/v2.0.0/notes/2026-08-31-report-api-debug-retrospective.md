# Report API Debug 复盘（2026-08-31）

> 范围：仅围绕 `/api/v1/report`（教师端成绩报告）进行。遵循 write-note-for-project 技能：bug 排查 → 发现 → 分析 → 解决 → 测试 五段式闭环。
> 本复盘覆盖本轮对话中对该 API 的全部真实改动与验证，未执行项明确标注。

## 背景与问题

- 本轮要解决的问题：`/api/v1/report` 从「前端上传 → 后端生成 PDF → 落库 → 下载/预览」的业务闭环打通，并修复一路排查出的多个故障。
- 触发原因或用户诉求：① 前端主页面成绩报告模块交互未对接后端；② 上传后一直报"请先上传成绩单"；③ SSE 流长时间无返回、前端报 network error；④ 生成 OK 却无法查看/下载；⑤ PDF 模板错位、综合评价无划线格子；⑥ 明确字段语义并支持手动选班级。
- 影响范围：`python/api/report.py`、`python/agent/report/service.py`、`python/tools/report/*`、`python/storage/{mysql,minio}/*`、`python/templates/report/*`、`sql/init-db.sql`、`docker-compose.yml`、`frontend/next.config.ts`、`frontend/src/app/(main)/report/page.tsx`、`frontend/src/lib/api.ts`、`frontend/src/types/index.ts`。

## 总体架构方案

- 涉及模块：FastAPI SSE 端点（`api/report.py`）→ 编排门面 `agent/report/service.py`（deepagents report_agent + 工具进度 channel 合流）→ 确定性工具 `tools/report/render_report_batch.py`（解析/合并/填表/评语/渲染/存储/落库）→ 存储（MinIO `report-artifacts` + 本地兜底；MySQL `report_uploads`/`report_artifacts`）→ 前端 ReportPage（antd Upload + SSE 消费 + 批次列表/详情/预览）。
- 数据流或调用链：
  ```
  前端 upload (files+semester+class_name+user_message+user_id)
    → POST /api/v1/report (SSE)
      → stream_report：落盘 → report_uploads(processing) → 建 report_agent
        → astream_events(v1) + 后台 drainer 实时转发 student_done/progress
        → render_report_batch：解析合并 → 班级覆盖 → 逐学生填表/评语/PDF → MinIO/本地
        → done → report_uploads(done + merged_batch_id) + report_artifacts 落库
      → 前端：done 后刷「已生成批次」；行内 查看(inline)/下载；批次详情弹窗
  ```
- 关键设计取舍：
  - 输入侧 `report_uploads` 与知识库 `document_records`、输出侧 `report_artifacts` **分表**（业务不同不混存）；批次级 + 文件清单 JSON + 状态机，便于扩展 per-file。
  - 工具进度用 ContextVar channel + **后台常驻 drainer**（长工具调用期间实时可见），替代"每 agent 事件后 drain"的旧设计。
  - 整批死线 `report_stream_timeout_seconds` 兜底 + 单次 LLM `request_timeout` 双保险，杜绝无限挂。
  - Next.js dev 代理超时由 `experimental.proxyTimeout` 显式放大（30s → 30min）。
  - 本地兜底卷挂载 + MinIO 30s 冷却自愈（不永久降级）。

## 细节实现

- 修改/分析的关键文件（按闭环顺序）：
  1. `frontend/src/app/(main)/report/page.tsx`：上传收集改 `onChange`（UploadFile 带 originFileObj）→ 再加固为 `rawFilesRef`（uid+File 自管，不依赖 antd 内部属性）；登录守卫；批次列表；班级输入；学生表 查看/下载；批次详情弹窗。
  2. `sql/init-db.sql`：新增 `report_uploads`（含 `merged_batch_id` + 列存在性迁移守卫）。
  3. `python/storage/mysql/report_upload_repo.py`：新建仓储（create/update_status/list/get，merged_batch_id 非空才更新）。
  4. `python/agent/report/service.py`：上传批次落库（processing→done/error）、整批死线 `asyncio.wait_for`、后台 drainer `_drain_forever`、class_name/user_message ContextVar 注入、done 回填 merged_batch_id。
  5. `python/api/report.py`：`class_name` Form 字段；`GET /api/v1/report/batches`；`GET /api/v1/report/batches/{batch_id}` 详情（归属校验 403）；`download?inline=1` 预览。
  6. `python/tools/report/render_report_batch.py`：`_fill_html`（report_llm_fill_enabled 开关）、`apply_class_override`、评语透传 user_message、长工具期间 `_put` 进度。
  7. `python/tools/report/generate_subjective_eval.py`：`user_message` 注入评语提示词。
  8. `python/storage/minio/minio_repo.py`：`_local_only` 永久锁 → `_local_until` 30s 冷却自愈。
  9. `docker-compose.yml`：python-api 挂载 `python_documents_data:/app/.documents` 卷。
  10. `frontend/next.config.ts`：`experimental.proxyTimeout: 30*60*1000`。
  11. `python/templates/report/{grade1-3,grade4-6}.html`：表外 `<tr>` 移回表内；`comment-box`/`comment-lines` 划线格。
  12. `python/config/settings.py`：`report_stream_timeout_seconds`、`report_llm_fill_enabled`。
- 核心逻辑：
  - 长工具进度：`_run_agent` 起 `asyncio.create_task(_drain_forever())`，`channel_q.get()` 持续转发 `student_done/student_error/progress` 到 SSE 队列，`batch_done` 记入 holder；agent 流结束后兜底再 drain。
  - 班级覆盖：`apply_class_override(merged.students, report_class_ctx.get())` 在 `merge_files` 后批量写 `stu["class"]`。
  - 划线格：`.comment-lines` 用 `line-height:32px` + `repeating-linear-gradient`（31px/32px 周期）使每行文字落在横线上；`min-height:128px` 默认 4 行。
- 兼容性与风险控制：所有 `data-slot` 锚点原样保留（LLM 填充契约不变）；`report_llm_fill_enabled` 默认 true（行为不变，false 才提速）；minio 冷却不影响既有测试语义（`is_local_only` 仍表示当前处于本地兜底）。

## Debug 结论

- 根因（按发现顺序）：
  1. 前端 `filter(f => f.originFileObj)` 恒空（beforeUpload 塞裸 File）→ 上传从未调后端。
  2. 新表 `report_uploads` 只进 init.sql，旧 MySQL 卷未建表 → 落库失败（warning，不阻塞生成）。
  3. `_run_agent` 只在 agent 事件间隙 drain channel；`render_report_batch` 是分钟级单工具调用，langgraph 期间无事件 → 进度全堵 → 前端冻结 → 用户取消 → uvicorn cancel（CancelledError 证据：`render_report_batch.py:183 gather` + `_per_student:118 async with sem` + `RequestResponseCycle.run_asgi`）。
  4. Next.js dev 代理 `proxy-request.js` 硬编码 `proxyTimeout || 30000`（30s）→ 长 SSE 被掐断 → 前端 network error。
  5. 文件存储：python-api 无卷，本地兜底重建即丢；`minio_repo._local_only` 永久锁定不重试 MinIO → 生成 OK 但下载 404。
  6. grade4-6.html 的「信息/劳动/综实」4 行 `<tr>` 在 `</table>` 外（非法 HTML）→ PDF 错位。
- 排查过程（证据链）：
  - 本地复现：真实 deepagents report agent + 假模型，`astream_events(v1/v2)` 均秒完（排除 agent 结构）；本地挂起 HTTP server 测 `build_chat_openai` → `APITimeoutError` 3.1s（证明单次 LLM 调用有界）；翻 Next.js 源码定位 30s proxyTimeout；`git`/eval 报告确认 37 人约 12~15min（`report_math_live-2026-08-18.json`: 910805ms/722222ms）。
- 解决方式：见「细节实现」1~12；核心是 channel 后台 drainer + 代理超时放大 + 卷持久化 + minio 自愈 + 模板结构修正 + 字段链路透传。

## 测试与验证

- 已执行（本轮全部真实执行）：
  - 后端 `python -m pytest tests/ -m "not slow"`：最终 **381 passed / 4 deselected**（新增：report_upload_repo CRUD、service 状态机 processing→done/error、整批超时 STREAM_TIMEOUT、长工具实时转发、inline/attachment、批次详情/403、class_name 透传、user_message 注入/空不注入、apply_class_override、merged_batch_id 回填、minio 冷却）。
  - 前端：`npm test` **132/132**（报告页 5 个：批次列表、流式消费到 done+class_name 断言、结构化 error、登录守卫、详情弹窗）；`npm run lint` 0 问题；`npm run build` 通过（12 静态路由）。
  - 模板结构校验：两个模板表外 `<tr>` = 0、`data-slot` 锚点全部完好、评语落进 `comment-box`。
- 结果：业务闭环打通；下载/预览/详情可用（需重建容器 + 重跑 init.sql 补 `merged_batch_id` 列后对新批次生效）。
- 未执行及原因：**真实 LLM 端到端 PDF 渲染未在本机执行**（WeasyPrint 仅在容器内、且需真实 LLM 配额），由 mock 测试覆盖各层契约 + 08-18 live eval（37 人 PDF 全生成）佐证；容器实机验证需用户重建后复测。

## 经验与后续

- 本轮经验：
  - "看似卡死"先分清**慢**与**挂**：用 08-18 eval 的 latency 数据证明 37 人本就要 12~15min，避免误判为 bug；再翻框架源码（Next.js proxy）找真实掐断点。
  - 长工具进度必须**独立于 agent 事件流**转发（后台 drainer），否则 UI 冻结诱导用户取消，产生误导性 CancelledError。
  - 依赖版本与文档要一起锁：`langchain>=0.3.0` 无上限会拉到 1.x；`astream_events v1` 虽可用但已废弃，后续应迁移 v2。
  - 容器内"本地兜底"默认不持久，凡是可被重建清掉的产物都要挂卷或进 MinIO；降级逻辑要可自愈（冷却）而非永久锁死。
- 后续建议：
  - `astream_events(version="v1")` → 迁移 `version="v2"`（chat/report 两处），消除弃用警告并适配 langchain 1.x。
  - 生产部署前端改用 `next start`（不走 dev 代理），验证 SSE 长连接；或调研 Next.js dev 代理在更大超时下的稳定性。
  - 旧批次详情（无 merged_batch_id）建议补一次性回填脚本；`report_llm_fill_enabled=false` 可作为大数据量批次的默认推荐。

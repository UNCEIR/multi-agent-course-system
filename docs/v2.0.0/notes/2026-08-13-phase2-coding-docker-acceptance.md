# Phase 2 编码 + Docker 验收（report / evaluation / 插件 / 记忆 / 评估骨架）

## 背景与问题

- 本轮要解决的问题：将 v2.0.0 Phase 2 的详细计划（`plans/phase-2-report-evaluation.md`）与编码清单（`plans/phase2-coding-plan.md`）完整落地，并在 Docker 环境做端到端验收。
- 触发原因或用户诉求：需求.md 要求体现 agent 工程深度（防幻觉、工具链路兜底、记忆管理、评估指标）；用户补充新增功能点（MCP 插件、chat 长期记忆、评估方针）；随后要求按 coding-plan 逐工作流编码，遇到真实 MCP 测试先跳过。
- 影响范围：`python/`（4 个智能体场景）、`sql/init-db.sql`（+5 张表）、`docker-compose.yml`（minio/milvus 凭据改造）、`docs/v2.0.0/plans/*`（两份计划）、`docs/v2.0.0/plan.md`（总计划状态）。

## 总体架构方案

- 涉及模块：
  - report（教师端成绩单批量生成）：deep agent 壳（A-shell）+ `render_report_batch` 确定性工具 + 进度 channel 合流 SSE
  - evaluation（教师端生成→学生端同步）：直接 asyncio 管线（不建 agent 壳），五层反幻觉
  - main agent 插件：`mcp_client` 实装（配置注册表/懒连接/每服务器熔断）+ web_search（MCP→tavily 兜底）/ image_generate（即梦 MCP）/ image_recognize（qwen3-vl-plus视觉直连）/ writing / mindmap（纯 Python 渲染）
  - chat 记忆：`chat_sessions/chat_messages/chat_memory_entries` 三表 + 写纪律 + 增量摘要提取（水位幂等）+ 首轮注入 + AGENTS.md 代码级禁写
  - 评估骨架：`eval_sets/` 4 集 + `eval/runner.py` 断言式指标 + LangSmith Dataset 导入
- 数据流或调用链：
  - report：Excel 上传 → agent 四决策点（摘要→分类→执行→汇总）→ 解析合并（学号主键+差集告警+完整性断言+Journal）→ LLM 填表（双校验→Jinja2 降级）→ PDF（WeasyPrint→HTML 兜底）→ MinIO/本地 → report_artifacts → HMAC token 下载
  - evaluation：快照（metadata_json 直查）→ LLM 维度提案（Pydantic 硬校验→默认维度集）→ 代码算值（metric 枚举）→ LLM 评语（数值引用核验硬闸→规则化兜底）→ evaluation_records → 学生端 /me
- 关键设计取舍：显式 LangGraph 节点图 vs A-shell/直接管线——report/evaluation 的编排是"线性确定性 + 少量可枚举 LLM 决策点"，显式图拓扑收益为零；图的价值留给 Phase 3 PPT 协作与 Phase 4 harness。

## 细节实现

- 修改或分析的关键文件：
  - `tools/report/`（parse_score_excels 表头驱动解析 / merge_students 键合并 / fill_report_html LLM 填表+Jinja2 / render_report_batch async 工具 / contract 别名映射）
  - `tools/evaluation/`（get_academic_snapshot / design_dimensions / compute_radar_values / generate_comment）
  - `tools/mcp_client.py` + `tools/circuit_breaker.py`（acall 补全）
  - `agent/memory/`（persistence/extractor/injector）+ `storage/mysql/chat_session_repo.py`（原子自增 seq/复合键/content_hash 去重）
  - `agent/report/service.py`（双流合流）、`agent/evaluation/service.py`（五层 + 独立熔断）
  - `storage/minio/minio_repo.py`（双后端统一寻址）、`storage/mysql/report_artifact_repo.py`、`evaluation_repo.py`
  - `ai/llm_client.py`（model/base_url/api_key/enable_thinking 覆盖参数，默认行为零变化）
- 核心逻辑：
  - 反幻觉三原则落地：确定性计算与 LLM 分离（统计/雷达/合并/校验全代码）；LLM 输出 schema 硬校验失败回灌重试；数值引用核验硬闸（评语数字必须 ∈ 数据源，容差 0.5）
  - 防信息丢失六道闸：数据不过 LLM / 学号键合并+差集告警 / 两阶段渲染断言 / Journal 续跑 / 只留等级 / 幂等 batch_id
  - 链路兜底链：LLM 填表→Jinja2；WeasyPrint→HTML；MinIO→本地；MCP→直连/沙箱；熔断→规则化降级
- 兼容性与风险控制：`build_chat_openai` 扩展为可选覆盖（15+ 既有调用点零破坏，有回归测试）；`AgentSpec.use_checkpointer`（无状态三 spec 不建 checkpoint）；main agent 对 AGENTS.md 的 FilesystemPermission deny write（修复多租户泄漏）。

## Debug 结论（Docker 验收阶段 5 个真实问题）

1. **minio secret `123456` 不合法**：minio 要求 secret ≥ 8 字符，容器直接退出（`Invalid credentials`）。→ 统一改为 `12345678`（.env/compose/settings 三处同步）。证据：容器退出日志 + 宿主 minio SDK 验证。
2. **milvus 报 minio 签名不匹配**：milvus v2.4.6 的 `MINIO_ACCESS_KEY/SECRET` 环境变量**不覆盖**镜像自带 `milvus.yaml` 的默认凭据（minioadmin/minioadmin），而共享 minio 密码已改。→ 导出镜像默认 yaml → 改 minio.secretAccessKey → compose 挂载覆盖。证据：`docker exec` 读 yaml + 签名错误日志。
3. **成绩单结构化提取为空**：`_COURSE_LINE_RE` 用整行 `$` 锚定单组，真实成绩单是表格 3 列拼行（`课程名 性质 学分 成绩` ×3/行）。→ 重写为 `finditer` 行内多组 + 分隔符仅空格类（防跨行拼入学期行），兼容三列简式。证据：真实 PDF 实测 71 门、无误配；单测 7 passed。
4. **minio `put_object` 传 bytes 必炸**：SDK 要求类文件对象，`'bytes' object has no attribute 'read'`，导致每次上传静默降级本地（旧容器层 rebuild 后丢失，下载 404）。→ `BytesIO` 包装。证据：宿主直连 put 复现→修复后 `report-artifacts` 落桶 38 对象 + 下载 HTTP 200。
5. **batch_id 对账不一致**：SSE 外壳 `rb_*`（落盘目录）vs 落库 `b_*`（merge 生成），前端无法对账。→ 工具结果携带 batch_id，done 事件以落库为准，student_done 原样透传。

## 测试与验证

- 已执行：
  - 单测：`python -m pytest tests/ -m "not slow"` = **235 passed, 4 deselected**（W-A~W-J 新增 111 个，含 minio/llm 默认行为/解析合并/填表防线/反幻觉/API SSE/记忆/评估 runner）
  - Docker 全服务健康：mysql/redis/minio(healthy)/milvus/etcd/python-api，health `deps` 三项 true
  - 重灌三管道：course 338 门/1352 chunks；handbook 221 chunks；transcript 3 chunks（**71 门课程结构化落 metadata_json**，user 分区隔离）
  - evaluation 端到端：SSE 事件序（stage×4→radar→comment_token→done）正确；5 维 LLM 提案 status=llm；评语数值核验放行（只引真实数据：85.85/100%/99/144.5/60）；落库 evaluation_id=1；`/evaluation/me` 返回本人记录
  - report 端到端：四决策点循环事件完整；**38 份 PDF**（容器内 WeasyPrint+中文字体成功）；token 下载 HTTP 200 / `%PDF` 魔数 / 259KB；report_artifacts 落库与 done.batch_id 一致
- 未执行及原因：
  - 真实 MCP 连接（tavily/即梦/E2B）：凭据未到位，按用户指示用假 MCP 服务器覆盖（14 passed）
  - qwen3-vl-plus多模态输入冒烟：中转站兼容性未验证，留退路 `qwen3-vl-plus-2025-12-19`（settings 一行切换）
  - course 全量 500 门摄入：embedding 外部 API 限速导致超时，用户确认 338 门够用
  - 技能 SKILL.md 按 C 方案补回（触发词/来源纪律/writing 迭代）：待办中

## 经验与后续

- 本轮经验：
  - 容器环境与宿主机差异是最大的坑：minio secret 长度、milvus yaml 优先于 env、镜像内 apt 源不可达、trixie 包名变化（`libgdk-pixbuf2.0-0`→`libgdk-pixbuf-2.0-0`）——这些在宿主单测全部绿的情况下只有 docker 验收能暴露，证明"本地绿 ≠ 容器绿"
  - SDK 隐性契约（put_object 要类文件对象）需在首轮集成时就用真实 SDK 冒烟，而不是依赖 mock（fake client 兼容 bytes 掩盖了真实缺陷）
  - 幂等设计（upsert/水位/Journal）让中断重试成本为零：摄入超时、容器重建后重跑均无副作用
  - "静默降级"是双刃剑：本地兜底保证了流程不断，但也掩盖了 MinIO 从未真正写入的事实——兜底路径需要可观测性（is_local_only 日志/指标）
- 后续建议：
  - 外部凭据到位后：MCP 真连冒烟 + qwen3-vl-plus多模态验证（或切 vl 备选）
  - 技能 SKILL.md 按 C 方案补回触发词与来源纪律
  - 端到端评测（eval runner --live + LangSmith evaluator）在 Phase 4 全量实施，Phase 2 的 trace 埋点已就绪
  - 长连接/慢任务（report 40 学生 ≈ 5 分钟）前端需断线重连语义；批量吞吐优化（如 fill 并发调参）留待真实负载数据

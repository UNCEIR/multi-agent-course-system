# Phase 3 扩展实施 + 门户聚合 / 持久会话 / 轻量认证 / 视觉升级（2026-08-16）

## 背景与问题

- **Phase 3 本轮要解决的问题**：① 调研发现的注册中心与 spec 白名单不一致（`image_generate_get` 未注册、`compute_weighted_grade` stub、evaluation 三函数未工具化）；② eval oracle 与真实数据未对齐（kb_retrieval 0/10）；③ 前端仅 2 页且调用了已删除的 4 个 404 端点；④ 前端需从 Vite SPA 迁移到服务端渲染框架（调研后定 Next.js）；⑤ 记忆管理需深化（summary_prompt 五字段 / forked worker / consolidation / checkpoint_backend）。
- **Phase 3.5 用户诉求**：入口页聚合智能体列表（学生/老师注册登录后跳转）；**用户对话不能因智能体切换/页面跳转而丢失**，可开新对话、可看历史会话（C 端 Chat 体验）；导航栏整合监控、A/B 实验等；页面美术升级为科技感校园风、淡蓝主色调。
- **影响范围**：后端（auth/sessions/工具注册/eval runner/记忆），前端整体重建（Next.js 16 + 8 页面 + 全局状态），文档（plan.md/AGENTS.md/计划文档）。

## 总体架构方案

- **涉及模块**：
  - 后端：`agent/runtime.py`（工具注册）、`tools/report|evaluation`（stub 实装与 @tool 化）、`models/schemas.py`+`api/recommend.py`（mode 透传）、`eval/runner.py`+`eval_sets/*`（oracle 对齐）、`agent/main/factory.py`+`agent/memory/*`（记忆深化）、`api/auth.py`+`auth/tokens.py`+`storage/mysql/user_repo.py`（轻量认证）、`api/chat.py`+`chat_session_repo.py`（会话管理端点）。
  - 前端：`frontend/` 整目录重建为 **Next.js 16（App Router, React+TSX）**；`lib/api.ts`+`lib/sse.ts` 客户端层；`stores/auth.ts`+`stores/session.ts` 全局状态（localStorage 持久）；8 页面（Hub/chat/recommend/report/evaluation/documents/experiments/monitor/login）。
- **数据流/调用链**：
  - 登录：`/login` → `POST /auth/register|login`（HMAC token）→ localStorage → Hub `/` → 点卡片进各智能体页。
  - 持久会话：`chat` 页 ↔ `useSessionStore`（全局+localStorage）↔ `GET /chat/sessions`（列表）/`GET /chat/sessions/{sid}/messages`（回显）/chat/stream（写）→ MySQL `chat_sessions/chat_messages`（user_id 分区）→ 刷新/跳转不丢。
  - 智能体隔离保持既有四层：checkpoint 隔离（main agent 独享 SqliteSaver）、工具白名单（AgentSpec.allowed_tools）、ContextVar user_id 注入、存储分区（chat_sessions/记忆/评价均按 user_id）。
- **关键设计取舍**：
  - 前端选型：Next.js（React 生态 SSR，现有 React/antd/zustand 资产零重写；Nuxt 需 Vue 重写被否）；`app/api/` 仅作 BFF 预留（决策 22，零代理逻辑），SSE 流式保持前端直连 Python。
  - 轻量认证范围声明：登录态只服务"注册登录→入口页"体验闭环，**业务接口维持 user_id 临时口径**（Java 身份体系落地时统一替换），避免全量接口大改。
  - 会话软删（status='closed'）而非硬删，保留记忆提取水位。
  - 验收策略：LLM 算力受限 → 真实端测全部延后，以确定性单测 + build + mock 路径验收，未来资源充足时补跑 live eval 回填报告。

## 细节实现

- **关键文件**：
  - `runtime.py` 注册补 `image_generate_get` + evaluation 三工具；`tools/evaluation/tool_wrappers.py`（@tool 薄壳，只包数据入参，llm/on_token 不进 schema）。
  - `compute_weighted_grade.py` 按 docstring 公式实装（display×0.3+exam×0.7+bonus，clamp 防 NaN）。
  - `test_tool_registry_consistency.py`：AST 解析 runtime.py 真实注册清单，锁死 spec 白名单 ⊆ 注册表（防静默缺失再犯）。
  - `eval/runner.py`：`_live_report_math` 重写为消费 `/api/v1/report` SSE；`_live_evaluation(case)` 参数化 + `status_ok/comment_length/error` 字段；`count_ge/count_le` 支持数字；live 分派 try/except 兜底；`_smoke_output` 合并重构。
  - `scripts/refresh_kb_retrieval_oracle.py`：MySQL 采集真实 chunk_id 回填（数据缺失显式跳过，不写假值）。
  - 记忆：`prompts/summarization.txt` 五字段（GOAL/PROGRESS/KEY DECISIONS/NEXT STEPS/CRITICAL CONTEXT）；`MemoryExtractWorker` 隔离提取；`consolidation.py`（确定性去重落库 + 超限 LLM 合并 + 失败仅去重）；`checkpoint_backend` 配置分支（redis 依赖缺失显式 RuntimeError）。
  - 前端：`lib/sse.ts`（共享 SSE 消费器）、`lib/api.ts`（auth/sessions/recommend/chat/report/evaluation/documents 统一客户端）、`stores/auth.ts`+`stores/session.ts`（localStorage 持久化）、`globals.css`（学院蓝 #2E6FBF + 电光青 #14B8A6 + 淡蓝渐变 + 实验室网格 + 玻璃卡片）、`lib/theme.ts`（antd ConfigProvider 共享 token）、chat 页左侧会话栏（新对话/历史/切换/重命名/删除/回显）。
- **核心逻辑**：会话列表 title 为空时由 SQL 子查询取首条 user 消息作显示名；越权隔离统一 403（session_owner 校验）；HMAC token 过期与篡改校验；会话 store 按 userId 键隔离 localStorage。
- **兼容与风险控制**：async @tool 用 `ainvoke`（`.func` 为 None）；echarts 组件 useEffect 内 init（SSR 安全）；全部交互组件 `'use client'`；`prefers-reduced-motion` 支持保留。

## Debug 结论

1. **注册静默缺失**：`image_generate_get` 已定义/导出/白名单引用，但 runtime 注册清单遗漏 → `registry.get_all` 静默跳过。修复：补注册 + AST 一致性测试锁死。
2. **评审发现算术错**：`compute_weighted_grade` 测试期望 60×0.3+80×0.7+5=**79.0**（非 70.0）→ 两份计划文档同步修正。
3. **create-next-app 版本冲突**：@latest 16.3.1 要求 node ≥ 20.9，旧 engines 允许 18.18 → 固定 16.3.1 + engines 收紧 `^20.9.0 || >=22.0.0`。
4. **async @tool 的 `.func` 为 None**（sync 的才有）→ 测试改用 `.ainvoke(...)`/`.coroutine`。
5. **`_smoke_output` 重构破坏反例语义**：通用回填覆盖了 evaluation_comment 的 `input.comment` → 幻觉反例不再被拦 → 对 `t=="evaluation_comment"` 且 `field=="comment"` 跳过回填。
6. **API 测试 patch 时序**：patch 上下文在 `TestClient` 构造时退出（请求惰性执行）→ 改为 fixture 在 `yield` 期间保持 patch。
7. **误操作 `Set-Content` 覆盖 chat.py**（仅剩一个端点）→ `git checkout` 恢复后重新用 edit 追加会话端点。经验：整文件写入必须用 write/edit 工具，避免 shell 重定向。
8. **TS 类型缺口**：`StreamDonePayload` 缺 `user_id`、`ChatItem.tools` 必填、`'use client'` 必须文件最顶 → 逐项补齐。

## 测试与验证

- **已执行**：
  - 后端 `pytest tests/ -m "not slow"`：Phase 3 后 **267 passed**；Phase 3.5 后 **281 passed, 4 deselected**（新增 auth 6 + sessions api 5 + session repo 扩展 3）。
  - eval smoke 全量：chat_intent 20/20、report_math 10/10、kb_retrieval 10/10、web_search 5/5、image_generate 5/5、evaluation_comment_live 6/6、report_math_live 2/2（evaluation_comment 8/10 中 2 个失败为幻觉反例被正确拦截，符合设计）。
  - 前端 `npm run build` 通过：9 路由（/ /chat /recommend /report /evaluation /documents /experiments /monitor /login）。
  - 失效端点 grep 清零；compileall 全通过。
- **未执行及原因**：真实 LLM 端测（live eval、真实对话、report PDF 下载、evaluation 生成）——上游 LLM 算力受限，按验收策略延后，算力允许时以 `eval/runner.py --live` 补跑并回填 `eval/reports/`；`refresh_kb_retrieval_oracle.py` 实际回填（MySQL 未运行，脚本验证过优雅跳过路径）；`npm run dev` 逐页人工冒烟（仅 build 级验证）。

## 经验与后续

- **本轮经验**：① 注册/白名单类"静默缺失"必须用一致性测试锁死（AST 读真实实现，避免测试与实现手工重复）；② 前端迁移大项目优先"备份→重建→逐文件适配→build 验证"，复用既有 React 资产零重写；③ 会话持久化的数据底座（chat_sessions/messages 按 user 分区）早已就绪，前端全局 store + localStorage + 后端列表 API 即可补全 C 端体验；④ 大量硬编码色的主题改造用"映射表批量替换 + 主题变量 + ConfigProvider"三步走，避免逐文件手改。
- **后续建议**：① 上游算力充足后按 plan 补 live eval 并回填报告（llm-as-judge 属 Phase 4）；② MySQL 启动后执行 `refresh_kb_retrieval_oracle.py` 回填 kb_retrieval 真实 chunk_id；③ Java 数据服务落地时以轻量认证为基准统一身份体系（token 接口已就位）；④ 管理平台（独立 React 项目）可与前端共享 `lib/theme.ts` 设计 token；⑤ PPT/图片独立页/FastGPT 桥接按 plan.md 后续 phase 输入清单推进。

# pi Skill/Tool/Harness 调研 → 本项目移植优化方案（2026-09-01）

> 研究目标：深挖 `E:\Agent\pi` 的「会话压缩 / 渐进式 Skill 加载 / 工具调用兜底与链式 / 工具意图识别 / Harness 编排」，
> 并把可借鉴思想**移植为本项目（mult-agent-university-system）的落地优化方案**。
> 来源：4 个只读 subagent（Kuhn=压缩、Helmholtz=Skill、Chandrasekhar=工具链、Lovelace=意图识别）。
> 关联：记忆/compaction 部分详见 `2026-08-31-pi-memory-compaction-mapping.md`；本文件侧重 Skill/Tool/Harness 与优化方案。

---

## 1. pi 各能力结论（一句话）

| 能力 | pi 做法 |
|---|---|
| 会话压缩 | 三路触发（阈值/溢出/手动）+ provider-usage 优先估算 + 安全切点 + split-turn 前缀摘要；CompactionEntry 自包含 checkpoint append-only 落树；LLM 失败=中止+显式 error，**无降级摘要** |
| 渐进式 Skill | 「索引常驻（name+description+location XML）+ read 按需读全文 + `/skill:name` 显式兜底」三层；`hasRead` 门控；`disable-model-invocation` 受控暴露 |
| 工具执行 | preflight（解析→校验→before 拦截）串行、执行并行；失败统一转 isError toolResult 回喂模型自纠；`stopReason=length` 整批不执行；重试只在模型层（黑白名单分类） |
| 链式 | 双层循环：toolResult 一等消息回写上下文→再请求 LLM；steer（打断）/followUp（收尾）双队列，注入必须在 turn 边界；terminate 需批内全 true |
| 意图识别 | **无显式路由**，靠模型按 description 自选；三层描述（description/promptSnippet/promptGuidelines 点名消歧）+ schema strict 强约束 + 校验错误三件套驱动自纠 |
| Harness | turn 快照不可变 + save point flush + phase 锁；配置入历史；类型化事件钩子（context/tool_call/tool_result） |

---

## 2. 移植优化方案（核心交付：pi 思想 → 本项目优化动作）

> 本项目现状对照（已核实）：`python/tools/registry.py`（ToolRegistry + register_many + allowlist）、`tools/circuit_breaker.py`、
> `python/agent/main/factory.py`（deepagents `SummarizationMiddleware`，摘要只存 checkpoint）、`python/agent/memory/`（extractor/injector/consolidation）、
> `python/agent/main/prompt.py`（教师端意图路由表）、`MAIN_AGENT_SPEC.allowed_tools`（16 工具）、`python/skills/`（SkillsMiddleware 渐进式加载）。

### A. 会话压缩：compact 落库 + 兜底（对应记忆文档 P0，本文件补充）

| pi 机制 | 本项目现状 | 优化动作 | 涉及文件 | 优先级 |
|---|---|---|---|---|
| threshold/overflow 双触发 + 单次恢复 | 仅 `agent_compaction_trigger_messages=8` | 新增 `estimate_context_tokens`（provider usage 优先 + 尾部估算；中文按 chars/2 或复用 usage_json.total_tokens）+ `should_compact`；`_overflow_recovery_attempted` 单次 compact-and-retry；时间戳防抖 | `python/agent/memory/tokens.py`(新)、`config/settings.py`、`factory.py` | P0 |
| CompactionEntry 落库自包含 | 摘要只在 checkpoint 图状态 | `chat_session_compactions` 表（summary/prev_compaction_id/first_kept_message_id/tokens_before/after/usage_json/details_json/status/reason）+ 写后同步（compact 完成后复制落库，失败仅告警不阻塞） | `sql/init-db.sql`、`storage/mysql/chat_session_repo.py`、`agent/memory/compaction.py`(新) | P0 |
| UPDATE 增量合并 | SummarizationMiddleware 每次重新摘要 | 移植 `summarization_update.txt`（`<previous-summary>` 注入，保留+增补+搬家+可删） | `agent/main/prompts/summarization_update.txt`(新)、`agent/memory/compaction.py` | P0 |
| **LLM 失败兜底** | 无（LLM 挂则压缩失败） | **确定性兜底**：LLM 失败/超时 → 规则式截断（最旧 N 条 + 保留最近）+ `status='fallback'` 标记；显式结构化 error 事件，不静默断流 | `agent/memory/compaction.py`、`services/sse_event_buffer.py` | P0 |

### B. Skill 渐进式加载 + 每 agent 记忆点

| pi 机制 | 本项目现状 | 优化动作 | 涉及文件 | 优先级 |
|---|---|---|---|---|
| 索引/正文分离 + hasRead 门控 | SkillsMiddleware 已有渐进式雏形 | 统一为「常驻=name+description 索引、命中再读全文」；按 `AgentSpec.allowed_tools` 是否有知识读取工具决定是否注入技能索引（5 spec 天然过滤） | `agent/main/factory.py`、`agent/main/specs.py` | P1 |
| description 硬门槛（必填/≤1024/命名） | skills 无加载期校验 | 加中文 description 模板（做什么/何时用/何时不用）+ 加载期校验 + 单测 | `python/skills/README.md`、`tools/registry.py`、tests | P1 |
| `disable-model-invocation` 受控暴露 | 无 | 敏感技能（成绩单写库/审批）设模型不可见、仅显式触发 | `python/skills/*/SKILL.md` | P1 |
| **每 agent AGENTS.md 记忆点** | 只有 main_agent 读 `python/memories/AGENTS.md`（只读） | `chat_memory_entries` 加 `agent_name` 列，UNIQUE 改 `(user_id, agent_name, kind, content_hash)`；每 `AgentSpec.name` 初始化记忆点；注入按 agent_name 过滤 | `sql/init-db.sql`、`storage/mysql/chat_session_repo.py`、`agent/memory/injector.py`、`agent/main/specs.py` | P1 |
| 长记忆点技能化（AGENTS.md 279→159 实证） | AGENTS.md 规则+操作清单混放 | 分层：决策性规则常驻，操作清单抽成技能（如 recommend-courses 的流程步骤） | `python/memories/AGENTS.md`、`python/skills/*` | P2 |

### C. 工具调用兜底 / 链式 / 意图识别

| pi 机制 | 本项目现状 | 优化动作 | 涉及文件 | 优先级 |
|---|---|---|---|---|
| preflight（校验/拦截）串行 + 执行并行 | ToolRegistry 无 before/after 钩子 | ToolRegistry 增加 `before_tool_call`（circuit breaker/权限/风控拦截，返回 `{block, reason}`）+ `after_tool_call`（成功/失败/耗时记账）横切点；block 的短路成 isError 回喂 | `tools/registry.py`、`tools/circuit_breaker.py`、`agent/runtime.py` | P1 |
| 失败统一 isError 回喂，不吞异常 | @tool 部分自行 try/except | 约定「失败 throw 或显式 isError，禁止把错误文案当成功 content」；校验错误三件套：`Validation failed for tool "X": - field.path: reason\nReceived arguments: {...}` | `tools/registry.py`、各 @tool | P1 |
| 同工具连续失败上限 | 无（模型可无限重发选错） | main_agent 外层加「同工具连续失败 ≥2~3 次 → 强制换策略或终止」护栏 | `agent/main/agent.py` | P1 |
| coerce 优先宽容校验 | pydantic 严格校验 | 入参先类型转换（string→number/bool）再严格校验；`strict: require` 用于参数必须精确的工具（query_transcript/recommend_courses） | `tools/registry.py` | P2 |
| per-tool `sequential` 强制整批串行 | 无 | 写类/读后写 @tool（如推荐落库、报告批次）声明串行，避免并行写竞态 | `tools/registry.py` | P2 |
| description=意图说明书（点名消歧） | description 一般化 | `query_transcript`/`query_handbook` 等 description 互相点名：「问我的成绩用 query_transcript；问公开手册用 query_handbook」；每个 allowed tool 加一行 promptSnippet 式索引 | `tools/knowledge/*`、`tools/recommend/*`、`agent/main/prompt.py` | P1 |
| 小候选集 + 激活集变更重建 system prompt | allowed_tools 16 个固定 | 按角色/轮次子集化（教师端/学生端各一小批），路由表判不了才落回模型自选；allowed_tools 变更时同步重建 system prompt | `agent/main/specs.py`、`agent/main/prompt.py` | P2 |

### D. Harness 横切（可选，后续）

| pi 机制 | 优化动作 | 优先级 |
|---|---|---|
| steer/followUp 双队列、turn 边界注入 | 用户中途追问实现为 turn 边界注入，不直接插 context（防 tool_use/tool_result 配对错乱） | P2 |
| abort 贯穿全链路 | SSE 取消透传到每个 @tool（signal），并行批次僵尸任务可收 | P2 |
| 配置入历史 | `model_change`/工具集变更作为会话条目（可审计回滚） | P3 |

---

## 3. 落地顺序与验收口径

1. **P0-1 压缩落库 + 兜底**：`chat_session_compactions` 表 + 写后同步 + 规则式 fallback。验收：compact 后 `SELECT * FROM chat_session_compactions` 有结构化记录；LLM 挂时 status='fallback' 且上下文不崩。
2. **P0-2 增量合并 + token 估算**：`summarization_update.txt` + `estimate_context_tokens/should_compact` 单测（mock usage / 纯字符两路）。
3. **P1-1 工具横切**：ToolRegistry before/after 钩子 + isError 约定 + 校验三件套 + 同工具失败上限。验收：熔断/权限拦截返回可读 reason；SSE 结构化 error；测试覆盖「并行 3 工具 1 失败 → 2 成功按源序返回」。
4. **P1-2 意图说明书 + 每 agent 记忆点**：description 点名消歧 + `chat_memory_entries.agent_name`。验收：query_transcript/query_handbook 描述互相点名；每 spec 注入自己的记忆点。
5. **P2**：coerce 校验 / sequential 逃生口 / 候选集子集化 / steer-followUp / abort 透传。

## 4. 移植 5 个坑

1. **pi 无降级摘要**：LLM 不稳定时压缩会失败——本项目必须预置规则式 fallback（已在 A 列 P0）。
2. **中文 token 估算**：`chars/4` 对中文低估 2~4 倍，触发过晚——用 `usage_json.total_tokens` 或 CJK 系数。
3. **`allowed-tools` 是 pi 文档字段、代码零实现**：移植前 grep 代码确认，别信规范文档；同理 docs 与代码不一致处以代码为准。
4. **@tool 别吞异常当成功**：否则 isError 无法识别、SSE 无法给结构化 error；重试（模型层重发）会让同一工具执行两次，@tool 要幂等或容忍重复。
5. **自定义 system prompt 会丢工具清单**：本项目 `prompt.py` 是自定义 system prompt，务必手动拼「当前可用工具」段（否则模型只靠 schema description，看不到索引）。

## 5. 一句话结论

pi 证明：**「索引常驻/正文按需的渐进披露 + 确定性 preflight 拦截 + 统一 isError 回喂自纠 + strict schema 强约束 + 压缩自包含 checkpoint + 显式命令兜底」**这套骨架，与本项目「ToolRegistry + @tool + args_schema + circuit breaker + SkillsMiddleware + SSE done/error」高度互补；
真正要自建的是：**压缩落库与 fallback 兜底、工具横切钩子（before/after）、意图说明书式 description、每 agent 记忆点（agent_name）**——即本文件 A/B/C 三组 P0/P1 优化。

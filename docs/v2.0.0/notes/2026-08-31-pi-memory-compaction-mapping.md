# pi 会话记忆/Compaction 调研 → 大学平台落地对照（2026-08-31）

> 研究目标：深挖 `E:\Agent\pi`（TS 多智能体平台）的会话记忆、compaction、条目树与 skills/AGENTS.md 机制，
> 为大学平台「会话级记忆 + 用户级总记忆 + 短期 checkpoint 塞满时 compact 落库 chat 表」的分层记忆设计提供可执行依据。
> 来源：4 个只读 subagent 调研（session/memory、skills、tools、harness）+ 1 个深挖 agent（compaction prompt/schema）。
> 本文件只沉淀「记忆/compaction」部分；skills/tools/harness 的可借鉴点见文末速查。

---

## 1. pi 记忆机制结论（一句话版）

- **会话 = append-only 条目树（session tree）**，按 cwd 隔离（无用户概念）；短期记忆 = 整棵树随轮次 append。
- **上下文构建 = 沿树路径回溯到 compaction 边界**（纯函数 `f(tree, leaf, compactionBoundary)`），原始消息永不删除。
- **compaction = 「摘要 + 保留尾部」作为一个新条目追加进同一棵树**（自包含 checkpoint），恢复时只读「摘要行 + 之后的行」。
- **pi 没有任何用户级/跨会话长期记忆**；唯一跨会话记忆 = 静态 `AGENTS.md/CLAUDE.md` 项目上下文文件（只读、无写回管线）。
- `memory-repo/memory-storage` 是**内存版会话存储**（测试/SDK 用），不是长期记忆。

---

## 2. compaction 摘要 prompt 全文（可直接移植）

### 2.1 `SUMMARIZATION_SYSTEM_PROMPT`（所有摘要请求共用 system prompt）
```text
You are a context summarization assistant. Your task is to read a conversation between a user and an AI assistant, then produce a structured summary following the exact format specified.

Do NOT continue the conversation. Do NOT respond to any questions in the conversation. ONLY output the structured summary.
```

### 2.2 `SUMMARIZATION_PROMPT`（首次 compact 主模板；注意是六节）
```text
The messages above are a conversation to summarize. Create a structured context checkpoint summary that another LLM will use to continue the work.

Use this EXACT format:

## Goal
[What is the user trying to accomplish? Can be multiple items if the session covers different tasks.]

## Constraints & Preferences
- [Any constraints, preferences, or requirements mentioned by user]
- [Or "(none)" if none were mentioned]

## Progress
### Done
- [x] [Completed tasks/changes]

### In Progress
- [ ] [Current work]

### Blocked
- [Issues preventing progress, if any]

## Key Decisions
- **[Decision]**: [Brief rationale]

## Next Steps
1. [Ordered list of what should happen next]

## Critical Context
- [Any data, examples, or references needed to continue]
- [Or "(none)" if not applicable]

Keep each section concise. Preserve exact file paths, function names, and error messages.
```
> 对大学平台的关键：`Constraints & Preferences` 节是「用户级习惯/偏好提取」最直接可复用的来源；
> 我们 `python/agent/main/prompts/summarization.txt` 目前只有五节（GOAL/PROGRESS/KEY DECISIONS/NEXT STEPS/CRITICAL CONTEXT），缺这一节、且 Progress 无 Done/In Progress/Blocked 子节。

### 2.3 `UPDATE_SUMMARIZATION_PROMPT`（迭代增量合并模板）
```text
The messages above are NEW conversation messages to incorporate into the existing summary provided in <previous-summary> tags.

Update the existing structured summary with new information. RULES:
- PRESERVE all existing information from the previous summary
- ADD new progress, decisions, and context from the new messages
- UPDATE the Progress section: move items from "In Progress" to "Done" when completed
- UPDATE "Next Steps" based on what was accomplished
- PRESERVE exact file paths, function names, and error messages
- If something is no longer relevant, you may remove it

Use this EXACT format:

## Goal
[Preserve existing goals, add new ones if the task expanded]

## Constraints & Preferences
- [Preserve existing, add new ones discovered]

## Progress
### Done
- [x] [Include previously done items AND newly completed items]

### In Progress
- [ ] [Current work - update based on progress]

### Blocked
- [Current blockers - remove if resolved]

## Key Decisions
- **[Decision]**: [Brief rationale] (preserve all previous, add new)

## Next Steps
1. [Update based on current state]

## Critical Context
- [Preserve important context, add new if needed]

Keep each section concise. Preserve exact file paths, function names, and error messages.
```
> 调用模式（pi compaction.ts L567-577）：`previousSummary ? UPDATE_... : SUMMARIZATION_...`；
> 旧摘要经 `<previous-summary>...</previous-summary>` 注入；摘要输出上限 = `0.8 * reserveTokens`。

### 2.4 `TURN_PREFIX_SUMMARIZATION_PROMPT`（split-turn：切点落在进行中轮次时，前缀单独摘要）
```text
This is the PREFIX of a turn that was too large to keep. The SUFFIX (recent work) is retained.

Summarize the prefix to provide context for the retained suffix:

## Original Request
[What did the user ask for in this turn?]

## Early Progress
- [Key decisions and work done in the prefix]

## Context for Suffix
- [Information needed to understand the retained recent work]

Be concise. Focus on what's needed to understand the kept suffix.
```

### 2.5 `BRANCH_SUMMARY_PREAMBLE` + `BRANCH_SUMMARY_PROMPT`（分支摘要）
```text
# BRANCH_SUMMARY_PREAMBLE
The user explored a different conversation branch before returning here.
Summary of that exploration:

# BRANCH_SUMMARY_PROMPT（五节，无 Critical Context）
Create a structured summary of this conversation branch for context when returning later.

Use this EXACT format:

## Goal
## Constraints & Preferences
## Progress
### Done / ### In Progress / ### Blocked
## Key Decisions
## Next Steps

Keep each section concise. Preserve exact file paths, function names, and error messages.
```

---

## 3. 条目树 schema（pi 核心数据结构）

### 3.1 11 种 `SessionTreeEntry`（基类：`{ type, id, parentId, timestamp }`）

| # | type | 关键字段 | 是否进模型上下文 |
|---|---|---|---|
| 1 | `message` | `message: AgentMessage` | 是 |
| 2 | `thinking_level_change` | `thinkingLevel` | 否（派生 `SessionContext.thinkingLevel`） |
| 3 | `model_change` | `provider` / `modelId` | 否（派生 `SessionContext.model`） |
| 4 | `active_tools_change` | `activeToolNames[]` | 否（派生 `SessionContext.activeToolNames`） |
| 5 | `compaction` | `summary / firstKeptEntryId? / tokensBefore / retainedTail? / details? / usage? / fromHook?` | 是（→ `compactionSummary` 角色消息） |
| 6 | `branch_summary` | `fromId / summary / details? / usage?` | 是（→ `branchSummary` 角色消息） |
| 7 | `custom` | `customType / data?` | **否**（需 `entryProjectors` 才进上下文） |
| 8 | `custom_message` | `customType / content / display` | **是**（→ `custom` 角色消息） |
| 9 | `label` | `targetId / label?` | 否（会话命名） |
| 10 | `session_info` | `name?` | 否（legacy 会话命名） |
| 11 | `leaf` | `targetId: string \| null` | 否（记录当前叶子） |

### 3.2 `CompactionEntry`（自包含 checkpoint）
```ts
interface CompactionEntry {
  type: "compaction";
  summary: string;              // 压缩后历史摘要
  firstKeptEntryId?: string;    // 保留历史开始处 entry id
  tokensBefore: number;         // 压缩前估算 token
  retainedTail?: AgentMessage[]; // 近期保留消息（存在时上下文重建优先用它，不再回溯旧条目）
  details?: { readFiles: string[]; modifiedFiles: string[] }; // 文件操作清单
  usage?: Usage;                // 摘要 LLM usage（可观测）
  fromHook?: boolean;
}
```

### 3.3 上下文重建（`defaultContextEntryTransform`）
```
上下文 = [compaction 摘要消息] + [retainedTail 或 firstKeptEntryId 起的保留条目] + [compaction 之后的条目]
```
摘要消息角色由 `createCompactionSummaryMessage(summary, tokensBefore, timestamp)` 生成（`role="compactionSummary"`，外包 `<summary>` 标签）。

### 3.4 SQLite 表结构（`packages/storage/sqlite-node/.../001_initial.sql`）
- `sessions(id PK, created_at, cwd, parent_session_id, metadata, active_leaf_id)`
- `session_entries(session_id, id, entry_seq, parent_id, type, timestamp, payload, PK(session_id,id))` + UNIQUE(session_id, entry_seq)
- `session_sequences(session_id PK, next_seq)`
- `branch_entries(session_id, branch_id, entry_id, entry_seq)`（物化分支路径）
- `session_materialized / entry_materialized`（上下文组装缓存，按 seq/type 增量重建）

### 3.5 存储接口（可移植）
`SessionStorage`：`getMetadata / getLeafId / setLeafId / createEntryId / appendEntry / getEntry / findEntries / getLabel / getSessionName / getSessionStats / getPathToRootOrCompaction / getEntries`。
`SessionRepo`：`create / open / list / delete / fork`。
> 领域层只依赖接口，存储实现（JSONL/SQLite/内存）可插拔 —— 大学平台可把 `chat_messages` 包成等价的「entry 接口」。

---

## 4. 对照表：pi → 大学平台（可直接落地）

### 4.0 大学平台现状速览（已核实）

| 文件 | 现状 |
|---|---|
| `python/config/settings.py` | `agent_context_window_tokens=128000`；`agent_compaction_trigger_tokens=None`（None→ctx-13000）；`agent_compaction_keep_tokens=20000`；`agent_compaction_trigger_messages=8`（demo）；`memory_extract_threshold_messages=20`；`memory_extract_max_messages=200`；`memory_extract_retry_after_seconds=600`；`memory_entries_per_user_limit=50`；`memory_consolidate_threshold_per_kind=15` |
| `sql/init-db.sql` | `chat_sessions(session_id,user_id,title,message_count,last_extracted_seq,last_failure_at,status)`；`chat_messages(id,session_id,user_id,seq,role[user\|assistant\|tool],content,tool_calls_json,usage_json)`；`chat_memory_entries(user_id,kind[preference\|fact\|decision],content,content_hash,source_session_id)` |
| `python/agent/main/factory.py` | deepagents `SummarizationMiddleware(trigger=("messages",8)|("tokens",ctx-13000), keep=("tokens",20000), summary_prompt=summarization.txt)`；摘要存 **checkpoint 图状态内，不落 chat 表**；main_agent 对 `/memories/AGENTS.md` 写权限 deny |
| `python/agent/main/prompts/summarization.txt` | 五节，缺 Constraints & Preferences、缺 Progress 三子节 |
| `python/agent/memory/` | extractor（≥20 未提取 → LLM 提取 preference/fact/decision → `chat_memory_entries`，水位+退避）；consolidation（NFKC 去重 + kind>15 LLM 合并）；injector（首轮注入 user 最近 ≤50 条/≤2000 字符） |

### 4.1 主对照表

| pi 概念 | pi 做了什么 | 大学平台落地改动 | 优先级 |
|---|---|---|---|
| **compaction 即条目** | `CompactionEntry`（summary+firstKept+retainedTail+tokensBefore+usage）自包含 checkpoint | 新建 **`chat_session_compactions`** 表（compaction_seq, session_id, summary, first_kept_seq, retained_tail_json, tokens_before, usage_json, details_json, from_hook, created_at, UNIQUE(session_id,compaction_seq)）+ repo 接口 + 上下文组装改「最新 summary + seq>first_kept 之后消息」 | **P0** |
| **UPDATE 增量合并** | `UPDATE_SUMMARIZATION_PROMPT` + `<previous-summary>` 注入 | 移植 `summarization_update.txt`；二次 compact 取 `compaction_seq-1` 的 summary 作 previousSummary | **P0** |
| **token 估算** | provider usage 优先 + 字符兜底；`shouldCompact = tokens > window - reserveTokens` | 新建 `python/agent/memory/tokens.py`：`estimate_context_tokens` + `should_compact`；中文按 `chars/2` 或复用 `usage_json.total_tokens` | **P0** |
| **scope 分层** | 会话内 compaction vs 跨会话记忆分离 | 会话级 = `chat_session_compactions`；用户级 = 现有 `chat_memory_entries`；新会话首轮注入 = 用户级记忆 + 可选被引用旧会话 compaction 摘要 | **P0** |
| **存储接口化** | `SessionStorage/SessionRepo` 接口隔离 | chat repo 增加 `append_compaction/get_latest_compaction/list_compactions/list_entries_after_seq`；compaction 逻辑只依赖 repo 接口 | **P0** |
| **模板补节** | 六节模板 | `summarization.txt` 补 `CONSTRAINTS & PREFERENCES` + Progress 三子节；`Constraints & Preferences` 作为用户级习惯提取来源 | **P1** |
| **引用清单** | `readFiles/modifiedFiles` → `<read-files>/<modified-files>` 标签 | 从 `tool_calls_json` 提取 query_handbook/query_transcript/recommend_courses 引用 → `referenced_ids{course[],doc[],source_doc[],transcript_hit}` 写 `details_json` + `<referenced-*>` 标签 | **P1** |
| **每 agent 记忆点** | （pi 每 agent 角色卡范式） | `chat_memory_entries` 加 **`agent_name`** 列，UNIQUE 改 `(user_id, agent_name, kind, content_hash)`；每 `AgentSpec` 初始化自己的记忆点，注入按 agent_name 过滤 | **P1** |
| **触发阈值** | `reserveTokens=16384 / keepRecentTokens=20000` | 新增 `agent_compaction_reserve_tokens=16384`；demo 保留 messages=8，生产切 tokens 路径 | **P1** |
| **摘要 usage/成本** | `combineUsage` | `chat_session_compactions.usage_json` 存摘要 LLM usage（Phase 4 指标源） | **P1** |
| **条目树轻量化** | 11 种 typed entry | 最小改动：`chat_messages` 加 `entry_type VARCHAR(32) DEFAULT 'message'`、`parent_seq INT NULL`、`entry_payload JSON NULL`；label/session_info/thinking 等走 entries | **P2** |
| **Custom vs CustomMessage** | 不入上下文 vs 入上下文 | 元数据（label/thinking）走 entries；系统注入（用户记忆前缀/compactionSummary）落 `role='custom'` + `entry_payload.custom_type` | **P2** |
| **分支摘要 / fork** | branch_summary + SessionRepo.fork | 轻量等价物：继续上次会话时对旧 session 未 compact 尾部做一次摘要注入新会话（compaction_seq=-1 表示续会话摘要） | **P2/P3** |
| **物化缓存** | session_materialized/entry_materialized | 用 Redis（已有）`session_context:{session_id}` 增量缓存（key 存 last_materialized_seq），不新增 MySQL 表 | **P2/P3** |

### 4.2 建议落地顺序（含验收口径）

1. **P0-1 会话级 compaction 落库**：新建 `chat_session_compactions` 表 + repo 接口 + 上下文组装改造。验收：compact 后新轮上下文含 summary 行，`SELECT * FROM chat_session_compactions` 可查结构化记录。
2. **P0-2 增量合并**：`previousSummary` 透传 + `summarization_update.txt`。验收：第二次 compact 的 summary 保留第一次全部节与条目。
3. **P0-3 token 估算**：`estimate_context_tokens` + `should_compact` 单测（mock usage_json / 纯字符两路）。
4. **P1 模板补节**：`summarization.txt` 补 Constraints & Preferences + Progress 三子节。
5. **P1 引用 ID 清单**：从 `tool_calls_json` 提取引用写 `details_json` + `<referenced-*>` 标签。
6. **P1 用户级 + agent 级记忆点**：`chat_memory_entries` 加 `agent_name` 列；每 AgentSpec 初始化记忆点（设计目标①③）。
7. **P2 条目树轻量化**：`chat_messages` 加 entry_type/parent_seq/entry_payload 或新建 `chat_session_entries`。
8. **P3 分支摘要 / fork / Redis 物化缓存**：按需启用。

### 4.3 移植 3 个坑

- **角色模型差异**：pi `AgentMessage.role` 有 9 种；大学平台 `chat_messages.role` 仅 3 种。落 compaction 摘要建议 `role='assistant' + entry_type='compaction'`（或新 role `compaction`），避免破坏既有查询。
- **SummarizationMiddleware 摘要只在 checkpoint 内**：需在 chat 服务层「写后同步」——compact 完成后把 summary 复制进 `chat_session_compactions`；建议先落库成功再推进、失败仅告警不阻塞（对齐 extractor 的水位+退避模式）。
- **中文 token 估算**：pi `chars/4` 对中文偏乐观；建议中文按 `chars/2` 或直接复用 provider `usage_json.total_tokens`，仅无 usage 时走字符兜底。

---

## 5. 设计目标与 pi 的对应

| 用户设计目标 | pi 的启示 | 落地载体 |
|---|---|---|
| ① 同一用户不同会话不共享记忆；同一用户同一会话共享长期记忆 | 会话隔离放 storage 层；会话级记忆 = compaction 摘要（per session） | `chat_session_compactions`（会话级）+ `chat_memory_entries`（用户级）双表 |
| ② 短期 checkpoint 塞满时 compact 汇总落库到 chat 表 | compaction 即条目、retainedTail 自包含 checkpoint、UPDATE 增量合并 | `chat_session_compactions` 表 + repo + 写后同步 |
| ③ 每个智能体有自己的 AGENTS.md 式总记忆点，更新用户总习惯 | AGENTS.md 继承链 + skills 渐进披露（索引进提示、全文按需读）；pi 无写回管线需自建 | `chat_memory_entries.agent_name` 维度 + 原子写回/版本化 |

---

## 6. skills / tools / harness 可借鉴点速查（旁支）

- **Skills**：目录=能力包（SKILL.md+附属资源）；frontmatter 强制 `description` 作检索索引；渐进披露（索引进 system prompt、全文按需 read）；同名碰撞保留先者；`disable-model-invocation` 受控触发。
- **Tools**：一份 schema 三处复用（模型/校验/UI，对应 pydantic `model_json_schema()`）；before/after 钩子 = 权限+熔断+审计横切面（circuit breaker 应放钩子而非工具内）；失败回喂模型自愈（isError toolResult）；per-turn 上下文快照注入（替代全局 ContextVar）；按 key 串行写队列（file-mutation-queue）。
- **Harness**：turn 快照不可变 + save point 确定性 flush + phase 锁；配置入历史（model_change 等做成条目）；类型化事件钩子（context 注入记忆 / tool_call 权限 / tool_result 脱敏）；「不许 throw、失败编码进流」与我们的 SSE `done/error` 同构。
- **冲突点**：pi 无 user 概念 → 大学平台必须把 user_id 分区/权限/脱敏下沉到 session 与记忆存储层；pi 无跨会话提取管线 → 我们已有 `python/agent/memory/`，增量是 scope + 原子写回；pi AGENTS.md 只读 → 写回需自建原子化+版本化+冲突检测。

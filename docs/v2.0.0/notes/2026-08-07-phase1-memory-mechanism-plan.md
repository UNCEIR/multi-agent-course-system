# 记忆机制实装计划（Phase 1 deepagents memory + 意图识别 + 渐进式 skill）

## 背景与问题

- **本轮要解决的问题**：为 v2.0.0 主 agent 实装完整的记忆管理机制（短期记忆 + 长期记忆 + compaction + checkpointing），并搭建可运行 demo。
- **触发原因或用户诉求**：用户要求学习 `E:\Agent\learn-deepseek-code` 和 `E:\Agent\claude-code` 的真实记忆机制，使用 deepagents 框架的 memory 体系（FilesystemMiddleware + MemoryMiddleware + SummarizationMiddleware + SkillsMiddleware）落地实现。要求能跑多轮对话、触发 compaction、读写长期记忆、thread_id 跨会话恢复，且主 agent 意图识别后渐进式加载 skill。
- **影响范围**：`python/agent/main/`（主 agent 工厂 6 个新文件）、`python/api/chat.py`（新端点）、`python/agent/runtime.py`（主 agent 生命周期）、`python/config/settings.py`（记忆相关配置）、`python/ai/llm_task_name.py`（新 task_name）、`python/requirements.txt`（新依赖）、`python/memories/AGENTS.md`（种子长期记忆）、`docs/v2.0.0/plan.md`（Phase 3 补充）。

## 总体架构方案

### 三源学习结论

| 来源 | 学习内容 | 对齐本项目方式 |
|------|---------|--------------|
| **deepagents 0.7.5**（`D:\Anaconda\Lib\site-packages\deepagents\`） | `MemoryMiddleware`（AGENTS.md 注入 system prompt）、`SummarizationMiddleware`（compaction 落盘 `/conversation_history/{thread_id}.md`）、`FilesystemMiddleware`（大 tool result 落盘）、`SkillsMiddleware`（渐进式 skill 披露）、`CompositeBackend`（路径前缀路由）、`SqliteSaver` | 用 `create_deep_agent` 注入 middleware，`CompositeBackend` 路由 `/skills/`/`/memories/` 走真实文件 |
| **learn-deepseek-code**（`E:\Agent\learn-deepseek-code\`） | `.memory/` 文件系统 + 四层压缩管线 + consolidation | `FilesystemBackend` 真实 `.md` 文件，AGENTS.md 作为长期记忆 |
| **claude-code**（`E:\Agent\claude-code\restored-src\src\`） | `autoCompact` 阈值 `contextWindow-13000`/`MAX_OUTPUT_TOKENS_FOR_SUMMARY=20000` + forked agent 提取记忆 | compaction 阈值对齐决策 11（`trigger=("tokens", cw-13000)`, `keep=("tokens", 20000)`） |

### 关键设计取舍

- **意图识别 + 渐进式 skill**：用 deepagents 原生 `SkillsMiddleware`（无需自定义 intent-router middleware），LLM 推理匹配 skill description → `read_file` 读全文 → 按步骤执行。
- **compaction 阈值**：对齐决策 11 `contextWindow-13000`/`keepRecentTokens=20000`；demo 可降为 messages 触发（`trigger=("messages", 8)`）便于验证。
- **checkpointer 选型**：先用 `SqliteSaver`（本地 sqlite 持久），`langgraph-checkpoint-redis` 加 requirements 备用，Phase 3 切 RedisSaver。
- **长期记忆**：`MemoryMiddleware` + `FilesystemBackend` 真实 `AGENTS.md` 文件，agent 经 `edit_file` 工具更新。

## 细节实现

### 计划文件

完整计划已写入 `docs/v2.0.0/plans/phase-1-coding-plan.md`，包含：

- **Context**：为什么做的背景（v1 无状态架构 vs 决策 11+12 已定稿记忆设计）
- **设计要点**：三源学习结论（deepagents 0.7.5 memory 体系 6 个 middleware + 4 种 backend + learn-deepseek-code 4 层压缩 + claude-code autoCompact 3 个参数）
- **三源融合表**：8 个维度（短期记忆/compaction/结构化摘要/长期记忆/大 tool result 落盘/checkpointing/subagent 隔离/意图识别+skill）
- **实现方案**：16 个新增/改动文件清单 + 关键代码结构（agent.py 要点）+ 意图识别机制 + plan.md 补充内容
- **验证步骤**：5 类验证（编译/单测/端到端冒烟/v1 不破/Docker）

### 关键代码结构（agent.py 核心）

```python
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend
from deepagents.middleware.summarization import SummarizationMiddleware, SummarizationToolMiddleware

def build_main_agent():
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/skills/": FilesystemBackend(root_dir=s.skills_dir),
            "/memories/": FilesystemBackend(root_dir=s.memory_dir),
        },
    )
    llm = build_chat_openai(temperature=0.2, max_tokens=2048, task_name=LLMTaskName.MAIN_AGENT_ROUTER)
    trigger = ("messages", s.agent_compaction_trigger_messages) if s.agent_compaction_trigger_messages \
               else ("tokens", s.agent_context_window_tokens - 13000)
    summ = SummarizationMiddleware(model=llm, backend=backend, trigger=trigger, keep=("tokens", s.agent_compaction_keep_tokens))
    return create_deep_agent(
        model=llm,
        tools=[list_available_skills, get_current_time],
        backend=backend, skills=["/skills/"], memory=["/memories/AGENTS.md"],
        checkpointer=sqlite_saver, system_prompt=MAIN_AGENT_SYSTEM_PROMPT,
        middleware=[summ, SummarizationToolMiddleware(summ)],
    )
```

## Debug 结论

- **根因**：deepagents 0.7.5 没有公开文档，WebFetch 官方文档网站因企业网络限制失败。
- **排查过程**：改为直接读 `D:\Anaconda\Lib\site-packages\deepagents\` 源码（涵括 `graph.py`、`middleware/memory.py`、`middleware/summarization.py`、`middleware/skills.py`、`middleware/filesystem.py`、`backends/` 等），同时学习 `E:\Agent\learn-deepseek-code` 和 `E:\Agent\claude-code` 源码。
- **解决方式**：三源学习结论固化到计划文档，关键发现：① `SummarizationMiddleware` 的 `create_summarization_middleware(model, backend)` 工厂对无 profile 的 ChatOpenAI（deepseek 经中转站）走 `trigger=("tokens",170000)`/`keep=("messages",6)`，需手构覆盖为 `("tokens", cw-13000)`/`("tokens", 20000)`；② `SqliteSaver` 导入路径为 `from langgraph.checkpoint.sqlite import SqliteSaver`（非 `langgraph.checkpoint.sqlite.base`）；③ `SkillsMiddleware` 自动注入 skill 索引到 system prompt，无需自定义 intent-router middleware。

## 测试与验证

- **已执行**：① `pip install langgraph-checkpoint-sqlite==3.1.1` 验证通过（`from langgraph.checkpoint.sqlite import SqliteSaver` 无报错）；② `pip install langgraph-checkpoint-redis==2.0.0` 验证通过；③ `python -c "import deepagents; print(deepagents.__version__)"` 确认 deepagents 0.7.5 已安装；④ 计划内容已写入 `docs/v2.0.0/plans/phase-1-coding-plan.md` 并获用户批准。
- **未执行及原因**：代码实现尚未开始（计划刚获批），测试需实现后执行。
- **计划验证**：编译（`compileall`）、单测（mock LLM 验证多轮 invoke/thread_id 恢复/compaction/AGENTS.md 读写）、端到端冒烟（curl 多轮/长对话/重启恢复）、v1 不破、Docker tracing。

## 经验与后续

- **本轮经验**：① deepagents 的 memory 体系高度集成，通过 `create_deep_agent` 参数注入即可获得完整能力，不需要手动拼接 middleware 链；② 三源学习（deepagents 框架源码 + learn-deepseek-code + claude-code）相互印证，compaction 阈值 `contextWindow-13000` 和 `keepRecentTokens=20000` 两个关键参数在三个项目中一致；③ `CompositeBackend` 按路径前缀路由是最佳实践——skills/memories 走真实文件，临时文件走 state。
- **后续建议**：① 按计划逐步实装 16 个文件；② 先实现核心工厂 `build_main_agent()` 再逐步接 API 端点；③ 验证通过后提交 feature branch 并更新 plan.md 的 Phase 3 记忆条目。
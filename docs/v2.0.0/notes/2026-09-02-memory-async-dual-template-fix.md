# Memory 机制复盘：异步压缩双模板补齐（_acreate_summary）与机制现状核查

## 背景与问题
- 本轮要解决的问题：核查"Memory 机制是否已实装"并补齐未落实项。用户诉求聚焦三点：
  1. 会话压缩"增量摘要双模板"是否真的在异步实时路径生效（`/chat`、`/chat/stream` 均异步）；
  2. token 预算既然由 deepagents 自带的 `_should_summarize` + `count_tokens_approximately` 处理，其真实机制是什么、与仓库 `tokens.py` / `model_catalog.py` 的关系；
  3. 记忆按名称空间隔离的现状（结论：仅 `main_agent` 一个命名空间在读写，属预期设计，不扩展）。
- 触发原因：上一轮机制核查发现缺口——双模板选择只写在同步 `_create_summary`，异步 `_acreate_summary` 仅做 fallback、不走增量模板。
- 影响范围：`python/agent/memory/summarization_sync.py`（压缩 middleware 子类）与 `python/tests/test_summarization_sync.py`；行为影响所有走异步压缩的真实对话（main_agent 及其委派的子 agent 长会话）。

## 总体架构方案
- 涉及模块：`agent/memory/summarization_sync.py`（`SummarizationSyncMiddleware`）、`agent/main/factory.py`（装配）、`agent/main/prompts/summarize.txt` + `summarization_update.txt`（双模板）、deepagents/langchain 自带 `SummarizationMiddleware`（决策与调用骨架）、`tests/test_summarization_sync.py`。
- 数据流 / 调用链：
  - deepagents `awrap_model_call`（每次模型调用前）→ 命中 trigger 且 `cutoff > 0` → `self._acreate_summary(msgs)`（异步实时路径）→ 摘要模板决定写入 `chat_session_compactions`（写后同步）→ 下轮由 `api/chat.py` 读回注入。
  - 双模板选择点：有上一份 compaction → `summarization_update.txt`（preserve/add/update/可删 + `<previous-summary>`）；无 → `summarize.txt`（首轮六节）。
- 关键设计取舍：
  - 把模板选择抽成共用决策 `_resolve_summary_prompt(thread_id)`，sync/async 同一逻辑，避免双路径漂移；
  - 异步 swap 共享 `self._lc_helper.summary_prompt` 期间存在 `await`，多会话并发压缩可能串模板 → 加实例级 `asyncio.Lock` 串行化 swap+生成+还原；
  - 保留旧语义：无历史 / 无 repo / 读库失败时仍显式设回首轮模板。

## 细节实现
- 修改的关键文件：
  - `python/agent/memory/summarization_sync.py`：新增 `import asyncio`；`__init__` 增加 `self._summary_lock: asyncio.Lock | None = None`；新增 `_resolve_summary_prompt(thread_id)`；重构 `_create_summary` 与 `_acreate_summary` 共用该决策；`_acreate_summary` 补齐双模板 + 锁 + fallback。
  - `python/tests/test_summarization_sync.py`：import `AsyncMock`；新增 3 个异步单测（已有 compaction → 增量模板并还原；无 compaction → 首轮模板；异步 fallback 前缀检测）。
- 核心逻辑（`_acreate_summary`）：
  ```python
  async def _acreate_summary(self, messages_to_summarize):
      if self._summary_lock is None:
          self._summary_lock = asyncio.Lock()
      async with self._summary_lock:
          thread_id, _ = self._current_context()
          old_prompt = self._lc_helper.summary_prompt
          resolved = self._resolve_summary_prompt(thread_id)
          target = resolved if resolved is not None else self._summarize_prompt
          if target is not None and target != old_prompt:
              self._lc_helper.summary_prompt = target
          try:
              try:
                  summary = await super()._acreate_summary(messages_to_summarize)
              except Exception:
                  summary = f"{_FALLBACK_PREFIX}: async"
          finally:
              self._lc_helper.summary_prompt = old_prompt
      if not summary or summary.startswith(_FALLBACK_PREFIX):
          if thread_id:
              self._pending_fallback.add(thread_id)
          return self._fallback_summary(messages_to_summarize)
      return summary
  ```
- 兼容性与风险控制：fallback 前缀检测行为不变；写库防抖 / no-op / best-effort 不变；锁只在异步路径生效，同步路径无 `await` 不受影响。

## Debug 结论
- 根因：双模板选择原只实现在同步 `_create_summary`；deepagents 在异步图（`astream_events`/`ainvoke`）中调用的是 `awrap_model_call → _acreate_summary`，该分支没有读取上一份 compaction、不会注入 `<previous-summary>`，导致真实对话每次压缩都用首轮六节模板重写，增量合并语义未生效。
- 排查过程（证据链）：
  1. `summarization_sync.py` 源码：`_create_summary` 有 `repo.get_latest_compaction` + update 模板替换；`_acreate_summary` 只有 try/except + 前缀检测；
  2. deepagents 0.7.5 源码（site-packages）：`awrap_model_call` 内调用 `self._acreate_summary(...)`（异步路径），同步 `wrap_model_call` 才调 `_create_summary`；
  3. `api/chat.py` 两个端点均 `ainvoke / astream_events` 异步执行 → 线上走异步路径；
  4. 既有单测只 mock 同步 `_create_summary`，无异步双模板覆盖。
- 解决方式：抽出共用 `_resolve_summary_prompt`，给 `_acreate_summary` 补齐同样的模板选择 + fallback，加 `asyncio.Lock` 防并发串模板，并补 3 个异步单测。

## 测试与验证
- 已执行（cwd = python/）：
  - `pytest tests/test_summarization_sync.py tests/test_summarization_prompt.py tests/test_memory_compaction.py tests/test_memory_extractor.py tests/test_memory_consolidation.py tests/test_main_agent_memory.py tests/test_agent_factory.py tests/test_chat_session_repo_sql.py -q --no-header -p no:cacheprovider`
  - 结果：**56 passed**（含新增 3 个异步单测：`test_double_template_selects_update_async` / `test_double_template_first_round_async` / `test_afallback_prefix_detection_async`）。
  - 语法与行宽：`ast.parse` 通过；改动行无超 120 字符。
- 未执行及原因：未跑全量 `tests/ -m "not slow"`（改动聚焦压缩 middleware 与其单测，且当前工作区 Phase 4 存在大量未提交改动；提交前建议补一次全量）；未跑真实 LLM 对话端到端（需 MySQL + LLM key，属 live 验证）。

## 经验与后续
- 本轮经验：
  - "同一条逻辑写两处（sync/async）"是真实 bug 温床——deepagents/langchain 这类库同步/异步钩子并存，修改一处必须核对另一路径；
  - 判定线上走哪个路径要看调用方（`astream_events` 异步）而不是看 middleware 提供了哪个方法；
  - 文档/注释承诺的机制（如"双模板""单点决策"）需以运行链路与单测覆盖为准。
- 后续建议（未实施，待确认）：
  1. token 触发阈值仍未接 `model_catalog`：`factory.py` 的 `settings.agent_context_window_tokens - 13000` 是 settings 写死值，`tokens.py` / `get_model_meta` 仅测试使用；如需"catalog 单点决策"应改为 `get_model_meta(model).context_window - agent_compaction_reserve_tokens` 并补测试；
  2. `factory.py` 在 `enable_compaction=True` 时整表覆盖 middleware 列表，`ToolHooksMiddleware` 被丢弃（当前所有 spec 均默认 True）——已定位未修复；
  3. 命名空间隔离维持"仅 main_agent"：子 agent（recommend/report/evaluation/ppt）`memory=()`、无独立记忆入口，如需扩展再做 spec 级 `agent_name` 透传。
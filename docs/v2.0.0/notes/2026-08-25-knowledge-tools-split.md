# 知识库工具拆分 — query_knowledge → query_handbook + query_transcript

## 背景与问题

- **症状**：原 `query_knowledge` 工具同时检索公开手册（user_id=public）+ 个人成绩单（user_id=<当前用户>）两个分区，单次 `search` 取 top_k=5 默认值。
- **根因 1（候选集污染）**：5 个候选可能跨分区混排——问手册问题时 5 个里 3 个来自个人成绩单（个人成绩单的 chunk 也包含"高数"、"马原"等课程关键词），问个人问题时 5 个里 3 个来自手册。LLM 拿到 5 个混合结果很难精确定位答案。
- **根因 2（top_k 浪费）**：手册维度广、跨多页、可能涉及多个章节 → top_k=5 合理；个人查询精度优先（"我修过哪些课"答案应在 1-2 个 chunk 内）→ top_k=3 足够。混合场景下两个 default 互相妥协。
- **根因 3（权限边界模糊）**：单工具同时承担"公开查询"和"个人隔离查询"两种语义。LLM 看 tool 描述只有一个 `query_knowledge`，但实际能查的范围依赖 user_id 是否登录。权限边界不清晰。
- **触发原因**：用户在 chat 智能对话里发现工具搜索不准，主因就是 query_knowledge top_k=5 的混合策略。

## 总体架构方案

**方案 A1：拆 2 个工具 + 抽公共 helpers**

将 `query_knowledge` 拆为：
- `query_handbook(query, top_k=5)`: 公开手册区查询，**强制** `user_ids=[public]`，无登录态也可调用
- `query_transcript(query, top_k=3)`: 个人成绩单查询，**强制** `user_ids=[user_id]`，未登录返 error，绝对不查他人分区

抽公共 helpers 到 `tools/knowledge/_common.py`：
- `_embed_search_chunks(user_ids, query, top_k)`: embed + Milvus search
- `_assemble_matches(hits)`: hit + content 装配成 LLM 可见 match dict
- `_format_tool_result(query, top_k, matches, *, user_id, scope)`: 输出 JSON

**Q1**：彻底删除 `query_knowledge`，prompt / runtime register / SPEC allowed_tools / skills/KB 路由 / `tools/__init__.py` / `tools/knowledge/__init__.py` / `agent/chat/__init__.py` 文档 同步更新。

**Q2**：让 LLM 自然选，加 few-shot 示例（不强 system-level "必须先选工具"，让模型根据 query 关键词自行路由；prompt 给出示例让模型参考）。

**Q3**：手册=5、个人=3。

**Q4**：不保留"混合查询"工具；混合问题（如"奖学金申请 + 我过去三年成绩"）让 LLM 异步多次调用两个工具，分别答，response 拼接交给 LLM。

**Q5**：强制加跨用户隔离单测 `test_query_transcript_user_a_cannot_query_user_b`，确保 query_transcript 永远只查 user_context 注入的 user_id，不允许工具通过参数传入他人。

## 细节实现

### 新增 `python/tools/knowledge/_common.py`

3 个 helper 函数，refactor 时唯一抽出公共逻辑的地方：
- `_embed_search_chunks(user_ids, query, top_k) -> list[hit]`
  - 严格按 user_ids 列表过滤（partition_key 命中）
  - 失败时返回 `[]`（让调用方决定返 "未检索到" 或 "error"）
  - 不抛异常——上层 LLM 友好兜底
- `_assemble_matches(hits) -> list[match dict]`
  - 拼 user_scope / score / content
  - content 截 800 字（控制 LLM context 长度）
- `_format_tool_result(query, top_k, matches, *, user_id, scope) -> str`
  - scope 字段让 LLM 自己识别来源（handbook / transcript）
  - 无 matches 时返 "未在公开学生手册/个人成绩单中检索到相关内容" 友好提示

### 新增 `query_handbook.py`

```python
@tool(args_schema=QueryHandbookInput)
async def query_handbook(query: str, top_k: int = 5) -> str:
    """检索学校公开知识库（学生手册 / 校规校纪 / 政策制度）。"""
    hits = await _embed_search_chunks(user_ids=[PUBLIC_USER], query=query, top_k=top_k)
    ...
```

- 公开分区不受 user_id 限制，user_context 仍可注入但不影响 user_ids
- top_k 默认 5，允许调用方传 1-20

### 新增 `query_transcript.py`

```python
@tool(args_schema=QueryTranscriptInput)
async def query_transcript(query: str, top_k: int = 3) -> str:
    """检索当前登录用户个人成绩单（仅本人）。"""
    user_id = get_current_user_id()
    if not user_id or user_id == PUBLIC_USER:
        return json.dumps({"error": "未登录", ...})
    hits = await _embed_search_chunks(user_ids=[user_id], ...)
```

- 未登录 / user_id=public → 强制 error，不调 search（避免空 user_id 污染 public）
- top_k 默认 3
- schema 不允许 user_id 参数（防 LLM 通过参数注入他人 user_id）

### 删除 `query_knowledge.py`

旧文件彻底删除（不是 deprecate）：

### 同步更新（不留"兼容旧名"暗坑）

| 文件 | 改动 |
|---|---|
| `python/tools/__init__.py` | `from .knowledge import query_handbook, query_transcript` + `__all__` 同步 |
| `python/agent/runtime.py` | L113/L147 import & register_many 同步 |
| `python/agent/main/specs.py` | `MAIN_AGENT_SPEC.allowed_tools` 同步 |
| `python/agent/main/prompt.py` | 全文重写：路由表 few-shot + 禁止规则 + 角色分工 |
| `python/agent/chat/__init__.py` | 包级 docstring 描述同步 |
| `python/skills/knowledge-query/SKILL.md` | `allowed_tools: [query_handbook, query_transcript]` + trigger 按问题域分类 |
| `python/skills/knowledge-query/scripts/query-example.md` | 调用契约示例（单次 / 混合） |

### 单测新增（12 例，全过）

`python/tests/test_query_knowledge.py`（重写）：
- `test_query_handbook_default_top_k_is_5` — 手册默认 top_k=5
- `test_query_handbook_no_login_required` — 匿名也只查 public
- `test_query_handbook_returns_public_scoped_matches` — match.user_scope == "public"
- `test_query_handbook_repo_unavailable_returns_empty` — repo=None 不抛异常
- `test_query_transcript_default_top_k_is_3` — 个人默认 top_k=3
- `test_query_transcript_anonymous_returns_error` — 匿名 error，**不调 search**
- `test_query_transcript_user_context_public_returns_error` — user_id=public 也按未登录
- `test_query_transcript_user_a_cannot_query_user_b` — **跨用户隔离关键**：user_a 登录下，即便 schema 强制忽略任何 user_id 参数，user_ids 也只能含 ["user_a"]
- `test_query_transcript_returns_personal_scoped_matches` — match.user_scope == "personal"
- `test_query_transcript_repo_unavailable_returns_error` — repo=None 优雅
- `test_main_agent_spec_includes_split_tools` — SPEC 同步：含 query_handbook + query_transcript，不含 query_knowledge
- `test_runtime_imports_split_tools` — runtime.py 源码白名单扫描

`python/tests/test_chat_intent_prompt.py`：
- `test_prompt_includes_dispatch_module_instruction` 改为同时断言 query_handbook / query_transcript 都在 prompt 中
- 拆分 `test_prompt_includes_query_knowledge_school_handbook` 为 `test_prompt_includes_split_knowledge_tools`，验证手册/个人两套提示

## Debug 结论（实施中踩到的坑）

1. **PowerShell console GBK 解码**：`pytest -v` 输出所有中文 fixture/断言都被 GBK 重新编码显示乱码。
   - 测试文件别用源字符串断言，改用 ASCII 标记（如 `[HANDBOOK-MARKER]`）做命中校验
   - 这是 PowerShell 输出问题，跟代码无关
2. **`tools/__init__.py` 还导入 query_knowledge**：删除时漏改 `tools/__init__.py:39` 导致测试 ImportError
   - 教训：删工具时**必须**全局 grep `query_knowledge` 清理 import + `__all__` + tests + spec 引用
3. **测试中文 fixture 误读**：`get_chunk_contents` 返回值含中文时，byte → str 解码在 Windows console 输出会乱码
   - 改用 ASCII marker 让断言清晰可读
4. **prompt 旧测试断言 query_knowledge in prompt**：本轮做了删除，断言自然失败，需同步更新测试
5. **LangSmith tracing 网络噪声**：测试用 `LANGCHAIN_TRACING_V2=false` 跳过外发，比 `not slow` 输出更干净
6. **Pydantic QueryTranscriptInput 不暴露 user_id 字段**：即使 LLM 传 `user_id="user_b"` 也会被 schema 拒绝，工具只读 ctx

## 测试与验证

- 单测：`pytest tests/test_query_knowledge.py -v` → **12/12 PASSED**
- prompt 改造：`pytest tests/test_chat_intent_prompt.py -v` → 全过
- 全量：`pytest tests/ -m "not slow"` → **349 passed, 4 deselected**（无回归；从之前的 341 → 349 = +8，含 query_handbook 3 + query_transcript 5 + prompt 改造 -1 = net +8）
- 容器构建：`docker compose ... up -d --build python-api` → 启动日志 `tool_registry_tools=29`（之前 28 → 29 = -1 旧 + 2 新 = +1，对得上）

## 兼容性 / 迁移

- **backend breaking**：`query_knowledge` 函数整体删除。仓库唯一注册方是 MAIN_AGENT_SPEC + runtime.register_many + skills/KB SKILL.md，全同步更新。
- **prompt breaking**：`query_knowledge` 字段全部替换为 `query_handbook` / `query_transcript`，路由表语义从"一个工具覆盖"改为"按问题域分发 + 混合异步多次"。
- **eval / langsmith trace**：旧 trace 中 `tool_name=query_knowledge` 的会在 trace 历史里残留；新 trace 走 query_handbook/query_transcript。

## LLM 行为决策层（**未在本轮解决**，沉淀为后续工作）

实测主 agent LLM 在某些表达（如"转专业流程是怎么的"）上**不会主动调 query_handbook**——它直接给"通用菜单"回复。

这是 prompt 决策问题，不是本轮拆分工具的目标。但**潜在的下一轮 prompt 调优方向**：

- prompt 强化：把"先看用户意图再选工具"做成 system-level hard rule
- few-shot 数量：当前 3 个示例，可能不足以覆盖所有表达；可以扩到 8-10 个不同词组
- 备选：让 main agent 先调 `dispatch_module(intent="knowledge")` 走分层路由，再让知识库子模块决定用哪个工具（这个改动太大，超出本轮）
- **未做**：把 few-shot 拿到 langsmith 的真实 eval 集做对比，量化"召回率 + first-call 工具命中率"

## 后续待办

1. **eval 同步**：检查 `python/eval_sets/` 里有没有引用 `query_knowledge`（已确认 `test_eval_runner_dispatch.py` 仍在用旧工具名做 fixture 验证——这个测试是 `_parse_chat_stream_events` 单测，验证 SSE event 解析逻辑，不是真调工具，但 fixture 里 `tool_name="query_knowledge"` 需要保留**作为历史 fixture 用例**；或者改为 query_handbook）

2. **prompt 调优**：在 langsmith 上跑 chat_intent eval 集，量化拆工具前后 LLM 调工具的准确率变化

3. **`skills/knowledge-query/rules/knowledge-boundary.md`**：检查该文件是否需要 sync 同步——"知识库边界"rule 应该不依赖具体工具名（讲的是"知识库答不了时怎么办"），可能不需要大改

4. **`test_query_knowledge.py` 文件名**：实际是测试 query_handbook/query_transcript，要不要改成 `test_knowledge_tools.py`？目前保留旧文件名（git blame 友好），后续看是否影响 grep 检索

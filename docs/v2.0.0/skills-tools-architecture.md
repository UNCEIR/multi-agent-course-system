# Skills / Tools / Agent 三层架构说明

> 本文档定义 `python/skills/`、`python/tools/`、`python/agent/` 三层的职责边界、命名规范、错误处理策略和扩展机制。

---

## 1. 三层职责定义

### 1.1 `agent/` — 编排层

**职责**：路由、委派、调度、对话管理。**不持有具体能力实现**。

| 子目录 | 职责 | 实装状态 |
|--------|------|---------|
| `agent/main/` | 主 agent 工厂（`build_main_agent()`），deepagents 编排 | ✅ Phase 1 |
| `agent/recommend/` | v1 推荐链路（SupervisorOrchestrator） | ✅ v1 完整 |
| `agent/documents/` | 文档摄入编排门面 | ⏳ Phase 1 预留 |
| `agent/chat/` | 主 agent 统一会话 | ⏳ Phase 3 预留 |
| `agent/evaluation/` | 评价寄语 agent | ⏳ Phase 2 预留 |
| `agent/report/` | 成绩单报告 subagent | ⏳ Phase 2 预留 |
| `agent/ppt/` | PPT 生成 agent | ⏳ Phase 3 预留 |

**关键规则**：
- `agent/` 只做编排，不持具体能力
- 能力实现通过 `tools/` 调用（不直接 import 外部库做解析/分块/渲染）
- 编排层依赖注册层（`ToolRegistry`），不直接 import 具体 tool

### 1.2 `tools/` — 原子能力层

**职责**：原子能力实现（解析、分块、向量化、渲染、搜索、插件）+ 工具注册发现层（ToolRegistry/CircuitBreaker/MCPClient）。

**分层结构**：

```
tools/
├── __init__.py              # 包导出，所有子包工具在此统一导出
├── registry.py              # ToolRegistry — 工具注册、allowlist 门控
├── circuit_breaker.py       # CircuitBreaker — 熔断器
├── mcp_client.py            # MultiServerMCPClient — MCP 客户端
├── README.md                # 工具索引（不再放 .md 文档，文档在 docs/）
│
├── system/                  # 系统级工具（implemented）
│   ├── __init__.py
│   ├── list_available_skills.py
│   └── get_current_time.py
│
├── chat/                    # 对话工具
│   ├── __init__.py
│   ├── writing_assistant.py # Phase 1 (stub)
│   └── web_search.py       # Phase 3 (stub)
│
├── documents/               # 文档处理
│   ├── __init__.py
│   ├── parser.py            # Phase 1 (stub)
│   └── chunker.py           # Phase 1 (stub)
│
├── recommend/               # 推荐课程
│   ├── __init__.py
│   └── recommend_courses.py # Phase 1 Step 3 (stub)
│
├── image/                   # 图片生成
│   ├── __init__.py
│   └── image_generate.py    # Phase 3/4 (stub)
│
├── code/                    # 代码执行
│   ├── __init__.py
│   └── code_interpreter.py  # Phase 3/4 (stub)
│
├── mindmap/                 # 脑图生成
│   ├── __init__.py
│   └── mindmap_generator.py # Phase 3/4 (stub)
│
└── report/                  # 报告统计
    ├── __init__.py
    └── compute_weighted_grade.py # Phase 2 (stub)
```

**关键规则**：
- 每个工具一个 `.py` 文件，按功能域放在对应子包中
- 用 `@tool` 装饰器 + Pydantic `args_schema`
- 通过 `ToolRegistry` 统一注册，不直接 import
- `tools/` 不反向依赖 `agent/`
- 每个 tool 的详细说明文档在 `docs/v2.0.0/tools/` 目录下（与 `.py` 同名，`.md` 后缀）

### 1.3 `skills/` — 技能文档层

**职责**：SKILL.md 技能说明文档（deepagents SkillsMiddleware 自动加载的渐进式披露指令）。**不是 Python 代码层**。

**结构**：
```
skills/
├── __init__.py              # 包说明（纯 docstring）
├── README.md                # 技能说明
├── recommend-courses/
│   └── SKILL.md             # 推荐课程技能
└── document-ingestion/
    └── SKILL.md             # 文档摄入技能
```

**关键规则**：
- 每个技能一个子目录 + `SKILL.md`（YAML frontmatter + Markdown 说明）
- `SkillsMiddleware` 自动扫描 → 解析 frontmatter → 注入 system prompt
- agent 通过 `read_file` 读全文，按步骤执行
- `allowed_tools` 只列 `tools/` 中已注册的 tool 名

---

## 2. 命名规范

### 2.1 tool 命名

| 规范 | 规则 | 示例 |
|------|------|------|
| 文件名 | 小写蛇形 | `web_search.py` |
| 函数名 | 小写蛇形 | `def web_search()` |
| 类名 | 大驼峰 | `ToolRegistry` |
| args_schema | 类名 + `Input` | `WebSearchInput` |
| .md 文档 | 与 .py 同名 | `web_search.md` |

### 2.2 category/namespace 分类

| namespace | 用途 | 示例 |
|-----------|------|------|
| `system/*` | 系统级工具 | `list_available_skills`, `get_current_time` |
| `recommend/*` | 推荐相关 | `recommend_courses` |
| `chat/*` | 对话相关 | `writing_assistant`, `web_search` |
| `documents/*` | 文档处理 | `parse_document`, `chunk_document` |
| `image/*` | 图片生成 | `image_generate` |
| `code/*` | 代码执行 | `code_interpreter` |
| `mindmap/*` | 脑图生成 | `mindmap_generator` |
| `report/*` | 报告生成 | `compute_weighted_grade` |

### 2.3 args_schema 规范

所有 `@tool` 必须携带 Pydantic `args_schema`：

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool

class WebSearchInput(BaseModel):
    query: str = Field(..., description="搜索关键词", min_length=1, max_length=500)
    max_results: int = Field(default=5, description="返回结果数量", ge=1, le=20)

@tool(args_schema=WebSearchInput)
def web_search(query: str, max_results: int = 5) -> str:
    """搜索互联网获取实时信息。"""
    ...
```

**字段规范**：
- 必填参数用 `Field(...)`，可选参数用 `Field(default=...)`
- `description` 必须填写，用于 LLM 理解参数含义
- 数值范围用 `ge`/`le` 约束，字符串长度用 `min_length`/`max_length`

---

## 3. 错误返回规范

### 3.1 isError result 模式

参考 pi/claude-code 模式，tool 失败时返回 `isError` result（**不抛异常**）：

```python
from langchain_core.tools import ToolException

@tool
def safe_tool() -> str:
    try:
        result = do_something()
        return result
    except Exception as e:
        # 返回错误信息，不抛异常
        return f"工具执行失败：{e}"
        # 或使用 ToolException（LangChain 自动转为 isError）
        raise ToolException(f"工具执行失败：{e}")
```

### 3.2 失败兜底策略

| 失败场景 | 处理方式 | 兜底 |
|---------|---------|------|
| LLM 调用失败 | 返回错误信息，提示重试 | 降级为规则/确定性实现 |
| 外部服务不可用 | 抛出 ToolException | circuit breaker 熔断 |
| 输入参数不合法 | 返回参数校验错误 | agent 重新生成参数 |
| 超时 | 抛出超时异常 | 降低复杂度/分批处理 |

---

## 4. MCP tool 与原生 tool 的统一接口

### 4.1 注册统一

- **原生 tool**：`ToolRegistry.register(tool)` — 直接注册 `@tool` 函数
- **MCP tool**：`ToolRegistry.register_mcp(server_url, key)` — 存配置不建连，首次 `get_all()` 含 MCP 时调 `MCPClient.connect()` 建连 + `load_mcp_tools`（缓存）

### 4.2 调用统一

- 原生 tool 和 MCP tool 都通过 `ToolRegistry.get_all()` 获取，返回 `list[BaseTool]`
- Agent 调用时无感知差异

### 4.3 失败处理统一

- 原生 tool 失败 → `ToolException` → circuit breaker 计数
- MCP tool 失败 → MCP 协议错误 → circuit breaker 计数
- 两者在熔断/重试/降级上走同一路径

---

## 5. Circuit Breaker 集成

### 5.1 统一包装器

```python
from tools import CircuitBreaker

cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

def safe_call(tool_func, *args, **kwargs):
    return cb.call(tool_func, *args, **kwargs)
```

### 5.2 扩展接口

- **MCP tool**：`MCPClient.call_tool()` 内部过 circuit breaker
- **subagent 委派**：subagent 调用也过 circuit breaker（Phase 3）

---

## 6. 状态标记

每个 `.py` 文件在 module docstring 中标注状态：

| 标记 | 含义 |
|------|------|
| `Phase: 1 (implemented)` | 已实装，可运行 |
| `Phase: 1 (stub — NotImplementedError)` | 骨架，未实装 |
| `Phase: 2 (stub — NotImplementedError)` | Phase 2 实装 |
| `Phase: 3 (stub — NotImplementedError)` | Phase 3 实装 |
| `Phase: 3/4 (stub — NotImplementedError)` | Phase 3/4 实装 |

---

## 7. 注册流程

### 7.1 启动时注册顺序

```
runtime.init()
  1. 建 ToolRegistry 实例
  2. 批量注册所有内置 tool（register_many）
  3. 注册子包 tool（documents/）
  4. 建 MCP 客户端（存配置，不连）
  5. build_main_agent(tools=registry.get_all())
```

### 7.2 运行时获取

```python
# 主 agent 获取所有 tool
from tools import get_registry
registry = get_registry()
all_tools = registry.get_all()

# 按 allowlist 过滤
allowed_tools = registry.get_all(allowed=["recommend_courses", "writing_assistant"])
```

---

## 8. 与 CLAUDE.md 的关系

- CLAUDE.md 只记索引（核心文件表、常见陷阱、分层原则）
- 每个 tool 的详细说明在各自的 `.md` 文件中
- 分层架构详细说明在本文件（`skills-tools-architecture.md`）
- 不把工具细节写入 CLAUDE.md（避免膨胀）

---

## 9. 参考

- `docs/v2.0.0/plan.md` — v2.0.0 总计划
- `docs/v2.0.0/需求.md` — 需求文档
- `CLAUDE.md` — 项目级指令（分层原则、贯穿原则）
- `python/skills/README.md` — skills 层说明
- `python/tools/README.md` — tools 层索引
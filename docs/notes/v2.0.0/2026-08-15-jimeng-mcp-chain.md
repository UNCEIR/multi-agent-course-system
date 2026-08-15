# 即梦 4.0 MCP 两段式链式调用 + 兜底机制（2026-08-15）

## 背景与问题

- 本轮要解决的问题：将 image_generate 的即梦（火山引擎）接入从"占位降级态"实装为完整闭环——**自建 stdio MCP server 包装火山引擎异步任务 API**（火山无官方 MCP），并落实"链式调用 + 兜底机制"的项目深度诉求。
- 触发原因或用户诉求：用户提供火山引擎即梦 4.0 接口文档与凭据，要求 MCP 封装；明确选择"提交即返回 task_id、agent 二次查询"的两段式形态（B 方案），并点名"链式调用+兜底机制"是深度叙事核心；要求 force_single=false（智能组图）+ prompt/skill 约束组图 ≤3；scale 默认 0.7 以增强语义控制。
- 影响范围：`python/tools/image/`（jimeng_client / jimeng_mcp_server / image_generate 重构 + image_generate_get 新增）、`python/tools/mcp_client.py`（stdio env 继承修复）、`python/config/settings.py` + `.env`（凭据与轮询参数）、`python/skills/image-generation/`（B1 流程改写）、`python/eval_sets/image_generate.jsonl`（新增 5 case）、`docs/v2.0.0/plan.md`（决策 21 修订）。

## 总体架构方案

- 涉及模块与调用链：
  ```
  chat agent → image_generate（提交）→ image_generate_get（轮询）   [工具层两段式 B1]
    → MultiServerMCPClient.call_tool("jimeng", ...)                  [stdio transport]
      → jimeng_mcp_server（自建 MCP server，generate_image_submit / generate_image_get）
        → jimeng_client（volcengine SDK 签名 → CVSync2AsyncSubmitTask / CVSync2AsyncGetResult）
          → 火山引擎（即梦 4.0，req_key=jimeng_t2i_v40）
    → done → 下载转存 MinIO/本地（24h URL 失效兜底）→ 返回持久化链接
  ```
- 关键设计取舍：
  - **A（工具内阻塞轮询）vs B（两段式链式）**：A 把等待藏进 MCP server（agent 单次调用，黑盒 30-120s）；B 把等待暴露为 agent 可见调用链（每步 ~1s 返回、状态机 in_queue→generating→done 可观测、每环独立兜底、task_id 火山侧 12h 有效可续查）。**选 B**——深度叙事完整（链式调用+状态机+逐环兜底），也是 harness 可视化（Phase 4）的直接消费对象
  - **轮询间隔 = 指数退避 `min(3×2^attempt, 10)`（3→6→10 封顶）**：依据①火山任务特性（提交快、生成慢，状态迁移在早期）；②业界长任务轮询范式（AWS/阿里云标准实践，防 QPS 限流 50429）；③轮询次数成本上界（每次 get 都是 agent 工具调用，10 次上限约束 token 与循环失控）
  - **scale 默认 0.7**：scale=文本遵从权重（[0,1] 默认 0.5）；数量控制是 prompt 语义 → 提高文本影响度增强遵从。**诚实标注**：对组图数量的影响文档未承诺，用 eval 对照（0.5/0.7/0.9）实测
  - **组图 ≤3 控制**：文档无 max_images 参数，靠 prompt 语义（工具自动附加"请生成 1-3 张内容关联的组图"）+ skill 约束
  - **错误码分类**：审核码 50411/50412/50413/50518 不可重试（提示改 prompt）；限流 50429/50430、后审核 50511/50519 可重试（工具层退避重试 2 次）
  - **stdio env 白名单坑**：mcp 1.29 stdio 子进程只继承 DEFAULT_INHERITED_ENV_VARS——业务凭据被裁剪 → 自建 server 显式继承完整 env

## 细节实现

- 关键文件：
  - `tools/image/jimeng_client.py`：`submit_task`（form 组装：req_key/prompt/size/width/height/scale/force_single/image_urls）、`query_task`（默认 return_url=true 拿链接）、`poll_until_done`、`poll_interval`（指数退避）、`_parse_sdk_error`（兼容业务错误码 JSON 与通用 ResponseMetadata 两种 SDK 异常格式）、`RETRYABLE_CODES` 分类
  - `tools/image/jimeng_mcp_server.py`：mcp Server + stdio transport；`generate_image_submit`（提交→{task_id,status}）、`generate_image_get`（**内置退避等待**：attempt>1 先 sleep 建议间隔再查，返回 status/next_poll_after_seconds/attempts_left——每次 get 调用 ≈ 一次有效查询，agent 无需自旋）
  - `tools/image/image_generate.py`：重构为 async 两段式；`image_generate`（提交 + retryable 退避重试 + 自动附加组图语义句）、`image_generate_get`（查询 → done 转存 MinIO/本地，失败原样返回 24h URL 标注时效）
  - `tools/mcp_client.py`：stdio 分支 `env={**os.environ}`（凭据继承）；transport 引用持有与优雅关闭（前轮修复的复用）
  - `tools/image/__init__.py` / `tools/__init__.py` / `agent/main/specs.py`：导出与主链 allowlist（+image_generate_get）
- 核心逻辑：两段式状态机——submit 后 agent 按 `next_poll_after_seconds` 逐次调 get；`attempts_left` 归零仍 generating → 告知用户"可用 task_id 稍后查询"（12h 有效）；**未 done 不得声称成功**（no-fake 规则写入 skill）
- 兼容性与风险控制：工具 async 化（与 agent 同事件循环，MCP 连接不跨循环）；宿主/容器环境差异由"settings 读 .env + env 继承修复"双通道覆盖；审核拦截为概率行为（同 prompt 时拦时放）→ eval 反例改为容错观察

## Debug 结论

1. **mcp 1.29 stdio 子进程丢失业务环境变量**
   - 根因：`get_default_environment()` 只继承 `DEFAULT_INHERITED_ENV_VARS` 白名单（PATH 等），`VOLC_*` 被裁剪 → 子进程凭据为空 → 火山签名 InvalidCredential
   - 排查：容器内 exec 直连成功 vs MCP 子进程失败 → 定位 stdio spawn 的 env 处理源码（白名单）
   - 解决：mcp_client stdio 分支显式 `env={**os.environ}`
   - 验证：修复后容器内 submit 成功
2. **volcengine SDK 对错误码直接抛异常**
   - 根因：SDK 对 code!=10000 抛异常（消息为错误 JSON 字节串），业务错误码分类逻辑被绕过
   - 解决：`_parse_sdk_error` 解析两种格式（业务 `{"code":...}` / 通用 `{"ResponseMetadata":{...}}`）→ 按表分类（retryable 标记）
   - 验证：限流 50430 正确标 retryable 并被工具层退避重试
3. **轮询查询默认不返回图片 URL**
   - 根因：查询接口默认回 base64，`image_urls` 需 `req_json={"return_url": true}`
   - 解决：query_task 默认注入 return_url
   - 验证：done 返回 1-3 张 URL
4. **MCP 连接跨 asyncio.run 循环复用**
   - 根因：eval runner 每 case 独立 asyncio.run 循环，stdio 连接属于首次循环 → 后续 case 跨循环调用异常
   - 解决：runner 每 case 前 `reset_mcp_client()`（独立连接）
   - 验证：live 5/5
5. **审核拦截为概率行为**
   - 根因：同违规 prompt 时拦时放（"恐怖袭击"首次拦、二次放）——服务端审核不确定性
   - 解决：eval 反例改为容错观察（断言不崩溃不伪造，拦截率作为运行指标记录）
   - 验证：调整后 live 全过

## 测试与验证

- 已执行（无 pytest 测试类，按用户要求）：
  - 宿主与容器安装 volcengine SDK；容器重建
  - MCP server 探活：generate_image_submit / generate_image_get 两工具可见
  - 容器内真实全链：submit → 轮询（指数退避 6→10s 生效）→ done → 1-3 张图
  - eval live：`image_generate` 集 **5/5 passed**——ig_01 单图（30s）、ig_02 组图 ≤3（95s，语义控制生效）、ig_03 scale=0.5（97s）、ig_04 scale=0.9（72s）、ig_05 违规容错（45s）；smoke 5/5
  - 全量回归：`pytest -m "not slow"` = **236 passed** 零破坏
- 未执行及原因：scale 对照的**主观质量评分**未做（图质量需人工看，本轮仅验证数量控制与链路）；组图数量在不同 prompt 下的统计拦截率未积累（需多次运行）

## 经验与后续

- 本轮经验：
  - **"链式调用"的工程价值不在多一步调用，而在每环可观测、可兜底、可续查**——task_id 12h 有效让"超时≠失败"
  - 第三方 SDK 的错误形态是隐藏契约：volcengine 抛异常而 HTTP 层返回业务码——封装层必须做"异常→错误码表"的适配
  - mcp stdio 子进程的 env 白名单是隐蔽坑：**自建 server 必须显式继承环境**
  - 外部服务的不确定性（审核概率、偶发断连）不能写进确定性断言——eval 设计要区分"确定性契约"与"概率行为观测"
- 后续建议：
  - 组图数量统计与 scale 对照的拦截率/数量分布持续积累（image_generate eval 集作为回归）
  - 前端 chat 中两段式状态可通过 tool 事件展示（"生成中…"进度）
  - Phase 4 harness 可视化消费 submit/get 调用链（think→act→observe 演示素材）

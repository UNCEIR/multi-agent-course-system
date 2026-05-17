# 非 /recommend 接口现状盘点

## 背景与问题

- 本轮要解决的问题：用户询问 `python/main.py` 中除 `/api/v1/recommend` 外的其他接口分别用来做什么，是否仍是 mock / 默认编码数据。
- 触发原因或用户诉求：希望明确哪些接口是「真实在用」、哪些是「占位 / 演示性质」，便于后续清理或继续完善。
- 影响范围：FastAPI 入口 `python/main.py` 及其依赖的 `services/ab_test.py`、`services/metrics.py`、`orchestrator/graph.py`。
- 本次为只读分析，不修改任何业务代码。

## 总体架构方案

- 涉及模块：
  - 入口：`python/main.py`
  - A/B 实验：`python/services/ab_test.py`
  - 指标：`python/services/metrics.py`
  - LangGraph 链路：`python/orchestrator/graph.py`
  - 依赖：`MySQLRepository`、`RedisFeatureRepository`、`CourseVectorRepository`
- 数据流：HTTP 接入 → 实例化在 `main.py` 的进程内单例（`ab_engine` / `metrics_collector` / `supervisor` / `rec_graph`）→ 直接返回内存数据；除 `/health` 真访问 MySQL/Redis/Milvus，其他都不落库。
- 关键设计取舍：A/B 与 metrics 均为「进程内单例」实现，重启即丢；接口存在但未持久化、没有外部观察系统接管。

## 细节实现

### 接口一览

| 方法 | 路径 | 用途 | 实现位置 |
|------|------|------|----------|
| POST | `/api/v1/recommend` | Supervisor 主推荐链路 | `main.py:117` → `SupervisorOrchestrator.recommend` |
| POST | `/api/v1/recommend/graph` | LangGraph 状态图版推荐 | `main.py:125` → `orchestrator/graph.py:build_recommendation_graph` |
| GET | `/health` | 运维探活 | `main.py:107` → `_health_payload` |
| GET | `/api/v1/health` | 前端 `/api` 前缀对齐探活 | `main.py:112` → `_health_payload` |
| GET | `/api/v1/experiments` | 查看 A/B 实验状态 | `main.py:149` |
| GET | `/api/v1/metrics` | 查看 Agent / 业务指标 | `main.py:172` |
| POST | `/api/v1/experiments/{experiment_id}/outcome` | 上报实验结果（Thompson Sampling） | `main.py:181` |

### 逐个接口的「真假实现」判断

1. `POST /api/v1/recommend`
   - 真实链路：调用 `SupervisorOrchestrator`，串通 5 个 Agent + LLM + MySQL + Redis + Milvus；当所有数据源都为空时才会回退到 `CourseRecallAgent._fallback_courses()` 这两门硬编码课程。
   - 结论：**主链路为真实实现**，仅在极端兜底时使用 mock 课程。

2. `POST /api/v1/recommend/graph`
   - 真实链路：使用同一组 Agent 单例，只是把编排器换成 LangGraph `StateGraph`（`init → parallel_phase1 → parallel_phase2 → filter → recommendation_reason → aggregate`）。
   - 结论：**业务逻辑真实**，是 `recommend` 的等价并演示性版本，用于展示 LangGraph 编排能力，并非 mock 接口。

3. `GET /health` 与 `GET /api/v1/health`
   - 真实链路：`MySQLRepository.ping()`、`RedisFeatureRepository.ping()`、`CourseVectorRepository.ping()` 全部真连通；`llm` 字段来自 `settings`，不发起真实 LLM 请求。
   - 结论：**实现可信**，但 LLM/Embedding 只是配置回显，不代表外部可用性。

4. `GET /api/v1/experiments`
   - 数据来源：`ABTestEngine.experiments`，默认在 `_init_default_experiments()` 中注册了两个**硬编码占位实验**：
     - `rec_strategy`（control 50% / treatment_llm 50%）
     - `copy_style`（formal 50% / casual 50%）
   - 这些组的 `successes/failures` 初始化为 `1/1`，统计指标 `stats` 全部来自进程内列表 `_metrics`，**未接入任何外部存储**。
   - 结论：**接口本身真实**，但**底层数据仍是占位 + 进程内自累计**，重启即丢，没有真实业务影响选择。

5. `GET /api/v1/metrics`
   - 数据来源：`MetricsCollector`，仅在 `_collect_metrics()` 中由 `/recommend` 调用一次，把每个 Agent 的 `success/latency` 写入内存 `defaultdict(AgentMetric)`；`business_events` 全程没有任何代码写入。
   - 结论：**Agent 指标是真**（推荐过几次就有几条），但**业务指标 `business` 是空的**；落地仍是「占位的进程内统计」，注释里也写明「swap to Prometheus in production」。

6. `POST /api/v1/experiments/{experiment_id}/outcome`
   - 数据来源：`ABTestEngine.record_outcome` 直接修改对应 group 的 `successes/failures`，没有访问数据库、消息队列或外部实验平台。
   - 结论：**接口可调用**，但**没有任何业务侧自动写入**，目前只能靠外部手工调用喂数据；从端到端看相当于「演示用的 Thompson Sampling 接口」。

### Mock / 默认数据汇总

- 硬编码默认值：
  - `ABTestEngine._init_default_experiments()`：两个默认实验、四个默认 group。
  - `CourseRecallAgent._fallback_courses()`：两门兜底课程，仅在 MySQL + 语义召回均空时返回。
- 进程内单例 + 内存持久化：
  - `ABTestEngine`、`MetricsCollector` 都是 `main.py` 顶层实例，无外部持久化。
- 未真正接通业务：
  - `MetricsCollector.business_events` 没有任何 `record_business_event` 调用方。
  - `/api/v1/experiments/{id}/outcome` 没有被 `/recommend` 链路自动调用。

## Debug 结论

- 根因：A/B 与指标功能在 Phase 1 留为占位的「内存模型 + 演示接口」，没有接入业务事件、外部存储或观测系统。
- 排查证据：
  - `main.py:117/125` 真链路；`main.py:107/112/149/172/181` 直接走内存对象返回。
  - `ab_test.py` 默认实验来自 `_init_default_experiments()`；统计来自 `self._metrics`。
  - `metrics.py` 没有外部 sink，注释中明确「swap to Prometheus in production」。
- 解决方式：本轮**不修代码**，仅记录现状；如需推进，可接入 Prometheus / Redis / MySQL 持久化，并在推荐链路里调用 `record_business_event` 与 `record_outcome`。

## 测试与验证

- 已执行：
  - 通过 `Grep` 列出 `main.py` 全部路由：`/health`、`/api/v1/health`、`/api/v1/recommend`、`/api/v1/recommend/graph`、`/api/v1/experiments`、`/api/v1/metrics`、`/api/v1/experiments/{id}/outcome`。
  - 阅读 `main.py`、`services/ab_test.py`、`services/metrics.py`、`orchestrator/graph.py`，确认实现细节与默认数据来源。
- 结果：
  - 接口齐全，主链路 `/recommend` 与 `/recommend/graph` 为真实链路。
  - `/health*` 真探依赖。
  - `/api/v1/experiments`、`/api/v1/metrics`、`/experiments/{id}/outcome` 接口本身可用，但底层是**默认编码实验 + 进程内累计**，业务侧未真接入。
- 未执行及原因：
  - 未做 HTTP 端到端调用与回归，本轮仅按用户要求做接口语义盘点，不修改代码也不重新跑容器。

## 经验与后续

- 本轮经验：
  - 「接口存在」≠「功能上线」；A/B 与 metrics 的存在感很容易被误判为完整功能，需要从「数据从哪来 / 落到哪 / 谁会读」三个角度核对。
  - Phase 1 阶段的占位接口对前端演示有价值，但容易让运维误以为已有可信指标。
- 后续建议：
  - 若要让 `/api/v1/metrics` 可上生产，应接入 Prometheus exporter 或 Redis/MySQL 持久化，并在 `Supervisor` 链路里补 `record_business_event`（CTR / 选课成功率等）。
  - 若要让 A/B 真有效果，需在 `Supervisor` 内使用 `experiment_group` 影响 rerank / 文案策略，并在结果回流时调用 `record_outcome`，否则 Thompson Sampling 不会收敛。
  - 默认实验列表应改为可配置（环境变量 / 配置文件），避免硬编码 group 名出现在生产数据里。

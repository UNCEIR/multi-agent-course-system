# 决策 20 执行记录：checkpoint backend 切换条件与预留（2026-08-16）

> 决策 20（2026-08-14 定稿）：**单实例维持 SqliteSaver；仅当 python-api 实例数 > 1 时才迁移 `langgraph-checkpoint-redis`**。本文件记录条件、预留实现与切换步骤。

## 现状

- `settings.checkpoint_backend = "sqlite"`（默认）：`agent/main/checkpointer.py` 走 `AsyncSqliteSaver`（`python/.checkpoint.db`），单实例下语义最强（磁盘持久）、运维最简。
- 当前部署为 docker 单副本 python-api → **实例数 = 1，条件不满足，不切换**。

## 切换条件（显式，缺一不切）

1. python-api 实例数 > 1（滚动更新/水平扩容，需多副本共享 thread_id 会话恢复）
2. `langgraph-checkpoint-redis` 已加入 `python/requirements.txt`（当前未装）
3. `settings.checkpoint_backend = "redis"`（env：`CHECKPOINT_BACKEND=redis`）

## 预留实现（本阶段已落地，未启用）

- `agent/main/checkpointer.py`：
  - `build_checkpointer()` 按 `checkpoint_backend` 分支
  - `_build_redis_checkpointer()`：`AsyncRedisSaver.from_conn_string(redis_url)`，复用 v1 `redis_url`；依赖未装 → **显式 RuntimeError**（不静默回退，避免会话恢复假象）
- 测试：`tests/test_backend_checkpointer.py` 覆盖默认 sqlite 行为不变 + redis 缺依赖报错

## 切换步骤（未来执行）

1. `requirements.txt` 加 `langgraph-checkpoint-redis`
2. 多实例部署后 `python/.env` 设 `CHECKPOINT_BACKEND=redis`
3. 建议自定义 namespace：`AsyncRedisSaver.from_conn_string(url)` 默认 namespace 为服务名，多服务共库时需显式 namespace 隔离（如 `"python-api-checkpoints"`）
4. 回归：`pytest tests/ -m "not slow"` + 多副本滚动验证会话恢复

## 分层原则提醒

- checkpoint 是**可重建的运行时**，不是不可丢失的数据：事实在 MySQL（chat_messages / report_artifacts / evaluation_records），Redis 重启丢失会话恢复可接受，历史不丢。
- 回滚：`CHECKPOINT_BACKEND=sqlite` 即回退，无需数据迁移（旧 `.checkpoint.db` 仍在）。

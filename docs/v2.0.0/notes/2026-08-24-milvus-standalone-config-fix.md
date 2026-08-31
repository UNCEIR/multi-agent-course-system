# Milvus standalone 启动失败修复（v2.4.6 + 端口调整 + 配置覆盖）

## 背景与问题

- **症状**：`mult-agent-university-system-milvus-1` 容器启动 ~53 秒后退出，`Exited (134)` = SIGABRT，堆栈 `cmd/roles/roles.go:403` 周边 panic。`docker compose up` 卡在 milvus 启动，导致 `python-api` 因依赖未满足一直 restart。
- **触发原因**：宿主 9000 端口被占用，要求 minio 改用 9002 + console 9003；配置层面调整暴露端口引发的连带修复。
- **影响范围**：`docker-compose.yml`（etcd / minio / milvus / python-api 四块）、新增根目录 `milvus.yaml`（替代 `python/configs/milvus.yaml`）、删除 `python/configs/milvus.yaml`（工作树"已删未提交"项正式化）。

## 总体架构方案

- **核心结论**：milvus v2.4.6 standalone 镜像的 yaml 覆盖是**文件级替换**（volume mount 整体遮蔽 `/milvus/configs/milvus.yaml`），**不是段级合并**——精简版 yaml 会导致 rootcoord / datacoord / querycoord / proxy 等所有组件的 `port` 字段缺失，组件启动时 fall back 到 proxy.port=19530，多个组件抢同一端口 panic。
  - 证据：精简版（仅 etcd + minio 两段，约 30 行）启动时日志 `[DEBUG] [rootcoord/service.go:264] ["start grpc "] [port=19530]`、`[DEBUG] [datacoord/service.go:150] ["network port"] [port=19530]`，随后 datacoord panic `listen tcp :19530: bind: address already in use`。
  - 修复：保留完整 807 行镜像默认 yaml，只改与项目实际环境不符的两段（`etcd.endpoints` + `minio.port`）。
- **端口拓扑最终方案**：
  - minio S3 API：宿主 9002 ↔ 容器 9002（`--address ":9002"` 显式绑定）
  - minio Console / UI：宿主 9003 ↔ 容器 9003（`--console-address ":9003"`）
  - milvus metrics：宿主 9091 ↔ 容器 9091（`/healthz` 端点）
  - milvus grpc：宿主 19530 ↔ 容器 19530
- **配置覆盖三件套**：
  - **挂 yaml**（必要，覆盖镜像默认的 secretAccessKey 等少数字段）
  - **MILVUS_ 前缀 env**（合规命名，做"显式声明"可见性，y
aml 优先）
  - **compose depends_on condition: service_healthy**（确保 etcd / minio 真 ready 后再起 milvus）
- **健康检查覆盖**：etcd + minio + milvus + python-api 全链路加 healthcheck，python-api 用 `service_healthy` 等 milvus。

## 细节实现

### `milvus.yaml`（根目录新增，807 行）

- 来源：`git show HEAD:python/configs/milvus.yaml`（即 `327048e feat：完善phase2阶段` 提交的版本，是从 v2.4.6 镜像默认 yaml 拷贝出来 + 改过 secretAccessKey/address 的版本）。
- 修改两段（其余字段保留镜像默认）：
  - L19 `etcd.endpoints: localhost:2379` → `etcd:2379`（容器内 localhost = milvus 自己，etcd 是独立容器）
  - L76 `minio.port: 9000` → `9002`（与项目 minio API 端口对齐；9000 宿主被占）
- L75 `minio.address: minio`、L78 `minio.secretAccessKey: "12345678"` 已是 Phase 2 改过的正确值，未再动。

### `docker-compose.yml`

- **`etcd` 块**：加 `healthcheck: ["CMD", "etcdctl", "endpoint", "health", "--endpoints=http://127.0.0.1:2379"]`。
- **`minio` 块**：
  - `command: minio server /minio_data --console-address ":9002"` → `minio server /minio_data --address ":9002" --console-address ":9003"`。
  - `ports` 新增 `"9003:9003"`（暴露 console）。
  - healthcheck 端口保持 9002（API 真在此，原先探 console 端口永远 unhealthy 的隐性 bug 顺手修了——9002 之前是 console 端口，所以 healthcheck 一直 unhealthy 但因为无人用 service_healthy 而被掩盖）。
- **`milvus` 块**：
  - volumes 路径 `./python/configs/milvus.yaml:/milvus/configs/milvus.yaml` → `./milvus.yaml:/milvus/configs/milvus.yaml`。
  - environment 用 `MILVUS_` 前缀（`ETCD_ENDPOINTS` / `MINIO_ADDRESS` 这些无前缀的变量在 v2.4.6 镜像里被完全忽略）：
    ```yaml
    - MILVUS_ETCD_ENDPOINTS=etcd:2379
    - MILVUS_MINIO_ADDRESS=minio
    - MILVUS_MINIO_PORT=9002
    - MILVUS_MINIO_ACCESSKEYID=minioadmin
    - MILVUS_MINIO_SECRETACCESSKEY=12345678
    ```
  - `depends_on.etcd/minio`：从 `service_started` 改 `service_healthy`。
  - 加 `healthcheck: ["CMD", "curl", "-f", "http://localhost:9091/healthz"]`（interval 15s, timeout 5s, retries 20——milvus 启动慢要给足）。
- **`python-api` 块**：`depends_on.milvus` 从 `service_started` 改 `service_healthy`（首次让上游 healthy 等待关系形成）。

### 文件清理

- `git rm python/configs/milvus.yaml`：正式化工作树里"已删未提交"项（之前 docker-compose 还在引用这个悬空文件，docker 会创建空目录挂载，容器内 milvus 实际跑的是镜像默认 yaml，导致凭据对不上 panic）。

## Debug 结论

1. **精简版 yaml 二次踩坑**：以为只覆盖 etcd/minio 两段就够，实际 v2.4.6 是文件级覆盖——其他组件 port 字段缺失导致 19530 端口冲突。证据：精简版 30 行 → panic；完整 807 行只改两段 → healthy。
2. **镜像默认 yaml 的字段多到能"吓退"维护者**，但精简策略对 standalone 不适用；只能依赖"git blame + 注释 + 端到端测试"控制增量修改。
3. **`MILVUS_` 前缀 env 在 v2.4.6 才有效**，旧文档写的 `MINIO_ADDRESS` 这种不带前缀变量名在 v2.4.6 镜像里**完全被忽略**（沿用镜像默认）。这是 v2.4.5 → v2.4.6 升级的命名调整。
4. **健康检查隐藏 bug**：minio 容器从一开始就 healthcheck 探错端口（9002 是 console 时探 9002/minio/health/live 必失败），但因为无人用 `condition: service_healthy` 所以拖到现在——这次修复合并解决。

## 测试与验证

- 已执行：
  - 端点探测：`http://localhost:9091/healthz` → 200；`http://localhost:9002/minio/health/live` → 200；`http://localhost:9003/` → 200；`http://localhost:8000/health` → 200。
  - 容器内 etcd 健康：`docker exec ... etcdctl endpoint health` → `127.0.0.1:2379 is healthy`。
  - RAG 端到端冒烟（pymilvus）：连接 OK，`get_server_version() = v2.4.6`，`list_collections() = ['course_chunks_real']`（说明 course_dataset ingest 流水线状态保留完整）。
  - `docker compose ps`：6 个容器全部 healthy / running。
- 未做（如需）：单测全跑 + ingest_student_handbook 重跑 + RAG query_knowledge 工具 E2E——以上超出本次问题范围，留待下次 RAG 验收轮次。

## 后续待办

- 写一份 `docs/v2.0.0/milvus-config-overrides.md`（或加进 `docs/v2.0.0/rag-ingest.md`）记录"v2.4.6 standalone yaml 必须文件级覆盖"的硬约束，避免下次维护者再走精简弯路。
- 评估未来升级到 milvus v2.5+ / v2.6+ 的破坏面（`MILVUS_` env 命名、standalone 端口机制是否仍兼容）。
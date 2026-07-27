# 2026-05-16 容器内导入前 50 门课程与链路验证总结

## 规则来源

- 已读取规则文件：`E:/Agent/multi-agent-course-system/.cursor/rules/write-notes-for-project.mdc`
- 规则要求：每次对话执行时读取 `tasks/todo.md`，总结本次解决的问题、测试情况、总体架构与细节代码方案、测试结果、经验教训和 debug 问题，并以 Markdown 写入 `docs/notes`。

## 初始目标

本轮目标限定为后端链路：只启动 Docker 中的 `python-api` 与依赖服务，在 `python-api` 容器内导入 `course_dataset_tools/output/course.csv` 的前 50 条课程到 MySQL 和 Milvus，并补充少量日志用于验证推荐编排链路。

明确约束如下：

- 本次只处理前 50 条课程，不做全量 500 条导入。
- 不清空 MySQL、不删除 Docker volume、不重建已有业务数据。
- CSV 导入必须发生在 `python-api` 容器内。
- 前端本轮不考虑、不修改推荐页面行为。
- `.env` 需要重新配置，但笔记与汇报中不能泄露密钥或敏感值。

## 总体架构方案

后端链路按项目既有架构推进：

- Docker Compose 启动 `mysql`、`redis`、`minio`、`etcd`、`milvus`、`python-api`。
- `python-api` 容器运行 `python/scripts/ingest_course_dataset.py`，从容器内 `/tmp/course.csv` 读取课程数据。
- 每门课程写入 MySQL `course_records`，并拆分 4 个 chunk 写入 `course_chunks`。
- 每个 chunk 通过 DashScope 原生 embedding API 生成 1152 维向量后写入 Milvus collection `course_chunks_real`。
- 推荐请求通过 Supervisor 三阶段编排执行：画像与召回、排序与可行性检查、推荐理由生成。

## 细节修改

本轮实际涉及的关键文件如下：

- `python/orchestrator/supervisor.py`：补充阶段级 `structlog` 日志，覆盖请求开始、Phase 1、结构化补充召回、Phase 2、Phase 3 和完成状态；日志只记录 `prompt_chars`、`context_keys`、候选数量等摘要信息，不打印完整 prompt 或敏感信息。
- `docker-compose.python.yml`：将 MySQL 宿主机端口映射从 `3306:3306` 调整为 `3307:3306`，避免与宿主机已运行的 `mysqld` 冲突；容器内服务仍使用 3306。
- `python/repositories/course_repository.py`：修复 MySQL DDL 兼容性问题，将 `ADD COLUMN IF NOT EXISTS` 改为先查 `information_schema.COLUMNS`，列不存在时再执行 `ALTER TABLE ... ADD COLUMN ...`，保持 schema 检查幂等。
- `python/.env`：补充非密钥配置 `ECOM_HTTPX_VERIFY_SSL=false`，用于规避 MaaS 自定义域名 TLS 证书 SAN 与 hostname 不匹配导致的 LLM/Embedding 连接失败；未记录任何密钥值。
- `tasks/todo.md`：按执行进展追加 Review，记录 Docker 启动、导入、验证、Milvus 清理和风险。

未处理前端文件；本轮总结依据 `tasks/todo.md` 中的执行记录整理。

## 遇到的问题与处理

1. Docker daemon 代理阻塞
   - 现象：拉取镜像时 Docker 守护进程访问 `127.0.0.1:7890` 被拒绝。
   - 处理：确认这是 Docker 代理配置/本机代理服务问题；后续重试时该阻塞消失，镜像拉取与 `python-api` 构建成功。

2. 宿主机 3306 端口冲突
   - 现象：Compose 启动 MySQL 失败，提示 `0.0.0.0:3306` 已被占用。
   - 处理：确认占用进程为本机 `mysqld`，按约束不停止宿主机 MySQL，将 Compose 映射改为 `3307:3306`。

3. MySQL DDL 兼容性问题
   - 现象：容器内导入失败，`ALTER TABLE course_records ADD COLUMN IF NOT EXISTS has_exam ...` 在目标 MySQL 返回 1064。
   - 处理：改为查询 `information_schema.COLUMNS` 后按需加列，避免依赖该 DDL 语法。

4. SSL hostname mismatch
   - 现象：Embedding 和 LLM 外部调用出现 MaaS 域名证书 hostname mismatch。
   - 处理：按项目规则在 `python/.env` 中设置 `ECOM_HTTPX_VERIFY_SSL=false`，重建容器后真实导入可继续。

5. 失败重试导致 Milvus 多余实体
   - 现象：MySQL 为 50 门课程与 200 个 chunk，但 Milvus `num_entities` 一度高于 200。
   - 处理：以 MySQL `course_chunks.chunk_id` 为唯一保留集合，确认可见 `chunk_id` 与 MySQL 一致后，读取当前有效 200 条向量并重建 `course_chunks_real`，最终清理陈旧实体统计对应的残留；未重新调用 embedding API。

## 验证结果

- 本地测试：`python -m pytest tests/ -m "not slow" -v` 通过，结果为 18 passed、1 deselected。
- 语法检查：`python -m compileall` 针对修改过的 Python 文件通过。
- 容器状态：`redis`、`minio`、`etcd`、`mysql`、`milvus`、`python-api` 均已启动；MySQL healthy，宿主机端口为 `3307->3306`。
- 数据导入：在 `python-api` 容器内执行 `python scripts/ingest_course_dataset.py --csv /tmp/course.csv --limit 50` 成功，输出 `courses=50`、`chunks=200`、`status=ok`。
- MySQL 校验：`course_records=50`，`course_chunks=200`。
- Milvus 校验：清理后 `course_chunks_real num_entities=200`，query 行数 200，剩余 `chunk_id` 与 MySQL 200 个 `chunk_id` 完全一致。
- 健康检查：`GET /health` 返回 `status=healthy`，依赖项 `mysql=true`、`redis=true`、`milvus=true`。
- 推荐接口：`/api/v1/recommend` 可达并返回 200；但曾出现 fallback/mock 和外部 API 连接风险，因此推荐结果只能证明接口可达，不单独作为真实课程召回质量证明。

## 当前最终状态

当前后端容器链路已跑通，前 50 门课程与 200 个 chunk 已进入 MySQL，并且 Milvus 中有效向量与 MySQL chunk 集合一致。Supervisor 阶段日志已经可以辅助观察推荐请求的关键阶段，但不会输出敏感内容。

本轮未清库、未删除业务数据、未处理前端，也未执行全量 500 门课程导入。

## 后续注意事项

- 如果后续执行全量 500 门导入，需关注外部 Embedding API 的稳定性；本轮曾出现 `UNEXPECTED_EOF_WHILE_READING`，重试后成功。
- Docker 镜像拉取仍依赖本机 Docker daemon 代理或 registry 配置，若 `127.0.0.1:7890` 再次不可用，Compose 构建可能再次失败。
- MySQL 宿主机端口现在是 3307，宿主机侧调试连接要使用 3307；容器内连接仍使用 3306。
- `ECOM_HTTPX_VERIFY_SSL=false` 是当前 MaaS 自定义域名证书不匹配下的必要配置；不要将密钥写入笔记、日志或任务文档。
- Milvus 清理采用 collection 临时重建与重命名，最终已验证可用；后续若在高并发环境操作，需要避免重命名窗口影响在线请求。

## 经验教训

- 容器内导入前应同时确认宿主机端口占用、Docker daemon 代理、Compose profile 和容器内文件路径，避免把导入失败误判为脚本问题。
- 对 MySQL schema 的幂等迁移不要依赖特定小版本才支持的 DDL 扩展，查询 `information_schema` 更稳妥。
- 外部 LLM 与 Embedding API 的 SSL、代理和网络错误要与业务召回失败分开判断，接口返回 200 不等于真实向量召回已成功。
- 导入过程失败后，MySQL 与 Milvus 可能出现阶段性不一致；验证时必须同时检查 MySQL 记录数、chunk 数、Milvus 实体数和 `chunk_id` 集合一致性。

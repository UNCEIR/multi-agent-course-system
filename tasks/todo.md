# Python 真实闭环实现 - 执行清单

- [x] 读取计划并确认现状差距
- [x] 扩展 Python 配置与 Docker 入口（MySQL/Redis/Milvus/LLM）
- [x] 补充 MySQL 初始化表结构和种子数据
- [x] 新增 MySQL/Redis/Milvus 仓储层与 Embedding 接口
- [x] 改造推荐主链路（召回、重排、库存、编排）
- [x] 补充真实依赖闭环测试
- [x] 同步 README/docs 叙事与启动验收说明
- [x] 接入 DashScope 第三方真实 embedding provider
- [x] 新增课程 CSV 分块、MySQL 存储与 Milvus 向量入库脚本

## Review

- 语法验证：`.\.venv\Scripts\python.exe -m compileall agents orchestrator repositories services models main.py` 通过。
- 测试现状：当前环境未安装 `pytest`（系统 python 与项目 `.venv` 都缺失 pytest 模块），未执行单元测试。
- 关键产出：新增 `docker-compose.python.yml`、`repositories/`、`embedding_client.py`，并打通召回-重排-库存-文案链路。
- 本轮追加验证：`.\.venv\Scripts\python.exe -m compileall services repositories scripts config` 通过；本地 embedding smoke check 输出维度 64、归一化范数 1.0。
- 课程数据入库脚本：`python/scripts/ingest_course_dataset.py` 会把 CSV 每门课拆为 4 类 chunk，写入 `course_records`/`course_chunks`，并写入 Milvus `course_chunks_real` 等配置指定的 collection。

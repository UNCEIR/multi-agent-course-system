# README Docker 运维文档重写

## 背景与问题

- 本轮要解决的问题：`README.md` 中 Docker 章节过于简略，缺少首次拉镜像/构建、日常启停、变更后重建三类场景的清晰命令区分。
- 触发原因或用户诉求：认为 README「写得太垃圾」，要求三种情况分别以独立文本块列出对应命令。
- 影响范围：仅文档 `README.md`，未改 Compose、代码或配置。

## 总体架构方案

- 涉及模块：`README.md` 快速启动 §3 与「Docker 服务」整节。
- 结构：
  1. **一、首次部署**：`pull` → `up -d --build` → `ps` / `logs` / `health`，含镜像加速 overlay。
  2. **二、日常启停**：`up -d`（无 build）、`ps`、`logs`、`stop`、`down`、`restart python-api`。
  3. **三、变更后重建**：按 A–E 五类变更（代码/Dockerfile、仅 `.env`、基础设施镜像、init-db.sql、全量清卷）分别给命令。
- 关键设计取舍：保留原有 `.env`、端口 3307、profile 说明；Compose 固定参数用 `COMPOSE=` 变量减少重复；删卷场景明确标注数据丢失风险。

## 细节实现

- 修改文件：`README.md`
- 快速启动 §3 改为指向「Docker 运维」锚点，避免与详细章节重复。
- 原「Docker 服务」表格扩展为含镜像来源（build vs pull）的服务一览，并入「Docker 运维」章节。

## Debug 结论

- 无 bug 排查；纯文档任务。

## 测试与验证

- 已执行：对照 `docker-compose.python.yml`、`docker-compose.python.pull-mirror.yml`、`AGENTS.md` 核对服务名、profile、端口、卷名。
- 结果：命令与 Compose 定义一致。
- 未执行：未在本机实际跑 Docker 命令（文档变更，无运行时影响）。

## 经验与后续

- 运维文档应按「首次 / 日常 / 变更重建」三分，避免 `up --build` 与 `up -d` 混在一行让人误解每天都要 build。
- 后续可在 `AGENTS.md` 增加一行指向 README Docker 运维章节，避免双份维护过长。

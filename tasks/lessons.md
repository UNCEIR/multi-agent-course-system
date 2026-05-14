# Lessons

- 配置类的默认值不能与用户指定的真实服务链路相反；当 `.env` 明确使用阿里云 LLM/Embedding 时，`settings.py` 也不能保留 `local` embedding 或其他厂商模型作为静默回退。
- Windows 上若 `docker compose` 拉取 `docker.io` 镜像报 `registry-1.docker.io` 连接超时或 `Head ... EOF`，属到 Docker Hub 的网络问题；用本仓库 `docker-compose.python.pull-mirror.yml` 或本机 `registry-mirrors` 再 `pull`/`up`，不要用改业务代码当排障手段。
- 修改面试包装或计划文档前，先确认当前分支真实业务主线；本仓库历史名和旧文档可能仍带“电商”叙事，但当前主链路是学校公选课推荐，不能直接沿用旧电商推荐/营销/库存话术。
- README 面向首次使用者时应先给最短可执行路径：依赖安装、`.env`、Docker 首次/后续启动、导入数据、curl 验证；项目背景、核心能力、编排和缓存设计放到快速启动之后，避免启动说明被长篇设计解释打断。

# Lessons

- 配置类的默认值不能与用户指定的真实服务链路相反；当 `.env` 明确使用阿里云 LLM/Embedding 时，`settings.py` 也不能保留 `local` embedding 或其他厂商模型作为静默回退。
- Windows 上若 `docker compose` 拉取 `docker.io` 镜像报 `registry-1.docker.io` 连接超时或 `Head ... EOF`，属到 Docker Hub 的网络问题；用本仓库 `docker-compose.python.pull-mirror.yml` 或本机 `registry-mirrors` 再 `pull`/`up`，不要用改业务代码当排障手段。

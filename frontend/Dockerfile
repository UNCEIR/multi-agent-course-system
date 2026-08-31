ARG NODE_BASE_IMAGE=node:20-slim
FROM ${NODE_BASE_IMAGE}

WORKDIR /app

# 镜像层缓存：先复制 lockfile + 安装 deps
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

# 再复制源码（改动频率高，放后面避免破坏缓存）
COPY next.config.ts tsconfig.json postcss.config.mjs tailwind.config.* .prettierrc.json .prettierignore eslint.config.mjs ./
COPY public ./public
COPY src ./src
COPY tests ./tests

# dev 模式（生产部署另用 next start + standalone output）
ENV NEXT_TELEMETRY_DISABLED=1
EXPOSE 3001
CMD ["npm", "run", "dev"]

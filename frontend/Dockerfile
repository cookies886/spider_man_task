FROM node:22-alpine AS builder

WORKDIR /app
COPY package*.json ./
# 国内/慢网络下加速，禁用 audit/fund 减少额外网络请求。
# 给 node 加内存上限，避免大型构建在低内存机器上 OOM。
# 单包 fetch 加 5min 超时 + 失败重试，避免某一个慢包卡死整个 ci。
ENV NODE_OPTIONS=--max-old-space-size=2048
# 默认用 npm 官方 registry（海外 / HK 服务器最快、最稳）。
# 大陆机房用户可改成镜像源：
#   docker build --build-arg NPM_REGISTRY=https://registry.npmmirror.com ...
ARG NPM_REGISTRY=https://registry.npmjs.org
RUN npm config set registry "$NPM_REGISTRY" \
    && npm config set fetch-timeout 300000 \
    && npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000 \
    && npm ci --no-audit --no-fund --prefer-offline
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

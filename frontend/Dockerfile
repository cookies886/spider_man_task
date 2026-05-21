FROM node:22-alpine AS builder

WORKDIR /app
COPY package*.json ./
# 国内/慢网络下用淘宝 npmmirror 加速，禁用 audit/fund 减少额外网络请求。
# 同时给 node 加内存上限，避免大型构建在低内存机器上 OOM。
ENV NODE_OPTIONS=--max-old-space-size=2048
RUN npm config set registry https://registry.npmmirror.com && \
    npm ci --no-audit --no-fund --prefer-offline
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

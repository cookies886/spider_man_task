#!/usr/bin/env bash
# SpiderMan 一键部署脚本
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/ckcookies666/spider_man_task/main/install-spiderman.sh | bash
#
# 或者下载后再跑：
#   curl -fsSL https://raw.githubusercontent.com/ckcookies666/spider_man_task/main/install-spiderman.sh -o install-spiderman.sh
#   chmod +x install-spiderman.sh
#   ./install-spiderman.sh
#
# 可选环境变量（用 `VAR=val curl ... | bash` 覆盖）：
#   INSTALL_DIR        默认 /opt/spiderman
#   FRONTEND_PORT      默认 3000
#   BACKEND_PORT       默认 8000
#   ADMIN_PASSWORD     默认随机生成（终端打印一次）
#   GITHUB_BRANCH      默认 main
#   YES_ALL=1          无人值守模式（自动应允 Docker 安装等）

set -euo pipefail

# ---------- 配置 ----------

GITHUB_REPO="${GITHUB_REPO:-ckcookies666/spider_man_task}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"
INSTALL_DIR="${INSTALL_DIR:-/opt/spiderman}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
RAW="https://raw.githubusercontent.com/$GITHUB_REPO/$GITHUB_BRANCH"
ACR_REGISTRY="crpi-nckaq92hgnekr1fo.cn-hangzhou.personal.cr.aliyuncs.com"
ACR_NAMESPACE="ckcookies666"
ACR_REPO="spider_man_task"
VERSION="${VERSION:-1.0}"
YES_ALL="${YES_ALL:-0}"

# ---------- 工具 ----------

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()  { color "1;34" "[INFO] $*"; }
ok()    { color "1;32" "[ OK ] $*"; }
warn()  { color "1;33" "[WARN] $*"; }
err()   { color "1;31" "[ERR ] $*" >&2; }

ask() {
    local q="$1"
    if [ "$YES_ALL" -eq 1 ]; then return 0; fi
    read -rp "$q [Y/n]: " ans </dev/tty || return 0
    case "$ans" in n|N|no|No) return 1 ;; *) return 0 ;; esac
}

rand_hex() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex "$1"
    else
        head -c "$1" /dev/urandom | xxd -p | tr -d '\n'
    fi
}

# 用 sudo 包一层（root 用户跳过）
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
    SUDO="sudo"
fi

# ---------- 1. 系统检测 ----------

case "$(uname -s)" in
    Linux) ok "操作系统: Linux" ;;
    Darwin) warn "macOS 检测到 — 仅支持开发测试，生产请用 Linux" ;;
    *) err "不支持的系统：$(uname -s)"; exit 1 ;;
esac

ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ok "架构: amd64" ;;
    aarch64|arm64) warn "架构: arm64 — 当前镜像仓库仅有 amd64，arm64 拉镜像会失败" ;;
    *) err "不支持的架构：$ARCH"; exit 1 ;;
esac

# ---------- 2. Docker ----------

if ! command -v docker >/dev/null 2>&1; then
    warn "未检测到 docker"
    if ! ask "是否使用阿里云源安装 Docker？"; then
        err "请手动安装 Docker 后重跑本脚本"
        exit 1
    fi
    info "正在安装 Docker（阿里云源）..."
    curl -fsSL https://get.docker.com | $SUDO sh -s -- --mirror Aliyun
    if ! command -v docker >/dev/null 2>&1; then
        err "Docker 安装失败，请手动检查"
        exit 1
    fi
    ok "Docker 安装完成"
    $SUDO systemctl start docker 2>/dev/null || true
    $SUDO systemctl enable docker 2>/dev/null || true
    if [ "$(id -u)" -ne 0 ] && ! groups | grep -q docker; then
        info "正在把当前用户加入 docker 组..."
        $SUDO usermod -aG docker "$USER" || true
        warn "重新登录或运行 'newgrp docker' 后再继续。本次脚本将 sudo 跑 docker。"
        DOCKER_CMD="$SUDO docker"
    else
        DOCKER_CMD="docker"
    fi
else
    ok "已检测到 docker：$(docker --version)"
    DOCKER_CMD="docker"
fi

if ! $DOCKER_CMD compose version >/dev/null 2>&1; then
    err "需要 Docker Compose v2（docker compose 子命令）。请升级 Docker 到 20.10+"
    exit 1
fi
ok "Docker Compose v2 就绪：$($DOCKER_CMD compose version --short 2>/dev/null || echo present)"

# ---------- 3. 工作目录 ----------

INSTALL_BASE="$INSTALL_DIR/install"
$SUDO mkdir -p "$INSTALL_BASE"
$SUDO chown -R "$(id -u):$(id -g)" "$INSTALL_DIR" 2>/dev/null || true

# 数据子目录
for sub in pgdata redisdata projects zips taskLogs persistent workerdata; do
    $SUDO mkdir -p "$INSTALL_DIR/$sub"
done
$SUDO chown -R "$(id -u):$(id -g)" "$INSTALL_DIR" 2>/dev/null || true
ok "数据目录就绪：$INSTALL_DIR"

cd "$INSTALL_BASE"

# ---------- 4. 下载 compose / .env.example / manage.sh ----------

DL() {
    local src="$1" dst="$2"
    info "下载 $dst"
    if ! curl -fsSL "$src" -o "$dst.tmp"; then
        err "下载失败：$src"
        rm -f "$dst.tmp"
        exit 1
    fi
    mv "$dst.tmp" "$dst"
}

DL "$RAW/dist-templates/docker-compose.registry.yml" "docker-compose.yml"
DL "$RAW/dist-templates/.env.example"                 ".env.example"
DL "$RAW/dist-templates/manage.sh"                    "manage.sh"
chmod +x manage.sh

# ---------- 5. 生成 .env ----------

if [ ! -f .env ]; then
    info "未发现 .env，从模板生成并随机化敏感项"
    cp .env.example .env
    SK="$(rand_hex 32)"
    MK="$(rand_hex 24)"
    AP="${ADMIN_PASSWORD:-$(rand_hex 8)}"
    sed -i.bak \
        -e "s|^SECRET_KEY=.*|SECRET_KEY=$SK|" \
        -e "s|^MASTER_LOCAL_API_KEY=.*|MASTER_LOCAL_API_KEY=$MK|" \
        -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$AP|" \
        -e "s|^FRONTEND_PORT=.*|FRONTEND_PORT=$FRONTEND_PORT|" \
        -e "s|^BACKEND_PORT=.*|BACKEND_PORT=$BACKEND_PORT|" \
        -e "s|^DATA_ROOT=.*|DATA_ROOT=$INSTALL_DIR|" \
        -e "s|^VERSION=.*|VERSION=$VERSION|" \
        .env
    rm -f .env.bak
    INITIAL_PASS="$AP"
    ok ".env 已生成"
else
    info ".env 已存在，沿用旧配置"
    INITIAL_PASS=""
fi

# ---------- 6. 拉镜像 + 起服务 ----------

info "从 ACR 拉取镜像（$ACR_REGISTRY/$ACR_NAMESPACE/$ACR_REPO）..."
if ! $DOCKER_CMD compose pull; then
    err "拉镜像失败。如果仓库是私有的，先跑：docker login $ACR_REGISTRY"
    exit 1
fi

info "启动服务（首次会跑 alembic 迁移）"
$DOCKER_CMD compose up -d

# ---------- 7. 等待健康 ----------

info "等待 master 健康（最多 60s）..."
HEALTHY=0
for _ in $(seq 1 30); do
    if curl -fsS "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 2
done
if [ "$HEALTHY" -eq 1 ]; then
    ok "master 健康"
else
    warn "等待超时，请用 ./manage.sh logs 查看错误"
fi

# ---------- 8. 完成 ----------

PUBLIC_IP="$(curl -fsS --max-time 3 https://ipv4.icanhazip.com 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo localhost)"

cat <<EOF

========================================================================
SpiderMan 部署完成

  访问地址：       http://$PUBLIC_IP:$FRONTEND_PORT
  API 健康：       http://$PUBLIC_IP:$BACKEND_PORT/health

  管理员账号：     admin
EOF
if [ -n "$INITIAL_PASS" ]; then
    cat <<EOF
  管理员密码：     $INITIAL_PASS    ← 已自动生成，请立即记录
EOF
else
    cat <<EOF
  管理员密码：     （沿用 .env 里的 ADMIN_PASSWORD）
EOF
fi

cat <<EOF

  日常管理：       cd $INSTALL_BASE && ./manage.sh
  停止：           cd $INSTALL_BASE && ./manage.sh stop
  日志：           cd $INSTALL_BASE && ./manage.sh logs
  升级到新版：     cd $INSTALL_BASE && docker compose pull && docker compose up -d

  数据目录：       $INSTALL_DIR
========================================================================

⚠ 重要：

1. 请确保你的云服务器**安全组**已放行 ${FRONTEND_PORT}/TCP 入方向
   阿里云 ECS 控制台 → 实例 → 安全组 → 配置规则 → 入方向 → 新增

2. 系统防火墙（如果开启了）也要放行：
   firewall-cmd --permanent --add-port=${FRONTEND_PORT}/tcp && firewall-cmd --reload
   或 ufw allow ${FRONTEND_PORT}

EOF

#!/usr/bin/env bash
# SpiderMan 一键安装。在解压后的目录运行：
#   ./install.sh           # 交互模式，缺 Docker 会询问是否安装
#   ./install.sh -y        # 自动模式（自动安装 Docker、生成 .env）
#   ./install.sh --no-docker-install  # 不要自动装 Docker，只检测

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

YES_ALL=0
NO_DOCKER_INSTALL=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) YES_ALL=1 ;;
        --no-docker-install) NO_DOCKER_INSTALL=1 ;;
        -h|--help)
            cat <<EOF
用法: $0 [-y] [--no-docker-install]

  -y, --yes              自动应允一切提示（无人值守）
  --no-docker-install    Docker 没装时不自动安装，只报错退出
EOF
            exit 0
            ;;
    esac
done

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()  { color "1;34" "[INFO] $*"; }
warn()  { color "1;33" "[WARN] $*"; }
err()   { color "1;31" "[ERR ] $*" >&2; }
ok()    { color "1;32" "[ OK ] $*"; }

ask() {
    # ask "question" — return 0=yes 1=no. -y forces yes.
    local q="$1"
    if [ "$YES_ALL" -eq 1 ]; then return 0; fi
    read -rp "$q [Y/n]: " ans
    case "$ans" in n|N|no|No) return 1 ;; *) return 0 ;; esac
}

# ---------- 1. OS check ----------

OS="$(uname -s)"
case "$OS" in
    Linux|Darwin) ok "操作系统: $OS" ;;
    *) err "不支持的操作系统：$OS（仅支持 Linux 和 macOS）"; exit 1 ;;
esac

# ---------- 2. Docker ----------

ensure_docker() {
    if command -v docker >/dev/null 2>&1; then
        ok "已检测到 docker：$(docker --version)"
        return 0
    fi
    warn "未检测到 docker"
    if [ "$NO_DOCKER_INSTALL" -eq 1 ]; then
        err "请手动安装 Docker：https://docs.docker.com/engine/install/"
        exit 1
    fi
    if [ "$OS" = "Darwin" ]; then
        err "macOS 需要安装 Docker Desktop：https://www.docker.com/products/docker-desktop"
        exit 1
    fi
    if ! ask "是否使用官方一键脚本安装 Docker？(curl https://get.docker.com)"; then
        err "已取消。请手动安装 Docker 后重跑此脚本。"
        exit 1
    fi
    info "正在下载并执行 get-docker.sh ..."
    curl -fsSL https://get.docker.com | sh
    if ! command -v docker >/dev/null 2>&1; then
        err "Docker 自动安装失败，请手动安装后重试。"
        exit 1
    fi
    ok "Docker 安装完成"
    if ! groups "$USER" | grep -q docker; then
        warn "建议将当前用户加入 docker 组：sudo usermod -aG docker $USER && newgrp docker"
    fi
    sudo systemctl start docker 2>/dev/null || true
    sudo systemctl enable docker 2>/dev/null || true
}

ensure_compose() {
    if docker compose version >/dev/null 2>&1; then
        ok "Docker Compose v2 已就绪：$(docker compose version --short 2>/dev/null || echo present)"
        return 0
    fi
    err "未检测到 Docker Compose v2（docker compose 子命令）。请升级 Docker 到 v20+ 自带 compose v2。"
    exit 1
}

ensure_docker
ensure_compose

DC="docker compose"

# ---------- 3. .env ----------

if [ ! -f .env ]; then
    info "未发现 .env，从 .env.example 生成"
    cp .env.example .env
    # 生成强随机密钥（避开 tr|head 的 SIGPIPE + pipefail 问题）
    rand_hex() {
        if command -v openssl >/dev/null 2>&1; then
            openssl rand -hex "$1"
        else
            # fallback：xxd 通常装在 vim-common 包里
            head -c "$1" /dev/urandom | xxd -p | tr -d '\n' | cut -c1-$(($1 * 2))
        fi
    }
    SK="$(rand_hex 32)"
    MK="$(rand_hex 24)"
    AP="$(rand_hex 8)"
    sed -i.bak \
        -e "s|^SECRET_KEY=.*|SECRET_KEY=$SK|" \
        -e "s|^MASTER_LOCAL_API_KEY=.*|MASTER_LOCAL_API_KEY=$MK|" \
        -e "s|^ADMIN_PASSWORD=.*|ADMIN_PASSWORD=$AP|" \
        .env
    rm -f .env.bak
    ok ".env 已生成，已为 SECRET_KEY / MASTER_LOCAL_API_KEY / ADMIN_PASSWORD 生成随机值"
    INITIAL_PASS="$AP"
else
    info ".env 已存在，跳过生成"
    INITIAL_PASS=""
fi

# ---------- 4. Data dir ----------

DATA_ROOT="$(grep -E '^DATA_ROOT=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
DATA_ROOT="${DATA_ROOT:-/opt/spiderman}"
info "数据目录：$DATA_ROOT"
SUDO=""
if ! mkdir -p "$DATA_ROOT" 2>/dev/null; then
    SUDO="sudo"
    $SUDO mkdir -p "$DATA_ROOT"
fi
for sub in pgdata redisdata projects zips taskLogs persistent workerdata; do
    $SUDO mkdir -p "$DATA_ROOT/$sub"
done
$SUDO chown -R "$(id -u):$(id -g)" "$DATA_ROOT" 2>/dev/null || true
ok "数据目录已就绪"

# ---------- 5. Load images ----------

if [ -d images ]; then
    for f in images/*.tar.gz images/*.tar; do
        [ -f "$f" ] || continue
        info "导入镜像：$f"
        if [[ "$f" == *.tar.gz ]]; then
            gunzip -c "$f" | docker load
        else
            docker load -i "$f"
        fi
    done
    ok "全部镜像已导入"
else
    warn "未找到 images/ 目录，假设镜像已经在本地或可从远端拉取"
fi

# ---------- 6. Up ----------

info "启动服务（首次会跑 alembic 迁移）"
$DC up -d

# ---------- 7. Health wait ----------

BACKEND_PORT="$(grep -E '^BACKEND_PORT=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="$(grep -E '^FRONTEND_PORT=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

info "等待 master 健康（最多 60s）..."
for i in $(seq 1 30); do
    if curl -fsS "http://localhost:$BACKEND_PORT/health" >/dev/null 2>&1; then
        ok "master 健康"
        break
    fi
    sleep 2
    if [ "$i" -eq 30 ]; then
        warn "等待超时。请用 './manage.sh logs' 查看错误。"
    fi
done

# ---------- Done ----------

ADMIN_USER="$(grep -E '^ADMIN_USERNAME=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
ADMIN_USER="${ADMIN_USER:-admin}"

cat <<EOF

========================================================================
SpiderMan 已部署完成

  访问地址：   http://$(hostname -I 2>/dev/null | awk '{print $1}' || echo localhost):$FRONTEND_PORT
  API 端点：   http://localhost:$BACKEND_PORT/health

  管理员账号： $ADMIN_USER
EOF

if [ -n "$INITIAL_PASS" ]; then
    cat <<EOF
  管理员密码： $INITIAL_PASS    ← 已自动生成，请立即记录
EOF
else
    cat <<EOF
  管理员密码： （沿用 .env 里的 ADMIN_PASSWORD）
EOF
fi

cat <<EOF

  日常管理：   ./manage.sh
  停止：       ./manage.sh stop
  日志：       ./manage.sh logs

  数据目录：   $DATA_ROOT
========================================================================
EOF

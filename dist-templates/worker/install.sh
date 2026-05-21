#!/usr/bin/env bash
# SpiderMan 远程 Worker 一键安装。
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

YES_ALL=0
NO_DOCKER_INSTALL=0
for arg in "$@"; do
    case "$arg" in
        -y|--yes) YES_ALL=1 ;;
        --no-docker-install) NO_DOCKER_INSTALL=1 ;;
    esac
done

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()  { color "1;34" "[INFO] $*"; }
warn()  { color "1;33" "[WARN] $*"; }
err()   { color "1;31" "[ERR ] $*" >&2; }
ok()    { color "1;32" "[ OK ] $*"; }

# Docker check
if ! command -v docker >/dev/null 2>&1; then
    if [ "$NO_DOCKER_INSTALL" -eq 1 ]; then
        err "未检测到 docker，请手动安装：https://docs.docker.com/engine/install/"
        exit 1
    fi
    warn "未检测到 docker"
    read -rp "使用官方一键脚本安装 Docker？[Y/n]: " ans
    case "$ans" in n|N) err "请手动安装 Docker 后重跑"; exit 1 ;; esac
    curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || { err "需要 Docker Compose v2"; exit 1; }
ok "Docker 已就绪"

# .env
if [ ! -f .env ]; then
    err "请先 cp .env.example .env 并填好 MASTER_URL / API_KEY / NODE_ID 后再跑此脚本"
    exit 1
fi

# Validate critical env vars are not the placeholder defaults
for var in MASTER_URL API_KEY NODE_ID; do
    val="$(grep -E "^$var=" .env | cut -d= -f2- | tr -d '"' | tr -d "'")"
    if [ -z "$val" ] || [[ "$val" == *"填入"* ]] || [[ "$val" == *"主控IP"* ]]; then
        err "$var 还没填实际值，请编辑 .env"
        exit 1
    fi
done

# Data dir
DATA_ROOT="$(grep -E '^DATA_ROOT=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
DATA_ROOT="${DATA_ROOT:-/opt/spiderman-worker}"
SUDO=""
mkdir -p "$DATA_ROOT/workerdata" 2>/dev/null || { SUDO="sudo"; $SUDO mkdir -p "$DATA_ROOT/workerdata"; }
$SUDO chown -R "$(id -u):$(id -g)" "$DATA_ROOT" 2>/dev/null || true

# Load image
if [ -d images ]; then
    for f in images/*.tar.gz images/*.tar; do
        [ -f "$f" ] || continue
        info "导入：$f"
        if [[ "$f" == *.tar.gz ]]; then
            gunzip -c "$f" | docker load
        else
            docker load -i "$f"
        fi
    done
fi

info "启动 worker"
docker compose up -d
sleep 3
docker compose ps

cat <<EOF

========================================================================
SpiderMan Worker 已启动
  日志：  docker compose logs -f
  停止：  docker compose stop
  卸载：  docker compose down

请到主控 UI「Worker 节点」页面确认状态变为 online。
========================================================================
EOF

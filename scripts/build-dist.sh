#!/usr/bin/env bash
# SpiderMan 离线交付包构建脚本（在开发机上跑）。
#
# 输出：
#   dist/spiderman-<VERSION>-linux-<ARCH>.tar.gz         # 主控 + 内置 worker
#   dist/spiderman-<VERSION>-worker-linux-<ARCH>.tar.gz  # 仅 worker（远程节点用）
#   dist/images/{master,frontend,worker}.tar.gz         # 单个镜像（增量升级用）
#
# 用法：
#   bash scripts/build-dist.sh             # 默认 VERSION=1.0
#   VERSION=1.0.1 bash scripts/build-dist.sh
#   bash scripts/build-dist.sh --skip-build   # 直接打包当前 docker images（不重新 build）

set -euo pipefail

VERSION="${VERSION:-1.0}"
# TARGET_ARCH 决定要构建给哪个架构的服务器跑（默认随宿主）。
# 在 Apple Silicon 上交叉构建 amd64 包给云服务器：TARGET_ARCH=amd64
ARCH_RAW="${TARGET_ARCH:-$(uname -m)}"
case "$ARCH_RAW" in
    x86_64|amd64) ARCH=amd64 ; PLATFORM=linux/amd64 ;;
    aarch64|arm64) ARCH=arm64 ; PLATFORM=linux/arm64 ;;
    *) ARCH="$ARCH_RAW" ; PLATFORM="linux/$ARCH_RAW" ;;
esac

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

DIST="$REPO_ROOT/dist"
TEMPLATES="$REPO_ROOT/dist-templates"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()  { color "1;34" "[INFO] $*"; }
ok()    { color "1;32" "[ OK ] $*"; }

SKIP_BUILD=0
for arg in "$@"; do
    case "$arg" in --skip-build) SKIP_BUILD=1 ;; esac
done

mkdir -p "$DIST/images"

# ---------- 1. Build prod images ----------

if [ "$SKIP_BUILD" -eq 0 ]; then
    info "目标架构: $PLATFORM"
    # buildx 支持交叉编译。--load 把镜像加载进本地 docker daemon。
    info "构建 master 镜像 (spiderman/master:$VERSION) ..."
    docker buildx build --platform "$PLATFORM" -f backend/Dockerfile.prod \
        -t "spiderman/master:$VERSION" --load backend

    info "构建 frontend 镜像 ..."
    docker buildx build --platform "$PLATFORM" \
        -t "spiderman/frontend:$VERSION" --load frontend

    info "构建 worker 镜像 ..."
    docker buildx build --platform "$PLATFORM" -f worker/Dockerfile.prod \
        -t "spiderman/worker:$VERSION" --load worker
else
    info "跳过 build，使用现有镜像"
fi

# ---------- 2. Save ----------

info "保存镜像到 $DIST/images/ ..."
docker save "spiderman/master:$VERSION"   | gzip -1 > "$DIST/images/master.tar.gz"
docker save "spiderman/frontend:$VERSION" | gzip -1 > "$DIST/images/frontend.tar.gz"
docker save "spiderman/worker:$VERSION"   | gzip -1 > "$DIST/images/worker.tar.gz"
ok "镜像保存完毕：$(du -sh "$DIST/images" | awk '{print $1}')"

# ---------- 3. Stage main bundle ----------

NAME="spiderman-$VERSION-linux-$ARCH"
STAGE="$DIST/$NAME"
rm -rf "$STAGE"
mkdir -p "$STAGE/images"
cp "$DIST/images"/{master,frontend,worker}.tar.gz "$STAGE/images/"
cp "$TEMPLATES/docker-compose.yml" "$STAGE/"
cp "$TEMPLATES/.env.example" "$STAGE/"
cp "$TEMPLATES/install.sh" "$STAGE/"
cp "$TEMPLATES/manage.sh" "$STAGE/"
cp "$TEMPLATES/README.md" "$STAGE/" 2>/dev/null || true
if [ -d "$TEMPLATES/scripts" ]; then
    cp -r "$TEMPLATES/scripts" "$STAGE/"
    chmod +x "$STAGE/scripts"/*.sh 2>/dev/null || true
fi
chmod +x "$STAGE/install.sh" "$STAGE/manage.sh"

# Stamp version into shipped files
sed -i.bak "s|^VERSION=.*|VERSION=$VERSION|" "$STAGE/.env.example"
rm -f "$STAGE/.env.example.bak"

info "打包主控 tar"
tar -czf "$DIST/$NAME.tar.gz" -C "$DIST" "$NAME"
rm -rf "$STAGE"
ok "主控包：$DIST/$NAME.tar.gz ($(du -sh "$DIST/$NAME.tar.gz" | awk '{print $1}'))"

# ---------- 4. Worker-only bundle ----------

WNAME="spiderman-$VERSION-worker-linux-$ARCH"
WSTAGE="$DIST/$WNAME"
rm -rf "$WSTAGE"
mkdir -p "$WSTAGE/images"
cp "$DIST/images/worker.tar.gz" "$WSTAGE/images/"
cp "$TEMPLATES/worker/docker-compose.yml" "$WSTAGE/"
cp "$TEMPLATES/worker/.env.example" "$WSTAGE/"
cp "$TEMPLATES/worker/install.sh" "$WSTAGE/"
cp "$TEMPLATES/worker/README.md" "$WSTAGE/"
chmod +x "$WSTAGE/install.sh"
sed -i.bak "s|^VERSION=.*|VERSION=$VERSION|" "$WSTAGE/.env.example"
rm -f "$WSTAGE/.env.example.bak"

info "打包远程 worker tar"
tar -czf "$DIST/$WNAME.tar.gz" -C "$DIST" "$WNAME"
rm -rf "$WSTAGE"
ok "Worker 包：$DIST/$WNAME.tar.gz ($(du -sh "$DIST/$WNAME.tar.gz" | awk '{print $1}'))"

# ---------- Summary ----------

cat <<EOF

========================================================================
SpiderMan v$VERSION 离线交付包构建完成

  架构：      linux-$ARCH
  主控包：    $DIST/$NAME.tar.gz
  Worker 包： $DIST/$WNAME.tar.gz
  独立镜像：  $DIST/images/{master,frontend,worker}.tar.gz

下一步：
  1. 把主控包发给运维 → 解开 → ./install.sh
  2. 远程 worker 节点 → 把 worker 包发过去 → 编辑 .env → ./install.sh
  3. Windows worker：让该 Windows 机器跑 worker/build_windows.bat
========================================================================
EOF

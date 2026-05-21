#!/usr/bin/env bash
# 把已经构建好的 spiderman 镜像推到阿里云 ACR（或任意 registry）。
#
# 前置：本地 docker images 里要有 spiderman/master:VERSION 等三个镜像。
# 通常在跑过 scripts/build-dist.sh 之后用。
#
# 用法：
#   bash scripts/push-to-acr.sh                # 用脚本默认配置（你的仓库）
#   REGISTRY=... NAMESPACE=... REPO=... bash scripts/push-to-acr.sh
#
# 默认目标：crpi-nckaq92hgnekr1fo.cn-hangzhou.personal.cr.aliyuncs.com/cookies886/spider_man_task
# 三个 tag：master-1.0 / frontend-1.0 / worker-1.0

set -euo pipefail

REGISTRY="${REGISTRY:-crpi-nckaq92hgnekr1fo.cn-hangzhou.personal.cr.aliyuncs.com}"
NAMESPACE="${NAMESPACE:-cookies886}"
REPO="${REPO:-spider_man_task}"
VERSION="${VERSION:-1.0}"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info() { color "1;34" "[INFO] $*"; }
ok()   { color "1;32" "[ OK ] $*"; }
err()  { color "1;31" "[ERR ] $*" >&2; }

REMOTE="$REGISTRY/$NAMESPACE/$REPO"
info "目标仓库：$REMOTE"

# 1. 登录（如果未登录会要密码，登录过就跳过）
if ! docker info 2>/dev/null | grep -q "Username:"; then
    info "请输入 ACR 固定密码（不是阿里云账号密码）"
    docker login "$REGISTRY"
fi

# 2. 检查本地镜像存在
for c in master frontend worker; do
    if ! docker image inspect "spiderman/$c:$VERSION" >/dev/null 2>&1; then
        err "本地缺少镜像 spiderman/$c:$VERSION，请先跑 bash scripts/build-dist.sh"
        exit 1
    fi
done

# 3. tag + push
for c in master frontend worker; do
    REMOTE_TAG="$REMOTE:$c-$VERSION"
    info "tag spiderman/$c:$VERSION → $REMOTE_TAG"
    docker tag "spiderman/$c:$VERSION" "$REMOTE_TAG"
    info "push $REMOTE_TAG ..."
    docker push "$REMOTE_TAG"
    ok "$c 推送完成"
done

cat <<EOF

========================================================================
全部推送完成。其他机器拉取部署：

  在 docker-compose.yml 里把 image: 行改成：

    master:
      image: $REMOTE:master-$VERSION
    frontend:
      image: $REMOTE:frontend-$VERSION
    master_local_worker:
      image: $REMOTE:worker-$VERSION

  然后：
    docker login $REGISTRY     # 私有仓库要登录；公开仓库免登录
    docker compose pull
    docker compose up -d
========================================================================
EOF

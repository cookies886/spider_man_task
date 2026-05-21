#!/usr/bin/env bash
# SpiderMan 日常管理。无参数进入交互菜单，或 ./manage.sh <cmd>。

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

DC="docker compose"

color() { printf "\033[%sm%s\033[0m\n" "$1" "$2"; }
info()  { color "1;34" "[INFO] $*"; }
warn()  { color "1;33" "[WARN] $*"; }
err()   { color "1;31" "[ERR ] $*" >&2; }
ok()    { color "1;32" "[ OK ] $*"; }

require_env() {
    if [ ! -f .env ]; then
        err "找不到 .env，请先跑 ./install.sh"
        exit 1
    fi
}

cmd_status() {
    require_env
    $DC ps
}

cmd_start() {
    require_env
    $DC up -d
    ok "已启动"
}

cmd_stop() {
    require_env
    $DC stop
    ok "已停止"
}

cmd_restart() {
    require_env
    $DC restart
    ok "已重启"
}

cmd_logs() {
    require_env
    if [ -n "${1:-}" ]; then
        $DC logs -f --tail 200 "$1"
    else
        $DC logs -f --tail 200
    fi
}

cmd_upgrade() {
    require_env
    if [ ! -d images ]; then
        err "未找到 images/ 目录。请把新版 tar 包解开覆盖到当前目录后再跑此命令。"
        exit 1
    fi
    info "导入新镜像"
    for f in images/*.tar.gz images/*.tar; do
        [ -f "$f" ] || continue
        info "导入：$f"
        if [[ "$f" == *.tar.gz ]]; then
            gunzip -c "$f" | docker load
        else
            docker load -i "$f"
        fi
    done
    info "重建容器"
    $DC up -d --force-recreate
    ok "升级完成"
}

cmd_backup() {
    require_env
    DATA_ROOT="$(grep -E '^DATA_ROOT=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
    DATA_ROOT="${DATA_ROOT:-/opt/spiderman}"
    if [ ! -d "$DATA_ROOT" ]; then
        err "数据目录不存在：$DATA_ROOT"
        exit 1
    fi
    BACKUP_FILE="spiderman-backup-$(date +%Y%m%d-%H%M%S).tar.gz"
    info "备份 $DATA_ROOT → $BACKUP_FILE"
    info "提示：建议先 './manage.sh stop' 以避免文件正在写入"
    tar -czf "$BACKUP_FILE" -C "$(dirname "$DATA_ROOT")" "$(basename "$DATA_ROOT")"
    ok "备份完成：$BACKUP_FILE ($(du -h "$BACKUP_FILE" | cut -f1))"
}

cmd_uninstall() {
    require_env
    warn "这会停止并删除所有容器。"
    read -rp "确认卸载？[y/N]: " ans
    case "$ans" in y|Y|yes|Yes) ;; *) info "已取消"; exit 0 ;; esac
    $DC down
    ok "容器已删除"

    DATA_ROOT="$(grep -E '^DATA_ROOT=' .env | cut -d= -f2 | tr -d '"' | tr -d "'")"
    DATA_ROOT="${DATA_ROOT:-/opt/spiderman}"
    warn "数据目录：$DATA_ROOT"
    read -rp "是否同时删除数据目录？删除后无法恢复 [y/N]: " ans
    case "$ans" in
        y|Y|yes|Yes)
            if [ -w "$DATA_ROOT" ] || [ "$(id -u)" -eq 0 ]; then
                rm -rf "$DATA_ROOT"
            else
                sudo rm -rf "$DATA_ROOT"
            fi
            ok "数据目录已删除"
            ;;
        *)
            info "已保留数据目录：$DATA_ROOT"
            ;;
    esac
}

cmd_edit_env() {
    require_env
    "${EDITOR:-vi}" .env
    info "如修改了端口/密码等，请运行：./manage.sh restart"
}

cmd_cron_backup() {
    require_env
    SCRIPT_PATH="$SCRIPT_DIR/scripts/backup.sh"
    if [ ! -f "$SCRIPT_PATH" ]; then
        err "找不到 backup.sh，预期路径：$SCRIPT_PATH"
        exit 1
    fi
    chmod +x "$SCRIPT_PATH"
    CRON_LINE="0 3 * * * cd $SCRIPT_DIR && bash scripts/backup.sh >> /var/log/spiderman-backup.log 2>&1"

    if crontab -l 2>/dev/null | grep -q "spiderman.*backup.sh"; then
        info "crontab 已存在 SpiderMan 备份任务："
        crontab -l | grep "backup.sh"
        read -rp "是否覆盖？[y/N]: " ans
        case "$ans" in y|Y|yes|Yes) ;; *) info "已取消"; exit 0 ;; esac
        ( crontab -l 2>/dev/null | grep -v "spiderman.*backup.sh"; echo "$CRON_LINE" ) | crontab -
    else
        ( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -
    fi
    ok "已添加 cron：每天 03:00 自动备份"
    info "查看：crontab -l"
    info "立即测试备份：bash scripts/backup.sh"
}

cmd_cron_backup_remove() {
    if crontab -l 2>/dev/null | grep -q "spiderman.*backup.sh"; then
        crontab -l | grep -v "spiderman.*backup.sh" | crontab -
        ok "已从 crontab 移除备份任务"
    else
        info "crontab 中没有 SpiderMan 备份任务"
    fi
}

show_menu() {
    cat <<EOF

==================== SpiderMan 管理 ====================
  1) 启动服务         (start)
  2) 停止服务         (stop)
  3) 重启服务         (restart)
  4) 查看状态         (status)
  5) 查看日志         (logs)
  6) 升级             (upgrade)
  7) 立即备份         (backup)
  8) 编辑 .env        (edit-env)
  9) 卸载             (uninstall)
  a) 启用每日自动备份 (cron-backup)
  b) 关闭自动备份     (cron-backup-remove)
  0) 退出
========================================================
EOF
}

if [ $# -gt 0 ]; then
    case "$1" in
        start)              cmd_start ;;
        stop)               cmd_stop ;;
        restart)            cmd_restart ;;
        status|ps)          cmd_status ;;
        logs)               shift; cmd_logs "$@" ;;
        upgrade)            cmd_upgrade ;;
        backup)             cmd_backup ;;
        uninstall)          cmd_uninstall ;;
        edit-env)           cmd_edit_env ;;
        cron-backup)        cmd_cron_backup ;;
        cron-backup-remove) cmd_cron_backup_remove ;;
        *) err "未知命令：$1"; exit 1 ;;
    esac
    exit 0
fi

while true; do
    show_menu
    read -rp "请选择 [0-9]: " choice
    case "$choice" in
        1) cmd_start ;;
        2) cmd_stop ;;
        3) cmd_restart ;;
        4) cmd_status ;;
        5) cmd_logs ;;
        6) cmd_upgrade ;;
        7) cmd_backup ;;
        8) cmd_edit_env ;;
        9) cmd_uninstall; break ;;
        a|A) cmd_cron_backup ;;
        b|B) cmd_cron_backup_remove ;;
        0) exit 0 ;;
        *) warn "无效选择" ;;
    esac
done

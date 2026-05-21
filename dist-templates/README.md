# SpiderMan 一键部署

## 快速开始

```bash
tar -xzf spiderman-1.0-linux-amd64.tar.gz
cd spiderman-1.0-linux-amd64
./install.sh
```

`install.sh` 会自动：

- 检测 Docker（缺失时询问是否一键安装）
- 创建数据目录 `${DATA_ROOT:-/opt/spiderman}/`
- 生成 `.env` 并随机化 `SECRET_KEY` / `MASTER_LOCAL_API_KEY` / `ADMIN_PASSWORD`
- 导入 `images/*.tar.gz` 三个镜像
- 跑数据库迁移并启动全部服务
- 等待健康检查通过

完成后浏览器打开 `http://本机IP:3000`。**首次登录的随机管理员密码会打印在终端**，请妥善保存（也可以在 `.env` 里查到）。

## 系统要求

- Linux（x86_64 / arm64）或 macOS
- Docker 20.10+ 自带 Compose v2
- ~2GB 内存、~2GB 磁盘

## 目录结构

```
spiderman-1.0-linux-amd64/
├── docker-compose.yml      # 容器编排
├── .env.example            # 环境变量模板
├── install.sh              # 一键安装
├── manage.sh               # 日常运维（菜单或子命令）
├── images/
│   ├── master.tar.gz
│   ├── frontend.tar.gz
│   └── worker.tar.gz
└── README.md
```

数据落盘位置（默认 `/opt/spiderman/`）：

| 子目录 | 内容 |
|---|---|
| `pgdata/` | Postgres |
| `redisdata/` | Redis |
| `projects/` | 用户上传的项目源码 |
| `zips/` | 项目打包用 zip |
| `taskLogs/` | 任务运行日志 (JSONL) |
| `persistent/` | 持久化文件管理 |
| `workerdata/` | master_local worker 工作目录 |

## 日常运维

```bash
./manage.sh                # 进入交互菜单
./manage.sh status         # 查看容器状态
./manage.sh logs master    # 跟随 master 日志
./manage.sh restart        # 全栈重启
./manage.sh backup         # 整库 + 文件备份成 tar.gz
./manage.sh edit-env       # 编辑 .env，记得 restart
```

## 升级到新版本

```bash
# 拿到新 tar 包
tar -xzf spiderman-1.0.1-linux-amd64.tar.gz --strip 1
./manage.sh upgrade
```

`upgrade` 会重新 `docker load` 并 `--force-recreate` 容器，数据不动。

## 卸载

```bash
./manage.sh uninstall
# 会问是否同时删除 /opt/spiderman 数据目录
```

## 添加远程 Worker

主控独立可用，但你可以加更多执行节点：

- **Linux 节点**：用 `spiderman-1.0-worker-linux-*.tar.gz`，里面有自己的 README。
- **Windows 节点**：你需要在 Windows 机器上跑 `worker/build_windows.bat` 产出 `windows_worker.exe`，或者向开发者要现成的 zip。

无论哪种节点，先在主控 UI **Worker 节点 → + 添加节点**，**保存时显示的 API Key 只显示一次**，必须复制下来填到 worker 的 `.env`。

## 常见问题

**`./install.sh` 报 "需要 Docker Compose v2"**
旧版 `docker-compose`（带横线）不支持。要用 Docker 20.10+ 自带的 `docker compose`（空格）。
升级 Docker：`curl -fsSL https://get.docker.com | sh`

**端口 3000 / 8000 被占用**
编辑 `.env` 改 `FRONTEND_PORT` 和 `BACKEND_PORT`，再 `./manage.sh restart`。

**忘了管理员密码**
`.env` 里 `ADMIN_PASSWORD` 是首次登录的密码（之后用户在 UI 改的密码存数据库）。如果你在 UI 里改过且忘了，目前需要进 master 容器手动重置：

```bash
docker compose exec master python -c "
from app.core.database import async_session
from app.core.security import hash_password
from app.models.user import User
from sqlalchemy import select
import asyncio
async def f():
    async with async_session() as s:
        u = (await s.execute(select(User).where(User.username=='admin'))).scalar_one()
        u.password_hash = hash_password('new-password-here')
        await s.commit()
asyncio.run(f())
"
```

**`SECRET_KEY` 改了之后旧加密数据无法读**
设计如此 — `SECRET_KEY` 派生 Fernet key 加密 git 凭据 / 环境变量。任何时候**不要改 `SECRET_KEY`**，改了等于把所有加密数据作废。

**Docker 镜像太大想瘦身**
单镜像 master ~700MB（含 Python 编译工具链以支持运行时编译 Python 多版本）、frontend ~60MB、worker ~160MB。可以删除 master 中的 `build-essential` 等 dev 依赖会缩到 ~250MB，但运行时新增 Python 版本的功能会失效。

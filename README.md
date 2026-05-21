# SpiderMan

Distributed Python task scheduling platform — a TaskPyro Pro-compatible reimplementation
(without the AI assistant / commercial license layer). Master-Worker architecture with a
lightweight HTTP/WebSocket worker protocol that runs on Windows / Linux / macOS as a
plain Python process.

## 持续集成 / 自动发布

`.github/workflows/ci.yml` — push / PR 到 main 时自动跑 backend + worker 后端测试 + 前端 build。
`.github/workflows/release.yml` — `git tag v1.0.x && git push --tags` 时自动用 buildx 构 amd64+arm64 双架构镜像，推到 ACR，并发 GitHub Release。

**首次启用**：在 GitHub Settings → Secrets and variables → Actions 添加：

| Secret | 值 |
|---|---|
| `ACR_USERNAME` | 你的阿里云 ACR 账号名（如 `ckcookies666`） |
| `ACR_PASSWORD` | ACR 控制台 → 个人实例 → 访问凭证 → 设的固定密码 |

发版示例：

```bash
git tag v1.0.1
git push origin v1.0.1
```

## 一键部署（最便捷）

任意 Linux 服务器（amd64）上：

```bash
curl -fsSL https://raw.githubusercontent.com/ckcookies666/spider_man_task/main/install-spiderman.sh | bash
```

脚本会自动：
- 检测 / 安装 Docker（缺失时使用阿里云源一键安装）
- 拉取预构建镜像（来自 ACR：`crpi-nckaq92hgnekr1fo.cn-hangzhou.personal.cr.aliyuncs.com/ckcookies666/spider_man_task`）
- 生成 `.env` 并随机化敏感密钥
- 启动全栈 + 跑数据库迁移
- 等待健康检查通过
- 终端打印访问地址 + 自动生成的管理员密码

完成后浏览器开 `http://你的服务器IP:3000`。**记得在云服务器安全组放行 3000/TCP**。

无人值守模式（CI/批量部署）：

```bash
YES_ALL=1 curl -fsSL https://raw.githubusercontent.com/ckcookies666/spider_man_task/main/install-spiderman.sh | bash
```

## Features

| 模块 | 能力 |
|---|---|
| **任务调度** | Cron / Interval / Once / Immediate；并发策略 (skip/queue)；重试；超时；任务依赖链 (DAG，含闭环检测) |
| **分布式执行** | 6 种节点选择策略 (auto/master/specific/group/platform/mixed)；轻量 HTTP+WS Worker，跨平台原生进程部署 |
| **项目管理** | ZIP 上传 + 自动推断工作路径；Git 仓库 (HTTPS + 私有凭据) clone/pull；Monaco 在线代码编辑；项目 hash 自动同步到 Worker |
| **虚拟环境** | venv 创建；6 个内置 PyPI 镜像源；可指定 Python 版本；`requirements.txt` 安装日志流式落盘 |
| **Python 多版本** | 主控容器内从源码编译多个 Python 版本（需 build deps，见下文） |
| **实时日志** | WebSocket 转发 stdout/stderr，浏览器实时滚动 |
| **RBAC** | 用户 / 角色 / 权限 / 页面 ACL 三层鉴权；JWT Access(15m) + Refresh(7d) |
| **仪表盘** | ECharts 图表：CPU/内存/磁盘/网络时序；任务成功率趋势；24h 分布；60d 日历热力；甘特图 |
| **运维** | 钉钉/飞书/企业微信 Webhook + SMTP 邮件通知；持久化文件管理；任务日志归档 + 自动清理；环境变量 Fernet 加密 |

## Quick Start (Docker)

需要 Docker Desktop（macOS/Windows）或 Docker Engine + Compose（Linux）。

```bash
git clone <this repo>
cd xk_ai_study

# 一键起 stack：postgres + redis + master + master_local worker + frontend
docker compose up -d --build

# 等约 15s，验证健康
curl http://localhost:8000/health    # {"status":"ok"}
curl -I http://localhost:3000/       # frontend (nginx) 200

# 浏览器访问
open http://localhost:3000           # 默认账号 admin / admin123
```

服务清单：

| 服务 | 端口 | 说明 |
|---|---|---|
| `postgres` | 5432 | 持久化数据 |
| `redis` | 6379 | WebSocket PubSub + dashboard 缓存 |
| `master` | 8000 | FastAPI + WebSocket 服务端 |
| `frontend` | 3000 | React (Vite build) + nginx 反代 `/api/v1`、`/ws` 到 master |
| `master_local_worker` | — | 与 master 同 compose 网络的内置 Worker；用 `MASTER_LOCAL_API_KEY` bearer 鉴权反向连入 `/ws/worker` |

环境变量（`docker-compose.yml` 已带默认值）：

```
SECRET_KEY                # JWT + Fernet 派生密钥（生产环境必须改）
ADMIN_USERNAME=admin
ADMIN_PASSWORD=admin123
MASTER_LOCAL_NODE_ID=master-local
MASTER_LOCAL_API_KEY=dev-master-local-key
DATABASE_URL=postgresql+asyncpg://spiderman:spiderman@postgres:5432/spiderman
REDIS_URL=redis://redis:6379/0
```

## 增加远程 Worker

Worker 是独立 Python 包，跨平台跑原生进程，**不需要 Redis 或 Docker**，只要能连上 master 的 8000 端口（HTTP + WebSocket）。

```bash
# 在远程节点上
git clone <this repo>
cd xk_ai_study/worker
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

在主控 Web UI（管理员）`Worker 节点 → 添加节点` 创建一行，**保存 API Key**（明文只显示一次），然后在远程节点：

```bash
export MASTER_URL=ws://<master-host>:8000
export API_KEY=<刚才显示的 api_key>
export NODE_ID=<填的 node_id>
export NODE_NAME=remote-prod-1
export WORK_DIR=/var/lib/spiderman_worker
spiderman-worker
```

Worker 启动后会反向连入 master 的 `/ws/worker?node_id=...&token=...`，注册成功后可在 `Worker 节点` 列表看到 `online`，并参与任务调度。

## 本地开发

需要 Python 3.12+、Node 20+、postgres 16、redis 7（或者跑 `docker compose up -d postgres redis`）。

```bash
# 后端
cd backend
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Worker
cd worker
pip install -e ".[dev]"
MASTER_URL=ws://localhost:8000 API_KEY=dev-master-local-key \
  NODE_ID=master-local NODE_NAME=master-local \
  WORK_DIR=/tmp/spiderman_worker_local \
  spiderman-worker

# 前端
cd frontend
npm install
npm run dev   # http://localhost:5173
```

## 测试

```bash
# 后端单元测试 (37)
cd backend && pytest -q

# Worker 单元测试 (3)
cd worker && pytest -q

# 全栈 E2E (15) — 需要 master + master_local worker 都在跑
pytest tests/e2e/test_full_smoke.py -v
```

## 构建离线发布包

```bash
# 主控 + 内置 worker 包 + 远程 Linux worker 包
bash scripts/build-dist.sh
# 产物：
#   dist/spiderman-1.0-linux-amd64.tar.gz
#   dist/spiderman-1.0-worker-linux-amd64.tar.gz

# 自定义版本号
VERSION=1.0.1 bash scripts/build-dist.sh

# Windows worker .exe（需要在 Windows 机器上跑）
cd worker && build_windows.bat
# 产物：worker/dist_release/windows_worker_1.0.zip
```

`scripts/build-dist.sh` 会用 `backend/Dockerfile.prod` / `worker/Dockerfile.prod` 构建生产镜像（无 dev extras、无 reload、autorun alembic），`docker save` 后连同 `dist-templates/` 里的 compose / install.sh / manage.sh 打成 tar.gz。最终用户拿到 tar.gz 后只需 `./install.sh` 一步。详见 `dist-templates/README.md`。

## 架构

```
                         ┌───────────────────┐
                         │   用户浏览器       │
                         └─────────┬─────────┘
                                   │
                       ┌───────────▼─────────┐
                       │  Frontend (nginx)   │  http://*:3000
                       │  React + Monaco     │
                       │  + ECharts          │
                       └─────────┬───────────┘
                                 │ proxy /api/v1, /ws
                       ┌─────────▼───────────┐
                       │   Master (FastAPI)  │  http://*:8000
                       │   + APScheduler     │
                       │   + Worker Registry │
                       └────┬──────┬─────┬───┘
                            │      │     │
                ┌───────────▼──┐ ┌─▼──┐ ┌▼────────────────┐
                │  PostgreSQL  │ │Redis│ │  Worker (WS)    │
                │              │ │     │ │  反向连入        │
                └──────────────┘ └─────┘ │  [Win/Linux/Mac]│
                                         └─────────────────┘
```

数据流（任务执行）：

```
1. APScheduler 触发 / 用户点击「立即运行」
2. dispatcher.trigger_run → 创建 task_run (status=DISPATCHING)
3. 按节点策略 + 在线状态选 worker (least_loaded)
4. send_task_run frame → WS 推送给 worker
5. worker 拿 project_id+expected_hash，按需 GET /api/v1/projects/{id}/zip 拉新代码
6. subprocess 执行命令，每行 stdout/stderr → task.log frame 回 master
7. master /ws/worker 处理器 → Redis PUBLISH task.log.{run_id}
8. 浏览器订阅 /ws/runs/{run_id}/logs，实时滚动
9. 进程结束 → task.done frame → master 更新 task_run，触发依赖链 / 通知
```

## 通知渠道

`消息通知` 页面创建渠道 + 规则：

| 类型 | 配置字段 |
|---|---|
| 钉钉 | `webhook` + 可选 `secret`（HMAC-SHA256 加签） |
| 飞书 | `webhook`（v2/hook 协议） |
| 企业微信 | `webhook`（cgi-bin/webhook/send） |
| 邮件 | `recipients[]`，依赖 `系统设置 → 邮件 (SMTP)` |

事件类型：`task_failed` / `task_timeout` / `task_killed` / `worker_offline`

## Python 多版本（高级特性）

默认的 docker 镜像没有源码编译需要的依赖（为了构建速度）。要启用 Python 多版本编译，
重新构建一个加全依赖的镜像：

```dockerfile
# backend/Dockerfile.pyver
FROM xk_ai_study-master
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
    libffi-dev libncurses-dev libgdbm-dev libnss3-dev liblzma-dev tk-dev wget \
    && rm -rf /var/lib/apt/lists/*
```

或者在 `docker-compose.yml` 里改 master service 直接用扩展 Dockerfile。源码编译耗时
**10-30 分钟**（取决于硬件），全程日志可在「Python 版本管理」页面下载。

## 安全提示

生产部署前必改：

- [ ] `SECRET_KEY`：JWT 签名 + Fernet 派生密钥（任何长随机字符串，**改一次后不要再变**，否则旧加密数据无法解密）
- [ ] `ADMIN_PASSWORD`：默认 `admin123`，登录后立即改
- [ ] `MASTER_LOCAL_API_KEY`：master_local worker bearer 鉴权
- [ ] CORS：`backend/app/main.py` 当前 `allow_origins=["*"]`，生产收紧
- [ ] HTTPS：master 8000 端口前面加 nginx/caddy 反代 + TLS

## 故障排查

**Worker 无法注册 (`connection lost, retry in Ns`)**
- 检查 `MASTER_URL`（`ws://` 不是 `http://`）
- `API_KEY` 与主控 `Worker 节点` 列表里那行一一对应
- master 的 `/ws/worker` 端口可达：`curl -I http://master:8000/health`

**任务一直 `pending`**
- 「Worker 节点」页面看节点 status 是否 `online`
- 节点策略是否能匹配（specific 节点要 ID 精确，platform 要 OS prefix）

**Docker arm64 下 master 启动 SIGILL**
- 已知 `cryptography>=44` 与 Docker Desktop arm64 不兼容；`pyproject.toml` 已 pin `<44`

**前端登录后不跳转**
- 浏览器 devtools 看 `/api/v1/auth/login` 响应
- 后端日志：`docker compose logs master`

## 项目布局

```
backend/         FastAPI + SQLAlchemy 2.0 async
  app/api/       REST 端点（按业务切分）
  app/core/      运行时核心：dispatcher / runs / scheduler / notifier / file_manager / git_sync ...
  app/models/    ORM
  app/schemas/   Pydantic v2
  app/ws/        WebSocket: /ws/worker (worker 反向接入), /ws/runs/{id}/logs (浏览器订阅)
  migrations/    Alembic
  tests/         单元 + 集成

worker/          独立可发布 pip 包：spiderman-worker
  agent/
    config.py    env 配置
    connector.py WebSocket 反向连接 + 指数退避重连
    executor.py  subprocess 行级流式输出 + 超时/SIGTERM/SIGKILL
    heartbeat.py psutil 采样
    main.py      WorkerRuntime 入口（signal handlers + frame router）

frontend/        React + Vite + shadcn/ui + TanStack Query + ECharts + Monaco
  src/api/       axios client
  src/pages/     dashboard / projects / project-detail / tasks / task-detail / workers /
                 environments / python-versions / users / notifications / files / logs / settings
  src/store/     zustand auth store

tests/e2e/       端到端冒烟（API + WS + 状态机）

docs/superpowers/
  specs/         设计文档
  plans/         切片实现 plan

docker-compose.yml  完整 stack 编排
```

## 致谢

接口契约和 UI 范型参考 [TaskPyro Pro](https://docs.taskpyro.cn/professional/)。

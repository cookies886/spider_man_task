# SpiderMan 远程 Worker (Linux)

将 Linux 机器加入 SpiderMan 集群作为执行节点。**不需要安装 Python**（Worker 跑在 Docker 容器里）。

## 步骤

### 1. 在主控（master）上添加一行节点记录

登录主控 Web UI（管理员），左侧 **Worker 节点 → + 添加节点**，填：

- 名称: `remote-prod-1`（任意）
- hostname: 这台机器的 hostname
- IP: 这台机器的 IP
- 端口: 8001

保存后会**一次性显示**一段 `api_key` 形如 `EAJ_K3F0pZ...` —— 把它复制下来，关掉对话框后就再也看不到。

### 2. 在远程机器上解开本包

```bash
tar -xzf spiderman-1.0-worker-linux-amd64.tar.gz
cd spiderman-1.0-worker-linux-amd64
cp .env.example .env
vi .env   # 填 MASTER_URL / API_KEY / NODE_ID 三项
./install.sh
```

`install.sh` 会：
- 检测 Docker，没装会问你是否一键装
- 校验 `.env` 三个必填项
- 导入 Worker 镜像
- `docker compose up -d` 启动

### 3. 回主控 UI 看节点状态

`Worker 节点` 页面应能看到这台节点变 `online`。在创建任务时把节点策略选 `specific` 并填 node_id，就能让任务跑到这台机器上。

## 常用运维

```bash
docker compose ps           # 状态
docker compose logs -f      # 跟随日志
docker compose restart      # 重启
docker compose stop         # 停
docker compose down         # 卸载（保留数据）
```

## 排错

**`connection lost, retry in Ns` 反复打印**
- 检查 `.env` 里 `MASTER_URL` 是 `ws://` 不是 `http://`
- 检查能 ping 通主控、能 `curl http://主控IP:8000/health`
- 检查 `API_KEY` 与 `NODE_ID` 跟主控记录的一致

**主控 UI 看到节点是 offline**
- worker 容器跑起来吗？`docker compose ps`
- 主控的 8000 端口对这台机器开放吗？

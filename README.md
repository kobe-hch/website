# 指数盈利分解网页展示

将 `code.py` 的核心“图表 + 表格”输出迁移为网页交互形式。

## 功能

- 输入证券名称（如 `龙蟠科技`）或 Wind 代码（如 `603906.SH`）生成图像。
- 保留原风格静态总图（Matplotlib）。
- 新增交互式折线图（Plotly），可悬停查看每个坐标点的日期和数值。
- 提供折线图坐标点明细表，并支持导出 CSV。
- 页面内「数据维护」：周度更新 parquet、添加新资产；可选「补充最近交易日快照（内存）」。

## 暂未实现（已预留接口）

- `initialize_data()`（对应 `code.py` 36-96 全量初始化）
- `batch_clean_data()`（对应 `code.py` 299-315）

## 依赖安装

在项目根目录执行：

```bash
pip install -r 网页展示/requirements.txt
```

## 本地运行

在项目根目录执行：

```bash
streamlit run 网页展示/app.py
```

## 一键启动（本机调试）

- 双击 `网页展示/启动网页.bat`：本机监听，并自动打开浏览器。
- 默认网址：`http://localhost:8501`（仅本机可访问）。

## 内网发布操作教程（本机当服务器，约 5 分钟）

以下做法等价于「在你这台电脑上开一个小网站」，**同一局域网/VPN 内的同事**用浏览器输入你的内网 IP + 端口即可访问。我无法替你配置公司 DNS，但按下面做完即可内网访问。

### 步骤 1：安装依赖（仅首次）

在项目根目录（与 `网页展示` 文件夹同级）打开终端，执行：

```bash
pip install -r 网页展示/requirements.txt
```

### 步骤 2：放行 Windows 防火墙端口

默认使用 **8501**（若被占用可改脚本里的端口，见步骤 4）。

1. 打开「Windows 安全中心」→「防火墙和网络保护」→「高级设置」。
2. 「入站规则」→「新建规则」→「端口」→ TCP → 特定本地端口填 `8501`（或你实际使用的端口）→ 允许连接 → 勾选当前网络类型 → 名称可写 `Streamlit 指数盈利分解`。

（管理员 PowerShell 示例，端口请与启动命令一致：）

```powershell
New-NetFirewallRule -DisplayName "Streamlit-8501" -Direction Inbound -Protocol TCP -LocalPort 8501 -Action Allow
```

### 步骤 3：启动「内网模式」服务

双击 **`网页展示/启动服务_内网.bat`**。

窗口会保持打开，**不要关**；关掉即停止服务。若需改端口：用记事本打开该 bat，把两处 `8501` 改成例如 `8502` 后保存。

或在项目根目录手动执行：

```bash
streamlit run 网页展示/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

### 步骤 4：确认本机内网 IPv4

在 PowerShell 或 CMD 执行：

```text
ipconfig
```

在输出里找 **「以太网」或「WLAN」适配器**下的 **IPv4 地址**（常见形如 `10.x.x.x`、`192.168.x.x`）。**不要**把仅本机虚拟网卡（如部分 `198.18.x.x`、`192.168.x.1` 的虚拟交换机）当成同事要连的地址；优先选你接公司网/办公 Wi‑Fi 的那块网卡。

### 步骤 5：把链接发给同事

把「步骤 4」得到的 IP 和「步骤 3」的端口拼成链接，例如：

```text
http://10.5.1.159:8501
```

同事在同一内网（或已拨公司 VPN）的 Chrome / Edge 中打开即可。

### 步骤 6：本机自测

- 本机浏览器：`http://localhost:8501`（端口与启动一致）。
- 模拟「同事访问」：`http://<你的IPv4>:8501`。

### 步骤 7：固定「域名」（可选）

若公司内网有 DNS：请网管增加 **A 记录**，例如 `zhishu-decomp.corp` → 你的机器 IPv4，则同事可访问 `http://zhishu-decomp.corp:8501`（若前面有 Nginx 监听 80，可省略端口，见下文「Nginx」一节）。

### 步骤 8：长期开机自动跑（可选）

- **Windows**：「任务计划程序」新建任务，触发器「工作站解锁时/启动时」，操作启动程序填 `streamlit`，参数填 `run 网页展示\app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true`，起始于填项目根目录；或使用 [NSSM](https://nssm.cc/) 注册为 Windows 服务。
- **Linux**：使用 `systemd` 服务，`WorkingDirectory` 为项目根，`ExecStart` 同上（路径改为 `网页展示/app.py`）。

### 常见问题

| 现象 | 处理 |
|------|------|
| 提示 `Port 8501 is already in use` | 关掉已占用 8501 的程序，或把 bat/命令里的端口改为 `8502` 等，防火墙规则同步放行新端口。 |
| 本机能开、同事打不开 | 检查防火墙、是否同一网段/VPN、IP 是否选错网卡。 |
| Wind 数据拉失败 | 部署机须能访问 `HHWindPy.py` 里的 `SERVER_URL`；仅影响部分扩展功能，本地图表仍可能可用。 |

## 内网固定域名 / 固定链接访问

应用为 **Streamlit**，需在一台内网可达机器上常驻运行，再通过 **内网 DNS** 或 **固定 IP + 端口** 访问。

### 1. 部署目录

将 **项目根目录**（包含 `网页展示/` 以及根目录下五个 parquet：`指数代码与名称`、`指数价格数据`、`指数PE数据`、`指数PB数据`、`指数PB数据_海外`）拷贝到服务器，相对路径与本地一致。`app.py` 通过父目录加载上述文件。

### 2. 监听所有网卡（内网其他电脑可访问）

在项目根目录执行：

```bash
streamlit run 网页展示/app.py --server.address 0.0.0.0 --server.port 8501 --server.headless true
```

- `--server.address 0.0.0.0`：允许内网其他主机访问（若仅 `127.0.0.1` 则只能本机打开）。
- `--server.port`：可改为公司分配的端口（如 `8851`），与防火墙放行一致。

Windows 下也可双击 **`网页展示/启动服务_内网.bat`**（在项目根起服务，不自动弹浏览器）。

Linux / macOS 可使用 **`网页展示/start_intranet.sh`**（需先 `chmod +x`）。

### 3. 固定「域名」或链接

| 方式 | 用户访问示例 |
|------|----------------|
| 固定 IP + 端口 | `http://10.x.x.x:8501` |
| 内网 DNS A 记录 | 网管配置 `index-decomp.internal` → 部署机 IP，访问 `http://index-decomp.internal:8501` |

### 4. 可选：Nginx 反代（省略端口、统一 80/443）

将 Nginx `proxy_pass` 到 `http://127.0.0.1:8501`。Streamlit 依赖 **WebSocket**，需至少包含：

- `proxy_http_version 1.1`
- `proxy_set_header Upgrade $http_upgrade`
- `proxy_set_header Connection "upgrade"`

配置片段可参考官方文档：[Streamlit Community Cloud / self-hosted proxy](https://docs.streamlit.io/deploy/tutorials/docker) 中的反向代理说明，或检索 “streamlit nginx reverse proxy websocket”。

### 5. 常驻运行

- **Linux**：使用 `systemd` 服务，`Restart=always`，`WorkingDirectory` 为项目根，`ExecStart` 为上面的 `streamlit run ...`。
- **Windows**：任务计划程序（开机/登录时运行）或 [NSSM](https://nssm.cc/) 将上述命令注册为服务。

### 6. 防火墙与安全

- 仅对办公网段/VLAN 放行 Streamlit 端口（或仅放行 Nginx 的 80/443），避免对公网全网段暴露。
- `网页展示/HHWindPy.py` 中的 Wind 代理 `SERVER_URL` 须从部署机网络可达。

### 7. 验证

- 从另一台内网电脑浏览器打开 `http://<内网域名或IP>:<端口>`，能加载页面、查询标的、交互图与数据维护功能正常。
- 重启部署机后进程应能自动拉起（若已配置 systemd / 任务计划）。

## 数据与环境要求

- 需存在以下文件（项目根目录）：`指数代码与名称.parquet`、`指数价格数据.parquet`、`指数PE数据.parquet`、`指数PB数据.parquet`、`指数PB数据_海外.parquet`。
- 需能导入 `HHWindPy`（根目录或 `网页展示/` 下的 `HHWindPy.py`），用于扩展指标与数据维护中的 Wind 拉数；失败时页面会提示并尽量继续展示本地数据。

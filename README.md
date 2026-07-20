<p align="center">
  <img src="docs/images/logo-suat-color.png" alt="Agent Hub / SUAT" width="420" />
</p>

<h1 align="center">Agent Hub</h1>

<p align="center">
  <strong>校园多 Agent 工作流控制台</strong><br/>
  统一调度 Hermes / OpenClaw / NanoBot / Direct LLM · Soul · Skills · MCP · 并行子代理
</p>

<p align="center">
  <a href="https://github.com/xielab2017/Agent-Hub/releases"><img alt="version" src="https://img.shields.io/badge/version-5.0.7-rose.svg" /></a>
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-blue.svg" /></a>
  <a href="https://www.python.org/"><img alt="python" src="https://img.shields.io/badge/python-%3E%3D3.9-brightgreen.svg" /></a>
  <a href="https://github.com/xielab2017/Agent-Hub"><img alt="platform" src="https://img.shields.io/badge/platform-macOS%20%7C%20Windows%20%7C%20Linux-lightgrey.svg" /></a>
</p>

<p align="center">
  <img src="docs/images/banner.jpg" alt="Agent Hub banner" width="100%" />
</p>

---

## 这是什么

**Agent Hub** 是一个本地 Web 控制台：浏览器只做 UI，真正的网关跑在本机进程里。  
它连接各 Claw 的**原生 home**（`~/.hermes` · `~/.openclaw` · `~/.nanobot`），而不是再造一份平行 Agent。

| 能力 | 说明 |
|------|------|
| **Agent / 快聊** | Agent 模式走 Hermes 工具链；Direct 适合问候与快速对话 |
| **分层路由 C0–C3** | 简单 / 办公 / 长文生成+审核 / 推理 / Vision，可绑定不同模型 |
| **并行子代理** | 自然语言或自动规划多车道，看板并行 + 合成 |
| **Soul / Skills / MCP** | 多身份、技能库、MCP Hub |
| **控制中心** | 模型、路由、生态、外观 Logo、定时任务、自我进化等 |
| **跨设备** | 默认监听 `0.0.0.0:8765`，同局域网可用 IP 访问 |

<p align="center">
  <img src="docs/images/screenshot-chat.jpg" alt="主界面：任务与会话" width="92%" />
  <br/><em>主界面 · v3.0.0</em>
</p>

<p align="center">
  <img src="docs/images/screenshot-control-center.jpg" alt="控制中心：外观与 Logo" width="92%" />
  <br/><em>控制中心 · 外观 / 内置品牌 Logo</em>
</p>

---

## 快速开始

### 要求

- Python **3.9+**
- 可选：已安装的 [Hermes Agent](https://github.com/NousResearch/hermes-agent) / OpenClaw 等（控制中心可检测）

### macOS（推荐：后台守护）

1. 克隆并进入仓库：

```bash
git clone https://github.com/xielab2017/Agent-Hub.git
cd Agent-Hub
chmod +x ctl.sh "Start Agent Hub.command" start.sh
```

2. 双击 **`Start Agent Hub.command`**，或：

```bash
./ctl.sh start
./ctl.sh open
```

浏览器：<http://127.0.0.1:8765>

> 关闭浏览器 / Terminal **不会**停止网关。显式停止：`./ctl.sh stop`。

#### macOS 首次启动排查

如果第一次双击 **`Start Agent Hub.command`** 后浏览器只显示：

```json
{"error":"not found"}
```

通常不是 v5 程序崩溃，而是 `8765` 端口上已有旧版/残留后台进程，启动脚本检测到端口可用后打开了旧服务。请在当前仓库目录执行：

```bash
./ctl.sh stop
./ctl.sh start
./ctl.sh open
curl -s http://127.0.0.1:8765/api/health
```

确认健康检查里显示 `"version": "5.0.7"`。如果仍然不对，可临时换端口验证当前源码：

```bash
python3 server.py --host 127.0.0.1 --port 9876 --open
```

再访问 <http://127.0.0.1:9876/>。若新端口正常，说明原来的 `8765` 被旧进程占用，重启电脑或执行 `./ctl.sh stop` 后再启动即可。

从 GitHub 下载 ZIP 后，macOS 也可能丢失执行权限；可重新赋权：

```bash
chmod +x ctl.sh "Start Agent Hub.command" start.sh
```

可选（开机自启 + 崩溃自动拉起）：

```bash
./ctl.sh install-service
./ctl.sh status   # logs | stop | restart | uninstall-service
```

> **提示（macOS）**：若仓库放在 `Documents` / `Desktop` / `Downloads`，系统 TCC 可能限制 launchd 直读 `server.py`。更稳的做法是把仓库放到例如 `~/Projects/Agent-Hub` 后再 `./ctl.sh install-service`。这不影响代码本身与其他平台。

### Windows

```bat
git clone https://github.com/xielab2017/Agent-Hub.git
cd Agent-Hub
start-agent-hub.bat
```

或 PowerShell：`.\start.ps1`

仓库的 `Windows smoke test` 工作流会在真实 `windows-latest` 环境持续验证安装、双击启动、健康检查、保留本地修改的更新，以及一般用户/管理员两种推送流程。

### Linux / 通用命令行

```bash
./ctl.sh start
# 前台调试：
python3 server.py --host 0.0.0.0 --port 8765
```

### 双击同步 GitHub 最新版本

通过 `git clone` 安装的仓库可以使用根目录中的更新器。更新器会临时保存未提交的本地修改，使用 fast-forward 模式同步当前分支，再恢复本地修改；不会执行 `reset --hard`。

- **macOS**：双击 **`Update Agent Hub.command`**
- **Windows**：双击 **`update-agent-hub.bat`**
- **macOS / Linux 命令行**：运行 `./update.sh`

同步完成后需要重启 Agent Hub 才会加载新代码：

```bash
# macOS / Linux
./ctl.sh restart
```

如果本地修改与 GitHub 新版本冲突，更新器会保留 `git stash` 并提示手动解决，不会删除本地文件。直接从 GitHub 下载的 ZIP 不包含 Git 历史，无法使用该更新器；首次使用建议通过 `git clone` 安装。

### 双击发布修改到 GitHub

仓库根目录还提供跨平台发布器：

- **macOS**：双击 **`Push Agent Hub.command`**
- **Windows**：双击 **`push-agent-hub.bat`**

发布器会先同步 `main`、保护未提交修改，并自动把版本号第三位加一，例如 `5.0.0` 更新为 `5.0.1`。选择“一般用户”时不需要本地管理员密码，会创建 `contrib/<用户>/v<版本>-<时间>` 分支并推送；选择“管理员”时会验证本机密码配置并直接推送 `main`。

管理员密码不会写入 Git 仓库。可将密码的 SHA-256 保存到以下本机文件，或设置 `AGENT_HUB_ADMIN_PASSWORD_SHA256`：

- macOS/Linux：`~/.hermes/ali/publish-admin.sha256`
- Windows：`%LOCALAPPDATA%\hermes-ali\publish-admin.sha256`

本地角色选择只是操作防误触，真正权限仍由 GitHub 仓库写入权限、认证和 `main` 分支保护控制。一般用户必须拥有该仓库分支的写入权限；没有写入权限时，应先使用个人 fork。

可选环境变量：

| 变量 | 含义 |
|------|------|
| `HERMES_ALI_HOST` | 绑定地址（默认 `0.0.0.0`） |
| `HERMES_ALI_PORT` | 端口（默认 `8765`） |
| `HERMES_ALI_PASSWORD` | 可选访问密码 |
| `HERMES_ALI_PUBLIC_URL` | HTTPS 隧道或反向代理提供的外网地址 |
| `HERMES_ALI_STATE_DIR` | 覆盖 Hub 状态目录 |
| `HERMES_HOME` | Hermes 原生 home |

### 局域网与外网访问

侧栏左下角会显示本机地址和可识别的局域网地址。局域网中的其他设备可通过 `http://<局域网IP>:8765` 访问；若无法连接，请检查系统防火墙是否允许 Python/Agent Hub 接收入站连接。

Agent Hub 会通过 ipify 尝试检测公网 IP，并在侧栏显示黄色的“外网 IP”候选地址。检测到公网 IP 不代表该地址已经可以访问：设备通常位于 NAT、校园网或防火墙之后，还需要端口映射或可信隧道。推荐使用提供 HTTPS 的隧道或反向代理，并同时设置访问密码与正式对外 URL：

```bash
export HERMES_ALI_PASSWORD='请换成高强度密码'
export HERMES_ALI_PUBLIC_URL='https://agent.example.edu'
./start.sh
```

配置后，正式“外网”地址会替代自动探测的 IP。只有 URL 使用 HTTPS 且启用了 `HERMES_ALI_PASSWORD` 时，界面才会将公网状态标记为就绪。不要把无密码的 `8765` 端口直接映射到公网；正式多人使用时还应在反向代理或零信任网关中配置账号、访问策略和日志审计。

---

## 数据与配置目录

| 路径 | 用途 |
|------|------|
| macOS/Linux：`~/.hermes/ali/` | Hub 状态、会话、日志、自定义 Logo |
| Windows：`%LOCALAPPDATA%\hermes-ali\` | 同上 |
| `~/.hermes/` · `~/.openclaw/` · … | 各 Claw **原生**配置（不受 Hub 克隆路径影响） |
| 密钥 | 存于 Hub 状态目录 `secrets.json`（权限收紧），**勿提交 Git** |

示例校园配置模板：[`assets/campus-office-ai.example.json`](assets/campus-office-ai.example.json)

---

## 功能速览

### Soul（多身份）

控制中心 → **Soul**：内置 / 自建角色；同步到 claw home 并注入系统提示。主界面底部可按任务切换。

### Skills

按分类选择；「自动匹配」可按任务推断。管理与安装见控制中心 **Skills**。

### 路由与模型

- **工作流 Auto**：按任务复杂度选 C0/C1/C2/C3
- **指定模型**：固定单一模型
- 多提供商目录（DeepSeek、OpenAI 兼容、NVIDIA NIM、OpenRouter 等）

### 并行子代理

自然语言如「分成三个子代理」，或 Agents 里多选 Slot；看板分车道运行，完成后合成。

### 外观

中英、浅/深色、主题色；Logo 可上传或选内置品牌（SUAT 彩标 / 白板）。

### EasyMultiProfiler 联合分析

v5.0.7 提供实验性的本机 16S 纵向流程：扫描本地数据目录、识别 assay/metadata、核对样本、确认结构化计划、调用 EMP 完成 taxonomy 与 Alpha 多样性分析，并把 JSON、PNG、PDF 和 Markdown 报告登记为会话产物。

先在 EasyMultiProfiler-Web 仓库启动 API；路径导入只允许 `EMP_ALLOWED_ROOTS` 中的目录：

```bash
cd /path/to/EasyMultiProfiler-Web
EMP_ALLOWED_ROOTS=/absolute/path/to/your/project \
Rscript webapp/backend/run_api.R
```

Windows PowerShell：

```powershell
$env:EMP_ALLOWED_ROOTS = "C:\Research\Project"
Rscript webapp\backend\run_api.R
```

然后打开 Agent Hub 的“控制中心 → 联合分析”，启用 EMP，保留默认地址 `http://127.0.0.1:8000`，保存并检查连接。首次版本只支持 `local-api` 和固定 16S 流程；远程上传、RNA-seq/多工作流规划及 R Direct 尚未启用。

常见问题：

- 显示“等待本机 EMP”：确认 EMP API 已启动，端口与控制中心一致。
- 显示“路径不允许”：把数据项目根目录加入 EMP 的 `EMP_ALLOWED_ROOTS`，重新启动 EMP。
- Agent Hub 重启：已完成 job、mapping 和 artifact 会恢复；中断中的本机编排会标记为可重试错误，避免静默重复提交。
- 回滚：在控制中心关闭 EMP，或设置配置项 `emp.enabled=false`；聊天、模型与其他功能不受影响。

开发环境可运行双服务 smoke：

```bash
python3 scripts/emp_e2e_smoke.py \
  --hub http://127.0.0.1:8765 \
  --workspace /path/to/EasyMultiProfiler-Web/tests
```

---

## 仓库结构

```
Agent-Hub/
├── server.py              # HTTP 网关入口
├── bootstrap.py           # 引导 / 依赖检查
├── ctl.sh                 # start/stop/status/install-service
├── Start Agent Hub.command  # macOS 一键后台启动
├── start-agent-hub.bat    # Windows 一键后台启动
├── start.sh / start.ps1
├── ali/                   # 业务逻辑（路由、流式、Agent、Soul…）
├── static/                # Web UI（HTML/CSS/JS）+ brand 资源
├── assets/                # 示例配置
├── docs/images/           # README 配图
└── pyproject.toml
```

---

## 开发与版本

当前版本：**v5.0.7**（分支 `v5.0.7`）

```bash
# 健康检查
curl -s http://127.0.0.1:8765/api/health

# 更新 main 分支
git fetch origin
git checkout main
git pull
```

简要更新：

- **v5.0.7** — EMP 16S 端到端加固：六段进度面、元数据分组变量、文件浏览器与状态修复；集成 Trellis 受控任务模式
- **v5.0.6** — Agent Hub x EasyMultiProfiler 本机 16S MVP：受控数据扫描、计划确认、持久 job/artifact、稳定进度和中英文 UI
- **v5.0.0** — 强化 Agent Hub 本地网关、启动器与跨平台使用体验；新增 macOS 首次启动排查说明
- **v4.0.0** — 发布 Agent Hub v4 系列能力与文档刷新
- **v3.0.0** — 并行子代理自动规划、共享 `HERMES_HOME`、C0–C3 路由；深度会话 iframe 已退役（能力内化到 Hub）
- **v2.0.0** — 统一模型目录、路由与 Agent/Subagent 选模；自适应可调布局；代理 TLS 配置持久化
- **v1.4.59** — 内置 Logo 预设：SUAT 彩标 + 白板；Hub 守护安装加固  
- **v1.4.58** — 子代理对接 C0–C3 + Soul；并行自动选档位  
- **v1.4.57** — 并行任务切换与进度条修复  
- **v1.4.56** — Appearance 可更换左侧/新对话 Logo  

更早版本见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## GitHub 上的使用方式

本仓库路径无关、跨平台：

```bash
git clone https://github.com/xielab2017/Agent-Hub.git
cd Agent-Hub
./ctl.sh start   # 或对应平台脚本
```

- **上传 / 协作**：照常 `git push` 到本仓库；**不要**提交 `.env`、真实 API Key、本机绝对路径。  
- **旧名 Hermes-ALI**：历史代码曾用该名；当前产品与主仓为 **Agent Hub**（本仓库）。  
- **Release**：打 tag `v*` 可触发 [Release workflow](.github/workflows/release.yml) 打包源码归档。

---

## 许可

[MIT](LICENSE) © Xie Lab / [xielab2017](https://github.com/xielab2017)

---

<p align="center">
  <sub>深圳理工大学 · Campus Agent Hub</sub>
</p>

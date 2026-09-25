<p align="center">
  <img src="docs/images/logo-suat-color.png" alt="Agent Hub / SUAT" width="420" />
</p>

<h1 align="center">Agent Hub</h1>

<p align="center">
  <strong>校园多 Agent 工作流控制台</strong><br/>
  统一调度 Hermes / OpenClaw / NanoBot / Direct LLM · Soul · Skills · MCP · 并行子代理
</p>

<p align="center">
  <a href="https://github.com/xielab2017/Agent-Hub/releases"><img alt="version" src="https://img.shields.io/badge/version-5.3.4-rose.svg" /></a>
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
| **可审计溯源** | 对标 Claude Science：每条回复都有可校验的溯源记录，可导出报告与复现包 |
| **审查代理** | 自动核查引用编号、链接、DOI/PMID 与无出处的数字，可联网核验 |
| **科学数据库** | UniProt · PDB · Ensembl · ChEMBL · ClinicalTrials · GEO · ClinVar · Reactome · Europe PMC · Crossref |
| **流程存为技能** | 一键把会话保存为 SKILL.md，后续相似请求自动套用 |
| **任务 · 自动下一步** | 在对话框输入任务（`/task` 或列出步骤），逐步执行、审查通过自动进入下一步 |
| **多引擎 + 读原文** | Bing / 360 / 百度 / 搜狗 / DuckDuckGo / SearXNG / Brave / Tavily / Google；深度搜索打开原文 |
| **数据核对与总结** | 来源分级、跨来源数值一致性与冲突检测；结构化总结与「来源与证据」面板 |
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

确认健康检查里显示 `"version": "5.3.4"`。如果仍然不对，可临时换端口验证当前源码：

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

### Linux / 通用命令行

```bash
./ctl.sh start
# 前台调试：
python3 server.py --host 0.0.0.0 --port 8765
```

可选环境变量：

| 变量 | 含义 |
|------|------|
| `HERMES_ALI_HOST` | 绑定地址（默认 `0.0.0.0`） |
| `HERMES_ALI_PORT` | 端口（默认 `8765`） |
| `HERMES_ALI_PASSWORD` | 可选访问密码 |
| `HERMES_ALI_STATE_DIR` | 覆盖 Hub 状态目录 |
| `HERMES_HOME` | Hermes 原生 home |

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

### 可审计溯源（对标 Claude Science）

每条助手回复都会自动生成一份**溯源记录**：模型 / 路由 / 引擎、Soul 与子代理、技能、工作区上下文、系统提示词哈希、联网来源（编号、域名、检索引擎）、工具调用、输出哈希、耗时，以及运行环境（版本、Python、平台、Git commit）。记录带 SHA-256 完整性校验，任何改动都会显示「哈希不一致」。**不记录任何 API Key**。

- 回复下方点 **溯源**：查看“生成方式”说明与明细，下载 JSON 或 Markdown 报告
- 会话列表点 **🧾**：导出**复现包**（zip：会话、全部溯源记录、运行日志、`REPORT.md`、带文件哈希的 `MANIFEST.json`）
- 存储位置：Hub 状态目录下 `provenance/<会话>/<消息>.json`

| API | 说明 |
|-----|------|
| `GET /api/provenance/<session>/<message>` | 完整记录 + `verified` |
| `GET /api/provenance/<session>/<message>/report` | Markdown 报告 |
| `GET /api/sessions/<id>/provenance` | 会话内记录列表 |
| `GET /api/sessions/<id>/reproducibility-bundle` | 复现包 zip |

### 审查代理（对标 Claude Science）

每条回复完成后自动审查（离线、毫秒级、只提示不改写正文），结果显示在回复下方并写入溯源记录：

- **引用**：`[n]` 编号超出检索来源数量、或无来源却引用
- **链接**：回复里的 URL 不在检索来源或你提供的材料中
- **标识符**：DOI / PMID 格式错误；点 **联网核验引用** 可经 Crossref / NCBI 实际解析
- **数字**：百分比、p 值、HR/OR/IC50 等统计量、n=、带单位的数量——在来源、你的问题、工作区摘录和工具输出中都找不到出处时标记为「数字无出处」

联网检索的来源在提示词中按 `[1]…[n]` 编号（与溯源记录一致），模型被要求按编号引用。

### 科学数据库连接器

问题中出现基因符号（TP53、PD-L1）、UniProt / PDB / Ensembl / ChEMBL / NCT / rsID / GEO 编号、DOI，或“蛋白结构、化合物、临床试验、变异、通路”等主题时，自动并行查询对应的公开数据库，结果作为编号来源进入回复与溯源记录。

- 控制中心 → **科学数据库**：逐库开关、测试检索；`data_policy=restricted` 时全部禁用
- 所有库均为公开只读、免密钥；每次查询写入审计日志
- 若校园网 / 代理拦截了这些域名，检索会快速失败并给出原因，不影响其他来源

### 流程存为技能

回复下方点 **存为技能**：根据会话与溯源记录生成 SKILL.md 草稿（适用场景、输入、步骤、输出格式、质量检查、溯源哈希），可编辑后保存。保存后自动加载到 Hub；以后遇到相似请求（按 `triggers:` 匹配）会自动套用这些步骤。同名技能不会被覆盖。

| API | 说明 |
|-----|------|
| `POST /api/review/<session>/<message>` | 重新审查；`{"online": true}` 联网核验 DOI/PMID |
| `GET /api/science/connectors` · `POST` 同路径 | 连接器列表 / 开关 |
| `GET /api/science/search?q=` | 科学数据库检索 |
| `POST /api/skills/from-session` | 生成技能草稿 |
| `POST /api/skills/from-session/save` | 保存并加载技能 |

### 在对话框输入任务 · 自动进入下一步

在输入框里直接写任务即可：

- `/task 调研 TP53 突变：1. 检索最新文献 2. 核对突变频率 3. 写总结` —— 按列出的步骤执行
- 消息里本身有 `1. … 2. …`、`第一步…第二步…`、`首先…然后…最后…` 时，会询问是否「按任务执行」
- 没有列步骤时，研究/检索类任务自动套用「检索资料 → 核对数据 → 整理总结 → 下一步建议」

每一步都走完整流程（检索、证据核对、审查、溯源）。输入框上方的**任务栏**显示进度：

- **自动推进**（默认）：本步审查无警告就自动进入下一步；有警告时暂停并显示原因，可「仍然继续」或「停止」
- **逐步确认**：每步完成后等你点「继续下一步」
- 运行中在输入框补充的「中途指引」会带入下一步

| 命令 | 作用 |
|------|------|
| `/task <描述>` | 按步骤执行任务，自动进入下一步 |
| `/search <问题>` · `/deep <问题>` | 联网检索 / 深度检索（多引擎 + 打开原文 + 交叉核对） |
| `/summary` | 把上一条回复整理成结构化总结 |
| `/verify` | 联网核验上一条回复的 DOI / PMID |
| `/next` · `/stop` | 继续下一步 / 停止当前任务 |

### Hermes 融合（已用 Hermes Agent v0.19.0 实测）

控制中心「Claws」连接 Hermes 后，对话走 Hermes 的工具链：

- **进程内**（Hub 所在 Python 能 `import run_agent`）：Hub 上下文作为 `ephemeral_system_prompt` 传入，用户消息保持干净；多轮历史作为 `conversation_history` 传入
- **CLI 回退**（找到 `hermes` 命令）：`hermes chat -q … -Q`，自动附带最近几轮对话；清除 CLI 提示行，记录 Hermes 会话 ID
- 工具调用（如 `read_file`、`terminal`）实时显示在「处理过程」，并连同耗时、成功与否写入溯源记录
- Soul、模型/密钥、MCP 服务器、技能同步到 `~/.hermes`：保留你在 `config.yaml` 里自己配置的 MCP；Hub 新装或「存为技能」的技能立即出现在 Hermes 里

### 外部搜索引擎与读原文

控制中心 → **搜索**：可选引擎优先级，并逐个开关——Bing RSS、360、百度、搜狗、DuckDuckGo、SearXNG（填自建实例地址）、Brave Search / Tavily（填 API Key）、Google CSE / SerpAPI。深度搜索会并行打开前几个结果页面（默认 3 个），提取与问题最相关的段落；只访问公网地址，不会访问本机或内网。

### 数据准确性与总结梳理

- 每个来源自动分级：官方 / 数据库 / 学术 / 预印本 / 新闻 / 社区自媒体，并识别日期
- 从来源中提取数值，统计**多少个独立域名一致**，发现**来源之间的数值分歧**
- 审查代理额外标记：来源间有分歧的数字（警告）、只有单一来源的数字、来源全部是论坛/自媒体
- 检索类回复按「结论摘要 / 关键数据表（指标 | 数值 | 来源 | 一致性）/ 分歧与不确定 / 下一步」组织；回复下方有「来源与证据」面板和可点击的「下一步」建议
- 表单 / Excel 联网填写优先采用多个来源一致的值，并给出 high / medium / low 置信度

| API | 说明 |
|-----|------|
| `POST /api/tasks` · `POST /api/tasks/preview` | 创建任务（返回第一步）/ 预览拆分的步骤 |
| `GET /api/tasks/<id>` · `GET /api/sessions/<id>/task` | 任务状态 / 会话当前任务 |
| `POST /api/tasks/<id>/advance` · `stop` · `mode` | 推进（`force` 跳过闸门）/ 停止 / 切换 auto·confirm |

### 外观

中英、浅/深色、主题色；Logo 可上传或选内置品牌（SUAT 彩标 / 白板）。

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
├── tests/                 # pytest（CI：.github/workflows/tests.yml）
├── assets/                # 示例配置
├── docs/images/           # README 配图
└── pyproject.toml
```

---

## 开发与版本

当前版本：**v5.3.4**（分支 `main`）

```bash
# 健康检查
curl -s http://127.0.0.1:8765/api/health

# 更新 main 分支
git fetch origin
git checkout main
git pull
```

简要更新：

- **v5.3.4** — MiniMax 实测脚本 `scripts/minimax_live_check.py`（一条命令测区域、对话、检索、记忆、多步任务与报错）；无模型列表时用一次对话判断区域；识别 MiniMax `base_resp` 错误
- **v5.3.3** — 搜索、问题处理、科学任务与连续性实测修复：检索词清洗、中文科研问题走文献库、同一论文去重、来源按可信度编号、浓度单位与数量级冲突核对；模型 429/5xx 自动重试、断流标记、停止生成真正生效；任务内统一来源编号、重启后任务可继续、被中断的提问有提示
- **v5.3.2** — MiniMax 更新：国际区 / 中国大陆区两个厂商、M2 系列模型、`sk-cp-` Coding Plan Key 识别、Hermes `minimax-cn` 映射、拉取模型失败时自动探测 Key 所属区域
- **v5.3.1** — Hermes 融合实测（Hermes Agent v0.19.0）：工具调用可见、系统上下文独立、MCP / 技能 / 模型同步修复、CLI 输出清理与多轮上下文
- **v5.3.0** — 对话框任务与自动下一步、多引擎搜索与读原文、来源分级与跨来源核对、结构化总结
- **v5.2.0** — 审查代理、科学数据库连接器、流程存为技能；CI 自动测试
- **v5.1.0** — 对标 Claude Science 的可审计溯源：每条回复的溯源记录、完整性校验、报告与复现包导出
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

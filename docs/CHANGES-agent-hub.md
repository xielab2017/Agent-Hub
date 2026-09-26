# Agent Hub 本分支改动记录（claude/eager-babbage-869kk8）

基线：`main`（ea71040）。代码改动 65+ 个文件，约 +1.5 万行；全部改动均有测试（`tests/`，260 项左右）。
下面按功能归类；每项注明主要文件，方便审阅。

## 1. 答案可审计与准确性（v5.1–v5.2）
- **每条回复可溯源**：来源、检索、路由、模型、审查结论写入密封记录，可导出复现包 — `ali/provenance.py`。
- **自动审稿器**：检查无出处数字、编造文献、DOI 格式、相互矛盾、设计参数误判 — `ali/reviewer.py`。
- **科学数据库连接器**：PubMed、Europe PMC 等 — `ali/science_connectors.py`。
- **对话存为 Skill** — `ali/skill_capture.py`。

## 2. 检索与多步任务（v5.3.0–v5.3.3）
- 多搜索引擎 + 网页正文读取 + 证据/来源分级 — `ali/search_engines.py`、`ali/page_fetch.py`、`ali/evidence.py`、`ali/source_quality.py`。
- 多步任务自动进入下一步、任务看板、斜杠命令 `/task /search /deep /summary /verify /next /stop` — `ali/task_runner.py`、`static/app.js`。
- 离线端到端测试发现并修复的检索、报错、科学任务、连续性问题。

## 3. MiniMax 与真实云端测试（v5.3.4–v5.3.6）
- MiniMax 国内 / 海外区域自动识别，Anthropic 兼容端点（`…/anthropic`）— `ali/providers.py`、`ali/anthropic_client.py`。
- 默认模型 MiniMax-M3；GitHub Actions 真实 API 测试 `minimax-live.yml`（key 只来自仓库 secret）。
- 真实运行暴露的问题：工具调用标记当答案、DOI 页面读不到、PubMed 按时间排序、中文问题查不到英文库、无关论文当来源、审稿器误判 — 均已修复。

## 4. 综述写作流水线 → 可运行 Skill
- `ali/review_writer.py`：PubMed 检索 → 摘要筛选 → 证据卡 → 提纲 → 分章起草 → 三位审稿子代理 → 审稿缺口补检 → 修改 → 逐章引用审计 → [n] 编号 → Word；检查点续跑、smoke 模式、模型调用跟踪。
- 主题无关：profile 描述主题、检索式、焦点词、筛选标准、提纲、审稿人、比较表列、特色工作与利益冲突声明；缺省字段由模型规划。
- `skills/literature-review/`（SKILL.md、`run.py`、profiles `thbs4`、`multiomics-emp`）；`ali/skill_runner.py`：运行、导出 zip、由 Hub 模型撰写 SKILL.md（参数自检）。
- 聊天命令 `/skill`、`/skill-author`、`/skill-export`；截屏演示 `scripts/skill_demo.py`、工作流 `review-pipeline.yml`、`skill-demo.yml`。
- 产出：THBS4 综述（59 篇引用）、多组学软件综述（64 篇引用，EasyMultiProfiler 专章）。

## 5. 多厂商模型 API（v5.4.0）
- 控制中心「多模型 API」：多家厂商同时接入，各自 key（加密存储、界面只显示掩码）、地址、TLS；保存不会切换当前后端；每家可测试并获取模型列表。
- 按任务等级路由：简单问答 / 办公写作 / 推理 / 视觉分别绑定厂商与模型；路由测试显示每级实际的厂商、模型、地址。
- 路由、子代理、中文→英文检索词、Claw 同步、综述 Skill 的模型客户端都使用各厂商自己的地址和 key。
- 文件：`ali/connections.py`、`ali/providers.py`（connection / hub_model）、`ali/routing.py`、`ali/settings.py`、`static/app.js`。

## 6. Claude Code 与 Codex agent（v5.4.0）
- Claws 新增 `claude-code`、`codex`：对话经官方 CLI 运行，实时流式输出文本和工具调用，同一会话自动续接；工作目录为 Hub 工作区；默认只读，可改为「可写工作区」；Hub 从不使用跳过权限的模式。
- **外部链接登录**：Claude Code 走 `claude setup-token`（界面显示授权链接，可粘贴回代码，长期 token 由 Hub 保存且不显示）；Codex 走浏览器链接或设备码；两者也可填 API key。
- CLI 参数漂移检查：CLI 版本缺少所需参数时给出明确提示；`agents-check.yml` 在 GitHub 上安装真实 CLI 核对参数并截屏演示。
- 文件：`ali/agent_cli.py`、`ali/runtimes.py`、`ali/streaming.py`、`ali/routes.py`、`static/app.js`、`tests/fakes/`。

## 安全
- 所有 key / token 只存 `secrets.json`（0600），界面、日志、截图中遮挡；每次提交前做泄漏检查。

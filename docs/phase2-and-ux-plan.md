# Agent Hub 二期与体验加固 — 实施计划

> 对照仓库现状整理。范围：Queue/Steer/Stop、RunJournal、每日推荐、主 Agent 配置、子代理子窗口、流式同步、搜索增强。  
> 「下载脚本」已在 `static/app.js` 落地，本计划不再展开。

---

## 0. 目标与原则

### 产品目标

1. **主对话轻量**：主窗口负责规划、收集、分析、合成；子代理在独立窗口跑实时产出。
2. **运行可控**：忙碌时可 Queue / Steer / Stop；断线可凭 RunJournal 续读。
3. **推荐可信**：每日推荐尽量走 GitHub；失败时状态诚实、回退可用。
4. **配置可读**：自动并行与窗口策略一眼能懂、保存后生效。
5. **流式即时**：token / progress 近实时出现，无需刷新。
6. **搜索够用**：赛事/新闻类（如「世界杯最新战局」）能检索 + 带出处总结。

### 原则

- 不嵌回 Hermes WebUI iframe；Queue/Steer/Journal 做在 Hub 网关内。
- 先修「看得见」的体验（流式、推荐文案、配置、子窗口），再补齐二期后端缺口。
- 每项有验收标准与回归点。

---

## 1. 现状盘点（仓库已有）

| 主题 | 已有能力 | 主要缺口 |
|------|----------|----------|
| Queue / Steer | 前端忙碌时改发送为 Queue/Steer；`done` 可带 `queued_message` 自动续发 | API 语义、UI 提示、Stop→发队列、与多车道关系需产品化与验收 |
| RunJournal | `ali/run_journal.py`；SSE `from_seq`；streaming 写盘 | 客户端 Last-Event-ID / 重连、过期清理、控制中心「运行历史」入口 |
| 推荐 | `ali/digest.py` + `ali/skills_hub.py` 直连优先、超时回退 | 常显示「GitHub 不可用」；无 token/代理说明；UX 偏恐吓 |
| 主 Agent 配置 | 自动并行、max_lanes、布局、弹窗、主窗只合成 | 布局选项与真实行为不一致；「旧版工具条」默认易误解 |
| 子窗口 | `openLaneSubagentWindow` / `subagent-window.html` | 弹窗拦截、与主窗同步、主窗挤满时未默认走子窗 |
| 流式 | `readSSE`、`resumeSessionStream`、journal | 卡顿/需刷新；`done` 迟到；多 tab 切换丢消费 |
| 搜索 | `ali/websearch.py` + `ali/search_extensions.py`（赛事/新闻意图） | 链路未完全打通到聊天；结果弱；世界杯类验收不稳定 |

---

## 2. 工作包 A — 流式输出同步与呈现（优先）

### 2.1 问题

处理中输出不同步，有时要刷新才看到；结构（thinking / token / progress / 最终 MD）层次不清。

### 2.2 后端

- 审查 `ali/streaming.py` 中 `_put` / `iter_sse`：确保每个 `token`/`progress` 立刻入 JOB + journal，且 `done` 一定发出。
- SSE：短 keepalive（现有约 120ms 级可保留）；连接断开不杀 worker。
- `content_preview` 定期更新，供 `resumeSessionStream` 补洞。
- 避免 finalize 路径阻塞 `done`（usage/grounding 已部分规避，再扫一遍）。

### 2.3 前端

- 审查 `static/app.js` 中 `readSSE`、token 追加、`requestAnimationFrame` 批渲染：平衡流畅与卡顿。
- 切会话：后台 consumer 不停；回切用 buffer + `from_seq` 续订。
- 刷新后：`/api/sessions/{id}/job` + resume + journal。
- 呈现：thinking 可折叠；正文流式；progress 独立条；最终 `renderMd` + 代码块工具条。

### 2.4 验收

1. 发中长回复，可见逐字/分段增长，无需刷新。
2. 流式中切走再回来，内容接得上。
3. 刷新后仍能看到进行中或最终结果。
4. 异常时有 error，且终态有 `done`。

---

## 3. 工作包 B — 每日推荐（GitHub / 本地精选）

### 3.1 问题

刷新常出现：`推荐已刷新 · 本地精选（GitHub 不可用） · 4 条`。

### 3.2 根因方向

- `fetch_github_trending_skills`（`ali/skills_hub.py`）：校园代理 / TLS / 限流。
- `_fetch_github_hot`（`ali/digest.py`）：硬超时 → `curated` / `timeout`。
- 前端把 `curated` 译成「GitHub 不可用」，体验偏负面。

### 3.3 计划

1. **连通性**：保留直连优先；可配 `GITHUB_TOKEN`；设置页提示「配置 Token 提高成功率」。
2. **诊断**：API 返回 `github_status` + `github_error`（脱敏），便于区分超时 / 403 / DNS。
3. **文案**：
   - `live`：GitHub 实时
   - `cache`：今日缓存（上次成功）
   - `timeout`：GitHub 超时 · 已用精选
   - `curated`：本地精选（网络受限时）— 弱化「不可用」恐吓感
4. **质量**：精选列表保持 4–8 条可用包；刷新优先复用当日 live 缓存。
5. **可选**：设置「推荐数据源：自动 / 仅本地」。

### 3.4 验收

- 有网 + Token（或直连成功）→ `live` 且条数 > 0。
- 断网/超时 → 精选仍可用，文案准确。
- 刷新不空白、不假成功。

---

## 4. 工作包 C — 主 Agent / 自动并行配置显示

### 4.1 问题

控制中心「自动并行」区：勾选态、布局文案、与真实行为不一致；「旧版顶部工具条」易误开。

### 4.2 计划

1. **信息架构**（建议分区）
   - 规划：启用自动多车道、最大车道数
   - 呈现：主窗布局（标签 / 侧栏 / 分屏）
   - 窗口：自动弹子代理窗、主窗只收合成
   - 兼容：旧版工具条（默认关，标注不推荐）
2. **绑定**：保存 `auto_parallel`、`max_lanes`、`layout`、`subagent_popout`、`main_synthesis_only`、`show_subagent_toolbar`；读回与 UI 一致。
3. **默认**：`subagent_popout=true`，`main_synthesis_only=true`，`layout=tabs`，`show_subagent_toolbar=false`。
4. **文案**：分屏旁注「易挤占主对话；推荐子窗口」。
5. **CSS**：grid-2 下 checkbox/select 对齐，避免错位。

### 4.3 验收

- 改选项 → 保存 → 刷新仍正确。
- 并行任务行为随「弹窗 / 只合成 / 布局」变化可感知。
- 关闭旧工具条后顶部不再出现推荐关闭的条。

---

## 5. 工作包 D — 子代理子窗口 + 主窗合成

### 5.1 目标

主窗不堆满车道正文；每车道独立窗；主窗收集并深度合成。

### 5.2 已有

- `openLaneSubagentWindow` / `openSubagentPopout`（`static/app.js`）
- `static/subagent-window.html`
- 配置项 `subagent_popout`、`main_synthesis_only`

### 5.3 计划

1. **默认策略**：`need_parallel` 且开启弹窗 → 每 lane 一窗；主消息区以计划条 + 状态 + 合成结果为主。
2. **同步**：`postMessage` 推送 plan / token / done / error；子窗可只读跟某 lane。
3. **主窗**：`main_synthesis_only` 时折叠或省略 lane 全文，保留徽章与「在子窗口打开」。
4. **拦截**：弹窗被拦时 toast + 一键「允许后重开」；降级分屏/侧栏。
5. **生命周期**：合成结束可提示关闭子窗；刷新后可按 parent/lane 重建。
6. **与 Queue/Steer**：Steer 打在主会话；子窗只显示本 lane。

### 5.4 验收

- 3–5 车道：多子窗 + 主窗合成，主对话不挤爆。
- 关弹窗权限时有降级且不丢结果。
- 合成含各 lane 要点与风险/未证实处。

---

## 6. 工作包 E — 搜索增强（含世界杯战局用例）

### 6.1 目标

联网总结有出处；赛事/新闻意图走专用源。

### 6.2 已有

- `ali/search_extensions.py`：event / news / academic 路由（含世界杯关键词）
- planner / streaming 可注入 `search_context`

### 6.3 计划

1. **打通**：`web_search=true` 或「世界杯/战局/比分」→ extensions 优先于泛搜索。
2. **查询改写**：如「世界杯最新战局」→ 多查询（积分榜、今日赛果、淘汰赛）。
3. **总结约束**：条列 + URL；禁止无来源编造比分。
4. **UI**：检索中 thinking；消息底「来源 n」；失败明示引擎错误。
5. **验收用例**：`请联网检索并总结当前世界杯（或最新相关国际足球大赛）战局，列出积分/赛果要点并附来源 URL。`
   - `sources >= 1`（理想 ≥ 3）
   - 正文含可点击 http(s)
   - 无来源时不得假装精确比分

### 6.4 回归

- 学术/普通新闻意图不串到体育源。
- 关联网时不静默假检索。

---

## 7. 工作包 F — 二期 Queue / Steer / Stop / RunJournal

### 7.1 产品语义

| 能力 | 行为 |
|------|------|
| Queue | 忙时发送 → 排队；当前 `done` 后自动发下一条 |
| Steer | 忙时发送 → 注入当前 run（不新开一轮） |
| Stop | 取消当前 stream；可选「停止并发送队列头」 |
| RunJournal | 事件落盘 JSONL；`from_seq` / 重连续读 |

### 7.2 后端

- 巩固 session 级 queue 与 steer API（与前端 `submitBusyIntent` 对齐）。
- `done` 携带 `queued_message`（已有钩子）并文档化。
- Journal：append、status、保留与清理策略（如 24h / 按条数）。
- 多车道：Queue 挂主会话；Steer 默认主 run（可后续按 lane）。

### 7.3 前端

- 忙时按钮文案 Queue/Steer；模式切换清晰。
- 队列待发提示；Steer 成功反馈。
- Stop / Stop+Send 与 `stopAndSendQueued` 打通。
- 可选：控制中心「运行 journal」只读列表。

### 7.4 Clarify / Approvals（二期延伸，可后置）

- Clarify：缺参时暂停并提问。
- Approvals：高风险工具需确认。
- 建议 Phase 2.1，避免拖垮 Queue/Journal。

### 7.5 验收

1. 忙时 Queue → 结束后自动续跑。
2. Steer 改变后续产出且不双开冲突。
3. Stop 停止 SSE；Stop+Send 行为符合文案。
4. 断网重连 / 刷新可用 journal + job 恢复。

---

## 8. 实施顺序（建议）

```text
第 1 周  A 流式同步与呈现
         B 每日推荐连通性与文案
第 2 周  C 主 Agent 配置显示与默认值
         D 子窗口默认路径 + 主窗只合成
第 3 周  E 搜索打通 + 世界杯验收
         F Queue/Steer/Stop/Journal 产品化收口
缓冲     Clarify/Approvals 原型（可选）
```

依赖：D 依赖 C 的配置项；F 的续跑体验依赖 A 的 SSE 稳定；E 可与 D 并行（不同模块）。

---

## 9. 关键文件地图

| 区域 | 文件 |
|------|------|
| 流式 | `ali/streaming.py`, `ali/routes.py`（SSE）, `static/app.js`（`readSSE` / resume） |
| Journal | `ali/run_journal.py` |
| 推荐 | `ali/digest.py`, `ali/skills_hub.py`, `static/app.js`（推荐 Tab） |
| 配置 | `ali/agents.py`, `static/app.js`（`#ctab-agents`） |
| 子窗口 | `static/app.js`（popout）, `static/subagent-window.html`, `static/style.css` |
| 搜索 | `ali/websearch.py`, `ali/search_extensions.py`, `ali/subagent_planner.py`, streaming 检索注入 |
| 并行规划 | `ali/subagent_planner.py`, `sendMultiSubagentMessage` |

---

## 10. 测试矩阵（最小）

| ID | 场景 | 期望 |
|----|------|------|
| T1 | 长回复流式 | 无刷新可见增长 |
| T2 | 刷新中恢复 | resume/journal 接上 |
| T3 | 推荐刷新 | live 或诚实回退 |
| T4 | 保存 Agents 配置 | 刷新后一致 |
| T5 | 3 车道 + 弹窗 | 子窗实时，主窗合成 |
| T6 | 世界杯战局 | 有来源总结 |
| T7 | Queue | done 后自动续发 |
| T8 | Steer | 注入成功 |
| T9 | Stop | 停止且可再发 |

自动化：扩展 `scripts/qa_multi_role_rounds.py` 覆盖 T3/T6/T7 中可 API 化部分。


---

## 11. 交付物

1. 上述能力的代码变更（按周合并）。
2. 简短「如何使用」说明（设置项 + 忙碌时 Queue/Steer + 子窗口）。
3. 验收记录：T1–T9 勾选；世界杯用例附一次真实输出摘要。
4. 已知问题列表（代理环境、弹窗策略、赛事数据源时效）。

---

## 12. 建议开工顺序

**流式 → 推荐 → 配置 → 子窗口 → 搜索 → Queue/Journal 收口**

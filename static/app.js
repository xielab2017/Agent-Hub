/* Hermes-ALI Campus Office frontend — i18n + themes */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const ACCENTS = ["suat", "ocean", "forest", "amber", "rose", "slate", "teal"];
const BGS = ["auto", "white", "suat"];
const BG_LABELS = {
  zh: { auto: "自动(昼夜)", white: "纯白", suat: "深理工紫" },
  en: { auto: "Auto day/night", white: "Pure white", suat: "SUAT purple" },
};
const LEGACY_BGS = new Set(["default", "black", "blue", "navy", "slate", "forest"]);
const FONT_SIZES = [13, 14, 15, 16, 18];
const FONT_SIZE_LABELS = {
  zh: { 13: "小 13", 14: "中 14", 15: "中大 15", 16: "大 16", 18: "特大 18" },
  en: { 13: "S 13", 14: "M 14", 15: "M+ 15", 16: "L 16", 18: "XL 18" },
};
const LOGO_VER = "3.0.0";
const DEFAULT_LOGO = `/brand/suat-logo-color.png?v=${LOGO_VER}`;
const LOGO_PRESETS = [
  { id: "suat-color", src: `/brand/suat-logo-color.png?v=${LOGO_VER}`, labelKey: "appearance.logoPresetColor" },
  { id: "whiteboard", src: `/brand/whiteboard.svg?v=${LOGO_VER}`, labelKey: "appearance.logoPresetWhiteboard" },
];
const THINKING_DEPTHS = ["light", "medium", "high", "very_high"];

function normalizeThinkingDepth(value) {
  const v = String(value || "").trim().toLowerCase().replace(/-/g, "_");
  if (THINKING_DEPTHS.includes(v)) return v;
  const aliases = { l: "light", med: "medium", m: "medium", h: "high", vh: "very_high", max: "very_high", veryhigh: "very_high" };
  return aliases[v] || "medium";
}

function detectSystemLanguage() {
  const nav = String(navigator.language || navigator.userLanguage || "en").toLowerCase();
  return nav.startsWith("zh") ? "zh" : "en";
}

function controlLangZh() {
  // Always sync with sidebar / prefs language toggle
  return state.prefs.language !== "en";
}

/** Colored multi-step install progress (prepare → install → verify → done). */
function renderInstallProgressHtml(job, langZh) {
  const esc = (s) => String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  const steps = (job && job.steps) || [
    { id: "prepare", label_zh: "准备", label_en: "Prepare" },
    { id: "install", label_zh: "安装", label_en: "Install" },
    { id: "verify", label_zh: "测试验证", label_en: "Verify" },
    { id: "done", label_zh: "完成", label_en: "Done" },
  ];
  const cur = (job && job.step) || "prepare";
  const status = (job && job.status) || "running";
  const pct = Math.max(0, Math.min(100, Number((job && job.pct) || 0)));
  const order = steps.map((s) => s.id);
  const idx = Math.max(0, order.indexOf(cur));
  const color = status === "failed"
    ? "var(--ip-fail)"
    : ({ prepare: "var(--ip-prepare)", install: "var(--ip-install)", verify: "var(--ip-verify)", done: "var(--ip-done)" }[cur] || "var(--ip-install)");
  const stepLis = steps.map((s, i) => {
    let cls = "pending";
    if (status === "ok") cls = "done";
    else if (status === "failed" && s.id === cur) cls = "fail";
    else if (s.id === cur) cls = "active";
    else if (i < idx) cls = "done";
    const label = langZh ? (s.label_zh || s.id) : (s.label_en || s.id);
    return `<li class="${cls}" data-step="${esc(s.id)}">${esc(label)}</li>`;
  }).join("");
  const err = (job && job.error) ? `<div class="ip-error">${esc(job.error)}</div>` : "";
  const verify = job && job.verify
    ? `<div class="ip-verify ${job.verify.ok ? "ok" : "bad"}">${langZh
      ? (job.verify.ok ? "验证通过：安装内容可用" : "验证失败：已尝试调试")
      : (job.verify.ok ? "Verified: install works" : "Verify failed: debug attempted")}</div>`
    : "";
  return `
    <div class="install-progress" data-status="${esc(status)}">
      <div class="ip-head">
        <strong>${langZh ? "安装进度" : "Install progress"}</strong>
        <span class="ip-pct" style="color:${color}">${pct}%</span>
      </div>
      <div class="ip-track"><div class="ip-fill" style="width:${pct}%;background:${color}"></div></div>
      <ol class="ip-steps">${stepLis}</ol>
      ${verify}${err}
    </div>`;
}

function updateInstallProgressEl(host, job, langZh) {
  if (!host) return;
  host.innerHTML = renderInstallProgressHtml(job || {}, langZh);
  host.classList.remove("hidden");
}
const SHORT_MODEL = (id) => {
  const s = String(id || "");
  const parts = s.split("/");
  return parts[parts.length - 1] || s;
};

const I18N = {
  zh: {
    "login.hint": "输入访问密码以连接终端",
    "login.password": "密码",
    "login.submit": "进入",
    "login.error": "密码错误",
    "nav.newChat": "+ 新任务",
    "nav.deepWebui": "◈ Hermes 深度会话",
    "nav.deepWebuiShort": "深度会话",
    "webui.deepTitle": "Hermes 深度会话",
    "webui.refresh": "刷新",
    "webui.newTab": "新标签打开",
    "webui.close": "关闭",
    "webui.starting": "正在启动 Hermes-WebUI…",
    "webui.ready": "已连接",
    "webui.failed": "启动失败",
    "nav.chats": "进行中",
    "nav.workflows": "模板",
    "nav.tasks": "任务",
    "nav.sessions": "会话",
    "nav.control": "⚙ 控制中心",
    "chat.new": "新任务",
    "empty.title": "校园 Agent Hub",
    "empty.body": "描述任务并运行 · Agent Hub 调度 Skill / Agent · 进度条跟踪执行",
    "skills.picker": "Skill",
    "skills.auto": "自动匹配",
    "skills.add": "添加",
    "skills.selected": "已选",
    "skills.none": "未选手动 Skill（仅在显式要求或点「自动匹配」时加载）",
    "skills.pick": "— 选择 Skill —",
    "skills.hubEmpty": "— 请先在控制中心「加载」Skill —",
    "skills.remove": "移除",
    "skills.delete": "删除",
    "thinking.process": "思考过程",
    "sublane.title": "并行子代理",
    "sublane.queued": "排队",
    "sublane.running": "执行中",
    "sublane.done": "完成",
    "sublane.error": "失败",
    "sublane.synth": "正在汇总各子代理结果…",
    "sublane.planned": "已拆分并行任务",
    "orch.boardTitle": "任务调度启动",
    "orch.goal": "目标",
    "orch.modeParallel": "并行调度",
    "orch.pending": "Pending",
    "orch.processing": "Processing",
    "orch.waiting": "Waiting",
    "orch.completed": "Completed",
    "orch.from": "来自",
    "orch.heartbeat": "状态心跳",
    "orch.laneOut": "子代理产出区",
    "orch.model": "模型",
    "orch.modelPending": "待绑定模型",
    "orch.routeOpenSquilla": "OpenSquilla 分模型并行",
    "wf.running": "工作流执行中",
    "wf.done": "完成",
    "stream.running": "思考与输出中…",
    "stream.thinking": "思考中…",
    "stream.outputting": "输出中…",
    "stream.done": "已完成",
    "stream.placeholder": "正在生成回答…",
    "stream.hint.match": "分析任务与 Skill…",
    "stream.hint.dispatch": "启动 Agent…",
    "stream.hint.execute": "执行并写入回答…",
    "stream.hint.summarize": "整理最终交付…",
    "stream.resume": "已重新连接后台任务",
    "mode.workflow": "工作流模式 · Agent Hub",
    "mode.ai": "AI 对话模式 · Direct LLM",
    "mode.demo": "演示模式 · 请配置 API Key 或安装 Agent",
    "mode.claw": "Claw 已连接 · Hub↔Claw Soul 融合 · Direct LLM",
    "mode.agent": "Agent 模式 · 工具/Skill",
    "composer.hubChat": "Hub 聊天",
    "composer.settings": "任务设置",
    "hubChat.agent": "Agent（工具）",
    "hubChat.direct": "快聊",
    "engine.hermes": "Hermes Agent",
    "engine.openclaw": "OpenClaw Agent",
    "engine.direct": "Direct LLM",
    "fs.title": "选择工作路径",
    "fs.use": "使用此目录",
    "fs.close": "关闭",
    "fs.up": "↑ 上级",
    "auto.hint": "Auto 预览",
    "composer.soul": "Soul",
    "composer.route": "路由",
    "composer.mode": "模式",
    "composer.model": "模型",
    "composer.thinkingDepth": "思考深度",
    "composer.workspace": "工作区",
    "composer.workspacePh": "可选：工作目录路径",
    "composer.inputPh": "描述办公/科研任务… Enter 换行 · ⌘/Ctrl+Enter 运行工作流",
    "composer.send": "运行",
    "composer.search": "联网搜索",
    "composer.deepSearch": "深度搜索",
    "thinking.light": "轻 / Light",
    "thinking.medium": "中 / Medium",
    "thinking.high": "高 / High",
    "thinking.veryHigh": "非常高 / Very high",
    "route.auto": "Auto（自动分级）",
    "route.simple": "C0 简单 / Fast",
    "route.office": "C1 办公 / Main",
    "route.c2": "C2 长文（生成+审核）",
    "route.reasoning": "C3 推理",
    "route.vision": "Vision",
    "route.agent": "Agent（主模型）",
    "control.title": "控制中心",
    "control.close": "关闭",
    "control.appearance": "外观",
    "control.health": "健康",
    "control.backend": "后端",
    "control.search": "搜索",
    "control.models": "模型",
    "control.routing": "路由",
    "control.obsidian": "知识库",
    "control.schedule": "定时任务",
    "control.security": "安全",
    "control.runtimes": "Claws",
    "control.ecosystem": "生态",
    "control.mcp": "MCP",
    "control.recommend": "每日推荐",
    "control.skills": "Skills",
    "control.soul": "Soul",
    "control.agents": "Agents",
    "control.feedback": "反馈",
    "control.save": "保存配置",
    "msg.copy": "复制",
    "msg.quote": "引用",
    "msg.revise": "提交修改",
    "msg.cancel": "取消",
    "msg.submit": "提交到对话",
    "msg.good": "有用",
    "msg.bad": "待改进",
    "msg.copied": "已复制",
    "msg.elapsed": "耗时",
    "code.copy": "复制",
    "code.revise": "提交修改",
    "code.cancel": "取消",
    "code.submit": "提交到对话",
    "runs.active": "并行任务",
    "upload.ok": "已上传",
    "upload.fail": "上传失败",
    "attach.clear": "清除附件",
    "sub.main": "主 Agent",
    "sub.split": "分屏",
    "sub.sidebar": "侧栏",
    "sub.picker": "Subagent",
    "sub.add": "添加",
    "sub.pick": "— 选择子代理 —",
    "sub.none": "未选子代理（默认主 Agent）",
    "sub.remove": "移除",
    "ground.ok": "已锚定工作区",
    "ground.missing": "未设置工作区 — 模型不得编造目录",
    "ground.optional": "工作区可选（附件仍可用）",
    "ground.warn": "实况提示：回复中提及未在工作区验证的路径（不影响正文）",
    "ground.entries": "个已验证条目",
    "wf.inputPh": "粘贴会议笔记 / 邮件要点 / 文档内容…",
    "wf.saveInbox": "完成后写入 Obsidian AI_Candidates（需确认）",
    "wf.cancel": "取消",
    "wf.run": "运行",
    "conn.local": "本机",
    "conn.lan": "局域网",
    "agent.ready": "Agent 就绪",
    "agent.demo": "演示模式",
    "confirm.vault": "将结果写入 Obsidian AI_Candidates？仅候选区，不会进入正式目录。",
    "vault.ok": "已写入知识库候选区",
    "vault.fail": "写入失败",
    "wf.template": "(使用工作流模板)",
    "appearance.lang": "界面语言",
    "appearance.theme": "深浅模式",
    "appearance.accent": "主题色",
    "appearance.fontSize": "字号",
    "appearance.hint": "可在侧栏一键切换；保存配置后会同步到服务器，供多设备默认使用。",
    "appearance.logo": "更换 Logo",
    "appearance.logoHint": "默认左右共用同一 Logo；也可分别设置左上角与新对话居中。支持 png / jpg / svg / webp，最大 2MB。",
    "appearance.logoSidebar": "左上角",
    "appearance.logoEmpty": "新对话居中",
    "appearance.logoSlotBoth": "两处一并更换",
    "appearance.logoSlotSidebar": "仅左上角",
    "appearance.logoSlotEmpty": "仅新对话居中",
    "appearance.logoUpload": "上传图片",
    "appearance.logoReset": "恢复默认",
    "appearance.logoPresets": "内置品牌",
    "appearance.logoPresetColor": "SUAT 彩标（默认）",
    "appearance.logoPresetWhiteboard": "白板",
    "appearance.logoTooLarge": "图片过大（最大 2MB）",
    "appearance.logoBadType": "仅支持 png / jpg / svg / webp",
    "appearance.logoUpdated": "Logo 已更新",
    "appearance.logoResetDone": "已恢复默认 Logo",
    "theme.dark": "深色",
    "theme.light": "浅色",
    "theme.auto": "自动(昼夜)",
    "bg.auto": "自动(昼夜)",
    "bg.white": "纯白",
    "bg.suat": "深理工紫",
    "saved": "已保存",
    "imported": "已导入",
    "key.set": "已设置",
    "key.missing": "未设置 — 请用系统环境变量，勿写入 JSON",
  },
  en: {
    "login.hint": "Enter password to access the terminal",
    "login.password": "Password",
    "login.submit": "Enter",
    "login.error": "Invalid password",
    "nav.newChat": "+ New task",
    "nav.deepWebui": "◈ Hermes deep session",
    "nav.deepWebuiShort": "Deep chat",
    "webui.deepTitle": "Hermes deep session",
    "webui.refresh": "Refresh",
    "webui.newTab": "Open in tab",
    "webui.close": "Close",
    "webui.starting": "Starting Hermes-WebUI…",
    "webui.ready": "Connected",
    "webui.failed": "Start failed",
    "nav.chats": "Active",
    "nav.workflows": "Templates",
    "nav.tasks": "Tasks",
    "nav.sessions": "Sessions",
    "nav.control": "⚙ Control Center",
    "chat.new": "New task",
    "empty.title": "Campus Agent Hub",
    "empty.body": "Describe a task and run · Agent Hub dispatches skills/agents · progress tracked",
    "skills.picker": "Skill",
    "skills.auto": "Auto-match",
    "skills.add": "Add",
    "skills.selected": "Selected",
    "skills.none": "No manual skill (load only on explicit skill intent or Auto-match)",
    "skills.pick": "— pick a skill —",
    "skills.hubEmpty": "— Load skills in Control Center first —",
    "skills.remove": "Remove",
    "skills.delete": "Delete",
    "thinking.process": "Thinking",
    "sublane.title": "Parallel subagents",
    "sublane.queued": "Queued",
    "sublane.running": "Running",
    "sublane.done": "Done",
    "sublane.error": "Failed",
    "sublane.synth": "Synthesizing subagent results…",
    "sublane.planned": "Split into parallel tasks",
    "orch.boardTitle": "Dispatch started",
    "orch.goal": "Goal",
    "orch.modeParallel": "Parallel",
    "orch.pending": "Pending",
    "orch.processing": "Processing",
    "orch.waiting": "Waiting",
    "orch.completed": "Completed",
    "orch.from": "From",
    "orch.heartbeat": "Heartbeat",
    "orch.laneOut": "Subagent outputs",
    "orch.model": "Model",
    "orch.modelPending": "Model pending",
    "orch.routeOpenSquilla": "OpenSquilla multi-model parallel",
    "wf.running": "Workflow running",
    "wf.done": "Workflow done",
    "stream.running": "Thinking & streaming…",
    "stream.thinking": "Thinking…",
    "stream.outputting": "Streaming output…",
    "stream.done": "Complete",
    "stream.placeholder": "Generating answer…",
    "stream.hint.match": "Analyzing task & skills…",
    "stream.hint.dispatch": "Starting agent…",
    "stream.hint.execute": "Executing & writing answer…",
    "stream.hint.summarize": "Finalizing delivery…",
    "stream.resume": "Reconnected to background job",
    "mode.workflow": "Workflow · Agent Hub",
    "mode.ai": "AI chat · Direct LLM",
    "mode.demo": "Demo · set API key or install an Agent",
    "mode.claw": "Claw connected · Hub↔Claw Soul fused · Direct LLM",
    "mode.agent": "Agent mode · tools/skills",
    "composer.hubChat": "Hub chat",
    "composer.settings": "Task settings",
    "hubChat.agent": "Agent (tools)",
    "hubChat.direct": "Fast chat",
    "engine.hermes": "Hermes Agent",
    "engine.openclaw": "OpenClaw Agent",
    "engine.direct": "Direct LLM",
    "fs.title": "Choose workspace",
    "fs.use": "Use this folder",
    "fs.close": "Close",
    "fs.up": "↑ Up",
    "auto.hint": "Auto preview",
    "composer.soul": "Soul",
    "composer.route": "Route",
    "composer.mode": "Mode",
    "composer.model": "Model",
    "composer.thinkingDepth": "Thinking depth",
    "composer.workspace": "Workspace",
    "composer.workspacePh": "Optional workspace path",
    "composer.inputPh": "Describe an office/research task… Enter = newline · ⌘/Ctrl+Enter run workflow",
    "composer.send": "Run",
    "composer.search": "Web search",
    "composer.deepSearch": "Deep search",
    "thinking.light": "Light",
    "thinking.medium": "Medium",
    "thinking.high": "High",
    "thinking.veryHigh": "Very high",
    "route.auto": "Auto (classify)",
    "route.simple": "C0 Simple / Fast",
    "route.office": "C1 Office / Main",
    "route.c2": "C2 Long-form (gen + review)",
    "route.reasoning": "C3 Reasoning",
    "route.vision": "Vision",
    "route.agent": "Agent (main model)",
    "control.title": "Control Center",
    "control.close": "Close",
    "control.appearance": "Appearance",
    "control.health": "Health",
    "control.backend": "Backend",
    "control.search": "Search",
    "control.models": "Models",
    "control.routing": "Routing",
    "control.obsidian": "Knowledge",
    "control.schedule": "Schedule",
    "control.security": "Security",
    "control.runtimes": "Claws",
    "control.ecosystem": "Ecosystem",
    "control.mcp": "MCP",
    "control.recommend": "Daily",
    "control.skills": "Skills",
    "control.soul": "Soul",
    "control.agents": "Agents",
    "control.feedback": "Feedback",
    "control.save": "Save",
    "msg.copy": "Copy",
    "msg.quote": "Quote",
    "msg.revise": "Propose change",
    "msg.cancel": "Cancel",
    "msg.submit": "Submit to chat",
    "msg.good": "Good",
    "msg.bad": "Needs work",
    "msg.copied": "Copied",
    "msg.elapsed": "took",
    "code.copy": "Copy",
    "code.revise": "Propose change",
    "code.cancel": "Cancel",
    "code.submit": "Submit to chat",
    "runs.active": "Active runs",
    "upload.ok": "Uploaded",
    "upload.fail": "Upload failed",
    "attach.clear": "Clear attachments",
    "sub.main": "Main Agent",
    "sub.split": "Split",
    "sub.sidebar": "Sidebar",
    "sub.picker": "Subagent",
    "sub.add": "Add",
    "sub.pick": "— pick a subagent —",
    "sub.none": "No subagent (main Agent)",
    "sub.remove": "Remove",
    "ground.ok": "Workspace grounded",
    "ground.missing": "No workspace — model must not invent trees",
    "ground.optional": "Workspace optional (uploads still work)",
    "ground.warn": "Grounding tip: paths not verified in workspace (reply body unchanged)",
    "ground.entries": "verified entries",
    "wf.inputPh": "Paste meeting notes / email points / document text…",
    "wf.saveInbox": "Save result to Obsidian AI_Candidates (confirm)",
    "wf.cancel": "Cancel",
    "wf.run": "Run",
    "conn.local": "Local",
    "conn.lan": "LAN",
    "agent.ready": "Agent ready",
    "agent.demo": "Demo mode",
    "confirm.vault": "Write result to Obsidian AI_Candidates? Candidates only — not formal folders.",
    "vault.ok": "Wrote to knowledge inbox",
    "vault.fail": "Write failed",
    "wf.template": "(workflow template)",
    "appearance.lang": "Language",
    "appearance.theme": "Light / Dark",
    "appearance.accent": "Accent color",
    "appearance.fontSize": "Font size",
    "appearance.hint": "Use sidebar toggles anytime. Saving syncs defaults to the server for other devices.",
    "appearance.logo": "Change logo",
    "appearance.logoHint": "By default one custom logo applies to both places; you can also set sidebar and empty-state separately. png / jpg / svg / webp, max 2MB.",
    "appearance.logoSidebar": "Top-left",
    "appearance.logoEmpty": "New-chat center",
    "appearance.logoSlotBoth": "Both places",
    "appearance.logoSlotSidebar": "Top-left only",
    "appearance.logoSlotEmpty": "Empty-state only",
    "appearance.logoUpload": "Upload image",
    "appearance.logoReset": "Reset default",
    "appearance.logoPresets": "Built-in brand",
    "appearance.logoPresetColor": "SUAT color (default)",
    "appearance.logoPresetWhiteboard": "Whiteboard",
    "appearance.logoTooLarge": "Image too large (max 2MB)",
    "appearance.logoBadType": "Only png / jpg / svg / webp",
    "appearance.logoUpdated": "Logo updated",
    "appearance.logoResetDone": "Logo reset to default",
    "theme.dark": "Dark",
    "theme.light": "Light",
    "theme.auto": "Auto (day/night)",
    "bg.auto": "Auto day/night",
    "bg.white": "Pure white",
    "bg.suat": "SUAT purple",
    "saved": "Saved",
    "imported": "Imported",
    "key.set": "set",
    "key.missing": "missing — set OS env var, never paste into JSON",
  },
};

const WF_I18N = {
  meeting_minutes: { en: { name: "Meeting minutes", description: "Structure notes into decisions / todos / risks" } },
  email_draft: { en: { name: "Email draft", description: "Draft a reviewable email (does not send)" } },
  doc_summary: { en: { name: "Doc summary", description: "Short summary + key points + filename" } },
  research_review: { en: { name: "Long-form + review", description: "Generate then checklist review (C2)" } },
  code_decision: { en: { name: "Reasoning / decision", description: "Architecture, code review, hard reasoning" } },
  vision_extract: { en: { name: "Vision extract", description: "PPT/PDF/figure structure extraction" } },
  deploy_preflight: { en: { name: "Deploy preflight", description: "Read-only campus-office-ai checklist" } },
  acceptance_check: { en: { name: "Acceptance checklist", description: "Hermes/API/routing/Obsidian/security table" } },
  sop_candidate: { en: { name: "SOP candidate", description: "Draft SOP into AI_Candidates only" } },
};

const state = {
  token: localStorage.getItem("hermes_ali_token") || "",
  sessions: [],
  workflows: [],
  currentId: null,
  streaming: false,
  streamingSessionId: "",
  sessionRuns: {}, // id -> { pct, streaming }
  status: null,
  streamMeta: null,
  streamConsumers: {},
  streamBuffers: {}, // sessionId -> live SSE buffer (survives session switches)
  settings: null,
  pendingWf: null,
  lastAssistantText: "",
  liveModels: [],
  agents: null,
  activeSubagent: "",
  selectedSubagents: [],
  /** parentSessionId -> [{ childId, laneKey, title }] for multi-subagent runs */
  multiLaneChildren: {},
  pendingFiles: [],
  skillCatalog: null,
  selectedSkills: [],
  hubLoadedSkills: [],
  webSearch: false,
  deepSearch: true,
  skillCat: "office",
  skillSub: "meeting",
  soulRoles: [],
  activeSoul: "office",
  prefs: {
    language: localStorage.getItem("hermes_ali_lang") || detectSystemLanguage(),
    theme: localStorage.getItem("hermes_ali_theme") || "auto",
    accent: localStorage.getItem("hermes_ali_accent") || "suat",
    bg: (() => {
      const raw = localStorage.getItem("hermes_ali_bg") || "auto";
      return LEGACY_BGS.has(raw) ? "auto" : raw;
    })(),
    fontSize: (() => {
      const n = Number(localStorage.getItem("hermes_ali_font_size"));
      return FONT_SIZES.includes(n) ? n : 14;
    })(),
    logoSidebar: localStorage.getItem("hermes_ali_logo_sidebar") || "",
    logoEmpty: localStorage.getItem("hermes_ali_logo_empty") || "",
    thinkingDepth: normalizeThinkingDepth(localStorage.getItem("hermes_ali_thinking_depth") || "medium"),
  },
  /** Cumulative token usage for the current session (from SSE done events) */
  usage: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, cost: null },
};

function t(key) {
  const lang = state.prefs.language === "en" ? "en" : "zh";
  return (I18N[lang] && I18N[lang][key]) || (I18N.zh[key] || key);
}

function applyI18n() {
  const lang = state.prefs.language === "en" ? "en" : "zh";
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  $$("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key) el.textContent = t(key);
  });
  $$("[data-i18n-html]").forEach((el) => {
    const key = el.getAttribute("data-i18n-html");
    if (key) el.innerHTML = t(key);
  });
  $$("[data-i18n-placeholder]").forEach((el) => {
    const key = el.getAttribute("data-i18n-placeholder");
    if (key) el.setAttribute("placeholder", t(key));
  });
  $$("[data-i18n-title]").forEach((el) => {
    const key = el.getAttribute("data-i18n-title");
    if (key) el.setAttribute("title", t(key));
  });
  const langBtn = $("#btn-lang");
  if (langBtn) langBtn.textContent = lang === "zh" ? "中 / EN" : "EN / 中";
  const themeBtn = $("#btn-theme");
  if (themeBtn) {
    const resolved = resolveAppearance();
    const mode = state.prefs.theme === "auto" ? "auto" : resolved.theme;
    themeBtn.textContent = mode === "auto" ? "◐ Auto" : (resolved.theme === "dark" ? "☾ Dark" : "☀ Light");
  }
  syncFontSizeControls();
}

function isDaytime(date = new Date()) {
  const h = date.getHours();
  return h >= 7 && h < 19;
}

function normalizeBg(bg) {
  if (!bg || LEGACY_BGS.has(bg)) return "auto";
  return BGS.includes(bg) ? bg : "auto";
}

function normalizeFontSize(size) {
  const n = Number(size);
  return FONT_SIZES.includes(n) ? n : 14;
}

function fontSizeOptionLabel(px) {
  const lang = state.prefs.language === "en" ? "en" : "zh";
  return (FONT_SIZE_LABELS[lang] && FONT_SIZE_LABELS[lang][px]) || String(px);
}

function fillFontSizeSelect(sel) {
  if (!sel) return;
  const cur = normalizeFontSize(state.prefs.fontSize);
  sel.innerHTML = FONT_SIZES.map((px) =>
    `<option value="${px}"${px === cur ? " selected" : ""}>${escapeHtml(fontSizeOptionLabel(px))}</option>`
  ).join("");
}

function syncFontSizeControls() {
  const cur = normalizeFontSize(state.prefs.fontSize);
  const sel = $("#font-size-select");
  if (sel) {
    if (!sel.options.length || sel.options.length !== FONT_SIZES.length) fillFontSizeSelect(sel);
    else {
      Array.from(sel.options).forEach((opt) => {
        opt.textContent = fontSizeOptionLabel(Number(opt.value));
      });
    }
    sel.value = String(cur);
  }
  const ctrlSel = document.querySelector('[data-key="ali.font_size"]');
  if (ctrlSel) ctrlSel.value = String(cur);
  const dec = $("#btn-font-dec");
  const inc = $("#btn-font-inc");
  if (dec) dec.disabled = cur <= FONT_SIZES[0];
  if (inc) inc.disabled = cur >= FONT_SIZES[FONT_SIZES.length - 1];
}

function applyFontSize() {
  const px = normalizeFontSize(state.prefs.fontSize);
  state.prefs.fontSize = px;
  document.documentElement.style.setProperty("--font-size-base", `${px}px`);
  syncFontSizeControls();
}

function stepFontSize(delta) {
  const cur = normalizeFontSize(state.prefs.fontSize);
  const idx = Math.max(0, Math.min(FONT_SIZES.length - 1, FONT_SIZES.indexOf(cur) + delta));
  setPrefs({ fontSize: FONT_SIZES[idx] }, { syncServer: true });
}

function resolveAppearance() {
  const prefTheme = state.prefs.theme || "auto";
  const prefBg = normalizeBg(state.prefs.bg);
  const day = isDaytime();
  let theme = prefTheme === "auto" ? (day ? "light" : "dark") : (prefTheme === "light" ? "light" : "dark");
  let bg = prefBg;
  if (prefBg === "auto") bg = day ? "white" : "suat";
  return { theme, bg };
}

function normalizeLogoUrl(url) {
  const raw = String(url || "").trim();
  if (!raw) return "";
  const path = raw.split("?")[0];
  if (path === "/brand/suat-logo-color.png") return "";
  if (/^\/brand\/[a-zA-Z0-9._-]+\.(?:png|jpe?g|webp|svg)$/.test(path)) return path;
  if (/^\/brand\/custom\/[a-zA-Z0-9._-]+\.(?:png|jpe?g|webp|svg)$/.test(path)) return path;
  return "";
}

function logoSrc(slot) {
  const key = slot === "empty" ? "logoEmpty" : "logoSidebar";
  const path = normalizeLogoUrl(state.prefs[key]);
  if (!path) return DEFAULT_LOGO;
  if (path.startsWith("/brand/custom/")) {
    const bust = localStorage.getItem(`hermes_ali_${key}_t`) || LOGO_VER;
    return `${path}?t=${encodeURIComponent(bust)}`;
  }
  return `${path}?v=${LOGO_VER}`;
}

function logoForTheme() {
  return logoSrc("sidebar");
}

function applyBrandLogos() {
  $$(".brand-logo").forEach((img) => {
    img.src = logoSrc("sidebar");
    img.style.background = "transparent";
  });
  $$(".empty-logo-img").forEach((img) => {
    img.src = logoSrc("empty");
    img.style.background = "transparent";
  });
  const prevSide = $("#logo-preview-sidebar");
  const prevEmpty = $("#logo-preview-empty");
  if (prevSide) prevSide.src = logoSrc("sidebar");
  if (prevEmpty) prevEmpty.src = logoSrc("empty");
}

function applyTheme() {
  const resolved = resolveAppearance();
  document.documentElement.setAttribute("data-theme", resolved.theme === "light" ? "light" : "dark");
  document.documentElement.setAttribute("data-accent", ACCENTS.includes(state.prefs.accent) ? state.prefs.accent : "suat");
  document.documentElement.setAttribute("data-bg", resolved.bg);
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) {
    const map = { white: "#ffffff", suat: resolved.theme === "light" ? "#f3eaf8" : "#2a1038" };
    meta.setAttribute("content", map[resolved.bg] || (resolved.theme === "light" ? "#ffffff" : "#1a0f22"));
  }
  renderAccentDots();
  renderBgDots();
  applyBrandLogos();
  applyFontSize();
  applyI18n();
}

function persistPrefsLocal() {
  localStorage.setItem("hermes_ali_lang", state.prefs.language);
  localStorage.setItem("hermes_ali_theme", state.prefs.theme);
  localStorage.setItem("hermes_ali_accent", state.prefs.accent);
  localStorage.setItem("hermes_ali_bg", state.prefs.bg);
  localStorage.setItem("hermes_ali_font_size", String(normalizeFontSize(state.prefs.fontSize)));
  localStorage.setItem("hermes_ali_logo_sidebar", normalizeLogoUrl(state.prefs.logoSidebar));
  localStorage.setItem("hermes_ali_logo_empty", normalizeLogoUrl(state.prefs.logoEmpty));
  localStorage.setItem(
    "hermes_ali_thinking_depth",
    normalizeThinkingDepth(state.prefs.thinkingDepth || ($("#thinking-depth-select") && $("#thinking-depth-select").value) || "medium")
  );
}

async function persistPrefsServer() {
  try {
    // Reload before writing: another tab or an external config edit may have
    // changed backend settings since state.settings was rendered.
    const view = await api("/api/settings");
    const cfg = JSON.parse(JSON.stringify((view && view.config) || {}));
    if (!cfg.ali) cfg.ali = {};
    cfg.ali.language = state.prefs.language;
    cfg.ali.theme = state.prefs.theme;
    cfg.ali.accent = state.prefs.accent;
    cfg.ali.bg = state.prefs.bg;
    cfg.ali.font_size = normalizeFontSize(state.prefs.fontSize);
    cfg.ali.logo_sidebar = normalizeLogoUrl(state.prefs.logoSidebar);
    cfg.ali.logo_empty = normalizeLogoUrl(state.prefs.logoEmpty);
    const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg }) });
    state.settings = data;
  } catch (_) {
    /* offline / unauth — local prefs still apply */
  }
}

function setPrefs(partial, { syncServer = false } = {}) {
  const langChanged = Object.prototype.hasOwnProperty.call(partial, "language")
    && partial.language !== undefined
    && partial.language !== state.prefs.language;
  const appearanceChanged = ["theme", "accent", "bg", "fontSize"].some(
    (k) => Object.prototype.hasOwnProperty.call(partial, k) && partial[k] !== undefined
  );
  Object.assign(state.prefs, partial);
  if (Object.prototype.hasOwnProperty.call(partial, "bg")) {
    state.prefs.bg = normalizeBg(state.prefs.bg);
  }
  if (Object.prototype.hasOwnProperty.call(partial, "fontSize")) {
    state.prefs.fontSize = normalizeFontSize(state.prefs.fontSize);
  }
  if (Object.prototype.hasOwnProperty.call(partial, "logoSidebar")) {
    state.prefs.logoSidebar = normalizeLogoUrl(state.prefs.logoSidebar);
  }
  if (Object.prototype.hasOwnProperty.call(partial, "logoEmpty")) {
    state.prefs.logoEmpty = normalizeLogoUrl(state.prefs.logoEmpty);
  }
  if (Object.prototype.hasOwnProperty.call(partial, "accent") && !ACCENTS.includes(state.prefs.accent)) {
    state.prefs.accent = "suat";
  }
  if (Object.prototype.hasOwnProperty.call(partial, "theme")
      && !["auto", "light", "dark"].includes(state.prefs.theme)) {
    state.prefs.theme = "auto";
  }
  persistPrefsLocal();
  applyTheme();
  if (syncServer) persistPrefsServer();
  if (state.status) {
    renderConn(state.status);
    renderAgent(state.status);
  }
  if (state.workflows.length) renderWorkflowList();
  // Keep Control Center + session chrome in sync with sidebar 中/EN
  if (langChanged || Object.prototype.hasOwnProperty.call(partial, "language")) {
    applyControlCenterLanguage();
    refreshSessions().catch(() => {});
    refreshChatChromeLanguage();
    const overlay = $("#control-overlay");
    if (overlay && !overlay.classList.contains("hidden")) {
      renderControl();
    }
  } else if (appearanceChanged) {
    syncAppearanceFormControls();
  }
}

/** Keep Control Center appearance selects/dots in sync without full re-render. */
function syncAppearanceFormControls() {
  const themeSel = document.querySelector('[data-key="ali.theme"]');
  if (themeSel) themeSel.value = state.prefs.theme || "auto";
  const accentSel = document.querySelector('[data-key="ali.accent"]');
  if (accentSel) accentSel.value = state.prefs.accent || "suat";
  const bgSel = document.querySelector('[data-key="ali.bg"]');
  if (bgSel) bgSel.value = normalizeBg(state.prefs.bg);
  const fontSel = document.querySelector('[data-key="ali.font_size"]');
  if (fontSel) fontSel.value = String(normalizeFontSize(state.prefs.fontSize));
  $$("#accent-row-control .accent-dot").forEach((b) => {
    b.classList.toggle("active", b.dataset.accent === state.prefs.accent);
  });
  $$("#bg-row-control .bg-dot").forEach((b) => {
    b.classList.toggle("active", b.dataset.bg === normalizeBg(state.prefs.bg));
  });
  syncFontSizeControls();
  applyBrandLogos();
}

function selectedLogoSlot() {
  const el = document.querySelector('input[name="logo-slot"]:checked');
  return (el && el.value) || "both";
}

function applyLogoApiResult(data, statusKey) {
  if (!data) return;
  state.prefs.logoSidebar = normalizeLogoUrl(data.logo_sidebar);
  state.prefs.logoEmpty = normalizeLogoUrl(data.logo_empty);
  const sideSrc = String(data.logo_sidebar_src || "");
  const emptySrc = String(data.logo_empty_src || "");
  const sideT = sideSrc.match(/[?&]t=([^&]+)/);
  const emptyT = emptySrc.match(/[?&]t=([^&]+)/);
  if (sideT) localStorage.setItem("hermes_ali_logoSidebar_t", decodeURIComponent(sideT[1]));
  if (emptyT) localStorage.setItem("hermes_ali_logoEmpty_t", decodeURIComponent(emptyT[1]));
  persistPrefsLocal();
  applyBrandLogos();
  const status = $("#logo-status");
  if (status) status.textContent = t(statusKey || "appearance.logoUpdated");
}

function bindLogoControls() {
  const presetRow = $("#logo-preset-row");
  if (presetRow) {
    presetRow.innerHTML = "";
    LOGO_PRESETS.forEach((p) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "logo-preset-btn";
      b.title = t(p.labelKey);
      b.innerHTML = `<img src="${escapeHtml(p.src)}" alt="" /><span>${escapeHtml(t(p.labelKey))}</span>`;
      b.addEventListener("click", async () => {
        try {
          const data = await api("/api/ui/logo/preset", {
            method: "POST",
            body: JSON.stringify({ preset: p.id, slot: selectedLogoSlot() }),
          });
          applyLogoApiResult(data, p.id === "suat-color" ? "appearance.logoResetDone" : "appearance.logoUpdated");
        } catch (err) {
          const status = $("#logo-status");
          if (status) status.textContent = err.message || String(err);
        }
      });
      presetRow.appendChild(b);
    });
  }

  const fileInput = $("#logo-file-input");
  const uploadBtn = $("#btn-logo-upload");
  if (uploadBtn && fileInput) {
    uploadBtn.onclick = () => fileInput.click();
    fileInput.onchange = async () => {
      const file = fileInput.files && fileInput.files[0];
      fileInput.value = "";
      if (!file) return;
      const status = $("#logo-status");
      const okType = /\.(png|jpe?g|webp|svg)$/i.test(file.name)
        || ["image/png", "image/jpeg", "image/webp", "image/svg+xml"].includes(file.type);
      if (!okType) {
        if (status) status.textContent = t("appearance.logoBadType");
        return;
      }
      if (file.size > 2 * 1024 * 1024) {
        if (status) status.textContent = t("appearance.logoTooLarge");
        return;
      }
      try {
        const fd = new FormData();
        fd.append("slot", selectedLogoSlot());
        fd.append("file", file, file.name);
        const headers = {};
        if (state.token) headers.Authorization = `Bearer ${state.token}`;
        const res = await fetch("/api/ui/logo", { method: "POST", headers, body: fd });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error((data && data.error) || res.statusText);
        applyLogoApiResult(data, "appearance.logoUpdated");
      } catch (err) {
        if (status) status.textContent = err.message || String(err);
      }
    };
  }

  const resetBtn = $("#btn-logo-reset");
  if (resetBtn) {
    resetBtn.onclick = async () => {
      try {
        const data = await api("/api/ui/logo/reset", {
          method: "POST",
          body: JSON.stringify({ slot: selectedLogoSlot() }),
        });
        applyLogoApiResult(data, "appearance.logoResetDone");
      } catch (err) {
        const status = $("#logo-status");
        if (status) status.textContent = err.message || String(err);
      }
    };
  }
}

/** Default session titles that should follow the UI language toggle. */
const DEFAULT_SESSION_TITLES = new Set([
  "新任务", "新会话", "新聊天", "New task", "New chat", "New session", "Untitled",
]);

function sessionDisplayTitle(s) {
  const title = String((s && s.title) || "").trim();
  if (!title || DEFAULT_SESSION_TITLES.has(title)) return t("chat.new");
  return title;
}

function refreshChatChromeLanguage() {
  const cur = state.sessions.find((s) => s.id === state.currentId);
  const titleEl = $("#chat-title");
  if (titleEl) titleEl.textContent = sessionDisplayTitle(cur || { title: titleEl.textContent });
  const empty = $("#empty-state");
  if (empty) {
    const h = empty.querySelector("[data-i18n='empty.title'], h3");
    const p = empty.querySelector("[data-i18n-html='empty.body'], p");
    if (h) h.textContent = t("empty.title");
    if (p) p.innerHTML = t("empty.body");
  }
  try { renderSoulSelect(); } catch (_) {}
  try { renderSkillPicker(); } catch (_) {}
  try { renderSubagentPicker(); } catch (_) {}
  applyI18n();
}

function renderAccentDots() {
  const row = $("#accent-row");
  if (!row) return;
  row.innerHTML = "";
  ACCENTS.forEach((name) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "accent-dot" + (state.prefs.accent === name ? " active" : "");
    b.dataset.accent = name;
    b.title = name;
    b.addEventListener("click", () => setPrefs({ accent: name }, { syncServer: true }));
    row.appendChild(b);
  });
}

function renderBgDots() {
  const row = $("#bg-row");
  if (!row) return;
  row.innerHTML = "";
  const lang = state.prefs.language === "en" ? "en" : "zh";
  BGS.forEach((name) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "bg-dot" + (normalizeBg(state.prefs.bg) === name ? " active" : "");
    b.dataset.bg = name;
    b.title = (BG_LABELS[lang] && BG_LABELS[lang][name]) || name;
    b.addEventListener("click", () => setPrefs({ bg: name }, { syncServer: true }));
    row.appendChild(b);
  });
}

async function api(path, opts = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    showLogin(true);
    throw new Error("unauthorized");
  }
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : null;
  if (!res.ok) throw new Error((data && data.error) || res.statusText || "request failed");
  return data;
}

function showLogin(on) { $("#login-overlay").classList.toggle("hidden", !on); }
function setSidebarOpen(open) {
  $("#sidebar").classList.toggle("open", open);
  $("#sidebar-backdrop").classList.toggle("hidden", !open);
}

const SIDEBAR_WIDTH_KEY = "hermes_ali_sidebar_width";
const SIDEBAR_NARROW_MQ = "(max-width: 860px)";

function clampSidebarWidth(px) {
  const root = getComputedStyle(document.documentElement);
  const min = parseFloat(root.getPropertyValue("--sidebar-width-min")) || 180;
  const max = parseFloat(root.getPropertyValue("--sidebar-width-max")) || 480;
  const mainMin = parseFloat(root.getPropertyValue("--main-min-width")) || 260;
  const handle = 6;
  const roomMax = Math.max(min, window.innerWidth - mainMin - handle);
  return Math.round(Math.min(max, roomMax, Math.max(min, px)));
}

function applySidebarWidth(px, { persist = false } = {}) {
  const w = clampSidebarWidth(px);
  document.documentElement.style.setProperty("--sidebar-width", `${w}px`);
  const handle = $("#sidebar-resize");
  if (handle) {
    handle.setAttribute("aria-valuenow", String(w));
    handle.setAttribute("aria-valuemin", "180");
    handle.setAttribute("aria-valuemax", "480");
  }
  if (persist) {
    try { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(w)); } catch (_) { /* ignore */ }
  }
  return w;
}

function clearSidebarWidthPreference() {
  try { localStorage.removeItem(SIDEBAR_WIDTH_KEY); } catch (_) { /* ignore */ }
  document.documentElement.style.removeProperty("--sidebar-width");
  const handle = $("#sidebar-resize");
  if (handle) {
    handle.removeAttribute("aria-valuenow");
  }
}

function loadSidebarWidthPreference() {
  if (window.matchMedia(SIDEBAR_NARROW_MQ).matches) return;
  let stored = null;
  try { stored = localStorage.getItem(SIDEBAR_WIDTH_KEY); } catch (_) { stored = null; }
  const n = stored != null ? Number(stored) : NaN;
  if (Number.isFinite(n) && n > 0) applySidebarWidth(n);
}

function setupSidebarResize() {
  const handle = $("#sidebar-resize");
  if (!handle) return;

  loadSidebarWidthPreference();

  let dragging = false;
  let startX = 0;
  let startW = 0;

  const onMove = (clientX) => {
    if (!dragging) return;
    const delta = clientX - startX;
    applySidebarWidth(startW + delta);
  };

  const endDrag = (clientX) => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("resizing-sidebar");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    if (typeof clientX === "number") onMove(clientX);
    const cur = parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"));
    if (Number.isFinite(cur)) applySidebarWidth(cur, { persist: true });
  };

  const onPointerMove = (e) => onMove(e.clientX);
  const onPointerUp = (e) => endDrag(e.clientX);

  handle.addEventListener("pointerdown", (e) => {
    if (window.matchMedia(SIDEBAR_NARROW_MQ).matches) return;
    if (e.button != null && e.button !== 0) return;
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = $("#sidebar")?.getBoundingClientRect().width
      || parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"))
      || 300;
    document.body.classList.add("resizing-sidebar");
    try { handle.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
  });

  handle.addEventListener("dblclick", () => {
    if (window.matchMedia(SIDEBAR_NARROW_MQ).matches) return;
    clearSidebarWidthPreference();
  });

  handle.addEventListener("keydown", (e) => {
    if (window.matchMedia(SIDEBAR_NARROW_MQ).matches) return;
    const step = e.shiftKey ? 24 : 12;
    const cur = $("#sidebar")?.getBoundingClientRect().width
      || parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--sidebar-width"))
      || 300;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      applySidebarWidth(cur - step, { persist: true });
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      applySidebarWidth(cur + step, { persist: true });
    } else if (e.key === "Home") {
      e.preventDefault();
      applySidebarWidth(180, { persist: true });
    } else if (e.key === "End") {
      e.preventDefault();
      applySidebarWidth(480, { persist: true });
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      clearSidebarWidthPreference();
    }
  });

  window.matchMedia(SIDEBAR_NARROW_MQ).addEventListener("change", (ev) => {
    if (ev.matches) {
      // Overlay mode: don't leave a fixed inline width fighting the drawer
      document.documentElement.style.removeProperty("--sidebar-width");
    } else {
      loadSidebarWidthPreference();
    }
  });
}

const COMPOSER_ADV_KEY = "hermes_ali_composer_advanced";
const COMPOSER_HEIGHT_KEY = "hermes_ali_composer_height";

function composerInputMaxPx() {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--composer-input-max");
  const n = parseFloat(raw);
  return Number.isFinite(n) && n > 0 ? n : 160;
}

function clampComposerInputHeight(px) {
  const root = getComputedStyle(document.documentElement);
  const min = parseFloat(root.getPropertyValue("--composer-input-min")) || 44;
  const ceil = parseFloat(root.getPropertyValue("--composer-input-max-ceil")) || 360;
  const room = Math.max(min, Math.floor(window.innerHeight * 0.45));
  return Math.round(Math.min(ceil, room, Math.max(min, px)));
}

function applyComposerInputHeight(px, { persist = false, syncTextarea = true } = {}) {
  const h = clampComposerInputHeight(px);
  document.documentElement.style.setProperty("--composer-input-max", `${h}px`);
  const handle = $("#composer-resize");
  if (handle) {
    handle.setAttribute("aria-valuenow", String(h));
    handle.setAttribute("aria-valuemin", "44");
    handle.setAttribute("aria-valuemax", String(Math.round(Math.min(
      parseFloat(getComputedStyle(document.documentElement).getPropertyValue("--composer-input-max-ceil")) || 360,
      window.innerHeight * 0.45
    ))));
  }
  if (syncTextarea) {
    const el = $("#input");
    if (el) {
      el.style.height = "auto";
      el.style.height = Math.min(el.scrollHeight, h) + "px";
    }
  }
  if (persist) {
    try { localStorage.setItem(COMPOSER_HEIGHT_KEY, String(h)); } catch (_) { /* ignore */ }
  }
  return h;
}

function clearComposerHeightPreference() {
  try { localStorage.removeItem(COMPOSER_HEIGHT_KEY); } catch (_) { /* ignore */ }
  document.documentElement.style.removeProperty("--composer-input-max");
  const handle = $("#composer-resize");
  if (handle) handle.removeAttribute("aria-valuenow");
  const el = $("#input");
  if (el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, composerInputMaxPx()) + "px";
  }
}

function loadComposerHeightPreference() {
  let stored = null;
  try { stored = localStorage.getItem(COMPOSER_HEIGHT_KEY); } catch (_) { stored = null; }
  const n = stored != null ? Number(stored) : NaN;
  if (Number.isFinite(n) && n > 0) applyComposerInputHeight(n, { syncTextarea: true });
}

function setupComposerResize() {
  const handle = $("#composer-resize");
  if (!handle) return;

  loadComposerHeightPreference();

  let dragging = false;
  let startY = 0;
  let startH = 0;

  const onMove = (clientY) => {
    if (!dragging) return;
    // Dragging handle upward increases textarea max height
    const delta = startY - clientY;
    applyComposerInputHeight(startH + delta, { syncTextarea: true });
  };

  const endDrag = (clientY) => {
    if (!dragging) return;
    dragging = false;
    document.body.classList.remove("resizing-composer");
    window.removeEventListener("pointermove", onPointerMove);
    window.removeEventListener("pointerup", onPointerUp);
    window.removeEventListener("pointercancel", onPointerUp);
    if (typeof clientY === "number") onMove(clientY);
    applyComposerInputHeight(composerInputMaxPx(), { persist: true, syncTextarea: true });
  };

  const onPointerMove = (e) => onMove(e.clientY);
  const onPointerUp = (e) => endDrag(e.clientY);

  handle.addEventListener("pointerdown", (e) => {
    if (e.button != null && e.button !== 0) return;
    e.preventDefault();
    dragging = true;
    startY = e.clientY;
    startH = composerInputMaxPx();
    document.body.classList.add("resizing-composer");
    try { handle.setPointerCapture(e.pointerId); } catch (_) { /* ignore */ }
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
  });

  handle.addEventListener("dblclick", () => clearComposerHeightPreference());

  handle.addEventListener("keydown", (e) => {
    const step = e.shiftKey ? 24 : 12;
    const cur = composerInputMaxPx();
    if (e.key === "ArrowUp") {
      e.preventDefault();
      applyComposerInputHeight(cur + step, { persist: true });
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      applyComposerInputHeight(cur - step, { persist: true });
    } else if (e.key === "Home") {
      e.preventDefault();
      applyComposerInputHeight(44, { persist: true });
    } else if (e.key === "End") {
      e.preventDefault();
      applyComposerInputHeight(360, { persist: true });
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      clearComposerHeightPreference();
    }
  });
}

function isComposerAdvancedOpen() {
  return !$("#composer-advanced")?.hidden;
}

function setComposerAdvancedOpen(open, { persist = true } = {}) {
  const panel = $("#composer-advanced");
  const btn = $("#btn-composer-adv");
  const composer = $(".composer");
  if (!panel || !btn) return;
  panel.hidden = !open;
  btn.setAttribute("aria-expanded", open ? "true" : "false");
  composer?.classList.toggle("is-adv-open", open);
  if (persist) {
    try { localStorage.setItem(COMPOSER_ADV_KEY, open ? "1" : "0"); } catch (_) { /* ignore */ }
  }
  updateComposerAdvSummary();
}

function updateComposerAdvSummary() {
  const summary = $("#composer-adv-summary");
  const badge = $("#composer-adv-badge");
  const soul = $("#soul-select");
  const model = $("#model-select");
  const route = $("#route-select");
  const nSkill = (state.selectedSkills || []).length;
  const nSub = (state.selectedSubagents || []).length;
  const count = nSkill + nSub;
  if (badge) {
    if (count > 0) {
      badge.textContent = String(count);
      badge.classList.remove("hidden");
    } else {
      badge.textContent = "";
      badge.classList.add("hidden");
    }
  }
  if (!summary || isComposerAdvancedOpen()) return;
  const parts = [];
  const soulLabel = soul?.selectedOptions?.[0]?.textContent?.trim();
  const modelLabel = model?.selectedOptions?.[0]?.textContent?.trim();
  const routeLabel = route?.selectedOptions?.[0]?.textContent?.trim();
  if (soulLabel) parts.push(soulLabel);
  if (routeLabel) parts.push(routeLabel);
  if (modelLabel) parts.push(modelLabel);
  if (nSkill) parts.push(state.prefs.language !== "en" ? `Skill×${nSkill}` : `Skill×${nSkill}`);
  if (nSub) parts.push(state.prefs.language !== "en" ? `子代理×${nSub}` : `Sub×${nSub}`);
  summary.textContent = parts.filter(Boolean).join(" · ");
  summary.title = summary.textContent;
}

function setupComposerAdvanced() {
  let stored = null;
  try { stored = localStorage.getItem(COMPOSER_ADV_KEY); } catch (_) { stored = null; }
  // Default collapsed unless user previously expanded
  setComposerAdvancedOpen(stored === "1", { persist: false });

  $("#btn-composer-adv")?.addEventListener("click", () => {
    setComposerAdvancedOpen(!isComposerAdvancedOpen());
  });

  ["soul-select", "route-select", "model-select", "chat-mode-select", "thinking-depth-select"].forEach((id) => {
    $(`#${id}`)?.addEventListener("change", () => updateComposerAdvSummary());
  });
  updateComposerAdvSummary();
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function looksLikeSecret(value) {
  const v = String(value || "").trim();
  if (!v) return false;
  const lower = v.toLowerCase();
  if (lower.startsWith("nvapi-") || lower.startsWith("sk-") || lower.startsWith("sk-ant-") || lower.startsWith("sk-or-")) return true;
  if (v.length >= 40 && /[a-z]/.test(v) && /\d/.test(v) && v !== v.toUpperCase()) return true;
  return false;
}

/** Format processing duration for message headers. */
function formatElapsed(ms) {
  const n = Math.max(0, Number(ms) || 0);
  if (n < 1000) return `${Math.round(n)}ms`;
  if (n < 60000) {
    const s = Math.round(n / 100) / 10;
    return `${String(s).replace(/\.0$/, "")}s`;
  }
  const m = Math.floor(n / 60000);
  const sec = Math.floor((n % 60000) / 1000);
  return `${m}m ${String(sec).padStart(2, "0")}s`;
}

function detectCodeLang(lang, code) {
  const L = String(lang || "").trim().toLowerCase();
  const map = {
    py: "python", python: "python",
    r: "r", rs: "rust", rust: "rust",
    pl: "perl", perl: "perl",
    sh: "shell", bash: "shell", zsh: "shell", shell: "shell", fish: "shell", powershell: "shell", ps1: "shell",
    md: "markdown", markdown: "markdown",
    js: "javascript", javascript: "javascript", ts: "typescript", typescript: "typescript",
    json: "json", yaml: "yaml", yml: "yaml", toml: "toml",
    sql: "sql", html: "html", css: "css", xml: "xml",
    go: "go", java: "java", c: "c", cpp: "cpp", "c++": "cpp", csharp: "csharp", cs: "csharp",
    rb: "ruby", ruby: "ruby", php: "php", swift: "swift", kt: "kotlin", kotlin: "kotlin",
    lua: "lua", dockerfile: "dockerfile", makefile: "makefile",
  };
  if (L && map[L]) return map[L];
  if (L) return L.replace(/[^a-z0-9_+-]/g, "") || "";
  const c = String(code || "");
  if (/^#!\/.+\b(?:bash|sh|zsh|fish)\b/m.test(c) || /^\s*(?:sudo\s+)?(?:apt|yum|dnf|pacman|brew|systemctl|chmod|chown|grep|awk|sed|curl|wget)\b/m.test(c)) return "shell";
  if (/^\s*(?:library|require)\s*\(|\s*<-\s*|ggplot|tidyverse|data\.frame/m.test(c)) return "r";
  if (/^\s*(?:def |async def |import |from \w+ import |class \w+[:(])/m.test(c) || /^\s*print\s*\(/m.test(c)) return "python";
  if (/^\s*(?:use\s+strict|my\s+\$|package\s+\w+|sub\s+\w+\s*\{)/m.test(c)) return "perl";
  if (/^#{1,6}\s|\[[^\]]+\]\([^)]+\)/m.test(c) && !/[{};]/.test(c.slice(0, 200))) return "markdown";
  return "";
}

function langBadgeLabel(id) {
  const labels = {
    python: "Python", r: "R", perl: "Perl", shell: "Shell",
    markdown: "Markdown", javascript: "JavaScript", typescript: "TypeScript",
    json: "JSON", yaml: "YAML", sql: "SQL", go: "Go", rust: "Rust",
    java: "Java", html: "HTML", css: "CSS", cpp: "C++", c: "C",
    ruby: "Ruby", php: "PHP", csharp: "C#", kotlin: "Kotlin",
  };
  return labels[id] || (id ? id : "code");
}

function codeBoxHtml(lang, code) {
  const detected = detectCodeLang(lang, code);
  const badge = langBadgeLabel(detected);
  const cls = detected ? `language-${escapeHtml(detected)}` : "";
  return `<div class="code-box" data-lang="${escapeHtml(detected || "code")}">
    <div class="code-box-head">
      <span class="code-lang">${escapeHtml(badge)}</span>
      <span class="code-box-actions">
        <button type="button" class="btn ghost chip code-act" data-code-act="copy" data-i18n="code.copy">${escapeHtml(t("code.copy"))}</button>
        <button type="button" class="btn ghost chip code-act" data-code-act="revise" data-i18n="code.revise">${escapeHtml(t("code.revise"))}</button>
      </span>
    </div>
    <pre class="code-box-pre"><code class="${cls}">${code}</code></pre>
    <div class="code-box-edit hidden">
      <textarea class="code-box-ta" rows="8" spellcheck="false"></textarea>
      <div class="code-box-edit-actions">
        <button type="button" class="btn ghost chip code-act" data-code-act="cancel-edit" data-i18n="code.cancel">${escapeHtml(t("code.cancel"))}</button>
        <button type="button" class="btn primary chip code-act" data-code-act="submit-edit" data-i18n="code.submit">${escapeHtml(t("code.submit"))}</button>
      </div>
    </div>
  </div>`;
}

function insertIntoComposer(text) {
  const input = $("#input");
  if (!input) return;
  input.value = text;
  input.focus();
  updateSendEnabled();
  input.scrollIntoView({ block: "nearest", behavior: "smooth" });
  try {
    const len = input.value.length;
    input.setSelectionRange(len, len);
  } catch (_) {}
}

function getMsgSelectionText(msgEl) {
  const body = msgEl && msgEl.querySelector(".body");
  if (!body) return "";
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed) return "";
  try {
    if (!body.contains(sel.anchorNode) || !body.contains(sel.focusNode)) return "";
  } catch (_) {
    return "";
  }
  return String(sel.toString() || "").trim();
}

/** Prefer in-bubble text selection; else full message content. */
function getMsgActionPayload(msgEl, m) {
  const selected = getMsgSelectionText(msgEl);
  if (selected) return { text: selected, fromSelection: true };
  const full = (m && m.content)
    || (msgEl.querySelector(".body") && msgEl.querySelector(".body").innerText)
    || "";
  return { text: String(full), fromSelection: false };
}

function buildQuoteComposerText(quoted) {
  const langZh = state.prefs.language !== "en";
  if (langZh) {
    return `【引用】\n${quoted}\n\n【问题】\n`;
  }
  return `[Quote]\n${quoted}\n\n[Question]\n`;
}

function buildProseReviseComposerText(orig, modified, fromSelection) {
  const langZh = state.prefs.language !== "en";
  if (langZh) {
    return fromSelection
      ? `请仅针对以下段落提交修改（不要改动其余回复内容）。\n\n【原文】\n${orig}\n\n【修改后】\n${modified}\n\n请基于「修改后」更新该片段，并给出简要说明。`
      : `请针对以下回复内容提交修改。\n\n【原文】\n${orig}\n\n【修改后】\n${modified}\n\n请基于「修改后」更新，并给出简要说明。`;
  }
  return fromSelection
    ? `Please revise only this passage (leave the rest of the reply unchanged).\n\n[Original]\n${orig}\n\n[Modified]\n${modified}\n\nUpdate this passage based on the modified version and briefly explain.`
    : `Please revise the following reply.\n\n[Original]\n${orig}\n\n[Modified]\n${modified}\n\nUpdate based on the modified version and briefly explain.`;
}

function ensureMsgProseEdit(el, m) {
  let edit = el.querySelector(".msg-prose-edit");
  if (edit) return edit;
  edit = document.createElement("div");
  edit.className = "msg-prose-edit hidden";
  edit.innerHTML = `<textarea class="msg-prose-ta" rows="8" spellcheck="true"></textarea>
    <div class="msg-prose-edit-actions">
      <button type="button" class="btn ghost chip msg-act" data-act="cancel-edit" data-i18n="msg.cancel">${escapeHtml(t("msg.cancel"))}</button>
      <button type="button" class="btn primary chip msg-act" data-act="submit-edit" data-i18n="msg.submit">${escapeHtml(t("msg.submit"))}</button>
    </div>`;
  const actions = el.querySelector(".msg-actions");
  if (actions) el.insertBefore(edit, actions);
  else el.appendChild(edit);
  edit.querySelectorAll(".msg-act").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      handleMsgAction(el, m, btn.dataset.act);
    });
  });
  return edit;
}

function bindCodeBoxActions(root) {
  const scope = root || document;
  scope.querySelectorAll(".code-box").forEach((box) => {
    if (box.dataset.bound === "1") return;
    box.dataset.bound = "1";
    const codeEl = box.querySelector(".code-box-pre code");
    const getText = () => (codeEl && codeEl.textContent) || "";
    box.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-code-act]");
      if (!btn || !box.contains(btn)) return;
      const act = btn.dataset.codeAct;
      const edit = box.querySelector(".code-box-edit");
      const pre = box.querySelector(".code-box-pre");
      const ta = box.querySelector(".code-box-ta");
      if (act === "copy") {
        try {
          await navigator.clipboard.writeText(getText());
        } catch (_) {
          const tmp = document.createElement("textarea");
          tmp.value = getText();
          document.body.appendChild(tmp);
          tmp.select();
          document.execCommand("copy");
          tmp.remove();
        }
        btn.textContent = "✓";
        setTimeout(() => { btn.textContent = t("code.copy"); }, 1000);
        return;
      }
      if (act === "revise") {
        if (ta) ta.value = getText();
        edit?.classList.remove("hidden");
        pre?.classList.add("hidden");
        ta?.focus();
        return;
      }
      if (act === "cancel-edit") {
        edit?.classList.add("hidden");
        pre?.classList.remove("hidden");
        return;
      }
      if (act === "submit-edit") {
        const lang = box.dataset.lang || "";
        const fence = lang && lang !== "code" ? lang : "";
        const modified = ta ? ta.value : "";
        const orig = getText();
        const langZh = state.prefs.language !== "en";
        const msg = langZh
          ? `请仅针对以下代码框提交修改（不要改动其余回复内容）。\n\n【原代码】\n\`\`\`${fence}\n${orig}\n\`\`\`\n\n【修改后】\n\`\`\`${fence}\n${modified}\n\`\`\`\n\n请基于「修改后」更新该片段，并给出简要说明。`
          : `Please revise only this code block (leave the rest of the reply unchanged).\n\n[Original]\n\`\`\`${fence}\n${orig}\n\`\`\`\n\n[Modified]\n\`\`\`${fence}\n${modified}\n\`\`\`\n\nUpdate this snippet based on the modified version and briefly explain.`;
        insertIntoComposer(msg);
        edit?.classList.add("hidden");
        pre?.classList.remove("hidden");
      }
    });
  });
}

function renderMd(text) {
  const blocks = [];
  let s = escapeHtml(text);
  s = s.replace(/```([a-zA-Z0-9_+\-]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    const i = blocks.length;
    blocks.push({ lang, code: code.replace(/\n$/, "") });
    return `\0CB${i}\0`;
  });
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/_([^_]+)_/g, "<em>$1</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  s = s.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^- (.+)$/gm, "<div>• $1</div>");
  s = s.replace(/\n/g, "<br>");
  s = s.replace(/\0CB(\d+)\0/g, (_, i) => {
    const b = blocks[Number(i)];
    return b ? codeBoxHtml(b.lang, b.code) : "";
  });
  return s;
}

async function boot() {
  applyTheme();
  try {
    const status = await api("/api/status");
    state.status = status;
    $("#version-label").textContent = `v${status.version || "1.2.0"}`;
    if (status.ui) {
      const hasLocal =
        localStorage.getItem("hermes_ali_lang") ||
        localStorage.getItem("hermes_ali_theme") ||
        localStorage.getItem("hermes_ali_accent") ||
        localStorage.getItem("hermes_ali_bg");
      if (!hasLocal) {
        setPrefs({
          language: status.ui.language || "zh",
          theme: status.ui.theme || "auto",
          accent: status.ui.accent || "suat",
          bg: normalizeBg(status.ui.bg || "auto"),
        });
      } else if (status.ui.bg && !localStorage.getItem("hermes_ali_bg")) {
        setPrefs({ bg: normalizeBg(status.ui.bg) });
      }
      // Logos: server is source of truth (uploaded files live on hub state dir)
      if ("logo_sidebar" in status.ui || "logo_empty" in status.ui) {
        state.prefs.logoSidebar = normalizeLogoUrl(status.ui.logo_sidebar);
        state.prefs.logoEmpty = normalizeLogoUrl(status.ui.logo_empty);
        const sideSrc = String(status.ui.logo_sidebar_src || "");
        const emptySrc = String(status.ui.logo_empty_src || "");
        const sideT = sideSrc.match(/[?&]t=([^&]+)/);
        const emptyT = emptySrc.match(/[?&]t=([^&]+)/);
        if (sideT) localStorage.setItem("hermes_ali_logoSidebar_t", decodeURIComponent(sideT[1]));
        if (emptyT) localStorage.setItem("hermes_ali_logoEmpty_t", decodeURIComponent(emptyT[1]));
        persistPrefsLocal();
        applyBrandLogos();
      }
    }
    await loadAgents();
    renderConn(status);
    renderAgent(status);
    // Prefer Auto; only honor non-office saved defaults (office was wrongly used as default before)
    const dr = status.default_route || "auto";
    if ($("#route-select")) $("#route-select").value = (dr === "office" || !dr) ? "auto" : dr;
    if ($("#chat-mode-select") && status.ui) {
      $("#chat-mode-select").value = status.ui.chat_mode === "single" ? "single" : "auto";
    }
    if ($("#thinking-depth-select")) {
      const depth = normalizeThinkingDepth(
        localStorage.getItem("hermes_ali_thinking_depth")
          || (status.ui && status.ui.thinking_depth)
          || state.prefs.thinkingDepth
          || "medium"
      );
      $("#thinking-depth-select").value = depth;
      state.prefs.thinkingDepth = depth;
    }
    if ($("#hub-chat-mode-select") && status.ui) {
      const hubMode = status.ui.hub_chat_mode === "direct" ? "direct" : "agent";
      $("#hub-chat-mode-select").value = hubMode;
    }
    if (status.auth_required && !status.authenticated && !state.token) {
      showLogin(true);
      applyI18n();
      return;
    }
    showLogin(false);
    await ensureAgentRuntime();
    await Promise.all([refreshSessions(), loadWorkflows(), loadSettings(), loadSkillCatalog(), loadSoulRoles()]);
    bindActiveRunsDelegation();
    bindSessionListDelegation();
    await syncActiveJobs();
    // refresh status after agent auto-activate
    try {
      const st2 = await api("/api/status");
      state.status = st2;
      renderAgent(st2);
      renderConn(st2);
    } catch (_) {}
    if (!state.sessions.length) await createSession();
    else if (!state.currentId) await selectSession(state.sessions[0].id);
    else if (state.sessionRuns[state.currentId]?.streaming && !state.streamConsumers[state.currentId]) {
      const cur = state.sessions.find((s) => s.id === state.currentId);
      const job = (cur && cur.active_job) || {
        stream_id: state.sessionRuns[state.currentId].streamId,
        pct: state.sessionRuns[state.currentId].pct,
        status: "running",
      };
      if (job.stream_id) resumeSessionStream(state.currentId, job).catch(() => {});
    }
    if (status.health && status.health.workspace) {
      $("#workspace-input").value = status.health.workspace;
    }
    applyI18n();
    scheduleWorkspaceGrounding();
  } catch (err) {
    if (String(err.message) !== "unauthorized") {
      $("#agent-badge").textContent = "offline";
      console.error(err);
    }
    applyI18n();
  }
}

function renderConn(status) {
  const port = status.port || 8765;
  const ips = status.local_ips || [];
  const lines = [`${t("conn.local")}: http://127.0.0.1:${port}`];
  ips.slice(0, 2).forEach((ip) => lines.push(`${t("conn.lan")}: http://${ip}:${port}`));
  $("#conn-info").innerHTML = lines.map(escapeHtml).join("<br>");
}

function clawLabelFor(agent, kind) {
  // Display label for Control Center Claw selection (resolved / linked / auto).
  const langZh = !(state.prefs && state.prefs.language === "en");
  if (kind === "linked") {
    return langZh
      ? (agent.claw_linked_label_zh || agent.claw_linked_label || agent.runtime_linked || "")
      : (agent.claw_linked_label || agent.runtime_linked || "");
  }
  if (kind === "auto") {
    return langZh
      ? (agent.claw_auto_label_zh || agent.claw_auto_label || agent.runtime_auto || "")
      : (agent.claw_auto_label || agent.runtime_auto || "");
  }
  return langZh
    ? (agent.claw_label_zh || agent.claw_label || agent.runtime_resolved || agent.runtime_active || "")
    : (agent.claw_label || agent.runtime_resolved || agent.runtime_active || "");
}

function renderEngineBadge(meta, routeInfo) {
  const el = $("#engine-badge");
  if (!el) return;
  const langZh = state.prefs.language !== "en";
  const hubMode = (routeInfo && routeInfo.hub_chat_mode)
    || ((state.status && state.status.agent && state.status.agent.hub_chat_mode) || "agent");
  const mode = (meta && meta.mode) || "";
  const engine = (meta && meta.engine) || (routeInfo && routeInfo.chat_engine) || "";
  if (meta && meta.agent_mode) {
    if (mode.includes("openclaw") || engine === "openclaw") {
      el.textContent = t("engine.openclaw");
    } else {
      el.textContent = t("engine.hermes");
    }
    el.className = "route-badge engine-badge ok";
    el.title = langZh ? "Agent 引擎运行中（工具/Skill）" : "Agent engine active (tools/skills)";
    return;
  }
  if (hubMode === "direct" || mode === "direct-llm" || engine === "direct") {
    el.textContent = langZh ? `${t("hubChat.direct")} · ${t("engine.direct")}` : `${t("hubChat.direct")} · Direct`;
    el.className = "route-badge engine-badge";
    el.title = langZh ? "快聊：Hub Direct 流式" : "Fast chat: Hub Direct streaming";
    return;
  }
  if (engine === "hermes" || engine === "openclaw") {
    el.textContent = engine === "openclaw" ? t("engine.openclaw") : t("engine.hermes");
    el.className = "route-badge engine-badge ok";
    el.title = langZh ? "Agent 模式（待发送）" : "Agent mode (idle)";
    return;
  }
  el.textContent = "";
  el.className = "route-badge engine-badge hidden";
}

function renderModeBanner(status) {
  let el = $("#mode-banner");
  if (!el) {
    el = document.createElement("div");
    el.id = "mode-banner";
    el.className = "mode-banner";
    const main = $(".main");
    const topbar = $(".topbar");
    if (main && topbar) main.insertBefore(el, topbar.nextSibling);
  }
  const agent = (status && status.agent) || {};
  const engine = agent.chat_engine || "";
  const hubMode = agent.hub_chat_mode || (agent.agent_mode ? "agent" : "direct");
  const rt = agent.runtime_resolved || agent.runtime_active || "";
  const linked = agent.runtime_linked || "";
  const clawName = clawLabelFor(agent, "resolved") || rt || "";
  const linkedName = clawLabelFor(agent, "linked") || linked;
  const autoName = clawLabelFor(agent, "auto");
  const soul = agent.soul || {};
  const soulRole = soul.active_role || state.activeSoul || "";
  const fused = soul.fused ? " · fused✓" : "";
  const clawSoul = soul.claw_soul_exists ? " · claw-soul✓" : (rt && rt !== "direct" ? " · claw-soul…" : "");
  const soulBit = soulRole ? ` · soul=<code>${escapeHtml(soulRole)}</code>${clawSoul}${fused}` : "";
  const autoBit = agent.runtime_auto && (agent.runtime_active === "auto" || !agent.runtime_active)
    ? ` · auto→<code>${escapeHtml(autoName || agent.runtime_auto)}</code>`
    : "";
  const clawBit = clawName ? ` · claw=<code>${escapeHtml(clawName)}</code>` : "";
  const hubBit = hubMode === "direct"
    ? ` · ${escapeHtml(t("hubChat.direct"))}`
    : ` · ${escapeHtml(t("hubChat.agent"))}`;
  if (engine === "hermes" || engine === "hermes-cli" || engine === "openclaw" || agent.agent_mode) {
    const engLabel = engine === "openclaw" ? t("engine.openclaw") : t("engine.hermes");
    el.innerHTML = `<strong>${escapeHtml(t("mode.agent"))}</strong> · ${escapeHtml(engLabel)}${hubBit}${clawBit || " · claw=<code>Hermes Agent</code>"}${autoBit}${soulBit}`;
  } else if (engine === "direct-llm" || agent.direct_llm) {
    el.innerHTML = `<strong>${escapeHtml(t("mode.ai"))}</strong>${hubBit} — ${escapeHtml(agent.api_key_masked || "API")}${clawBit}${autoBit}${soulBit}`;
  } else if (rt && rt !== "direct" && rt !== "auto") {
    const linkedBit = linked && linked !== rt
      ? ` · linked=<code>${escapeHtml(linkedName)}</code>`
      : "";
    el.innerHTML = `<strong>${escapeHtml(t("mode.claw"))}</strong>${clawBit}${linkedBit}${autoBit}${soulBit}`;
  } else {
    el.innerHTML = `<strong>${escapeHtml(t("mode.demo"))}</strong>${clawBit}${soulBit}`;
  }
}

function renderAgent(status) {
  const el = $("#agent-badge");
  const agent = status.agent || {};
  const health = status.health || {};
  const policy = health.data_policy || "";
  const rt = agent.runtime_resolved || "";
  const clawName = clawLabelFor(agent, "resolved") || rt || "";
  const hubMode = agent.hub_chat_mode || "agent";
  const engine = agent.chat_engine || "";
  if (engine === "hermes" || engine === "hermes-cli" || engine === "openclaw" || agent.agent_mode) {
    const eng = engine === "openclaw" ? "OpenClaw" : (clawName || "Hermes");
    el.textContent = `${t("mode.agent")} · ${eng} · ${policy || "office"}`;
    el.className = "badge ok";
  } else if (agent.direct_llm || engine === "direct-llm") {
    const label = hubMode === "direct" ? t("hubChat.direct") : ((rt && rt !== "direct") ? t("mode.claw") : t("mode.ai"));
    el.textContent = `${label} · ${clawName || rt || "direct"}`;
    el.className = "badge ok";
  } else {
    el.textContent = `${t("mode.demo")}`;
    el.className = "badge warn";
  }
  renderModeBanner(status);
  renderEngineBadge(null, (status && status.agent) || {});
}

function setRouteBadge(info) {
  if (!info) return;
  const auto = info.auto ? "AUTO→" : "";
  const depth = info.thinking_label || info.thinking_depth || "";
  const depthBit = depth ? ` · ${depth}` : "";
  const label = `${auto}${info.tier || "?"} / ${info.route_key || ""}${depthBit}${info.model ? " · " + info.model : ""}`;
  $("#route-badge").textContent = label;
  const titleParts = [
    info.provider || "",
    info.model || "",
    info.thinking_depth ? `depth=${info.thinking_depth}` : "",
    info.temperature != null ? `T=${info.temperature}` : "",
    info.max_tokens != null ? `max=${info.max_tokens}` : "",
  ].filter(Boolean);
  $("#route-badge").title = titleParts.join(" · ");
}

let _wsSnapTimer = null;
async function refreshWorkspaceGrounding() {
  const box = $("#ws-grounding");
  if (!box) return;
  const path = ($("#workspace-input") && $("#workspace-input").value || "").trim();
  if (!path) {
    // No scary warning — workspace is optional when using session uploads
    box.innerHTML = "";
    return;
  }
  try {
    const q = new URLSearchParams({ path, session_id: state.currentId || "" });
    const snap = await api(`/api/workspace/snapshot?${q}`);
    if (!snap.ok && !(snap.upload_count > 0)) {
      box.innerHTML = `<span class="ground-badge warn">${escapeHtml(snap.error || t("ground.missing"))}</span>`;
      return;
    }
    const sample = (snap.entries || []).slice(0, 8).map((e) => e.relative).join(", ");
    box.innerHTML = `<span class="ground-badge ok">${escapeHtml(t("ground.ok"))} · ${snap.entry_count || 0} ${escapeHtml(t("ground.entries"))}</span>
      <span class="ground-sample" title="${escapeHtml(sample)}">${escapeHtml(sample)}${(snap.entries || []).length > 8 ? "…" : ""}</span>`;
  } catch (e) {
    box.innerHTML = `<span class="ground-badge warn">${escapeHtml(e.message || "snapshot failed")}</span>`;
  }
}

function scheduleWorkspaceGrounding() {
  clearTimeout(_wsSnapTimer);
  _wsSnapTimer = setTimeout(() => refreshWorkspaceGrounding().catch(() => {}), 400);
}

function showGroundingWarn(check, hostEl) {
  // Soft footer only — never rewrite streamed assistant body.
  if (!check || check.ok || !(check.unverified || []).length) return;
  const host = hostEl || $("#messages");
  if (host && host.querySelector?.(".ground-warn")) return;
  const note = document.createElement("div");
  note.className = "ground-warn soft";
  note.innerHTML = `<strong>${escapeHtml(t("ground.warn"))}</strong>:
    ${(check.unverified || []).slice(0, 10).map((p) => `<code>${escapeHtml(p)}</code>`).join(" ")}
    ${check.scaffold_risk ? " · scaffold risk" : ""}`;
  host.appendChild(note);
}

let _autoTimer = null;
async function previewAutoRoute() {
  const hint = $("#auto-route-hint");
  if (!hint) return;
  const route = $("#route-select").value || "auto";
  const text = $("#input").value.trim();
  if (route !== "auto") {
    hint.textContent = "";
    return;
  }
  if (!text) {
    hint.textContent = `${t("auto.hint")}: …`;
    return;
  }
  try {
    const info = await api("/api/routing/resolve", {
      method: "POST",
      body: JSON.stringify({ route: "auto", message: text }),
    });
    hint.textContent = `${t("auto.hint")}: ${info.tier} → ${info.route_key} · ${info.model || "(no model)"}`;
    setRouteBadge(info);
  } catch (_) {
    hint.textContent = "";
  }
}

function scheduleAutoPreview() {
  clearTimeout(_autoTimer);
  _autoTimer = setTimeout(previewAutoRoute, 280);
}

let fsState = { path: "", parent: null, target: null };

async function openFsBrowser(startPath, targetSelector) {
  fsState.target = targetSelector || "#workspace-input";
  $("#fs-overlay").classList.remove("hidden");
  $("#fs-title").textContent = t("fs.title");
  $("#btn-fs-use").textContent = t("fs.use");
  $("#btn-fs-close").textContent = t("fs.close");
  $("#btn-fs-up").textContent = t("fs.up");
  const start = startPath || ($(fsState.target) && $(fsState.target).value.trim()) || "";
  await loadFs(start);
}

async function loadFs(path) {
  const data = await api(`/api/fs/list?path=${encodeURIComponent(path || "")}`);
  if (!data.ok) {
    $("#fs-list").innerHTML = `<div class="muted">${escapeHtml(data.error || "error")}</div>`;
    return;
  }
  fsState.path = data.path;
  fsState.parent = data.parent;
  $("#fs-path").value = data.path;
  const shorts = $("#fs-shortcuts");
  shorts.innerHTML = "";
  (data.shortcuts || []).forEach((s) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "btn ghost chip";
    b.textContent = s.label;
    b.addEventListener("click", () => loadFs(s.path));
    shorts.appendChild(b);
  });
  const list = $("#fs-list");
  list.innerHTML = "";
  (data.entries || []).forEach((e) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "fs-item";
    b.textContent = `📁 ${e.name}`;
    b.addEventListener("click", () => loadFs(e.path));
    b.addEventListener("dblclick", () => {
      const target = $(fsState.target || "#workspace-input");
      if (target) target.value = e.path;
      closeFsBrowser();
      if ((fsState.target || "") === "#workspace-input") scheduleWorkspaceGrounding();
    });
    list.appendChild(b);
  });
  if (!(data.entries || []).length) {
    list.innerHTML = `<div class="muted">(empty)</div>`;
  }
}

function closeFsBrowser() {
  $("#fs-overlay").classList.add("hidden");
}

async function refreshSessions() {
  const data = await api("/api/sessions");
  state.sessions = data.sessions || [];
  for (const s of state.sessions) {
    const job = s.active_job;
    if (job && job.status === "running") {
      const prev = state.sessionRuns[s.id] || {};
      state.sessionRuns[s.id] = {
        ...prev,
        streaming: true,
        pct: job.pct || prev.pct || 0,
        streamId: job.stream_id || prev.streamId,
      };
    }
  }
  renderSessionList();
}

async function syncActiveJobs() {
  try {
    const data = await api("/api/jobs/active");
    for (const job of data.jobs || []) {
      if (job.status === "running") {
        const prev = state.sessionRuns[job.session_id] || {};
        state.sessionRuns[job.session_id] = {
          ...prev,
          streaming: true,
          pct: job.pct || prev.pct || 0,
          streamId: job.stream_id,
        };
      }
    }
    renderSessionList();
  } catch (_) {}
}

function getStreamBuffer(sessionId) {
  if (!sessionId) return { rawBuf: "", full: "" };
  if (!state.streamBuffers[sessionId]) {
    state.streamBuffers[sessionId] = { rawBuf: "", full: "", route: null, elapsed_ms: null };
  }
  return state.streamBuffers[sessionId];
}

function resolveLiveAssistant(sessionId) {
  if (state.currentId !== sessionId) return { assistantEl: null, bodyEl: null };
  const assistantEl = $("#messages .msg.assistant:last-child");
  const bodyEl = assistantEl ? assistantEl.querySelector(".body") : null;
  return { assistantEl, bodyEl };
}

function paintStreamBuffer(sessionId, { force = false } = {}) {
  if (state.currentId !== sessionId) return;
  const bag = getStreamBuffer(sessionId);
  let { assistantEl, bodyEl } = resolveLiveAssistant(sessionId);
  if (!bodyEl) return;
  bag.assistantEl = assistantEl;
  bag.bodyEl = bodyEl;
  const text = force && bag.rawBuf ? sanitizeWorkflowText(bag.rawBuf) : (bag.full || sanitizeWorkflowText(bag.rawBuf));
  bag.full = text;
  bodyEl.innerHTML = text
    ? renderMd(text)
    : `<p class="muted">${escapeHtml(t("stream.placeholder"))}</p>`;
  bindCodeBoxActions(bodyEl);
  if (bag.elapsed_ms != null && assistantEl) {
    updateMessageElapsedMeta(assistantEl, bag.route, bag.elapsed_ms);
  }
  const messages = $("#messages");
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function scheduleStreamPaint(sessionId) {
  const bag = getStreamBuffer(sessionId);
  if (state.currentId !== sessionId) return; // inert while switched away
  if (bag._paintTimer) return;
  bag._paintTimer = setTimeout(() => {
    bag._paintTimer = null;
    requestAnimationFrame(() => paintStreamBuffer(sessionId));
  }, 150);
}

function updateMessageElapsedMeta(assistantEl, route, elapsedMs) {
  if (!assistantEl || elapsedMs == null) return;
  const meta = assistantEl.querySelector(".meta");
  if (!meta) return;
  const role = "Agent Hub";
  let routeBit = "";
  if (route && route.tier) {
    routeBit = ` · ${route.tier}/${route.route_key || ""}${route.model ? " · " + route.model : ""}`;
  }
  if (route && route.subagent_label) {
    routeBit += ` · ${route.subagent_label}`;
  }
  const label = state.prefs.language !== "en"
    ? `${t("msg.elapsed")} ${formatElapsed(elapsedMs)}`
    : formatElapsed(elapsedMs);
  meta.textContent = `${role}${routeBit} · ${label}`;
}

function isVisibleSessionRun(sid, run) {
  if (!sid || !run || !run.streaming) return false;
  // Hidden parallel-lane children must not steal the strip / switch target
  if (run.parentId) return false;
  if (run.multi === false && run.subagent_label && !state.sessions.some((s) => s.id === sid)) return false;
  // Only sessions that appear in the sidebar (non-hidden)
  return state.sessions.some((s) => s.id === sid);
}

function topLevelActiveRuns() {
  return Object.entries(state.sessionRuns).filter(([sid, r]) => isVisibleSessionRun(sid, r));
}

function chipLabelForRun(sid, r) {
  const sess = state.sessions.find((s) => s.id === sid);
  const title = sess ? sessionDisplayTitle(sess) : String(sid).slice(0, 8);
  const pct = Math.max(0, Math.min(100, Math.round((r && r.pct) || 0)));
  const multi = r && r.multi ? (state.prefs.language !== "en" ? " · 多代理" : " · multi") : "";
  return { title, pct, multi, text: `${title}${multi} · ${pct}%` };
}

function renderActiveRuns({ force = false } = {}) {
  const box = $("#active-runs");
  if (!box) return;
  const runs = topLevelActiveRuns();
  if (!runs.length) {
    box.classList.add("hidden");
    box.innerHTML = "";
    box.dataset.sig = "";
    return;
  }
  box.classList.remove("hidden");
  const sig = runs.map(([sid]) => sid).sort().join("|");
  // In-place pct update — avoid destroying chips mid-click (was blocking session switch)
  if (!force && box.dataset.sig === sig && box.querySelector(".active-run-chip")) {
    runs.forEach(([sid, r]) => {
      const btn = box.querySelector(`.active-run-chip[data-sid="${CSS.escape(sid)}"]`);
      if (!btn) return;
      const { text } = chipLabelForRun(sid, r);
      const label = btn.querySelector(".ar-label");
      if (label) label.textContent = text;
      else btn.lastChild && (btn.childNodes[btn.childNodes.length - 1].textContent = ` ${text}`);
      btn.classList.toggle("active", sid === state.currentId);
      btn.dataset.pct = String(Math.round(r.pct || 0));
    });
    return;
  }
  box.dataset.sig = sig;
  box.innerHTML = `<span class="active-runs-label">${escapeHtml(t("runs.active"))}</span>` + runs.map(([sid, r]) => {
    const { text, pct } = chipLabelForRun(sid, r);
    const active = sid === state.currentId ? " active" : "";
    return `<button type="button" class="active-run-chip${active}" data-sid="${escapeHtml(sid)}" data-pct="${pct}">
      <span class="ar-dot" aria-hidden="true"></span>
      <span class="ar-label">${escapeHtml(text)}</span>
    </button>`;
  }).join("");
}

function bindActiveRunsDelegation() {
  const box = $("#active-runs");
  if (!box || box.dataset.delegated === "1") return;
  box.dataset.delegated = "1";
  box.addEventListener("click", (e) => {
    const btn = e.target.closest(".active-run-chip[data-sid]");
    if (!btn || !box.contains(btn)) return;
    e.preventDefault();
    const sid = btn.dataset.sid;
    if (!sid) return;
    if (sid === state.currentId) return;
    selectSession(sid).catch((err) => {
      console.warn(err);
      const langZh = state.prefs.language !== "en";
      alert(langZh ? `无法切换任务：${err.message || err}` : `Cannot switch task: ${err.message || err}`);
    });
  });
}

function restoreLiveMultiOrch(sessionId) {
  const bag = state.streamBuffers[sessionId];
  const plan = bag && bag.orchPlan;
  if (!plan || !plan.lanes || !plan.lanes.length) return false;
  if (state.currentId !== sessionId) return false;
  let { assistantEl, bodyEl } = resolveLiveAssistant(sessionId);
  if (!assistantEl) {
    assistantEl = appendMessage({
      role: "assistant",
      content: bag.full || bag.rawBuf || "",
      route: { multi_subagents: true, lane_count: plan.lanes.length, goal: plan.goal },
    });
    bodyEl = assistantEl.querySelector(".body");
  }
  ensureOrchBoard(assistantEl, plan);
  ensureSublanes(assistantEl, plan);
  plan.lanes.forEach((l) => {
    const st = l.status || (l.content ? "completed" : "processing");
    setLaneStatus(assistantEl, l.key, st, l.progress || formatLaneModelLabel(l));
    setLaneModel(assistantEl, l.key, l);
    if (l.content) setLaneBody(assistantEl, l.key, l.content);
  });
  if (bodyEl && (bag.full || bag.rawBuf)) {
    bodyEl.innerHTML = renderMd(sanitizeWorkflowText(bag.full || bag.rawBuf));
    bindCodeBoxActions(bodyEl);
  }
  bag.assistantEl = assistantEl;
  bag.bodyEl = bodyEl;
  return true;
}

function makeStreamHandlers(sessionId, assistantEl, bodyEl, startRoute, stateBag) {
  const bag = getStreamBuffer(sessionId);
  if (stateBag) {
    bag.rawBuf = stateBag.rawBuf || bag.rawBuf || "";
    bag.full = stateBag.full || bag.full || "";
  }
  bag.route = startRoute || bag.route || null;
  bag.assistantEl = assistantEl || null;
  bag.bodyEl = bodyEl || null;
  // Keep caller bag in sync for sendMessage return value
  const mirror = stateBag || bag;
  const viewAlive = () => state.currentId === sessionId;
  const liveAssistant = () => {
    if (!viewAlive()) return { assistantEl: null, bodyEl: null };
    let a = bag.assistantEl;
    let b = bag.bodyEl;
    if (!a || !a.isConnected || !b || !b.isConnected) {
      ({ assistantEl: a, bodyEl: b } = resolveLiveAssistant(sessionId));
      bag.assistantEl = a;
      bag.bodyEl = b;
    }
    return { assistantEl: a, bodyEl: b };
  };
  return {
    onRoute(r) {
      bag.route = r || bag.route;
      const subLabel = (r && (r.subagent_label || r.subagent_id)) || "";
      setSessionRun(sessionId, {
        route: r,
        subagent_label: subLabel || undefined,
      });
      if (viewAlive()) {
        setRouteBadge(r);
        renderEngineBadge(state.streamMeta, r);
      }
    },
    onProgress(p) {
      if (!p) return;
      const pct = p.pct || state.sessionRuns[sessionId]?.pct || 30;
      const hint = streamHintFromProgressLabel(p.label);
      const phase = (p.label === "execute" || p.label === "summarize" || pct >= 45) ? "outputting" : "thinking";
      setSessionRun(sessionId, { pct });
      if (viewAlive()) setWorkflowProgress(pct, null, hint || undefined, phase);
      const thinkLine = thinkingFromProgressLabel(p.label);
      if (thinkLine && viewAlive()) {
        bag._progressThink = bag._progressThink || new Set();
        if (!bag._progressThink.has(p.label)) {
          bag._progressThink.add(p.label);
          const { assistantEl: a } = liveAssistant();
          if (a) appendThinking(a, thinkLine);
        }
      }
    },
    onThinking(text) {
      if (!viewAlive()) return;
      const { assistantEl: a } = liveAssistant();
      if (a) appendThinking(a, text);
      else setWorkflowProgress(state.sessionRuns[sessionId]?.pct || 20, null, text, "thinking");
    },
    onHeal(h) {
      if (!viewAlive() || !h) return;
      const { assistantEl: a } = liveAssistant();
      if (!a) return;
      const bits = [h.label || "heal"];
      if (h.message) bits.push(h.message);
      if (h.candidates && h.candidates.length) bits.push("候选：" + h.candidates.slice(0, 3).join(", "));
      if (h.installed && h.installed.length) bits.push("已装：" + h.installed.join(", "));
      appendThinking(a, bits.join(" · "));
    },
    onToken(tok) {
      bag.rawBuf += tok;
      mirror.rawBuf = bag.rawBuf;
      const skillId = detectSkillCallFromText(tok);
      const nextPct = Math.min(85, (state.sessionRuns[sessionId]?.pct || 50) + (skillId ? 5 : 1));
      setSessionRun(sessionId, { pct: nextPct });
      // Defer sanitize/renderMd — only for the visible session, throttled.
      if (viewAlive()) {
        if (!bag._wroteFirstToken) {
          bag._wroteFirstToken = true;
          const { assistantEl: a } = liveAssistant();
          if (a) appendThinking(a, state.prefs.language !== "en" ? "已开始写入回答正文" : "Started writing the reply");
        }
        if (skillId) {
          const { assistantEl: a } = liveAssistant();
          if (a) appendThinking(a, `Skill：${skillId}`);
        }
        setWorkflowProgress(nextPct, null, t("stream.hint.execute"), "outputting");
        scheduleStreamPaint(sessionId);
      }
    },
    onTool(tool) {
      const name = tool.name || tool.skill || "skill";
      const nextPct = Math.min(90, (state.sessionRuns[sessionId]?.pct || 55) + 8);
      setSessionRun(sessionId, { pct: nextPct });
      if (viewAlive()) {
        setWorkflowProgress(nextPct, null, `${name}${tool.preview ? " — " + tool.preview : ""}`, "outputting");
        const { assistantEl: a } = liveAssistant();
        if (a) appendThinking(a, `工具：${name}${tool.preview ? " — " + tool.preview : ""}`);
      }
    },
    onOrchestrationPlan(payload) {
      if (!viewAlive()) return;
      const { assistantEl: a } = liveAssistant();
      if (a) applyOrchestrationPlanEvent(a, payload);
    },
    onSubagentStatus(payload) {
      if (!viewAlive()) return;
      const { assistantEl: a } = liveAssistant();
      if (a) applySubagentStatusEvent(a, payload);
    },
    onSubagentDone(payload) {
      if (!viewAlive()) return;
      const { assistantEl: a } = liveAssistant();
      if (!a) return;
      const key = (payload && (payload.id || payload.lane || payload.key)) || "";
      setLaneStatus(a, key, "completed", (payload && (payload.progress || payload.message)) || t("sublane.done"));
      if (payload && payload.content && key) setLaneBody(a, key, payload.content);
      appendThinking(a, `${t("orch.from")} ${payload.title || key} · ${t("sublane.done")}`);
    },
    onMeta(m) {
      state.streamMeta = m || null;
      if (viewAlive()) renderEngineBadge(m, startRoute || bag.route || null);
    },
    onError(err) {
      bag.rawBuf += `\n\n**Error:** ${err}`;
      mirror.rawBuf = bag.rawBuf;
      bag.full = sanitizeWorkflowText(bag.rawBuf);
      mirror.full = bag.full;
      if (viewAlive()) {
        const { assistantEl: a, bodyEl: b } = liveAssistant();
        if (b) {
          b.innerHTML = renderMd(bag.full);
          bindCodeBoxActions(b);
        }
        if (a) a.classList.add("error");
      }
    },
    onDone(payload) {
      if (payload && payload.content) {
        bag.rawBuf = payload.content;
        bag.full = sanitizeWorkflowText(payload.content);
        mirror.rawBuf = bag.rawBuf;
        mirror.full = bag.full;
      } else {
        bag.full = sanitizeWorkflowText(bag.rawBuf);
        mirror.full = bag.full;
      }
      state.lastAssistantText = bag.full;
      if (payload && payload.elapsed_ms != null) bag.elapsed_ms = payload.elapsed_ms;
      if (payload && payload.route) bag.route = payload.route;
      const { assistantEl: a, bodyEl: b } = liveAssistant();
      if (viewAlive()) {
        if (a && payload && payload.message_id) a.dataset.mid = payload.message_id;
        if (payload && payload.grounding_check) showGroundingWarn(payload.grounding_check, a);
        if (b) {
          b.innerHTML = renderMd(bag.full || "(完成)");
          bindCodeBoxActions(b);
        }
        if (a) {
          collapseThinking(a);
          if (bag.elapsed_ms != null) updateMessageElapsedMeta(a, bag.route || payload?.route, bag.elapsed_ms);
        }
      }
      setSessionRun(sessionId, { pct: 100 });
      // ── Token usage from done payload (OpenSquilla) ─────────────────────
      if (payload && payload.usage) {
        const u = payload.usage;
        state.usage.input = (state.usage.input || 0) + (u.inputTokens || 0);
        state.usage.output = (state.usage.output || 0) + (u.outputTokens || 0);
        state.usage.cacheRead = (state.usage.cacheRead || 0) + (u.cacheReadTokens || 0);
        state.usage.cacheWrite = (state.usage.cacheWrite || 0) + (u.cacheWriteTokens || 0);
        if (u.costUsd != null) {
          state.usage.cost = (state.usage.cost || 0) + u.costUsd;
        }
        updateTokenChip(state.usage);
      }
    },
    bag: mirror,
  };
}

async function resumeSessionStream(sessionId, jobInfo) {
  const streamId = (jobInfo && (jobInfo.stream_id || jobInfo.streamId)) || "";
  if (!streamId || state.streamConsumers[sessionId]) return;
  state.streamConsumers[sessionId] = true;
  state.streaming = true;
  state.streamingSessionId = sessionId;
  const route = (jobInfo && jobInfo.route) || null;
  setSessionRun(sessionId, {
    streaming: true,
    pct: (jobInfo && jobInfo.pct) || 0,
    streamId,
    route,
    subagent_label: (route && (route.subagent_label || route.subagent_id)) || "",
  });
  updateSendEnabled();

  const viewAlive = () => state.currentId === sessionId;
  let assistantEl = null;
  let bodyEl = null;
  if (viewAlive()) {
    assistantEl = $("#messages .msg.assistant:last-child");
    bodyEl = assistantEl && assistantEl.querySelector(".body");
    const lastMsg = $("#messages .msg:last-child");
    if (!lastMsg || lastMsg.classList.contains("user")) {
      assistantEl = appendMessage({ role: "assistant", content: "", route });
      bodyEl = assistantEl.querySelector(".body");
    }
    resetWorkflowProgress(t("stream.running"));
    setWorkflowProgress((jobInfo && jobInfo.pct) || 12, null, t("stream.resume"), "thinking");
    if (route) {
      setRouteBadge(route);
      renderEngineBadge(null, route);
    }
  }

  const preview = (jobInfo && jobInfo.content_preview) || "";
  const bag = getStreamBuffer(sessionId);
  if (preview && preview.length > (bag.rawBuf || "").length) {
    bag.rawBuf = preview;
    bag.full = sanitizeWorkflowText(preview);
  }
  bag.route = route || bag.route;
  if (viewAlive() && bodyEl && bag.full) {
    bodyEl.innerHTML = renderMd(bag.full);
    bindCodeBoxActions(bodyEl);
  }

  const handlers = makeStreamHandlers(sessionId, assistantEl, bodyEl, route, bag);
  try {
    await readSSE(`/api/stream/${encodeURIComponent(streamId)}?from=0`, handlers);
    if (viewAlive()) finishWorkflowProgress(true);
  } catch (err) {
    if (viewAlive()) {
      const live = resolveLiveAssistant(sessionId);
      if (live.bodyEl) {
        live.bodyEl.innerHTML = renderMd(`**Error:** ${err.message || err}`);
        bindCodeBoxActions(live.bodyEl);
      }
      if (live.assistantEl) live.assistantEl.classList.add("error");
      finishWorkflowProgress(false);
    }
  } finally {
    delete state.streamConsumers[sessionId];
    clearSessionRun(sessionId);
    // Drop buffer after a short delay so refresh can show persisted message
    setTimeout(() => {
      if (!state.streamConsumers[sessionId]) delete state.streamBuffers[sessionId];
    }, 8000);
    state.streaming = Object.values(state.sessionRuns).some((r) => r.streaming);
    state.streamingSessionId = state.streaming
      ? (Object.keys(state.sessionRuns).find((k) => state.sessionRuns[k].streaming) || "")
      : "";
    updateSendEnabled();
    renderActiveRuns();
    await refreshSessions();
  }
}

function updateSessionRunUi(id) {
  const next = state.sessionRuns[id];
  if (!next) return;
  // Hidden multi-lane children: never rebuild sidebar; strip ignores them
  if (next.parentId || !state.sessions.some((s) => s.id === id)) {
    renderActiveRuns();
    return;
  }
  const el = document.querySelector(`.session-item[data-sid="${CSS.escape(String(id))}"]`);
  if (!el) {
    // Avoid full list rebuild on every pct tick — only when item missing
    if (!next._listed) {
      next._listed = true;
      renderSessionList();
    }
    renderActiveRuns();
    return;
  }
  const running = !!next.streaming;
  const pct = Math.max(0, Math.min(100, Math.round(next.pct || 0)));
  const sub = next.subagent_label || "";
  el.classList.toggle("running", running);
  el.style.setProperty("--run-pct", `${pct}%`);
  let spin = el.querySelector(".session-spinner");
  const main = el.querySelector(".session-main");
  if (running) {
    if (!spin && main) {
      spin = document.createElement("span");
      spin.className = "session-spinner";
      spin.setAttribute("aria-hidden", "true");
      main.insertBefore(spin, main.firstChild);
    }
    let statusEl = el.querySelector(".session-status");
    if (!statusEl && main) {
      statusEl = document.createElement("span");
      statusEl.className = "session-status running-tag";
      main.appendChild(statusEl);
    }
    if (statusEl) {
      statusEl.className = "session-status running-tag";
      const langZh = state.prefs.language !== "en";
      statusEl.textContent = `${langZh ? "执行中" : "Running"} ${pct}%${sub ? ` · ${sub}` : ""}`;
    }
  } else {
    spin?.remove();
    const statusEl = el.querySelector(".session-status");
    if (statusEl) {
      statusEl.className = "session-status idle-tag";
      statusEl.textContent = state.prefs.language !== "en" ? "就绪" : "Idle";
    }
  }
  // Soft update parallel strip (no full rebuild unless membership changed)
  renderActiveRuns();
}

function setSessionRun(id, patch) {
  if (!id) return;
  const prev = state.sessionRuns[id] || { pct: 0, streaming: false };
  const next = { ...prev, ...patch };
  state.sessionRuns[id] = next;
  const keys = patch ? Object.keys(patch) : [];
  const pctOnly = keys.length === 1 && keys[0] === "pct";
  if (pctOnly) {
    if (next._uiPctTimer) return;
    next._uiPctTimer = setTimeout(() => {
      if (state.sessionRuns[id]) delete state.sessionRuns[id]._uiPctTimer;
      updateSessionRunUi(id);
    }, 200);
    return;
  }
  if (next._uiPctTimer) {
    clearTimeout(next._uiPctTimer);
    delete next._uiPctTimer;
  }
  updateSessionRunUi(id);
}

function clearSessionRun(id) {
  if (!id || !state.sessionRuns[id]) return;
  const run = state.sessionRuns[id];
  if (run._uiPctTimer) clearTimeout(run._uiPctTimer);
  delete state.sessionRuns[id];
  const el = document.querySelector(`.session-item[data-sid="${CSS.escape(String(id))}"]`);
  if (el) {
    el.classList.remove("running");
    el.style.removeProperty("--run-pct");
    el.querySelector(".session-spinner")?.remove();
    el.querySelector(".session-pct")?.remove();
    const statusEl = el.querySelector(".session-status");
    if (statusEl) {
      statusEl.className = "session-status idle-tag";
      statusEl.textContent = state.prefs.language !== "en" ? "就绪" : "Idle";
    }
  } else {
    renderSessionList();
  }
  // Keep live buffer briefly so switch-back still paints final text until refresh
  renderActiveRuns();
}

function bindSessionListDelegation() {
  const list = $("#session-list");
  if (!list || list.dataset.delegated === "1") return;
  list.dataset.delegated = "1";
  list.addEventListener("click", (e) => {
    const actions = e.target.closest(".session-actions");
    if (actions) {
      const rename = e.target.closest("[data-rename]");
      const backup = e.target.closest("[data-backup]");
      const del = e.target.closest("[data-del]");
      if (rename) {
        e.preventDefault();
        e.stopPropagation();
        const sid = rename.dataset.rename;
        const s = state.sessions.find((x) => x.id === sid);
        renameSession(sid, s && s.title);
      } else if (backup) {
        e.preventDefault();
        e.stopPropagation();
        const sid = backup.dataset.backup;
        const s = state.sessions.find((x) => x.id === sid);
        backupSession(sid, s && s.title);
      } else if (del) {
        e.preventDefault();
        e.stopPropagation();
        const sid = del.dataset.del;
        const langZh = state.prefs.language !== "en";
        if (confirm(langZh ? "删除该会话？" : "Delete this chat?")) deleteSession(sid);
      }
      return;
    }
    const item = e.target.closest(".session-item[data-sid]");
    if (!item || !list.contains(item)) return;
    const sid = item.dataset.sid;
    if (!sid) return;
    if (sid === state.currentId) {
      setSidebarOpen(false);
      return;
    }
    selectSession(sid).catch((err) => {
      console.warn(err);
      const langZh = state.prefs.language !== "en";
      alert(langZh ? `无法切换会话：${err.message || err}` : `Cannot switch session: ${err.message || err}`);
    });
    setSidebarOpen(false);
  });
}

function renderSessionList() {
  const list = $("#session-list");
  if (!list) return;
  const langZh = state.prefs.language !== "en";
  list.innerHTML = "";
  state.sessions.forEach((s) => {
    const run = state.sessionRuns[s.id];
    const running = !!(run && run.streaming);
    const pct = Math.max(0, Math.min(100, Math.round((run && run.pct) || 0)));
    const btn = document.createElement("div");
    btn.className = "session-item"
      + (s.id === state.currentId ? " active" : "")
      + (running ? " running" : "");
    btn.dataset.sid = s.id;
    btn.setAttribute("role", "button");
    btn.tabIndex = 0;
    const title = sessionDisplayTitle(s);
    btn.innerHTML = `
      <span class="session-main">
        ${running ? `<span class="session-spinner" aria-hidden="true"></span>` : ""}
        <span class="title">${escapeHtml(title)}</span>
        ${running
          ? `<span class="session-status running-tag">${langZh ? "执行中" : "Running"} ${pct}%</span>`
          : `<span class="session-status idle-tag">${langZh ? "就绪" : "Idle"}</span>`}
      </span>
      <span class="session-actions">
        <button type="button" class="act" data-rename="${escapeHtml(s.id)}" title="${escapeHtml(langZh ? "更改名称" : "Rename")}">✎</button>
        <button type="button" class="act" data-backup="${escapeHtml(s.id)}" title="${escapeHtml(langZh ? "备份" : "Backup")}">⬇</button>
        <button type="button" class="act danger" data-del="${escapeHtml(s.id)}" title="${escapeHtml(langZh ? "删除" : "Delete")}">×</button>
      </span>`;
    if (running) {
      btn.style.setProperty("--run-pct", `${pct}%`);
    }
    btn.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        if (s.id === state.currentId) {
          setSidebarOpen(false);
          return;
        }
        selectSession(s.id).catch((err) => {
          console.warn(err);
          if (langZh) alert(`无法切换会话：${err.message || err}`);
          else alert(`Cannot switch session: ${err.message || err}`);
        });
        setSidebarOpen(false);
      }
    });
    list.appendChild(btn);
  });
}

async function renameSession(id, current) {
  const next = prompt(state.prefs.language === "zh" ? "会话名称" : "Chat title", current || sessionDisplayTitle({ title: current }) || "");
  if (next == null) return;
  const title = next.trim();
  if (!title) return;
  await api(`/api/sessions/${id}`, { method: "PATCH", body: JSON.stringify({ title }) });
  if (state.currentId === id) $("#chat-title").textContent = title;
  await refreshSessions();
}

async function backupSession(id, titleHint) {
  const langZh = state.prefs.language !== "en";
  try {
    const s = await api(`/api/sessions/${id}`);
    const payload = {
      backed_up_at: new Date().toISOString(),
      session: s,
    };
    // Prefer server-side backup when available
    let serverPath = "";
    try {
      const res = await api(`/api/sessions/${id}/backup`, { method: "POST", body: "{}" });
      if (res && res.path) serverPath = res.path;
    } catch (_) { /* fall through to download */ }
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const a = document.createElement("a");
    const safe = String(titleHint || s.title || id).replace(/[^\w\u4e00-\u9fff\-]+/g, "_").slice(0, 40);
    a.href = URL.createObjectURL(blob);
    a.download = `session-backup-${safe || id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(a.href);
    const status = $("#settings-status");
    const msg = serverPath
      ? (langZh ? `已备份并下载；服务器：${serverPath}` : `Backed up & downloaded; server: ${serverPath}`)
      : (langZh ? "已下载会话备份 JSON" : "Session backup JSON downloaded");
    if (status) status.textContent = msg;
    else console.info(msg);
  } catch (err) {
    alert(langZh ? `备份失败：${err.message || err}` : `Backup failed: ${err.message || err}`);
  }
}

async function archiveSession(id) {
  await api(`/api/sessions/${id}`, { method: "PATCH", body: JSON.stringify({ archived: true }) });
  if (state.currentId === id) {
    state.currentId = null;
    $("#messages").innerHTML = "";
    $("#chat-title").textContent = t("chat.new");
  }
  await refreshSessions();
  if (!state.currentId && state.sessions.length) await selectSession(state.sessions[0].id);
  else if (!state.sessions.length) await createSession();
}

function wfLabel(w) {
  if (state.prefs.language === "en" && WF_I18N[w.id] && WF_I18N[w.id].en) {
    return {
      name: WF_I18N[w.id].en.name,
      description: WF_I18N[w.id].en.description,
    };
  }
  return { name: w.name, description: w.description || "" };
}

function renderWorkflowList() {
  const list = $("#workflow-list");
  if (!list) return;
  list.innerHTML = "";
  state.workflows.forEach((w) => {
    const label = wfLabel(w);
    const btn = document.createElement("button");
    btn.className = "wf-item";
    btn.innerHTML = `<div class="name">${escapeHtml(w.icon || "")} ${escapeHtml(label.name)}</div>
      <div class="desc">${escapeHtml(label.description)}</div>
      <span class="tier">${escapeHtml(w.tier)} · ${escapeHtml(w.route)}</span>`;
    btn.addEventListener("click", () => openWorkflow(w));
    list.appendChild(btn);
  });
}

async function loadWorkflows() {
  const data = await api("/api/workflows");
  state.workflows = data.presets || [];
  renderWorkflowList();
}

async function loadSkillCatalog() {
  try {
    state.skillCatalog = await api("/api/skills/catalog");
  } catch (_) {
    state.skillCatalog = { taxonomy: [] };
  }
  await loadHubLoadedSkills();
  renderSkillPicker();
}

async function loadHubLoadedSkills() {
  try {
    const data = await api("/api/skills/hub-loaded");
    state.hubLoadedSkills = data.hub_loaded_skills || [];
  } catch (_) {
    state.hubLoadedSkills = state.hubLoadedSkills || [];
  }
}

async function loadSoulRoles() {
  try {
    const data = await api("/api/soul");
    state.soulRoles = data.core_roles || [];
    state.activeSoul = data.active_role || state.activeSoul || "office";
    // If legacy Hermes identity still on disk, seed Agent Hub soul once
    const content = data.content || "";
    if (!data.exists || /Hermes ALI|Hermes Identity|You are Hermes/i.test(content)) {
      try {
        await api("/api/soul", { method: "POST", body: JSON.stringify({ seed: true }) });
        const again = await api("/api/soul");
        state.soulRoles = again.core_roles || state.soulRoles;
        state.activeSoul = again.active_role || state.activeSoul;
      } catch (_) {}
    }
  } catch (_) {
    state.soulRoles = [];
  }
  renderSoulSelect();
}

function renderSoulSelect() {
  const sel = $("#soul-select");
  if (!sel) return;
  const langZh = state.prefs.language !== "en";
  const roles = state.soulRoles || [];
  sel.innerHTML = roles.map((r) => {
    const label = langZh ? (r.label || r.id) : (r.label_en || r.label || r.id);
    return `<option value="${escapeHtml(r.id)}" ${r.id === state.activeSoul ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("") || `<option value="office">office</option>`;
  sel.value = state.activeSoul || "office";
  updateComposerAdvSummary();
}

async function setActiveSoul(roleId) {
  roleId = (roleId || "").trim();
  if (!roleId) return;
  state.activeSoul = roleId;
  try {
    const res = await api("/api/soul/role", { method: "POST", body: JSON.stringify({ role: roleId }) });
    const sync = res && res.claw_sync;
    const rt = (res && res.runtime) || {};
    const claw = rt.runtime_resolved || (sync && sync.runtime) || "";
    if ($("#settings-status")) {
      const langZh = state.prefs.language !== "en";
      $("#settings-status").textContent = claw
        ? (langZh ? `Soul → ${roleId} · 已同步到 ${claw}` : `Soul → ${roleId} · synced to ${claw}`)
        : (langZh ? `Soul → ${roleId}` : `Soul → ${roleId}`);
    }
    try {
      const status = await api("/api/status");
      state.status = status;
      renderAgent(status);
      renderModeBanner(status);
    } catch (_) {}
  } catch (e) {
    console.warn(e);
  }
  renderSoulSelect();
}


function currentSkillCat() {
  const tax = (state.skillCatalog && state.skillCatalog.taxonomy) || [];
  return tax.find((c) => c.id === state.skillCat) || tax[0] || null;
}

function currentSkillSub() {
  const cat = currentSkillCat();
  if (!cat) return null;
  return (cat.subs || []).find((s) => s.id === state.skillSub) || (cat.subs || [])[0] || null;
}

function skillMetaById(id) {
  const tax = (state.skillCatalog && state.skillCatalog.taxonomy) || [];
  for (const cat of tax) {
    for (const sub of cat.subs || []) {
      const hit = (sub.skills || []).find((s) => s.id === id);
      if (hit) return { ...hit, category: cat.id, sub: sub.id };
    }
  }
  return { id, name: id, managed: true };
}

function renderSkillPicker() {
  const catSel = $("#skill-cat-select");
  const subSel = $("#skill-sub-select");
  const pickSel = $("#skill-pick-select");
  const row = $("#skill-selected");
  if (!catSel || !subSel || !pickSel || !row) return;
  const tax = (state.skillCatalog && state.skillCatalog.taxonomy) || [];
  const langZh = state.prefs.language !== "en";
  catSel.innerHTML = tax.map((c) =>
    `<option value="${escapeHtml(c.id)}" ${c.id === state.skillCat ? "selected" : ""}>${escapeHtml(langZh ? c.label : c.label_en)}</option>`
  ).join("");
  const cat = currentSkillCat();
  if (cat && !(cat.subs || []).some((s) => s.id === state.skillSub)) {
    state.skillSub = (cat.subs && cat.subs[0] && cat.subs[0].id) || "";
  }
  subSel.innerHTML = ((cat && cat.subs) || []).map((s) => {
    const n = (s.skills || []).length;
    return `<option value="${escapeHtml(s.id)}" ${s.id === state.skillSub ? "selected" : ""}>${escapeHtml(langZh ? s.label : s.label_en)} (${n})</option>`;
  }).join("");
  const sub = currentSkillSub();
  const skills = (sub && sub.skills) || [];
  pickSel.innerHTML = `<option value="">${escapeHtml(t("skills.pick"))}</option>` + skills.map((sk) => {
    const id = sk.id;
    const label = langZh ? (sk.label || sk.name || id) : (sk.name || sk.label || id);
    const used = state.selectedSkills.includes(id) ? " ✓" : "";
    return `<option value="${escapeHtml(id)}">${escapeHtml(label)}${used}</option>`;
  }).join("");

  if (!state.selectedSkills.length) {
    row.innerHTML = `<span class="muted">${escapeHtml(t("skills.none"))}</span>`;
  } else {
    row.innerHTML = state.selectedSkills.map((id) => {
      const meta = skillMetaById(id);
      const label = langZh ? (meta.label || meta.name || id) : (meta.name || meta.label || id);
      return `<span class="skill-tag" data-skill="${escapeHtml(id)}">
        <span>${escapeHtml(label)}</span>
        <button type="button" class="rm-skill" title="${escapeHtml(t("skills.remove"))}" aria-label="remove">×</button>
      </span>`;
    }).join("");
    row.querySelectorAll(".rm-skill").forEach((btn) => {
      btn.onclick = () => {
        const id = btn.closest(".skill-tag")?.dataset?.skill;
        if (!id) return;
        state.selectedSkills = state.selectedSkills.filter((x) => x !== id);
        renderSkillPicker();
      };
    });
  }
  updateComposerAdvSummary();
}

function addPickedSkill() {
  const id = ($("#skill-pick-select") && $("#skill-pick-select").value) || "";
  if (!id) return;
  if (!state.selectedSkills.includes(id)) state.selectedSkills = [...state.selectedSkills, id];
  renderSkillPicker();
}

function streamHintFromProgressLabel(label) {
  const map = {
    "match-skills": t("stream.hint.match"),
    "dispatch-agent": t("stream.hint.dispatch"),
    execute: t("stream.hint.execute"),
    summarize: t("stream.hint.summarize"),
  };
  return map[String(label || "").trim()] || "";
}

function resetWorkflowProgress(title) {
  const box = $("#stream-status");
  if (!box) return;
  box.classList.remove("hidden", "is-done", "is-outputting");
  const label = $("#stream-status-label");
  if (label) label.textContent = title || t("stream.running");
  const pctEl = $("#stream-status-pct");
  if (pctEl) pctEl.textContent = "0%";
  const fill = $("#stream-status-bar");
  if (fill) fill.style.width = "0%";
  const hint = $("#stream-status-hint");
  if (hint) hint.textContent = t("stream.hint.match");
  state.streamStatus = { pct: 0, phase: "thinking" };
}

function setWorkflowProgress(pct, _stepIndex, hint, phase) {
  const box = $("#stream-status");
  if (!box || box.classList.contains("hidden")) return;
  const p = Math.max(0, Math.min(100, Math.round(pct)));
  state.streamStatus = state.streamStatus || { pct: 0, phase: "thinking" };
  state.streamStatus.pct = p;
  if (phase) state.streamStatus.phase = phase;
  else if (p >= 50 && state.streamStatus.phase !== "done") state.streamStatus.phase = "outputting";
  const pctEl = $("#stream-status-pct");
  if (pctEl) pctEl.textContent = `${p}%`;
  const fill = $("#stream-status-bar");
  if (fill) fill.style.width = `${p}%`;
  const label = $("#stream-status-label");
  if (label) {
    const ph = state.streamStatus.phase;
    label.textContent = ph === "done" ? t("stream.done") : (ph === "outputting" ? t("stream.outputting") : t("stream.thinking"));
  }
  if (hint) {
    const hintEl = $("#stream-status-hint");
    if (hintEl) hintEl.textContent = String(hint);
  }
  box.classList.toggle("is-outputting", state.streamStatus.phase === "outputting");
  box.classList.toggle("is-done", state.streamStatus.phase === "done");
}

function finishWorkflowProgress(ok = true) {
  setWorkflowProgress(100, null, ok ? t("stream.done") : t("stream.running"), "done");
  setTimeout(() => {
    const box = $("#stream-status");
    if (box && !state.streaming) box.classList.add("hidden");
  }, 1200);
}

/** Model think / reasoning tags to hide from the main reply bubble. */
const MODEL_THINK_TAG = "think(?:ing)?|reasoning|redacted_reasoning|thought";

/**
 * Strip <think>…</think> (and common variants) from assistant text.
 * Also hides incomplete open tags mid-stream so partial tags never flash in the bubble.
 */
function stripModelThinkTags(text) {
  let s = String(text || "");
  const open = `<\\s*(?:${MODEL_THINK_TAG})\\b[^>]*>`;
  const close = `<\\s*\\/\\s*(?:${MODEL_THINK_TAG})\\s*>`;
  const pair = new RegExp(`${open}[\\s\\S]*?${close}`, "gi");
  let prev = "";
  while (s !== prev) {
    prev = s;
    s = s.replace(pair, "");
  }
  // Unclosed block: hide from open tag through end of buffer
  s = s.replace(new RegExp(`${open}[\\s\\S]*$`, "i"), "");
  // Trailing stub of an opening/closing tag (e.g. "<thi", "</think")
  const stub = s.match(/<\s*\/?\s*[A-Za-z_]{0,32}$/);
  if (stub) {
    const name = stub[0].replace(/^<\s*\/?\s*/i, "").toLowerCase();
    const names = ["think", "thinking", "reasoning", "redacted_reasoning", "thought"];
    if (!name || names.some((n) => n.startsWith(name))) {
      s = s.slice(0, -stub[0].length);
    }
  }
  return s;
}

function sanitizeWorkflowText(text) {
  let s = stripModelThinkTags(text);
  // Hermes reasoning boxes / banners
  s = s.replace(/┌─[\s\S]*?┐[\s\S]*?└─+┘/g, "");
  s = s.replace(/╭─[\s\S]*?╯/g, "");
  // Fake "orchestration dashboard" prose (LLM simulating Hub board in markdown)
  s = s.replace(/(?:^|\n)\s*(?:\*{0,2})?(?:🚀\s*)?Agent Hub\s*任务调度启动[\s\S]*?(?=(?:\n#{1,3}\s|\n📦|\n###\s|$))/gi, "\n");
  s = s.replace(/(?:^|\n)\s*\*+\(?\s*系统模拟实时状态更新[\s\S]*?(?=(?:\n#{1,3}\s|\n📦|\n###\s|$))/gi, "\n");
  s = s.replace(/(?:^|\n)\s*\[(?:⏳|⌛|✅|🔄)\s*(?:Pending|Completed|Processing|Waiting)\][^\n]*/gi, "");
  // Skill JSON payloads (model dumping tool calls as text)
  s = s.replace(/```(?:json|javascript|js)?\s*\{[\s\S]*?"skill"\s*:[\s\S]*?\}\s*```/gi, "");
  s = s.replace(/\{\s*"skill"\s*:\s*"[^"]+"[\s\S]*?\}/g, "");
  s = s.replace(/\{\s*"name"\s*:\s*"[^"]+"\s*,\s*"arguments"\s*:[\s\S]*?\}/g, "");
  // Collapse excess blank lines
  s = s.replace(/\n{3,}/g, "\n\n").trim();
  return s;
}

function ensureThinkingBlock(assistantEl) {
  if (!assistantEl) return null;
  let details = assistantEl.querySelector(".msg-thinking");
  if (!details) {
    details = document.createElement("details");
    details.className = "msg-thinking";
    details.hidden = true; // only show after meaningful lines
    details.open = true;
    details.innerHTML = `<summary>${escapeHtml(t("thinking.process"))}</summary><ul class="msg-thinking-body"></ul>`;
    const body = assistantEl.querySelector(".body");
    const lanes = assistantEl.querySelector(".msg-sublanes");
    if (lanes) assistantEl.insertBefore(details, lanes);
    else if (body) assistantEl.insertBefore(details, body);
    else assistantEl.appendChild(details);
  }
  return details.querySelector(".msg-thinking-body");
}

function isNoiseThinking(text) {
  const s = String(text || "").trim();
  if (!s) return true;
  if (s.length < 2) return true;
  return (
    /^跳过\s*Skill/i.test(s)
    || /^已跳过\s*Skill/i.test(s)
    || /^调度\s*Agent\b/i.test(s)
    || /^开始执行任务/i.test(s)
    || /^汇总交付/i.test(s)
    || /^Dispatch agent/i.test(s)
    || /^Skip(ped)?\s+skill/i.test(s)
    || /^Hermes Agent 启动/i.test(s)
    || /^OpenClaw Agent 启动/i.test(s)
    || /^正在生成回答/i.test(s)
    || /^思考中…?$/i.test(s)
    || /^启动 Agent/i.test(s)
    || /^Starting agent/i.test(s)
    || /^Thinking…?$/i.test(s)
    || /^Streaming output/i.test(s)
  );
}

function thinkingFromProgressLabel(label) {
  const mapZh = {
    "match-skills": "分析任务意图，匹配可用 Skill",
    "dispatch-agent": "选定执行引擎，调度模型",
    execute: "模型开始产出交付内容",
    summarize: "整理与校验最终交付",
  };
  const mapEn = {
    "match-skills": "Analyzing task & matching skills",
    "dispatch-agent": "Dispatching model runtime",
    execute: "Model producing deliverables",
    summarize: "Finalizing delivery",
  };
  const langZh = state.prefs.language !== "en";
  const key = String(label || "").trim();
  return (langZh ? mapZh : mapEn)[key] || "";
}

function appendThinking(assistantEl, text) {
  const chunk = String(text || "").trim();
  if (!chunk || !assistantEl || isNoiseThinking(chunk)) return;
  const body = ensureThinkingBlock(assistantEl);
  if (!body) return;
  const details = assistantEl.querySelector(".msg-thinking");
  if (details) {
    details.hidden = false;
    details.open = true;
  }
  // Dedupe consecutive identical items
  const last = body.querySelector(".msg-thinking-line:last-child");
  if (last && (last.textContent || "").trim() === chunk) return;
  // Cap length to keep UI snappy
  const lines = body.querySelectorAll(".msg-thinking-line");
  if (lines.length >= 40) lines[0].remove();
  const line = document.createElement("li");
  line.className = "msg-thinking-line";
  line.textContent = chunk;
  body.appendChild(line);
  body.scrollTop = body.scrollHeight;
  const hint = $("#stream-status-hint");
  if (hint && !$("#stream-status")?.classList.contains("hidden")) {
    hint.textContent = chunk.length > 120 ? `${chunk.slice(0, 117)}…` : chunk;
  }
  const messages = $("#messages");
  if (messages) messages.scrollTop = messages.scrollHeight;
}

function collapseThinking(assistantEl) {
  const details = assistantEl && assistantEl.querySelector(".msg-thinking");
  if (!details) return;
  const body = details.querySelector(".msg-thinking-body");
  const lines = body ? Array.from(body.querySelectorAll(".msg-thinking-line")) : [];
  const meaningful = lines.filter((el) => !isNoiseThinking(el.textContent || ""));
  if (!meaningful.length) {
    details.remove();
    return;
  }
  // Drop leftover noise lines
  lines.forEach((el) => {
    if (isNoiseThinking(el.textContent || "")) el.remove();
  });
  details.hidden = false;
  details.open = false;
}

function messageImpliesSkills(text) {
  const s = String(text || "");
  return /(?:\bskills?\b|skill\.md|claude\s*skill|codex\s*skill|技能|调用技能|使用技能|匹配技能|加载技能|安装技能|用\s*skill|跑\s*skill|启用\s*skill)/i.test(s);
}

function detectSkillCallFromText(chunk) {
  const m = String(chunk || "").match(/"skill"\s*:\s*"([^"]+)"/);
  return m ? m[1] : "";
}

async function autoMatchSkills(text) {
  try {
    const data = await api("/api/skills/suggest", {
      method: "POST",
      body: JSON.stringify({ message: text || $("#input")?.value || "" }),
    });
    state.selectedSkills = (data.skills || []).map((s) => s.id).filter(Boolean);
    if (data.skills && data.skills[0]) {
      state.skillCat = data.skills[0].category || state.skillCat;
      state.skillSub = data.skills[0].sub || state.skillSub;
    }
    renderSkillPicker();
  } catch (e) {
    console.warn(e);
  }
}

async function ensureAgentRuntime() {
  // Cache Control Center runtime prefs only — never force Hermes over a
  // user-connected claw or ali.auto_runtime preference.
  try {
    const rt = await api("/api/runtimes");
    state.runtime = {
      active: rt.active || "auto",
      auto_runtime: rt.auto_runtime || "hermes",
      resolved: rt.resolved || "direct",
      linked: rt.linked || rt.resolved || "direct",
    };
  } catch (_) {}
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  state.liveModels = (((state.settings || {}).model_options || {}).options || [])
    .filter((item) => item && item.source === "fetched")
    .map((item) => item.model);
  if (state.settings.config && state.settings.config.workspace) {
    $("#workspace-input").value = state.settings.config.workspace;
  }
  syncComposerFromSettings();
}

function sharedModelOptions(extra = [], payloadOverride = null) {
  const payload = payloadOverride || (state.settings && state.settings.model_options) || {};
  const configured = Array.isArray(payload.options) ? payload.options : [];
  const out = [];
  const seen = new Set();
  [...configured, ...(extra || [])].forEach((raw) => {
    const item = typeof raw === "string" ? { model: raw } : (raw || {});
    const provider = String(
      Object.prototype.hasOwnProperty.call(item, "provider") ? item.provider : (payload.provider || "")
    ).trim();
    const model = String(item.model || item.id || "").trim();
    if (!model) return;
    const key = `${provider}\n${model}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({
      provider,
      model,
      available: item.available !== false,
      source: item.source || "configured",
    });
  });
  return out;
}

function modelBindingValue(provider, model) {
  if (!model) return "";
  return `${encodeURIComponent(provider || "")}::${encodeURIComponent(model)}`;
}

function parseModelBinding(value) {
  const raw = String(value || "");
  if (!raw) return { provider: "", model: "" };
  const at = raw.indexOf("::");
  if (at < 0) return { provider: "", model: raw };
  try {
    return {
      provider: decodeURIComponent(raw.slice(0, at)),
      model: decodeURIComponent(raw.slice(at + 2)),
    };
  } catch (_) {
    return { provider: "", model: raw.slice(at + 2) };
  }
}

function normalizeAgentRoute(value) {
  const raw = String(value || "").trim();
  if (!raw) return "auto";
  return ({
    auto: "auto", inherit: "auto",
    simple: "C0", fast: "C0", c0: "C0",
    office: "C1", main: "C1", c1: "C1",
    c2: "C2",
    reasoning: "C3", reason: "C3", c3: "C3",
    vision: "Vision",
  })[raw.toLowerCase()] || raw;
}

function modelBindingOptions(selectedProvider, selectedModel, {
  allowAuto = false, autoLabel = "", modelPayload = null,
} = {}) {
  const current = {
    provider: String(selectedProvider || "").trim(),
    model: String(selectedModel || "").trim(),
    available: false,
    source: "configured",
  };
  const options = sharedModelOptions(current.model ? [current] : [], modelPayload);
  const selectedValue = modelBindingValue(current.provider, current.model);
  const auto = allowAuto
    ? `<option value="" ${!current.model ? "selected" : ""}>${escapeHtml(autoLabel || "Auto")}</option>`
    : "";
  return auto + options.map((item) => {
    const value = modelBindingValue(item.provider, item.model);
    const stale = item.available === false ? (state.prefs.language === "en" ? " · unavailable (kept)" : " · 已不在目录（保留）") : "";
    const label = `${item.provider ? item.provider + " · " : ""}${item.model}${stale}`;
    return `<option value="${escapeHtml(value)}" ${value === selectedValue ? "selected" : ""}>${escapeHtml(label)}</option>`;
  }).join("");
}

function modelIdOptions(selectedModel, provider = "") {
  const selected = String(selectedModel || "").trim();
  const entries = sharedModelOptions(selected ? [{
    provider,
    model: selected,
    available: false,
    source: "configured",
  }] : []).filter((item) => !provider || item.provider === provider || !item.provider);
  return entries.map((item) => {
    const stale = item.available === false ? (state.prefs.language === "en" ? " · unavailable (kept)" : " · 已不在目录（保留）") : "";
    return `<option value="${escapeHtml(item.model)}" ${item.model === selected ? "selected" : ""}>${escapeHtml(item.model + stale)}</option>`;
  }).join("") || `<option value="${escapeHtml(selected)}">${escapeHtml(selected || "—")}</option>`;
}

function modelChoicesFromSettings() {
  const cfg = (state.settings && state.settings.config) || {};
  const models = cfg.models || {};
  const backendType = ((cfg.backend || {}).type || "").trim();
  const ids = [];
  ["main", "fast", "vision", "reasoning", "qwen_main", "qwen_fast", "qwen_vl", "deepseek_reasoning"].forEach((k) => {
    if (models[k]) ids.push(models[k]);
  });
  sharedModelOptions().forEach((item) => ids.push(item.model));
  Object.values(models).forEach((m) => { if (m) ids.push(m); });
  const sug = (state.settings && state.settings.model_suggestions) || {};
  Object.values(sug).forEach((arr) => {
    if (Array.isArray(arr)) arr.forEach((m) => ids.push(m));
  });
  const all = [...new Set(ids.filter(Boolean))];
  // Filter out foreign vendor ids so composer can't re-select NVIDIA deepseek-ai/*
  // while backend is official DeepSeek (that path used to 503 on integrate.api.nvidia.com).
  if (backendType === "deepseek") {
    return all
      .map((id) => (String(id).includes("/") ? String(id).split("/").pop() : String(id)))
      .filter((id) => {
        const s = id.toLowerCase();
        if (s.startsWith("nvidia/") || s.startsWith("meta/") || s.startsWith("google/")) return false;
        if (s.startsWith("deepseek-ai/")) return false;
        return s.includes("deepseek") || s === "deepseek-chat" || s === "deepseek-reasoner";
      });
  }
  if (backendType === "nvidia-nim") {
    return all.filter((id) => String(id).includes("/") || String(id).startsWith("nvidia"));
  }
  return all;
}

function syncRouteLabels() {
  const cfg = (state.settings && state.settings.config) || {};
  const models = cfg.models || {};
  const fast = SHORT_MODEL(models.fast || models.qwen_fast || "");
  const main = SHORT_MODEL(models.main || models.qwen_main || "");
  const vision = SHORT_MODEL(models.vision || models.qwen_vl || "");
  const reason = SHORT_MODEL(models.reasoning || models.deepseek_reasoning || "");
  const sel = $("#route-select");
  if (!sel) return;
  const map = {
    auto: state.prefs.language === "zh" ? "Auto（自动分级）" : "Auto",
    simple: `C0 · ${fast || "fast"}`,
    office: `C1 · ${main || "main"}`,
    C2: `C2 · ${main || "main"}+review`,
    reasoning: `C3 · ${reason || "reasoning"}`,
    vision: `Vision · ${vision || "vision"}`,
    agent: state.prefs.language === "zh" ? `Agent · ${main || "main"}` : `Agent · ${main || "main"}`,
  };
  Array.from(sel.options).forEach((opt) => {
    if (map[opt.value]) opt.textContent = map[opt.value];
  });
}

function syncComposerFromSettings() {
  const cfg = (state.settings && state.settings.config) || {};
  const ali = cfg.ali || {};
  const modeSel = $("#chat-mode-select");
  if (modeSel) modeSel.value = ali.chat_mode === "single" ? "single" : "auto";
  syncRouteLabels();
  populateModelSelect(ali.last_model || modelsMain(cfg) || "");
  const depthSel = $("#thinking-depth-select");
  if (depthSel) {
    const depth = normalizeThinkingDepth(
      ali.thinking_depth || state.prefs.thinkingDepth || localStorage.getItem("hermes_ali_thinking_depth") || "medium"
    );
    depthSel.value = depth;
    state.prefs.thinkingDepth = depth;
  }
  const hubSel = $("#hub-chat-mode-select");
  if (hubSel) {
    const hubMode = ali.hub_chat_mode === "direct" ? "direct" : "agent";
    hubSel.value = hubMode;
  }
  updateModeUi();
}

function modelsMain(cfg) {
  const m = (cfg && cfg.models) || {};
  return m.main || m.qwen_main || "";
}

function populateModelSelect(selected) {
  const sel = $("#model-select");
  if (!sel) return;
  const choices = modelChoicesFromSettings();
  const cur = selected || sel.value || "";
  if (cur && !choices.includes(cur)) choices.unshift(cur);
  sel.innerHTML = choices.map((id) =>
    `<option value="${escapeHtml(id)}" ${id === cur ? "selected" : ""}>${escapeHtml(SHORT_MODEL(id))}</option>`
  ).join("") || `<option value="">—</option>`;
  if (cur) sel.value = cur;
  updateComposerAdvSummary();
}

function updateModeUi() {
  const mode = ($("#chat-mode-select") && $("#chat-mode-select").value) || "auto";
  const route = $("#route-select");
  const model = $("#model-select");
  if (route) route.disabled = mode === "single";
  if (model) model.disabled = false;
}

async function persistChatModeAndModel() {
  try {
    // Always reload from server — never POST a stale state.settings that can
    // revive NVIDIA hybrid backend after the user switched to DeepSeek.
    const view = await api("/api/settings");
    const cfg = JSON.parse(JSON.stringify((view && view.config) || {}));
    if (!cfg.ali) cfg.ali = {};
    cfg.ali.chat_mode = ($("#chat-mode-select") && $("#chat-mode-select").value) || "auto";
    let lastModel = ($("#model-select") && $("#model-select").value) || "";
    const backendType = ((cfg.backend || {}).type || "").trim();
    // Strip NVIDIA org prefix when backend is official DeepSeek
    if (backendType === "deepseek" && lastModel.includes("/")) {
      lastModel = lastModel.split("/").pop() || lastModel;
    }
    if (backendType === "deepseek" && lastModel.startsWith("deepseek-ai/")) {
      lastModel = lastModel.replace(/^deepseek-ai\//, "");
    }
    cfg.ali.last_model = lastModel;
    cfg.ali.default_route = ($("#route-select") && $("#route-select").value) || "auto";
    cfg.ali.thinking_depth = normalizeThinkingDepth(
      ($("#thinking-depth-select") && $("#thinking-depth-select").value) || state.prefs.thinkingDepth || "medium"
    );
    const hubSel = $("#hub-chat-mode-select");
    cfg.ali.hub_chat_mode = (hubSel && hubSel.value === "direct") ? "direct" : "agent";
    cfg.ali.hub_fast_chat = cfg.ali.hub_chat_mode === "direct";
    // Concrete backend must stay single (don't resurrect hybrid from old UI memory)
    if (backendType && backendType !== "hybrid") cfg.mode = "single";
    state.prefs.thinkingDepth = cfg.ali.thinking_depth;
    persistPrefsLocal();
    const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg }) });
    state.settings = data;
    if (lastModel && $("#model-select") && $("#model-select").value !== lastModel) {
      populateModelSelect(lastModel);
    }
  } catch (_) {}
}

async function createSession() {
  const langZh = state.prefs.language !== "en";
  const btn = $("#btn-new");
  if (btn) {
    btn.disabled = true;
    btn.setAttribute("aria-busy", "true");
  }
  try {
    const s = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title: t("chat.new") }),
    });
    if (!s || !s.id) throw new Error(langZh ? "创建失败：无会话 ID" : "Create failed: no session id");
    await refreshSessions();
    await selectSession(s.id);
    setSidebarOpen(false);
    $("#input")?.focus();
    return s;
  } catch (err) {
    console.error(err);
    alert(langZh ? `无法创建新任务：${err.message || err}` : `Cannot create task: ${err.message || err}`);
    throw err;
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.removeAttribute("aria-busy");
    }
  }
}

async function deleteSession(id) {
  await api(`/api/sessions/${id}`, { method: "DELETE" });
  if (state.currentId === id) {
    state.currentId = null;
    $("#messages").innerHTML = "";
    $("#chat-title").textContent = t("chat.new");
  }
  await refreshSessions();
  if (!state.currentId && state.sessions.length) await selectSession(state.sessions[0].id);
  else if (!state.sessions.length) await createSession();
}

async function selectSession(id) {
  if (!id) return;
  // Never land the UI on a hidden lane child — jump to its parent if known
  const run = state.sessionRuns[id];
  if (run && run.parentId) {
    id = run.parentId;
  } else if (!state.sessions.some((s) => s.id === id)) {
    // Hidden session id from an old chip — refuse and stay
    const parentHit = Object.entries(state.multiLaneChildren || {}).find(([, kids]) =>
      (kids || []).some((k) => k.childId === id)
    );
    if (parentHit) id = parentHit[0];
    else return;
  }

  // Optimistic highlight so switching feels instant even if API is slow
  const prevId = state.currentId;
  if (prevId === id) {
    setSidebarOpen(false);
    return;
  }
  state.currentId = id;
  renderSessionList();
  renderActiveRuns({ force: true });
  updateSendEnabled();

  // Instant paint from live buffer while history loads (no freeze waiting on API)
  const live = state.streamBuffers[id];
  if (live && (live.rawBuf || live.full || live.orchPlan) && state.sessionRuns[id]?.streaming) {
    if (!$("#messages .msg")) {
      appendMessage({ role: "assistant", content: live.full || live.rawBuf || "", route: live.route });
      if (live.orchPlan) restoreLiveMultiOrch(id);
      else paintStreamBuffer(id, { force: true });
    }
    resetWorkflowProgress(t("stream.running"));
    setWorkflowProgress(state.sessionRuns[id].pct || 30, null, t("stream.hint.execute"), "outputting");
  }

  try {
    const s = await api(`/api/sessions/${id}`);
    if (state.currentId !== id) return; // user switched again
    $("#chat-title").textContent = sessionDisplayTitle(s);
    renderMessages(s.messages || []);

    // Rehydrate live multi-subagent board after history wipe
    if (state.sessionRuns[id]?.multi || state.streamBuffers[id]?.orchPlan) {
      restoreLiveMultiOrch(id);
      resetWorkflowProgress(t("stream.running"));
      setWorkflowProgress(state.sessionRuns[id]?.pct || 30, null, t("orch.modeParallel"), "thinking");
    }

    // Rebind paint target to fresh DOM when a consumer is already running
    if (state.streamConsumers[id]) {
      const bag = getStreamBuffer(id);
      const { assistantEl, bodyEl } = resolveLiveAssistant(id);
      let a = assistantEl;
      let b = bodyEl;
      const lastMsg = $("#messages .msg:last-child");
      if (!lastMsg || lastMsg.classList.contains("user")) {
        a = appendMessage({ role: "assistant", content: "", route: bag.route || (s.active_job && s.active_job.route) });
        b = a.querySelector(".body");
      }
      bag.assistantEl = a;
      bag.bodyEl = b;
      if (bag.orchPlan) restoreLiveMultiOrch(id);
      else paintStreamBuffer(id, { force: true });
      resetWorkflowProgress(t("stream.running"));
      setWorkflowProgress(state.sessionRuns[id]?.pct || 30, null, t("stream.hint.execute"), "outputting");
      if (bag.route) {
        setRouteBadge(bag.route);
        renderEngineBadge(state.streamMeta, bag.route);
      }
    } else if (!(state.sessionRuns[id]?.multi || state.streamBuffers[id]?.orchPlan)) {
      const job = s.active_job || (state.sessionRuns[id] && state.sessionRuns[id].streamId
        ? { stream_id: state.sessionRuns[id].streamId, pct: state.sessionRuns[id].pct, status: "running", route: state.sessionRuns[id].route }
        : null);
      if (job && job.status === "running" && (job.stream_id || state.sessionRuns[id]?.streamId)) {
        resumeSessionStream(id, job).catch(() => {});
      } else if (state.sessionRuns[id]?.streaming) {
        resetWorkflowProgress(t("stream.running"));
        setWorkflowProgress(state.sessionRuns[id].pct || 30, null, t("stream.hint.execute"), "outputting");
      } else {
        const box = $("#stream-status");
        if (box) box.classList.add("hidden");
      }
    }
    $("#input")?.focus();
  } catch (err) {
    state.currentId = prevId;
    renderSessionList();
    renderActiveRuns({ force: true });
    throw err;
  }
}

function renderMessages(messages) {
  const box = $("#messages");
  box.innerHTML = "";
  if (!messages.length) {
    box.innerHTML = `<div class="empty-state" id="empty-state">
      <img class="empty-logo-img" src="${logoSrc("empty")}" alt="深圳理工大学" />
      <h3 data-i18n="empty.title">${escapeHtml(t("empty.title"))}</h3>
      <p data-i18n-html="empty.body">${t("empty.body")}</p>
    </div>`;
    applyBrandLogos();
    return;
  }
  messages.forEach((m) => appendMessage(m, false));
  box.scrollTop = box.scrollHeight;
}

function appendMessage(m, scroll = true) {
  const empty = $("#empty-state");
  if (empty) empty.remove();
  const div = document.createElement("div");
  div.className = `msg ${m.role || "assistant"}${m.error ? " error" : ""}`;
  if (m.id) div.dataset.mid = m.id;
  const role = m.role === "user" ? "You" : "Agent Hub";
  let route = "";
  if (m.route && m.route.tier) {
    route = ` · ${m.route.tier}/${m.route.route_key || ""}${m.route.model ? " · " + m.route.model : ""}`;
  }
  if (m.route && m.route.subagent_label) {
    route += ` · ${m.route.subagent_label}`;
  }
  if (m.route && m.route.multi_subagents) {
    const n = m.route.lane_count || (m.route.lanes && m.route.lanes.length) || 0;
    const models = (m.route.lanes || [])
      .map((l) => [l.tier, l.model].filter(Boolean).join("·"))
      .filter(Boolean)
      .join(" / ");
    route += n ? ` · ${n}${state.prefs.language !== "en" ? "路并行" : " lanes"}` : "";
    if (models) route += ` · ${models}`;
  }
  const elapsed = m.elapsed_ms != null ? m.elapsed_ms : null;
  if (elapsed != null && m.role === "assistant") {
    const label = state.prefs.language !== "en"
      ? `${t("msg.elapsed")} ${formatElapsed(elapsed)}`
      : formatElapsed(elapsed);
    route += ` · ${label}`;
  }
  let tools = "";
  if (m.tools && m.tools.length) {
    tools = `<div class="tools">${m.tools
      .map((x) => `⚙ ${escapeHtml(x.name)} — ${escapeHtml(x.preview || "")}`)
      .join("<br>")}</div>`;
  }
  let handoff = "";
  if (m.role === "assistant" && m.route && m.route.subagent_label) {
    const langZh = state.prefs.language !== "en";
    const auto = m.route.subagent_auto ? (langZh ? "自动匹配" : "auto") : (langZh ? "指定" : "pinned");
    handoff = `<div class="msg-handoff"><span class="handoff-tag">${escapeHtml(langZh ? "子代理" : "Subagent")}</span> ${escapeHtml(m.route.subagent_label)} · ${escapeHtml(auto)}</div>`;
  }
  const fb = (m.feedback && m.feedback.rating) || 0;
  const actions = `<div class="msg-actions">
    <button type="button" class="btn ghost chip msg-act" data-act="copy" data-i18n="msg.copy">${escapeHtml(t("msg.copy"))}</button>
    <button type="button" class="btn ghost chip msg-act" data-act="quote" data-i18n="msg.quote">${escapeHtml(t("msg.quote"))}</button>
    ${m.role === "assistant" ? `
      <button type="button" class="btn ghost chip msg-act" data-act="revise" data-i18n="msg.revise">${escapeHtml(t("msg.revise"))}</button>
      <button type="button" class="btn ghost chip msg-act ${fb === 1 || fb >= 4 ? "active" : ""}" data-act="up" data-i18n-title="msg.good" title="${escapeHtml(t("msg.good"))}">👍</button>
      <button type="button" class="btn ghost chip msg-act ${fb === -1 || fb === 2 ? "active" : ""}" data-act="down" data-i18n-title="msg.bad" title="${escapeHtml(t("msg.bad"))}">👎</button>
    ` : ""}
  </div>`;
  div.innerHTML = `<div class="meta">${role}${escapeHtml(route)}</div>${handoff}<div class="body">${
    m.role === "user"
      ? escapeHtml(m.content || "").replace(/\n/g, "<br>")
      : renderMd(sanitizeWorkflowText(m.content || ""))
  }</div>${tools}${actions}`;
  div.querySelectorAll(".msg-act").forEach((btn) => {
    btn.addEventListener("click", () => handleMsgAction(div, m, btn.dataset.act));
  });
  if (m.role !== "user") bindCodeBoxActions(div);
  $("#messages").appendChild(div);
  if (m.role === "assistant" && m.route && m.route.multi_subagents) {
    restoreOrchFromRoute(div, m.route, m.content || "");
  }
  if (scroll) $("#messages").scrollTop = $("#messages").scrollHeight;
  return div;
}

async function handleMsgAction(el, m, act) {
  if (act === "cancel-edit") {
    const edit = el.querySelector(".msg-prose-edit");
    if (edit) edit.classList.add("hidden");
    return;
  }
  if (act === "submit-edit") {
    const edit = el.querySelector(".msg-prose-edit");
    const ta = edit && edit.querySelector(".msg-prose-ta");
    const orig = (edit && edit.dataset.orig) || "";
    const modified = ta ? ta.value : "";
    const fromSelection = !!(edit && edit.dataset.fromSelection === "1");
    insertIntoComposer(buildProseReviseComposerText(orig, modified, fromSelection));
    if (edit) edit.classList.add("hidden");
    return;
  }

  const payload = getMsgActionPayload(el, m);
  const text = payload.text;

  if (act === "copy") {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const tmp = document.createElement("textarea");
      tmp.value = text;
      document.body.appendChild(tmp);
      tmp.select();
      document.execCommand("copy");
      tmp.remove();
    }
    const btn = el.querySelector('[data-act="copy"]');
    if (btn) {
      btn.textContent = "✓";
      setTimeout(() => { if (btn) btn.textContent = t("msg.copy"); }, 1200);
    }
    return;
  }

  if (act === "quote") {
    if (!text.trim()) return;
    insertIntoComposer(buildQuoteComposerText(text.trim()));
    return;
  }

  if (act === "revise") {
    if (!text.trim()) return;
    const edit = ensureMsgProseEdit(el, m);
    const ta = edit.querySelector(".msg-prose-ta");
    edit.dataset.orig = text;
    edit.dataset.fromSelection = payload.fromSelection ? "1" : "0";
    if (ta) {
      ta.value = text;
      edit.classList.remove("hidden");
      ta.focus();
      try { ta.setSelectionRange(0, ta.value.length); } catch (_) {}
    }
    return;
  }

  if (act !== "up" && act !== "down") return;
  if (!state.currentId) return;
  let mid = m.id || el.dataset.mid;
  if (!mid) {
    mid = `local-${Date.now()}`;
    el.dataset.mid = mid;
  }
  const rating = act === "up" ? 1 : -1;
  const previewSrc = m.content || text;
  try {
    await api("/api/feedback", {
      method: "POST",
      body: JSON.stringify({
        session_id: state.currentId,
        message_id: mid,
        rating,
        model: (m.route && m.route.model) || "",
        content_preview: String(previewSrc || "").slice(0, 400),
      }),
    });
    el.querySelectorAll('[data-act="up"],[data-act="down"]').forEach((b) => b.classList.remove("active"));
    const b = el.querySelector(`[data-act="${act}"]`);
    if (b) b.classList.add("active");
  } catch (e) {
    console.warn(e);
  }
}

function renderAttachBar() {
  const bar = $("#attach-bar");
  if (!bar) return;
  if (!state.pendingFiles.length) {
    bar.classList.add("hidden");
    bar.innerHTML = "";
    return;
  }
  bar.classList.remove("hidden");
  bar.innerHTML = state.pendingFiles.map((f, i) =>
    `<span class="attach-chip">${escapeHtml(f.relative || f.name)} <button type="button" data-i="${i}">×</button></span>`
  ).join("") + `<button type="button" class="btn ghost chip" id="btn-clear-attach">${escapeHtml(t("attach.clear"))}</button>`;
  bar.querySelectorAll("[data-i]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.pendingFiles.splice(Number(btn.dataset.i), 1);
      renderAttachBar();
    });
  });
  const clear = $("#btn-clear-attach");
  if (clear) clear.onclick = () => { state.pendingFiles = []; renderAttachBar(); };
}

async function uploadSelectedFiles(fileList, { folder = false } = {}) {
  if (!fileList || !fileList.length || !state.currentId) return;
  const fd = new FormData();
  fd.append("session_id", state.currentId);
  fd.append("into_workspace", "0");
  const names = [];
  Array.from(fileList).forEach((file) => {
    const rel = file.webkitRelativePath || file.name;
    fd.append("file", file, rel);
    names.push(rel);
  });
  try {
    const headers = {};
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    const res = await fetch("/api/uploads", { method: "POST", headers, body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || t("upload.fail"));
    (data.files || []).forEach((f, i) => {
      state.pendingFiles.push({ name: names[i] || f.relative, relative: f.relative, path: f.path });
    });
    renderAttachBar();
    const note = `${t("upload.ok")}: ${(data.files || []).map((f) => f.relative).join(", ")}`;
    appendMessage({ role: "assistant", content: note });
  } catch (e) {
    appendMessage({ role: "assistant", content: `${t("upload.fail")}: ${e.message || e}`, error: true });
  }
}

function renderSubagentBar() {
  // Legacy top chip-wall disabled — use composer picker instead
  const bar = $("#subagent-bar");
  if (bar) {
    bar.classList.add("hidden");
    bar.innerHTML = "";
    bar.hidden = true;
  }
  renderSubagentPicker();
  applyChatLayout();
}

function availableSubagents() {
  const ag = state.agents;
  return ((ag && ag.subagents) || []).filter((s) => s.enabled !== false);
}

function renderSubagentPicker() {
  const pick = $("#subagent-pick-select");
  const row = $("#subagent-selected");
  const picker = $("#subagent-picker");
  if (!pick || !row) return;
  const langZh = state.prefs.language !== "en";
  const subs = availableSubagents();
  if (picker) picker.classList.toggle("hidden", !subs.length && !state.selectedSubagents.length);

  pick.innerHTML = `<option value="">${escapeHtml(t("sub.pick"))}</option>` + subs.map((s) => {
    const label = langZh ? (s.label || s.id) : (s.label_en || s.label || s.id);
    const used = state.selectedSubagents.includes(s.id) ? " ✓" : "";
    return `<option value="${escapeHtml(s.id)}">${escapeHtml(label)}${used}</option>`;
  }).join("");

  if (!state.selectedSubagents.length) {
    row.innerHTML = `<span class="muted">${escapeHtml(t("sub.none"))}</span>`;
    state.activeSubagent = "";
    updateComposerAdvSummary();
    return;
  }
  // Keep active pointing at a selected id
  if (!state.selectedSubagents.includes(state.activeSubagent)) {
    state.activeSubagent = state.selectedSubagents[state.selectedSubagents.length - 1] || "";
  }
  row.innerHTML = state.selectedSubagents.map((id) => {
    const s = subs.find((x) => x.id === id) || ((state.agents && state.agents.subagents) || []).find((x) => x.id === id) || { id, label: id };
    const label = langZh ? (s.label || id) : (s.label_en || s.label || id);
    const active = state.activeSubagent === id;
    return `<span class="skill-tag ${active ? "active-sub" : ""}" data-sub="${escapeHtml(id)}">
      <button type="button" class="sub-activate" title="active">${escapeHtml(label)}${active ? " · ✓" : ""}</button>
      <button type="button" class="rm-sub" title="${escapeHtml(t("sub.remove"))}" aria-label="remove">×</button>
    </span>`;
  }).join("");
  row.querySelectorAll(".sub-activate").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.closest("[data-sub]")?.dataset?.sub || "";
      state.activeSubagent = id;
      renderSubagentPicker();
      applyChatLayout();
    };
  });
  row.querySelectorAll(".rm-sub").forEach((btn) => {
    btn.onclick = () => {
      const id = btn.closest("[data-sub]")?.dataset?.sub;
      if (!id) return;
      state.selectedSubagents = state.selectedSubagents.filter((x) => x !== id);
      if (state.activeSubagent === id) state.activeSubagent = state.selectedSubagents[0] || "";
      renderSubagentPicker();
      applyChatLayout();
    };
  });
  updateComposerAdvSummary();
}

function addPickedSubagent() {
  const id = ($("#subagent-pick-select") && $("#subagent-pick-select").value) || "";
  if (!id) return;
  if (!state.selectedSubagents.includes(id)) {
    state.selectedSubagents = [...state.selectedSubagents, id];
  }
  state.activeSubagent = id;
  renderSubagentPicker();
  applyChatLayout();
}

function applyChatLayout() {
  const panes = $("#chat-panes");
  const pane = $("#subagent-pane");
  const ag = state.agents;
  const layout = (ag && ag.ui && ag.ui.layout) || "tabs";
  const selected = state.selectedSubagents || [];
  const active = state.activeSubagent && selected.includes(state.activeSubagent)
    ? state.activeSubagent
    : (selected[0] || "");
  // Show side panel when multiple subagents are selected (parallel lanes) or split layout
  const showPane = selected.length > 1 || (layout === "split" && !!active);
  if (panes) panes.classList.toggle("split", showPane);
  if (!pane) return;
  if (!showPane) {
    pane.classList.add("hidden");
    return;
  }
  pane.classList.remove("hidden");
  const langZh = state.prefs.language !== "en";
  const catalog = (ag && ag.subagents) || [];
  const lanes = selected.map((id) => catalog.find((s) => s.id === id) || { id, label: id });
  const running = Object.entries(state.sessionRuns).filter(([, r]) => r && r.streaming);
  $("#subagent-pane-title").textContent = langZh
    ? (lanes.length > 1 ? `并行子代理 (${lanes.length})` : (lanes[0].label || "Subagent"))
    : (lanes.length > 1 ? `Parallel agents (${lanes.length})` : (lanes[0].label_en || lanes[0].label || "Subagent"));
  const laneHtml = lanes.map((sub) => {
    const isActive = sub.id === state.activeSubagent;
    const label = langZh ? (sub.label || sub.id) : (sub.label_en || sub.label || sub.id);
    const runHint = running
      .filter(([, r]) => r.subagent_label && (r.subagent_label === sub.label || r.subagent_label === sub.id))
      .map(([sid, r]) => {
        const sess = state.sessions.find((s) => s.id === sid);
        return `${sess ? sessionDisplayTitle(sess) : sid.slice(0, 6)} ${Math.round(r.pct || 0)}%`;
      });
    return `<div class="subagent-lane${isActive ? " active" : ""}" data-sub="${escapeHtml(sub.id)}">
      <strong>${escapeHtml(label)}</strong>
      <div class="muted">${escapeHtml(sub.desc || "")}</div>
      <div class="muted">role: <code>${escapeHtml(sub.role || "")}</code></div>
      ${runHint.length ? `<div class="lane-run">${escapeHtml(langZh ? "执行中：" : "Running: ")}${escapeHtml(runHint.join(" · "))}</div>` : ""}
      <div class="muted">${langZh
        ? "切换到当前角色后发送，或开「新任务」让多会话并行。"
        : "Activate then send, or open New chat for parallel sessions."}</div>
    </div>`;
  }).join("");
  const handoff = lanes.length > 1
    ? `<p class="handoff-hint">${langZh
      ? "跨区传递：在当前子代理任务完成后，切到另一个子代理标签并粘贴/引用上一段结论即可衔接。"
      : "Handoff: after one agent finishes, switch tag and paste/reference its conclusion."}</p>`
    : "";
  $("#subagent-pane-body").innerHTML = handoff + laneHtml;
  pane.querySelectorAll(".subagent-lane[data-sub]").forEach((el) => {
    el.addEventListener("click", () => {
      state.activeSubagent = el.dataset.sub || "";
      renderSubagentPicker();
      applyChatLayout();
    });
  });
}

async function loadAgents() {
  try {
    state.agents = await api("/api/agents");
    // Do not auto-activate every enabled subagent on the main UI
    if (state.activeSubagent && !state.selectedSubagents.includes(state.activeSubagent)) {
      state.activeSubagent = "";
    }
    renderSubagentBar();
  } catch (_) {
    state.agents = null;
  }
}

function updateSendEnabled() {
  const has = $("#input").value.trim().length > 0;
  const busyHere = !!(state.currentId && state.sessionRuns[state.currentId]?.streaming);
  $("#btn-send").disabled = !has || busyHere || !state.currentId;
  const stop = $("#btn-stop");
  if (stop) stop.classList.toggle("hidden", !busyHere);
}

/* ── Multi-subagent orchestration (Hermes-style board → heartbeat → tagged delivery) ── */

function detectNlSubagentCount(text) {
  const s = String(text || "");
  const cnMap = { 两: 2, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6 };
  const parseN = (raw) => {
    const n = cnMap[raw] || parseInt(raw, 10) || 0;
    return n >= 2 && n <= 6 ? n : 0;
  };
  let m = s.match(/(?:分成|分作|拆成|拆分(?:成)?|拆为|并行(?:调度)?)\s*([二三四五六两\d]+)\s*个?\s*(?:子代理|子\s*agent|sub[-\s]?agents?|agents?|代理)/i);
  if (!m) m = s.match(/(?:启动|调用|派发|开|用)\s*([二三四五六两\d]+)\s*个?\s*(?:子代理|子\s*agent|sub[-\s]?agents?|agents?)/i);
  if (!m) m = s.match(/([二三四五六两\d]+)\s*个\s*(?:子代理|子\s*agent|sub[-\s]?agents?|agents?)/i);
  if (!m) m = s.match(/([二三四五六两\d]+)\s*个?\s*sub[-\s]?agents?/i);
  if (!m) m = s.match(/(?:split|parallel|launch|spawn|start)\s*(?:into\s*)?(\d+)\s*(?:sub[-\s]?agents?|agents?)/i);
  if (m) return parseN(m[1]);
  // 「分别用子代理总结 A/B/C」without explicit count → infer from group labels
  if (/(?:子代理|sub[-\s]?agent)/i.test(s) && /(?:分别|并行|同时)/.test(s)) {
    const groups = s.match(/(?:^|[^A-Za-z])([ABC])(?=[组組\s、，,]|$)/gi) || [];
    const uniq = [...new Set(groups.map((g) => g.replace(/[^A-Za-z]/gi, "").toUpperCase()))];
    if (uniq.length >= 2) return Math.min(6, uniq.length);
    if (/[三3]/.test(s)) return 3;
    if (/[四4]/.test(s)) return 4;
    return 3;
  }
  return 0;
}

function wantsMultiSubagents(text) {
  const nl = detectNlSubagentCount(text);
  const selected = (state.selectedSubagents || []).length;
  if (selected >= 2 || nl >= 2) {
    return { count: Math.min(6, Math.max(nl || 0, selected >= 2 ? selected : 0)), nl, selected };
  }
  return null;
}

function inferPartitionRoles(text, n, langZh) {
  const s = String(text || "");
  const letters = [];
  const re = /(?:^|[^A-Za-z])([ABC])(?=[组組\s、，,]|$)/gi;
  let gm;
  while ((gm = re.exec(s)) !== null) {
    const L = gm[1].toUpperCase();
    if (!letters.includes(L)) letters.push(L);
  }
  if (/三组|甲乙丙|A\s*[、,]\s*B\s*[、,]\s*C|ABC/i.test(s) && letters.length < 3) {
    ["A", "B", "C"].forEach((L) => { if (!letters.includes(L)) letters.push(L); });
  }
  if (letters.length >= 2) {
    return letters.slice(0, n).map((L) => (
      langZh
        ? { title: `${L}组数据采集`, focus: `只负责汇总「${L}组」最新赛果/积分/出线形势；不要包办其他组；注明信息时效与来源。` }
        : { title: `Group ${L} collector`, focus: `Only summarize Group ${L} latest results/standings; cite sources; do not cover other groups.` }
    ));
  }
  return null;
}

function inferTaskRoles(text, n, langZh) {
  const partitioned = inferPartitionRoles(text, n, langZh);
  if (partitioned && partitioned.length) {
    while (partitioned.length < n) {
      const i = partitioned.length + 1;
      partitioned.push(langZh
        ? { title: `补充线路 ${i}`, focus: "补充交叉核对与遗漏信息。" }
        : { title: `Extra lane ${i}`, focus: "Cross-check gaps." });
    }
    return partitioned.slice(0, n);
  }
  const s = String(text || "");
  const isCode = /(?:\bR\b|\bpython\b|代码|脚本|分析|ggplot|dplyr|pandas|可视化|统计|建模|bioinformatics|生信)/i.test(s);
  const codeZh = [
    { title: "数据准备与清洗", focus: "负责数据导入、清洗、缺失值/因子处理；交付可运行代码块与简要说明。" },
    { title: "核心分析与建模", focus: "负责核心统计/建模分析代码与关键结果要点。" },
    { title: "可视化与报告输出", focus: "负责图表（如 ggplot）与可读报告输出代码。" },
    { title: "校验与复现说明", focus: "补充依赖、seed、测试与复现步骤。" },
    { title: "扩展与健壮性", focus: "补充错误处理、边界情况与可选优化。" },
    { title: "用法文档注释", focus: "补充函数文档、参数说明与使用示例。" },
  ];
  const codeEn = [
    { title: "Data prep & cleaning", focus: "Import/clean data; deliver runnable code." },
    { title: "Core analysis & modeling", focus: "Stats/modeling code and key findings." },
    { title: "Viz & report output", focus: "Plots and readable report code." },
    { title: "Validation & repro", focus: "Dependencies, seeds, tests, repro steps." },
    { title: "Robustness extras", focus: "Error handling and optional optimizations." },
    { title: "Usage docs", focus: "Docstrings, params, usage examples." },
  ];
  const genZh = [
    { title: "目标拆解与方案", focus: "明确目标、约束与可交付结构。" },
    { title: "核心内容产出", focus: "产出主体内容/草稿交付。" },
    { title: "校验补全与润色", focus: "检查缺口与风险，润色成可用交付。" },
    { title: "风险与备选方案", focus: "列出风险、假设与备选路径。" },
    { title: "落地步骤清单", focus: "给出可执行下一步清单。" },
    { title: "摘要与交接说明", focus: "产出简洁摘要供主代理汇总。" },
  ];
  const genEn = [
    { title: "Scope & plan", focus: "Goals, constraints, deliverable structure." },
    { title: "Core draft", focus: "Main content/draft deliverable." },
    { title: "Review & polish", focus: "Gaps, risks, polish to shippable." },
    { title: "Risks & alternatives", focus: "Assumptions, risks, alternatives." },
    { title: "Action checklist", focus: "Concrete next steps." },
    { title: "Handoff summary", focus: "Short summary for synthesis." },
  ];
  const pool = isCode ? (langZh ? codeZh : codeEn) : (langZh ? genZh : genEn);
  return pool.slice(0, n);
}

const LANE_TIER_CYCLE = ["C0", "C1", "C2"];
const SLOT_TO_TIER = {
  simple: "C0", fast: "C0", c0: "C0",
  office: "C1", main: "C1", c1: "C1", c2: "C2",
  reasoning: "C3", c3: "C3",
  vision: "Vision",
};
const SLOT_TO_ROUTE = {
  simple: "simple", fast: "simple", c0: "simple",
  office: "office", main: "office", c1: "office", c2: "office",
  reasoning: "reasoning", c3: "reasoning",
  vision: "vision",
};

function formatLaneModelLabel(lane) {
  const tier = (lane && lane.tier) || "";
  const model = (lane && lane.model) || "";
  const soul = (lane && lane.soul_role) || "";
  const bits = [];
  if (tier && model) bits.push(`${tier} · ${model}`);
  else if (model) bits.push(model);
  else if (tier) bits.push(tier);
  else bits.push(t("orch.modelPending"));
  if (soul) bits.push(`soul:${soul}`);
  return bits.join(" · ");
}

async function enrichPlanFromCatalog(plan, userText) {
  if (!plan || !plan.lanes || !plan.lanes.length) return plan;
  const prefer = (state.selectedSubagents || []).slice(0, plan.lanes.length);
  try {
    const data = await api("/api/agents/parallel-plan", {
      method: "POST",
      body: JSON.stringify({
        count: plan.lanes.length,
        message: userText || plan.goal || "",
        prefer_ids: prefer,
      }),
    });
    const picked = data.lanes || [];
    const langZh = state.prefs.language !== "en";
    picked.forEach((sub, i) => {
      const lane = plan.lanes[i];
      if (!lane || !sub) return;
      lane.subagent_id = String(sub.id || lane.subagent_id || "");
      lane.soul_role = String(sub.soul_role || sub.role || lane.soul_role || "office");
      lane.model_slot = String(sub.model_slot || lane.model_slot || "");
      lane.model = String(sub.resolved_model || sub.model || lane.model || "").trim();
      lane.tier = String(sub.tier || SLOT_TO_TIER[lane.model_slot] || lane.tier || LANE_TIER_CYCLE[i % 3]);
      lane.route_key = SLOT_TO_ROUTE[lane.model_slot] || lane.route_key || "";
      const label = langZh ? (sub.label || sub.id) : (sub.label_en || sub.label || sub.id);
      if (label) {
        lane.shortTitle = label;
        lane.title = langZh ? `子代理 ${lane.letter} · ${label}` : `Agent ${lane.letter} · ${label}`;
      }
      if (sub.desc) lane.responsibility = sub.desc;
    });
  } catch (_) { /* fall through to local tier cycle */ }
  return plan;
}

async function assignLaneModels(plan, userText) {
  if (!plan || !plan.lanes) return plan;
  await Promise.all(plan.lanes.map(async (lane, i) => {
    const slot = String(lane.model_slot || "").trim().toLowerCase();
    const tierHint = lane.tier || SLOT_TO_TIER[slot] || LANE_TIER_CYCLE[i % LANE_TIER_CYCLE.length];
    const routeHint = lane.route_key || SLOT_TO_ROUTE[slot] || tierHint;
    // Already have an explicit resolved model from catalog — keep it, just ensure tier
    if (lane.model) {
      lane.tier = lane.tier || tierHint;
      lane.route_key = lane.route_key || routeHint;
      return;
    }
    try {
      const info = await api("/api/routing/resolve", {
        method: "POST",
        body: JSON.stringify({
          route: routeHint || tierHint,
          message: `${lane.responsibility || lane.shortTitle || ""}\n${userText || ""}`.slice(0, 800),
        }),
      });
      lane.tier = String((info && (info.tier || tierHint)) || tierHint);
      lane.route_key = String((info && info.route_key) || routeHint || "").trim();
      lane.model = String((info && info.model) || "").trim();
      lane.provider = String((info && (info.provider || info.provider_id)) || "").trim();
    } catch (_) {
      lane.tier = tierHint;
      lane.route_key = routeHint || "";
      lane.model = "";
    }
  }));
  return plan;
}

function buildMultiLanePlan(userText) {
  const intent = wantsMultiSubagents(userText);
  if (!intent) return null;
  const langZh = state.prefs.language !== "en";
  const letters = "ABCDEF";
  const selected = state.selectedSubagents || [];
  const catalog = ((state.agents && state.agents.subagents) || []);
  const n = intent.count || Math.max(selected.length, intent.nl || 2);
  const roles = inferTaskRoles(userText, n, langZh);
  const lanes = [];
  for (let i = 0; i < n; i++) {
    const letter = letters[i] || String(i + 1);
    const sid = selected[i] || "";
    const sub = sid ? catalog.find((x) => x.id === sid) : null;
    const role = roles[i] || roles[roles.length - 1] || { title: langZh ? `子任务 ${i + 1}` : `Task ${i + 1}`, focus: "" };
    const title = sub
      ? (langZh ? (sub.label || sid) : (sub.label_en || sub.label || sid))
      : role.title;
    const responsibility = sub ? (sub.desc || role.focus) : role.focus;
    const slot = String((sub && sub.model_slot) || "").trim();
    const tierHint = SLOT_TO_TIER[slot] || LANE_TIER_CYCLE[i % LANE_TIER_CYCLE.length];
    lanes.push({
      key: `lane-${letter.toLowerCase()}`,
      letter,
      title: langZh ? `子代理 ${letter} · ${title}` : `Agent ${letter} · ${title}`,
      shortTitle: title,
      responsibility,
      subagent_id: sid || "",
      soul_role: String((sub && (sub.soul_role || sub.role)) || "").trim(),
      model_slot: slot,
      status: "pending",
      progress: "",
      content: "",
      eta: langZh ? "约 15–40s" : "~15–40s",
      tier: tierHint,
      route_key: SLOT_TO_ROUTE[slot] || "",
      model: String((sub && sub.model) || "").trim(),
      provider: "",
    });
  }
  const goal = String(userText || "").replace(/\n+/g, " ").trim().slice(0, 160);
  return {
    goal,
    mode: "parallel",
    lanes,
    source: selected.length >= 2 ? "selected" : "nl",
  };
}

function orchStatusLabel(status) {
  const map = {
    pending: t("orch.pending"),
    processing: t("orch.processing"),
    waiting: t("orch.waiting"),
    completed: t("orch.completed"),
    error: t("sublane.error"),
  };
  return map[status] || status;
}

function resolveOrchAssistant(parentSessionId, fallback) {
  if (state.currentId !== parentSessionId) return null;
  const live = resolveLiveAssistant(parentSessionId);
  if (live.assistantEl) return live.assistantEl;
  return fallback && document.contains(fallback) ? fallback : null;
}

function ensureOrchBoard(assistantEl, plan) {
  if (!assistantEl || !plan) return null;
  let board = assistantEl.querySelector(".msg-orch-board");
  if (!board) {
    board = document.createElement("div");
    board.className = "msg-orch-board";
    const body = assistantEl.querySelector(".body");
    const think = assistantEl.querySelector(".msg-thinking");
    if (think) assistantEl.insertBefore(board, think.nextSibling);
    else if (body) assistantEl.insertBefore(board, body);
    else assistantEl.appendChild(board);
  }
  const langZh = state.prefs.language !== "en";
  const modeLine = `${t("orch.modeParallel")} · ${t("orch.routeOpenSquilla")} · ${plan.lanes.length}${langZh ? " 路" : " lanes"}`;
  board.innerHTML = `
    <div class="orch-head">
      <strong>${escapeHtml(t("orch.boardTitle"))}</strong>
      <span class="orch-mode">${escapeHtml(modeLine)}</span>
    </div>
    <div class="orch-goal"><span class="muted">${escapeHtml(t("orch.goal"))}：</span>${escapeHtml(plan.goal || "")}</div>
    <div class="orch-agents"></div>`;
  const list = board.querySelector(".orch-agents");
  plan.lanes.forEach((lane) => {
    const row = document.createElement("div");
    row.className = "orch-agent";
    row.dataset.lane = lane.key;
    row.innerHTML = `
      <span class="orch-status is-pending">${escapeHtml(orchStatusLabel(lane.status || "pending"))}</span>
      <div class="orch-name">${escapeHtml(lane.title)}</div>
      <div class="orch-model">${escapeHtml(t("orch.model"))}: <code>${escapeHtml(formatLaneModelLabel(lane))}</code></div>
      <div class="orch-role">${escapeHtml(lane.responsibility || "")}${lane.soul_role ? ` · Soul ${escapeHtml(lane.soul_role)}` : ""}${lane.eta ? ` · ETA ${escapeHtml(lane.eta)}` : ""}</div>
      <div class="orch-progress"></div>`;
    list.appendChild(row);
  });
  return board;
}

function ensureSublanes(assistantEl, plan) {
  if (!assistantEl || !plan) return null;
  let wrap = assistantEl.querySelector(".msg-sublanes");
  if (!wrap) {
    wrap = document.createElement("div");
    wrap.className = "msg-sublanes";
    wrap.setAttribute("aria-label", t("orch.laneOut"));
    const board = assistantEl.querySelector(".msg-orch-board");
    const body = assistantEl.querySelector(".body");
    if (board) board.after(wrap);
    else if (body) assistantEl.insertBefore(wrap, body);
    else assistantEl.appendChild(wrap);
  }
  const langZh = state.prefs.language !== "en";
  wrap.innerHTML = plan.lanes.map((lane) => `
    <div class="msg-sublane" data-lane="${escapeHtml(lane.key)}">
      <div class="sublane-head">
        <strong>${escapeHtml(lane.title)}</strong>
        <span class="sublane-model"><code>${escapeHtml(formatLaneModelLabel(lane))}</code></span>
        <span class="sublane-badge">${escapeHtml(t("sublane.queued"))}</span>
      </div>
      <div class="sublane-think"></div>
      <div class="sublane-body" data-placeholder="${escapeHtml(langZh ? "等待产出…" : "Waiting for output…")}"></div>
    </div>`).join("");
  return wrap;
}

function findByLaneKey(root, selector, laneKey) {
  if (!root || !laneKey) return null;
  return Array.from(root.querySelectorAll(selector)).find((el) => el.dataset.lane === laneKey) || null;
}

function setLaneModel(assistantEl, laneKey, lane) {
  if (!assistantEl || !laneKey) return;
  const label = formatLaneModelLabel(lane || {});
  const row = findByLaneKey(assistantEl, ".orch-agent", laneKey);
  if (row) {
    let el = row.querySelector(".orch-model code");
    if (!el) {
      const box = row.querySelector(".orch-model") || (() => {
        const d = document.createElement("div");
        d.className = "orch-model";
        d.innerHTML = `${escapeHtml(t("orch.model"))}: <code></code>`;
        const name = row.querySelector(".orch-name");
        if (name) name.after(d);
        else row.appendChild(d);
        return d;
      })();
      el = box.querySelector("code");
    }
    if (el) el.textContent = label;
  }
  const pane = findByLaneKey(assistantEl, ".msg-sublane", laneKey);
  if (pane) {
    let el = pane.querySelector(".sublane-model code");
    if (!el) {
      const head = pane.querySelector(".sublane-head");
      if (head) {
        const span = document.createElement("span");
        span.className = "sublane-model";
        span.innerHTML = `<code></code>`;
        const badge = head.querySelector(".sublane-badge");
        if (badge) head.insertBefore(span, badge);
        else head.appendChild(span);
        el = span.querySelector("code");
      }
    }
    if (el) el.textContent = label;
  }
}

function setLaneStatus(assistantEl, laneKey, status, progressText) {
  if (!assistantEl || !laneKey) return;
  const row = findByLaneKey(assistantEl, ".orch-agent", laneKey);
  if (row) {
    const badge = row.querySelector(".orch-status");
    if (badge) {
      badge.className = `orch-status is-${status}`;
      badge.textContent = orchStatusLabel(status);
    }
    const prog = row.querySelector(".orch-progress");
    if (prog && progressText != null) prog.textContent = progressText;
  }
  const pane = findByLaneKey(assistantEl, ".msg-sublane", laneKey);
  if (pane) {
    pane.classList.toggle("is-running", status === "processing" || status === "waiting");
    pane.classList.toggle("is-done", status === "completed");
    pane.classList.toggle("is-error", status === "error");
    const badge = pane.querySelector(".sublane-badge");
    if (badge) {
      const map = {
        pending: t("sublane.queued"),
        processing: t("sublane.running"),
        waiting: t("orch.waiting"),
        completed: t("sublane.done"),
        error: t("sublane.error"),
      };
      badge.textContent = map[status] || status;
    }
  }
}

function appendLaneThinking(assistantEl, laneKey, text) {
  const chunk = String(text || "").trim();
  if (!chunk || isNoiseThinking(chunk) || !assistantEl) return;
  const pane = findByLaneKey(assistantEl, ".msg-sublane", laneKey);
  if (!pane) return;
  const box = pane.querySelector(".sublane-think");
  if (!box) return;
  const last = box.lastChild;
  if (last && last.textContent === chunk) return;
  const line = document.createElement("div");
  line.textContent = chunk;
  box.appendChild(line);
  while (box.children.length > 8) box.firstChild.remove();
  box.scrollTop = box.scrollHeight;
}

function setLaneBody(assistantEl, laneKey, markdown) {
  const pane = findByLaneKey(assistantEl, ".msg-sublane", laneKey);
  if (!pane) return;
  const body = pane.querySelector(".sublane-body");
  if (!body) return;
  const cleaned = sanitizeWorkflowText(markdown || "");
  body.innerHTML = cleaned ? renderMd(cleaned) : "";
  if (cleaned) bindCodeBoxActions(body);
}

function buildLanePrompt(userText, lane, index, total) {
  const langZh = state.prefs.language !== "en";
  const modelNote = formatLaneModelLabel(lane);
  if (langZh) {
    return (
      `你是并行子代理「${lane.shortTitle}」（${lane.letter}/${total}）。\n` +
      `本路指定模型路由：${modelNote}\n` +
      `职责：${lane.responsibility || lane.shortTitle}\n` +
      `只完成自己负责的部分，不要包办其他子代理的工作；用 Markdown，代码必须带语言标签的围栏。\n` +
      `不要寒暄，不要编造「任务调度看板 / 系统模拟实时状态」之类的 UI 叙事（看板由 Hub 界面展示）。直接交付本路结果。\n\n` +
      `【用户总任务】\n${userText}`
    );
  }
  return (
    `You are parallel subagent "${lane.shortTitle}" (${lane.letter}/${total}).\n` +
    `Assigned model route: ${modelNote}\n` +
    `Responsibility: ${lane.responsibility || lane.shortTitle}\n` +
    `Only deliver your slice; fenced code with language tags. No chit-chat.\n` +
    `Do NOT invent fake orchestration dashboards / simulated heartbeats (Hub UI shows those).\n\n` +
    `【User task】\n${userText}`
  );
}

function buildSynthesisPrompt(userText, laneResults) {
  const langZh = state.prefs.language !== "en";
  const parts = laneResults.map((r) => (
    `### ${langZh ? "来自" : "From"} ${r.title}` +
    `${r.tier || r.model ? ` · ${[r.tier, r.model].filter(Boolean).join(" · ")}` : ""}\n` +
    `${r.content || (langZh ? "（无产出）" : "(empty)")}`
  )).join("\n\n");
  if (langZh) {
    return (
      `你是 Agent Hub 主代理。以下是 ${laneResults.length} 个子代理并行完成的部分结果（各路已标注实际模型）。\n` +
      `请综合为一份连贯交付：\n` +
      `1. 先用简短总述；\n` +
      `2. 再按「来自 子代理 X（模型 …）」分节保留各子代理要点（可轻量去重）；\n` +
      `3. 最后给使用顺序/注意事项。\n` +
      `严禁输出「任务调度启动 / Pending / 系统模拟实时状态更新」等看板式假进度（Hub UI 已展示真实进度）。\n` +
      `语言：中文。\n\n【用户原任务】\n${userText}\n\n【子代理结果矩阵】\n${parts}`
    );
  }
  return (
    `You are the Hub parent agent. Synthesize ${laneResults.length} parallel subagent results (models labeled).\n` +
    `Short overview, then sections tagged "From Agent X (model …)", then usage notes.\n` +
    `Do NOT invent fake orchestration dashboards or simulated status lines.\n\n` +
    `【Task】\n${userText}\n\n【Matrix】\n${parts}`
  );
}

function applyOrchestrationPlanEvent(assistantEl, payload) {
  if (!assistantEl || !payload) return;
  const lanes = (payload.agents || payload.lanes || []).map((a, i) => ({
    key: a.id || a.key || `lane-${i}`,
    letter: a.letter || "ABCDEF"[i] || String(i + 1),
    title: a.title || a.label || `Agent ${i + 1}`,
    shortTitle: a.short_title || a.title || a.label || `Agent ${i + 1}`,
    responsibility: a.responsibility || a.role || a.desc || "",
    status: a.status || "pending",
    progress: a.progress || "",
    eta: a.eta || "",
    subagent_id: a.subagent_id || "",
    tier: a.tier || "",
    model: a.model || "",
    content: "",
  }));
  if (!lanes.length) return;
  const plan = {
    goal: payload.goal || payload.objective || "",
    mode: payload.mode || "parallel",
    lanes,
  };
  ensureOrchBoard(assistantEl, plan);
  ensureSublanes(assistantEl, plan);
  lanes.forEach((l) => {
    setLaneStatus(assistantEl, l.key, l.status || "pending", l.progress || "");
    setLaneModel(assistantEl, l.key, l);
  });
  appendThinking(assistantEl, t("sublane.planned") + ` · ${lanes.length}`);
}

function applySubagentStatusEvent(assistantEl, payload) {
  if (!assistantEl || !payload) return;
  const key = payload.id || payload.lane || payload.key || "";
  const status = String(payload.status || "processing").toLowerCase();
  const mapped = (
    status === "pending" || status === "queued" ? "pending"
      : status === "done" || status === "completed" || status === "complete" ? "completed"
        : status === "error" || status === "failed" ? "error"
          : status === "waiting" || status === "wait" ? "waiting"
            : "processing"
  );
  setLaneStatus(assistantEl, key, mapped, payload.progress || payload.message || payload.text || "");
  if (payload.model || payload.tier) {
    setLaneModel(assistantEl, key, {
      model: payload.model || "",
      tier: payload.tier || "",
    });
  }
  if (payload.message || payload.text) appendLaneThinking(assistantEl, key, payload.message || payload.text);
}

function restoreOrchFromRoute(assistantEl, route, content) {
  if (!assistantEl || !route || !route.multi_subagents) return;
  const lanes = (route.lanes || []).map((l, i) => ({
    key: l.id || l.key || `lane-${i}`,
    letter: l.letter || "ABCDEF"[i] || String(i + 1),
    title: l.title || `Agent ${i + 1}`,
    shortTitle: l.short_title || l.title || `Agent ${i + 1}`,
    responsibility: l.responsibility || "",
    status: l.status || "completed",
    progress: l.progress || "",
    eta: "",
    model: l.model || "",
    tier: l.tier || "",
    content: l.content || "",
  }));
  if (!lanes.length) return;
  const plan = { goal: route.goal || "", mode: "parallel", lanes };
  ensureOrchBoard(assistantEl, plan);
  ensureSublanes(assistantEl, plan);
  lanes.forEach((l) => {
    setLaneStatus(assistantEl, l.key, l.status || "completed", l.progress || formatLaneModelLabel(l));
    setLaneModel(assistantEl, l.key, l);
    if (l.content) setLaneBody(assistantEl, l.key, l.content);
  });
  if (content) {
    const body = assistantEl.querySelector(".body");
    if (body) {
      body.innerHTML = renderMd(sanitizeWorkflowText(content));
      bindCodeBoxActions(body);
    }
  }
}

async function runOneLaneJob(parentSessionId, lane, userText, index, total, assistantElRef, common) {
  const langZh = state.prefs.language !== "en";
  const paintTarget = () => resolveOrchAssistant(parentSessionId, assistantElRef);
  const child = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({
      title: lane.title,
      hidden: true,
      parent_id: parentSessionId,
    }),
  });
  const childId = child && child.id;
  if (!childId) throw new Error(langZh ? "子代理会话创建失败" : "Failed to create subagent session");

  state.multiLaneChildren[parentSessionId] = state.multiLaneChildren[parentSessionId] || [];
  state.multiLaneChildren[parentSessionId].push({ childId, laneKey: lane.key, title: lane.title });

  let a0 = paintTarget();
  setLaneStatus(a0, lane.key, "processing", langZh ? "调度中…" : "Dispatching…");
  setLaneModel(a0, lane.key, lane);
  appendThinking(a0, langZh
    ? `${lane.title} 开始 · ${formatLaneModelLabel(lane)}`
    : `${lane.title} started · ${formatLaneModelLabel(lane)}`);
  appendLaneThinking(a0, lane.key, langZh
    ? `绑定模型 ${formatLaneModelLabel(lane)}`
    : `Bound model ${formatLaneModelLabel(lane)}`);

  const prompt = buildLanePrompt(userText, lane, index, total);
  const laneRoute = lane.route_key || lane.tier || common.route;
  const start = await api(`/api/sessions/${childId}/chat`, {
    method: "POST",
    body: JSON.stringify({
      message: prompt,
      route: laneRoute,
      model: lane.model || common.model,
      thinking_depth: common.thinking_depth,
      workspace: common.workspace,
      skills: common.skills,
      execution_mode: "workflow",
      soul_role: lane.soul_role || undefined,
      subagent_id: lane.subagent_id || "",
      web_search: common.web_search,
      display_message: `[${lane.title}]`,
    }),
  });

  const resolvedModel = String((start && start.model) || (start && start.route && start.route.model) || lane.model || "").trim();
  const resolvedTier = String((start && start.route && start.route.tier) || lane.tier || "").trim();
  const resolvedKey = String((start && start.route && start.route.route_key) || lane.route_key || "").trim();
  if (resolvedModel) lane.model = resolvedModel;
  if (resolvedTier) lane.tier = resolvedTier;
  if (resolvedKey) lane.route_key = resolvedKey;

  a0 = paintTarget();
  setLaneModel(a0, lane.key, lane);
  appendLaneThinking(a0, lane.key, langZh
    ? `实际调用 ${formatLaneModelLabel(lane)}`
    : `Actually calling ${formatLaneModelLabel(lane)}`);
  appendThinking(a0, langZh
    ? `${lane.title} 实际模型：${formatLaneModelLabel(lane)}`
    : `${lane.title} model: ${formatLaneModelLabel(lane)}`);

  setSessionRun(childId, {
    streaming: true,
    pct: 10,
    streamId: start.stream_id,
    subagent_label: lane.shortTitle,
    parentId: parentSessionId,
    model: lane.model,
    tier: lane.tier,
  });
  state.streamConsumers[childId] = true;

  let raw = "";
  await new Promise((resolve, reject) => {
    const headers = {};
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    fetch(`/api/stream/${encodeURIComponent(start.stream_id)}?from=0`, { headers })
      .then(async (res) => {
        if (!res.ok) throw new Error("stream failed");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() || "";
          for (const part of parts) {
            const lines = part.split("\n");
            let event = "message";
            let data = "";
            for (const line of lines) {
              if (line.startsWith("event:")) event = line.slice(6).trim();
              if (line.startsWith("data:")) data += line.slice(5).trim();
            }
            if (!data) continue;
            let payload = {};
            try { payload = JSON.parse(data); } catch (_) {}
            const a = paintTarget();
            if (event === "route" || event === "meta") {
              const m = String((payload && payload.model) || "").trim();
              const tier = String((payload && payload.tier) || "").trim();
              if (m) lane.model = m;
              if (tier) lane.tier = tier;
              if (m || tier) {
                setLaneModel(a, lane.key, lane);
                appendLaneThinking(a, lane.key, langZh
                  ? `确认模型 ${formatLaneModelLabel(lane)}`
                  : `Confirmed ${formatLaneModelLabel(lane)}`);
              }
            } else if (event === "progress") {
              const pct = payload.pct || 30;
              setSessionRun(childId, { pct });
              const parentPct = Math.min(75, 20 + Math.round(((index + pct / 100) / total) * 50));
              setSessionRun(parentSessionId, { pct: parentPct });
              if (state.currentId === parentSessionId) {
                setWorkflowProgress(parentPct, null, `${lane.shortTitle} ${Math.round(pct)}% · ${formatLaneModelLabel(lane)}`, "thinking");
              }
              const tip = thinkingFromProgressLabel(payload.label) || payload.label || "";
              if (tip) {
                setLaneStatus(a, lane.key, "processing", tip);
                appendLaneThinking(a, lane.key, tip);
              }
            } else if (event === "thinking") {
              appendLaneThinking(a, lane.key, payload.text || payload.message || "");
            } else if (event === "tool") {
              const name = payload.name || payload.skill || "tool";
              appendLaneThinking(a, lane.key, `工具：${name}`);
              setLaneStatus(a, lane.key, "processing", name);
            } else if (event === "token") {
              raw += payload.text || "";
              setLaneStatus(a, lane.key, "processing", langZh ? "写入产出…" : "Writing…");
              if (!lane._paintTimer) {
                lane._paintTimer = setTimeout(() => {
                  lane._paintTimer = null;
                  if (state.currentId === parentSessionId) setLaneBody(paintTarget(), lane.key, raw);
                }, 280);
              }
            } else if (event === "error") {
              raw += `\n\n**Error:** ${payload.message || "error"}`;
              setLaneStatus(a, lane.key, "error", payload.message || "error");
            } else if (event === "done") {
              if (payload && payload.content) raw = payload.content;
              if (payload && payload.model) lane.model = String(payload.model);
              if (payload && payload.route && payload.route.model) lane.model = String(payload.route.model);
              if (payload && payload.route && payload.route.tier) lane.tier = String(payload.route.tier);
              resolve();
              return;
            }
          }
        }
        resolve();
      })
      .catch(reject);
  });

  if (lane._paintTimer) {
    clearTimeout(lane._paintTimer);
    lane._paintTimer = null;
  }
  const cleaned = sanitizeWorkflowText(raw);
  lane.content = cleaned;
  const aDone = paintTarget();
  setLaneBody(aDone, lane.key, cleaned);
  setLaneModel(aDone, lane.key, lane);
  setLaneStatus(aDone, lane.key, "completed", langZh
    ? `完成 · ${formatLaneModelLabel(lane)}`
    : `Done · ${formatLaneModelLabel(lane)}`);
  appendThinking(aDone, langZh
    ? `${lane.title} 完成（${formatLaneModelLabel(lane)}）`
    : `${lane.title} completed (${formatLaneModelLabel(lane)})`);
  clearSessionRun(childId);
  delete state.streamConsumers[childId];
  return {
    title: lane.title,
    key: lane.key,
    content: cleaned,
    letter: lane.letter,
    model: lane.model,
    tier: lane.tier,
  };
}

async function sendMultiSubagentMessage(text, plan, extra = {}) {
  const sessionId = state.currentId;
  if (!text || !sessionId || !plan || state.sessionRuns[sessionId]?.streaming) return "";
  const langZh = state.prefs.language !== "en";
  const viewAlive = () => state.currentId === sessionId;

  const wantSearch = !!(
    state.webSearch
    || ($("#btn-web-search") && $("#btn-web-search").classList.contains("active"))
    || ($("#btn-deep-search") && $("#btn-deep-search").classList.contains("active") && state.deepSearch && state.webSearch)
  );

  if (viewAlive()) {
    appendMessage({ role: "user", content: extra.display_message || text });
  }
  const assistantEl = viewAlive()
    ? appendMessage({ role: "assistant", content: "" })
    : null;
  const bodyEl = assistantEl ? assistantEl.querySelector(".body") : null;

  state.streaming = true;
  state.streamingSessionId = sessionId;
  state.streamConsumers[sessionId] = true;
  state.multiLaneChildren[sessionId] = [];
  setSessionRun(sessionId, { streaming: true, pct: 5, streamId: "", multi: true });
  state.streamBuffers[sessionId] = { rawBuf: "", full: "", route: null, elapsed_ms: null, orchPlan: plan };
  const stateBag = state.streamBuffers[sessionId];
  updateSendEnabled();

  // Bind catalog subagents (soul + tier model) then resolve concrete model ids
  try {
    await enrichPlanFromCatalog(plan, text);
    await assignLaneModels(plan, text);
  } catch (_) { /* keep tier hints */ }
  stateBag.orchPlan = plan;

  if (viewAlive() && assistantEl) {
    ensureOrchBoard(assistantEl, plan);
    ensureSublanes(assistantEl, plan);
    plan.lanes.forEach((l) => setLaneModel(assistantEl, l.key, l));
    appendThinking(assistantEl, `${t("sublane.planned")} · ${plan.lanes.length}${langZh ? " 路并行" : " parallel"}`);
    plan.lanes.forEach((l) => {
      appendThinking(assistantEl, `${l.title} → ${formatLaneModelLabel(l)}`);
    });
    resetWorkflowProgress(t("orch.boardTitle"));
    setWorkflowProgress(8, null, t("orch.routeOpenSquilla"), "thinking");
  }

  const common = {
    route: ($("#chat-mode-select")?.value === "single") ? "agent" : ($("#route-select").value || "auto"),
    model: ($("#model-select")?.value || "").trim(),
    thinking_depth: normalizeThinkingDepth(
      ($("#thinking-depth-select") && $("#thinking-depth-select").value) || state.prefs.thinkingDepth || "medium"
    ),
    workspace: $("#workspace-input").value.trim(),
    skills: state.selectedSkills || [],
    soul_role: state.activeSoul || ($("#soul-select") && $("#soul-select").value) || "",
    web_search: wantSearch ? true : undefined,
  };

  try {
    const results = await Promise.all(
      plan.lanes.map((lane, i) =>
        runOneLaneJob(sessionId, lane, text, i, plan.lanes.length, assistantEl, common)
          .catch((err) => {
            const a = resolveOrchAssistant(sessionId, assistantEl);
            setLaneStatus(a, lane.key, "error", String(err.message || err));
            appendThinking(a, `${lane.title} ${langZh ? "失败" : "failed"}: ${err.message || err}`);
            return { title: lane.title, key: lane.key, content: "", letter: lane.letter, model: lane.model, tier: lane.tier, error: true };
          })
      )
    );

    const matrixMd = results.map((r) => (
      `### ${t("orch.from")} ${r.title}` +
      `${r.tier || r.model ? ` · \`${[r.tier, r.model].filter(Boolean).join(" · ")}\`` : ""}\n\n` +
      `${r.content || (langZh ? "_（本路无产出）_" : "_(empty)_")}`
    )).join("\n\n");
    const aMat = resolveOrchAssistant(sessionId, assistantEl);
    const bodyMat = aMat ? aMat.querySelector(".body") : bodyEl;
    if (viewAlive() && bodyMat) {
      stateBag.rawBuf = matrixMd;
      stateBag.full = sanitizeWorkflowText(matrixMd);
      bodyMat.innerHTML = renderMd(stateBag.full);
      bindCodeBoxActions(bodyMat);
    }

    plan.lanes.forEach((l) => {
      const failed = results.some((r) => r.key === l.key && r.error);
      setLaneStatus(aMat, l.key, failed ? "error" : "waiting", langZh ? "待主代理汇总" : "Awaiting synthesis");
    });
    appendThinking(aMat, t("sublane.synth"));
    setSessionRun(sessionId, { pct: 80 });
    if (viewAlive()) setWorkflowProgress(80, null, t("sublane.synth"), "outputting");

    // Synthesis on a hidden child so parent history stays clean
    const synthSession = await api("/api/sessions", {
      method: "POST",
      body: JSON.stringify({
        title: langZh ? "主代理汇总" : "Parent synthesis",
        hidden: true,
        parent_id: sessionId,
      }),
    });
    const synthId = synthSession && synthSession.id;
    if (synthId) {
      state.multiLaneChildren[sessionId].push({ childId: synthId, laneKey: "synth", title: "synth" });
      const synthPrompt = buildSynthesisPrompt(text, results);
      let synthModel = common.model;
      let synthRoute = common.route;
      try {
        const synthInfo = await api("/api/routing/resolve", {
          method: "POST",
          body: JSON.stringify({ route: "C2", message: text.slice(0, 500) }),
        });
        if (synthInfo && synthInfo.model) synthModel = synthInfo.model;
        if (synthInfo && (synthInfo.route_key || synthInfo.tier)) {
          synthRoute = synthInfo.route_key || synthInfo.tier || synthRoute;
        }
        appendThinking(resolveOrchAssistant(sessionId, assistantEl), langZh
          ? `主代理汇总模型：${synthInfo.tier || "C2"} · ${synthModel}`
          : `Synthesis model: ${synthInfo.tier || "C2"} · ${synthModel}`);
      } catch (_) { /* keep common */ }
      const start = await api(`/api/sessions/${synthId}/chat`, {
        method: "POST",
        body: JSON.stringify({
          message: synthPrompt,
          route: synthRoute,
          model: synthModel,
          thinking_depth: common.thinking_depth,
          workspace: common.workspace,
          skills: common.skills,
          execution_mode: "workflow",
          soul_role: common.soul_role,
          web_search: common.web_search,
          display_message: langZh ? "【主代理汇总】" : "[Parent synthesis]",
        }),
      });
      setSessionRun(synthId, { streaming: true, pct: 85, streamId: start.stream_id, parentId: sessionId });
      state.streamConsumers[synthId] = true;
      setSessionRun(sessionId, { streamId: start.stream_id, pct: 85 });

      let synthRaw = "";
      await new Promise((resolve, reject) => {
        const headers = {};
        if (state.token) headers.Authorization = `Bearer ${state.token}`;
        fetch(`/api/stream/${encodeURIComponent(start.stream_id)}?from=0`, { headers })
          .then(async (res) => {
            if (!res.ok) throw new Error("stream failed");
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = "";
            let paintTimer = null;
            const paint = () => {
              paintTimer = null;
              stateBag.rawBuf = synthRaw;
              stateBag.full = sanitizeWorkflowText(synthRaw);
              if (viewAlive()) {
                const a = resolveOrchAssistant(sessionId, assistantEl);
                const b = a && a.querySelector(".body");
                if (b) {
                  b.innerHTML = renderMd(stateBag.full || "(…)");
                  bindCodeBoxActions(b);
                }
              }
            };
            while (true) {
              const { value, done } = await reader.read();
              if (done) break;
              buf += decoder.decode(value, { stream: true });
              const parts = buf.split("\n\n");
              buf = parts.pop() || "";
              for (const part of parts) {
                const lines = part.split("\n");
                let event = "message";
                let data = "";
                for (const line of lines) {
                  if (line.startsWith("event:")) event = line.slice(6).trim();
                  if (line.startsWith("data:")) data += line.slice(5).trim();
                }
                if (!data) continue;
                let payload = {};
                try { payload = JSON.parse(data); } catch (_) {}
                if (event === "thinking" && viewAlive()) {
                  appendThinking(resolveOrchAssistant(sessionId, assistantEl), payload.text || payload.message || "");
                } else if (event === "progress") {
                  const pct = Math.min(98, 80 + Math.round((payload.pct || 0) / 5));
                  setSessionRun(sessionId, { pct });
                  if (viewAlive()) setWorkflowProgress(pct, null, t("sublane.synth"), "outputting");
                } else if (event === "token") {
                  synthRaw += payload.text || "";
                  if (!paintTimer) paintTimer = setTimeout(paint, 220);
                } else if (event === "error") {
                  synthRaw += `\n\n**Error:** ${payload.message || "error"}`;
                } else if (event === "done") {
                  if (payload && payload.content) synthRaw = payload.content;
                  if (paintTimer) clearTimeout(paintTimer);
                  paint();
                  resolve();
                  return;
                }
              }
            }
            if (paintTimer) clearTimeout(paintTimer);
            paint();
            resolve();
          })
          .catch(reject);
      });
      clearSessionRun(synthId);
      delete state.streamConsumers[synthId];
    }

    if (!(stateBag.full || "").trim()) {
      stateBag.rawBuf = matrixMd;
      stateBag.full = sanitizeWorkflowText(matrixMd);
      if (viewAlive()) {
        const a = resolveOrchAssistant(sessionId, assistantEl);
        const b = a && a.querySelector(".body");
        if (b) {
          b.innerHTML = renderMd(stateBag.full);
          bindCodeBoxActions(b);
        }
      }
    }
    if (viewAlive()) {
      const aEnd = resolveOrchAssistant(sessionId, assistantEl);
      plan.lanes.forEach((l) => {
        if (!l.error) setLaneStatus(aEnd, l.key, "completed", langZh
          ? `已汇总 · ${formatLaneModelLabel(l)}`
          : `Merged · ${formatLaneModelLabel(l)}`);
        setLaneModel(aEnd, l.key, l);
      });
      collapseThinking(aEnd);
    }

    // Persist clean turn on parent (no synth-prompt pollution)
    try {
      await api(`/api/sessions/${sessionId}/messages`, {
        method: "POST",
        body: JSON.stringify({
          messages: [
            { role: "user", content: text },
            {
              role: "assistant",
              content: stateBag.full || matrixMd,
              route: {
                multi_subagents: true,
                lane_count: plan.lanes.length,
                goal: plan.goal,
                lanes: plan.lanes.map((l) => ({
                  id: l.key,
                  title: l.title,
                  status: "completed",
                  model: l.model || "",
                  tier: l.tier || "",
                  soul_role: l.soul_role || "",
                  model_slot: l.model_slot || "",
                  subagent_id: l.subagent_id || "",
                  responsibility: l.responsibility || "",
                  content: (l.content || "").slice(0, 12000),
                })),
              },
            },
          ],
        }),
      });
    } catch (persistErr) {
      console.warn(persistErr);
    }

    if (viewAlive()) finishWorkflowProgress(true);
  } catch (err) {
    if (viewAlive()) {
      const a = resolveOrchAssistant(sessionId, assistantEl);
      const b = a && a.querySelector(".body");
      if (b) b.innerHTML = renderMd(`**Error:** ${err.message || err}`);
      if (a) a.classList.add("error");
      finishWorkflowProgress(false);
    }
  } finally {
    delete state.streamConsumers[sessionId];
    clearSessionRun(sessionId);
    const kids = state.multiLaneChildren[sessionId] || [];
    for (const k of kids) {
      clearSessionRun(k.childId);
      delete state.streamConsumers[k.childId];
    }
    delete state.multiLaneChildren[sessionId];
    setTimeout(() => {
      if (!state.streamConsumers[sessionId]) delete state.streamBuffers[sessionId];
    }, 8000);
    if (state.streamingSessionId === sessionId) {
      state.streaming = Object.values(state.sessionRuns).some((r) => r.streaming);
      state.streamingSessionId = state.streaming
        ? (Object.keys(state.sessionRuns).find((k) => state.sessionRuns[k].streaming) || "")
        : "";
    }
    updateSendEnabled();
    renderActiveRuns();
    await refreshSessions();
    if (viewAlive()) {
      const cur = state.sessions.find((s) => s.id === state.currentId);
      if (cur) $("#chat-title").textContent = sessionDisplayTitle(cur);
    }
  }
  return stateBag.full || "";
}

async function sendMessage(overrideText, extra = {}) {
  let text = (overrideText != null ? overrideText : $("#input").value).trim();
  const sessionId = state.currentId;
  if (!text || !sessionId || state.sessionRuns[sessionId]?.streaming) return;

  if (state.pendingFiles.length) {
    const paths = state.pendingFiles.map((f) => f.relative || f.name).join(", ");
    text = `${text}\n\n[Attachments]\n${paths}`;
  }

  // Multi-subagent: NL "分成三个子代理" OR composer multi-select ≥2
  const multiPlan = buildMultiLanePlan(text);
  if (multiPlan && multiPlan.lanes.length >= 2 && !extra._skip_multi) {
    if (overrideText == null) $("#input").value = "";
    state.pendingFiles = [];
    renderAttachBar();
    return sendMultiSubagentMessage(text, multiPlan, extra);
  }

  if (state.activeSubagent && state.selectedSubagents.includes(state.activeSubagent) && state.agents) {
    const sub = (state.agents.subagents || []).find((s) => s.id === state.activeSubagent);
    if (sub) {
      extra = {
        ...extra,
        subagent_id: sub.id,
        system: `${extra.system || ""}\nYou are Agent Hub subagent "${sub.label}" (role=${sub.role}, soul=${sub.soul_role || sub.role || ""}). ${sub.desc || ""}`.trim(),
        soul_role: sub.soul_role || sub.role || state.activeSoul || "",
        display_message: extra.display_message || `[${sub.label}] ${overrideText != null ? overrideText : $("#input").value}`.trim(),
      };
    }
  }

  // Auto-match skills only when user selected none AND message implies skills.
  // Manual picker / 「自动匹配」 button still load skills; plain chat skips.
  if (!state.selectedSkills.length && messageImpliesSkills(text)) {
    await autoMatchSkills(text).catch(() => {});
  }

  const hasXlsxAttach = (state.pendingFiles || []).some((f) =>
    /\.xlsx?$/i.test(String(f.relative || f.name || f.path || ""))
  );
  const fillLike = /填写|填表|填入|填充|凝练|补全|完善|教授|方向|根据|研究|特色|excel|xlsx|表格|联网|检索|搜索/i.test(text);
  const autoExcelSearch = hasXlsxAttach && fillLike;
  const wantSearch = !!(
    state.webSearch
    || ($("#btn-web-search") && $("#btn-web-search").classList.contains("active"))
    || ($("#btn-deep-search") && $("#btn-deep-search").classList.contains("active") && state.deepSearch && state.webSearch)
    || autoExcelSearch
  );

  if (overrideText == null) $("#input").value = "";
  state.pendingFiles = [];
  renderAttachBar();

  const viewAlive = () => state.currentId === sessionId;
  if (viewAlive()) {
    appendMessage({ role: "user", content: extra.display_message || text });
  }
  const assistantEl = viewAlive()
    ? appendMessage({ role: "assistant", content: "" })
    : null;
  const bodyEl = assistantEl ? assistantEl.querySelector(".body") : null;

  state.streaming = true;
  state.streamingSessionId = sessionId;
  state.streamConsumers[sessionId] = true;
  setSessionRun(sessionId, { streaming: true, pct: 8, streamId: "" });
  state.lastAssistantText = "";
  // Reset live buffer for this turn
  state.streamBuffers[sessionId] = { rawBuf: "", full: "", route: null, elapsed_ms: null };
  const stateBag = state.streamBuffers[sessionId];
  updateSendEnabled();
  if (viewAlive()) {
    resetWorkflowProgress(t("stream.running"));
    setWorkflowProgress(5, null, t("stream.hint.match"), "thinking");
    if (assistantEl) appendThinking(assistantEl, thinkingFromProgressLabel("match-skills") || t("stream.hint.match"));
  }

  try {
    if (viewAlive()) setWorkflowProgress(15, null, t("stream.hint.dispatch"), "thinking");
    setSessionRun(sessionId, { pct: 15 });
    const start = await api(`/api/sessions/${sessionId}/chat`, {
      method: "POST",
      body: JSON.stringify({
        message: text,
        route: ($("#chat-mode-select")?.value === "single") ? "agent" : ($("#route-select").value || "auto"),
        model: ($("#model-select")?.value || "").trim(),
        thinking_depth: normalizeThinkingDepth(
          ($("#thinking-depth-select") && $("#thinking-depth-select").value) || state.prefs.thinkingDepth || "medium"
        ),
        workspace: $("#workspace-input").value.trim(),
        skills: state.selectedSkills || [],
        execution_mode: "workflow",
        soul_role: state.activeSoul || ($("#soul-select") && $("#soul-select").value) || "",
        subagent_id: extra.subagent_id || state.activeSubagent || "",
        web_search: wantSearch ? true : undefined,
        ...extra,
      }),
    });
    persistChatModeAndModel();
    if (viewAlive() && start.route) {
      setRouteBadge(start.route);
      renderEngineBadge(null, start.route);
    }
    setSessionRun(sessionId, { streamId: start.stream_id });
    stateBag.rawBuf = "";
    stateBag.full = "";
    if (start.route && start.route.excel_fill && start.route.excel_fill.markdown) {
      stateBag.rawBuf = String(start.route.excel_fill.markdown) + "\n\n";
      stateBag.full = sanitizeWorkflowText(stateBag.rawBuf);
      state.lastAssistantText = stateBag.full;
      if (viewAlive() && bodyEl) {
        bodyEl.innerHTML = renderMd(stateBag.full);
        bindCodeBoxActions(bodyEl);
        setWorkflowProgress(35, null, t("stream.hint.execute"), "outputting");
      }
      if (viewAlive() && assistantEl) {
        appendThinking(assistantEl, "Excel 联网填写结果已就绪");
      }
      setSessionRun(sessionId, { pct: 35 });
    }
    if (start.route && start.route.skills) {
      if (start.route.skills_auto && (!state.selectedSkills || !state.selectedSkills.length)) {
        state.selectedSkills = start.route.skills;
        renderSkillPicker();
      }
    }
    if (viewAlive()) setWorkflowProgress(25, null, t("stream.hint.dispatch"), "thinking");
    setSessionRun(sessionId, { pct: 25 });
    state.streamMeta = null;
    const handlers = makeStreamHandlers(sessionId, assistantEl, bodyEl, start.route || null, stateBag);
    await readSSE(`/api/stream/${encodeURIComponent(start.stream_id)}?from=0`, handlers);
    if (viewAlive()) finishWorkflowProgress(true);
  } catch (err) {
    if (viewAlive() && bodyEl && assistantEl) {
      bodyEl.innerHTML = renderMd(`**Error:** ${err.message || err}`);
      assistantEl.classList.add("error");
      finishWorkflowProgress(false);
    }
  } finally {
    delete state.streamConsumers[sessionId];
    clearSessionRun(sessionId);
    setTimeout(() => {
      if (!state.streamConsumers[sessionId]) delete state.streamBuffers[sessionId];
    }, 8000);
    if (state.streamingSessionId === sessionId) {
      state.streaming = Object.values(state.sessionRuns).some((r) => r.streaming);
      state.streamingSessionId = state.streaming ? (Object.keys(state.sessionRuns).find((k) => state.sessionRuns[k].streaming) || "") : "";
    }
    updateSendEnabled();
    renderActiveRuns();
    await refreshSessions();
    if (viewAlive()) {
      const cur = state.sessions.find((s) => s.id === state.currentId);
      if (cur) $("#chat-title").textContent = sessionDisplayTitle(cur);
    }
  }
  return stateBag.full || "";
}

function readSSE(url, handlers) {
  return new Promise((resolve, reject) => {
    const headers = {};
    if (state.token) headers.Authorization = `Bearer ${state.token}`;
    fetch(url, { headers })
      .then(async (res) => {
        if (!res.ok) throw new Error("stream failed");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const parts = buf.split("\n\n");
          buf = parts.pop() || "";
          for (const part of parts) {
            const lines = part.split("\n");
            let event = "message";
            let data = "";
            for (const line of lines) {
              if (line.startsWith("event:")) event = line.slice(6).trim();
              if (line.startsWith("data:")) data += line.slice(5).trim();
            }
            if (!data) continue;
            let payload = {};
            try { payload = JSON.parse(data); } catch (_) {}
            if (event === "route" && handlers.onRoute) handlers.onRoute(payload);
            if (event === "meta" && handlers.onMeta) handlers.onMeta(payload);
            if (event === "progress" && handlers.onProgress) handlers.onProgress(payload);
            if (event === "thinking" && handlers.onThinking) handlers.onThinking(payload.text || payload.message || "");
            if (event === "heal" && handlers.onHeal) handlers.onHeal(payload);
            if (event === "token" && handlers.onToken) handlers.onToken(payload.text || "");
            if (event === "tool" && handlers.onTool) handlers.onTool(payload);
            if (event === "orchestration_plan" && handlers.onOrchestrationPlan) handlers.onOrchestrationPlan(payload);
            if ((event === "subagent_status" || event === "subagent_update") && handlers.onSubagentStatus) handlers.onSubagentStatus(payload);
            if (event === "subagent_done" && handlers.onSubagentDone) handlers.onSubagentDone(payload);
            if (event === "error" && handlers.onError) handlers.onError(payload.message || "error");
            if (event === "done") {
              if (handlers.onDone) handlers.onDone(payload);
              resolve();
              return;
            }
          }
        }
        resolve();
      })
      .catch(reject);
  });
}

async function stopStream() {
  const id = state.currentId;
  if (!id) return;
  try { await api(`/api/sessions/${id}/cancel`, { method: "POST", body: "{}" }); } catch (_) {}
  const kids = state.multiLaneChildren[id] || [];
  for (const k of kids) {
    try { await api(`/api/sessions/${k.childId}/cancel`, { method: "POST", body: "{}" }); } catch (_) {}
    clearSessionRun(k.childId);
    delete state.streamConsumers[k.childId];
  }
}

function openWorkflow(w) {
  state.pendingWf = w;
  const label = wfLabel(w);
  $("#wf-title").textContent = `${w.icon || ""} ${label.name}`;
  $("#wf-desc").textContent = label.description || "";
  $("#wf-input").value = "";
  $("#wf-save-inbox").checked = !!w.save_to_inbox;
  $("#wf-overlay").classList.remove("hidden");
  setSidebarOpen(false);
}

async function runWorkflow() {
  const w = state.pendingWf;
  if (!w) return;
  const input = $("#wf-input").value.trim();
  const saveInbox = $("#wf-save-inbox").checked;
  $("#wf-overlay").classList.add("hidden");
  const label = wfLabel(w);

  resetWorkflowProgress(`${label.name} · ${t("stream.running")}`);
  setWorkflowProgress(8, null, t("stream.hint.match"), "thinking");

  const data = await api("/api/workflows/run", {
    method: "POST",
    body: JSON.stringify({
      preset_id: w.id,
      session_id: state.currentId,
      input,
      workspace: $("#workspace-input").value.trim(),
      skills: state.selectedSkills || [],
      execution_mode: "workflow",
      thinking_depth: normalizeThinkingDepth(
        ($("#thinking-depth-select") && $("#thinking-depth-select").value) || state.prefs.thinkingDepth || "medium"
      ),
    }),
  });
  if (data.session_id && data.session_id !== state.currentId) {
    await selectSession(data.session_id);
  }
  if (data.route) {
    setRouteBadge(data.route);
    if (data.route.route_key) {
      const sel = $("#route-select");
      if ([...sel.options].some((o) => o.value === data.route.route_key)) sel.value = data.route.route_key;
    }
  }

  appendMessage({
    role: "user",
    content: `[${label.name}] ${input || t("wf.template")}`,
    route: data.route,
  });
  const sessionId = data.session_id || state.currentId;
  const assistantEl = appendMessage({ role: "assistant", content: "", route: data.route });
  const bodyEl = assistantEl.querySelector(".body");
  state.streaming = true;
  if (sessionId) {
    state.streamConsumers[sessionId] = true;
    setSessionRun(sessionId, { streaming: true, pct: 20, streamId: data.stream_id, route: data.route });
  }
  $("#btn-stop").classList.remove("hidden");
  setWorkflowProgress(20, null, t("stream.hint.dispatch"), "thinking");
  const stateBag = { rawBuf: "", full: "" };
  try {
    setWorkflowProgress(30, null, t("stream.hint.execute"), "thinking");
    const handlers = makeStreamHandlers(sessionId, assistantEl, bodyEl, data.route || null, stateBag);
    await readSSE(`/api/stream/${data.stream_id}`, handlers);
    finishWorkflowProgress(true);
  } finally {
    if (sessionId) {
      delete state.streamConsumers[sessionId];
      clearSessionRun(sessionId);
    }
    state.streaming = Object.values(state.sessionRuns).some((r) => r.streaming);
    $("#btn-stop").classList.add("hidden");
    updateSendEnabled();
    renderActiveRuns();
    await refreshSessions();
  }

  const full = stateBag.full || "";
  if (saveInbox && full.trim()) {
    const ok = confirm(t("confirm.vault"));
    if (ok) {
      const wr = await api("/api/obsidian/write", {
        method: "POST",
        body: JSON.stringify({
          title: label.name,
          content: full,
          approved: true,
          tags: ["ai-candidate", w.id],
        }),
      });
      if (wr.ok) appendMessage({ role: "assistant", content: `${t("vault.ok")}：\`${wr.path}\`` });
      else appendMessage({ role: "assistant", content: `${t("vault.fail")}：${wr.error || "unknown"}`, error: true });
    }
  }
}

function openControl(on = true) {
  $("#control-overlay").classList.toggle("hidden", !on);
  if (on) {
    applyControlCenterLanguage();
    renderControl();
  }
}

function applyControlCenterLanguage() {
  const lang = controlLangZh() ? "zh" : "en";
  const dict = I18N[lang] || I18N.zh;
  const root = $("#control-overlay");
  if (!root) return;
  root.querySelectorAll("[data-i18n]").forEach((el) => {
    const key = el.getAttribute("data-i18n");
    if (key && dict[key]) el.textContent = dict[key];
  });
}

function field(label, key, value, type = "text") {
  if (type === "checkbox") {
    return `<label class="field"><span>${escapeHtml(label)}</span>
      <input type="checkbox" data-key="${escapeHtml(key)}" ${value ? "checked" : ""} /></label>`;
  }
  if (type === "select") {
    const opts = value.options.map((o) => {
      const optLabel = o.label || o.value || o;
      const optVal = o.value != null ? o.value : o;
      return `<option value="${escapeHtml(optVal)}" ${optVal === value.selected ? "selected" : ""}>${escapeHtml(optLabel)}</option>`;
    }).join("");
    return `<label class="field"><span>${escapeHtml(label)}</span>
      <select data-key="${escapeHtml(key)}">${opts}</select></label>`;
  }
  return `<label class="field"><span>${escapeHtml(label)}</span>
    <input type="${type}" data-key="${escapeHtml(key)}" value="${escapeHtml(value || "")}" /></label>`;
}

async function renderSearchPanel(langZh) {
  const box = $("#ctab-search");
  if (!box) return;
  const cfg = ((state.settings && state.settings.config) || {}).search || {};
  let status = (state.settings && state.settings.search) || {};
  try {
    status = await api("/api/search/status");
  } catch (_) {}
  const note = langZh ? (status.campus_note_zh || "") : (status.campus_note_en || "");
  box.innerHTML = `
    <h3>${langZh ? "信息搜索 / 深度检索" : "Information / deep search"}</h3>
    <p class="muted">${escapeHtml(note)}</p>
    <div class="grid-2">
      ${field(langZh ? "启用外网搜索" : "Enable search", "search.enabled", cfg.enabled !== false, "checkbox")}
      ${field(langZh ? "默认深度搜索" : "Deep search by default", "search.deep", cfg.deep !== false, "checkbox")}
      ${field(langZh ? "引擎优先" : "Provider preference", "search.provider", {
        selected: cfg.provider || "auto",
        options: [
          { value: "auto", label: langZh ? "自动（Google 有钥优先 → Bing → 360/搜狗）" : "Auto (Google if keyed → Bing → 360/Sogou)" },
          { value: "google_cse", label: "Google CSE" },
          { value: "serpapi", label: "SerpAPI Google" },
          { value: "bing", label: "Bing RSS" },
          { value: "so360", label: langZh ? "360 搜索" : "360 so.com" },
        ],
      }, "select")}
      ${field(langZh ? "HTTPS 代理（可选，打通 Google）" : "HTTPS proxy (optional, for Google)", "search.proxy", cfg.proxy || "")}
      ${field("Google CSE CX", "search.google_cse_cx", cfg.google_cse_cx || "")}
      ${field(langZh ? "校验证书" : "Verify TLS", "search.verify_tls", cfg.verify_tls !== false, "checkbox")}
    </div>
    <label class="field"><span>Google CSE API Key</span>
      <input type="password" id="search-google-cse-key" placeholder="${status.google_cse_configured ? (langZh ? "已配置（留空保留）" : "configured (leave blank to keep)") : "AIza…"}" autocomplete="off" />
    </label>
    <label class="field"><span>SerpAPI Key（Google 深度结果）</span>
      <input type="password" id="search-serpapi-key" placeholder="${status.serpapi_configured ? (langZh ? "已配置（留空保留）" : "configured (leave blank to keep)") : "serpapi…"}" autocomplete="off" />
    </label>
    <p class="muted">${langZh
      ? `状态：Google CSE ${status.google_cse_configured ? "✓" : "—"} · SerpAPI ${status.serpapi_configured ? "✓" : "—"} · 代理 ${status.proxy_configured ? "✓" : "—"}`
      : `Status: CSE ${status.google_cse_configured ? "on" : "off"} · SerpAPI ${status.serpapi_configured ? "on" : "off"} · proxy ${status.proxy_configured ? "on" : "off"}`}</p>
    <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap">
      <button type="button" class="btn primary" id="btn-search-save">${langZh ? "保存搜索设置" : "Save search settings"}</button>
      <button type="button" class="btn ghost" id="btn-search-test">${langZh ? "测试深度搜索" : "Test deep search"}</button>
    </div>
    <pre id="search-test-out" class="muted" style="white-space:pre-wrap;max-height:240px;overflow:auto"></pre>
  `;
  $("#btn-search-save")?.addEventListener("click", async () => {
    const body = {
      enabled: !!document.querySelector('[data-key="search.enabled"]')?.checked,
      deep: !!document.querySelector('[data-key="search.deep"]')?.checked,
      provider: document.querySelector('[data-key="search.provider"]')?.value || "auto",
      proxy: document.querySelector('[data-key="search.proxy"]')?.value || "",
      google_cse_cx: document.querySelector('[data-key="search.google_cse_cx"]')?.value || "",
      verify_tls: !!document.querySelector('[data-key="search.verify_tls"]')?.checked,
    };
    const cse = $("#search-google-cse-key")?.value?.trim();
    const serp = $("#search-serpapi-key")?.value?.trim();
    if (cse) body.google_cse_key = cse;
    if (serp) body.serpapi_key = serp;
    try {
      const data = await api("/api/search/keys", { method: "POST", body: JSON.stringify(body) });
      state.settings = data;
      $("#settings-status").textContent = langZh ? "搜索设置已保存并激活" : "Search settings saved & activated";
      await renderSearchPanel(langZh);
    } catch (e) {
      $("#settings-status").textContent = e.message || String(e);
    }
  });
  $("#btn-search-test")?.addEventListener("click", async () => {
    const out = $("#search-test-out");
    if (out) out.textContent = langZh ? "检索中…" : "Searching…";
    try {
      const q = langZh ? "深圳理工大学 合成生物学" : "synthetic biology SUAT";
      const data = await api("/api/search", { method: "POST", body: JSON.stringify({ q, deep: true, limit: 6 }) });
      const lines = [
        `ok=${data.ok} engines=${(data.engines || []).join(",") || "-"} offline=${!!data.offline}`,
        ...(data.results || []).slice(0, 6).map((r, i) => `${i + 1}. [${r.source}] ${r.title}\n   ${r.url || ""}\n   ${(r.snippet || "").slice(0, 120)}`),
      ];
      if (out) out.textContent = lines.join("\n\n") || JSON.stringify(data, null, 2);
      $("#settings-status").textContent = data.ok
        ? (langZh ? `深度搜索 OK · ${(data.results || []).length} 条` : `Deep search OK · ${(data.results || []).length} hits`)
        : (langZh ? "搜索仍失败，请检查代理 / API Key" : "Search failed — check proxy / API keys");
    } catch (e) {
      if (out) out.textContent = e.message || String(e);
    }
  });
}

async function renderControl() {
  applyControlCenterLanguage();
  await loadSettings();
  const cfg = (state.settings && state.settings.config) || {};
  const health = await api("/api/health/office");
  const matrix = await api("/api/routing");
  const ali = cfg.ali || {};

  $("#ctab-appearance").innerHTML = `
    <div class="grid-2">
      ${field(t("appearance.lang"), "ali.language", {
        selected: state.prefs.language,
        options: [
          { value: "zh", label: "中文" },
          { value: "en", label: "English" },
        ],
      }, "select")}
      ${field(t("appearance.theme"), "ali.theme", {
        selected: state.prefs.theme || "auto",
        options: [
          { value: "auto", label: t("theme.auto") },
          { value: "dark", label: t("theme.dark") },
          { value: "light", label: t("theme.light") },
        ],
      }, "select")}
      ${field(t("appearance.accent"), "ali.accent", {
        selected: state.prefs.accent,
        options: ACCENTS.map((a) => ({ value: a, label: a === "suat" ? "深理工紫 / SUAT" : a })),
      }, "select")}
      ${field(state.prefs.language === "zh" ? "背景色" : "Background", "ali.bg", {
        selected: normalizeBg(state.prefs.bg),
        options: BGS.map((a) => ({
          value: a,
          label: (BG_LABELS[state.prefs.language === "en" ? "en" : "zh"] || {})[a] || a,
        })),
      }, "select")}
      ${field(t("appearance.fontSize"), "ali.font_size", {
        selected: String(normalizeFontSize(state.prefs.fontSize)),
        options: FONT_SIZES.map((px) => ({
          value: String(px),
          label: fontSizeOptionLabel(px),
        })),
      }, "select")}
    </div>
    <p class="muted">${controlLangZh()
      ? "控制中心与侧栏语言开关同步（中 / EN）。"
      : "Control Center language stays in sync with the sidebar 中 / EN toggle."}</p>
    <div class="bg-row" id="bg-row-control"></div>
    <div class="accent-row" id="accent-row-control"></div>
    <p class="muted">${escapeHtml(t("appearance.hint"))}</p>
    <div class="logo-section" id="logo-section">
      <h3 class="logo-section-title">${escapeHtml(t("appearance.logo"))}</h3>
      <p class="muted">${escapeHtml(t("appearance.logoHint"))}</p>
      <div class="logo-previews">
        <div class="logo-preview-card">
          <div class="logo-preview-label">${escapeHtml(t("appearance.logoSidebar"))}</div>
          <img id="logo-preview-sidebar" class="logo-preview-img" src="${escapeHtml(logoSrc("sidebar"))}" alt="" />
        </div>
        <div class="logo-preview-card">
          <div class="logo-preview-label">${escapeHtml(t("appearance.logoEmpty"))}</div>
          <img id="logo-preview-empty" class="logo-preview-img logo-preview-empty" src="${escapeHtml(logoSrc("empty"))}" alt="" />
        </div>
      </div>
      <div class="logo-slot-row" role="radiogroup" aria-label="${escapeHtml(t("appearance.logo"))}">
        <label class="logo-slot-opt"><input type="radio" name="logo-slot" value="both" checked /> ${escapeHtml(t("appearance.logoSlotBoth"))}</label>
        <label class="logo-slot-opt"><input type="radio" name="logo-slot" value="sidebar" /> ${escapeHtml(t("appearance.logoSlotSidebar"))}</label>
        <label class="logo-slot-opt"><input type="radio" name="logo-slot" value="empty" /> ${escapeHtml(t("appearance.logoSlotEmpty"))}</label>
      </div>
      <div class="logo-actions chip-row">
        <button type="button" class="btn" id="btn-logo-upload">${escapeHtml(t("appearance.logoUpload"))}</button>
        <button type="button" class="btn ghost" id="btn-logo-reset">${escapeHtml(t("appearance.logoReset"))}</button>
        <input type="file" id="logo-file-input" accept="image/png,image/jpeg,image/webp,image/svg+xml,.png,.jpg,.jpeg,.webp,.svg" hidden />
      </div>
      <div class="muted" style="margin-top:8px">${escapeHtml(t("appearance.logoPresets"))}</div>
      <div class="logo-preset-row" id="logo-preset-row"></div>
      <p class="muted" id="logo-status" aria-live="polite"></p>
    </div>`;

  bindLogoControls();

  const bgCtrl = $("#bg-row-control");
  if (bgCtrl) {
    const lang = state.prefs.language === "en" ? "en" : "zh";
    BGS.forEach((name) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "bg-dot" + (normalizeBg(state.prefs.bg) === name ? " active" : "");
      b.dataset.bg = name;
      b.title = (BG_LABELS[lang] && BG_LABELS[lang][name]) || name;
      b.addEventListener("click", () => {
        const sel = document.querySelector('[data-key="ali.bg"]');
        if (sel) sel.value = name;
        setPrefs({ bg: name }, { syncServer: true });
      });
      bgCtrl.appendChild(b);
    });
  }

  const ctrlRow = $("#accent-row-control");
  if (ctrlRow) {
    ACCENTS.forEach((name) => {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "accent-dot" + (state.prefs.accent === name ? " active" : "");
      b.dataset.accent = name;
      b.title = name;
      b.addEventListener("click", () => {
        const sel = document.querySelector('[data-key="ali.accent"]');
        if (sel) sel.value = name;
        setPrefs({ accent: name }, { syncServer: true });
      });
      ctrlRow.appendChild(b);
    });
  }

  $$("#ctab-appearance [data-key]").forEach((el) => {
    el.addEventListener("change", () => {
      const key = el.getAttribute("data-key");
      if (key === "ali.language") setPrefs({ language: el.value }, { syncServer: true });
      if (key === "ali.theme") setPrefs({ theme: el.value }, { syncServer: true });
      if (key === "ali.accent") setPrefs({ accent: el.value }, { syncServer: true });
      if (key === "ali.bg") setPrefs({ bg: el.value }, { syncServer: true });
      if (key === "ali.font_size") setPrefs({ fontSize: el.value }, { syncServer: true });
    });
  });

  $("#ctab-health").innerHTML = (health.checks || []).map((c) =>
    `<div class="check-row"><div><strong>${escapeHtml(c.id)}</strong><div class="muted">${escapeHtml(c.detail || "")}</div></div>
      <span class="${c.ok ? "ok" : "bad"}">${c.ok ? "PASS" : "CHECK"}</span></div>`
  ).join("") + `<p class="muted">API Key (${escapeHtml((health.api_key || {}).env_name || "")}): ${(health.api_key || {}).present ? t("key.set") : t("key.missing")}</p>`;

  const b = cfg.backend || {};
  const catalog = (state.settings && state.settings.catalog) || {};
  const providers = catalog.providers || [];
  const hybridPresets = catalog.hybrid_presets || [];
  const providerOpts = providers.map((p) => ({ value: p.id, label: p.label }));
  const currentProv = providers.find((p) => p.id === (b.type || "")) || null;
  const langZh = controlLangZh();

  const keyStatus = (state.settings && state.settings.api_key) || {};
  $("#ctab-backend").innerHTML = `
    <div class="grid-2">
      ${field(langZh ? "后端类型 / Provider" : "Backend type", "backend.type", {
        selected: b.type || "campus-openai-compatible",
        options: providerOpts,
      }, "select")}
      ${field(langZh ? "API Key 环境变量名" : "API key ENV name", "backend.api_key_env",
        looksLikeSecret(b.api_key_env) ? ((currentProv && currentProv.api_key_env) || "") : (b.api_key_env || ""))}
      ${field("Base URL", "backend.base_url", b.base_url || "")}
      ${field("Timeout (s)", "backend.timeout_seconds", String(b.timeout_seconds || 60), "number")}
      ${field(langZh ? "校验证书（LLM 后端）" : "Verify TLS (LLM backend)", "backend.verify_tls", b.verify_tls !== false, "checkbox")}
    </div>
    <p class="muted">${langZh
      ? "默认安全开启。仅当本机代理使用自签名证书并导致证书校验失败时关闭；此项不影响联网搜索的证书设置。"
      : "Secure by default. Disable only for a self-signed proxy that causes certificate verification failures; this does not affect search TLS."}</p>
    <label class="field"><span>${langZh ? "API Key（保存在本机 secrets，不会写入 JSON）" : "API Key (local secrets only)"}</span>
      <input type="password" id="api-key-input" placeholder="${keyStatus.present ? (langZh ? "已保存：" : "saved: ") + escapeHtml(keyStatus.masked || "****") : (langZh ? "粘贴 nvapi-… / sk-or-… 等密钥" : "paste API key")}" autocomplete="off" />
    </label>
    <p class="muted" id="provider-hint">${escapeHtml((currentProv && currentProv.hint) || "")}</p>
    <p class="muted">${langZh ? "密钥状态：" : "Key status: "} <strong>${keyStatus.present ? (langZh ? "已配置" : "set") : (langZh ? "未配置" : "missing")}</strong>
      ${keyStatus.masked ? ` (${escapeHtml(keyStatus.masked)})` : ""}
      ${keyStatus.source ? ` · ${escapeHtml(keyStatus.source)}` : ""}</p>
    <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap">
      <button type="button" class="btn primary" id="btn-save-key">${langZh ? "保存 API Key" : "Save API Key"}</button>
      <button type="button" class="btn primary" id="btn-refresh-models">${langZh ? "拉取可用模型" : "Fetch models"}</button>
      <button type="button" class="btn ghost" id="btn-apply-provider">${langZh ? "应用厂商默认" : "Apply provider defaults"}</button>
      <button type="button" class="btn ghost" id="btn-sync-hermes-backend">${langZh ? "同步 LLM 到当前 Claw" : "Sync LLM to active Claw"}</button>
    </div>
    <div id="live-models-box" class="muted"></div>
    ${field(langZh ? "安装 / 根目录" : "Install / workspace root", "install_root", cfg.install_root || "")}
    ${field(langZh ? "默认工作区" : "Default workspace", "workspace", cfg.workspace || "")}
    <hr class="soft" />
    <h4>${langZh ? "混合融合 Hybrid" : "Hybrid fusion"}</h4>
    <p class="muted">${langZh ? "一键套用多厂商组合；再在「模型 / 路由」里微调。" : "One-click multi-provider recipes; tune in Models / Routing."}</p>
    <div class="hybrid-presets" id="hybrid-presets"></div>`;

  const hp = $("#hybrid-presets");
  if (hp) {
    hybridPresets.forEach((preset) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn ghost";
      btn.textContent = preset.label;
      btn.addEventListener("click", async () => {
        try {
          const data = await api("/api/settings/apply-provider", {
            method: "POST",
            body: JSON.stringify({ hybrid_preset: preset.id }),
          });
          state.settings = data;
          if (data.warning) alert(data.warning);
          $("#settings-status").textContent = langZh ? "已应用混合方案" : "Hybrid applied";
          renderControl();
          // jump to models tab
          document.querySelector('.ctab[data-ctab="models"]')?.click();
        } catch (e) {
          $("#settings-status").textContent = e.message;
        }
      });
      hp.appendChild(btn);
    });
  }

  const typeSel = document.querySelector('[data-key="backend.type"]');
  if (typeSel) {
    typeSel.addEventListener("change", () => {
      const p = providers.find((x) => x.id === typeSel.value);
      const hint = $("#provider-hint");
      if (hint) hint.textContent = (p && p.hint) || "";
      const envEl = document.querySelector('[data-key="backend.api_key_env"]');
      const urlEl = document.querySelector('[data-key="backend.base_url"]');
      if (p && p.id !== "hybrid") {
        if (envEl && (!envEl.value || !looksLikeSecret(envEl.value))) envEl.value = p.api_key_env || "";
        if (urlEl) urlEl.value = p.base_url || "";
      }
    });
  }

  const applyBtn = $("#btn-apply-provider");
  if (applyBtn) {
    applyBtn.onclick = async () => {
      const pid = document.querySelector('[data-key="backend.type"]').value;
      try {
        // save form backend fields first
        await saveSettings();
        const data = await api("/api/settings/apply-provider", {
          method: "POST",
          body: JSON.stringify({ provider: pid, fill_models: true }),
        });
        state.settings = data;
        if (data.warning) alert(data.warning);
        $("#settings-status").textContent = langZh ? "已应用厂商默认模型" : "Provider defaults applied";
        renderControl();
        document.querySelector('.ctab[data-ctab="routing"]')?.click();
      } catch (e) {
        $("#settings-status").textContent = e.message;
      }
    };
  }

  const saveKeyBtn = $("#btn-save-key");
  if (saveKeyBtn) {
    saveKeyBtn.onclick = async () => {
      const keyEl = $("#api-key-input");
      const key = (keyEl && keyEl.value || "").trim();
      const pid = document.querySelector('[data-key="backend.type"]').value;
      const envName = document.querySelector('[data-key="backend.api_key_env"]').value;
      const baseUrl = document.querySelector('[data-key="backend.base_url"]').value;
      if (!key) {
        $("#settings-status").textContent = langZh ? "请先粘贴 API Key" : "Paste API key first";
        return;
      }
      try {
        // persist backend fields
        const cfg = collectSettingsFromForm();
        cfg.backend = cfg.backend || {};
        cfg.backend.type = pid;
        cfg.backend.api_key_env = envName;
        cfg.backend.base_url = baseUrl;
        await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg, backend_update: true }) });
        const data = await api("/api/settings/api-key", {
          method: "POST",
          body: JSON.stringify({ api_key: key, provider: pid, api_key_env: envName, auto_switch: false }),
        });
        state.settings = data;
        if (keyEl) keyEl.value = "";
        const warn = data.warning || (data.api_key_saved && data.api_key_saved.mismatch && data.api_key_saved.mismatch.message);
        $("#settings-status").textContent = warn
          ? warn
          : (langZh
            ? `API Key 已保存（${(data.api_key_saved && data.api_key_saved.masked) || "****"}）· 仅绑定当前后端 ${pid}`
            : `API Key saved (${(data.api_key_saved && data.api_key_saved.masked) || "****"}) for ${pid}`);
        const hs = data.hermes_sync || {};
        if (hs.ok) {
          $("#settings-status").textContent = langZh
            ? `API Key 已保存 · 已同步到 Hermes/Claw（${hs.hermes_provider || pid}）`
            : `API Key saved · synced to Hermes/Claw (${hs.hermes_provider || pid})`;
        } else if (hs.error_zh || hs.error_en) {
          $("#settings-status").textContent = (langZh ? (hs.error_zh || hs.error) : (hs.error_en || hs.error)) || $("#settings-status").textContent;
        }
        renderControl();
      } catch (e) {
        $("#settings-status").textContent = e.message;
      }
    };
  }

  $("#btn-sync-hermes-backend")?.addEventListener("click", async () => {
    try {
      const rtSel = $("#runtime-active");
      const rt = (rtSel && rtSel.value) || (state.status && (state.status.agent_runtime || state.status.runtime)) || "auto";
      $("#settings-status").textContent = langZh ? "同步 LLM…" : "Syncing LLM…";
      const res = await api("/api/runtimes/sync-llm", {
        method: "POST",
        body: JSON.stringify({ runtime: rt || "auto" }),
      });
      const note = langZh ? (res.note_zh || res.error_zh || "已同步 LLM") : (res.note_en || res.error_en || "Synced LLM");
      $("#settings-status").textContent = note;
    } catch (e) {
      $("#settings-status").textContent = e.message;
    }
  });

  const refreshBtn = $("#btn-refresh-models");
  if (refreshBtn) {
    refreshBtn.onclick = async () => {
      const pid = document.querySelector('[data-key="backend.type"]').value;
      const baseUrl = document.querySelector('[data-key="backend.base_url"]').value;
      const envName = document.querySelector('[data-key="backend.api_key_env"]').value;
      const key = ($("#api-key-input") && $("#api-key-input").value || "").trim();
      try {
        $("#settings-status").textContent = langZh ? "正在拉取模型…" : "Fetching models…";
        // save key if pasted
        if (key) {
          await api("/api/settings/api-key", {
            method: "POST",
            body: JSON.stringify({ api_key: key, provider: pid, api_key_env: envName, auto_switch: false }),
          });
        }
        const cfg = collectSettingsFromForm();
        cfg.backend = cfg.backend || {};
        cfg.backend.type = pid;
        cfg.backend.base_url = baseUrl;
        cfg.backend.api_key_env = envName;
        await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg, backend_update: true }) });
        const data = await api("/api/settings/refresh-models", {
          method: "POST",
          body: JSON.stringify({ provider: pid, base_url: baseUrl, apply_suggestions: true }),
        });
        state.settings = data;
        state.liveModels = data.models || [];
        const box = $("#live-models-box");
        if (box) {
          const sample = (data.models || []).slice(0, 12).map(escapeHtml).join(", ");
          box.innerHTML = langZh
            ? `已拉取 <strong>${data.count || 0}</strong> 个模型，并自动填入推荐档位。<br/><code>${sample}${(data.models || []).length > 12 ? "…" : ""}</code>`
            : `Fetched <strong>${data.count || 0}</strong> models and applied slot suggestions.<br/><code>${sample}${(data.models || []).length > 12 ? "…" : ""}</code>`;
        }
        $("#settings-status").textContent = langZh
          ? `模型已更新（${data.count || 0}）`
          : `Models updated (${data.count || 0})`;
        renderControl();
        syncComposerFromSettings();
        document.querySelector('.ctab[data-ctab="routing"]')?.click();
      } catch (e) {
        $("#settings-status").textContent = e.message;
        const box = $("#live-models-box");
        if (box) box.innerHTML = `<span class="warn-box" style="display:inline-block">${escapeHtml(e.message)}</span>`;
      }
    };
  }

  const m = cfg.models || {};
  const slots = catalog.slots || [
    { id: "fast", legacy: "qwen_fast", tier: "C0", label: "Fast" },
    { id: "main", legacy: "qwen_main", tier: "C1/C2", label: "Main" },
    { id: "vision", legacy: "qwen_vl", tier: "Vision", label: "Vision" },
    { id: "reasoning", legacy: "deepseek_reasoning", tier: "C3", label: "Reasoning" },
    { id: "embedding", legacy: "embedding", tier: "—", label: "Embedding" },
    { id: "reranker", legacy: "reranker", tier: "—", label: "Reranker" },
  ];

  function modelField(slot) {
    const legacy = slot.legacy;
    const val = m[legacy] || m[slot.id] || "";
    return `<label class="field"><span>${escapeHtml(slot.label)} <em class="muted">(${escapeHtml(slot.tier)})</em></span>
      <select data-key="models.${escapeHtml(legacy)}">${modelIdOptions(val, b.type === "hybrid" ? "" : b.type)}</select>
    </label>`;
  }

  const isHybrid = (cfg.mode === "hybrid") || (b.type === "hybrid");
  let hybridHtml = "";
  if (isHybrid) {
    const hy = cfg.hybrid || {};
    const routeKeys = [
      { key: "simple", label: "C0 Fast" },
      { key: "office", label: "C1 Office" },
      { key: "vision", label: "Vision" },
      { key: "reasoning", label: "C3 Reasoning" },
    ];
    hybridHtml = `<h4>${langZh ? "混合路由绑定" : "Hybrid route binding"}</h4>
      <div class="grid-2">${routeKeys.map((rk) => {
        const entry = hy[rk.key] || {};
        const provOpts = providers.filter((p) => p.id !== "hybrid").map((p) =>
          `<option value="${escapeHtml(p.id)}" ${p.id === entry.provider ? "selected" : ""}>${escapeHtml(p.label)}</option>`
        ).join("");
        return `<div class="field"><span>${escapeHtml(rk.label)}</span>
          <select data-key="hybrid.${rk.key}.provider">${provOpts}</select>
          <select data-key="hybrid.${rk.key}.model">${modelIdOptions(entry.model || "", entry.provider || "")}</select>
        </div>`;
      }).join("")}</div>`;
  }

  $("#ctab-models").innerHTML = `
    <p class="muted">${langZh
      ? `当前厂商：<strong>${escapeHtml((currentProv && currentProv.label) || b.type || "—")}</strong>。切换后端后点「应用此厂商」可自动填充推荐模型。`
      : `Provider: <strong>${escapeHtml((currentProv && currentProv.label) || b.type || "—")}</strong>. Apply provider to auto-fill recommendations.`}</p>
    <div class="grid-2">${slots.map(modelField).join("")}</div>
    ${hybridHtml}`;

  const r = cfg.routing || {};
  const tierModels = r.tier_models || {};
  const routeTiers = [
    ["C0", "C0 · Fast"],
    ["C1", "C1 · Office"],
    ["C2", "C2 · Long-form"],
    ["C3", "C3 · Reasoning"],
    ["Vision", "Vision"],
  ];
  $("#ctab-routing").innerHTML = `
    <p class="muted">${langZh
      ? "每个等级可跟随旧槽位/自动，或固定到真实 Provider + Model。旧配置会继续生效。"
      : "Each tier can follow the legacy route/auto binding or pin a real Provider + Model. Old configs remain valid."}</p>
    <div class="grid-2">
      ${routeTiers.map(([tier, label]) => {
        const entry = tierModels[tier] || {};
        const row = (matrix.matrix || []).find((item) => item.tier === tier) || {};
        const follow = langZh
          ? `跟随路由 / 自动（当前 ${row.provider || "—"} · ${row.model || "—"}）`
          : `Follow route / auto (now ${row.provider || "—"} · ${row.model || "—"})`;
        return `<label class="field"><span>${escapeHtml(label)}</span>
          <select data-route-tier="${escapeHtml(tier)}">${modelBindingOptions(
            entry.provider || "", entry.model || "", { allowAuto: true, autoLabel: follow }
          )}</select></label>`;
      }).join("")}
    </div>
    ${field("restricted_external_fallback", "routing.restricted_external_fallback", !!r.restricted_external_fallback, "checkbox")}
    <table class="matrix"><thead><tr><th>Tier</th><th>Examples</th><th>Provider</th><th>Model</th></tr></thead>
    <tbody>${(matrix.matrix || []).map((row) =>
      `<tr><td>${escapeHtml(row.tier)}</td><td>${escapeHtml(row.examples)}</td>
       <td>${escapeHtml(row.provider || "—")}</td><td><code>${escapeHtml(row.model || "—")}</code></td></tr>`
    ).join("")}</tbody></table>`;

  const o = cfg.obsidian || {};
  $("#ctab-obsidian").innerHTML = `
    <label class="field"><span>Vault path</span>
      <div class="path-row">
        <input data-key="obsidian.vault_path" type="text" value="${escapeHtml(o.vault_path || "")}" />
        <button type="button" class="btn ghost" id="btn-browse-vault">…</button>
      </div>
    </label>
    ${field("AI inbox", "obsidian.ai_inbox", o.ai_inbox || "00_Inbox/AI_Candidates")}
    ${field("Allowed roots (comma)", "obsidian.allowed_roots", (o.allowed_roots || []).join(", "))}
    ${field("Write requires approval", "obsidian.write_requires_approval", o.write_requires_approval !== false, "checkbox")}`;
  $("#btn-browse-vault")?.addEventListener("click", () => {
    openFsBrowser(o.vault_path || "", '[data-key="obsidian.vault_path"]').catch((e) => alert(e.message));
  });

  // schedule panel
  await renderSchedulePanel(langZh);

  $("#ctab-security").innerHTML = `
    ${field("data_policy", "data_policy", { selected: cfg.data_policy || "internal", options: ["public", "internal", "restricted"] }, "select")}
    <p class="muted"><code>${escapeHtml((state.settings && state.settings.config_path) || "")}</code></p>
    ${field("Import campus-office-ai.json path", "import_path", "")}
    <button type="button" class="btn ghost" id="btn-import-cfg">Import</button>`;

  await renderRuntimesPanel(langZh);
  await renderEcosystemRecommend(langZh);
  await renderMcpPanel(langZh);
  await renderSkillsSoulAgents(langZh);
  await renderSearchPanel(langZh);

  const importBtn = $("#btn-import-cfg");
  if (importBtn) {
    importBtn.onclick = async () => {
      const path = document.querySelector('[data-key="import_path"]').value.trim();
      if (!path) return;
      try {
        await api("/api/settings/import", { method: "POST", body: JSON.stringify({ path }) });
        $("#settings-status").textContent = t("imported");
        renderControl();
      } catch (e) {
        $("#settings-status").textContent = e.message;
      }
    };
  }

  // keep ali defaults in form for save
  if (!document.querySelector('[data-key="ali.default_route"]')) {
    const hidden = document.createElement("input");
    hidden.type = "hidden";
    hidden.setAttribute("data-key", "ali.default_route");
    hidden.value = ali.default_route || "office";
    $("#ctab-appearance").appendChild(hidden);
  }
}

async function renderSchedulePanel(langZh) {
  const panel = $("#ctab-schedule");
  if (!panel) return;
  let data = { tasks: [], builtins: [], defaults: {} };
  try { data = await api("/api/schedule"); } catch (_) {}
  const d = data.defaults || {};
  panel.innerHTML = `
    <h4>${langZh ? "定时复盘 / 进化" : "Review & evolve schedule"}</h4>
    <p class="muted">${langZh ? "夜间复盘与早间进化简报可改时间；也可添加自定义定时任务。" : "Configure nightly/morning hours and custom jobs."}</p>
    <div class="grid-2">
      <label class="field"><span>${langZh ? "夜间复盘（时）" : "Nightly hour"}</span>
        <input type="number" min="0" max="23" id="sched-nightly" value="${escapeHtml(String(d.nightly_hour ?? 0))}" />
      </label>
      <label class="field"><span>${langZh ? "早间进化（时）" : "Morning hour"}</span>
        <input type="number" min="0" max="23" id="sched-morning" value="${escapeHtml(String(d.morning_hour ?? 7))}" />
      </label>
    </div>
    <button type="button" class="btn primary" id="btn-sched-defaults">${langZh ? "保存时间" : "Save hours"}</button>
    <h4>${langZh ? "内置任务" : "Built-ins"}</h4>
    <div class="skill-list">${(data.builtins || []).map((t) => `
      <div class="skill-row"><div><strong>${escapeHtml(langZh ? t.label : t.label_en)}</strong>
        <div class="muted">${String(t.hour).padStart(2,"0")}:00 · ${escapeHtml(t.kind)}</div></div></div>`).join("")}</div>
    <h4>${langZh ? "自定义定时任务" : "Custom tasks"}</h4>
    <div class="grid-2">
      <label class="field"><span>${langZh ? "名称" : "Label"}</span><input id="task-label" type="text" /></label>
      <label class="field"><span>${langZh ? "类型" : "Kind"}</span>
        <select id="task-kind"><option value="custom">custom</option><option value="review">review</option><option value="evolve">evolve</option></select>
      </label>
      <label class="field"><span>${langZh ? "时" : "Hour"}</span><input id="task-hour" type="number" min="0" max="23" value="9" /></label>
      <label class="field"><span>${langZh ? "分" : "Minute"}</span><input id="task-minute" type="number" min="0" max="59" value="0" /></label>
    </div>
    <label class="field"><span>${langZh ? "提示词 / 说明" : "Prompt"}</span><textarea id="task-prompt" rows="3"></textarea></label>
    <button type="button" class="btn primary" id="btn-task-add">${langZh ? "添加任务" : "Add task"}</button>
    <div class="skill-list" style="margin-top:10px">${(data.tasks || []).map((t) => `
      <div class="skill-row"><div><strong>${escapeHtml(t.label || t.id)}</strong>
        <div class="muted">${String(t.hour).padStart(2,"0")}:${String(t.minute||0).padStart(2,"0")} · ${escapeHtml(t.kind)} ${t.enabled === false ? "(off)" : ""}</div></div>
        <div class="skill-actions"><button type="button" class="btn ghost chip" data-del-task="${escapeHtml(t.id)}">${langZh ? "删除" : "Delete"}</button></div>
      </div>`).join("") || `<p class="muted">${langZh ? "暂无自定义任务" : "No custom tasks"}</p>`}</div>`;
  $("#btn-sched-defaults")?.addEventListener("click", async () => {
    try {
      await api("/api/schedule", {
        method: "POST",
        body: JSON.stringify({
          nightly_hour: Number($("#sched-nightly")?.value || 0),
          morning_hour: Number($("#sched-morning")?.value || 7),
        }),
      });
      $("#settings-status").textContent = langZh ? "定时时间已保存" : "Schedule hours saved";
      renderControl();
    } catch (e) { $("#settings-status").textContent = e.message; }
  });
  $("#btn-task-add")?.addEventListener("click", async () => {
    try {
      await api("/api/schedule", {
        method: "POST",
        body: JSON.stringify({
          label: $("#task-label")?.value || "自定义任务",
          kind: $("#task-kind")?.value || "custom",
          hour: Number($("#task-hour")?.value || 9),
          minute: Number($("#task-minute")?.value || 0),
          prompt: $("#task-prompt")?.value || "",
          enabled: true,
        }),
      });
      renderControl();
    } catch (e) { $("#settings-status").textContent = e.message; }
  });
  panel.querySelectorAll("[data-del-task]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api(`/api/schedule/${btn.dataset.delTask}`, { method: "DELETE" });
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });
}

async function renderRuntimesPanel(langZh) {
  const panel = $("#ctab-runtimes");
  if (!panel) return;
  let data = { runtimes: [], active: "auto", auto_runtime: "hermes", resolved: "direct", linked: "hermes", os: {}, agent_cli_home: "" };
  try { data = await api("/api/runtimes"); } catch (_) {}
  const osKind = (data.os && data.os.kind) || data.platform || "";
  const autoPrefer = data.auto_runtime || "hermes";
  const autoLabel = data.resolved || autoPrefer || "direct";
  const refreshAfterRuntimeChange = async (msg) => {
    $("#settings-status").textContent = msg;
    const status = await api("/api/status");
    state.status = status;
    renderAgent(status);
    renderControl();
  };
  panel.innerHTML = `
    <h4>Agent Hub · Claws</h4>
    <p class="muted">${langZh
      ? `系统自动识别：<strong>${escapeHtml(osKind)}</strong> · Hub 操作界面 · Claw 原生目录（<code>~/.hermes</code> / <code>~/.openclaw</code> / <code>~/.nanobot</code>）· 聊天默认<strong>快路径 Direct 流式</strong>。`
      : `OS detected: <strong>${escapeHtml(osKind)}</strong> · Hub control UI · native claw homes · chat defaults to <strong>fast Direct streaming</strong>.`}</p>
    <p class="muted">${langZh
      ? "聊天窗口通用 Direct LLM；Hermes 走工作流。OpenSquilla/科研/知识库见「生态」页。"
      : "Chat uses universal Direct LLM; Hermes for workflows. See Ecosystem tab for OpenSquilla / science / knowledge kits."}</p>
    <label class="field"><span>${langZh ? "当前 Claw" : "Active Claw"}</span>
      <select id="runtime-active">
        <option value="auto" ${data.active === "auto" ? "selected" : ""}>auto → ${escapeHtml(autoLabel)}</option>
        ${(data.runtimes || []).map((r) =>
          `<option value="${escapeHtml(r.id)}" ${data.active === r.id ? "selected" : ""}>${escapeHtml(langZh ? (r.label_zh || r.label) : r.label)}${r.linked ? (langZh ? " · 已连接" : " · linked") : ""}</option>`
        ).join("")}
      </select>
    </label>
    <label class="field" id="runtime-auto-wrap"><span>${langZh ? "auto 默认指向" : "auto prefers"}</span>
      <select id="runtime-auto-prefer">
        ${(data.runtimes || []).map((r) =>
          `<option value="${escapeHtml(r.id)}" ${autoPrefer === r.id ? "selected" : ""}>${escapeHtml(langZh ? (r.label_zh || r.label) : r.label)}</option>`
        ).join("")}
      </select>
    </label>
    <div class="row gap" style="justify-content:flex-start;margin:8px 0 14px;flex-wrap:wrap">
      <button type="button" class="btn primary" id="btn-runtime-set">${langZh ? "设为当前" : "Set active"}</button>
      <button type="button" class="btn primary" id="btn-runtime-connect">${langZh ? "连接" : "Connect"}</button>
      <button type="button" class="btn ghost" id="btn-runtime-disconnect">${langZh ? "解除" : "Disconnect"}</button>
      <button type="button" class="btn primary" id="btn-runtime-upgrade">${langZh ? "一键升级" : "One-click upgrade"}</button>
      <button type="button" class="btn primary" id="btn-sync-llm">${langZh ? "同步 LLM" : "Sync LLM"}</button>
      <button type="button" class="btn ghost" id="btn-sync-hermes">${langZh ? "同步到 Hermes" : "Sync to Hermes"}</button>
    </div>
    <p class="muted">${langZh
      ? "「连接」把所选 Claw 设为 Hub 唯一链接（并写入 auto 偏好）；「解除」取消链接并回退到 auto → 直连。「auto 默认指向」可单独改个人偏好。"
      : "Connect links one Claw for Hub use (and sets auto preference). Disconnect unlinks and falls back to auto → Direct. “auto prefers” is your personal default."}</p>
    <p class="muted">${langZh
      ? "「一键升级」升级上方所选 Claw 到最新版（需已安装）；进度见下方日志。"
      : "One-click upgrade updates the selected Claw to latest (must be installed); see log below."}</p>
    <p class="muted">${langZh
      ? "「同步 LLM」把控制中心的 Provider / API Key / 模型写入上方所选 Claw（OpenClaw / NanoBot / Hermes 等）的配置；「同步到 Hermes」仅写入 Hermes。"
      : "Sync LLM writes Hub provider/API key/model into the selected Claw (OpenClaw / NanoBot / Hermes…). Sync to Hermes only updates Hermes homes."}</p>
    <div class="webui-bridge-card" id="webui-bridge-card">
      <h4>${langZh ? "Hermes-WebUI 深度会话" : "Hermes-WebUI deep session"}</h4>
      <p class="muted" id="webui-bridge-status">${langZh ? "检测中…" : "Checking…"}</p>
      <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap">
        <button type="button" class="btn primary" id="btn-webui-start">${langZh ? "启动 WebUI" : "Start WebUI"}</button>
        <button type="button" class="btn ghost" id="btn-webui-open-panel">${langZh ? "打开深度会话" : "Open deep session"}</button>
        <button type="button" class="btn ghost" id="btn-webui-stop">${langZh ? "停止" : "Stop"}</button>
      </div>
    </div>
    <div class="skill-list" id="runtime-list"></div>
    <div id="runtime-install-progress" class="hidden"></div>
    <pre id="runtime-install-log" class="install-log muted"></pre>`;

  const syncAutoPreferVisibility = () => {
    const wrap = $("#runtime-auto-wrap");
    const active = $("#runtime-active")?.value || "auto";
    if (wrap) wrap.style.display = active === "auto" ? "" : "none";
  };
  syncAutoPreferVisibility();
  $("#runtime-active")?.addEventListener("change", syncAutoPreferVisibility);

  const list = $("#runtime-list");
  (data.runtimes || []).forEach((r) => {
    const row = document.createElement("div");
    row.className = "skill-row runtime-row";
    const title = langZh ? (r.label_zh || r.label) : r.label;
    const desc = langZh ? (r.desc_zh || r.desc) : r.desc;
    const det = r.detect || {};
    const cmds = (r.install && r.install.resolved_commands && r.install.resolved_commands.length)
      ? r.install.resolved_commands
      : ((osKind === "windows") ? (r.install.windows || []) : (r.install.posix || []));
    const status = det.installed
      ? `<span class="ok">installed</span>`
      : `<span class="bad">missing</span>`;
    const linkedBadge = r.linked
      ? (langZh ? ` <span class="ok">已连接</span>` : ` <span class="ok">linked</span>`)
      : "";
    const verRaw = (r.version || "").trim();
    const verLabel = verRaw || (langZh ? "—" : "unknown");
    const upgradedAt = (r.last_upgraded_at || "").trim();
    const installedAt = (r.last_installed_at || "").trim();
    const formatClawTime = (iso) => {
      if (!iso) return "";
      const ms = Date.parse(iso);
      if (!Number.isFinite(ms)) return iso;
      try {
        return new Date(ms).toLocaleString(langZh ? "zh-CN" : undefined);
      } catch (_) {
        return iso;
      }
    };
    let timeLabel = "—";
    if (upgradedAt) {
      timeLabel = formatClawTime(upgradedAt);
    } else if (installedAt) {
      timeLabel = formatClawTime(installedAt) + (langZh ? "（安装）" : " (installed)");
    }
    const metaLine = langZh
      ? `目前的版本：<code>${escapeHtml(verLabel)}</code> · 上次升级时间：${escapeHtml(timeLabel)}`
      : `Current version: <code>${escapeHtml(verLabel)}</code> · Last upgrade: ${escapeHtml(timeLabel)}`;
    const target = (r.install && r.install.target_dir) || "";
    row.innerHTML = `
      <div style="flex:1;min-width:0">
        <strong>${escapeHtml(title)}</strong> ${status}${linkedBadge}
        <div class="muted">${escapeHtml(desc || "")}</div>
        <div class="muted claw-meta">${metaLine}</div>
        ${target ? `<div class="muted">→ <code>${escapeHtml(target)}</code></div>` : ""}
        <div class="muted">${r.homepage ? `<a href="${escapeHtml(r.homepage)}" target="_blank" rel="noopener">GitHub</a>` : ""}
          ${r.docs ? ` · <a href="${escapeHtml(r.docs)}" target="_blank" rel="noopener">Docs</a>` : ""}
          ${r.requires && r.requires.length ? ` · requires: ${r.requires.join(", ")}` : ""}</div>
        ${cmds.length ? `<code class="muted" style="display:block;margin-top:6px;white-space:pre-wrap">${escapeHtml(cmds.join("\n"))}</code>` : ""}
        ${r.install.notes_zh || r.install.notes_en ? `<div class="muted">${escapeHtml(langZh ? (r.install.notes_zh || r.install.notes_en) : (r.install.notes_en || r.install.notes_zh))}</div>` : ""}
        ${r.install.marketplace_hint_zh && langZh ? `<div class="muted">${escapeHtml(r.install.marketplace_hint_zh)}</div>` : ""}
      </div>
      <div style="display:flex;flex-direction:column;gap:6px">
        ${r.id !== "direct"
          ? (r.linked
            ? `<button type="button" class="btn ghost chip" data-disconnect="${escapeHtml(r.id)}">${langZh ? "解除" : "Disconnect"}</button>`
            : `<button type="button" class="btn primary chip" data-connect="${escapeHtml(r.id)}">${langZh ? "连接" : "Connect"}</button>`)
          : ""}
        <button type="button" class="btn ghost chip" data-opt="${escapeHtml(r.id)}">${langZh ? "自动优化" : "Optimize"}</button>
        ${r.id !== "direct"
          ? `<button type="button" class="btn ghost chip" data-evo-rt="${escapeHtml(r.id)}">${langZh ? "自我进化" : "Evolve"}</button>`
          : ""}
        ${r.upgrade && r.upgrade.supported && (det.installed || r.upgrade.installed)
          ? `<button type="button" class="btn primary chip" data-upgrade="${escapeHtml(r.id)}">${langZh ? "升级" : "Upgrade"}</button>`
          : ""}
        ${(r.install_kind === "script" || (cmds.length && r.install_kind !== "none")) && cmds.length && !r.install.interactive
          ? `<button type="button" class="btn primary chip" data-inst="${escapeHtml(r.id)}">${langZh ? "一键安装" : "Install"}</button>`
          : `<button type="button" class="btn ghost chip" data-copy="${escapeHtml(r.id)}">${langZh ? "复制命令" : "Copy cmds"}</button>`}
      </div>`;
    list.appendChild(row);
  });

  const refreshWebuiBridgeStatus = async () => {
    const el = $("#webui-bridge-status");
    try {
      const st = await api("/api/webui/status");
      if (!el) return;
      const root = st.root_found ? (st.root || "") : (langZh ? "未找到仓库" : "root missing");
      el.innerHTML = langZh
        ? `状态：<strong>${st.healthy ? "在线" : (st.running ? "启动中" : "离线")}</strong> · 端口 <code>${escapeHtml(String(st.port || ""))}</code> · PID ${escapeHtml(String(st.pid || "—"))}<br/>HOME <code>${escapeHtml(st.hermes_home || "")}</code><br/>WebUI <code>${escapeHtml(root)}</code>`
        : `Status: <strong>${st.healthy ? "online" : (st.running ? "starting" : "offline")}</strong> · port <code>${escapeHtml(String(st.port || ""))}</code> · PID ${escapeHtml(String(st.pid || "—"))}<br/>HOME <code>${escapeHtml(st.hermes_home || "")}</code><br/>WebUI <code>${escapeHtml(root)}</code>`;
    } catch (e) {
      if (el) el.textContent = e.message;
    }
  };
  refreshWebuiBridgeStatus();
  $("#btn-webui-start")?.addEventListener("click", async () => {
    try {
      $("#settings-status").textContent = t("webui.starting");
      const res = await api("/api/webui/start", { method: "POST", body: JSON.stringify({ sync: true }) });
      $("#settings-status").textContent = res.healthy ? t("webui.ready") : (res.error_zh || res.error || t("webui.failed"));
      await refreshWebuiBridgeStatus();
    } catch (e) { $("#settings-status").textContent = e.message; }
  });
  $("#btn-webui-open-panel")?.addEventListener("click", () => openDeepWebui().catch((e) => {
    $("#settings-status").textContent = e.message;
  }));
  $("#btn-webui-stop")?.addEventListener("click", async () => {
    try {
      await api("/api/webui/stop", { method: "POST", body: "{}" });
      $("#settings-status").textContent = langZh ? "已停止 WebUI" : "WebUI stopped";
      await refreshWebuiBridgeStatus();
    } catch (e) { $("#settings-status").textContent = e.message; }
  });

  $("#btn-runtime-set").onclick = async () => {
    try {
      const rt = $("#runtime-active").value;
      const prefer = $("#runtime-auto-prefer")?.value;
      await api("/api/runtimes/active", { method: "POST", body: JSON.stringify({ runtime: rt }) });
      if (rt === "auto" && prefer) {
        await api("/api/runtimes/auto", { method: "POST", body: JSON.stringify({ runtime: prefer }) });
      }
      await refreshAfterRuntimeChange(`Claw → ${rt}`);
    } catch (e) { $("#settings-status").textContent = e.message; }
  };

  $("#runtime-auto-prefer")?.addEventListener("change", async () => {
    try {
      const prefer = $("#runtime-auto-prefer").value;
      await api("/api/runtimes/auto", { method: "POST", body: JSON.stringify({ runtime: prefer }) });
      await refreshAfterRuntimeChange(langZh ? `auto 默认 → ${prefer}` : `auto prefers → ${prefer}`);
    } catch (e) { $("#settings-status").textContent = e.message; }
  });

  $("#btn-runtime-connect").onclick = async () => {
    try {
      let rt = $("#runtime-active")?.value || "";
      if (rt === "auto") rt = $("#runtime-auto-prefer")?.value || data.auto_runtime || "";
      if (!rt || rt === "auto") throw new Error(langZh ? "请先选择要连接的 Claw" : "Select a Claw to connect");
      await api("/api/runtimes/connect", { method: "POST", body: JSON.stringify({ runtime: rt }) });
      await refreshAfterRuntimeChange(langZh ? `已连接 ${rt}` : `Connected ${rt}`);
    } catch (e) { $("#settings-status").textContent = e.message; }
  };

  $("#btn-runtime-disconnect").onclick = async () => {
    try {
      let rt = $("#runtime-active")?.value || "";
      if (rt === "auto") rt = data.linked || data.auto_runtime || "";
      await api("/api/runtimes/disconnect", { method: "POST", body: JSON.stringify({ runtime: rt }) });
      await refreshAfterRuntimeChange(langZh ? `已解除 ${rt || ""}` : `Disconnected ${rt || ""}`);
    } catch (e) { $("#settings-status").textContent = e.message; }
  };

  const startRuntimeUpgrade = async (rt) => {
    const logEl = $("#runtime-install-log");
    const progEl = $("#runtime-install-progress");
    if (!rt || rt === "auto" || rt === "direct") {
      throw new Error(langZh ? "请选择可升级的 Claw（非 auto / 直连）" : "Pick an upgradable Claw (not auto/direct)");
    }
    $("#settings-status").textContent = langZh ? "升级中…" : "Upgrading…";
    updateInstallProgressEl(progEl, { status: "running", step: "prepare", pct: 5 }, langZh);
    const res = await api("/api/runtimes/upgrade", { method: "POST", body: JSON.stringify({ runtime: rt }) });
    const jobId = res.job && res.job.id;
    if (!jobId) throw new Error("no job");
    updateInstallProgressEl(progEl, res.job, langZh);
    const poll = async () => {
      const st = await api(`/api/runtimes/jobs/${jobId}`);
      const job = st.job || {};
      updateInstallProgressEl(progEl, job, langZh);
      if (logEl) logEl.textContent = job.log || "";
      if (job.status === "running") {
        setTimeout(poll, 1200);
        return;
      }
      $("#settings-status").textContent = job.status === "ok"
        ? (langZh ? "升级完成" : "Upgraded")
        : (job.error || job.status);
      renderControl();
    };
    poll();
  };

  $("#btn-runtime-upgrade")?.addEventListener("click", async () => {
    try {
      let rt = $("#runtime-active")?.value || "auto";
      if (rt === "auto") rt = data.resolved || data.auto_runtime || "";
      await startRuntimeUpgrade(rt);
    } catch (e) { $("#settings-status").textContent = e.message; }
  });

  panel.querySelectorAll("[data-upgrade]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await startRuntimeUpgrade(btn.dataset.upgrade);
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  $("#btn-sync-llm")?.addEventListener("click", async () => {
    try {
      const rt = $("#runtime-active")?.value || "auto";
      $("#settings-status").textContent = langZh ? "同步 LLM…" : "Syncing LLM…";
      const res = await api("/api/runtimes/sync-llm", {
        method: "POST",
        body: JSON.stringify({ runtime: rt }),
      });
      const note = langZh
        ? (res.note_zh || res.error_zh || (res.ok ? "已同步 LLM" : "同步失败"))
        : (res.note_en || res.error_en || (res.ok ? "LLM synced" : "Sync failed"));
      $("#settings-status").textContent = note;
    } catch (e) {
      $("#settings-status").textContent = e.message;
    }
  });

  $("#btn-sync-hermes")?.addEventListener("click", async () => {
    try {
      const rt = $("#runtime-active")?.value || "auto";
      $("#settings-status").textContent = langZh ? "同步 LLM…" : "Syncing LLM…";
      const res = await api("/api/runtimes/sync-llm", {
        method: "POST",
        body: JSON.stringify({ runtime: rt }),
      });
      const note = langZh ? (res.note_zh || res.error_zh || "已同步") : (res.note_en || res.error_en || "Synced");
      $("#settings-status").textContent = note;
    } catch (e) {
      $("#settings-status").textContent = e.message;
    }
  });

  panel.querySelectorAll("[data-connect]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api("/api/runtimes/connect", { method: "POST", body: JSON.stringify({ runtime: btn.dataset.connect }) });
        await refreshAfterRuntimeChange(langZh ? `已连接 ${btn.dataset.connect}` : `Connected ${btn.dataset.connect}`);
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  panel.querySelectorAll("[data-disconnect]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api("/api/runtimes/disconnect", { method: "POST", body: JSON.stringify({ runtime: btn.dataset.disconnect }) });
        await refreshAfterRuntimeChange(langZh ? `已解除 ${btn.dataset.disconnect}` : `Disconnected ${btn.dataset.disconnect}`);
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  panel.querySelectorAll("[data-opt]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        const res = await api("/api/runtimes/optimize", { method: "POST", body: JSON.stringify({ runtime: btn.dataset.opt }) });
        $("#settings-status").textContent = langZh ? (res.note_zh || "已优化") : (res.note_en || "Optimized");
        const status = await api("/api/status");
        state.status = status;
        renderAgent(status);
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  panel.querySelectorAll("[data-evo-rt]").forEach((btn) => {
    btn.onclick = () => startEvolutionWizard("claw", btn.dataset.evoRt, langZh);
  });

  panel.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.onclick = async () => {
      const r = (data.runtimes || []).find((x) => x.id === btn.dataset.copy);
      if (!r) return;
      const cmds = (r.install && r.install.resolved_commands && r.install.resolved_commands.length)
        ? r.install.resolved_commands
        : (r.install.posix || r.install.windows || []);
      const text = cmds.join("\n") || r.docs || r.homepage || "";
      try { await navigator.clipboard.writeText(text); $("#settings-status").textContent = t("msg.copied"); } catch (_) {}
    };
  });

  panel.querySelectorAll("[data-inst]").forEach((btn) => {
    btn.onclick = async () => {
      const logEl = $("#runtime-install-log");
      const progEl = $("#runtime-install-progress");
      try {
        $("#settings-status").textContent = langZh ? "安装中…" : "Installing…";
        updateInstallProgressEl(progEl, { status: "running", step: "prepare", pct: 5 }, langZh);
        const res = await api("/api/runtimes/install", { method: "POST", body: JSON.stringify({ runtime: btn.dataset.inst }) });
        const jobId = res.job && res.job.id;
        if (!jobId) throw new Error("no job");
        updateInstallProgressEl(progEl, res.job, langZh);
        const poll = async () => {
          const st = await api(`/api/runtimes/jobs/${jobId}`);
          const job = st.job || {};
          updateInstallProgressEl(progEl, job, langZh);
          if (logEl) logEl.textContent = job.log || "";
          if (job.status === "running") {
            setTimeout(poll, 1200);
            return;
          }
          $("#settings-status").textContent = job.status === "ok"
            ? (langZh ? "安装完成并已验证" : "Installed & verified")
            : (job.error || job.status);
          renderControl();
        };
        poll();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });
}

function githubStatusLabel(status, langZh) {
  const map = langZh
    ? { live: "GitHub 实时", curated: "本地精选（GitHub 不可用）", cache: "今日缓存", timeout: "GitHub 超时 · 已回退" }
    : { live: "Live from GitHub", curated: "Curated (GitHub unavailable)", cache: "Today's cache", timeout: "GitHub timeout · fallback" };
  return map[status] || (langZh ? "推荐列表" : "Recommendations");
}

function renderAgentModelRows(models, langZh) {
  const list = models || [];
  if (!list.length) return `<p class="muted">—</p>`;
  return `<div class="skill-list">${list.map((m) => {
    const role = m.role || "main";
    const prov = m.provider || "";
    const docs = m.docs || "";
    return `<div class="skill-row">
      <div style="flex:1">
        <strong>${escapeHtml(m.label || m.id)}</strong>
        <div class="muted"><code>${escapeHtml(m.id || "")}</code> · ${escapeHtml(prov)} · ${escapeHtml(role)}</div>
      </div>
      <div class="skill-actions">
        ${docs ? `<a class="btn ghost chip" href="${escapeHtml(docs)}" target="_blank" rel="noopener">${langZh ? "文档" : "Docs"}</a>` : ""}
        <button type="button" class="btn primary chip" data-apply-model="${escapeHtml(m.id || "")}"
          data-provider="${escapeHtml(prov)}" data-role="${escapeHtml(role)}">${langZh ? "应用" : "Apply"}</button>
      </div>
    </div>`;
  }).join("")}</div>`;
}

async function applyRecommendedModelFromBtn(btn, langZh) {
  const modelId = btn.dataset.applyModel || "";
  if (!modelId) return;
  try {
    $("#settings-status").textContent = langZh ? `正在应用 ${modelId}…` : `Applying ${modelId}…`;
    const res = await api("/api/recommend/apply-model", {
      method: "POST",
      body: JSON.stringify({
        model_id: modelId,
        provider: btn.dataset.provider || "",
        role: btn.dataset.role || "main",
        apply_provider: true,
      }),
    });
    state.settings = res;
    syncComposerFromSettings();
    const applied = (res && res.applied) || {};
    $("#settings-status").textContent = langZh
      ? (res.note_zh || `已应用 ${applied.model_id || modelId} → ${applied.slot || "main"}`)
      : (res.note_en || `Applied ${applied.model_id || modelId} → ${applied.slot || "main"}`);
    // Refresh model slot fields in Control Center models tab if present
    const slot = applied.slot || "main";
    const legacy = { fast: "qwen_fast", main: "qwen_main", vision: "qwen_vl", reasoning: "deepseek_reasoning" }[slot] || "";
    const selMain = document.querySelector(`[data-key="models.${slot}"]`) || document.querySelector(`[data-key="models.${legacy}"]`);
    if (selMain) selMain.value = modelId;
  } catch (e) {
    $("#settings-status").textContent = e.message || String(e);
  }
}

function wireApplyModelButtons(root, langZh) {
  if (!root) return;
  root.querySelectorAll("[data-apply-model]").forEach((btn) => {
    btn.onclick = () => applyRecommendedModelFromBtn(btn, langZh);
  });
}

async function refreshDailyRecommend(langZh, { stayOn } = {}) {
  const statusEl = $("#settings-status");
  if (statusEl) statusEl.textContent = langZh ? "正在刷新推荐…" : "Refreshing…";
  try {
    const rec = await api(`/api/recommend/daily?refresh=1&_=${Date.now()}`);
    await renderEcosystemRecommend(langZh);
    if (stayOn) {
      document.querySelector(`.ctab[data-ctab="${stayOn}"]`)?.click();
    }
    const gh = githubStatusLabel(rec && rec.github_status, langZh);
    if (statusEl) {
      statusEl.textContent = langZh
        ? `推荐已刷新 · ${gh} · ${(rec.github_hot || []).length} 条`
        : `Refreshed · ${gh} · ${(rec.github_hot || []).length} items`;
    }
    return rec;
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || String(e);
    throw e;
  }
}

async function renderMcpPanel(langZh) {
  const panel = $("#ctab-mcp");
  if (!panel) return;
  let data = { templates: [], items: [], path: "", note_zh: "", note_en: "" };
  try { data = await api("/api/mcp"); } catch (_) {}
  const enabled = new Set(data.enabled || []);
  panel.innerHTML = `
    <h4>MCP · Model Context Protocol</h4>
    <p class="muted">${escapeHtml(langZh ? (data.note_zh || "") : (data.note_en || ""))}</p>
    <p class="muted">${langZh ? "配置目录" : "Config"}: <code>${escapeHtml(data.path || "~/.agent-cli/mcp/servers.json")}</code>
      · Hermes: <code>hermes mcp list</code> / config.yaml <code>mcp_servers</code></p>
    <div class="row gap" style="justify-content:flex-start;margin:8px 0 12px;flex-wrap:wrap">
      <button type="button" class="btn primary" id="btn-mcp-sync">${langZh ? "同步 MCP → Hermes" : "Sync MCP → Hermes"}</button>
      <button type="button" class="btn ghost" id="btn-mcp-skills">${langZh ? "去 Skills（vibe/Codex）" : "Skills (vibe/Codex)"}</button>
    </div>
    <h4>${langZh ? "模板（GitHub / 编程 Agent）" : "Templates (GitHub / coding agents)"}</h4>
    <div class="skill-list" id="mcp-templates"></div>
    <h4>${langZh ? "已配置" : "Configured"}</h4>
    <div class="skill-list" id="mcp-items"></div>`;

  const tplList = $("#mcp-templates");
  (data.templates || []).forEach((t) => {
    const row = document.createElement("div");
    row.className = "skill-row";
    const on = enabled.has(t.id);
    row.innerHTML = `<div style="flex:1"><strong>${escapeHtml(langZh ? (t.label_zh || t.label) : t.label)}</strong>
      ${on ? `<span class="ok">${langZh ? "已启用" : "enabled"}</span>` : ""}
      <div class="muted">${escapeHtml(langZh ? (t.desc_zh || t.desc) : t.desc)}</div>
      <div class="muted">use-case: ${escapeHtml(t.use_case || "")}</div></div>
      <div class="skill-actions">
        <button type="button" class="btn ${on ? "ghost" : "primary"} chip" data-mcp-tpl="${escapeHtml(t.id)}">${on ? (langZh ? "重新写入" : "Re-add") : (langZh ? "启用模板" : "Enable")}</button>
      </div>`;
    tplList.appendChild(row);
  });
  panel.querySelectorAll("[data-mcp-tpl]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api("/api/mcp/enable", { method: "POST", body: JSON.stringify({ id: btn.dataset.mcpTpl }) });
        $("#settings-status").textContent = langZh ? "MCP 模板已启用" : "MCP template enabled";
        renderMcpPanel(langZh);
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  const itemList = $("#mcp-items");
  (data.items || []).forEach((it) => {
    const row = document.createElement("div");
    row.className = "skill-row";
    row.innerHTML = `<div style="flex:1"><strong>${escapeHtml(it.id)}</strong>
      ${it.enabled ? `<span class="ok">${langZh ? "启用中" : "on"}</span>` : `<span class="muted">${langZh ? "关闭" : "off"}</span>`}
      <div class="muted"><code>${escapeHtml(JSON.stringify(it.config || {}).slice(0, 120))}</code></div></div>
      <div class="skill-actions">
        <button type="button" class="btn ghost chip" data-mcp-tog="${escapeHtml(it.id)}" data-on="${it.enabled ? "0" : "1"}">${it.enabled ? (langZh ? "停用" : "Disable") : (langZh ? "启用" : "Enable")}</button>
      </div>`;
    itemList.appendChild(row);
  });
  if (!(data.items || []).length) {
    itemList.innerHTML = `<p class="muted">${langZh ? "尚未启用模板。点上方「启用模板」添加 GitHub / filesystem 等。" : "No servers yet — enable a template above."}</p>`;
  }
  panel.querySelectorAll("[data-mcp-tog]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await api("/api/mcp/toggle", {
          method: "POST",
          body: JSON.stringify({ id: btn.dataset.mcpTog, enabled: btn.dataset.on === "1" }),
        });
        renderMcpPanel(langZh);
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  $("#btn-mcp-sync")?.addEventListener("click", async () => {
    try {
      const res = await api("/api/mcp/sync-hermes", { method: "POST", body: "{}" });
      $("#settings-status").textContent = langZh ? (res.note_zh || "已同步") : (res.note_en || "Synced");
    } catch (e) { $("#settings-status").textContent = e.message; }
  });
  $("#btn-mcp-skills")?.addEventListener("click", () => {
    document.querySelector('.ctab[data-ctab="skills"]')?.click();
  });
}

async function startEvolutionWizard(kind, id, langZh) {
  const label = id || "";
  const ok = confirm(
    langZh
      ? `对「${label}」开始自我进化评审？\n\n流程：检查基线 → 批判/提案 → 你确认后再写入（自动备份，可回滚）。\n不会静默覆盖配置。`
      : `Start self-evolution review for "${label}"?\n\nInspect → critique/propose → confirm before write (backup + rollback).`
  );
  if (!ok) return;
  const statusEl = $("#settings-status");
  try {
    if (statusEl) statusEl.textContent = langZh ? "自我进化评审中…" : "Evolution review…";
    const res = await api("/api/evolution/start", {
      method: "POST",
      body: JSON.stringify({ kind, id }),
    });
    const runId = res.run_id;
    if (!runId) {
      if (statusEl) statusEl.textContent = res.error || (langZh ? "启动失败" : "Failed");
      return;
    }
    const poll = async () => {
      const st = await api(`/api/evolution/jobs/${runId}`);
      const run = st.run || {};
      if (run.status === "running") {
        if (statusEl) statusEl.textContent = langZh ? `评审中 · ${run.phase || ""}` : `Reviewing · ${run.phase || ""}`;
        setTimeout(poll, 1500);
        return;
      }
      if (run.status === "failed") {
        if (statusEl) statusEl.textContent = run.error || "failed";
        return;
      }
      // await_confirm — show proposals & ask apply
      let detail = { run: {} };
      try { detail = await api(`/api/evolution/runs/${runId}`); } catch (_) {}
      const full = detail.run || {};
      const proposals = full.proposals || [];
      const patchable = proposals.filter((p) => p.action === "patch" && p.proposed_content);
      const critique = (full.critique || []).slice(0, 6).map((c) => `• ${c}`).join("\n");
      const summary = full.summary || run.summary || "";
      if (!patchable.length) {
        alert(
          langZh
            ? `评审完成（无可直接应用的补丁）\n\n${summary}\n\n${critique}`
            : `Review done (no applyable patches)\n\n${summary}\n\n${critique}`
        );
        if (statusEl) statusEl.textContent = summary || (langZh ? "评审完成" : "Review done");
        return;
      }
      const applyOk = confirm(
        langZh
          ? `自我进化提案就绪（${patchable.length} 条可写入）\n\n${summary}\n\n${critique}\n\n确认应用全部补丁？将先备份原文件到 ~/.agent-cli/evolution/backups/`
          : `Evolution proposals ready (${patchable.length} patches)\n\n${summary}\n\nApply all? Originals backed up under ~/.agent-cli/evolution/backups/`
      );
      if (!applyOk) {
        if (statusEl) statusEl.textContent = langZh ? "已保留提案，未写入。可在进化历史中稍后应用。" : "Proposals kept; not applied.";
        return;
      }
      const applied = await api("/api/evolution/apply", {
        method: "POST",
        body: JSON.stringify({ run_id: runId, confirm: true }),
      });
      if (statusEl) {
        statusEl.textContent = langZh
          ? (applied.note_zh || `已应用 ${((applied.applied) || []).length} 个文件`)
          : (applied.note_en || `Applied ${((applied.applied) || []).length} files`);
      }
      if (applied.verify && applied.verify.rollback_tip) {
        // soft tip only
      }
    };
    poll();
  } catch (e) {
    if (statusEl) statusEl.textContent = e.message || String(e);
  }
}

async function renderEcosystemRecommend(langZh) {
  const ecoPanel = $("#ctab-ecosystem");
  const recPanel = $("#ctab-recommend");
  if (ecoPanel) {
    let eco = { items: [], home: "" };
    let rec = { github_hot: [], agent_models: { cn: [], global: [] } };
    let evo = { recent: [], nous: {}, claws: [] };
    try { eco = await api("/api/ecosystem"); } catch (_) {}
    try { rec = await api("/api/recommend/daily"); } catch (_) {}
    try { evo = await api("/api/evolution"); } catch (_) {}
    const ghLabel = githubStatusLabel(rec.github_status, langZh);
    const recentEvo = (evo.recent || []).slice(0, 5).map((r) => {
      const st = r.status || "";
      const when = r.started_at ? new Date(r.started_at * 1000).toLocaleString(langZh ? "zh-CN" : undefined) : "";
      return `<div class="skill-row" style="padding:8px 0">
        <div><strong>${escapeHtml(r.label || r.target_id || "")}</strong>
          <span class="muted">${escapeHtml(st)}</span>
          <div class="muted">${escapeHtml(r.summary || "")} · ${escapeHtml(when)} · ${escapeHtml(String(r.proposal_count || 0))} proposals</div>
        </div>
        <div class="skill-actions">
          ${(st === "await_confirm" || st === "partial")
            ? `<button type="button" class="btn primary chip" data-evo-apply="${escapeHtml(r.id)}">${langZh ? "确认应用" : "Apply"}</button>`
            : ""}
          ${st === "applied"
            ? `<button type="button" class="btn ghost chip" data-evo-rb="${escapeHtml(r.id)}">${langZh ? "回滚" : "Rollback"}</button>`
            : ""}
        </div>
      </div>`;
    }).join("") || `<p class="muted">${langZh ? "尚无进化记录 — 点下方卡片「自我进化」开始" : "No evolution runs yet"}</p>`;
    ecoPanel.innerHTML = `
      <h4>${langZh ? "生态并行目录" : "Ecosystem (parallel)"}</h4>
      <p class="muted">${langZh ? "OpenSquilla · OpenScience · scientific-agent-skills 默认已自动激活；Obsidian / Notion / 自我进化引擎安装后可手动激活。全部装在 Agent Hub 主目录下。" : "OpenSquilla · OpenScience · scientific-agent-skills auto-activate by default; Obsidian / Notion / self-evolution install then activate. All under Agent Hub home."}
      <br/><code>${escapeHtml(eco.home || "")}</code></p>
      <div class="eco-evolution" style="margin:12px 0 18px;padding:12px 0;border-top:1px solid var(--border, #ddd);border-bottom:1px solid var(--border, #ddd)">
        <h4 style="margin:0 0 6px">${langZh ? "自我进化 / 自我迭代" : "Self-evolution"}</h4>
        <p class="muted" style="margin:0 0 8px">${langZh
          ? "引导式循环（参考 Nous hermes-agent-self-evolution）：批判 → 提案 → 确认写入 → 验证 → 变更记录。适用于任意 Claw 与已装生态包；不会静默覆盖。"
          : "Guided loop (Nous hermes-agent-self-evolution): critique → propose → confirm → verify → changelog. Works for any claw / kit; no silent overwrites."}</p>
        <p class="muted" style="margin:0 0 8px">${escapeHtml(langZh ? (evo.nous && evo.nous.note_zh) || "" : (evo.nous && evo.nous.note_en) || "")}
          ${(evo.nous && evo.nous.repo) ? ` · <a href="${escapeHtml(evo.nous.repo)}" target="_blank" rel="noopener">Nous repo</a>` : ""}</p>
        <div class="row gap" style="flex-wrap:wrap;margin-bottom:8px">
          <button type="button" class="btn primary chip" data-evo-claw="hermes">${langZh ? "进化 Hermes" : "Evolve Hermes"}</button>
          <button type="button" class="btn ghost chip" data-evo-claw="openclaw">${langZh ? "进化 OpenClaw" : "Evolve OpenClaw"}</button>
        </div>
        <h4 style="margin:10px 0 4px;font-size:0.95em">${langZh ? "近期进化" : "Recent runs"}</h4>
        <div id="eco-evo-history">${recentEvo}</div>
        <pre id="eco-evo-log" class="install-log muted"></pre>
      </div>
      <div class="skill-list" id="eco-list"></div>
      <div id="eco-install-progress" class="hidden"></div>
      <pre id="eco-log" class="install-log muted"></pre>
      <div class="eco-daily">
        <div class="row gap" style="justify-content:space-between;align-items:center;flex-wrap:wrap;margin-top:16px">
          <h4 style="margin:0">${langZh ? "每日推荐 · GitHub" : "Daily · GitHub"}</h4>
          <button type="button" class="btn ghost chip" id="btn-eco-rec-refresh">${langZh ? "刷新推荐" : "Refresh"}</button>
        </div>
        <p class="muted">${escapeHtml(langZh ? (rec.note_zh || "生态页同步展示每日推荐") : (rec.note_en || "Daily picks mirrored here"))}
          · ${escapeHtml(ghLabel)}</p>
        <h4>GitHub · Skills</h4>
        <div class="skill-list" id="eco-gh">${(rec.github_hot || []).slice(0, 6).map((g) => `
          <div class="skill-row"><div><strong>${escapeHtml(g.name || "")}</strong>
            <div class="muted">${escapeHtml(g.desc || "")} · ⭐ ${escapeHtml(String(g.stars || ""))}</div></div>
            <div class="skill-actions">${g.url ? `<a class="btn ghost chip" href="${escapeHtml(g.url)}" target="_blank" rel="noopener">${langZh ? "打开" : "Open"}</a>` : ""}</div>
          </div>`).join("") || `<p class="muted">${langZh ? "暂无（可点刷新；网络不通时用本地精选）" : "Empty — refresh uses curated fallback if GitHub is blocked"}</p>`}</div>
        <h4>${langZh ? "热门 Agent 模型（推荐配置，非自动安装）" : "Popular agent models (configure — not auto-install)"}</h4>
        <p class="muted">${langZh ? "点「应用」写入 models 槽位并设为当前模型；需已配置对应 Provider / API Key。" : "Apply writes into model slots + current model; provider/API key still required."}</p>
        <div class="grid-2">
          <div><strong>${langZh ? "国内" : "CN"}</strong>${renderAgentModelRows((rec.agent_models && rec.agent_models.cn) || [], langZh)}</div>
          <div><strong>${langZh ? "国外" : "Global"}</strong>${renderAgentModelRows((rec.agent_models && rec.agent_models.global) || [], langZh)}</div>
        </div>
      </div>`;
    const list = $("#eco-list");
    (eco.items || []).forEach((e) => {
      const row = document.createElement("div");
      row.className = "skill-row";
      const title = langZh ? (e.label_zh || e.label) : e.label;
      const desc = langZh ? (e.desc_zh || e.desc) : e.desc;
      const ok = e.detect && e.detect.installed;
      const act = e.detect && e.detect.activated;
      const statusBits = [];
      if (ok) statusBits.push(`<span class="ok">${langZh ? "已安装" : "installed"}</span>`);
      else statusBits.push(`<span class="bad">${langZh ? "未安装" : "missing"}</span>`);
      if (act) statusBits.push(`<span class="ok">${langZh ? (e.detect && e.detect.soft ? "已激活（软）" : "已激活") : (e.detect && e.detect.soft ? "activated (soft)" : "activated")}</span>`);
      else if (ok) statusBits.push(`<span class="muted">${langZh ? "未激活" : "inactive"}</span>`);
      const appLine = e.detect && e.detect.app
        ? `<div class="muted">App: <code>${escapeHtml(e.detect.app)}</code>${e.detect.version ? ` · v${escapeHtml(e.detect.version)}` : ""}</div>`
        : "";
      const home = e.homepage || e.docs || "";
      const canToggle = ok || act || e.auto_activate;
      row.innerHTML = `<div style="flex:1"><strong>${escapeHtml(title)}</strong>
        ${statusBits.join(" ")}
        <div class="muted">${escapeHtml(desc || "")}</div>
        ${appLine}
        <div class="muted">${home ? `<a href="${escapeHtml(home)}" target="_blank" rel="noopener">${langZh ? "主页/文档" : "Home/Docs"}</a>` : ""}
          ${e.detect && e.detect.path ? ` · <code>${escapeHtml(e.detect.path)}</code>` : ""}</div></div>
        <div class="skill-actions">
          ${canToggle ? `<button type="button" class="btn ${act ? "ghost" : "primary"} chip" data-eco-act="${escapeHtml(e.id)}" data-eco-on="${act ? "0" : "1"}">${act ? (langZh ? "取消激活" : "Deactivate") : (langZh ? "激活/使用" : "Activate")}</button>` : ""}
          <button type="button" class="btn ghost chip" data-evo-eco="${escapeHtml(e.id)}">${langZh ? "自我进化" : "Evolve"}</button>
          ${home ? `<a class="btn ghost chip" href="${escapeHtml(home)}" target="_blank" rel="noopener">${langZh ? "打开" : "Open"}</a>` : ""}
          <button type="button" class="btn primary chip" data-eco="${escapeHtml(e.id)}">${ok ? (langZh ? "重新安装" : "Reinstall") : (langZh ? "一键安装" : "Install")}</button>
        </div>`;
      list.appendChild(row);
    });
    ecoPanel.querySelectorAll("[data-eco-act]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          const on = btn.dataset.ecoOn === "1";
          const res = await api("/api/ecosystem/activate", {
            method: "POST",
            body: JSON.stringify({ id: btn.dataset.ecoAct, active: on }),
          });
          $("#settings-status").textContent = langZh ? (res.note_zh || "已更新") : (res.note_en || "Updated");
          renderControl();
        } catch (e) { $("#settings-status").textContent = e.message; }
      };
    });
    ecoPanel.querySelectorAll("[data-eco]").forEach((btn) => {
      btn.onclick = async () => {
        const log = $("#eco-log");
        const progEl = $("#eco-install-progress");
        try {
          $("#settings-status").textContent = langZh ? "安装中…" : "Installing…";
          updateInstallProgressEl(progEl, { status: "running", step: "prepare", pct: 5 }, langZh);
          const res = await api("/api/ecosystem/install", { method: "POST", body: JSON.stringify({ id: btn.dataset.eco }) });
          const jobId = res.job && res.job.id;
          updateInstallProgressEl(progEl, res.job || {}, langZh);
          if (!jobId) {
            if (log) log.textContent = JSON.stringify(res.job || res, null, 2);
            setTimeout(() => renderControl(), 2000);
            return;
          }
          const poll = async () => {
            const st = await api(`/api/ecosystem/jobs/${jobId}`);
            const job = st.job || {};
            updateInstallProgressEl(progEl, job, langZh);
            if (log) log.textContent = job.log || "";
            if (job.status === "running") {
              setTimeout(poll, 1200);
              return;
            }
            $("#settings-status").textContent = job.status === "ok"
              ? (langZh ? "安装完成并已验证" : "Installed & verified")
              : (job.error || job.status);
            renderControl();
          };
          poll();
        } catch (e) { $("#settings-status").textContent = e.message; }
      };
    });
    ecoPanel.querySelectorAll("[data-evo-eco]").forEach((btn) => {
      btn.onclick = () => startEvolutionWizard("ecosystem", btn.dataset.evoEco, langZh);
    });
    ecoPanel.querySelectorAll("[data-evo-claw]").forEach((btn) => {
      btn.onclick = () => startEvolutionWizard("claw", btn.dataset.evoClaw, langZh);
    });
    ecoPanel.querySelectorAll("[data-evo-apply]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm(langZh ? "确认应用该次进化提案？" : "Apply this evolution run?")) return;
        try {
          const res = await api("/api/evolution/apply", {
            method: "POST",
            body: JSON.stringify({ run_id: btn.dataset.evoApply, confirm: true }),
          });
          $("#settings-status").textContent = langZh ? (res.note_zh || "已应用") : (res.note_en || "Applied");
          renderControl();
        } catch (e) { $("#settings-status").textContent = e.message; }
      };
    });
    ecoPanel.querySelectorAll("[data-evo-rb]").forEach((btn) => {
      btn.onclick = async () => {
        if (!confirm(langZh ? "从备份回滚该次写入？" : "Rollback this run from backup?")) return;
        try {
          const res = await api("/api/evolution/rollback", {
            method: "POST",
            body: JSON.stringify({ run_id: btn.dataset.evoRb }),
          });
          $("#settings-status").textContent = langZh
            ? `已回滚 ${(res.restored || []).length} 个文件`
            : `Rolled back ${(res.restored || []).length} files`;
          renderControl();
        } catch (e) { $("#settings-status").textContent = e.message; }
      };
    });
    wireApplyModelButtons(ecoPanel, langZh);
    $("#btn-eco-rec-refresh")?.addEventListener("click", () => {
      refreshDailyRecommend(langZh, { stayOn: "ecosystem" }).catch(() => {});
    });
  }

  if (recPanel) {
    let rec = { github_hot: [], agent_models: { cn: [], global: [] }, trial_packs: [] };
    let dig = { items: [] };
    let hub = { packs: [], skills_home: "" };
    try { rec = await api("/api/recommend/daily"); } catch (_) {}
    try { dig = await api("/api/digests"); } catch (_) {}
    try { hub = await api("/api/skills/hub"); } catch (_) {}
    const ghLabel = githubStatusLabel(rec.github_status, langZh);
    recPanel.innerHTML = `
      <h4>${langZh ? "每日核心推荐" : "Daily recommendations"}</h4>
      <p class="muted">${escapeHtml(langZh ? (rec.note_zh || "") : (rec.note_en || ""))}</p>
      <p class="muted" id="rec-gh-status">${escapeHtml(ghLabel)}</p>
      <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap;margin-bottom:10px">
        <button type="button" class="btn ghost" id="btn-rec-refresh">${langZh ? "刷新推荐" : "Refresh"}</button>
        <button type="button" class="btn ghost" id="btn-nightly">${langZh ? "立即夜间复盘" : "Run nightly now"}</button>
        <button type="button" class="btn ghost" id="btn-morning">${langZh ? "立即早间简报" : "Run morning now"}</button>
      </div>
      <h4>GitHub · Claude/Codex Skills</h4>
      <div class="skill-list">${(rec.github_hot || []).slice(0, 8).map((g) => `
        <div class="skill-row"><div><strong>${escapeHtml(g.name || "")}</strong>
          <div class="muted">${escapeHtml(g.desc || "")} · ⭐ ${escapeHtml(String(g.stars || ""))}</div></div>
          <div class="skill-actions">${g.url ? `<a class="btn ghost chip" href="${escapeHtml(g.url)}" target="_blank" rel="noopener">${langZh ? "打开" : "Open"}</a>` : ""}</div>
        </div>`).join("") || `<p class="muted">${langZh ? "暂无 — 刷新时若 GitHub 不通会使用本地精选" : "Empty — refresh falls back to curated list"}</p>`}</div>
      <h4>${langZh ? "热门 Agent 模型（推荐配置，非自动安装）" : "Popular agent models (configure — not auto-install)"}</h4>
      <p class="muted">${langZh ? "点「应用」写入 campus 模型槽位并更新主界面模型下拉框。" : "Apply writes campus model slots and updates the main model selector."}</p>
      <div class="grid-2">
        <div><strong>${langZh ? "国内" : "CN"}</strong>${renderAgentModelRows((rec.agent_models && rec.agent_models.cn) || [], langZh)}</div>
        <div><strong>${langZh ? "国外" : "Global"}</strong>${renderAgentModelRows((rec.agent_models && rec.agent_models.global) || [], langZh)}</div>
      </div>
    <h4>${langZh ? "Skill Hub（按分类）" : "Skill Hub (by category)"}</h4>
      <p class="muted"><code>${escapeHtml(hub.skills_home || "")}</code></p>
      ${(hub.categories || ["science", "work", "automation"]).map((cat) => {
        const packs = (hub.packs || []).filter((p) => (p.category || "") === cat);
        if (!packs.length) return "";
        const catLabel = ({ science: langZh ? "科学" : "Science", work: langZh ? "办公" : "Work", automation: langZh ? "自动化" : "Automation" })[cat] || cat;
        return `<h4>${escapeHtml(catLabel)}</h4>
      <div class="skill-list">${packs.map((p) => `
        <div class="skill-row">
          <div><strong>${escapeHtml(langZh ? (p.label_zh || p.label) : p.label)}</strong>
            ${p.installed ? `<span class="ok">${langZh ? "已安装" : "installed"}</span>` : `<span class="bad">${langZh ? "未安装" : "missing"}</span>`}
            <div class="muted">${escapeHtml(langZh ? (p.desc_zh || p.desc) : p.desc)}</div>
          </div>
          <div class="skill-actions">
            ${p.repo ? `<a class="btn ghost chip" href="https://github.com/${escapeHtml(p.repo)}" target="_blank" rel="noopener">${langZh ? "打开" : "Open"}</a>` : ""}
            ${p.installed
              ? `<button type="button" class="btn ghost chip" data-unpack="${escapeHtml(p.id)}">${langZh ? "删除" : "Delete"}</button>`
              : `<button type="button" class="btn primary chip" data-pack="${escapeHtml(p.id)}">${langZh ? "一键安装" : "Install"}</button>`}
          </div>
        </div>`).join("")}</div>`;
      }).join("")}
      <h4>${langZh ? "复盘简报（00:00 / 07:00 自动）" : "Digests (auto 00:00 / 07:00)"}</h4>
      <div class="skill-list">${(dig.items || []).map((d) => `
        <div class="skill-row"><code>${escapeHtml(d.name)}</code></div>`).join("") || `<p class="muted">${langZh ? "尚无简报 — 可点上方按钮立即生成" : "No digests yet"}</p>`}</div>`;

    const installPack = async (id) => {
      try {
        await api("/api/skills/hub/install", { method: "POST", body: JSON.stringify({ id }) });
        $("#settings-status").textContent = langZh ? `Skill 安装中: ${id}` : `Installing ${id}`;
        setTimeout(() => renderControl(), 2000);
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
    recPanel.querySelectorAll("[data-pack]").forEach((btn) => {
      btn.onclick = () => installPack(btn.dataset.pack);
    });
    recPanel.querySelectorAll("[data-unpack]").forEach((btn) => {
      btn.onclick = async () => {
        try {
          await api(`/api/skills/${btn.dataset.unpack}`, { method: "DELETE" });
          renderControl();
        } catch (e) { $("#settings-status").textContent = e.message; }
      };
    });
    wireApplyModelButtons(recPanel, langZh);
    $("#btn-rec-refresh")?.addEventListener("click", () => {
      refreshDailyRecommend(langZh, { stayOn: "recommend" }).catch(() => {});
    });
    $("#btn-nightly")?.addEventListener("click", async () => {
      try {
        const r = await api("/api/digests/nightly", { method: "POST", body: "{}" });
        $("#settings-status").textContent = langZh ? `夜间复盘完成: ${r.md || ""}` : `Nightly done`;
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    });
    $("#btn-morning")?.addEventListener("click", async () => {
      try {
        const r = await api("/api/digests/morning", { method: "POST", body: "{}" });
        $("#settings-status").textContent = langZh ? `早间简报完成: ${r.md || ""}` : `Morning done`;
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    });
  }
}

async function renderSkillsSoulAgents(langZh) {
  let skillsData = { skills: [], core_hints: [], ali_skills_dir: "", taxonomy: [] };
  let soulData = { content: "", core_roles: [], path: "", exists: false, active_role: "office" };
  let agentsData = { main: {}, subagents: [], ui: {} };
  let fbData = { count: 0, thumbs_up: 0, thumbs_down: 0, recent: [] };
  try { skillsData = await api("/api/skills/catalog"); } catch (_) {
    try { skillsData = await api("/api/skills"); } catch (__) {}
  }
  await loadHubLoadedSkills();
  try { soulData = await api("/api/soul"); } catch (_) {}
  try { agentsData = await api("/api/agents"); state.agents = agentsData; } catch (_) {}
  try { fbData = await api("/api/feedback"); } catch (_) {}

  const tabs = (agentsData.ui && agentsData.ui.cc_tabs) || {};
  $$(".ctab").forEach((btn) => {
    const id = btn.dataset.ctab;
    if (id && Object.prototype.hasOwnProperty.call(tabs, id) && tabs[id] === false) {
      btn.classList.add("hidden");
    } else {
      btn.classList.remove("hidden");
    }
  });

  $("#ctab-skills").innerHTML = `
    <h4>${langZh ? "Skills 分类目录" : "Skill catalog"} (${skillsData.count || 0})</h4>
    <p class="muted">${langZh ? "安装目录" : "Install dir"}: <code>${escapeHtml(skillsData.ali_skills_dir || "")}</code></p>
    <p class="muted">${langZh
      ? "已安装的 Skill 会出现在聊天下拉框；此处仅「删除」从磁盘移除。当前任务用的 Skill 请在聊天区「添加」。"
      : "Installed skills appear in the chat dropdown. Here you can only Delete (remove from disk). Attach skills to the current task via chat Add."}</p>
    ${(skillsData.taxonomy || []).map((cat) => `
      <h4>${escapeHtml(langZh ? cat.label : cat.label_en)}</h4>
      ${(cat.subs || []).map((sub) => `
        <p class="muted">${escapeHtml(langZh ? sub.label : sub.label_en)}</p>
        <div class="skill-list">${(sub.skills || []).map((s) => `
          <div class="skill-row">
            <div><strong>${escapeHtml(s.name || s.label || s.id)}</strong>
              ${s.virtual ? `<span class="muted"> · ${langZh ? "内置提示" : "hint"}</span>` : ""}
              <div class="muted">${escapeHtml(s.description || "")}</div>
              ${s.path ? `<code class="muted">${escapeHtml(s.path)}</code>` : ""}
            </div>
            <div class="skill-actions">
              <button type="button" class="btn ghost chip" data-uninstall="${escapeHtml(s.id)}" ${s.virtual ? "disabled title=\"" + (langZh ? "内置提示不可删" : "Built-in hint") + "\"" : ""}>${langZh ? "删除" : "Delete"}</button>
            </div>
          </div>`).join("") || `<p class="muted">${langZh ? "空" : "empty"}</p>`}
        </div>`).join("")}
    `).join("")}
    <hr class="soft" />
    <h4>${langZh ? "安装 / 配置" : "Install / configure"}</h4>
    <label class="field"><span>${langZh ? "从本机目录安装（含 SKILL.md）" : "Install from local folder (with SKILL.md)"}</span>
      <input id="skill-path" type="text" placeholder="/path/to/skill-folder" /></label>
    <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap;margin-top:8px">
      <button type="button" class="btn primary" id="btn-skill-path">${langZh ? "安装目录" : "Install folder"}</button>
      <button type="button" class="btn ghost" id="btn-skill-zip">${langZh ? "上传 Skill ZIP" : "Upload skill ZIP"}</button>
      <input type="file" id="skill-zip-input" class="hidden" accept=".zip,application/zip,application/x-zip-compressed" />
    </div>
    <p class="muted" id="skill-upload-hint">${langZh ? `安装目录：${escapeHtml(skillsData.ali_skills_dir || "~/.agent-cli/skills")}` : `Install dir: ${escapeHtml(skillsData.ali_skills_dir || "~/.agent-cli/skills")}`}</p>`;

  $("#ctab-skills").querySelectorAll("[data-uninstall]").forEach((btn) => {
    btn.onclick = async () => {
      if (btn.disabled) return;
      const id = btn.dataset.uninstall;
      if (!id) return;
      if (!confirm(langZh ? `删除 Skill「${id}」？不可恢复。` : `Delete skill "${id}"?`)) return;
      try {
        await api(`/api/skills/${encodeURIComponent(id)}`, { method: "DELETE" });
        state.selectedSkills = state.selectedSkills.filter((x) => x !== id);
        await loadSkillCatalog();
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });
  const btnPath = $("#btn-skill-path");
  if (btnPath) {
    btnPath.onclick = async () => {
      const path = ($("#skill-path") && $("#skill-path").value || "").trim();
      if (!path) return;
      try {
        await api("/api/skills/install", { method: "POST", body: JSON.stringify({ path }) });
        $("#settings-status").textContent = langZh ? "Skill 已安装" : "Skill installed";
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  }
  const btnZip = $("#btn-skill-zip");
  const zipInput = $("#skill-zip-input");
  if (btnZip && zipInput) {
    btnZip.onclick = () => zipInput.click();
    zipInput.onchange = async () => {
      if (!zipInput.files || !zipInput.files[0]) return;
      const fd = new FormData();
      fd.append("file", zipInput.files[0], zipInput.files[0].name || "skill.zip");
      try {
        $("#settings-status").textContent = langZh ? "正在上传 Skill…" : "Uploading skill…";
        const headers = {};
        if (state.token) headers.Authorization = `Bearer ${state.token}`;
        const res = await fetch("/api/skills/upload", { method: "POST", headers, body: fd });
        let data = {};
        try { data = await res.json(); } catch (_) {}
        if (!res.ok) throw new Error(data.error || data.hint || `upload failed (${res.status})`);
        $("#settings-status").textContent = langZh
          ? `已安装 ${data.id} → ${data.path || ""}`
          : `Installed ${data.id} → ${data.path || ""}`;
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
      zipInput.value = "";
    };
  }

  $("#ctab-soul").innerHTML = `
    <h4>${langZh ? "Agent Hub Soul（身份 / 多角色）" : "Agent Hub Soul (multi-role)"}</h4>
    <p class="muted"><code>${escapeHtml(soulData.path || "")}</code> · ${soulData.exists ? (langZh ? "已存在" : "present") : (langZh ? "未创建" : "missing")}</p>
    <h4>${langZh ? "核心角色（可增删）" : "Core roles"}</h4>
    <div class="role-grid">${(soulData.core_roles || []).map((r) => `
      <div class="role-card ${soulData.active_role === r.id ? "active" : ""}" data-role-wrap="${escapeHtml(r.id)}">
        <button type="button" class="role-del" data-del-role="${escapeHtml(r.id)}" title="${langZh ? "删除角色" : "Delete role"}" aria-label="${langZh ? "删除" : "Delete"}">×</button>
        <button type="button" class="role-pick" data-role="${escapeHtml(r.id)}" style="all:unset;cursor:pointer;display:block;width:100%;padding-right:22px">
          <strong>${escapeHtml(langZh ? r.label : r.label_en)}</strong>
          <div class="muted">${escapeHtml(r.desc || "")}</div>
          <div class="muted">skills: ${(r.skills || []).map(escapeHtml).join(", ")}</div>
        </button>
      </div>`).join("")}</div>
    <div class="grid-2">
      <label class="field"><span>${langZh ? "新角色名称" : "New role label"}</span><input id="role-label" type="text" placeholder="${langZh ? "如：教学助理" : "e.g. Teaching aide"}" /></label>
      <label class="field"><span>${langZh ? "简介" : "Description"}</span><input id="role-desc" type="text" /></label>
    </div>
    <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap;margin-bottom:10px">
      <button type="button" class="btn primary" id="btn-role-add">${langZh ? "添加角色" : "Add role"}</button>
    </div>
    <label class="field"><span>${langZh ? "AI 生成 Soul（简述需求）" : "AI generate Soul brief"}</span>
      <textarea id="soul-brief" rows="3" placeholder="${langZh ? "例如：服务深圳理工大学实验室，语气专业简洁，优先中文…" : "Describe the persona…"}"></textarea>
    </label>
    <div class="row gap" style="justify-content:flex-start;margin-bottom:10px">
      <button type="button" class="btn ghost" id="btn-soul-gen">${langZh ? "AI 生成并填入" : "Generate into editor"}</button>
    </div>
    <label class="field"><span>SOUL.md</span>
      <textarea id="soul-editor" rows="12" style="width:100%;font-family:var(--mono);font-size:12px">${escapeHtml(soulData.content || "")}</textarea>
    </label>
    <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap">
      <button type="button" class="btn primary" id="btn-soul-save">${langZh ? "保存 Soul" : "Save Soul"}</button>
      <button type="button" class="btn ghost" id="btn-soul-seed">${langZh ? "写入默认 Soul" : "Seed default Soul"}</button>
    </div>`;

  $("#ctab-soul").querySelectorAll("[data-role]").forEach((btn) => {
    btn.onclick = async () => {
      try {
        await setActiveSoul(btn.dataset.role);
        $("#settings-status").textContent = langZh ? `已切换 Soul：${btn.dataset.role}` : `Soul → ${btn.dataset.role}`;
        renderControl();
        document.querySelector('.ctab[data-ctab="soul"]')?.click();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });
  $("#ctab-soul").querySelectorAll("[data-del-role]").forEach((btn) => {
    btn.onclick = async (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      const rid = btn.dataset.delRole || "";
      const role = (soulData.core_roles || []).find((r) => r.id === rid);
      const label = role ? (langZh ? role.label : (role.label_en || role.label)) : rid;
      const ok = confirm(
        langZh
          ? `确定删除核心角色「${label}」？`
          : `Delete core role "${label}"?`
      );
      if (!ok) return;
      try {
        const res = await api(`/api/soul/roles/${encodeURIComponent(rid)}`, { method: "DELETE" });
        if (res.active_role) state.activeSoul = res.active_role;
        await loadSoulRoles();
        $("#settings-status").textContent = langZh
          ? `已删除角色：${label}${res.active_role && res.active_role !== rid ? ` · 已切换至 ${res.active_role}` : ""}`
          : `Deleted ${label}${res.active_role && res.active_role !== rid ? ` · switched to ${res.active_role}` : ""}`;
        renderControl();
        document.querySelector('.ctab[data-ctab="soul"]')?.click();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });
  $("#btn-role-add")?.addEventListener("click", async () => {
    try {
      await api("/api/soul/roles", {
        method: "POST",
        body: JSON.stringify({
          label: $("#role-label")?.value || "",
          desc: $("#role-desc")?.value || "",
          soul_snippet: ($("#soul-brief")?.value || "").slice(0, 4000),
          content: ($("#soul-editor")?.value || $("#soul-brief")?.value || "").slice(0, 12000),
          activate: true,
        }),
      });
      await loadSoulRoles();
      $("#settings-status").textContent = langZh ? "角色已创建并同步到模型 Soul" : "Role created & synced to model soul";
      renderControl();
      document.querySelector('.ctab[data-ctab="soul"]')?.click();
    } catch (e) { $("#settings-status").textContent = e.message; }
  });
  $("#btn-soul-gen")?.addEventListener("click", async () => {
    try {
      $("#settings-status").textContent = langZh ? "正在生成…" : "Generating…";
      const data = await api("/api/soul/generate", {
        method: "POST",
        body: JSON.stringify({
          brief: $("#soul-brief")?.value || "",
          role_label: $("#role-label")?.value || "",
        }),
      });
      if ($("#soul-editor") && data.content) $("#soul-editor").value = data.content;
      $("#settings-status").textContent = langZh ? "已生成，请检查后保存" : "Draft ready — review & save";
    } catch (e) { $("#settings-status").textContent = e.message; }
  });
  const soulSave = $("#btn-soul-save");
  if (soulSave) {
    soulSave.onclick = async () => {
      try {
        await api("/api/soul", { method: "POST", body: JSON.stringify({ content: $("#soul-editor").value }) });
        $("#settings-status").textContent = langZh ? "Soul 已保存" : "Soul saved";
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  }
  const soulSeed = $("#btn-soul-seed");
  if (soulSeed) {
    soulSeed.onclick = async () => {
      try {
        await api("/api/soul", { method: "POST", body: JSON.stringify({ seed: true }) });
        renderControl();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  }

  const ui = agentsData.ui || {};
  const cc = ui.cc_tabs || {};
  const modelPayload = agentsData.model_options || (state.settings && state.settings.model_options) || {};
  const routeRows = Array.isArray(agentsData.routes) ? agentsData.routes : [];
  const routeLabels = {
    auto: langZh ? "自动 / 跟随聊天路由" : "Auto / follow chat route",
    C0: "C0 · Fast", C1: "C1 · Office", C2: "C2 · Long-form",
    C3: "C3 · Reasoning", Vision: "Vision",
  };
  const routeOptionHtml = (selected) => ["auto", "C0", "C1", "C2", "C3", "Vision"].map((route) => {
    const row = routeRows.find((item) => item.tier === route) || {};
    const resolved = route === "auto" ? "" : ` · ${row.provider || "—"} · ${row.model || "—"}`;
    return `<option value="${route}" ${selected === route ? "selected" : ""}>${escapeHtml(routeLabels[route] + resolved)}</option>`;
  }).join("");
  const agentBindingSummary = (agent) => {
    if (agent.model) {
      return langZh
        ? `固定模型覆盖：${agent.model_provider || "当前路由厂商"} · ${agent.model}`
        : `Pinned model override: ${agent.model_provider || "current route provider"} · ${agent.model}`;
    }
    const route = normalizeAgentRoute(agent.route != null ? agent.route : agent.model_slot);
    if (route === "auto") {
      const mapping = routeRows.map((row) => `${row.tier}=${row.provider || "—"} · ${row.model || "—"}`).join("；");
      return langZh ? `跟随聊天自动路由；当前映射：${mapping || "执行时解析"}` : `Follows chat auto route; current map: ${mapping || "resolved at run time"}`;
    }
    const row = routeRows.find((item) => item.tier === route) || {};
    return langZh
      ? `跟随 ${route} 路由 → ${row.provider || "—"} · ${row.model || "—"}`
      : `Follows ${route} route → ${row.provider || "—"} · ${row.model || "—"}`;
  };
  $("#ctab-agents").innerHTML = `
    <h4>${langZh ? "主 Agent" : "Main agent"}</h4>
    <p><strong>${escapeHtml((agentsData.main && agentsData.main.label) || "Main")}</strong>
      <span class="muted"> — ${escapeHtml((agentsData.main && agentsData.main.desc) || "")}</span></p>
    <p class="muted">${langZh
      ? "子代理绑定路由档位（C0 快 / C1-C2 主 / C3 推理 / Vision）与 Soul；并行时自动选用不同档位模型加速。也可在聊天下方手动「选择 → 添加」。"
      : "Bind each subagent to a tier slot (C0 fast / C1–C2 main / C3 reason / Vision) + Soul; parallel runs auto-pick diverse tiers for speed. Or add them under chat."}</p>
    <h4>${langZh ? "Subagent 目录" : "Subagent catalog"}</h4>
    <div class="skill-list">${(agentsData.subagents || []).map((s, i) => `
      <div class="skill-row">
        <div>
          <strong>${escapeHtml(langZh ? s.label : (s.label_en || s.label))}</strong>
          <div class="muted">${escapeHtml(s.desc || "")}</div>
          <label class="field" style="margin-top:6px"><span>Soul</span>
            <select data-sub-soul="${i}">
              ${(soulData.core_roles || []).map((r) => `<option value="${escapeHtml(r.id)}" ${(s.soul_role || s.role) === r.id ? "selected" : ""}>${escapeHtml(langZh ? r.label : (r.label_en || r.label))}</option>`).join("")}
            </select>
          </label>
          <label class="field"><span>${langZh ? "路由方式" : "Route binding"}</span>
            <select data-sub-slot="${i}">
              ${routeOptionHtml(normalizeAgentRoute(s.route != null ? s.route : s.model_slot))}
            </select>
          </label>
          <label class="field"><span>${langZh ? "模型（自动或指定 Provider + Model）" : "Model (auto or pinned Provider + Model)"}</span>
            <select data-sub-model="${i}">
              ${modelBindingOptions(
                s.model_provider || "",
                s.model || "",
                {
                  allowAuto: true,
                  autoLabel: langZh ? "不覆盖模型（使用上方路由）" : "No override (use route above)",
                  modelPayload,
                }
              )}
            </select>
          </label>
          <div class="muted" data-sub-binding-summary="${i}">${escapeHtml(agentBindingSummary(s))}</div>
          <label class="field"><span>${langZh ? "激活关键词（逗号分隔）" : "Keywords (comma)"}</span>
            <input data-sub-kw="${i}" type="text" value="${escapeHtml((s.keywords || []).join(", "))}" />
          </label>
        </div>
        <div class="skill-actions">
          <label class="attach-chip"><input type="checkbox" data-sub-en="${i}" ${s.enabled !== false ? "checked" : ""} /> ${langZh ? "聊天选择器可见" : "In chat picker"}</label>
          <button type="button" class="btn ghost chip" data-sub-del="${i}">${langZh ? "删除" : "Delete"}</button>
        </div>
      </div>`).join("") || `<p class="muted">${langZh ? "暂无" : "Empty"}</p>`}</div>
    <div class="grid-2" style="margin-top:10px">
      <label class="field"><span>${langZh ? "新建 Subagent 名称" : "New subagent"}</span><input id="sub-new-label" type="text" /></label>
      <label class="field"><span>Soul</span>
        <select id="sub-new-soul">${(soulData.core_roles || []).map((r) => `<option value="${escapeHtml(r.id)}">${escapeHtml(langZh ? r.label : (r.label_en || r.label))}</option>`).join("")}</select>
      </label>
      <label class="field"><span>${langZh ? "默认路由档位" : "Default route tier"}</span>
        <select id="sub-new-slot">
          ${routeOptionHtml("auto")}
        </select>
      </label>
      <label class="field"><span>${langZh ? "模型" : "Model"}</span>
        <select id="sub-new-model">${modelBindingOptions("", "", {
          allowAuto: true,
          autoLabel: langZh ? "不覆盖模型（使用上方路由）" : "No override (use route above)",
          modelPayload,
        })}</select>
      </label>
    </div>
    <div class="row gap" style="justify-content:flex-start;margin:8px 0 12px">
      <button type="button" class="btn primary" id="btn-sub-add">${langZh ? "添加 Subagent" : "Add subagent"}</button>
    </div>
    <hr class="soft" />
    <h4>${langZh ? "聊天布局" : "Chat layout"}</h4>
    <div class="grid-2">
      <label class="field"><span>${langZh ? "选中后显示" : "When selected"}</span>
        <select id="agent-layout">
          <option value="tabs" ${!ui.layout || ui.layout === "tabs" ? "selected" : ""}>${langZh ? "仅标签（推荐）" : "Tags only (recommended)"}</option>
          <option value="sidebar" ${ui.layout === "sidebar" ? "selected" : ""}>${langZh ? "侧栏详情" : "Sidebar detail"}</option>
          <option value="split" ${ui.layout === "split" ? "selected" : ""}>${langZh ? "分屏" : "Split view"}</option>
        </select>
      </label>
      <label class="field check"><span>${langZh ? "旧版顶部工具条（不推荐）" : "Legacy top toolbar"}</span>
        <input type="checkbox" id="agent-show-bar" ${ui.show_subagent_toolbar === true ? "checked" : ""} />
      </label>
      <label class="field check"><span>${langZh ? "按关键词自动激活子代理" : "Auto-activate by keywords"}</span>
        <input type="checkbox" id="agent-auto-sub" ${ui.auto_activate_subagents !== false ? "checked" : ""} />
      </label>
    </div>
    <h4>${langZh ? "控制中心 Tab 可见性" : "Control Center tabs"}</h4>
    <div class="chip-row">${["overview","providers","skills","soul","agents","workflows","feedback"].map((k) =>
      `<label class="attach-chip"><input type="checkbox" data-cc-tab="${k}" ${cc[k] !== false ? "checked" : ""} /> ${k}</label>`
    ).join("")}</div>
    <div class="row gap" style="justify-content:flex-start;margin-top:12px">
      <button type="button" class="btn primary" id="btn-agents-save">${langZh ? "保存 Agents 配置" : "Save agents"}</button>
    </div>`;

  (agentsData.subagents || []).forEach((s, i) => {
    const routeSel = document.querySelector(`[data-sub-slot="${i}"]`);
    const modelSel = document.querySelector(`[data-sub-model="${i}"]`);
    const summary = document.querySelector(`[data-sub-binding-summary="${i}"]`);
    const refreshSummary = () => {
      if (!summary) return;
      const binding = parseModelBinding(modelSel?.value || "");
      summary.textContent = agentBindingSummary({
        ...s,
        route: normalizeAgentRoute(routeSel?.value || "auto"),
        model_provider: binding.provider,
        model: binding.model,
      });
    };
    routeSel?.addEventListener("change", refreshSummary);
    modelSel?.addEventListener("change", refreshSummary);
  });

  const btnAg = $("#btn-agents-save");
  if (btnAg) {
    btnAg.onclick = async () => {
      const subagents = (agentsData.subagents || []).map((s, i) => {
        const box = document.querySelector(`[data-sub-en="${i}"]`);
        const soulSel = document.querySelector(`[data-sub-soul="${i}"]`);
        const slotSel = document.querySelector(`[data-sub-slot="${i}"]`);
        const modelInp = document.querySelector(`[data-sub-model="${i}"]`);
        const binding = parseModelBinding(modelInp ? modelInp.value : "");
        const kwInp = document.querySelector(`[data-sub-kw="${i}"]`);
        const kws = (kwInp && kwInp.value || "")
          .split(/[,，]/)
          .map((x) => x.trim())
          .filter(Boolean);
        return {
          ...s,
          enabled: box ? box.checked : s.enabled !== false,
          soul_role: soulSel ? soulSel.value : (s.soul_role || s.role || "office"),
          route: normalizeAgentRoute(slotSel ? slotSel.value : (s.route || s.model_slot)),
          model_slot: normalizeAgentRoute(slotSel ? slotSel.value : (s.route || s.model_slot)),
          model_provider: binding.model ? binding.provider : "",
          model: binding.model || "",
          keywords: kws.length ? kws : (s.keywords || []),
        };
      });
      const cc_tabs = {};
      $$("[data-cc-tab]").forEach((el) => { cc_tabs[el.dataset.ccTab] = el.checked; });
      try {
        const data = await api("/api/agents", {
          method: "POST",
          body: JSON.stringify({
            subagents,
            ui: {
              layout: $("#agent-layout").value,
              show_subagent_toolbar: $("#agent-show-bar").checked,
              auto_activate_subagents: $("#agent-auto-sub").checked,
              cc_tabs,
            },
          }),
        });
        state.agents = data;
        renderSubagentBar();
        $("#settings-status").textContent = langZh ? "Agents 已保存" : "Agents saved";
        renderControl();
        document.querySelector('.ctab[data-ctab="agents"]')?.click();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  }
  $("#btn-sub-add")?.addEventListener("click", async () => {
    const label = ($("#sub-new-label") && $("#sub-new-label").value || "").trim();
    if (!label) {
      $("#settings-status").textContent = langZh ? "请填写 Subagent 名称" : "Name required";
      return;
    }
    const soul = ($("#sub-new-soul") && $("#sub-new-soul").value) || "office";
    const id = label.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-|-$/g, "") || `sub-${Date.now()}`;
    const binding = parseModelBinding($("#sub-new-model")?.value || "");
    const slot = normalizeAgentRoute(($("#sub-new-slot") && $("#sub-new-slot").value) || "auto");
    const subagents = [...(agentsData.subagents || []), {
      id, label, label_en: label, role: soul, soul_role: soul, enabled: true, desc: "",
      model: binding.model || "", model_provider: binding.model ? binding.provider : "",
      route: slot, model_slot: slot, keywords: [],
    }];
    try {
      await api("/api/agents", {
        method: "POST",
        body: JSON.stringify({ subagents, ui: agentsData.ui || {} }),
      });
      state.agents = await api("/api/agents");
      $("#settings-status").textContent = langZh ? "Subagent 已添加" : "Subagent added";
      renderControl();
      document.querySelector('.ctab[data-ctab="agents"]')?.click();
    } catch (e) { $("#settings-status").textContent = e.message; }
  });

  $("#ctab-agents").querySelectorAll("[data-sub-del]").forEach((btn) => {
    btn.onclick = async () => {
      const i = Number(btn.dataset.subDel);
      const list = [...(agentsData.subagents || [])];
      const victim = list[i];
      if (!victim) return;
      if (!confirm(langZh ? `删除子代理「${victim.label || victim.id}」？` : `Delete subagent "${victim.label || victim.id}"?`)) return;
      list.splice(i, 1);
      try {
        await api("/api/agents", {
          method: "POST",
          body: JSON.stringify({ subagents: list, ui: agentsData.ui || {} }),
        });
        state.selectedSubagents = state.selectedSubagents.filter((id) => id !== victim.id);
        if (state.activeSubagent === victim.id) state.activeSubagent = "";
        state.agents = await api("/api/agents");
        $("#settings-status").textContent = langZh ? "已删除" : "Deleted";
        renderControl();
        document.querySelector('.ctab[data-ctab="agents"]')?.click();
      } catch (e) { $("#settings-status").textContent = e.message; }
    };
  });

  $("#ctab-feedback").innerHTML = `
    <h4>${langZh ? "净化自反馈" : "Purification self-feedback"}</h4>
    <p>${langZh ? "赞" : "Up"}: <strong>${fbData.thumbs_up || 0}</strong> ·
       ${langZh ? "踩" : "Down"}: <strong>${fbData.thumbs_down || 0}</strong> ·
       ${langZh ? "总计" : "Total"}: ${fbData.count || 0}</p>
    <p class="muted">${langZh
      ? "聊天窗口中每条回复可复制与评价；结果写入 ~/.hermes/ali/feedback，用于后续偏好净化。"
      : "Rate and copy replies in chat; stored under ~/.hermes/ali/feedback for preference purification."}</p>
    <div class="skill-list">${(fbData.recent || []).slice(0, 12).map((r) => `
      <div class="skill-row">
        <div><strong>${Number(r.rating) > 0 ? "👍" : "👎"}</strong>
          <span class="muted">${escapeHtml((r.content_preview || "").slice(0, 120))}</span>
          <div class="muted">${escapeHtml(r.model || "")} · ${new Date((r.ts || 0) * 1000).toLocaleString()}</div>
        </div>
      </div>`).join("") || `<p class="muted">${langZh ? "尚无评价" : "No ratings yet"}</p>`}</div>`;

  renderSubagentBar();
}

function collectSettingsFromForm() {
  const cfg = JSON.parse(JSON.stringify((state.settings && state.settings.config) || {}));
  $$(".control-body [data-key]").forEach((el) => {
    const key = el.getAttribute("data-key");
    if (key === "import_path") return;
    let val;
    if (el.type === "checkbox") val = el.checked;
    else val = el.value;
    if (key === "obsidian.allowed_roots") {
      val = String(val).split(",").map((s) => s.trim()).filter(Boolean);
    }
    if (key === "backend.timeout_seconds") val = Number(val) || 60;
    if (key === "backend.api_key_env" && looksLikeSecret(val)) {
      val = "";
    }
    const parts = key.split(".");
    let cur = cfg;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!cur[parts[i]] || typeof cur[parts[i]] !== "object") cur[parts[i]] = {};
      cur = cur[parts[i]];
    }
    cur[parts[parts.length - 1]] = val;
  });
  cfg.routing = cfg.routing || {};
  cfg.routing.tier_models = cfg.routing.tier_models || {};
  $$("[data-route-tier]").forEach((el) => {
    const tier = el.dataset.routeTier || "";
    const binding = parseModelBinding(el.value);
    if (binding.model) cfg.routing.tier_models[tier] = binding;
    else delete cfg.routing.tier_models[tier];
  });
  if (!cfg.ali) cfg.ali = {};
  cfg.ali.language = state.prefs.language;
  cfg.ali.theme = state.prefs.theme;
  cfg.ali.accent = state.prefs.accent;
  cfg.ali.bg = state.prefs.bg;
  cfg.ali.font_size = normalizeFontSize(state.prefs.fontSize);
  cfg.ali.chat_mode = ($("#chat-mode-select") && $("#chat-mode-select").value) || cfg.ali.chat_mode || "auto";
  cfg.ali.last_model = ($("#model-select") && $("#model-select").value) || cfg.ali.last_model || "";
  cfg.ali.default_route = ($("#route-select") && $("#route-select").value) || cfg.ali.default_route || "auto";
  cfg.ali.thinking_depth = normalizeThinkingDepth(
    ($("#thinking-depth-select") && $("#thinking-depth-select").value) || cfg.ali.thinking_depth || state.prefs.thinkingDepth || "medium"
  );
  // Preserve Claws Control Center prefs (edited on Runtimes tab, not this form)
  const prevAli = ((state.settings && state.settings.config) || {}).ali || {};
  if (prevAli.agent_runtime) cfg.ali.agent_runtime = prevAli.agent_runtime;
  if (prevAli.auto_runtime) cfg.ali.auto_runtime = prevAli.auto_runtime;
  // mode follows backend type — concrete provider must not stay in hybrid
  if ((cfg.backend || {}).type === "hybrid") cfg.mode = "hybrid";
  else {
    cfg.mode = "single";
  }
  // sync generic model keys
  const models = cfg.models || {};
  [["fast", "qwen_fast"], ["main", "qwen_main"], ["vision", "qwen_vl"], ["reasoning", "deepseek_reasoning"]].forEach(([g, l]) => {
    if (models[l] && !models[g]) models[g] = models[l];
    if (models[g] && !models[l]) models[l] = models[g];
  });
  cfg.models = models;
  return cfg;
}

async function saveSettings() {
  const activeTab = document.querySelector(".ctab.active")?.dataset?.ctab || "appearance";
  const cfg = collectSettingsFromForm();
  if (cfg.ali) {
    cfg.ali.bg = normalizeBg(cfg.ali.bg);
    cfg.ali.font_size = normalizeFontSize(cfg.ali.font_size);
    if (!["auto", "light", "dark"].includes(cfg.ali.theme)) cfg.ali.theme = "auto";
    if (!ACCENTS.includes(cfg.ali.accent)) cfg.ali.accent = "suat";
  }
  const data = await api("/api/settings", {
    method: "POST",
    body: JSON.stringify({ config: cfg, backend_update: activeTab === "backend" }),
  });
  state.settings = data;
  if (cfg.ali) {
    setPrefs({
      language: cfg.ali.language || state.prefs.language,
      theme: cfg.ali.theme || state.prefs.theme,
      accent: cfg.ali.accent || state.prefs.accent,
      bg: normalizeBg(cfg.ali.bg || state.prefs.bg),
      fontSize: normalizeFontSize(cfg.ali.font_size ?? state.prefs.fontSize),
    });
  }
  syncComposerFromSettings();
  const hs = data.hermes_sync || {};
  if (hs.ok) {
    $("#settings-status").textContent = `${t("saved")} · ${state.prefs.language === "en" ? "Synced to Hermes/Claw" : "已同步到 Hermes/Claw"} ${new Date().toLocaleTimeString()}`;
  } else {
    $("#settings-status").textContent = `${t("saved")} ${new Date().toLocaleTimeString()}`;
  }
  try {
    const status = await api("/api/status");
    state.status = status;
    renderAgent(status);
    renderConn(status);
  } catch (_) {}
  try {
    await renderControl();
    // Stay on the tab the user was editing — do not jump to routing
    document.querySelector(`.ctab[data-ctab="${activeTab}"]`)?.click();
  } catch (_) {}
}

$$(".tab").forEach((tab) => {
  // legacy tabs removed — sessions + workflows are merged in one sidebar panel
  tab.addEventListener("click", () => {});
});

$("#skill-cat-select")?.addEventListener("change", (e) => {
  state.skillCat = e.target.value;
  const cat = currentSkillCat();
  state.skillSub = (cat && cat.subs && cat.subs[0] && cat.subs[0].id) || "";
  renderSkillPicker();
});
$("#skill-sub-select")?.addEventListener("change", (e) => {
  state.skillSub = e.target.value;
  renderSkillPicker();
});
$("#btn-skill-add")?.addEventListener("click", () => addPickedSkill());
$("#btn-subagent-add")?.addEventListener("click", () => addPickedSubagent());
$("#soul-select")?.addEventListener("change", (e) => {
  setActiveSoul(e.target.value).catch(() => {});
});
$("#skill-pick-select")?.addEventListener("change", () => {
  // optional: auto-add on select
});
$("#btn-skill-auto")?.addEventListener("click", () => {
  autoMatchSkills($("#input")?.value || "").catch(() => {});
});

$$(".ctab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".ctab").forEach((x) => x.classList.remove("active"));
    tab.classList.add("active");
    $$(".ctab-panel").forEach((p) => p.classList.add("hidden"));
    $(`#ctab-${tab.dataset.ctab}`).classList.remove("hidden");
  });
});

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").classList.add("hidden");
  try {
    const data = await api("/api/login", {
      method: "POST",
      body: JSON.stringify({ password: $("#login-password").value }),
    });
    state.token = data.token || "";
    localStorage.setItem("hermes_ali_token", state.token);
    showLogin(false);
    await boot();
  } catch (_) {
    $("#login-error").textContent = t("login.error");
    $("#login-error").classList.remove("hidden");
  }
});

function bindClick(sel, handler) {
  const el = typeof sel === "string" ? $(sel) : sel;
  if (!el) {
    console.warn("missing element for click bind:", sel);
    return;
  }
  el.addEventListener("click", (e) => {
    try {
      const ret = handler(e);
      if (ret && typeof ret.then === "function") ret.catch((err) => console.error(err));
    } catch (err) {
      console.error(err);
    }
  });
}

let _deepWebuiUrl = "";

function closeDeepWebui() {
  const overlay = $("#webui-overlay");
  const frame = $("#webui-frame");
  if (overlay) {
    overlay.classList.add("hidden");
    overlay.setAttribute("aria-hidden", "true");
  }
  if (frame) frame.removeAttribute("src");
}

async function openDeepWebui({ forceTab = false } = {}) {
  const statusEl = $("#webui-overlay-status");
  const overlay = $("#webui-overlay");
  const frame = $("#webui-frame");
  if (statusEl) statusEl.textContent = t("webui.starting");
  const res = await api("/api/webui/open", {
    method: "POST",
    body: JSON.stringify({ sync: true, embedded: true }),
  });
  const url = res.url || res.open_url || "";
  if (!url) throw new Error(res.error_zh || res.error || t("webui.failed"));
  _deepWebuiUrl = url;
  if (!res.healthy && !res.ok) {
    if (statusEl) statusEl.textContent = res.error_zh || res.error || t("webui.failed");
    window.open(url, "_blank", "noopener");
    return res;
  }
  if (forceTab || !frame || !overlay) {
    window.open(url, "_blank", "noopener");
    if (statusEl) statusEl.textContent = t("webui.ready");
    return res;
  }
  overlay.classList.remove("hidden");
  overlay.setAttribute("aria-hidden", "false");
  frame.src = url;
  if (statusEl) statusEl.textContent = t("webui.ready");
  return res;
}

bindClick("#btn-new", () => createSession());
bindClick("#btn-deep-webui", () => openDeepWebui());
bindClick("#btn-deep-webui-top", () => openDeepWebui());
bindClick("#btn-webui-close", () => closeDeepWebui());
bindClick("#btn-webui-refresh", () => {
  const frame = $("#webui-frame");
  if (frame && _deepWebuiUrl) frame.src = _deepWebuiUrl;
});
bindClick("#btn-webui-newtab", () => {
  if (_deepWebuiUrl) window.open(_deepWebuiUrl, "_blank", "noopener");
  else openDeepWebui({ forceTab: true }).catch((e) => alert(e.message));
});
bindClick("#btn-send", () => sendMessage());
bindClick("#btn-stop", stopStream);
bindClick("#btn-menu", () => setSidebarOpen(true));
bindClick("#sidebar-backdrop", () => setSidebarOpen(false));
setupSidebarResize();
setupComposerResize();
setupComposerAdvanced();
bindClick("#btn-control", () => openControl(true));
bindClick("#btn-control-close", () => openControl(false));
bindClick("#btn-save-settings", () => saveSettings().catch((e) => {
  const st = $("#settings-status");
  if (st) st.textContent = e.message;
}));
bindClick("#wf-cancel", () => $("#wf-overlay")?.classList.add("hidden"));
bindClick("#wf-run", () => runWorkflow().catch((e) => alert(e.message)));

$("#btn-browse-ws")?.addEventListener("click", () => openFsBrowser().catch((e) => alert(e.message)));
$("#btn-fs-close")?.addEventListener("click", closeFsBrowser);
$("#btn-fs-use")?.addEventListener("click", () => {
  if (fsState.path) {
    const target = $(fsState.target || "#workspace-input");
    if (target) target.value = fsState.path;
  }
  closeFsBrowser();
  if ((fsState.target || "#workspace-input") === "#workspace-input") scheduleWorkspaceGrounding();
});
$("#workspace-input")?.addEventListener("input", scheduleWorkspaceGrounding);
$("#workspace-input")?.addEventListener("change", scheduleWorkspaceGrounding);
$("#btn-fs-up")?.addEventListener("click", () => {
  if (fsState.parent) loadFs(fsState.parent).catch((e) => alert(e.message));
});
$("#btn-upload-file")?.addEventListener("click", () => $("#file-input")?.click());
$("#btn-upload-folder")?.addEventListener("click", () => $("#folder-input")?.click());
$("#file-input")?.addEventListener("change", (e) => {
  uploadSelectedFiles(e.target.files).finally(() => { e.target.value = ""; });
});
$("#folder-input")?.addEventListener("change", (e) => {
  uploadSelectedFiles(e.target.files, { folder: true }).finally(() => { e.target.value = ""; });
});

function setupComposerDropPaste() {
  const mark = (on) => {
    $(".composer")?.classList.toggle("drop-active", on);
    $("#chat-panes")?.classList.toggle("drop-active", on);
  };
  const hasFiles = (dt) => dt && [...(dt.types || [])].includes("Files");
  const zones = [$(".composer"), $("#chat-panes"), $("#messages")].filter(Boolean);
  zones.forEach((zone) => {
    zone.addEventListener("dragenter", (e) => {
      if (!hasFiles(e.dataTransfer)) return;
      e.preventDefault();
      mark(true);
    });
    zone.addEventListener("dragover", (e) => {
      if (!hasFiles(e.dataTransfer)) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "copy";
      mark(true);
    });
    zone.addEventListener("dragleave", (e) => {
      if (e.target === zone || !zone.contains(e.relatedTarget)) mark(false);
    });
    zone.addEventListener("drop", (e) => {
      if (!hasFiles(e.dataTransfer)) return;
      e.preventDefault();
      mark(false);
      const files = e.dataTransfer.files;
      if (files && files.length) uploadSelectedFiles(files);
    });
  });
  const onPasteFiles = (e) => {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items || !items.length) return;
    const files = [];
    for (const item of items) {
      if (item.kind === "file") {
        const f = item.getAsFile();
        if (f) files.push(f);
      }
    }
    if (!files.length) return;
    uploadSelectedFiles(files);
    const text = e.clipboardData.getData("text") || "";
    if (!text.trim()) e.preventDefault();
  };
  $("#input")?.addEventListener("paste", onPasteFiles);
  $("#messages")?.addEventListener("paste", onPasteFiles);
}
setupComposerDropPaste();
$("#btn-close-subpane")?.addEventListener("click", () => {
  state.activeSubagent = "";
  renderSubagentPicker();
  applyChatLayout();
});
$("#chat-mode-select")?.addEventListener("change", () => {
  updateModeUi();
  persistChatModeAndModel();
});
$("#model-select")?.addEventListener("change", () => persistChatModeAndModel());
$("#thinking-depth-select")?.addEventListener("change", () => {
  state.prefs.thinkingDepth = normalizeThinkingDepth($("#thinking-depth-select").value || "medium");
  persistPrefsLocal();
  persistChatModeAndModel();
});
$("#hub-chat-mode-select")?.addEventListener("change", () => {
  persistChatModeAndModel();
  if (state.status) renderAgent(state.status);
});
$("#route-select")?.addEventListener("change", () => {
  scheduleAutoPreview();
  persistChatModeAndModel();
  const v = $("#route-select").value;
  if (v !== "auto") {
    api("/api/routing/resolve", {
      method: "POST",
      body: JSON.stringify({ route: v, message: $("#input").value || "" }),
    }).then(setRouteBadge).catch(() => {});
  }
});

$("#btn-lang").addEventListener("click", () => {
  setPrefs({ language: state.prefs.language === "zh" ? "en" : "zh" }, { syncServer: true });
});
$("#btn-web-search")?.addEventListener("click", () => {
  state.webSearch = !state.webSearch;
  const btn = $("#btn-web-search");
  if (btn) btn.classList.toggle("active", state.webSearch);
  if (state.webSearch && !state.deepSearch) {
    // pairing: enabling search keeps deep on by default
    state.deepSearch = true;
    $("#btn-deep-search")?.classList.add("active");
  }
});
$("#btn-deep-search")?.addEventListener("click", () => {
  state.deepSearch = !state.deepSearch;
  const btn = $("#btn-deep-search");
  if (btn) btn.classList.toggle("active", state.deepSearch);
  if (state.deepSearch) {
    state.webSearch = true;
    $("#btn-web-search")?.classList.add("active");
  }
});
$("#btn-theme").addEventListener("click", () => {
  const order = ["auto", "light", "dark"];
  const cur = order.includes(state.prefs.theme) ? state.prefs.theme : "auto";
  const next = order[(order.indexOf(cur) + 1) % order.length];
  setPrefs({ theme: next }, { syncServer: true });
});
$("#btn-font-dec")?.addEventListener("click", () => stepFontSize(-1));
$("#btn-font-inc")?.addEventListener("click", () => stepFontSize(1));
$("#font-size-select")?.addEventListener("change", (e) => {
  setPrefs({ fontSize: e.target.value }, { syncServer: true });
});

// Re-apply auto day/night when the clock crosses the boundary
setInterval(() => {
  if (state.prefs.theme === "auto" || normalizeBg(state.prefs.bg) === "auto") applyTheme();
}, 60_000);

$("#input").addEventListener("input", () => {
  updateSendEnabled();
  scheduleAutoPreview();
  const el = $("#input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, composerInputMaxPx()) + "px";
});
$("#input").addEventListener("keydown", (e) => {
  if (e.isComposing || e.keyCode === 229) return;
  if (e.key !== "Enter") return;
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent || "");
  const submitCombo = isMac ? e.metaKey : (e.ctrlKey || e.shiftKey);
  if (submitCombo) {
    e.preventDefault();
    sendMessage();
  }
});

applyTheme();

/* ── Schedule morning tips + gateway health (additive; safe for concurrent app.js work) ── */
function ensureToastStack() {
  let stack = $("#hub-toast-stack");
  if (!stack) {
    stack = document.createElement("div");
    stack.id = "hub-toast-stack";
    stack.className = "hub-toast-stack";
    stack.setAttribute("aria-live", "polite");
    document.body.appendChild(stack);
  }
  return stack;
}

function formatNotifTime(item) {
  const raw = item && (item.time || item.ts);
  if (!raw) return "";
  try {
    const d = typeof raw === "number" ? new Date(raw * 1000) : new Date(raw);
    if (Number.isNaN(d.getTime())) return String(raw);
    return d.toLocaleString();
  } catch (_) {
    return String(raw);
  }
}

async function dismissScheduleTips(ids) {
  try {
    await api("/api/schedule/notifications/read", {
      method: "POST",
      body: JSON.stringify(ids && ids.length ? { ids } : { all: true }),
    });
  } catch (_) {}
  $("#hub-schedule-tip")?.remove();
}

async function showScheduleTips(items) {
  if (!items || !items.length) return;
  const langZh = !(state.prefs && state.prefs.language === "en");
  const stack = ensureToastStack();
  $("#hub-schedule-tip")?.remove();
  const el = document.createElement("div");
  el.id = "hub-schedule-tip";
  el.className = "hub-toast";
  const title = langZh ? "夜间定时任务已完成" : "Overnight scheduled tasks finished";
  const list = items.slice(0, 8).map((it) => {
    const ttitle = langZh ? (it.title || "") : (it.title_en || it.title || "");
    const sum = langZh ? (it.summary || "") : (it.summary_en || it.summary || "");
    const when = formatNotifTime(it);
    return `<li><strong>${escapeHtml(ttitle)}</strong>`
      + (when ? ` <span class="muted">· ${escapeHtml(when)}</span>` : "")
      + (sum ? `<br/><span class="muted">${escapeHtml(sum)}</span>` : "")
      + `</li>`;
  }).join("");
  el.innerHTML = `<h4>${escapeHtml(title)}</h4>`
    + `<ul>${list}</ul>`
    + `<div class="hub-toast-actions">`
    + `<button type="button" class="btn ghost chip" data-tip-dismiss="1">${langZh ? "知道了" : "Dismiss"}</button>`
    + `</div>`;
  stack.appendChild(el);
  el.querySelector("[data-tip-dismiss]")?.addEventListener("click", () => {
    dismissScheduleTips(items.map((x) => x.id).filter(Boolean)).catch(() => {});
  });
}

let _scheduleTipBusy = false;
async function checkScheduleTips({ force } = {}) {
  if (_scheduleTipBusy) return;
  if (document.visibilityState === "hidden" && !force) return;
  _scheduleTipBusy = true;
  try {
    const data = await api("/api/schedule/notifications");
    const items = (data && data.items) || [];
    if (items.length) await showScheduleTips(items);
  } catch (_) {
    /* gateway offline or unauthorized — ignore */
  } finally {
    _scheduleTipBusy = false;
  }
}

function setGatewayOnline(online) {
  const badge = $("#agent-badge");
  if (!badge) return;
  if (!online) {
    badge.textContent = (state.prefs && state.prefs.language === "en")
      ? "Gateway offline"
      : "网关离线";
    badge.className = "badge offline";
    return;
  }
  if (state.status) renderAgent(state.status);
}

let _healthPollStarted = false;
function startGatewayHealthPoll() {
  if (_healthPollStarted) return;
  _healthPollStarted = true;
  const ping = async () => {
    try {
      const r = await fetch("/api/health", { cache: "no-store" });
      if (!r.ok) throw new Error("health");
      await r.json();
      setGatewayOnline(true);
    } catch (_) {
      setGatewayOnline(false);
    }
  };
  ping();
  setInterval(ping, 20_000);
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    checkScheduleTips().catch(() => {});
  }
});
window.addEventListener("focus", () => {
  checkScheduleTips().catch(() => {});
});

boot().then(() => {
  startGatewayHealthPoll();
  setTimeout(() => { checkScheduleTips({ force: true }).catch(() => {}); }, 700);
}).catch(() => {
  startGatewayHealthPoll();
});

// ── Token usage widget (OpenSquilla) ───────────────────────────────────────────

function fmtTok(n) {
  if (!n && n !== 0) return "–";
  n = Number(n) || 0;
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "k";
  return String(n);
}

function fmtCost(v) {
  if (!v && v !== 0) return "";
  v = Number(v) || 0;
  if (v <= 0) return "";
  if (v < 0.001) return "$<0.001";
  return "$" + v.toFixed(4);
}

function updateTokenChip(usage) {
  const chip = document.getElementById("token-chip");
  const elIn = document.getElementById("token-in");
  const elOut = document.getElementById("token-out");
  const elCost = document.getElementById("token-cost");
  if (!chip) return;
  if (!usage || (usage.input === 0 && usage.output === 0)) {
    chip.classList.add("hidden");
    return;
  }
  chip.classList.remove("hidden");
  if (elIn) elIn.textContent = fmtTok(usage.input);
  if (elOut) elOut.textContent = fmtTok(usage.output);
  if (elCost) {
    if (usage.cost != null && usage.cost > 0) {
      elCost.textContent = " " + fmtCost(usage.cost);
    } else {
      elCost.textContent = "";
    }
  }
}

function showUsageModal(sessions) {
  const langZh = (document.documentElement.lang || "zh").startsWith("zh");
  const overlay = document.createElement("div");
  overlay.style.cssText = "position:fixed;inset:0;background:rgba(0,0,0,0.5);z-index:9999;display:flex;align-items:center;justify-content:center;";
  const panel = document.createElement("div");
  panel.style.cssText = "background:var(--surface,#fff);border-radius:12px;padding:24px;min-width:360px;max-width:560px;max-height:80vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.2);";
  let totalCost = 0, totalIn = 0, totalOut = 0, totalCacheRead = 0, totalCacheWrite = 0;
  let rows = sessions.map(s => {
    totalIn += Number(s.inputTokens || 0);
    totalOut += Number(s.outputTokens || 0);
    totalCost += Number(s.costUsd || 0);
    totalCacheRead += Number(s.cacheReadTokens || 0);
    totalCacheWrite += Number(s.cacheWriteTokens || 0);
    const cost = Number(s.costUsd || 0);
    return `<tr>
      <td style="padding:6px 12px;font-size:12px;max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${s.sessionKey || ""}">${s.sessionKey || "–"}</td>
      <td style="padding:6px 12px;font-size:12px">${fmtTok(s.inputTokens)}</td>
      <td style="padding:6px 12px;font-size:12px">${fmtTok(s.outputTokens)}</td>
      <td style="padding:6px 12px;font-size:12px">${fmtTok(s.cacheReadTokens)}</td>
      <td style="padding:6px 12px;font-size:12px">${fmtTok(s.cacheWriteTokens)}</td>
      <td style="padding:6px 12px;font-size:12px">${cost > 0 ? fmtCost(cost) : "–"}</td>
    </tr>`;
  }).join("");
  const title = langZh ? "Token 使用详情" : "Token Usage Details";
  const colSession = langZh ? "会话" : "Session";
  const colIn = langZh ? "输入" : "In";
  const colOut = langZh ? "输出" : "Out";
  const colCR = langZh ? "缓存读" : "Cache R";
  const colCW = langZh ? "缓存写" : "Cache W";
  const colCost = langZh ? "费用" : "Cost";
  panel.innerHTML = `
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
      <h3 style="margin:0;font-size:16px">${title}</h3>
      <button id="usage-modal-close" style="background:none;border:none;font-size:20px;cursor:pointer;padding:4px;line-height:1">×</button>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px;text-align:center">
      <div><div style="font-size:20px;font-weight:600">${fmtTok(totalIn)}</div><div style="font-size:11px;color:var(--muted)">${colIn} ↑</div></div>
      <div><div style="font-size:20px;font-weight:600">${fmtTok(totalOut)}</div><div style="font-size:11px;color:var(--muted)">${colOut} ↓</div></div>
      <div><div style="font-size:20px;font-weight:600">${totalCost > 0 ? fmtCost(totalCost) : "–"}</div><div style="font-size:11px;color:var(--muted)">${colCost}</div></div>
    </div>
    <div style="margin-bottom:16px;font-size:11px;color:var(--muted)">${colCR}: ${fmtTok(totalCacheRead)} &nbsp;|&nbsp; ${colCW}: ${fmtTok(totalCacheWrite)}</div>
    ${rows ? `<table style="width:100%;border-collapse:collapse">
      <thead><tr style="border-bottom:1px solid var(--border)">
        <th style="text-align:left;padding:4px 12px;font-size:11px;font-weight:600">${colSession}</th>
        <th style="text-align:right;padding:4px 12px;font-size:11px;font-weight:600">${colIn}</th>
        <th style="text-align:right;padding:4px 12px;font-size:11px;font-weight:600">${colOut}</th>
        <th style="text-align:right;padding:4px 12px;font-size:11px;font-weight:600">${colCR}</th>
        <th style="text-align:right;padding:4px 12px;font-size:11px;font-weight:600">${colCW}</th>
        <th style="text-align:right;padding:4px 12px;font-size:11px;font-weight:600">${colCost}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>` : `<p style="color:var(--muted);font-size:13px;text-align:center;padding:16px">${langZh ? "暂无数据" : "No data yet"}</p>`}
  `;
  overlay.appendChild(panel);
  document.body.appendChild(overlay);
  overlay.addEventListener("click", e => { if (e.target === overlay) overlay.remove(); });
  document.getElementById("usage-modal-close").addEventListener("click", () => overlay.remove());
}

async function showUsagePanel() {
  try {
    const res = await fetch("/api/usage");
    if (!res.ok) return;
    const data = await res.json();
    if (data && data.sessions) {
      showUsageModal(data.sessions);
    }
  } catch (_) {}
}

document.addEventListener("DOMContentLoaded", () => {
  const chip = document.getElementById("token-chip");
  if (chip) chip.addEventListener("click", showUsagePanel);
});

// Extend onDone to consume usage data from SSE done payload
const _origOnDone = window._onDoneRef;
// We'll patch the onDone handler inline below (see token-chip integration in onDone)

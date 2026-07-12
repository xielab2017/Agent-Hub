/* Hermes-ALI Campus Office frontend — i18n + themes */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

const ACCENTS = ["ocean", "forest", "amber", "rose", "slate", "teal"];

const I18N = {
  zh: {
    "login.hint": "输入访问密码以连接终端",
    "login.password": "密码",
    "login.submit": "进入",
    "login.error": "密码错误",
    "nav.newChat": "+ 新对话",
    "nav.chats": "会话",
    "nav.workflows": "工作流",
    "nav.control": "⚙ 控制中心",
    "chat.new": "新对话",
    "empty.title": "校园办公 AI 终端",
    "empty.body": "Hermes 管任务 · OpenSquilla 式路由 · Obsidian 存知识<br/>从左侧选择办公工作流，或直接对话。",
    "composer.route": "路由",
    "composer.workspace": "工作区",
    "composer.workspacePh": "可选：工作目录路径",
    "composer.inputPh": "输入消息或工作流内容… (Enter 发送)",
    "composer.send": "发送",
    "route.auto": "Auto（自动分级）",
    "route.simple": "C0 简单 / Qwen fast",
    "route.office": "C1 办公 / Qwen main",
    "route.c2": "C2 长文（生成+审核）",
    "route.reasoning": "C3 推理 / DeepSeek",
    "route.vision": "Vision / Qwen-VL",
    "control.title": "控制中心",
    "control.close": "关闭",
    "control.appearance": "外观",
    "control.health": "健康",
    "control.backend": "后端",
    "control.models": "模型",
    "control.routing": "路由",
    "control.obsidian": "知识库",
    "control.security": "安全",
    "control.save": "保存配置",
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
    "appearance.hint": "可在侧栏一键切换；保存配置后会同步到服务器，供多设备默认使用。",
    "theme.dark": "深色",
    "theme.light": "浅色",
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
    "nav.newChat": "+ New chat",
    "nav.chats": "Chats",
    "nav.workflows": "Workflows",
    "nav.control": "⚙ Control Center",
    "chat.new": "New chat",
    "empty.title": "Campus Office AI Terminal",
    "empty.body": "Hermes runs tasks · OpenSquilla-style routing · Obsidian stores knowledge<br/>Pick an office workflow on the left, or just chat.",
    "composer.route": "Route",
    "composer.workspace": "Workspace",
    "composer.workspacePh": "Optional workspace path",
    "composer.inputPh": "Message or workflow input… (Enter to send)",
    "composer.send": "Send",
    "route.auto": "Auto (classify)",
    "route.simple": "C0 Simple / Qwen fast",
    "route.office": "C1 Office / Qwen main",
    "route.c2": "C2 Long-form (gen + review)",
    "route.reasoning": "C3 Reasoning / DeepSeek",
    "route.vision": "Vision / Qwen-VL",
    "control.title": "Control Center",
    "control.close": "Close",
    "control.appearance": "Appearance",
    "control.health": "Health",
    "control.backend": "Backend",
    "control.models": "Models",
    "control.routing": "Routing",
    "control.obsidian": "Knowledge",
    "control.security": "Security",
    "control.save": "Save",
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
    "appearance.hint": "Use sidebar toggles anytime. Saving syncs defaults to the server for other devices.",
    "theme.dark": "Dark",
    "theme.light": "Light",
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
  status: null,
  settings: null,
  pendingWf: null,
  lastAssistantText: "",
  prefs: {
    language: localStorage.getItem("hermes_ali_lang") || "zh",
    theme: localStorage.getItem("hermes_ali_theme") || "dark",
    accent: localStorage.getItem("hermes_ali_accent") || "ocean",
  },
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
  const langBtn = $("#btn-lang");
  if (langBtn) langBtn.textContent = lang === "zh" ? "中 / EN" : "EN / 中";
  const themeBtn = $("#btn-theme");
  if (themeBtn) themeBtn.textContent = state.prefs.theme === "dark" ? "☾ Dark" : "☀ Light";
}

function applyTheme() {
  document.documentElement.setAttribute("data-theme", state.prefs.theme === "light" ? "light" : "dark");
  document.documentElement.setAttribute("data-accent", ACCENTS.includes(state.prefs.accent) ? state.prefs.accent : "ocean");
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", state.prefs.theme === "light" ? "#f4f7fb" : "#0f1419");
  renderAccentDots();
  applyI18n();
}

function persistPrefsLocal() {
  localStorage.setItem("hermes_ali_lang", state.prefs.language);
  localStorage.setItem("hermes_ali_theme", state.prefs.theme);
  localStorage.setItem("hermes_ali_accent", state.prefs.accent);
}

async function persistPrefsServer() {
  try {
    const view = state.settings || (await api("/api/settings"));
    const cfg = JSON.parse(JSON.stringify((view && view.config) || {}));
    if (!cfg.ali) cfg.ali = {};
    cfg.ali.language = state.prefs.language;
    cfg.ali.theme = state.prefs.theme;
    cfg.ali.accent = state.prefs.accent;
    const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg }) });
    state.settings = data;
  } catch (_) {
    /* offline / unauth — local prefs still apply */
  }
}

function setPrefs(partial, { syncServer = false } = {}) {
  Object.assign(state.prefs, partial);
  persistPrefsLocal();
  applyTheme();
  if (syncServer) persistPrefsServer();
  if (state.status) {
    renderConn(state.status);
    renderAgent(state.status);
  }
  if (state.workflows.length) renderWorkflowList();
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

function renderMd(text) {
  let s = escapeHtml(text);
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code}</code></pre>`);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/_([^_]+)_/g, "<em>$1</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  s = s.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  s = s.replace(/^- (.+)$/gm, "<div>• $1</div>");
  s = s.replace(/\n/g, "<br>");
  return s;
}

async function boot() {
  applyTheme();
  try {
    const status = await api("/api/status");
    state.status = status;
    $("#version-label").textContent = `v${status.version || "1.1.1"}`;
    if (status.ui) {
      // Server defaults fill gaps; localStorage already loaded — prefer local if set
      const hasLocal =
        localStorage.getItem("hermes_ali_lang") ||
        localStorage.getItem("hermes_ali_theme") ||
        localStorage.getItem("hermes_ali_accent");
      if (!hasLocal) {
        setPrefs({
          language: status.ui.language || "zh",
          theme: status.ui.theme || "dark",
          accent: status.ui.accent || "ocean",
        });
      }
    }
    renderConn(status);
    renderAgent(status);
    if (status.default_route) $("#route-select").value = status.default_route;
    if (status.auth_required && !status.authenticated && !state.token) {
      showLogin(true);
      applyI18n();
      return;
    }
    showLogin(false);
    await Promise.all([refreshSessions(), loadWorkflows(), loadSettings()]);
    if (status.health && status.health.workspace) {
      $("#workspace-input").value = status.health.workspace;
    }
    applyI18n();
    if (!state.sessions.length) await createSession();
    else await selectSession(state.sessions[0].id);
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

function renderAgent(status) {
  const el = $("#agent-badge");
  const agent = status.agent || {};
  const health = status.health || {};
  const policy = health.data_policy || "";
  if (agent.available) {
    el.textContent = `${t("agent.ready")} · ${policy || "office"}`;
    el.className = "badge ok";
  } else {
    el.textContent = `${t("agent.demo")} · ${policy || "office"}`;
    el.className = "badge warn";
  }
}

async function refreshSessions() {
  const data = await api("/api/sessions");
  state.sessions = data.sessions || [];
  const list = $("#session-list");
  list.innerHTML = "";
  state.sessions.forEach((s) => {
    const btn = document.createElement("button");
    btn.className = "session-item" + (s.id === state.currentId ? " active" : "");
    const title = s.title || t("chat.new");
    btn.innerHTML = `<span class="title">${escapeHtml(title)}</span>
      <span class="del" title="Delete" data-del="${s.id}">×</span>`;
    btn.addEventListener("click", (e) => {
      if (e.target && e.target.dataset && e.target.dataset.del) {
        e.stopPropagation();
        deleteSession(e.target.dataset.del);
        return;
      }
      selectSession(s.id);
      setSidebarOpen(false);
    });
    list.appendChild(btn);
  });
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

async function loadSettings() {
  state.settings = await api("/api/settings");
  if (state.settings.config && state.settings.config.workspace) {
    $("#workspace-input").value = state.settings.config.workspace;
  }
}

async function createSession() {
  const s = await api("/api/sessions", { method: "POST", body: JSON.stringify({ title: t("chat.new") }) });
  await refreshSessions();
  await selectSession(s.id);
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
  const s = await api(`/api/sessions/${id}`);
  state.currentId = id;
  $("#chat-title").textContent = s.title || t("chat.new");
  renderMessages(s.messages || []);
  await refreshSessions();
  $("#input").focus();
}

function renderMessages(messages) {
  const box = $("#messages");
  box.innerHTML = "";
  if (!messages.length) {
    box.innerHTML = `<div class="empty-state" id="empty-state">
      <div class="empty-logo">ALI</div>
      <h3 data-i18n="empty.title">${escapeHtml(t("empty.title"))}</h3>
      <p data-i18n-html="empty.body">${t("empty.body")}</p>
    </div>`;
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
  const role = m.role === "user" ? "You" : "Hermes";
  let route = "";
  if (m.route && m.route.tier) {
    route = ` · ${m.route.tier}/${m.route.route_key || ""}${m.route.model ? " · " + m.route.model : ""}`;
  }
  let tools = "";
  if (m.tools && m.tools.length) {
    tools = `<div class="tools">${m.tools
      .map((x) => `⚙ ${escapeHtml(x.name)} — ${escapeHtml(x.preview || "")}`)
      .join("<br>")}</div>`;
  }
  div.innerHTML = `<div class="meta">${role}${escapeHtml(route)}</div><div class="body">${
    m.role === "user" ? escapeHtml(m.content || "").replace(/\n/g, "<br>") : renderMd(m.content || "")
  }</div>${tools}`;
  $("#messages").appendChild(div);
  if (scroll) $("#messages").scrollTop = $("#messages").scrollHeight;
  return div;
}

function updateSendEnabled() {
  const has = $("#input").value.trim().length > 0;
  $("#btn-send").disabled = !has || state.streaming || !state.currentId;
}

function setRouteBadge(info) {
  if (!info) return;
  const label = `${info.tier || "?"}→${info.route_key || ""}${info.model ? " · " + info.model : ""}`;
  $("#route-badge").textContent = label;
}

async function sendMessage(overrideText, extra = {}) {
  const text = (overrideText != null ? overrideText : $("#input").value).trim();
  if (!text || !state.currentId || state.streaming) return;

  if (overrideText == null) $("#input").value = "";
  updateSendEnabled();
  appendMessage({ role: "user", content: extra.display_message || text });

  const assistantEl = appendMessage({ role: "assistant", content: "" });
  const bodyEl = assistantEl.querySelector(".body");
  state.streaming = true;
  state.lastAssistantText = "";
  $("#btn-stop").classList.remove("hidden");
  updateSendEnabled();

  let full = "";
  try {
    const start = await api(`/api/sessions/${state.currentId}/chat`, {
      method: "POST",
      body: JSON.stringify({
        message: text,
        route: $("#route-select").value || "auto",
        workspace: $("#workspace-input").value.trim(),
        ...extra,
      }),
    });
    if (start.route) setRouteBadge(start.route);
    await readSSE(`/api/stream/${start.stream_id}`, {
      onRoute(r) { setRouteBadge(r); },
      onToken(tok) {
        full += tok;
        state.lastAssistantText = full;
        bodyEl.innerHTML = renderMd(full);
        $("#messages").scrollTop = $("#messages").scrollHeight;
      },
      onTool(tool) {
        let tools = assistantEl.querySelector(".tools");
        if (!tools) {
          tools = document.createElement("div");
          tools.className = "tools";
          assistantEl.appendChild(tools);
        }
        tools.innerHTML += `⚙ ${escapeHtml(tool.name)} — ${escapeHtml(tool.preview || "")}<br>`;
      },
      onError(err) {
        full += `\n\n**Error:** ${err}`;
        bodyEl.innerHTML = renderMd(full);
        assistantEl.classList.add("error");
      },
    });
  } catch (err) {
    bodyEl.innerHTML = renderMd(`**Error:** ${err.message || err}`);
    assistantEl.classList.add("error");
  } finally {
    state.streaming = false;
    $("#btn-stop").classList.add("hidden");
    updateSendEnabled();
    await refreshSessions();
    const cur = state.sessions.find((s) => s.id === state.currentId);
    if (cur) $("#chat-title").textContent = cur.title || t("chat.new");
  }
  return full;
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
            if (event === "token" && handlers.onToken) handlers.onToken(payload.text || "");
            if (event === "tool" && handlers.onTool) handlers.onTool(payload);
            if (event === "error" && handlers.onError) handlers.onError(payload.message || "error");
            if (event === "done") { resolve(); return; }
          }
        }
        resolve();
      })
      .catch(reject);
  });
}

async function stopStream() {
  if (!state.currentId) return;
  try { await api(`/api/sessions/${state.currentId}/cancel`, { method: "POST", body: "{}" }); } catch (_) {}
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

  const data = await api("/api/workflows/run", {
    method: "POST",
    body: JSON.stringify({
      preset_id: w.id,
      session_id: state.currentId,
      input,
      workspace: $("#workspace-input").value.trim(),
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
  const assistantEl = appendMessage({ role: "assistant", content: "", route: data.route });
  const bodyEl = assistantEl.querySelector(".body");
  state.streaming = true;
  $("#btn-stop").classList.remove("hidden");
  let full = "";
  try {
    await readSSE(`/api/stream/${data.stream_id}`, {
      onRoute(r) { setRouteBadge(r); },
      onToken(tok) {
        full += tok;
        state.lastAssistantText = full;
        bodyEl.innerHTML = renderMd(full);
        $("#messages").scrollTop = $("#messages").scrollHeight;
      },
      onTool(tool) {
        let tools = assistantEl.querySelector(".tools");
        if (!tools) {
          tools = document.createElement("div");
          tools.className = "tools";
          assistantEl.appendChild(tools);
        }
        tools.innerHTML += `⚙ ${escapeHtml(tool.name)} — ${escapeHtml(tool.preview || "")}<br>`;
      },
      onError(err) {
        full += `\n\n**Error:** ${err}`;
        bodyEl.innerHTML = renderMd(full);
        assistantEl.classList.add("error");
      },
    });
  } finally {
    state.streaming = false;
    $("#btn-stop").classList.add("hidden");
    await refreshSessions();
  }

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
  if (on) renderControl();
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

async function renderControl() {
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
        selected: state.prefs.theme,
        options: [
          { value: "dark", label: t("theme.dark") },
          { value: "light", label: t("theme.light") },
        ],
      }, "select")}
      ${field(t("appearance.accent"), "ali.accent", {
        selected: state.prefs.accent,
        options: ACCENTS.map((a) => ({ value: a, label: a })),
      }, "select")}
    </div>
    <div class="accent-row" id="accent-row-control"></div>
    <p class="muted">${escapeHtml(t("appearance.hint"))}</p>`;

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
        setPrefs({ accent: name });
        renderControl();
      });
      ctrlRow.appendChild(b);
    });
  }

  $$("#ctab-appearance [data-key]").forEach((el) => {
    el.addEventListener("change", () => {
      const key = el.getAttribute("data-key");
      if (key === "ali.language") setPrefs({ language: el.value });
      if (key === "ali.theme") setPrefs({ theme: el.value });
      if (key === "ali.accent") setPrefs({ accent: el.value });
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
  const langZh = state.prefs.language !== "en";

  $("#ctab-backend").innerHTML = `
    <div class="grid-2">
      ${field(langZh ? "后端类型 / Provider" : "Backend type", "backend.type", {
        selected: b.type || "campus-openai-compatible",
        options: providerOpts,
      }, "select")}
      ${field(langZh ? "API Key 环境变量名（不要填密钥本身）" : "API key ENV name (not the secret)", "backend.api_key_env",
        looksLikeSecret(b.api_key_env) ? "" : (b.api_key_env || ""))}
      ${field("Base URL", "backend.base_url", b.base_url || "")}
      ${field("Timeout (s)", "backend.timeout_seconds", String(b.timeout_seconds || 60), "number")}
    </div>
    <p class="muted" id="provider-hint">${escapeHtml((currentProv && currentProv.hint) || "")}</p>
    ${looksLikeSecret(b.api_key_env) ? `<p class="warn-box">${langZh
      ? "⚠ 检测到你把真实 API Key 填进了「环境变量名」。已拒绝保存密钥。请在系统环境变量中设置（如 NVIDIA_API_KEY），此处只填变量名。若密钥已泄露请立刻轮换。"
      : "⚠ A real API key was pasted into the env-name field. Cleared. Set the secret in your OS env (e.g. NVIDIA_API_KEY) and put only the variable NAME here. Rotate the key if exposed."}</p>` : ""}
    <div class="row gap" style="justify-content:flex-start;flex-wrap:wrap">
      <button type="button" class="btn primary" id="btn-apply-provider">${langZh ? "应用此厂商并刷新模型" : "Apply provider → refresh models"}</button>
    </div>
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
        const data = await api("/api/settings/apply-provider", {
          method: "POST",
          body: JSON.stringify({ provider: pid, fill_models: true }),
        });
        state.settings = data;
        if (data.warning) alert(data.warning);
        $("#settings-status").textContent = langZh ? "已切换厂商并写入推荐模型" : "Provider applied with model defaults";
        renderControl();
        document.querySelector('.ctab[data-ctab="models"]')?.click();
      } catch (e) {
        $("#settings-status").textContent = e.message;
      }
    };
  }

  const m = cfg.models || {};
  const suggestions = (currentProv && currentProv.suggestions) || {};
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
    const opts = suggestions[slot.id] || [];
    const listId = `suggest-${slot.id}`;
    return `<label class="field"><span>${escapeHtml(slot.label)} <em class="muted">(${escapeHtml(slot.tier)})</em></span>
      <input list="${listId}" data-key="models.${escapeHtml(legacy)}" value="${escapeHtml(val)}" placeholder="${langZh ? "选择或输入模型 ID" : "pick or type model id"}" />
      <datalist id="${listId}">${opts.map((o) => `<option value="${escapeHtml(o)}"></option>`).join("")}</datalist>
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
          <input data-key="hybrid.${rk.key}.model" value="${escapeHtml(entry.model || "")}" placeholder="model id" />
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
  $("#ctab-routing").innerHTML = `
    <div class="grid-2">
      ${field("simple →", "routing.simple", r.simple || "qwen_fast")}
      ${field("office →", "routing.office", r.office || "qwen_main")}
      ${field("vision →", "routing.vision", r.vision || "qwen_vl")}
      ${field("reasoning →", "routing.reasoning", r.reasoning || "deepseek_reasoning")}
    </div>
    ${field("restricted_external_fallback", "routing.restricted_external_fallback", !!r.restricted_external_fallback, "checkbox")}
    <table class="matrix"><thead><tr><th>Tier</th><th>Examples</th><th>Provider</th><th>Model</th></tr></thead>
    <tbody>${(matrix.matrix || []).map((row) =>
      `<tr><td>${escapeHtml(row.tier)}</td><td>${escapeHtml(row.examples)}</td>
       <td>${escapeHtml(row.provider || "—")}</td><td><code>${escapeHtml(row.model || "—")}</code></td></tr>`
    ).join("")}</tbody></table>`;

  const o = cfg.obsidian || {};
  $("#ctab-obsidian").innerHTML = `
    ${field("Vault path", "obsidian.vault_path", o.vault_path || "")}
    ${field("AI inbox", "obsidian.ai_inbox", o.ai_inbox || "00_Inbox/AI_Candidates")}
    ${field("Allowed roots (comma)", "obsidian.allowed_roots", (o.allowed_roots || []).join(", "))}
    ${field("Write requires approval", "obsidian.write_requires_approval", o.write_requires_approval !== false, "checkbox")}`;

  $("#ctab-security").innerHTML = `
    ${field("data_policy", "data_policy", { selected: cfg.data_policy || "internal", options: ["public", "internal", "restricted"] }, "select")}
    <p class="muted"><code>${escapeHtml((state.settings && state.settings.config_path) || "")}</code></p>
    ${field("Import campus-office-ai.json path", "import_path", "")}
    <button type="button" class="btn ghost" id="btn-import-cfg">Import</button>`;

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
  if (!cfg.ali) cfg.ali = {};
  cfg.ali.language = state.prefs.language;
  cfg.ali.theme = state.prefs.theme;
  cfg.ali.accent = state.prefs.accent;
  // mode follows backend type
  if ((cfg.backend || {}).type === "hybrid") cfg.mode = "hybrid";
  else if (cfg.mode === "hybrid" && (cfg.backend || {}).type !== "hybrid") {
    // keep hybrid bindings if user still has hybrid map, else single
    cfg.mode = Object.keys(cfg.hybrid || {}).length ? "hybrid" : "single";
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
  const cfg = collectSettingsFromForm();
  const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg }) });
  state.settings = data;
  if (cfg.ali) {
    setPrefs({
      language: cfg.ali.language || state.prefs.language,
      theme: cfg.ali.theme || state.prefs.theme,
      accent: cfg.ali.accent || state.prefs.accent,
    });
  }
  $("#settings-status").textContent = `${t("saved")} ${new Date().toLocaleTimeString()}`;
  const status = await api("/api/status");
  state.status = status;
  renderAgent(status);
  renderConn(status);
}

$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((x) => x.classList.remove("active"));
    tab.classList.add("active");
    const panel = tab.dataset.panel;
    $("#panel-chats").classList.toggle("hidden", panel !== "chats");
    $("#panel-workflows").classList.toggle("hidden", panel !== "workflows");
  });
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

$("#btn-new").addEventListener("click", () => createSession());
$("#btn-send").addEventListener("click", () => sendMessage());
$("#btn-stop").addEventListener("click", stopStream);
$("#btn-menu").addEventListener("click", () => setSidebarOpen(true));
$("#sidebar-backdrop").addEventListener("click", () => setSidebarOpen(false));
$("#btn-control").addEventListener("click", () => openControl(true));
$("#btn-control-close").addEventListener("click", () => openControl(false));
$("#btn-save-settings").addEventListener("click", () => saveSettings().catch((e) => {
  $("#settings-status").textContent = e.message;
}));
$("#wf-cancel").addEventListener("click", () => $("#wf-overlay").classList.add("hidden"));
$("#wf-run").addEventListener("click", () => runWorkflow().catch((e) => alert(e.message)));

$("#btn-lang").addEventListener("click", () => {
  setPrefs({ language: state.prefs.language === "zh" ? "en" : "zh" }, { syncServer: true });
});
$("#btn-theme").addEventListener("click", () => {
  setPrefs({ theme: state.prefs.theme === "dark" ? "light" : "dark" }, { syncServer: true });
});

$("#input").addEventListener("input", () => {
  updateSendEnabled();
  const el = $("#input");
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 160) + "px";
});
$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

applyTheme();
boot();

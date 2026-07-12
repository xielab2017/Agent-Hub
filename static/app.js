/* Hermes-ALI Campus Office frontend */

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

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
};

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
  try {
    const status = await api("/api/status");
    state.status = status;
    $("#version-label").textContent = `v${status.version || "1.1.0"}`;
    renderConn(status);
    renderAgent(status);
    if (status.default_route) $("#route-select").value = status.default_route;
    if (status.auth_required && !status.authenticated && !state.token) {
      showLogin(true);
      return;
    }
    showLogin(false);
    await Promise.all([refreshSessions(), loadWorkflows(), loadSettings()]);
    if (status.health && status.health.workspace) {
      $("#workspace-input").value = status.health.workspace;
    }
    if (!state.sessions.length) await createSession();
    else await selectSession(state.sessions[0].id);
  } catch (err) {
    if (String(err.message) !== "unauthorized") {
      $("#agent-badge").textContent = "offline";
      console.error(err);
    }
  }
}

function renderConn(status) {
  const port = status.port || 8765;
  const ips = status.local_ips || [];
  const lines = [`本机: http://127.0.0.1:${port}`];
  ips.slice(0, 2).forEach((ip) => lines.push(`局域网: http://${ip}:${port}`));
  $("#conn-info").innerHTML = lines.map(escapeHtml).join("<br>");
}

function renderAgent(status) {
  const el = $("#agent-badge");
  const agent = status.agent || {};
  const health = status.health || {};
  const policy = health.data_policy || "";
  if (agent.available) {
    el.textContent = `Agent ready · ${policy || "office"}`;
    el.className = "badge ok";
  } else {
    el.textContent = `Demo · ${policy || "office"}`;
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
    btn.innerHTML = `<span class="title">${escapeHtml(s.title || "New chat")}</span>
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

async function loadWorkflows() {
  const data = await api("/api/workflows");
  state.workflows = data.presets || [];
  const list = $("#workflow-list");
  list.innerHTML = "";
  state.workflows.forEach((w) => {
    const btn = document.createElement("button");
    btn.className = "wf-item";
    btn.innerHTML = `<div class="name">${escapeHtml(w.icon || "")} ${escapeHtml(w.name)}</div>
      <div class="desc">${escapeHtml(w.description || "")}</div>
      <span class="tier">${escapeHtml(w.tier)} · ${escapeHtml(w.route)}</span>`;
    btn.addEventListener("click", () => openWorkflow(w));
    list.appendChild(btn);
  });
}

async function loadSettings() {
  state.settings = await api("/api/settings");
  if (state.settings.config && state.settings.config.workspace) {
    $("#workspace-input").value = state.settings.config.workspace;
  }
}

async function createSession() {
  const s = await api("/api/sessions", { method: "POST", body: JSON.stringify({ title: "New chat" }) });
  await refreshSessions();
  await selectSession(s.id);
}

async function deleteSession(id) {
  await api(`/api/sessions/${id}`, { method: "DELETE" });
  if (state.currentId === id) {
    state.currentId = null;
    $("#messages").innerHTML = "";
    $("#chat-title").textContent = "New chat";
  }
  await refreshSessions();
  if (!state.currentId && state.sessions.length) await selectSession(state.sessions[0].id);
  else if (!state.sessions.length) await createSession();
}

async function selectSession(id) {
  const s = await api(`/api/sessions/${id}`);
  state.currentId = id;
  $("#chat-title").textContent = s.title || "New chat";
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
      <h3>校园办公 AI 终端</h3>
      <p>Hermes 管任务 · OpenSquilla 式路由 · Obsidian 存知识<br/>从左侧选择办公工作流，或直接对话。</p>
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
      .map((t) => `⚙ ${escapeHtml(t.name)} — ${escapeHtml(t.preview || "")}`)
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
      onToken(t) {
        full += t;
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
    if (cur) $("#chat-title").textContent = cur.title || "New chat";
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

/* ---- Workflows ---- */
function openWorkflow(w) {
  state.pendingWf = w;
  $("#wf-title").textContent = `${w.icon || ""} ${w.name}`;
  $("#wf-desc").textContent = w.description || "";
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

  // Stream already started by server — attach to SSE
  appendMessage({ role: "user", content: `[${w.name}] ${input || "(使用工作流模板)"}`, route: data.route });
  const assistantEl = appendMessage({ role: "assistant", content: "", route: data.route });
  const bodyEl = assistantEl.querySelector(".body");
  state.streaming = true;
  $("#btn-stop").classList.remove("hidden");
  let full = "";
  try {
    await readSSE(`/api/stream/${data.stream_id}`, {
      onRoute(r) { setRouteBadge(r); },
      onToken(t) {
        full += t;
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
    const ok = confirm("将结果写入 Obsidian AI_Candidates？仅候选区，不会进入正式目录。");
    if (ok) {
      const wr = await api("/api/obsidian/write", {
        method: "POST",
        body: JSON.stringify({
          title: w.name,
          content: full,
          approved: true,
          tags: ["ai-candidate", w.id],
        }),
      });
      if (wr.ok) appendMessage({ role: "assistant", content: `已写入知识库候选区：\`${wr.path}\`` });
      else appendMessage({ role: "assistant", content: `写入失败：${wr.error || "unknown"}`, error: true });
    }
  }
}

/* ---- Control Center ---- */
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
    const opts = value.options.map((o) =>
      `<option value="${escapeHtml(o)}" ${o === value.selected ? "selected" : ""}>${escapeHtml(o)}</option>`
    ).join("");
    return `<label class="field"><span>${escapeHtml(label)}</span>
      <select data-key="${escapeHtml(key)}">${opts}</select></label>`;
  }
  if (type === "textarea") {
    return `<label class="field"><span>${escapeHtml(label)}</span>
      <textarea data-key="${escapeHtml(key)}" rows="3">${escapeHtml(value || "")}</textarea></label>`;
  }
  return `<label class="field"><span>${escapeHtml(label)}</span>
    <input type="${type}" data-key="${escapeHtml(key)}" value="${escapeHtml(value || "")}" /></label>`;
}

async function renderControl() {
  await loadSettings();
  const cfg = (state.settings && state.settings.config) || {};
  const health = await api("/api/health/office");
  const matrix = await api("/api/routing");

  $("#ctab-health").innerHTML = (health.checks || []).map((c) =>
    `<div class="check-row"><div><strong>${escapeHtml(c.id)}</strong><div class="muted">${escapeHtml(c.detail || "")}</div></div>
      <span class="${c.ok ? "ok" : "bad"}">${c.ok ? "PASS" : "CHECK"}</span></div>`
  ).join("") + `<p class="muted">API Key (${escapeHtml((health.api_key || {}).env_name || "")}): ${(health.api_key || {}).present ? "已设置" : "未设置 — 请用系统环境变量，勿写入 JSON"}</p>`;

  const b = cfg.backend || {};
  $("#ctab-backend").innerHTML = `
    <div class="grid-2">
      ${field("Backend type", "backend.type", { selected: b.type || "campus-openai-compatible", options: ["campus-openai-compatible", "nvidia-nim", "local-ollama"] }, "select")}
      ${field("API key env name", "backend.api_key_env", b.api_key_env || "CAMPUS_LLM_API_KEY")}
      ${field("Base URL", "backend.base_url", b.base_url || "")}
      ${field("Timeout (s)", "backend.timeout_seconds", String(b.timeout_seconds || 60), "number")}
    </div>
    ${field("Install / workspace root", "install_root", cfg.install_root || "")}
    ${field("Default workspace", "workspace", cfg.workspace || "")}
    <p class="muted">密钥只放在环境变量（如 CAMPUS_LLM_API_KEY），与手册一致。</p>`;

  const m = cfg.models || {};
  $("#ctab-models").innerHTML = `
    <div class="grid-2">
      ${field("Qwen fast (C0)", "models.qwen_fast", m.qwen_fast || "")}
      ${field("Qwen main (C1/C2)", "models.qwen_main", m.qwen_main || "")}
      ${field("Qwen VL (Vision)", "models.qwen_vl", m.qwen_vl || "")}
      ${field("DeepSeek reasoning (C3)", "models.deepseek_reasoning", m.deepseek_reasoning || "")}
      ${field("Embedding", "models.embedding", m.embedding || "")}
      ${field("Reranker", "models.reranker", m.reranker || "")}
    </div>
    <p class="muted">模型 ID 必须来自校园 <code>/v1/models</code>，勿用宣传名猜测。</p>`;

  const r = cfg.routing || {};
  $("#ctab-routing").innerHTML = `
    <div class="grid-2">
      ${field("simple →", "routing.simple", r.simple || "qwen_fast")}
      ${field("office →", "routing.office", r.office || "qwen_main")}
      ${field("vision →", "routing.vision", r.vision || "qwen_vl")}
      ${field("reasoning →", "routing.reasoning", r.reasoning || "deepseek_reasoning")}
    </div>
    ${field("允许受限数据外部降级（危险）", "routing.restricted_external_fallback", !!r.restricted_external_fallback, "checkbox")}
    <table class="matrix"><thead><tr><th>等级</th><th>场景</th><th>路由</th><th>当前模型</th></tr></thead>
    <tbody>${(matrix.matrix || []).map((row) =>
      `<tr><td>${escapeHtml(row.tier)}</td><td>${escapeHtml(row.examples)}</td>
       <td>${escapeHtml(row.route_key)}</td><td><code>${escapeHtml(row.model || "(未配置)")}</code></td></tr>`
    ).join("")}</tbody></table>`;

  const o = cfg.obsidian || {};
  $("#ctab-obsidian").innerHTML = `
    ${field("Vault 路径", "obsidian.vault_path", o.vault_path || "")}
    ${field("AI 候选目录", "obsidian.ai_inbox", o.ai_inbox || "00_Inbox/AI_Candidates")}
    ${field("允许检索目录（逗号分隔）", "obsidian.allowed_roots", (o.allowed_roots || []).join(", "))}
    ${field("写入需审批", "obsidian.write_requires_approval", o.write_requires_approval !== false, "checkbox")}
    <p class="muted">正式目录只放人工审核后的笔记；AI 默认只写 AI_Candidates。</p>`;

  $("#ctab-security").innerHTML = `
    ${field("数据策略", "data_policy", { selected: cfg.data_policy || "internal", options: ["public", "internal", "restricted"] }, "select")}
    <p class="muted">restricted：禁止校外 NVIDIA/云端降级。邮件发送、删改文件、防火墙、开机启动均需人工确认。</p>
    <p class="muted">配置文件：<code>${escapeHtml((state.settings && state.settings.config_path) || "")}</code></p>
    ${field("从本地路径导入 campus-office-ai.json", "import_path", "")}
    <button type="button" class="btn ghost" id="btn-import-cfg">导入配置文件</button>`;

  const importBtn = $("#btn-import-cfg");
  if (importBtn) {
    importBtn.onclick = async () => {
      const path = document.querySelector('[data-key="import_path"]').value.trim();
      if (!path) return;
      try {
        await api("/api/settings/import", { method: "POST", body: JSON.stringify({ path }) });
        $("#settings-status").textContent = "已导入";
        renderControl();
      } catch (e) {
        $("#settings-status").textContent = e.message;
      }
    };
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
    const parts = key.split(".");
    let cur = cfg;
    for (let i = 0; i < parts.length - 1; i++) {
      if (!cur[parts[i]] || typeof cur[parts[i]] !== "object") cur[parts[i]] = {};
      cur = cur[parts[i]];
    }
    cur[parts[parts.length - 1]] = val;
  });
  return cfg;
}

async function saveSettings() {
  const cfg = collectSettingsFromForm();
  const data = await api("/api/settings", { method: "POST", body: JSON.stringify({ config: cfg }) });
  state.settings = data;
  $("#settings-status").textContent = "已保存 " + new Date().toLocaleTimeString();
  const status = await api("/api/status");
  state.status = status;
  renderAgent(status);
}

/* ---- Events ---- */
$$(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".tab").forEach((t) => t.classList.remove("active"));
    tab.classList.add("active");
    const panel = tab.dataset.panel;
    $("#panel-chats").classList.toggle("hidden", panel !== "chats");
    $("#panel-workflows").classList.toggle("hidden", panel !== "workflows");
  });
});

$$(".ctab").forEach((tab) => {
  tab.addEventListener("click", () => {
    $$(".ctab").forEach((t) => t.classList.remove("active"));
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
    $("#login-error").textContent = "密码错误";
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

boot();

/* Hermes-ALI frontend — vanilla JS, no build step */

const $ = (sel) => document.querySelector(sel);

const state = {
  token: localStorage.getItem("hermes_ali_token") || "",
  sessions: [],
  currentId: null,
  streaming: false,
  status: null,
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
  if (!res.ok) {
    throw new Error((data && data.error) || res.statusText || "request failed");
  }
  return data;
}

function showLogin(on) {
  $("#login-overlay").classList.toggle("hidden", !on);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

/** Minimal markdown: bold, italic, code, links, newlines */
function renderMd(text) {
  let s = escapeHtml(text);
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => `<pre><code>${code}</code></pre>`);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/_([^_]+)_/g, "<em>$1</em>");
  s = s.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  s = s.replace(/\n/g, "<br>");
  return s;
}

function setSidebarOpen(open) {
  $("#sidebar").classList.toggle("open", open);
  $("#sidebar-backdrop").classList.toggle("hidden", !open);
}

async function boot() {
  try {
    const status = await api("/api/status");
    state.status = status;
    $("#version-label").textContent = `v${status.version || "1.0.0"}`;
    renderConn(status);
    renderAgent(status.agent);
    if (status.auth_required && !status.authenticated && !state.token) {
      showLogin(true);
      return;
    }
    showLogin(false);
    await refreshSessions();
    if (!state.sessions.length) {
      await createSession();
    } else {
      await selectSession(state.sessions[0].id);
    }
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
  ips.slice(0, 3).forEach((ip) => lines.push(`局域网: http://${ip}:${port}`));
  $("#conn-info").innerHTML = lines.map(escapeHtml).join("<br>");
}

function renderAgent(agent) {
  const el = $("#agent-badge");
  if (!agent) {
    el.textContent = "unknown";
    return;
  }
  if (agent.available) {
    el.textContent = "Agent ready";
    el.className = "badge ok";
  } else {
    el.textContent = "Demo mode";
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

async function createSession() {
  const s = await api("/api/sessions", {
    method: "POST",
    body: JSON.stringify({ title: "New chat" }),
  });
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
  if (!state.currentId && state.sessions.length) {
    await selectSession(state.sessions[0].id);
  } else if (!state.sessions.length) {
    await createSession();
  }
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
      <h3>轻量 Hermes 终端</h3>
      <p>在任意设备浏览器中打开本页 IP 即可互通。<br/>发送消息开始对话。</p>
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
  let tools = "";
  if (m.tools && m.tools.length) {
    tools = `<div class="tools">${m.tools
      .map((t) => `⚙ ${escapeHtml(t.name)} — ${escapeHtml(t.preview || "")}`)
      .join("<br>")}</div>`;
  }
  div.innerHTML = `<div class="meta">${role}</div><div class="body">${
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

async function sendMessage() {
  const text = $("#input").value.trim();
  if (!text || !state.currentId || state.streaming) return;

  $("#input").value = "";
  updateSendEnabled();
  appendMessage({ role: "user", content: text });

  const assistantEl = appendMessage({ role: "assistant", content: "" });
  const bodyEl = assistantEl.querySelector(".body");
  state.streaming = true;
  $("#btn-stop").classList.remove("hidden");
  updateSendEnabled();

  let full = "";
  try {
    const start = await api(`/api/sessions/${state.currentId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message: text }),
    });
    const streamId = start.stream_id;
    await readSSE(`/api/stream/${streamId}`, {
      onToken(t) {
        full += t;
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
            try {
              payload = JSON.parse(data);
            } catch (_) {}
            if (event === "token" && handlers.onToken) handlers.onToken(payload.text || "");
            if (event === "tool" && handlers.onTool) handlers.onTool(payload);
            if (event === "error" && handlers.onError) handlers.onError(payload.message || "error");
            if (event === "done") {
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
  if (!state.currentId) return;
  try {
    await api(`/api/sessions/${state.currentId}/cancel`, { method: "POST", body: "{}" });
  } catch (_) {}
}

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
  } catch (err) {
    $("#login-error").textContent = "密码错误";
    $("#login-error").classList.remove("hidden");
  }
});

$("#btn-new").addEventListener("click", () => createSession());
$("#btn-send").addEventListener("click", sendMessage);
$("#btn-stop").addEventListener("click", stopStream);
$("#btn-menu").addEventListener("click", () => setSidebarOpen(true));
$("#sidebar-backdrop").addEventListener("click", () => setSidebarOpen(false));

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

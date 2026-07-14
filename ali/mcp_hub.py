"""Hub MCP (Model Context Protocol) config — bridge Hub tools ↔ GitHub / coding apps.

Stores server entries under ~/.agent-cli/mcp/servers.json and can sync into
Hermes config.yaml ``mcp_servers`` so Claw/Hermes sees the same bridges.
"""

from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from .home import ensure_home

# Curated templates for vibe-coding / Codex-style / GitHub workflows
MCP_TEMPLATES: list[dict[str, Any]] = [
    {
        "id": "github",
        "label": "GitHub",
        "label_zh": "GitHub",
        "desc": "Repos, issues, PRs via @modelcontextprotocol/server-github (needs GITHUB_PERSONAL_ACCESS_TOKEN).",
        "desc_zh": "通过 MCP 连接 GitHub（仓库/Issues/PR）；需设置 GITHUB_PERSONAL_ACCESS_TOKEN。",
        "use_case": "vibe-coding",
        "entry": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": ""},
        },
    },
    {
        "id": "filesystem",
        "label": "Filesystem",
        "label_zh": "工作区文件",
        "desc": "Expose a workspace folder as MCP tools for coding agents.",
        "desc_zh": "把工作区目录暴露为 MCP 工具，供编程 Agent 读写文件。",
        "use_case": "codex",
        "entry": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", str(Path.home())],
        },
    },
    {
        "id": "git",
        "label": "Git",
        "label_zh": "Git",
        "desc": "Local git status / diff / log via MCP git server.",
        "desc_zh": "本地 Git 状态 / diff / log（MCP git server）。",
        "use_case": "vibe-coding",
        "entry": {
            "command": "uvx",
            "args": ["mcp-server-git", "--repository", str(Path.home())],
        },
    },
    {
        "id": "memory",
        "label": "Memory",
        "label_zh": "Memory",
        "desc": "Persistent key-value memory MCP for long coding sessions.",
        "desc_zh": "长会话持久记忆 MCP（适合 Codex / vibe coding）。",
        "use_case": "codex",
        "entry": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-memory"],
        },
    },
]


def _mcp_dir() -> Path:
    d = ensure_home()["root"] / "mcp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def servers_path() -> Path:
    return _mcp_dir() / "servers.json"


def _load_raw() -> dict[str, Any]:
    path = servers_path()
    if not path.is_file():
        return {"schema_version": 1, "servers": {}, "enabled": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("servers", {})
            data.setdefault("enabled", [])
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"schema_version": 1, "servers": {}, "enabled": []}


def _save_raw(data: dict[str, Any]) -> None:
    path = servers_path()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def list_mcp() -> dict[str, Any]:
    raw = _load_raw()
    servers = raw.get("servers") or {}
    enabled = set(raw.get("enabled") or [])
    items = []
    for tid, entry in servers.items():
        items.append(
            {
                "id": tid,
                "enabled": tid in enabled,
                "config": entry,
            }
        )
    return {
        "ok": True,
        "path": str(servers_path()),
        "note_zh": (
            "MCP（Model Context Protocol）把 Hub / Hermes 工具桥接到外部应用："
            "GitHub、本地 Git、文件系统、Memory 等。启用后可同步到 Hermes config.yaml。"
            "Scientific Agent Skills / Anthropic Skills 见 Skills 页，用于 vibe coding / Codex 工作流。"
        ),
        "note_en": (
            "MCP bridges Hub/Hermes tools to external apps (GitHub, git, filesystem, memory). "
            "Enable entries then Sync to Hermes. Skills hub packs cover vibe-coding / Codex workflows."
        ),
        "templates": MCP_TEMPLATES,
        "items": items,
        "enabled": list(enabled),
    }


def enable_template(template_id: str, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = next((t for t in MCP_TEMPLATES if t["id"] == template_id), None)
    if not meta:
        raise ValueError(f"unknown MCP template: {template_id}")
    raw = _load_raw()
    entry = deepcopy(meta["entry"])
    if overrides:
        if "args" in overrides and isinstance(overrides["args"], list):
            entry["args"] = list(overrides["args"])
        if "env" in overrides and isinstance(overrides["env"], dict):
            env = dict(entry.get("env") or {})
            env.update({str(k): str(v) for k, v in overrides["env"].items()})
            entry["env"] = env
        if "command" in overrides:
            entry["command"] = str(overrides["command"])
        if "url" in overrides:
            entry = {"url": str(overrides["url"])}
            if overrides.get("headers"):
                entry["headers"] = overrides["headers"]
    raw.setdefault("servers", {})[template_id] = entry
    enabled = list(raw.get("enabled") or [])
    if template_id not in enabled:
        enabled.append(template_id)
    raw["enabled"] = enabled
    _save_raw(raw)
    return list_mcp()


def set_enabled(server_id: str, enabled: bool) -> dict[str, Any]:
    raw = _load_raw()
    if server_id not in (raw.get("servers") or {}):
        raise ValueError(f"MCP server not configured: {server_id}")
    cur = list(raw.get("enabled") or [])
    if enabled and server_id not in cur:
        cur.append(server_id)
    if not enabled:
        cur = [x for x in cur if x != server_id]
    raw["enabled"] = cur
    _save_raw(raw)
    return list_mcp()


def remove_server(server_id: str) -> dict[str, Any]:
    raw = _load_raw()
    (raw.get("servers") or {}).pop(server_id, None)
    raw["enabled"] = [x for x in (raw.get("enabled") or []) if x != server_id]
    _save_raw(raw)
    return list_mcp()


def upsert_server(server_id: str, entry: dict[str, Any], *, enable: bool = True) -> dict[str, Any]:
    sid = (server_id or "").strip()
    if not sid or not re.match(r"^[a-zA-Z0-9_-]+$", sid):
        raise ValueError("invalid server id")
    if not isinstance(entry, dict) or not (entry.get("command") or entry.get("url")):
        raise ValueError("entry needs command or url")
    raw = _load_raw()
    raw.setdefault("servers", {})[sid] = entry
    enabled = list(raw.get("enabled") or [])
    if enable and sid not in enabled:
        enabled.append(sid)
    raw["enabled"] = enabled
    _save_raw(raw)
    return list_mcp()


def active_servers_for_hermes() -> dict[str, Any]:
    raw = _load_raw()
    servers = raw.get("servers") or {}
    out: dict[str, Any] = {}
    for sid in raw.get("enabled") or []:
        entry = servers.get(sid)
        if isinstance(entry, dict):
            # Drop empty env values so Hermes does not get blank tokens
            cleaned = dict(entry)
            env = cleaned.get("env")
            if isinstance(env, dict):
                cleaned["env"] = {k: v for k, v in env.items() if str(v or "").strip()}
                if not cleaned["env"]:
                    cleaned.pop("env", None)
            out[sid] = cleaned
    return out


def sync_to_hermes() -> dict[str, Any]:
    """Merge Hub MCP servers into Hermes config.yaml mcp_servers block."""
    from . import hermes_cli

    active = active_servers_for_hermes()
    homes = hermes_cli.hermes_config_homes()
    written: list[str] = []
    for home in homes:
        path = home / "config.yaml"
        hermes_cli.merge_mcp_servers_into_config(path, active)
        written.append(str(path))
    return {
        "ok": True,
        "synced": len(active),
        "servers": list(active.keys()),
        "written": written,
        "note_zh": f"已将 {len(active)} 个 MCP 同步到 Hermes（{', '.join(active) or '无'}）。",
        "note_en": f"Synced {len(active)} MCP server(s) into Hermes ({', '.join(active) or 'none'}).",
    }

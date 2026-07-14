"""Agent Hub identity — multi-soul roles synced into model system prompts."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from .config import STATE_DIR, hermes_home
from .home import ensure_home
from .settings import load_campus_config, save_campus_config

DEFAULT_SOUL = """# SOUL.md — Agent Hub Identity

You are **Agent Hub**, the campus multi-agent workflow orchestrator for Shenzhen University of Advanced Technology.

## Core roles
- **Office**: meetings, email drafts, notices, schedules
- **Research**: literature notes, paper review, experiment logs
- **Ops**: deploy checks, skill install, workspace hygiene

## Principles
- Reply in the user's language: Chinese questions → Simplified Chinese, unless they explicitly request another language
- Prefer skills and tools when available; ask before irreversible actions
- Protect secrets; never echo API keys
- Execute multi-step office workflows; do not dump raw tool JSON to the user
- On failure, Agent Hub auto-searches GitHub for skills, installs them, and retries
"""

BUILTIN_ROLES = [
    {
        "id": "office",
        "label": "办公助理",
        "label_en": "Office",
        "skills": ["meeting-minutes", "email-draft", "notice-draft"],
        "desc": "会议纪要、邮件、通知与日程",
        "soul_snippet": "You are the Office soul of Agent Hub: meetings, email, notices, schedules.",
        "builtin": True,
    },
    {
        "id": "research",
        "label": "科研助手",
        "label_en": "Research",
        "skills": ["research-review", "literature-notes"],
        "desc": "文献笔记、审稿与实验记录",
        "soul_snippet": "You are the Research soul of Agent Hub: literature, papers, lab notes.",
        "builtin": True,
    },
    {
        "id": "ops",
        "label": "运维部署",
        "label_en": "Ops",
        "skills": ["deploy-campus-office-ai"],
        "desc": "部署检查、Skill 安装与工作区维护",
        "soul_snippet": "You are the Ops soul of Agent Hub: deploy checks, skills, workspace hygiene.",
        "builtin": True,
    },
]

CORE_ROLES = BUILTIN_ROLES


def soul_path() -> Path:
    """Canonical SOUL.md under Agent Hub home (also mirrored for Hermes runtime)."""
    root = ensure_home()["root"]
    path = root / "SOUL.md"
    return path


def hermes_soul_path() -> Path:
    return hermes_home() / "SOUL.md"


def _roles_file() -> Path:
    return STATE_DIR / "soul_roles.json"


def _load_roles_store() -> dict[str, Any]:
    """Persist custom roles + removed builtin ids (soft-delete from catalog)."""
    path = _roles_file()
    if not path.is_file():
        return {"roles": [], "removed": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {"roles": data, "removed": []}
        if not isinstance(data, dict):
            return {"roles": [], "removed": []}
        roles = data.get("roles") or []
        removed = [str(x).strip() for x in (data.get("removed") or []) if str(x).strip()]
        return {"roles": roles if isinstance(roles, list) else [], "removed": removed}
    except (OSError, json.JSONDecodeError):
        return {"roles": [], "removed": []}


def _save_roles_store(roles: list[dict[str, Any]], removed: list[str] | None = None) -> None:
    path = _roles_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = []
    for r in roles:
        if r.get("builtin"):
            continue
        if not r.get("id"):
            continue
        clean.append(
            {
                "id": r["id"],
                "label": r.get("label") or r["id"],
                "label_en": r.get("label_en") or r.get("label") or r["id"],
                "skills": list(r.get("skills") or []),
                "desc": r.get("desc") or "",
                "soul_snippet": r.get("soul_snippet") or "",
                "content": r.get("content") or "",
            }
        )
    builtin_ids = {r["id"] for r in BUILTIN_ROLES}
    removed_clean = []
    for rid in removed if removed is not None else _load_roles_store().get("removed") or []:
        rid = str(rid).strip()
        if rid and rid in builtin_ids and rid not in removed_clean:
            removed_clean.append(rid)
    path.write_text(
        json.dumps({"roles": clean, "removed": removed_clean}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_custom_roles() -> list[dict[str, Any]]:
    out = []
    for r in _load_roles_store().get("roles") or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        item = dict(r)
        item["builtin"] = False
        out.append(item)
    return out


def _save_custom_roles(roles: list[dict[str, Any]]) -> None:
    store = _load_roles_store()
    _save_roles_store(roles, list(store.get("removed") or []))


def _removed_builtin_ids() -> set[str]:
    return {str(x).strip() for x in (_load_roles_store().get("removed") or []) if str(x).strip()}


def all_roles() -> list[dict[str, Any]]:
    removed = _removed_builtin_ids()
    custom = _load_custom_roles()
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for r in BUILTIN_ROLES:
        rid = r["id"]
        if rid in removed:
            continue
        merged.append(dict(r))
        seen.add(rid)
    for r in custom:
        if r["id"] in seen:
            # allow custom to overlay builtin id only if explicitly different — skip overwrite
            continue
        merged.append(r)
        seen.add(r["id"])
    return merged


def get_role(role_id: str) -> dict[str, Any] | None:
    role_id = (role_id or "").strip()
    for r in all_roles():
        if r.get("id") == role_id:
            return r
    return None


def get_soul() -> dict[str, Any]:
    path = soul_path()
    # migrate legacy Hermes SOUL if hub missing
    if not path.is_file():
        legacy = hermes_soul_path()
        if legacy.is_file():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(legacy.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            except OSError:
                pass
    exists = path.is_file()
    content = ""
    if exists:
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            content = ""
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    roles = all_roles()
    active_role = (ali.get("active_soul_role") or "office").strip()
    role_ids = {r["id"] for r in roles}
    if active_role not in role_ids:
        active_role = roles[0]["id"] if roles else "office"
    active = get_role(active_role) or {}
    status = soul_runtime_status()
    return {
        "ok": True,
        "path": str(path),
        "exists": exists,
        "content": content,
        "core_roles": roles,
        "active_role": active_role,
        "active_role_meta": active,
        "default_preview": DEFAULT_SOUL[:400],
        "app_name": "Agent Hub",
        "runtime": status,
        "claw_soul": read_claw_soul(status.get("runtime_resolved")),
    }


def save_soul(content: str, *, seed_if_missing: bool = False) -> dict[str, Any]:
    path = soul_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (content or "").strip()
    if not text and seed_if_missing:
        text = DEFAULT_SOUL
    if not text:
        raise ValueError("SOUL content is empty")
    # rewrite legacy Hermes identity if seeding
    if seed_if_missing and "Hermes ALI" in text and "Agent Hub" not in text:
        text = DEFAULT_SOUL
    body = text + ("\n" if not text.endswith("\n") else "")
    path.write_text(body, encoding="utf-8")
    # Mirror to Hermes home so CLI agents see the same soul
    try:
        hp = hermes_soul_path()
        hp.parent.mkdir(parents=True, exist_ok=True)
        hp.write_text(body, encoding="utf-8")
    except OSError:
        pass
    # Immediately push fused Hub+Claw soul into the connected claw
    claw_sync: dict[str, Any] = {}
    try:
        claw_sync = sync_soul_to_claw()
    except Exception:  # noqa: BLE001
        claw_sync = {"ok": False}
    return {"ok": True, "path": str(path), "bytes": path.stat().st_size, "claw_sync": claw_sync}


def set_active_role(role_id: str, *, apply_to_soul_file: bool = True) -> dict[str, Any]:
    role_id = (role_id or "").strip()
    valid = {r["id"] for r in all_roles()}
    if role_id and role_id not in valid:
        raise ValueError(f"unknown role: {role_id}")
    cfg = load_campus_config()
    ali = cfg.setdefault("ali", {})
    if not isinstance(ali, dict):
        ali = {}
        cfg["ali"] = ali
    ali["active_soul_role"] = role_id or "office"
    save_campus_config(cfg)
    role = get_role(ali["active_soul_role"]) or {}
    # Sync role content into SOUL.md so selected model + Hermes CLI both see it
    claw_sync: dict[str, Any] = {}
    if apply_to_soul_file:
        snippet = (role.get("content") or role.get("soul_snippet") or "").strip()
        if snippet:
            label = role.get("label") or role_id
            composed = (
                f"# SOUL.md — Agent Hub · {label}\n\n"
                f"You are **Agent Hub** acting as soul role `{role_id}` ({label}).\n\n"
                f"{snippet.strip()}\n"
            )
            try:
                saved = save_soul(composed)
                claw_sync = saved.get("claw_sync") or {}
            except ValueError:
                try:
                    claw_sync = sync_soul_to_claw(role_id=ali["active_soul_role"])
                except Exception:  # noqa: BLE001
                    claw_sync = {}
        else:
            try:
                claw_sync = sync_soul_to_claw(role_id=ali["active_soul_role"])
            except Exception:  # noqa: BLE001
                claw_sync = {}
    else:
        try:
            claw_sync = sync_soul_to_claw(role_id=ali["active_soul_role"])
        except Exception:  # noqa: BLE001
            claw_sync = {}
    return {
        "ok": True,
        "active_role": ali["active_soul_role"],
        "roles": all_roles(),
        "role": role,
        "claw_sync": claw_sync,
        "runtime": soul_runtime_status(),
    }


def upsert_role(body: dict[str, Any]) -> dict[str, Any]:
    roles = _load_custom_roles()
    rid = str(body.get("id") or "").strip()
    if not rid:
        label = str(body.get("label") or "custom").strip()
        rid = re.sub(r"[^a-z0-9_-]+", "-", label.lower()).strip("-") or f"role-{uuid.uuid4().hex[:8]}"
    builtin_ids = {r["id"] for r in BUILTIN_ROLES}
    removed = _removed_builtin_ids()
    # Soft-deleted builtin: posting the same id restores it to the catalog
    if rid in builtin_ids and rid in removed:
        store = _load_roles_store()
        new_removed = [x for x in (store.get("removed") or []) if str(x).strip() != rid]
        _save_roles_store(list(store.get("roles") or []), new_removed)
        role_out = next((dict(b) for b in BUILTIN_ROLES if b["id"] == rid), {"id": rid})
        cfg = load_campus_config()
        ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
        if bool(body.get("activate")) or (ali or {}).get("active_soul_role") == rid:
            set_active_role(rid, apply_to_soul_file=True)
        return {"ok": True, "role": role_out, "core_roles": all_roles(), "restored": True}
    if rid in builtin_ids:
        raise ValueError("cannot overwrite builtin role id — pick another id")
    item = {
        "id": rid,
        "label": str(body.get("label") or rid).strip(),
        "label_en": str(body.get("label_en") or body.get("label") or rid).strip(),
        "skills": [str(s).strip() for s in (body.get("skills") or []) if str(s).strip()],
        "desc": str(body.get("desc") or "").strip(),
        "soul_snippet": str(body.get("soul_snippet") or body.get("content") or "").strip(),
        "content": str(body.get("content") or body.get("soul_snippet") or "").strip(),
        "builtin": False,
    }
    found = False
    for i, r in enumerate(roles):
        if r["id"] == rid:
            roles[i] = item
            found = True
            break
    if not found:
        roles.append(item)
    _save_custom_roles(roles)
    # If this role is active (or activate=true), sync into SOUL.md immediately
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    activate = bool(body.get("activate")) or (ali or {}).get("active_soul_role") == rid
    if activate:
        set_active_role(rid, apply_to_soul_file=True)
    return {"ok": True, "role": item, "core_roles": all_roles()}


def delete_role(role_id: str) -> dict[str, Any]:
    role_id = (role_id or "").strip()
    current = all_roles()
    if not any(r.get("id") == role_id for r in current):
        raise ValueError(f"unknown role: {role_id}")
    if len(current) <= 1:
        raise ValueError("cannot delete the last core role")
    store = _load_roles_store()
    builtin_ids = {r["id"] for r in BUILTIN_ROLES}
    custom = [r for r in (store.get("roles") or []) if isinstance(r, dict) and r.get("id") != role_id]
    removed = [str(x).strip() for x in (store.get("removed") or []) if str(x).strip()]
    if role_id in builtin_ids:
        if role_id not in removed:
            removed.append(role_id)
    _save_roles_store(custom, removed)
    remaining = all_roles()
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    active = (ali or {}).get("active_soul_role")
    switched = None
    if active == role_id:
        switched = remaining[0]["id"] if remaining else "office"
        set_active_role(switched)
    return {
        "ok": True,
        "deleted": role_id,
        "active_role": switched or active,
        "core_roles": remaining,
    }


def generate_soul_draft(brief: str, *, role_label: str = "") -> dict[str, Any]:
    """Generate a SOUL.md draft from a short brief (template or LLM if available)."""
    brief = (brief or "").strip()
    role = (role_label or "Campus Assistant").strip() or "Campus Assistant"
    if not brief:
        raise ValueError("brief required")
    try:
        from . import llm_client
        from .secrets import resolve_api_key
        from .settings import load_campus_config

        cfg = load_campus_config()
        key_info = resolve_api_key(cfg)
        backend = cfg.get("backend") or {}
        base_url = str(backend.get("base_url") or "").strip()
        model = str(((cfg.get("models") or {}).get("main") or (cfg.get("models") or {}).get("fast") or "")).strip()
        api_key = key_info.get("key") or ""
        if base_url and model and api_key:
            prompt = (
                "Write a concise SOUL.md identity document in Markdown for Agent Hub.\n"
                f"Role label: {role}\n"
                f"User brief:\n{brief}\n\n"
                f"Start with '# SOUL.md — Agent Hub · {role}'. "
                "State clearly: You are Agent Hub (not Hermes CLI). "
                "Include principles, tools preference, and language."
            )
            text = llm_client.stream_chat(
                base_url,
                api_key,
                model=model,
                messages=[
                    {"role": "system", "content": "You write agent identity documents."},
                    {"role": "user", "content": prompt},
                ],
                timeout=60,
                verify_tls=bool(backend.get("verify_tls", True)),
            )
            if text.strip():
                return {"ok": True, "content": text.strip(), "source": "llm"}
    except Exception:  # noqa: BLE001
        pass
    content = (
        f"# SOUL.md — Agent Hub · {role}\n\n"
        f"You are **Agent Hub** acting as **{role}**, a campus AI workflow assistant.\n\n"
        f"## Brief\n{brief}\n\n"
        "## Principles\n"
        "- Match the user's language (Chinese → 简体中文) unless they request another language\n"
        "- Concise, actionable replies\n"
        "- Prefer skills/tools; ask before irreversible actions\n"
        "- Never echo secrets\n"
        "- Multi-step workflows over chit-chat\n"
        "- On failure, auto-search/install GitHub skills and retry\n"
    )
    return {"ok": True, "content": content, "source": "template"}


# Marker block injected into claw SOUL.md so Hub role is visible to the claw runtime.
_HUB_SOUL_BEGIN = "# --- Agent Hub Soul (managed) ---"
_HUB_SOUL_END = "# --- end Agent Hub Soul ---"


def _active_runtime_ids() -> dict[str, str]:
    """Resolve connected claw from Control Center (fast peek — no version probes)."""
    try:
        from . import runtimes

        data = runtimes.peek_runtime()
        return {
            "active": str(data.get("active") or "auto"),
            "auto_runtime": str(data.get("auto_runtime") or "hermes"),
            "resolved": str(data.get("resolved") or "direct"),
            "linked": str(data.get("linked") or data.get("resolved") or "direct"),
        }
    except Exception:  # noqa: BLE001
        return {"active": "auto", "auto_runtime": "hermes", "resolved": "direct", "linked": "direct"}


def claw_soul_candidate_paths(runtime_id: str) -> list[Path]:
    """Candidate SOUL.md / AGENTS.md locations — native claw homes only."""
    from .config import hermes_home

    rid = (runtime_id or "").strip()
    if not rid or rid in ("auto", "direct"):
        return []
    home = Path.home()
    cands: list[Path] = []
    if rid == "hermes":
        cands.extend(
            [
                hermes_home() / "SOUL.md",
                hermes_home() / "hermes-home" / "SOUL.md",
            ]
        )
    elif rid in ("openclaw", "qqclaw", "aliyun_claw"):
        cands.extend(
            [
                home / ".openclaw" / "workspace" / "SOUL.md",
                home / ".openclaw" / "SOUL.md",
                home / ".openclaw" / "workspace" / "AGENTS.md",
            ]
        )
    elif rid == "nanobot":
        cands.extend(
            [
                home / ".nanobot" / "SOUL.md",
                home / ".nanobot" / "AGENTS.md",
            ]
        )
    elif rid in ("nano_claw", "nanoclaw"):
        cands.extend(
            [
                home / ".nano-claw" / "SOUL.md",
                home / ".nanoclaw" / "SOUL.md",
                home / "nanoclaw" / "SOUL.md",
            ]
        )
    else:
        cands.extend(
            [
                home / f".{rid}" / "SOUL.md",
                home / f".{rid}" / "workspace" / "SOUL.md",
            ]
        )
    # de-dupe while preserving order
    seen: set[str] = set()
    out: list[Path] = []
    for p in cands:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def read_claw_soul(runtime_id: str | None = None) -> dict[str, Any]:
    """Load the connected claw's native soul file if present."""
    rt = _active_runtime_ids()
    rid = (runtime_id or rt.get("resolved") or rt.get("linked") or "").strip()
    if not rid or rid in ("auto", "direct"):
        return {
            "ok": True,
            "runtime": rid or "direct",
            "exists": False,
            "path": "",
            "content": "",
            "source": "none",
        }
    for path in claw_soul_candidate_paths(rid):
        if not path.is_file():
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Strip prior Hub managed block so we can re-fuse cleanly
        content = _strip_hub_managed_block(raw).strip()
        return {
            "ok": True,
            "runtime": rid,
            "exists": True,
            "path": str(path),
            "content": content,
            "raw": raw,
            "source": path.name,
        }
    return {
        "ok": True,
        "runtime": rid,
        "exists": False,
        "path": "",
        "content": "",
        "source": "none",
    }


def _strip_hub_managed_block(text: str) -> str:
    if _HUB_SOUL_BEGIN not in (text or ""):
        return text or ""
    pattern = re.compile(
        re.escape(_HUB_SOUL_BEGIN) + r"[\s\S]*?" + re.escape(_HUB_SOUL_END) + r"\n?",
        re.M,
    )
    return pattern.sub("", text or "").strip()


def hub_soul_managed_block(*, role_id: str | None = None) -> str:
    """Markdown block written into claw SOUL.md so the claw receives Hub soul."""
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    rid = (role_id or ali.get("active_soul_role") or "office").strip()
    role = get_role(rid) or {}
    hub = get_soul()
    hub_body = (hub.get("content") or "").strip()
    snippet = (role.get("content") or role.get("soul_snippet") or "").strip()
    label = role.get("label") or rid
    parts = [
        _HUB_SOUL_BEGIN,
        f"# Agent Hub · soul role `{rid}` ({label})",
        "",
        "You are running **through Agent Hub**. Honor Hub role directives below **and** your claw identity.",
        "When Hub and claw guidance conflict on campus workflows, prefer Hub role for tool/workflow choice;",
        "keep claw personality, tone, and safety boundaries.",
        "",
    ]
    if snippet:
        parts.extend([f"## Hub role directives ({label})", snippet, ""])
    if hub_body and hub_body != snippet:
        parts.extend(["## Hub SOUL.md", hub_body[:6000], ""])
    parts.append(_HUB_SOUL_END)
    return "\n".join(parts).rstrip() + "\n"


def compose_fused_soul_file(*, role_id: str | None = None, runtime_id: str | None = None) -> str:
    """Fused SOUL.md text for writing into the active claw home."""
    claw = read_claw_soul(runtime_id)
    hub_block = hub_soul_managed_block(role_id=role_id)
    native = (claw.get("content") or "").strip()
    if native:
        return hub_block + "\n" + native + ("\n" if not native.endswith("\n") else "")
    # No native claw soul — still write Hub block as the claw SOUL.md
    rid = claw.get("runtime") or runtime_id or "claw"
    return (
        hub_block
        + f"\n# SOUL.md — {rid}\n\n"
        + "Claw identity follows Agent Hub until a native claw SOUL.md is created.\n"
    )


def sync_soul_to_claw(
    runtime_id: str | None = None,
    *,
    role_id: str | None = None,
) -> dict[str, Any]:
    """Push fused Hub+Claw soul into the connected claw's SOUL.md (immediate)."""
    rt = _active_runtime_ids()
    rid = (runtime_id or rt.get("resolved") or rt.get("linked") or "").strip()
    if not rid or rid in ("auto", "direct"):
        return {"ok": True, "synced": False, "runtime": rid or "direct", "written": [], "reason": "no claw"}
    fused = compose_fused_soul_file(role_id=role_id, runtime_id=rid)
    written: list[str] = []
    # Prefer primary write targets (first existing parent or creatable workspace)
    targets = _claw_soul_write_targets(rid)
    for path in targets:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(fused if fused.endswith("\n") else fused + "\n", encoding="utf-8")
            written.append(str(path))
        except OSError:
            continue
    return {
        "ok": True,
        "synced": bool(written),
        "runtime": rid,
        "written": written,
        "role": (role_id or "").strip() or None,
        "bytes": len(fused.encode("utf-8")),
    }


def _claw_soul_write_targets(runtime_id: str) -> list[Path]:
    """Primary SOUL.md paths — native claw homes only."""
    from .config import hermes_home

    rid = (runtime_id or "").strip()
    home = Path.home()
    if rid == "hermes":
        return [hermes_home() / "SOUL.md"]
    if rid in ("openclaw", "qqclaw", "aliyun_claw"):
        return [home / ".openclaw" / "workspace" / "SOUL.md"]
    if rid == "nanobot":
        return [home / ".nanobot" / "SOUL.md"]
    if rid in ("nano_claw", "nanoclaw"):
        return [home / ".nano-claw" / "SOUL.md", home / ".nanoclaw" / "SOUL.md"]
    return [home / f".{rid}" / "SOUL.md"]


def soul_context_for_prompt(
    *,
    role_id: str | None = None,
    subagent_soul: str | None = None,
    runtime_id: str | None = None,
) -> str:
    """Build system-prompt block: Hub soul fused with connected Claw soul."""
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    rid = (role_id or subagent_soul or ali.get("active_soul_role") or "office").strip()
    role = get_role(rid) or {}
    rt = _active_runtime_ids()
    claw_id = (runtime_id or rt.get("resolved") or rt.get("linked") or "direct").strip()
    claw = read_claw_soul(claw_id)

    lines = [
        "## Agent Hub identity (fused with Claw)",
        "You are **Agent Hub**, the campus multi-agent workflow orchestrator.",
        f"Active Hub soul role: `{rid}` ({role.get('label') or rid}).",
        f"Connected / resolved Claw runtime: `{claw_id}`.",
        "You must execute according to **both** the Hub soul role and the Claw soul below.",
        "Do not ignore Claw personality, boundaries, or continuity notes when a Claw is connected.",
    ]
    data = get_soul()
    content = (data.get("content") or "").strip()
    snippet = (role.get("content") or role.get("soul_snippet") or "").strip()
    if snippet:
        lines.append("### Hub soul directives")
        lines.append(snippet[:4000])
    if content and content != snippet:
        lines.append("### Hub SOUL.md")
        lines.append(content[:5000])
    if claw.get("exists") and (claw.get("content") or "").strip():
        lines.append(f"### Claw soul (`{claw_id}` from `{claw.get('path') or claw.get('source')}`)")
        lines.append((claw.get("content") or "")[:6000])
        lines.append(
            "### Fusion rule\n"
            "Apply Hub role for campus workflows/tools; keep Claw tone, safety, and identity. "
            "If the user switched Soul or Claw, treat the blocks above as authoritative for this turn."
        )
    elif claw_id not in ("", "direct", "auto"):
        lines.append(f"### Claw `{claw_id}`")
        lines.append(
            "Claw is connected but no native SOUL.md was found yet; Hub soul applies and was synced into the claw home."
        )
    if subagent_soul and subagent_soul != rid:
        sub = get_role(subagent_soul) or {}
        lines.append(f"### Subagent soul `{subagent_soul}`")
        lines.append((sub.get("content") or sub.get("soul_snippet") or sub.get("desc") or "")[:2000])
    return "\n".join(lines)


def soul_runtime_status() -> dict[str, Any]:
    """Light status for UI / chat: connected claw + fused soul readiness."""
    rt = _active_runtime_ids()
    claw = read_claw_soul(rt.get("resolved"))
    path = soul_path()
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    return {
        "ok": True,
        "active_role": (ali.get("active_soul_role") or "office"),
        "hub_soul_exists": path.is_file(),
        "runtime_active": rt.get("active"),
        "runtime_auto": rt.get("auto_runtime"),
        "runtime_resolved": rt.get("resolved"),
        "runtime_linked": rt.get("linked"),
        "claw_soul_exists": bool(claw.get("exists")),
        "claw_soul_path": claw.get("path") or "",
        "fused": path.is_file() or bool(claw.get("exists")),
    }

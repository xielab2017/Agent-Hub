"""Hermes skills discovery, install, catalog, and auto-suggest."""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

from .config import REPO_ROOT, STATE_DIR, ensure_state_dirs, hermes_home
from .home import skill_dir as agent_cli_skills

# Legacy path (still scanned); new installs go to ~/.agent-cli/skills
ALI_SKILLS = STATE_DIR / "skills"

# Top-level categories → subcategories for Control Center + composer picker
SKILL_TAXONOMY: list[dict[str, Any]] = [
    {
        "id": "office",
        "label": "办公",
        "label_en": "Office",
        "subs": [
            {"id": "meeting", "label": "会议纪要", "label_en": "Meetings", "keywords": ["会议", "纪要", "meeting", "minutes"]},
            {"id": "email", "label": "邮件公文", "label_en": "Email", "keywords": ["邮件", "email", "通知", "公文", "notice"]},
            {"id": "schedule", "label": "日程安排", "label_en": "Schedule", "keywords": ["日程", "排期", "schedule", "calendar"]},
        ],
    },
    {
        "id": "research",
        "label": "科研",
        "label_en": "Research",
        "subs": [
            {"id": "literature", "label": "文献综述", "label_en": "Literature", "keywords": ["文献", "论文", "综述", "paper", "review"]},
            {"id": "experiment", "label": "实验记录", "label_en": "Experiments", "keywords": ["实验", "数据", "experiment", "lab"]},
            {"id": "writing", "label": "科研写作", "label_en": "Writing", "keywords": ["写作", "稿件", "manuscript", "撰写"]},
        ],
    },
    {
        "id": "ops",
        "label": "运维部署",
        "label_en": "Ops",
        "subs": [
            {"id": "deploy", "label": "部署验收", "label_en": "Deploy", "keywords": ["部署", "安装", "验收", "deploy", "install"]},
            {"id": "workspace", "label": "工作区", "label_en": "Workspace", "keywords": ["工作区", "目录", "workspace", "path"]},
        ],
    },
    {
        "id": "science",
        "label": "科学计算",
        "label_en": "Science",
        "subs": [
            {"id": "bio", "label": "生信/生物", "label_en": "Bio", "keywords": ["生信", "基因", "蛋白", "biology", "genome"]},
            {"id": "chem", "label": "化学", "label_en": "Chem", "keywords": ["化学", "分子", "chemistry"]},
            {"id": "viz", "label": "科研可视化", "label_en": "Viz", "keywords": ["绘图", "图表", "火山图", "plot", "figure"]},
        ],
    },
    {
        "id": "automation",
        "label": "自动化",
        "label_en": "Automation",
        "subs": [
            {"id": "agent", "label": "Agent 流程", "label_en": "Agent flows", "keywords": ["agent", "自动化", "workflow", "多步骤"]},
            {"id": "code", "label": "代码助手", "label_en": "Code", "keywords": ["代码", "重构", "bug", "code", "debug"]},
        ],
    },
]


def install_skills_root() -> Path:
    """Canonical install target for Control Center uploads."""
    root = agent_cli_skills()
    root.mkdir(parents=True, exist_ok=True)
    return root


CORE_SKILL_HINTS = [
    {"id": "deploy-campus-office-ai", "label": "校园办公部署", "role": "ops", "category": "ops", "sub": "deploy"},
    {"id": "meeting-minutes", "label": "会议纪要", "role": "office", "category": "office", "sub": "meeting"},
    {"id": "email-draft", "label": "邮件起草", "role": "office", "category": "office", "sub": "email"},
    {"id": "research-review", "label": "科研审阅", "role": "research", "category": "research", "sub": "literature"},
]


def skill_dirs() -> list[Path]:
    home = hermes_home()
    candidates = [
        agent_cli_skills(),
        REPO_ROOT / ".agents" / "skills",
        ALI_SKILLS,
        home / "skills",
        home / "hermes-data" / "skills",
        home / "hermes-agent" / "skills",
    ]
    # Activated ecosystem packs (OpenScience / scientific-agent-skills) contribute skills
    try:
        from .ecosystem import ecosystem_dir, _activation_map

        activated = _activation_map()
        for eco_id in ("openscience", "scientific-agent-skills"):
            if not (activated.get(eco_id) or {}).get("active"):
                continue
            root = ecosystem_dir(eco_id)
            for cand in (root / "skills", root):
                if cand.is_dir() and cand not in candidates:
                    candidates.append(cand)
    except Exception:  # noqa: BLE001
        pass
    return [p for p in candidates if p.exists()]


def _parse_skill_md(path: Path) -> dict[str, Any]:
    meta: dict[str, Any] = {"name": path.parent.name, "description": "", "path": str(path.parent)}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return meta
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            block = text[3:end]
            for line in block.splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip().strip("\"'")
            rest = text[end + 4 :].strip()
            if rest and not meta.get("description"):
                meta["description"] = rest.splitlines()[0][:200]
            return meta
    for line in text.splitlines():
        if line.startswith("# "):
            meta["name"] = line[2:].strip() or meta["name"]
            break
    meta["description"] = next(
        (ln.strip() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")),
        "",
    )[:200]
    return meta


def classify_skill(meta: dict[str, Any]) -> tuple[str, str]:
    """Return (category_id, sub_id) for a skill."""
    blob = " ".join(
        str(meta.get(k) or "")
        for k in ("id", "name", "description", "role", "category", "tags")
    ).lower()
    for cat in SKILL_TAXONOMY:
        for sub in cat["subs"]:
            if any(kw.lower() in blob for kw in sub.get("keywords") or []):
                return cat["id"], sub["id"]
    # role / known id fallbacks
    role = str(meta.get("role") or "").lower()
    role_sub = {"office": "meeting", "ops": "deploy", "research": "literature"}
    if role in role_sub:
        return ("ops" if role == "ops" else role), role_sub[role]
    if "deploy" in blob or "campus" in blob:
        return "ops", "deploy"
    if "meeting" in blob or "纪要" in blob:
        return "office", "meeting"
    return "automation", "agent"


def list_skills() -> dict[str, Any]:
    ensure_state_dirs()
    ALI_SKILLS.mkdir(parents=True, exist_ok=True)
    # Prefer Agent Hub install root, then others. Dedupe by skill id.
    preferred = str(install_skills_root().resolve())
    project_skills = str((REPO_ROOT / ".agents" / "skills").resolve())
    by_id: dict[str, dict[str, Any]] = {}
    for root in skill_dirs() or [ALI_SKILLS]:
        try:
            root_res = str(root.resolve())
        except OSError:
            root_res = str(root)
        for skill_md in root.rglob("SKILL.md"):
            parent = skill_md.parent.resolve()
            sid = parent.name
            meta = _parse_skill_md(skill_md)
            meta["id"] = sid
            meta["path"] = str(parent)
            meta["source_root"] = root_res
            # Project-owned Trellis skills are versioned source files, not
            # removable user installs exposed by the Control Center.
            meta["managed"] = root_res != project_skills
            cat, sub = classify_skill(meta)
            meta["category"] = cat
            meta["sub"] = sub
            existing = by_id.get(sid)
            if not existing:
                by_id[sid] = meta
                continue
            # Prefer ~/.agent-cli/skills, then shallower path
            ex_root = str(existing.get("source_root") or "")
            score_new = (0 if root_res.startswith(preferred) else 1, len(str(parent).split("/")))
            score_old = (0 if ex_root.startswith(preferred) else 1, len(str(existing.get("path") or "").split("/")))
            if score_new < score_old:
                by_id[sid] = meta
    found = list(by_id.values())
    found.sort(key=lambda s: (s.get("category") or "", s.get("sub") or "", s.get("name") or s.get("id") or ""))
    root = install_skills_root()
    return {
        "ok": True,
        "skills": found,
        "count": len(found),
        "dirs": [str(p) for p in skill_dirs()],
        "ali_skills_dir": str(root),
        "legacy_skills_dir": str(ALI_SKILLS),
        "core_hints": CORE_SKILL_HINTS,
        "taxonomy": SKILL_TAXONOMY,
    }


def skill_catalog() -> dict[str, Any]:
    """Grouped catalog for composer picker + Control Center."""
    data = list_skills()
    by_cat: dict[str, dict[str, list]] = {}
    for s in data["skills"]:
        cat = s.get("category") or "automation"
        sub = s.get("sub") or "agent"
        by_cat.setdefault(cat, {}).setdefault(sub, []).append(s)
    tree = []
    for cat in SKILL_TAXONOMY:
        subs_out = []
        for sub in cat["subs"]:
            items = by_cat.get(cat["id"], {}).get(sub["id"], [])
            # also surface core hints as virtual skills if missing
            for hint in CORE_SKILL_HINTS:
                if hint.get("category") == cat["id"] and hint.get("sub") == sub["id"]:
                    if not any(i.get("id") == hint["id"] for i in items):
                        items.append({**hint, "virtual": True, "description": hint.get("label")})
            subs_out.append({**sub, "skills": items, "count": len(items)})
        tree.append({**cat, "subs": subs_out})
    return {"ok": True, "taxonomy": tree, "count": data["count"], "ali_skills_dir": data["ali_skills_dir"], "hub_loaded_skills": get_hub_loaded()}


def get_hub_loaded() -> list[str]:
    """Skills loaded into the Hub system (not the chat work window)."""
    from .settings import load_campus_config

    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    raw = ali.get("hub_loaded_skills") if isinstance(ali, dict) else None
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen = set()
    for x in raw:
        sid = str(x or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sid)
    return out


def set_hub_loaded(skill_ids: list[str]) -> dict[str, Any]:
    from .settings import load_campus_config, save_campus_config

    cleaned: list[str] = []
    seen = set()
    for x in skill_ids or []:
        sid = str(x or "").strip()
        if not sid or sid in seen:
            continue
        seen.add(sid)
        cleaned.append(sid)
    cfg = load_campus_config()
    ali = cfg.setdefault("ali", {})
    if not isinstance(ali, dict):
        ali = {}
        cfg["ali"] = ali
    ali["hub_loaded_skills"] = cleaned
    save_campus_config(cfg)
    return {"ok": True, "hub_loaded_skills": cleaned}


def load_skill_to_hub(skill_id: str) -> dict[str, Any]:
    sid = str(skill_id or "").strip()
    if not sid:
        raise ValueError("empty skill id")
    ids = get_hub_loaded()
    if sid not in ids:
        ids.append(sid)
    return set_hub_loaded(ids)


def unload_skill_from_hub(skill_id: str) -> dict[str, Any]:
    sid = str(skill_id or "").strip()
    ids = [x for x in get_hub_loaded() if x != sid]
    return set_hub_loaded(ids)


# Explicit skill-intent cues — do NOT auto-match on every chat turn
_SKILL_INTENT_RE = re.compile(
    r"(?i)(?:"
    r"\bskills?\b|skill\.md|claude\s*skill|codex\s*skill|"
    r"技能|调用技能|使用技能|匹配技能|加载技能|安装技能|"
    r"用\s*skill|跑\s*skill|启用\s*skill"
    r")"
)


def message_implies_skills(message: str) -> bool:
    """True when the user explicitly asks for skills (not every office task)."""
    text = (message or "").strip()
    if not text:
        return False
    return bool(_SKILL_INTENT_RE.search(text))


def suggest_skills(message: str, *, limit: int = 4) -> dict[str, Any]:
    """Heuristic skill suggestions; prefer Hub-loaded skills when they match.

    Callers should gate with message_implies_skills() / explicit selection —
    this function itself only scores; it no longer injects hub-loaded skills
    for unrelated messages.
    """
    text = (message or "").strip().lower()
    catalog = skill_catalog()
    hub = set(get_hub_loaded())
    scored: list[tuple[int, dict[str, Any]]] = []
    for cat in catalog["taxonomy"]:
        for sub in cat["subs"]:
            hits = sum(1 for kw in (sub.get("keywords") or []) if kw.lower() in text)
            if not hits:
                continue
            for sk in sub.get("skills") or []:
                sid = sk.get("id")
                # Hub-loaded skills get a strong boost so auto-match prefers them
                boost = 10 if sid in hub else 0
                scored.append(
                    (hits + boost, {**sk, "category": cat["id"], "sub": sub["id"], "score": hits + boost, "hub_loaded": sid in hub})
                )
    scored.sort(key=lambda x: (-x[0], 0 if x[1].get("hub_loaded") else 1, x[1].get("id") or ""))
    # dedupe
    seen = set()
    out = []
    for _, sk in scored:
        sid = sk.get("id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(sk)
        if len(out) >= limit:
            break
    return {"ok": True, "skills": out, "query": message[:200], "hub_loaded_skills": list(hub)}


def skill_context_block(skill_ids: list[str]) -> str:
    """Build system preamble snippet for selected skills."""
    if not skill_ids:
        return ""
    data = list_skills()
    by_id = {s["id"]: s for s in data["skills"]}
    lines = ["## Active skills (follow these when relevant)"]
    for sid in skill_ids:
        sid = str(sid).strip()
        if not sid:
            continue
        sk = by_id.get(sid)
        if sk:
            lines.append(f"- **{sk.get('name') or sid}** (`{sid}`): {sk.get('description') or ''}")
            lines.append(f"  path: `{sk.get('path')}`")
        else:
            # virtual / hint
            hint = next((h for h in CORE_SKILL_HINTS if h["id"] == sid), None)
            if hint:
                lines.append(f"- **{hint['label']}** (`{sid}`)")
            else:
                lines.append(f"- `{sid}`")
    lines.append("Prefer multi-step workflow: clarify → gather context → apply skill → verify → deliver.")
    return "\n".join(lines)


def install_skill_dir(src: Path, *, name: str = "") -> dict[str, Any]:
    ensure_state_dirs()
    root = install_skills_root()
    src = src.expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(str(src))
    dest_name = name or src.name
    dest = root / dest_name
    if dest.exists():
        shutil.rmtree(dest)
    if not src.is_dir():
        raise ValueError("skill source must be a directory")
    shutil.copytree(src, dest)
    skill_md = dest / "SKILL.md"
    if not skill_md.is_file():
        skill_md.write_text(
            f"---\nname: {dest_name}\ndescription: Installed via Agent Hub\n---\n\n# {dest_name}\n",
            encoding="utf-8",
        )
    return {"ok": True, "id": dest_name, "path": str(dest)}


def install_skill_zip(zip_path: Path, *, name: str = "") -> dict[str, Any]:
    ensure_state_dirs()
    root = install_skills_root()
    zip_path = zip_path.expanduser().resolve()
    if not zip_path.is_file():
        raise FileNotFoundError(str(zip_path))
    tmp = root / f".tmp-{zip_path.stem}"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)
    except zipfile.BadZipFile as exc:
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"invalid zip: {exc}") from exc
    children = [c for c in tmp.iterdir() if not c.name.startswith(".")]
    if len(children) == 1 and children[0].is_dir():
        src = children[0]
        default_name = children[0].name
    else:
        src = tmp
        default_name = zip_path.stem
    result = install_skill_dir(src, name=name or default_name)
    shutil.rmtree(tmp, ignore_errors=True)
    return result


def uninstall_skill(skill_id: str) -> dict[str, Any]:
    """Delete all directories named skill_id that contain SKILL.md under known roots."""
    skill_id = (skill_id or "").strip()
    if not skill_id or "/" in skill_id or "\\" in skill_id or skill_id in (".", ".."):
        raise ValueError("invalid skill id")
    roots = []
    for base in (install_skills_root(), ALI_SKILLS, *skill_dirs()):
        try:
            roots.append(base.resolve())
        except OSError:
            continue
    seen_roots: set[str] = set()
    uniq: list[Path] = []
    for r in roots:
        key = str(r)
        if key in seen_roots:
            continue
        seen_roots.add(key)
        uniq.append(r)

    removed: list[str] = []
    for base in uniq:
        # top-level
        candidates = [base / skill_id]
        # nested (e.g. pack/skill_id/SKILL.md)
        try:
            for skill_md in base.rglob("SKILL.md"):
                if skill_md.parent.name == skill_id:
                    candidates.append(skill_md.parent)
        except OSError:
            continue
        for dest in candidates:
            try:
                if not dest.exists() or not dest.is_dir():
                    continue
                resolved = dest.resolve()
                if not str(resolved).startswith(str(base)):
                    continue
                # require SKILL.md for safety
                if not (dest / "SKILL.md").is_file() and dest.name != skill_id:
                    continue
                shutil.rmtree(dest)
                removed.append(str(dest))
            except OSError:
                continue
    if not removed:
        raise FileNotFoundError(skill_id)
    return {"ok": True, "id": skill_id, "removed": removed, "path": removed[0]}


def sync_skills_to_claw(runtime_id: str) -> dict[str, Any]:
    """Copy/symlink Hub catalog skills into the claw's native skills directory."""
    import os
    import shutil

    from .config import hermes_home
    from .home import native_claw_home

    rid = (runtime_id or "").strip()
    if not rid or rid in ("auto", "direct"):
        return {"ok": True, "synced": False, "reason": "no claw", "written": []}

    if rid == "hermes":
        dest_root = hermes_home() / "skills"
    elif rid in ("openclaw", "qqclaw", "aliyun_claw"):
        dest_root = Path.home() / ".openclaw" / "skills"
    elif rid == "nanobot":
        dest_root = Path.home() / ".nanobot" / "skills"
    else:
        native = native_claw_home(rid)
        dest_root = (native / "skills") if native else None
    if dest_root is None:
        return {"ok": False, "synced": False, "reason": "no native skills dir", "written": []}

    src_root = install_skills_root()
    written: list[str] = []
    try:
        dest_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return {"ok": False, "error": str(exc), "written": []}

    if not src_root.is_dir():
        return {"ok": True, "synced": False, "reason": "empty hub catalog", "written": [], "dest": str(dest_root)}

    for child in src_root.iterdir():
        if child.name.startswith(".") or not child.is_dir():
            continue
        if not (child / "SKILL.md").is_file():
            continue
        target = dest_root / child.name
        try:
            if target.exists() or target.is_symlink():
                continue
            try:
                os.symlink(child.resolve(), target, target_is_directory=True)
            except OSError:
                shutil.copytree(child, target)
            written.append(str(target))
        except OSError:
            continue
    return {
        "ok": True,
        "synced": bool(written),
        "runtime": rid,
        "dest": str(dest_root),
        "written": written,
        "count": len(written),
    }

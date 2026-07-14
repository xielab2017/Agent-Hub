"""Skills hub — curated GitHub science/office/automation skills + install into Agent-CLI home."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .home import ensure_home, os_profile, skill_dir

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()

# Curated mainstream skill / agent skill packs (install into ~/.agent-cli/skills/)
SKILL_PACKS: list[dict[str, Any]] = [
    {
        "id": "scientific-agent-skills",
        "category": "science",
        "label": "Scientific Agent Skills",
        "label_zh": "科学 Agent Skills（K-Dense）",
        "desc": "148 research/lab skills — Claude/Codex/Cursor/OpenClaw/Hermes compatible.",
        "desc_zh": "148 个科研/实验室 Skill，兼容 Claude·Codex·Cursor·OpenClaw·Hermes。",
        "repo": "K-Dense-AI/scientific-agent-skills",
        "git": "https://github.com/K-Dense-AI/scientific-agent-skills.git",
        "stars_hint": "30k+",
        "tags": ["science", "claude", "codex", "biology", "chemistry"],
    },
    {
        "id": "agent-research-skills",
        "category": "science",
        "label": "Agent Research Skills",
        "label_zh": "学术研究 Skills",
        "desc": "Literature search → paper writing → slides lifecycle skills.",
        "desc_zh": "文献检索 → 写作 → 幻灯片全流程学术 Skill。",
        "repo": "lingzhi227/agent-research-skills",
        "git": "https://github.com/lingzhi227/agent-research-skills.git",
        "tags": ["science", "literature", "writing"],
    },
    {
        "id": "deploy-campus-office-ai",
        "category": "work",
        "label": "Campus Office AI Deploy",
        "label_zh": "校园办公 AI 部署",
        "desc": "Hermes × OpenSquilla campus office deploy / acceptance skill.",
        "desc_zh": "Hermes×OpenSquilla 校园办公部署与验收 Skill。",
        "repo": "local/campus",
        "git": "",
        "local_hint": "~/Downloads/deploy-campus-office-ai",
        "tags": ["work", "ops", "campus"],
    },
    {
        "id": "anthropic-skills",
        "category": "automation",
        "label": "Anthropic Skills Examples",
        "label_zh": "Anthropic Skills 示例",
        "desc": "Official-style Agent Skills examples for Claude Code workflows.",
        "desc_zh": "Anthropic / Claude Code 风格 Agent Skills 示例。",
        "repo": "anthropics/skills",
        "git": "https://github.com/anthropics/skills.git",
        "tags": ["claude", "automation", "office"],
    },
    {
        "id": "openai-cookbook-agents",
        "category": "automation",
        "label": "OpenAI Cookbook Agents",
        "label_zh": "OpenAI Cookbook Agents",
        "desc": "Popular agent patterns from OpenAI Cookbook (reference clone).",
        "desc_zh": "OpenAI Cookbook 热门 Agent 模式（参考克隆）。",
        "repo": "openai/openai-cookbook",
        "git": "https://github.com/openai/openai-cookbook.git",
        "tags": ["codex", "openai", "automation"],
    },
]


def _installed_ids() -> set[str]:
    base = skill_dir()
    if not base.is_dir():
        return set()
    return {p.name for p in base.iterdir() if p.is_dir() and not p.name.startswith(".")}


def list_skill_packs() -> dict[str, Any]:
    ensure_home()
    installed = _installed_ids()
    packs = []
    for p in SKILL_PACKS:
        packs.append(
            {
                **p,
                "installed": p["id"] in installed,
                "path": str(skill_dir(p["id"])) if p["id"] in installed else "",
            }
        )
    return {
        "ok": True,
        "skills_home": str(skill_dir()),
        "packs": packs,
        "os": os_profile(),
        "categories": ["science", "work", "automation"],
    }


def start_install_pack(pack_id: str) -> dict[str, Any]:
    meta = next((p for p in SKILL_PACKS if p["id"] == pack_id), None)
    if not meta:
        raise ValueError(f"unknown skill pack: {pack_id}")
    ensure_home()
    dest = skill_dir(pack_id)
    return _start_git_or_local_install(pack_id, dest, meta)


def start_install_git(name: str, git_url: str) -> dict[str, Any]:
    """Clone an arbitrary GitHub skill repo into ~/.agent-cli/skills/<name>."""
    safe = re.sub(r"[^\w.\-]+", "_", (name or "github-skill").strip())[:80] or "github-skill"
    git_url = (git_url or "").strip()
    if not git_url.startswith("https://") and not git_url.startswith("git@"):
        raise ValueError("invalid git url")
    ensure_home()
    dest = skill_dir(safe)
    meta = {"id": safe, "git": git_url}
    return _start_git_or_local_install(safe, dest, meta)


def _start_git_or_local_install(pack_id: str, dest: Path, meta: dict[str, Any]) -> dict[str, Any]:
    job_id = str(uuid.uuid4())
    log_path = ensure_home()["logs"] / f"skill-{job_id}.log"
    job: dict[str, Any] = {
        "id": job_id,
        "pack_id": pack_id,
        "status": "running",
        "log_path": str(log_path),
        "dest": str(dest),
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
    }
    with _lock:
        _jobs[job_id] = job

    def _run() -> None:
        try:
            with log_path.open("w", encoding="utf-8") as log:
                if meta.get("git"):
                    if dest.exists():
                        shutil.rmtree(dest)
                    log.write(f"$ git clone {meta['git']} {dest}\n")
                    log.flush()
                    r = subprocess.run(
                        ["git", "clone", "--depth", "1", meta["git"], str(dest)],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=600,
                    )
                    if r.returncode != 0:
                        raise RuntimeError("git clone failed")
                else:
                    # local campus hint
                    hint = Path(meta.get("local_hint") or "").expanduser()
                    dest.mkdir(parents=True, exist_ok=True)
                    if hint.is_dir():
                        for child in hint.iterdir():
                            target = dest / child.name
                            if child.is_dir():
                                if target.exists():
                                    shutil.rmtree(target)
                                shutil.copytree(child, target)
                            else:
                                shutil.copy2(child, target)
                        log.write(f"# copied from {hint}\n")
                    else:
                        (dest / "SKILL.md").write_text(
                            f"---\nname: {pack_id}\ndescription: Placeholder — place skill files here\n---\n\n# {pack_id}\n",
                            encoding="utf-8",
                        )
                        log.write("# placeholder SKILL.md (local source not found)\n")
                job["status"] = "ok"
                job["finished_at"] = time.time()
                log.write("# done\n")
        except Exception as exc:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(exc)
            job["finished_at"] = time.time()

    threading.Thread(target=_run, daemon=True, name=f"skill-{pack_id}").start()
    return {"ok": True, "job": dict(job)}


def uninstall_pack(pack_id: str) -> dict[str, Any]:
    dest = skill_dir(pack_id)
    root = skill_dir().resolve()
    if not dest.exists() or not str(dest.resolve()).startswith(str(root)):
        raise FileNotFoundError(pack_id)
    shutil.rmtree(dest)
    return {"ok": True, "id": pack_id}


def job_status(job_id: str) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise FileNotFoundError(job_id)
    out = dict(job)
    try:
        out["log"] = Path(job["log_path"]).read_text(encoding="utf-8", errors="replace")[-8000:]
    except OSError:
        out["log"] = ""
    return {"ok": True, "job": out}


def curated_skill_fallback(limit: int = 8) -> list[dict[str, Any]]:
    """Local curated list when GitHub is slow/blocked."""
    return [
        {
            "source": "curated",
            "name": p["repo"],
            "desc": p.get("desc") or "",
            "stars": p.get("stars_hint"),
            "url": f"https://github.com/{p['repo']}" if "/" in p["repo"] else "",
            "git": p.get("git") or "",
            "pack_id": p["id"],
        }
        for p in SKILL_PACKS
        if p.get("git")
    ][:limit]


def fetch_github_trending_skills(limit: int = 8, *, timeout: float = 3.0) -> list[dict[str, Any]]:
    """Best-effort GitHub search; falls back to curated list. Short timeout so UI never hangs."""
    q = "agent+skills+OR+claude+skills+OR+codex+skills"
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={limit}"
    try:
        req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Agent-Hub"})
        with urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        out = []
        for it in data.get("items") or []:
            out.append(
                {
                    "source": "github",
                    "name": it.get("full_name"),
                    "desc": it.get("description") or "",
                    "stars": it.get("stargazers_count"),
                    "url": it.get("html_url"),
                    "git": it.get("clone_url"),
                }
            )
        if out:
            return out
    except Exception:  # noqa: BLE001
        pass
    return curated_skill_fallback(limit)

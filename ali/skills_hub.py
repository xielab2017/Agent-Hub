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
from urllib.request import ProxyHandler, Request, build_opener, urlopen

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


# 常驻 curated 兜底列表 — 包含仓内 SKILL_PACKS（即便无 git 字段也给本地 URL）
# + 一批 GitHub 上稳定热门的 Agent / Skills / 教学仓库作为网络不可用时的可读推荐。
# 该列表仅在 GitHub 实时请求失败时使用，避免推荐区空白。
_EXTRA_CURATED_REPOS: list[dict[str, Any]] = [
    {
        "repo": "openai/openai-cookbook",
        "desc": "OpenAI Cookbook — agent / tool use / RAG 实战模式集锦。",
        "stars_hint": "60k+",
        "pack_id": "openai-cookbook-agents",
    },
    {
        "repo": "anthropics/anthropic-cookbook",
        "desc": "Anthropic 官方 cookbook — Claude tool use / 长期 agent 教程。",
        "stars_hint": "20k+",
        "pack_id": "anthropic-cookbook",
    },
    {
        "repo": "anthropics/skills",
        "desc": "Anthropic Skills 示例 — 文档 / Excel / PDF 等官方风格 agent skills。",
        "stars_hint": "8k+",
        "pack_id": "anthropic-skills",
    },
    {
        "repo": "K-Dense-AI/scientific-agent-skills",
        "desc": "K-Dense 科研 agent skills（148 个，覆盖生物/化学/统计）。",
        "stars_hint": "30k+",
        "pack_id": "scientific-agent-skills",
    },
    {
        "repo": "lingzhi227/agent-research-skills",
        "desc": "学术研究 skills — 文献检索 → 写作 → 幻灯片全流程。",
        "stars_hint": "1k+",
        "pack_id": "agent-research-skills",
    },
    {
        "repo": "microsoft/autogen",
        "desc": "AutoGen — 多 agent 对话与编排框架。",
        "stars_hint": "30k+",
        "pack_id": "autogen",
    },
    {
        "repo": "crewAIInc/crewAI",
        "desc": "CrewAI — 角色化多 agent 协作框架。",
        "stars_hint": "20k+",
        "pack_id": "crewai",
    },
    {
        "repo": "langchain-ai/langgraph",
        "desc": "LangGraph — 状态化多 agent / 长流程编排。",
        "stars_hint": "10k+",
        "pack_id": "langgraph",
    },
    {
        "repo": "openai/swarm",
        "desc": "OpenAI Swarm — 轻量级 handoff-style 多 agent 示例。",
        "stars_hint": "12k+",
        "pack_id": "openai-swarm",
    },
    {
        "repo": "google/adk-python",
        "desc": "Google Agent Development Kit (Python) — 官方多 agent 框架。",
        "stars_hint": "8k+",
        "pack_id": "google-adk",
    },
]


def curated_skill_fallback(limit: int = 8) -> list[dict[str, Any]]:
    """Local curated list when GitHub is slow/blocked.

    Always returns up to ``limit`` items. Merges two sources:

    1. ``SKILL_PACKS`` that have a real git URL (these are directly installable).
    2. ``_EXTRA_CURATED_REPOS`` — a stable list of well-known agent-skill repos
       so the recommended list never collapses to a handful of entries.
    """

    def _to_row(p: dict[str, Any]) -> dict[str, Any]:
        repo = p.get("repo") or ""
        url = p.get("url") or ""
        # Only auto-build a GitHub URL for real org/repo pairs (so local-only
        # packs like ``local/campus`` don't render a dead github.com/local/campus
        # link). Treat entries with a ``git`` field as installable.
        if (
            not url
            and "/" in repo
            and not repo.startswith("local/")
            and "/" in repo
            and repo.split("/", 1)[0]
            and not repo.split("/", 1)[0].startswith("local")
        ):
            url = f"https://github.com/{repo}"
        return {
            "source": "curated",
            "name": repo or p.get("id") or "",
            "desc": p.get("desc") or p.get("desc_zh") or "",
            "stars": p.get("stars_hint"),
            "url": url,
            "git": p.get("git") or "",
            "pack_id": p.get("id") or p.get("pack_id") or "",
        }

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in SKILL_PACKS:
        row = _to_row(p)
        if not row["name"]:
            continue
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        rows.append(row)
    for p in _EXTRA_CURATED_REPOS:
        row = _to_row(p)
        if not row["name"] or row["name"] in seen:
            continue
        seen.add(row["name"])
        rows.append(row)
    return rows[:limit]


def _github_openers():
    """Prefer direct (no macOS system proxy); then configured/env proxy; then system default."""
    openers = [build_opener(ProxyHandler({}))]
    proxy = (
        __import__("os").environ.get("HTTPS_PROXY")
        or __import__("os").environ.get("HTTP_PROXY")
        or ""
    ).strip()
    if proxy:
        openers.append(build_opener(ProxyHandler({"http": proxy, "https": proxy})))
    openers.append(build_opener())  # may pick macOS system proxy
    return openers


def fetch_github_trending_skills(limit: int = 8, *, timeout: float = 10.0) -> list[dict[str, Any]]:
    """Best-effort GitHub search; falls back to curated list.

    Always tries a direct (ProxyHandler({})) path first — campus/macOS system proxies
    often break GitHub API TLS while curated fallback would otherwise always win.
    Optional ``GITHUB_TOKEN`` / ``GH_TOKEN`` raises rate limits.
    """
    import os

    q = "agent+skills+OR+claude+skills+OR+codex+skills"
    url = f"https://api.github.com/search/repositories?q={q}&sort=stars&order=desc&per_page={max(1, min(30, int(limit or 8)))}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Agent-Hub",
        "Accept-Encoding": "identity",
    }
    tok = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if tok:
        headers["Authorization"] = f"Bearer {tok}"
    req = Request(url, headers=headers)
    last_err = None
    for opener in _github_openers():
        try:
            with opener.open(req, timeout=max(3.0, float(timeout or 10.0))) as resp:
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
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            continue
    _ = last_err
    return curated_skill_fallback(limit)

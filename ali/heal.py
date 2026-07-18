"""Auto problem-solving: on task failure, search GitHub skills, install, retry."""

from __future__ import annotations

import re
import time
from typing import Any, Callable

from . import skills_hub
from .home import ensure_home


def looks_like_failure(text: str = "", *, error: str = "") -> bool:
    t = f"{text or ''}\n{error or ''}".lower()
    if error:
        return True
    if not (text or "").strip() or (text or "").strip() in ("(no response)",):
        return True
    keys = (
        "**error:**",
        "traceback",
        "failed to",
        "failure",
        "无法完成",
        "执行失败",
        "没有找到",
        "skill not found",
        "module not found",
        "command not found",
        "not installed",
        "缺少技能",
        "无法读取",
        "permission denied",
        "http 4",
        "http 5",
        "rate limit",
        "api key missing",
    )
    return any(k in t for k in keys)


def is_provider_api_error(error: str = "", text: str = "") -> bool:
    """True for LLM HTTP / auth failures — do NOT auto-install GitHub skills."""
    t = f"{error or ''}\n{text or ''}".lower()
    if not t.strip():
        return False
    if any(
        x in t
        for x in (
            "http 401",
            "http 403",
            "http 404",
            "http 429",
            "unauthorized",
            "page not found",
            "api key",
            "非流式重试失败",
            "base_url",
            "model empty",
            "does not match backend",
        )
    ):
        return True
    if re.search(r"http\s*5\d\d", t):
        return True
    return False


def _keywords(message: str, error: str = "") -> list[str]:
    blob = f"{message} {error}"
    words = re.findall(r"[A-Za-z][A-Za-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", blob)
    stop = {"the", "and", "for", "with", "this", "that", "please", "帮我", "一下", "这个", "那个", "如何", "怎么"}
    out: list[str] = []
    for w in words:
        wl = w.lower()
        if wl in stop:
            continue
        if wl not in out:
            out.append(wl)
        if len(out) >= 12:
            break
    return out


def match_curated_packs(message: str, error: str = "") -> list[dict[str, Any]]:
    keys = [k.lower() for k in _keywords(message, error)]
    blob = f"{message} {error}".lower()
    scored: list[tuple[int, dict[str, Any]]] = []
    for p in skills_hub.SKILL_PACKS:
        if not p.get("git") and not p.get("local_hint"):
            continue
        score = 0
        tags = [str(t).lower() for t in (p.get("tags") or [])]
        hay = " ".join(
            [
                p.get("id") or "",
                p.get("label") or "",
                p.get("label_zh") or "",
                p.get("desc") or "",
                p.get("desc_zh") or "",
                " ".join(tags),
                p.get("repo") or "",
            ]
        ).lower()
        for k in keys:
            if k in hay:
                score += 1
            if k in blob and k in tags:
                score += 2
        for t in tags:
            if t in blob:
                score += 3
        if score:
            scored.append((score, p))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored[:3]]


def search_github_skills(message: str, error: str = "", *, limit: int = 5) -> list[dict[str, Any]]:
    keys = _keywords(message, error)[:6]
    q = "+".join(keys) if keys else "agent+skills"
    q = f"{q}+skills+OR+claude+skill+OR+codex+skill"
    # reuse hub fetch with custom query via trending fallback + filter
    hits = skills_hub.fetch_github_trending_skills(limit=limit)
    # also try a tighter search
    try:
        from urllib.parse import quote
        from urllib.request import Request, urlopen
        import json

        url = (
            "https://api.github.com/search/repositories"
            f"?q={quote(q[:180])}&sort=stars&order=desc&per_page={limit}"
        )
        req = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "Agent-Hub"})
        with urlopen(req, timeout=12) as resp:
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
    return hits


def _wait_job(job_id: str, *, timeout: float = 180.0) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        try:
            last = skills_hub.job_status(job_id)
        except FileNotFoundError:
            time.sleep(0.5)
            continue
        st = (last.get("job") or {}).get("status")
        if st in ("ok", "failed"):
            return last
        time.sleep(1.2)
    return last or {"ok": False, "job": {"status": "timeout", "error": "install timeout"}}


def install_candidates(candidates: list[dict[str, Any]], *, max_install: int = 2) -> dict[str, Any]:
    """Install curated packs and/or git repos into ~/.agent-cli/skills."""
    ensure_home()
    installed: list[str] = []
    errors: list[str] = []
    jobs: list[dict[str, Any]] = []
    for cand in candidates[:max_install]:
        pack_id = cand.get("pack_id") or cand.get("id")
        git = cand.get("git") or ""
        try:
            if pack_id and any(p["id"] == pack_id for p in skills_hub.SKILL_PACKS):
                res = skills_hub.start_install_pack(str(pack_id))
                job = res.get("job") or {}
                jobs.append(job)
                waited = _wait_job(str(job.get("id") or ""))
                st = (waited.get("job") or {}).get("status")
                if st == "ok":
                    installed.append(str(pack_id))
                else:
                    errors.append((waited.get("job") or {}).get("error") or f"{pack_id} failed")
            elif git:
                name = str(cand.get("name") or pack_id or "github-skill").replace("/", "__")
                res = skills_hub.start_install_git(name, git)
                job = res.get("job") or {}
                jobs.append(job)
                waited = _wait_job(str(job.get("id") or ""))
                st = (waited.get("job") or {}).get("status")
                if st == "ok":
                    installed.append(name)
                else:
                    errors.append((waited.get("job") or {}).get("error") or f"{name} failed")
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))
    return {"ok": bool(installed), "installed": installed, "errors": errors, "jobs": jobs}


EmitProgress = Callable[[str, dict[str, Any]], None]


def auto_recover(
    message: str,
    *,
    error: str = "",
    emit: EmitProgress | None = None,
) -> dict[str, Any]:
    """Search + install skills to recover a failed task."""

    def _emit(label: str, extra: dict[str, Any] | None = None) -> None:
        if emit:
            emit(label, extra or {})

    _emit("heal-search", {"message": "searching GitHub skills"})
    curated = match_curated_packs(message, error)
    gh = search_github_skills(message, error, limit=5)
    # Prefer curated, then GitHub hits not already in curated repos
    curated_repos = {p.get("repo") for p in curated}
    candidates: list[dict[str, Any]] = [{**p, "pack_id": p["id"]} for p in curated]
    for g in gh:
        name = g.get("name") or ""
        if name in curated_repos:
            continue
        candidates.append(g)
    if not candidates:
        return {"ok": False, "reason": "no skill candidates", "installed": []}

    _emit("heal-install", {"candidates": [c.get("name") or c.get("id") or c.get("pack_id") for c in candidates[:3]]})
    result = install_candidates(candidates, max_install=2)
    result["candidates"] = candidates[:5]
    result["note_zh"] = (
        f"已自动检索并安装 Skill：{', '.join(result.get('installed') or []) or '无'}，准备重试任务。"
        if result.get("ok")
        else f"自动安装未成功：{'; '.join(result.get('errors') or ['unknown'])}"
    )
    _emit("heal-ready", {"installed": result.get("installed") or []})
    return result

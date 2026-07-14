"""Daily recommendations + night/morning digests. Agent-CLI is the scheduler master."""

from __future__ import annotations

import concurrent.futures
import json
import shutil
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any

from . import audit, feedback, skills_hub
from .home import ensure_home, os_profile
from .sessions import list_sessions
from .settings import load_campus_config

_sched_started = False
_sched_lock = threading.Lock()

# Hard ceiling so refresh never blocks the HTTP worker / UI for long
_GH_FETCH_TIMEOUT = 3.5

POPULAR_AGENT_MODELS = {
    "cn": [
        {"id": "qwen3-max", "provider": "dashscope", "role": "main", "label": "Qwen3 Max", "docs": "https://help.aliyun.com/zh/model-studio/"},
        {"id": "qwen3-coder-plus", "provider": "dashscope", "role": "code", "label": "Qwen3 Coder", "docs": "https://help.aliyun.com/zh/model-studio/"},
        {"id": "deepseek-chat", "provider": "deepseek", "role": "main", "label": "DeepSeek V3", "docs": "https://platform.deepseek.com/api-docs/"},
        {"id": "deepseek-reasoner", "provider": "deepseek", "role": "reasoning", "label": "DeepSeek R1", "docs": "https://platform.deepseek.com/api-docs/"},
        {"id": "kimi-k2", "provider": "moonshot", "role": "main", "label": "Kimi K2", "docs": "https://platform.moonshot.cn/docs"},
        {"id": "glm-4.5", "provider": "zhipu", "role": "main", "label": "GLM-4.5", "docs": "https://open.bigmodel.cn/"},
        {"id": "doubao-pro", "provider": "volcengine", "role": "main", "label": "Doubao Pro", "docs": "https://www.volcengine.com/docs/82379"},
        {"id": "minimax-m1", "provider": "minimax", "role": "main", "label": "MiniMax M1", "docs": "https://platform.minimaxi.com/"},
        {"id": "hunyuan-turbos", "provider": "tencent", "role": "main", "label": "Hunyuan", "docs": "https://cloud.tencent.com/document/product/1729"},
        {"id": "yi-lightning", "provider": "01ai", "role": "fast", "label": "Yi Lightning", "docs": "https://platform.lingyiwanwu.com/"},
    ],
    "global": [
        {"id": "claude-opus-4", "provider": "anthropic", "role": "reasoning", "label": "Claude Opus 4", "docs": "https://docs.anthropic.com/"},
        {"id": "claude-sonnet-4", "provider": "anthropic", "role": "main", "label": "Claude Sonnet 4", "docs": "https://docs.anthropic.com/"},
        {"id": "gpt-4.1", "provider": "openai", "role": "main", "label": "GPT-4.1", "docs": "https://platform.openai.com/docs"},
        {"id": "o3", "provider": "openai", "role": "reasoning", "label": "OpenAI o3", "docs": "https://platform.openai.com/docs"},
        {"id": "gemini-2.5-pro", "provider": "gemini", "role": "main", "label": "Gemini 2.5 Pro", "docs": "https://ai.google.dev/gemini-api/docs"},
        {"id": "gemini-2.5-flash", "provider": "gemini", "role": "fast", "label": "Gemini 2.5 Flash", "docs": "https://ai.google.dev/gemini-api/docs"},
        {"id": "grok-3", "provider": "xai", "role": "main", "label": "Grok 3", "docs": "https://docs.x.ai/"},
        {"id": "mistral-large", "provider": "mistral", "role": "main", "label": "Mistral Large", "docs": "https://docs.mistral.ai/"},
        {"id": "llama-4-maverick", "provider": "openrouter", "role": "main", "label": "Llama 4 Maverick", "docs": "https://openrouter.ai/models"},
        {"id": "command-r-plus", "provider": "cohere", "role": "main", "label": "Command R+", "docs": "https://docs.cohere.com/"},
    ],
}


def _load_recommend_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _fetch_github_hot(limit: int = 8) -> tuple[list[dict[str, Any]], str]:
    """Fetch GitHub trending with a hard wall-clock timeout; never raise."""
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(skills_hub.fetch_github_trending_skills, limit, timeout=3.0)
            items = fut.result(timeout=_GH_FETCH_TIMEOUT)
        if items and (items[0] or {}).get("source") == "github":
            return items, "live"
        return items or skills_hub.curated_skill_fallback(limit), "curated"
    except Exception:  # noqa: BLE001
        return skills_hub.curated_skill_fallback(limit), "timeout"


def daily_recommend(refresh: bool = False) -> dict[str, Any]:
    ensure_home()
    path = ensure_home()["recommend"] / f"{date.today().isoformat()}.json"
    cached = _load_recommend_cache(path)
    if cached and not refresh:
        cached.setdefault("ok", True)
        cached.setdefault("agent_models", POPULAR_AGENT_MODELS)
        cached.setdefault("trial_packs", [p["id"] for p in skills_hub.SKILL_PACKS[:4]])
        cached.setdefault(
            "note_zh",
            "推荐由 Agent Hub 主控生成。模型需手动「应用」到配置，不是自动安装运行时。",
        )
        cached.setdefault(
            "note_en",
            "Recommendations from Agent Hub. Models must be Applied into config — not auto-installed runtimes.",
        )
        return cached

    prev_gh = list((cached or {}).get("github_hot") or [])
    gh, gh_status = _fetch_github_hot(8)
    # Prefer previous live cache if this refresh only got curated/timeout
    if gh_status != "live" and prev_gh and (prev_gh[0] or {}).get("source") == "github":
        gh = prev_gh
        gh_status = "cache"

    payload = {
        "ok": True,
        "date": date.today().isoformat(),
        "generated_at": time.time(),
        "refreshed": bool(refresh),
        "os": os_profile(),
        "github_hot": gh,
        "github_status": gh_status,
        "agent_models": POPULAR_AGENT_MODELS,
        "trial_packs": [p["id"] for p in skills_hub.SKILL_PACKS[:4]],
        "note_zh": "推荐由 Agent Hub 主控生成。热门模型需点「应用」写入配置；一键安装 Skill 写入 ~/.agent-cli/skills。",
        "note_en": "Recommendations from Agent Hub. Apply popular models into config; skill installs go to ~/.agent-cli/skills.",
    }
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
    return payload


def _habit_snapshot() -> dict[str, Any]:
    sessions = list_sessions()[:30]
    fb = feedback.summary(40)
    cfg = load_campus_config()
    return {
        "session_count": len(sessions),
        "recent_titles": [s.get("title") for s in sessions[:8]],
        "feedback": {"up": fb.get("thumbs_up"), "down": fb.get("thumbs_down"), "count": fb.get("count")},
        "workspace": cfg.get("workspace") or "",
        "runtime": ((cfg.get("ali") or {}) if isinstance(cfg.get("ali"), dict) else {}).get("agent_runtime") or "auto",
        "backend": ((cfg.get("backend") or {}) if isinstance(cfg.get("backend"), dict) else {}).get("type"),
    }


def run_nightly() -> dict[str, Any]:
    """00:00 — review, backup, self-evolution notes."""
    ensure_home()
    today = date.today().isoformat()
    habits = _habit_snapshot()
    rec = daily_recommend(refresh=True)
    # backup state + sessions
    backup_root = ensure_home()["backups"] / today
    backup_root.mkdir(parents=True, exist_ok=True)
    from .config import STATE_DIR

    for name in ("sessions", "feedback", "campus-office-ai.json", "secrets.json"):
        src = STATE_DIR / name
        try:
            if src.is_dir():
                dst = backup_root / name
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            elif src.is_file():
                shutil.copy2(src, backup_root / name)
        except OSError:
            continue
    # also snapshot agent-cli skills list
    skills = skills_hub.list_skill_packs()
    evolve = {
        "date": today,
        "type": "nightly",
        "habits": habits,
        "recommendations": {
            "github_top": [x.get("name") for x in (rec.get("github_hot") or [])[:5]],
            "trial": rec.get("trial_packs"),
        },
        "installed_skills": [p["id"] for p in skills.get("packs") or [] if p.get("installed")],
        "self_evolution": [
            "Keep skills that received thumbs_up; demote packs unused for 7+ days.",
            "Prefer CN models during daytime office; route C3 to reasoning models at night review.",
            "Backup completed; restore from ~/.agent-cli/backups/<date> if needed.",
        ],
        "ts": time.time(),
    }
    try:
        from . import evolution as evo_mod

        tips = evo_mod.recent_tips(limit=5)
        evolve["self_evolution"] = list(tips) + list(evolve["self_evolution"])
        evolve["evolution_runs"] = (evo_mod.list_runs(limit=5).get("runs") or [])
    except Exception:  # noqa: BLE001
        pass
    out_path = ensure_home()["digests"] / f"{today}-nightly.json"
    out_path.write_text(json.dumps(evolve, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ensure_home()["digests"] / f"{today}-nightly.md"
    md.write_text(
        f"# Nightly digest {today}\n\n"
        f"- Sessions tracked: {habits['session_count']}\n"
        f"- Feedback ↑{habits['feedback']['up']} ↓{habits['feedback']['down']}\n"
        f"- Runtime: `{habits['runtime']}` backend=`{habits['backend']}`\n"
        f"- Backup: `{backup_root}`\n\n"
        "## Evolution\n"
        + "\n".join(f"- {x}" for x in evolve["self_evolution"])
        + "\n\n## Hot skills\n"
        + "\n".join(f"- {n}" for n in evolve["recommendations"]["github_top"])
        + "\n",
        encoding="utf-8",
    )
    audit.log_event("digest_nightly", {"date": today, "backup": str(backup_root)})
    try:
        from .schedule import push_notification

        push_notification(
            title="夜间复盘已完成",
            title_en="Nightly review completed",
            kind="review",
            status="ok",
            summary=f"会话 {habits.get('session_count', 0)} · 备份 {backup_root.name if hasattr(backup_root, 'name') else backup_root}",
            summary_en=f"Sessions {habits.get('session_count', 0)} · backup ready",
            task_id="builtin-nightly",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "path": str(out_path), "md": str(md), "backup": str(backup_root)}


def run_morning() -> dict[str, Any]:
    """07:00 — work summary, problem review, improvements, install tips."""
    ensure_home()
    today = date.today().isoformat()
    habits = _habit_snapshot()
    rec = daily_recommend(refresh=False)
    nightly = ensure_home()["digests"] / f"{today}-nightly.json"
    nightly_data = {}
    if nightly.is_file():
        try:
            nightly_data = json.loads(nightly.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            nightly_data = {}
    problems = []
    if (habits.get("feedback") or {}).get("down"):
        problems.append("昨日存在差评回复 — 检查 grounding / 工作区是否未设置。")
    if not habits.get("workspace"):
        problems.append("未设置工作区 — 建议今早选定项目目录以防幻觉。")
    improvements = [
        "用控制中心 Claws 确认运行时；聊天继续走 Direct LLM 通用模型。",
        "从今日推荐安装 1 个科学 Skill + 1 个办公 Skill 试用。",
        "OpenSquilla 已装则开启 recommended 路由以省 Token。",
    ]
    try:
        from . import evolution as evo_mod

        for tip in evo_mod.recent_tips(limit=3):
            if tip not in improvements:
                improvements.insert(0, tip)
    except Exception:  # noqa: BLE001
        pass
    installs = {
        "skills": rec.get("trial_packs") or [],
        "models_cn": [m["id"] for m in POPULAR_AGENT_MODELS["cn"][:4]],
        "models_global": [m["id"] for m in POPULAR_AGENT_MODELS["global"][:4]],
    }
    payload = {
        "date": today,
        "type": "morning",
        "summary": {
            "recent_titles": habits.get("recent_titles"),
            "runtime": habits.get("runtime"),
            "from_nightly": bool(nightly_data),
        },
        "problems": problems,
        "improvements": improvements,
        "install_recommend": installs,
        "ts": time.time(),
    }
    out_path = ensure_home()["digests"] / f"{today}-morning.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md = ensure_home()["digests"] / f"{today}-morning.md"
    md.write_text(
        f"# Morning briefing {today}\n\n"
        f"## 工作摘要\n- Runtime: `{habits.get('runtime')}`\n"
        + "\n".join(f"- {t}" for t in (habits.get("recent_titles") or [])[:6])
        + "\n\n## 问题复盘\n"
        + ("\n".join(f"- {p}" for p in problems) or "- 暂无阻断问题")
        + "\n\n## 改进方案\n"
        + "\n".join(f"- {i}" for i in improvements)
        + "\n\n## 推荐安装\n"
        + f"- Skills: {', '.join(installs['skills'])}\n"
        + f"- CN models: {', '.join(installs['models_cn'])}\n"
        + f"- Global models: {', '.join(installs['models_global'])}\n",
        encoding="utf-8",
    )
    audit.log_event("digest_morning", {"date": today})
    try:
        from .schedule import push_notification

        tip = (problems[0] if problems else "暂无阻断问题")[:160]
        push_notification(
            title="早间进化简报已就绪",
            title_en="Morning evolve brief ready",
            kind="evolve",
            status="ok",
            summary=tip,
            summary_en=tip,
            task_id="builtin-morning",
        )
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "path": str(out_path), "md": str(md), "briefing": payload}


def latest_digests() -> dict[str, Any]:
    ensure_home()
    dig = ensure_home()["digests"]
    files = sorted(dig.glob("*.md"), key=lambda p: -p.stat().st_mtime)[:10]
    items = []
    for f in files:
        items.append({"name": f.name, "path": str(f), "mtime": f.stat().st_mtime})
    return {"ok": True, "items": items, "home": str(dig)}


def start_scheduler() -> None:
    """Background loop: nightly + morning digests at configurable local hours."""
    global _sched_started
    with _sched_lock:
        if _sched_started:
            return
        _sched_started = True

    # Best-effort: curated ecosystem packs (OpenSquilla / OpenScience) on scheduler start
    try:
        from .ecosystem import ensure_auto_activated

        ensure_auto_activated()
    except Exception:  # noqa: BLE001
        pass

    state_file = ensure_home()["state"] / "scheduler.json"

    def _load() -> dict[str, str]:
        if state_file.is_file():
            try:
                return json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
        return {}

    def _save(st: dict[str, str]) -> None:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(st, indent=2), encoding="utf-8")

    def _hours() -> tuple[int, int]:
        try:
            from .schedule import _load as load_sched

            d = (load_sched().get("defaults") or {})
            return int(d.get("nightly_hour", 0)), int(d.get("morning_hour", 7))
        except Exception:  # noqa: BLE001
            return 0, 7

    def _loop() -> None:
        while True:
            try:
                now = datetime.now()
                st = _load()
                nh, mh = _hours()
                key_n = f"nightly:{now.date().isoformat()}"
                key_m = f"morning:{now.date().isoformat()}"
                if now.hour == nh and now.minute < 5 and st.get("nightly") != key_n:
                    run_nightly()
                    st["nightly"] = key_n
                    _save(st)
                if now.hour == mh and now.minute < 5 and st.get("morning") != key_m:
                    run_morning()
                    st["morning"] = key_m
                    _save(st)
            except Exception:  # noqa: BLE001
                pass
            time.sleep(60)

    threading.Thread(target=_loop, daemon=True, name="agent-cli-scheduler").start()
    try:
        from .schedule import start_custom_scheduler

        start_custom_scheduler()
    except Exception:  # noqa: BLE001
        pass

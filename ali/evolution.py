"""Claw / ecosystem self-evolution orchestrator.

Adopts the hermes-agent-self-evolution loop shape (Nous Research):
  select target → inspect baseline → critique → propose → constrain →
  (user confirm) apply with backup → verify → changelog.

Does NOT pull in DSPy/GEPA as a hard dependency. Uses Hub's configured LLM
(DeepSeek / OpenAI-compatible) for a safe guided review cycle. Full GEPA runs
remain available after installing the ecosystem pack ``hermes-self-evolution``.

Targets any claw under Hub via adapters (Hermes ``~/.hermes``, OpenClaw
``~/.openclaw``, ecosystem packages under ``~/.agent-cli/ecosystem/``).
"""

from __future__ import annotations

import json
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .home import ecosystem_dir, ensure_home, native_claw_home

_lock = threading.RLock()
_jobs: dict[str, dict[str, Any]] = {}

# Mirrors Nous constraints (skill ≤15KB, growth ≤20%, SKILL.md structure).
MAX_SKILL_CHARS = 15_000
MAX_GROWTH = 0.20
# Prefer fewer files for faster guided reviews
MAX_SCAN_FILES = 5
MAX_FILE_CHARS = 8_000

EVOLUTION_SKILL_PACK_ID = "hermes-self-evolution"
NOUS_REPO = "https://github.com/NousResearch/hermes-agent-self-evolution"


def _evo_root() -> Path:
    root = ensure_home()["root"] / "evolution"
    root.mkdir(parents=True, exist_ok=True)
    (root / "runs").mkdir(parents=True, exist_ok=True)
    (root / "backups").mkdir(parents=True, exist_ok=True)
    return root


def _runs_dir() -> Path:
    return _evo_root() / "runs"


def _backup_dir(run_id: str) -> Path:
    d = _evo_root() / "backups" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_run(run: dict[str, Any]) -> Path:
    path = _runs_dir() / f"{run['id']}.json"
    path.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_run(run_id: str) -> dict[str, Any]:
    path = _runs_dir() / f"{run_id}.json"
    if not path.is_file():
        raise FileNotFoundError(run_id)
    return json.loads(path.read_text(encoding="utf-8"))


def list_runs(*, limit: int = 30, target_id: str = "") -> dict[str, Any]:
    _evo_root()
    items: list[dict[str, Any]] = []
    for p in sorted(_runs_dir().glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if target_id and str(data.get("target_id") or "") != target_id:
            continue
        items.append(
            {
                "id": data.get("id"),
                "target_kind": data.get("target_kind"),
                "target_id": data.get("target_id"),
                "label": data.get("label"),
                "status": data.get("status"),
                "phase": data.get("phase"),
                "started_at": data.get("started_at"),
                "finished_at": data.get("finished_at"),
                "summary": data.get("summary") or "",
                "proposal_count": len(data.get("proposals") or []),
                "applied_count": len(data.get("applied") or []),
                "error": data.get("error"),
            }
        )
        if len(items) >= max(1, min(limit, 100)):
            break
    return {"ok": True, "runs": items, "home": str(_evo_root())}


def get_run(run_id: str) -> dict[str, Any]:
    run = _load_run(run_id)
    return {"ok": True, "run": run}


# ── Adapters ───────────────────────────────────────────────────────────────


def _find_skill_mds(root: Path, *, limit: int = 24) -> list[Path]:
    if not root or not root.is_dir():
        return []
    hits: list[Path] = []
    for name in ("SKILL.md", "skill.md", "AGENTS.md", "SOUL.md"):
        direct = root / name
        if direct.is_file():
            hits.append(direct)
    try:
        for p in root.rglob("SKILL.md"):
            if p not in hits:
                hits.append(p)
            if len(hits) >= limit:
                break
    except OSError:
        pass
    return hits[:limit]


def _claw_skills_dirs(runtime_id: str, home: Path) -> list[Path]:
    rid = (runtime_id or "").strip()
    candidates = [
        home / "skills",
        home / "hermes-agent" / "skills",
        home / ".agents" / "skills",
        home / "agent" / "skills",
    ]
    if rid == "hermes":
        candidates.insert(0, home / "hermes-agent" / "skills")
    if rid in ("openclaw", "qqclaw", "aliyun_claw"):
        candidates.extend([home / "skills", home / "workspace" / "skills"])
    out: list[Path] = []
    seen: set[Path] = set()
    for c in candidates:
        try:
            r = c.resolve()
        except OSError:
            continue
        if r in seen or not r.is_dir():
            continue
        seen.add(r)
        out.append(r)
    return out


def _claw_prompt_files(runtime_id: str, home: Path) -> list[Path]:
    rid = (runtime_id or "").strip()
    names = [
        "SOUL.md",
        "AGENTS.md",
        "IDENTITY.md",
        "SYSTEM.md",
        "prompts/system.md",
        "config/soul.md",
    ]
    if rid == "hermes":
        names.extend(["hermes-agent/SOUL.md", "hermes-agent/AGENTS.md"])
    hits: list[Path] = []
    for n in names:
        p = home / n
        if p.is_file() and p not in hits:
            hits.append(p)
    try:
        from . import soul

        for p in soul.claw_soul_candidate_paths(rid):
            if p.is_file() and p not in hits:
                hits.append(p)
    except Exception:  # noqa: BLE001
        pass
    return hits[:6]


def resolve_target(kind: str, target_id: str) -> dict[str, Any]:
    """Resolve a claw or ecosystem package into an evolution target."""
    kind = (kind or "claw").strip().lower()
    tid = (target_id or "").strip()
    if not tid:
        raise ValueError("target_id required")

    if kind in ("ecosystem", "eco", "kit"):
        from . import ecosystem as eco_mod

        meta = next((e for e in eco_mod.ECOSYSTEM if e["id"] == tid), None)
        home = ecosystem_dir(tid)
        if not home.is_dir() and not (meta and meta.get("scaffold")):
            # still allow soft-targets with empty tree
            home.mkdir(parents=True, exist_ok=True)
        skills_dirs = []
        for cand in (home / "skills", home):
            if cand.is_dir():
                skills_dirs.append(cand)
        files = _find_skill_mds(home, limit=20)
        label = (meta or {}).get("label_zh") or (meta or {}).get("label") or tid
        return {
            "kind": "ecosystem",
            "id": tid,
            "label": label,
            "home": str(home),
            "skills_dirs": [str(p) for p in skills_dirs],
            "prompt_files": [str(p) for p in files if p.name.upper() in ("SOUL.MD", "AGENTS.MD")],
            "skill_files": [str(p) for p in files if p.name.upper() == "SKILL.MD"],
            "adapter": "ecosystem",
            "nous_compatible": tid == EVOLUTION_SKILL_PACK_ID,
        }

    # claw / runtime
    if tid in ("direct", "auto"):
        raise ValueError("direct/auto runtime cannot be evolved — pick a concrete claw")
    native = native_claw_home(tid)
    if not native:
        raise ValueError(f"unknown claw: {tid}")
    home = native
    skills_dirs = _claw_skills_dirs(tid, home)
    skill_files: list[Path] = []
    for d in skills_dirs:
        skill_files.extend(_find_skill_mds(d, limit=12))
    # de-dupe preserve order
    seen: set[str] = set()
    uniq_skills: list[Path] = []
    for p in skill_files:
        k = str(p)
        if k in seen:
            continue
        seen.add(k)
        uniq_skills.append(p)
    prompts = _claw_prompt_files(tid, home)
    try:
        from . import runtimes

        meta = runtimes.get_runtime(tid) or {}
    except Exception:  # noqa: BLE001
        meta = {}
    label = meta.get("label_zh") or meta.get("label") or tid
    return {
        "kind": "claw",
        "id": tid,
        "label": label,
        "home": str(home),
        "skills_dirs": [str(p) for p in skills_dirs],
        "prompt_files": [str(p) for p in prompts],
        "skill_files": [str(p) for p in uniq_skills[:24]],
        "adapter": tid,
        "nous_compatible": tid == "hermes",
        "home_exists": home.is_dir(),
    }


def list_targets() -> dict[str, Any]:
    """Claws + ecosystem packs available for self-evolution."""
    claws: list[dict[str, Any]] = []
    try:
        from . import runtimes

        data = runtimes.list_runtimes()
        for r in data.get("runtimes") or []:
            rid = r.get("id")
            if not rid or rid in ("direct", "auto"):
                continue
            det = r.get("detect") or {}
            home = native_claw_home(rid)
            claws.append(
                {
                    "kind": "claw",
                    "id": rid,
                    "label": r.get("label_zh") or r.get("label") or rid,
                    "label_en": r.get("label") or rid,
                    "installed": bool(det.get("installed") or (home and home.is_dir())),
                    "linked": bool(r.get("linked")),
                    "home": str(home) if home else "",
                    "nous_compatible": rid == "hermes",
                }
            )
    except Exception:  # noqa: BLE001
        for rid in ("hermes", "openclaw", "nanobot"):
            home = native_claw_home(rid)
            claws.append(
                {
                    "kind": "claw",
                    "id": rid,
                    "label": rid,
                    "label_en": rid,
                    "installed": bool(home and home.is_dir()),
                    "linked": False,
                    "home": str(home) if home else "",
                    "nous_compatible": rid == "hermes",
                }
            )

    kits: list[dict[str, Any]] = []
    try:
        from . import ecosystem as eco_mod

        for e in eco_mod.list_ecosystem(ensure_auto=False).get("items") or []:
            det = e.get("detect") or {}
            kits.append(
                {
                    "kind": "ecosystem",
                    "id": e.get("id"),
                    "label": e.get("label_zh") or e.get("label"),
                    "label_en": e.get("label"),
                    "installed": bool(det.get("installed")),
                    "activated": bool(det.get("activated")),
                    "home": (det.get("path") or str(ecosystem_dir(e["id"]))),
                    "category": e.get("category"),
                    "nous_compatible": e.get("id") == EVOLUTION_SKILL_PACK_ID,
                }
            )
    except Exception:  # noqa: BLE001
        pass

    pack_installed = ecosystem_dir(EVOLUTION_SKILL_PACK_ID).is_dir() and any(
        ecosystem_dir(EVOLUTION_SKILL_PACK_ID).iterdir()
    ) if ecosystem_dir(EVOLUTION_SKILL_PACK_ID).exists() else False

    return {
        "ok": True,
        "claws": claws,
        "ecosystem": kits,
        "evolution_home": str(_evo_root()),
        "nous": {
            "repo": NOUS_REPO,
            "ecosystem_id": EVOLUTION_SKILL_PACK_ID,
            "installed": pack_installed,
            "note_zh": "Hub 引导式迭代（默认）不依赖 DSPy；安装 hermes-self-evolution 后可在本机跑完整 GEPA。",
            "note_en": "Hub guided cycle (default) needs no DSPy; install hermes-self-evolution for full GEPA locally.",
        },
        "recent": list_runs(limit=8).get("runs") or [],
    }


# ── Constraints (Nous-inspired) ────────────────────────────────────────────


def validate_artifact(text: str, *, baseline: str = "", artifact_type: str = "skill") -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    size = len(text or "")
    limit = MAX_SKILL_CHARS if artifact_type == "skill" else MAX_SKILL_CHARS
    results.append(
        {
            "constraint": "size_limit",
            "passed": size <= limit and size > 0,
            "message": f"size {size}/{limit}",
        }
    )
    if baseline:
        growth = (size - len(baseline)) / max(1, len(baseline))
        results.append(
            {
                "constraint": "growth_limit",
                "passed": growth <= MAX_GROWTH,
                "message": f"growth {growth:.1%} (max {MAX_GROWTH:.0%})",
            }
        )
    if artifact_type == "skill":
        has_heading = bool(re.search(r"(?m)^#\s+\S", text or ""))
        results.append(
            {
                "constraint": "skill_structure",
                "passed": has_heading,
                "message": "has markdown H1" if has_heading else "missing markdown H1",
            }
        )
    results.append(
        {
            "constraint": "non_empty",
            "passed": bool((text or "").strip()),
            "message": "non-empty" if (text or "").strip() else "empty",
        }
    )
    return results


def _constraints_ok(results: list[dict[str, Any]]) -> bool:
    return all(r.get("passed") for r in results)


# ── Inspect / LLM ──────────────────────────────────────────────────────────


def _read_baseline_files(target: dict[str, Any], *, focus: str = "") -> list[dict[str, Any]]:
    paths: list[Path] = []
    focus = (focus or "").strip()
    skill_files = [Path(p) for p in (target.get("skill_files") or [])]
    prompt_files = [Path(p) for p in (target.get("prompt_files") or [])]

    if focus:
        # match by skill folder name or basename
        for p in skill_files + prompt_files:
            if focus.lower() in str(p).lower() or focus.lower() == p.parent.name.lower():
                paths.append(p)
        if not paths:
            # treat focus as relative path under home
            cand = Path(target["home"]) / focus
            if cand.is_file():
                paths.append(cand)

    if not paths:
        # Prefer a few skills + one soul/prompt
        paths.extend(skill_files[: MAX_SCAN_FILES - 1])
        if prompt_files:
            paths.append(prompt_files[0])
        paths = paths[:MAX_SCAN_FILES]

    out: list[dict[str, Any]] = []
    for p in paths:
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(raw) > MAX_FILE_CHARS:
            raw = raw[:MAX_FILE_CHARS] + "\n\n…[truncated]…"
        rel = str(p)
        try:
            rel = str(p.relative_to(Path(target["home"])))
        except ValueError:
            pass
        out.append(
            {
                "path": str(p),
                "rel": rel,
                "name": p.name,
                "parent": p.parent.name,
                "chars": len(raw),
                "content": raw,
                "kind": "skill" if p.name.upper() == "SKILL.MD" else "prompt",
            }
        )
    return out


def _llm_chat(messages: list[dict[str, str]], *, timeout: float = 90) -> str:
    from . import llm_client
    from .secrets import resolve_api_key
    from .settings import load_campus_config

    cfg = load_campus_config()
    key_info = resolve_api_key(cfg)
    backend = cfg.get("backend") or {}
    base_url = str(backend.get("base_url") or "").strip()
    models = cfg.get("models") or {}
    model = str(models.get("main") or models.get("fast") or models.get("reasoning") or "").strip()
    api_key = key_info.get("key") or ""
    if not (base_url and model and api_key):
        raise RuntimeError("Hub LLM 未配置（需要 backend.base_url + models.main + API Key）")
    return llm_client.stream_chat(
        base_url,
        api_key,
        model=model,
        messages=messages,
        timeout=timeout,
        verify_tls=bool(backend.get("verify_tls", True)),
        temperature=0.4,
        max_tokens=4096,
    )


def _extract_json_block(text: str) -> dict[str, Any] | list[Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    # fenced
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if m:
        text = m.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # find first { ... } or [ ... ]
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    return None


def _heuristic_proposals(files: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any]:
    """Offline fallback when LLM is unavailable — structured critique tips."""
    critiques: list[str] = []
    proposals: list[dict[str, Any]] = []
    for f in files:
        content = f.get("content") or ""
        cnotes: list[str] = []
        if len(content) < 200:
            cnotes.append("内容过短，可补充步骤、边界条件与失败回退。")
        if "TODO" in content or "FIXME" in content:
            cnotes.append("存在 TODO/FIXME，建议落成明确指引。")
        if f.get("kind") == "skill" and not re.search(r"(?m)^##\s+", content):
            cnotes.append("缺少二级标题分节（流程 / 约束 / 示例）。")
        if len(content) > MAX_SKILL_CHARS * 0.9:
            cnotes.append("接近 15KB 上限，宜精简冗余。")
        if not cnotes:
            cnotes.append("结构尚可；可补充 1–2 个正反例以稳定行为。")
        critiques.append(f"{f.get('rel')}: " + "；".join(cnotes))
        # Propose a light appendix rather than rewriting whole file blindly
        appendix = (
            f"\n\n## Hub Self-Evolution Notes\n"
            f"- Target: {target.get('label')} (`{target.get('id')}`)\n"
            f"- Keep original purpose; tighten failure handling and examples.\n"
            f"- Generated by Agent Hub guided evolution (review before apply).\n"
        )
        proposed = content.rstrip() + appendix
        constraints = validate_artifact(proposed, baseline=content, artifact_type=f.get("kind") or "skill")
        if not _constraints_ok(constraints):
            # if growth blows limit, skip rewrite
            proposals.append(
                {
                    "path": f["path"],
                    "rel": f["rel"],
                    "action": "note_only",
                    "rationale": "；".join(cnotes),
                    "constraints": constraints,
                    "proposed_content": None,
                }
            )
            continue
        proposals.append(
            {
                "path": f["path"],
                "rel": f["rel"],
                "action": "patch",
                "rationale": "；".join(cnotes),
                "constraints": constraints,
                "proposed_content": proposed,
                "baseline_chars": len(content),
                "proposed_chars": len(proposed),
            }
        )
    return {
        "critique": critiques,
        "proposals": proposals,
        "summary": f"启发式评审：{len(files)} 个文件，{sum(1 for p in proposals if p.get('action')=='patch')} 条可申请补丁（需确认）。",
        "source": "heuristic",
    }


def _llm_proposals(files: list[dict[str, Any]], target: dict[str, Any], *, focus: str = "") -> dict[str, Any]:
    catalog = []
    for f in files[:6]:
        catalog.append(
            {
                "rel": f["rel"],
                "path": f["path"],
                "kind": f["kind"],
                "chars": f["chars"],
                "content": (f["content"] or "")[:6000],
            }
        )
    system = (
        "You are Agent Hub's self-evolution reviewer, inspired by NousResearch/hermes-agent-self-evolution "
        "(critique → propose → constrain → human-confirm apply). "
        "Improve skills/prompts for the target claw or ecosystem pack. "
        "Do NOT invent unrelated features. Preserve original purpose. "
        "Respect size ≤15000 chars and ≤20% growth vs baseline. "
        "Reply with JSON only."
    )
    user = (
        f"Target kind={target.get('kind')} id={target.get('id')} label={target.get('label')}\n"
        f"Home={target.get('home')}\n"
        f"Focus={focus or '(auto)'}\n\n"
        "Baseline files:\n"
        f"{json.dumps(catalog, ensure_ascii=False)}\n\n"
        "Return JSON object:\n"
        "{\n"
        '  "critique": ["short note per file or overall"],\n'
        '  "summary": "one-line Chinese summary",\n'
        '  "proposals": [\n'
        "    {\n"
        '      "path": "absolute path from baseline",\n'
        '      "rel": "relative path",\n'
        '      "action": "patch" | "note_only",\n'
        '      "rationale": "why",\n'
        '      "proposed_content": "full new file text if action=patch else null"\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Only include files you reviewed. Prefer actionable SKILL.md / SOUL.md improvements."
    )
    text = _llm_chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        timeout=75,
    )
    parsed = _extract_json_block(text)
    if not isinstance(parsed, dict):
        raise RuntimeError("LLM did not return valid JSON proposals")
    proposals_in = parsed.get("proposals") or []
    proposals: list[dict[str, Any]] = []
    baseline_by_path = {f["path"]: f for f in files}
    for item in proposals_in:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        base = baseline_by_path.get(path)
        if not base:
            # try match by rel
            rel = str(item.get("rel") or "")
            base = next((f for f in files if f.get("rel") == rel), None)
            if base:
                path = base["path"]
        if not base:
            continue
        action = str(item.get("action") or "note_only")
        proposed = item.get("proposed_content")
        entry: dict[str, Any] = {
            "path": path,
            "rel": item.get("rel") or base.get("rel"),
            "action": action,
            "rationale": str(item.get("rationale") or ""),
            "proposed_content": None,
            "baseline_chars": base.get("chars"),
        }
        if action == "patch" and isinstance(proposed, str) and proposed.strip():
            constraints = validate_artifact(
                proposed,
                baseline=base.get("content") or "",
                artifact_type=base.get("kind") or "skill",
            )
            entry["constraints"] = constraints
            if _constraints_ok(constraints):
                entry["proposed_content"] = proposed
                entry["proposed_chars"] = len(proposed)
            else:
                entry["action"] = "note_only"
                entry["proposed_content"] = None
                entry["blocked_by_constraints"] = True
        else:
            entry["action"] = "note_only"
            entry["constraints"] = validate_artifact(
                base.get("content") or "",
                baseline=base.get("content") or "",
                artifact_type=base.get("kind") or "skill",
            )
        proposals.append(entry)
    return {
        "critique": parsed.get("critique") or [],
        "proposals": proposals,
        "summary": str(parsed.get("summary") or f"LLM 评审完成：{len(proposals)} 条提案"),
        "source": "llm",
        "raw_preview": text[:1200],
    }


# ── Run lifecycle ───────────────────────────────────────────────────────────


def start_review(
    *,
    kind: str,
    target_id: str,
    focus: str = "",
    auto_apply: bool = False,
    mode: str = "auto",
) -> dict[str, Any]:
    """Start a guided evolution review job (critique + proposals). Never auto-applies unless asked.

    mode: auto (LLM then heuristic fallback) | heuristic | llm
    """
    if auto_apply:
        # Still require explicit apply endpoint for safety — flag only notes intent
        pass
    target = resolve_target(kind, target_id)
    run_id = str(uuid.uuid4())
    mode = (mode or "auto").strip().lower()
    if mode not in ("auto", "heuristic", "llm"):
        mode = "auto"
    run: dict[str, Any] = {
        "id": run_id,
        "target_kind": target["kind"],
        "target_id": target["id"],
        "label": target.get("label"),
        "home": target.get("home"),
        "adapter": target.get("adapter"),
        "focus": focus or "",
        "mode": mode,
        "status": "running",
        "phase": "inspect",
        "started_at": time.time(),
        "finished_at": None,
        "files": [],
        "critique": [],
        "proposals": [],
        "applied": [],
        "backup_dir": "",
        "summary": "",
        "error": None,
        "pattern": "nous-hermes-agent-self-evolution (guided LLM cycle)",
        "auto_apply_requested": bool(auto_apply),
        "log": [],
    }
    _write_run(run)
    with _lock:
        _jobs[run_id] = {"id": run_id, "status": "running", "pct": 5}

    def _log(msg: str) -> None:
        run["log"].append({"ts": time.time(), "msg": msg})

    def _work() -> None:
        try:
            _log(f"resolve target {target['kind']}:{target['id']} → {target['home']}")
            files = _read_baseline_files(target, focus=focus)
            run["files"] = [
                {k: v for k, v in f.items() if k != "content"} | {"content_preview": (f.get("content") or "")[:400]}
                for f in files
            ]
            if not files:
                run["status"] = "failed"
                run["phase"] = "inspect"
                run["error"] = "未找到可进化文件（SKILL.md / SOUL.md）。请先安装 claw 或 ecosystem 包。"
                run["finished_at"] = time.time()
                _write_run(run)
                return
            run["phase"] = "critique"
            with _lock:
                _jobs[run_id]["pct"] = 35
            _log(f"critique {len(files)} files (mode={mode})")
            _write_run(run)
            result: dict[str, Any]
            if mode == "heuristic":
                result = _heuristic_proposals(files, target)
            elif mode == "llm":
                result = _llm_proposals(files, target, focus=focus)
            else:
                try:
                    result = _llm_proposals(files, target, focus=focus)
                except Exception as exc:  # noqa: BLE001
                    _log(f"LLM unavailable ({exc}); heuristic fallback")
                    result = _heuristic_proposals(files, target)
            run["critique"] = result.get("critique") or []
            run["proposals"] = result.get("proposals") or []
            run["summary"] = result.get("summary") or ""
            run["source"] = result.get("source")
            run["phase"] = "await_confirm"
            run["status"] = "await_confirm"
            run["finished_at"] = time.time()
            _log("proposals ready — awaiting user confirm via /api/evolution/apply")
            _write_run(run)
            try:
                from . import audit

                audit.log_event(
                    "evolution_review",
                    {
                        "id": run_id,
                        "target": f"{target['kind']}:{target['id']}",
                        "proposals": len(run["proposals"]),
                        "source": run.get("source"),
                    },
                )
            except Exception:  # noqa: BLE001
                pass
            try:
                from .schedule import push_notification

                push_notification(
                    title=f"自我进化提案就绪 · {target.get('label')}",
                    title_en=f"Evolution proposals ready · {target.get('label')}",
                    kind="evolution",
                    status="ok",
                    summary=run.get("summary") or f"{len(run['proposals'])} proposals",
                    summary_en=run.get("summary") or f"{len(run['proposals'])} proposals",
                    task_id=f"evo-{run_id[:8]}",
                )
            except Exception:  # noqa: BLE001
                pass
            with _lock:
                _jobs[run_id] = {"id": run_id, "status": "await_confirm", "pct": 100}
        except Exception as exc:  # noqa: BLE001
            run["status"] = "failed"
            run["error"] = str(exc)
            run["finished_at"] = time.time()
            _write_run(run)
            with _lock:
                _jobs[run_id] = {"id": run_id, "status": "failed", "pct": 100, "error": str(exc)}

    threading.Thread(target=_work, daemon=True, name=f"evo-{run_id[:8]}").start()
    return {
        "ok": True,
        "run_id": run_id,
        "status": "running",
        "target": {k: target[k] for k in ("kind", "id", "label", "home", "adapter", "nous_compatible") if k in target},
        "note_zh": "正在评审；完成后需在 Hub 确认后再写入补丁。不会静默覆盖配置。",
        "note_en": "Reviewing; Hub will ask for confirm before writing patches.",
    }


def job_status(run_id: str) -> dict[str, Any]:
    with _lock:
        job = dict(_jobs.get(run_id) or {})
    try:
        run = _load_run(run_id)
    except FileNotFoundError:
        raise
    return {
        "ok": True,
        "job": job or {"id": run_id, "status": run.get("status"), "pct": 100 if run.get("status") != "running" else 50},
        "run": {
            "id": run.get("id"),
            "status": run.get("status"),
            "phase": run.get("phase"),
            "summary": run.get("summary"),
            "error": run.get("error"),
            "proposal_count": len(run.get("proposals") or []),
            "critique": run.get("critique"),
            "log": (run.get("log") or [])[-20:],
        },
    }


def apply_proposals(
    run_id: str,
    *,
    indices: list[int] | None = None,
    confirm: bool = False,
) -> dict[str, Any]:
    """Apply selected patches after explicit confirm. Backs up originals first."""
    if not confirm:
        raise ValueError("confirm=true required — refuse silent apply")
    run = _load_run(run_id)
    if run.get("status") not in ("await_confirm", "partial", "applied", "rolled_back"):
        if run.get("status") == "running":
            raise ValueError("review still running")
        if run.get("status") == "failed":
            raise ValueError(run.get("error") or "run failed")
    proposals = list(run.get("proposals") or [])
    if indices is None:
        selected = [(i, p) for i, p in enumerate(proposals) if p.get("action") == "patch" and p.get("proposed_content")]
    else:
        selected = []
        for i in indices:
            if 0 <= i < len(proposals):
                selected.append((i, proposals[i]))
    if not selected:
        raise ValueError("no patchable proposals selected")

    bdir = _backup_dir(run_id)
    run["backup_dir"] = str(bdir)
    applied: list[dict[str, Any]] = list(run.get("applied") or [])
    errors: list[str] = []

    for idx, prop in selected:
        if prop.get("action") != "patch" or not prop.get("proposed_content"):
            errors.append(f"#{idx} not a patch")
            continue
        path = Path(prop["path"])
        if not path.is_file():
            errors.append(f"#{idx} missing file {path}")
            continue
        # re-validate
        try:
            baseline = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"#{idx} read fail: {exc}")
            continue
        constraints = validate_artifact(
            prop["proposed_content"],
            baseline=baseline,
            artifact_type="skill" if path.name.upper() == "SKILL.MD" else "prompt",
        )
        if not _constraints_ok(constraints):
            errors.append(f"#{idx} constraints failed: {constraints}")
            continue
        # backup
        rel_safe = re.sub(r"[^\w.\-]+", "_", prop.get("rel") or path.name)
        bak = bdir / f"{idx}_{rel_safe}"
        try:
            shutil.copy2(path, bak)
            path.write_text(prop["proposed_content"], encoding="utf-8")
        except OSError as exc:
            errors.append(f"#{idx} write fail: {exc}")
            continue
        applied.append(
            {
                "index": idx,
                "path": str(path),
                "rel": prop.get("rel"),
                "backup": str(bak),
                "ts": time.time(),
            }
        )

    run["applied"] = applied
    run["apply_errors"] = errors
    run["phase"] = "verify"
    # light verify: files readable + constraints
    verify = {"ok": True, "checked": [], "rollback_tip": f"POST /api/evolution/rollback {{run_id: {run_id!r}}} 或从 {bdir} 还原"}
    for a in applied:
        p = Path(a["path"])
        ok = p.is_file() and p.stat().st_size > 0
        verify["checked"].append({"path": a["path"], "ok": ok})
        if not ok:
            verify["ok"] = False
    run["verify"] = verify
    run["status"] = "applied" if applied and not errors else ("partial" if applied else "await_confirm")
    run["summary"] = (run.get("summary") or "") + f" · applied {len(applied)}"
    run["finished_at"] = time.time()
    # changelog
    changelog = _evo_root() / "CHANGELOG.md"
    line = (
        f"- {time.strftime('%Y-%m-%d %H:%M')} `{run['target_kind']}:{run['target_id']}` "
        f"run={run_id[:8]} applied={len(applied)} backup=`{bdir}`\n"
    )
    try:
        prev = changelog.read_text(encoding="utf-8") if changelog.is_file() else "# Evolution changelog\n\n"
        changelog.write_text(prev + line, encoding="utf-8")
    except OSError:
        pass
    _write_run(run)
    try:
        from . import audit

        audit.log_event("evolution_apply", {"id": run_id, "applied": len(applied), "errors": errors})
    except Exception:  # noqa: BLE001
        pass
    return {
        "ok": bool(applied),
        "run": run,
        "applied": applied,
        "errors": errors,
        "verify": verify,
        "note_zh": f"已写入 {len(applied)} 个文件；备份在 {bdir}。可用「回滚」还原。",
        "note_en": f"Wrote {len(applied)} files; backup at {bdir}. Use rollback to restore.",
    }


def rollback_run(run_id: str) -> dict[str, Any]:
    run = _load_run(run_id)
    applied = list(run.get("applied") or [])
    if not applied:
        raise ValueError("nothing to rollback")
    restored: list[str] = []
    errors: list[str] = []
    for a in reversed(applied):
        bak = Path(a.get("backup") or "")
        dest = Path(a.get("path") or "")
        if not bak.is_file():
            errors.append(f"missing backup {bak}")
            continue
        try:
            shutil.copy2(bak, dest)
            restored.append(str(dest))
        except OSError as exc:
            errors.append(str(exc))
    run["status"] = "rolled_back"
    run["rollback"] = {"restored": restored, "errors": errors, "ts": time.time()}
    run["finished_at"] = time.time()
    _write_run(run)
    try:
        from . import audit

        audit.log_event("evolution_rollback", {"id": run_id, "restored": len(restored)})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "restored": restored, "errors": errors, "run_id": run_id}


def recent_tips(*, limit: int = 5) -> list[str]:
    """Short tips for nightly/morning digests."""
    tips: list[str] = []
    for r in list_runs(limit=limit).get("runs") or []:
        st = r.get("status")
        label = r.get("label") or r.get("target_id")
        if st == "await_confirm":
            tips.append(f"自我进化提案待确认：{label}（{r.get('proposal_count') or 0} 条）")
        elif st == "applied":
            tips.append(f"已应用自我进化：{label} — 见 ~/.agent-cli/evolution/")
        elif st == "failed":
            tips.append(f"自我进化失败：{label} — {(r.get('error') or '')[:80]}")
    if not tips:
        tips.append("可在生态 / Claws 页点击「自我进化」启动引导式迭代（backup + 确认后写入）。")
    return tips

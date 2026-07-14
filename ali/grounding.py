"""Workspace grounding — verified file trees to suppress path/content hallucinations."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import uploads
from .settings import load_campus_config

# Paths the model often invents for "data science packages"
SCAFFOLD_HINTS = (
    "src/main.py",
    "preprocessing.py",
    "setup.py",
    "requirements.txt",
    "notebooks/",
    "tests/test_",
    "exploratory_analysis.ipynb",
)

_PATH_RE = re.compile(
    r"(?:"
    r"(?:`|/Users/[\w./\-]+|/home/[\w./\-]+|[A-Za-z]:\\[\w.\\/\-]+|"
    r"(?:\.?/)?(?:[\w.\-]+/){1,8}[\w.\-]+\.(?:py|R|r|md|txt|csv|json|yaml|yml|ipynb|pdf|docx|xlsx|png|jpg))"
    r")"
)
_REL_FILE_RE = re.compile(
    r"\b((?:[\w.\-]+/){0,6}[\w.\-]+\.(?:py|R|r|md|txt|csv|json|yaml|yml|ipynb|pdf|docx|xlsx|png|jpg|js|ts|sh))\b"
)


def _safe_root(raw: str) -> Path | None:
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        p = Path(raw).expanduser().resolve()
    except OSError:
        return None
    if not p.is_dir():
        return None
    return p


def snapshot_workspace(
    workspace: str = "",
    *,
    max_depth: int = 3,
    max_entries: int = 120,
    session_id: str = "",
) -> dict[str, Any]:
    """Return a verified shallow tree of the workspace (+ session uploads)."""
    cfg = load_campus_config()
    root = _safe_root(workspace) or _safe_root(str(cfg.get("workspace") or ""))
    entries: list[dict[str, Any]] = []
    rel_set: set[str] = set()
    abs_set: set[str] = set()

    if root:
        abs_set.add(str(root))
        stack: list[tuple[Path, int]] = [(root, 0)]
        while stack and len(entries) < max_entries:
            cur, depth = stack.pop(0)
            try:
                children = sorted(cur.iterdir(), key=lambda c: (not c.is_dir(), c.name.lower()))
            except OSError:
                continue
            for child in children:
                if child.name.startswith("."):
                    continue
                try:
                    is_dir = child.is_dir()
                    is_file = child.is_file()
                except OSError:
                    continue
                try:
                    rel = str(child.relative_to(root)).replace("\\", "/")
                except ValueError:
                    continue
                abs_path = str(child.resolve())
                abs_set.add(abs_path)
                rel_set.add(rel)
                if is_dir:
                    rel_set.add(rel + "/")
                    abs_set.add(abs_path + "/")
                entries.append(
                    {
                        "relative": rel + ("/" if is_dir else ""),
                        "path": abs_path,
                        "is_dir": is_dir,
                        "size": child.stat().st_size if is_file else None,
                    }
                )
                if is_dir and depth + 1 < max_depth and len(entries) < max_entries:
                    stack.append((child, depth + 1))

    upload_info = uploads.list_uploads(session_id) if session_id else {"files": [], "root": ""}
    upload_files = list(upload_info.get("files") or [])
    for f in upload_files:
        rel = f"uploads/{f.get('relative')}"
        rel_set.add(rel)
        if f.get("path"):
            abs_set.add(str(f["path"]))

    has_uploads = bool(upload_files)
    # Session uploads alone are enough to ground — workspace folder is optional
    ok = bool(root) or has_uploads
    ws_label = str(root) if root else (str(upload_info.get("root") or "") if has_uploads else "")

    return {
        "ok": ok,
        "workspace": ws_label,
        "workspace_dir": str(root) if root else "",
        "workspace_kind": "dir" if root else ("uploads" if has_uploads else "none"),
        "exists": bool(root) or has_uploads,
        "entries": entries,
        "relative_paths": sorted(rel_set),
        "absolute_paths": sorted(abs_set),
        "truncated": len(entries) >= max_entries,
        "uploads": upload_info,
        "entry_count": len(entries),
        "upload_count": len(upload_files),
    }


def read_text_excerpts(
    workspace: str,
    relative_paths: list[str] | None = None,
    *,
    max_files: int = 8,
    max_bytes: int = 4000,
) -> list[dict[str, Any]]:
    """Read small text files for grounding excerpts (never invent)."""
    root = _safe_root(workspace)
    if not root:
        return []
    snap = snapshot_workspace(str(root), max_depth=3, max_entries=200)
    allowed = set(snap.get("relative_paths") or [])
    picks = relative_paths or []
    if not picks:
        # Prefer reports / README / summaries at top level
        preferred = (
            "README.md",
            "readme.md",
            "proteomics_deep_analysis_report.md",
            "analysis_summary.json",
            "proteomics_reproducible_analysis.R",
        )
        picks = [p for p in preferred if p in allowed or p.rstrip("/") in allowed]
        # Also top-level .md/.json/.R/.txt
        for rel in snap.get("relative_paths") or []:
            if "/" in rel.rstrip("/"):
                continue
            if rel.endswith((".md", ".json", ".R", ".r", ".txt", ".yaml", ".yml")):
                if rel not in picks:
                    picks.append(rel)
            if len(picks) >= max_files:
                break

    out: list[dict[str, Any]] = []
    for rel in picks[:max_files]:
        rel = rel.lstrip("/").replace("\\", "/")
        if ".." in rel.split("/"):
            continue
        # must be in verified set (file, not only dir)
        if rel not in allowed and (rel + "/") not in allowed:
            # allow basename match against verified relatives
            if not any(r == rel or r.endswith("/" + rel) for r in allowed):
                continue
        path = (root / rel).resolve()
        if not str(path).startswith(str(root)) or not path.is_file():
            continue
        from . import office_files

        extracted = office_files.extract_file_text(path, max_bytes=max_bytes)
        if extracted.get("skipped") or not extracted.get("ok"):
            out.append(
                {
                    "relative": rel,
                    "path": str(path),
                    "skipped": bool(extracted.get("skipped")),
                    "reason": extracted.get("reason") or extracted.get("error") or "unreadable",
                }
            )
            continue
        content = extracted.get("content") or ""
        out.append(
            {
                "relative": rel,
                "path": str(path),
                "bytes_read": len(content.encode("utf-8", errors="replace")),
                "truncated": bool(extracted.get("truncated")),
                "content": content,
                "kind": extracted.get("kind"),
            }
        )
    return out


def read_upload_excerpts(
    session_id: str,
    *,
    max_files: int = 6,
    max_bytes: int = 8000,
    prefer_names: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Read session uploads (Excel/CSV/text) into grounding excerpts."""
    if not session_id:
        return []
    from . import office_files

    info = uploads.list_uploads(session_id)
    files = list(info.get("files") or [])
    prefer = {n.lower() for n in (prefer_names or []) if n}

    def _score(f: dict[str, Any]) -> tuple[int, int, float]:
        name = str(f.get("relative") or "").lower()
        hit = 1 if any(p in name or name.endswith(p) for p in prefer) else 0
        suf = Path(name).suffix.lower()
        tabular = 1 if suf in (".xlsx", ".xlsm", ".xls", ".csv", ".tsv") else 0
        return (hit, tabular, float(f.get("mtime") or 0))

    files.sort(key=_score, reverse=True)
    out: list[dict[str, Any]] = []
    for f in files[:max_files]:
        path = Path(str(f.get("path") or ""))
        if not path.is_file():
            continue
        rel = f"uploads/{f.get('relative')}"
        extracted = office_files.extract_file_text(path, max_bytes=max_bytes)
        if extracted.get("skipped") or not extracted.get("ok"):
            out.append(
                {
                    "relative": rel,
                    "path": str(path),
                    "skipped": bool(extracted.get("skipped")),
                    "reason": extracted.get("reason") or extracted.get("error") or "unreadable",
                }
            )
            continue
        out.append(
            {
                "relative": rel,
                "path": str(path),
                "content": extracted.get("content") or "",
                "truncated": bool(extracted.get("truncated")),
                "kind": extracted.get("kind"),
            }
        )
    return out


def anti_hallucination_block(snap: dict[str, Any], excerpts: list[dict[str, Any]] | None = None) -> str:
    lines = [
        "=== GROUNDING (advisory — soft check) ===",
        "Prefer verified listings and excerpts below when describing the user's workspace.",
        "When listing a directory, answer from VERIFIED listings below.",
        "Do not invent a project tree that is not listed below.",
        "Prefer short quotes from VERIFIED EXCERPTS for attachment questions; never invent spreadsheet rows.",
        "OK to use illustrative/example paths inside code samples or tutorials "
        "(e.g. config.yaml, output.json, plot.png) — finish the full answer continuously; "
        "do not stop mid-reply for path verification.",
    ]
    kind = snap.get("workspace_kind") or ("dir" if snap.get("workspace_dir") else "none")
    ws_dir = snap.get("workspace_dir") or ""
    ups = (snap.get("uploads") or {}).get("files") or []
    has_excerpts = bool(excerpts) and any(not e.get("skipped") and not e.get("error") and e.get("content") for e in (excerpts or []))

    if ws_dir:
        lines.append(f"Verified workspace folder: {ws_dir}")
    else:
        lines.append("Verified workspace folder: (not set — optional; session uploads still work)")

    if kind == "none" and not ups and not has_excerpts:
        lines.append("WARNING: no workspace and no session uploads. Do not invent a project tree or file contents.")
    elif not ws_dir and ups:
        lines.append(
            "NOTE: No workspace folder is set. That is OK. "
            "Session attachments listed below ARE verified — you MUST read and use VERIFIED EXCERPTS "
            "to answer questions about those files (including .xlsx). Do NOT refuse attached files."
        )

    if ws_dir and snap.get("entries"):
        lines.append("VERIFIED WORKSPACE LISTING (authoritative):")
        for e in snap.get("entries") or []:
            mark = "dir " if e.get("is_dir") else "file"
            size = e.get("size")
            size_s = f"  ({size} bytes)" if isinstance(size, int) else ""
            lines.append(f"  - [{mark}] {e.get('relative')}{size_s}")
        if snap.get("truncated"):
            lines.append("  … (listing truncated; ask to drill into a subdirectory)")

    if ups:
        lines.append("Verified session uploads (authoritative — these files exist):")
        for f in ups[:40]:
            lines.append(f"  - uploads/{f.get('relative')}  ({f.get('size') or '?'} bytes)")

    if excerpts:
        lines.append("VERIFIED EXCERPTS (confirmed contents — USE THESE for the user's attachment questions):")
        for ex in excerpts:
            if ex.get("skipped") or ex.get("error"):
                lines.append(f"--- {ex.get('relative')}: ({ex.get('reason') or ex.get('error')})")
                continue
            kind_s = ex.get("kind") or "text"
            lines.append(f"--- BEGIN {ex.get('relative')} ({kind_s}) ---")
            lines.append(ex.get("content") or "")
            if ex.get("truncated"):
                lines.append("… [truncated]")
            lines.append(f"--- END {ex.get('relative')} ---")
        lines.append(
            "If VERIFIED EXCERPTS above include spreadsheet/text from an attachment, "
            "answer the user's request using that data. Do not claim you cannot access the attachment."
        )
    elif ups:
        lines.append(
            "Uploads are listed but excerpts were empty — say you need the user to re-attach "
            "or set a workspace; do not invent Excel contents."
        )

    lines.append("=== END GROUNDING ===")
    return "\n".join(lines)


def wants_file_context(message: str) -> bool:
    t = (message or "").lower()
    keys = (
        "目录", "文件", "文件夹", "工作区", "workspace", "列出", "list", "readme",
        "总结", "概览", "结构", "package", "项目", "有哪些", "读取", "内容",
        "folder", "directory", "files", "tree", "ls ", "总结报告",
        "excel", "xlsx", "xls", "csv", "表格", "附件", "attachment", "uploads/",
        "[attachments]", "上传", "打开", "分析", "数据",
    )
    return any(k in t for k in keys)


def _attachment_names(message: str) -> list[str]:
    names: list[str] = []
    if not message:
        return names
    if "[Attachments]" in message:
        for line in message.split("[Attachments]", 1)[-1].splitlines():
            line = line.strip().strip("-").strip()
            if line and not line.startswith("["):
                for part in line.split(","):
                    p = part.strip()
                    if p:
                        names.append(p)
    for m in re.finditer(r"([\w.\u4e00-\u9fff\- /]+\.(?:xlsx|xlsm|xls|csv|tsv|txt|md|json))", message, re.I):
        names.append(m.group(1).strip())
    return names[:20]


def _strip_code_for_path_scan(text: str) -> str:
    """Remove fenced/inline code so illustrative example paths are not flagged."""
    s = text or ""
    # Fenced blocks (``` … ```) — keep newlines so line structure survives
    s = re.sub(r"```[\s\S]*?```", "\n", s)
    # Indented code blocks (4+ spaces) — common in tutorials
    s = re.sub(r"(?m)^( {4,}|\t+).*$", "", s)
    # Inline `code` spans
    s = re.sub(r"`[^`\n]+`", " ", s)
    return s


def _looks_like_write_claim(prose: str) -> bool:
    """True when the assistant claims to have written/created real workspace files."""
    t = (prose or "").lower()
    keys = (
        "已写入", "已创建", "写入了", "创建了文件", "保存到", "写到工作区",
        "wrote ", "created file", "saved to", "written to", "writing to",
        "created the file", "i created", "i wrote", "saved as",
    )
    return any(k in t for k in keys)


def extract_claimed_paths(text: str, *, prose_only: bool = True) -> list[str]:
    """Extract file-like paths. By default scan prose only (ignore code examples)."""
    scan = _strip_code_for_path_scan(text) if prose_only else (text or "")
    found: list[str] = []
    seen = set()
    for m in _REL_FILE_RE.finditer(scan):
        p = m.group(1).replace("\\", "/")
        if p not in seen:
            seen.add(p)
            found.append(p)
    # markdown bold filenames like **main.py**
    for m in re.finditer(r"\*\*([^*\n]+\.(?:py|R|r|md|csv|json|yaml|yml|ipynb))\*\*", scan):
        p = m.group(1).strip()
        if p not in seen:
            seen.add(p)
            found.append(p)
    return found


def verify_response_paths(text: str, snap: dict[str, Any]) -> dict[str, Any]:
    """Soft-flag paths in prose that are not in the verified snapshot.

    Illustrative paths inside code fences are ignored. Without a workspace
    listing, skips hard failure so long coding answers stay continuous.
    """
    prose = _strip_code_for_path_scan(text)
    claimed = extract_claimed_paths(text, prose_only=True)
    allowed_rel = {p.rstrip("/") for p in (snap.get("relative_paths") or [])}
    allowed_base = {Path(p).name for p in allowed_rel}
    ws = snap.get("workspace") or snap.get("workspace_dir") or ""
    # Agent identity / config files are not workspace fabrications
    allowlist_names = {
        "SOUL.md", "soul.md", "AGENTS.md", "README.md", "SKILL.md",
        "campus-office-ai.json", "settings.json", "config.yaml", "config.yml",
        "config.json", "package.json", "pyproject.toml", ".env", "Dockerfile",
    }
    # Common tutorial / example basenames — soft-ignore unless a write claim
    example_basenames = {
        "volcano.png", "heatmap.png", "fastp.json", "output.json", "input.json",
        "example.png", "demo.png", "plot.png", "figure.png", "results.json",
        "data.csv", "sample.csv", "main.py", "app.py", "index.js", "index.ts",
        "script.sh", "run.sh", "test.py", "utils.py",
    }
    write_claim = _looks_like_write_claim(prose)

    # No workspace tree to verify against → don't treat example paths as fatal
    if not allowed_rel and not ws:
        return {
            "ok": True,
            "soft": True,
            "claimed": claimed,
            "verified": [],
            "unverified": [],
            "scaffold_risk": False,
            "workspace": "",
            "skipped": "no_workspace",
        }

    missing: list[str] = []
    verified: list[str] = []
    for p in claimed:
        pn = p.rstrip("/")
        base = Path(pn).name
        if base in allowlist_names or pn in allowlist_names:
            verified.append(p)
            continue
        # Bare example filenames in explanatory prose (not write claims)
        if not write_claim and "/" not in pn and base.lower() in example_basenames:
            verified.append(p)
            continue
        ok = (
            pn in allowed_rel
            or any(a == pn or a.endswith("/" + pn) or a.endswith(pn) for a in allowed_rel)
            or (base in allowed_base and "/" not in pn)
        )
        if ws and pn.startswith(str(ws)):
            ok = True
        if ok:
            verified.append(p)
        else:
            missing.append(p)

    scaffold_risk = any(h in prose for h in SCAFFOLD_HINTS) and bool(missing) and write_claim
    # Soft by default: UI footer only; never truncate/rewrite the assistant body
    return {
        "ok": len(missing) == 0,
        "soft": True,
        "claimed": claimed,
        "verified": verified,
        "unverified": missing,
        "scaffold_risk": scaffold_risk,
        "workspace": ws,
        "write_claim": write_claim,
    }


def build_grounded_preamble(
    route_info: dict[str, Any],
    cfg: dict[str, Any] | None,
    *,
    message: str = "",
    session_id: str = "",
    extra_system: str = "",
) -> tuple[str, dict[str, Any]]:
    from . import routing

    cfg = cfg or load_campus_config()
    base = routing.system_preamble(route_info, cfg)
    ws = (route_info or {}).get("workspace") or cfg.get("workspace") or ""
    snap = snapshot_workspace(str(ws), session_id=session_id)
    excerpts: list[dict[str, Any]] = []
    prefer = _attachment_names(message)
    upload_files = (snap.get("uploads") or {}).get("files") or []
    has_attachments = bool(prefer) or "[Attachments]" in (message or "") or bool(upload_files)
    need_files = wants_file_context(message) or has_attachments

    ws_dir = snap.get("workspace_dir") or (str(ws).strip() if ws else "")
    if need_files and ws_dir:
        excerpts = read_text_excerpts(str(ws_dir), relative_paths=prefer or None, max_files=6, max_bytes=4000)

    # Always pull session uploads when the user attached files or asks about data —
    # even if no workspace folder is configured.
    if session_id and (has_attachments or need_files or bool(upload_files)):
        # Prefer recently attached names; otherwise latest tabular uploads
        up_ex = read_upload_excerpts(
            session_id,
            max_files=8,
            max_bytes=20000,
            prefer_names=prefer or None,
        )
        seen = {e.get("relative") for e in excerpts}
        for e in up_ex:
            if e.get("relative") not in seen:
                excerpts.append(e)

    block = anti_hallucination_block(snap, excerpts)
    parts = [base, block]
    if extra_system.strip():
        parts.append(extra_system.strip())
    # Inject fused Agent Hub + Claw soul into model system prompt
    try:
        from . import soul as soul_mod
        from . import runtimes as runtimes_mod

        ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
        role = (ali or {}).get("active_soul_role")
        resolved = str(
            (route_info or {}).get("runtime_resolved")
            or runtimes_mod.resolved_runtime_id()
        )
        # Ensure claw has latest Hub soul before this turn
        try:
            if resolved and resolved not in ("direct", "auto"):
                soul_mod.sync_soul_to_claw(resolved, role_id=str(role or "office"))
        except Exception:  # noqa: BLE001
            pass
        soul_block = soul_mod.soul_context_for_prompt(
            role_id=str(role or "office"),
            runtime_id=resolved,
        )
        if soul_block:
            parts.append(soul_block)
    except Exception:  # noqa: BLE001
        ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
        role = (ali or {}).get("active_soul_role")
        if role:
            parts.append(f"Active Soul role: {role}. You are Agent Hub.")
    return "\n\n".join(parts), {
        "snapshot": snap,
        "excerpts": len(excerpts),
        "excerpt_ok": sum(1 for e in excerpts if e.get("content") and not e.get("skipped")),
    }

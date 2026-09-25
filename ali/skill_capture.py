"""Save a finished session as a reusable skill (modelled on Claude Science).

``draft_from_session`` turns a session (its request, route, skills, sources,
tools and the provenance/review records) into a SKILL.md draft.
``save_skill`` installs it under the Hub skills root without overwriting an
existing skill and loads it into the Hub.  Captured skills carry
``origin: agent-hub-capture`` and ``triggers:`` in their front matter so
``match_captured`` can attach them automatically to future matching requests,
and ``context_block`` injects their steps (not only the path) into the prompt.
"""

from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

ORIGIN = "agent-hub-capture"
_MAX_BODY = 4000
_ZH_STOP = (
    "帮我", "帮忙", "请你", "请", "一下", "一份", "一个", "关于", "进行", "整理成", "并且", "以及", "然后",
    "我们", "你们", "如何", "怎么", "什么", "可以", "需要", "这个", "那个", "的", "和", "与", "及", "并", "对",
    "把", "给", "在", "是", "了", "吗", "呢",
    # request verbs say what to do, not what the task is about
    "总结", "整理", "分析", "给出", "列出", "生成", "解释", "介绍", "检索", "搜索", "查找", "撰写",
    "提供", "说明", "描述", "比较", "评估", "写", "做", "查", "再", "一次", "最新",
    # question words
    "多少", "是否", "哪些", "哪个", "为什么", "怎样", "有没有",
)
_EN_STOP = frozenset(
    "the and for with from that this what how please help make write give into about some can you your "
    "our are was were will would should could".split()
)


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:48].strip("-")


def extract_triggers(text: str, *, limit: int = 8) -> list[str]:
    """Keywords that should re-activate this skill in future requests."""
    # Identifiers and links are specific to one run, not what the task is about.
    raw = re.sub(r"https?://\S+|\b10\.\d{4,9}/\S+|\b(?:doi|pmid)\s*[:：]?", " ", text or "", flags=re.I)
    out: list[str] = []
    try:
        from .science_connectors import detect_entities

        ent = detect_entities(raw)
        out.extend(ent["genes"])
    except Exception:  # noqa: BLE001
        pass
    for tok in re.findall(r"[A-Za-z][A-Za-z0-9+\-]{2,24}", raw):
        if tok.lower() not in _EN_STOP:
            out.append(tok)
    zh = re.sub(r"[^一-鿿]+", " ", raw)
    for stop in sorted(_ZH_STOP, key=len, reverse=True):
        zh = zh.replace(stop, " ")
    for seg in zh.split():
        if len(seg) >= 3 and seg[-1] in "中里上内":
            seg = seg[:-1]  # 肿瘤中 → 肿瘤
        if 2 <= len(seg) <= 8:
            out.append(seg)
    seen: set[str] = set()
    uniq: list[str] = []
    for t in out:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            uniq.append(t)
    return uniq[:limit]


def _headings(markdown: str, limit: int = 12) -> list[str]:
    heads = []
    in_code = False
    for line in (markdown or "").splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        m = None if in_code else re.match(r"^(#{1,4})\s+(.+?)\s*#*\s*$", line)
        if m:
            heads.append(("  " * (len(m.group(1)) - 1)) + "- " + m.group(2))
    return heads[:limit]


def _one_line(text: str, n: int = 160) -> str:
    return re.sub(r"\s+", " ", text or "").strip()[:n]


def draft_from_session(
    session_id: str,
    message_id: str = "",
    *,
    name: str = "",
    description: str = "",
) -> dict[str, Any]:
    from . import provenance
    from . import sessions as store

    session = store.get_session(session_id)
    if session is None:
        raise FileNotFoundError("session not found")
    msgs = session.messages
    assistants = [(i, m) for i, m in enumerate(msgs) if m.get("role") == "assistant" and not m.get("error")]
    if message_id:
        pick = next(((i, m) for i, m in assistants if m.get("id") == message_id), None)
        if pick is None:
            raise FileNotFoundError("assistant message not found")
    elif assistants:
        pick = assistants[-1]
    else:
        raise ValueError("session has no assistant reply to capture")
    idx, reply = pick
    users = [str(m.get("content") or "") for m in msgs[:idx] if m.get("role") == "user"]
    request = users[-1] if users else ""
    first_request = users[0] if users else request
    route = reply.get("route") or {}
    record = provenance.load_record(session_id, str(reply.get("id") or "")) or {}
    model = record.get("model") or {}
    ctx = record.get("context") or {}
    search = record.get("search") or {}
    tools = record.get("tools") or reply.get("tools") or []
    review = reply.get("review") or record.get("review") or {}

    title = (name or "").strip() or _one_line(first_request, 40) or session.title or "Captured workflow"
    slug = slugify(name) or slugify(" ".join(extract_triggers(first_request, limit=4))) or f"captured-{time.strftime('%Y%m%d-%H%M%S')}"
    desc = (description or "").strip() or f"Reusable workflow captured from Agent Hub: {_one_line(first_request, 120)}"
    triggers = extract_triggers(" ".join(users[:3]) or request)

    steps: list[str] = []
    mode = route.get("execution_mode") or (record.get("request") or {}).get("execution_mode") or "workflow"
    wf = (record.get("request") or {}).get("workflow_id")
    tier = "·".join(x for x in (model.get("tier") or route.get("tier"), model.get("route_key") or route.get("route_key")) if x)
    steps.append(
        f"Run in **{mode}** mode"
        + (f" using workflow preset `{wf}`" if wf else "")
        + (f" on route **{tier}**" if tier else "")
        + " — produce deliverables, not chit-chat."
    )
    skills_used = [s for s in (ctx.get("skills") or route.get("skills") or []) if s]
    if skills_used:
        steps.append("Apply skills: " + ", ".join(f"`{s}`" for s in skills_used) + ".")
    if search.get("sources") or route.get("web_search"):
        engines = ", ".join(search.get("engines") or []) or "web + science databases"
        q = search.get("query") or ""
        steps.append(
            f"Gather evidence first (engines: {engines})"
            + (f"; e.g. query `{_one_line(q, 80)}`" if q else "")
            + ". Cite every claim inline as [n]."
        )
    try:
        from .science_connectors import route as sci_route

        sci = sci_route(request, {})
        if sci:
            steps.append("Look up structured records in: " + ", ".join(f"`{c}`" for c in sci) + ".")
    except Exception:  # noqa: BLE001
        pass
    for t in tools[:8]:
        steps.append(f"Tool `{t.get('name')}`" + (f" — {_one_line(str(t.get('preview') or ''), 90)}" if t.get("preview") else ""))
    steps.append("Verify: every number / percentage / statistic traces to a source or the user's material; DOIs and PMIDs resolve.")
    steps.append("Deliver in the output format below; match the user's language.")

    heads = _headings(str(reply.get("content") or ""))
    rv_line = ""
    if review and not review.get("skipped"):
        rv_line = f"- Original run review: {review.get('warn', 0)} warning(s), {review.get('info', 0)} note(s)."
    lines = [
        "---",
        f"name: {title}",
        f"description: {_one_line(desc, 200)}",
        f"origin: {ORIGIN}",
        "triggers: " + ", ".join(triggers),
        f"source_session: {session_id}",
        f"source_message: {reply.get('id') or ''}",
        "---",
        "",
        f"# {title}",
        "",
        "## When to use",
        "",
        f"Requests like: “{_one_line(first_request, 240)}”",
        "",
        "## Inputs",
        "",
        "- The user's question / topic and any uploaded files or workspace folder.",
        "- Optional: identifiers (gene symbols, UniProt/PDB/ChEMBL/NCT/GEO IDs, DOIs).",
        "",
        "## Steps",
        "",
    ]
    lines += [f"{i}. {s}" for i, s in enumerate(steps, start=1)]
    lines += ["", "## Output format", ""]
    lines += heads or ["- Structured Markdown: summary, main findings (cited), table where useful, limitations, next steps."]
    lines += [
        "",
        "## Quality checks",
        "",
        "- No numbered citation without a matching retrieved source.",
        "- No URL, DOI or PMID that was not retrieved or verified.",
        "- Mark estimates and uncertain claims explicitly.",
    ]
    if rv_line:
        lines.append(rv_line)
    lines += [
        "",
        "## Provenance",
        "",
        f"- Captured {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} from session `{session_id}` / message `{reply.get('id') or ''}`.",
    ]
    if (record.get("integrity") or {}).get("record_sha256"):
        lines.append(f"- Provenance record sha256 `{record['integrity']['record_sha256']}`.")
    lines.append("")
    return {
        "ok": True,
        "slug": slug,
        "name": title,
        "description": desc,
        "triggers": triggers,
        "markdown": "\n".join(lines),
        "source": {"session_id": session_id, "message_id": reply.get("id")},
    }


def _unique_slug(root: Path, slug: str) -> str:
    base = slugify(slug) or "captured-skill"
    cand = base
    n = 2
    while (root / cand).exists():
        cand = f"{base}-{n}"
        n += 1
    return cand


def save_skill(slug: str, markdown: str, *, load: bool = True) -> dict[str, Any]:
    from . import skills

    md = (markdown or "").strip()
    if not md:
        raise ValueError("empty SKILL.md")
    if not md.startswith("---"):
        md = f"---\nname: {slug or 'Captured skill'}\ndescription: Captured workflow\norigin: {ORIGIN}\n---\n\n" + md
    root = skills.install_skills_root()
    final = _unique_slug(root, slug)
    tmp = Path(tempfile.mkdtemp(prefix="ali-skill-"))
    try:
        src = tmp / final
        src.mkdir()
        (src / "SKILL.md").write_text(md + "\n", encoding="utf-8")
        res = skills.install_skill_dir(src, name=final)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if load:
        skills.load_skill_to_hub(final)
    try:
        from . import audit

        audit.log_event("skill_captured", {"skill_id": final, "path": res.get("path"), "loaded": load})
    except Exception:  # noqa: BLE001
        pass
    return {"ok": True, "id": final, "path": res.get("path"), "loaded": bool(load), "renamed": final != (slugify(slug) or "captured-skill")}


def _front_matter(text: str) -> dict[str, str]:
    meta: dict[str, str] = {}
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end > 0:
            for line in text[3:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
    return meta


def captured_skills() -> list[dict[str, Any]]:
    """Captured skills that are currently loaded into the Hub."""
    from . import skills

    loaded = set(skills.get_hub_loaded())
    root = skills.install_skills_root()
    out = []
    for sid in sorted(loaded):
        path = root / sid / "SKILL.md"
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        meta = _front_matter(text)
        if meta.get("origin") != ORIGIN:
            continue
        triggers = [t.strip() for t in (meta.get("triggers") or "").split(",") if t.strip()]
        out.append({"id": sid, "name": meta.get("name") or sid, "triggers": triggers, "path": str(path), "text": text})
    return out


def match_captured(message: str, *, limit: int = 2) -> list[str]:
    """Ids of loaded captured skills whose triggers match this request."""
    low = (message or "").lower()
    scored = []
    for sk in captured_skills():
        trig = sk["triggers"]
        if not trig:
            continue
        hits = sum(1 for t in trig if t.lower() in low)
        need = 1 if len(trig) <= 2 else 2
        if hits >= need:
            scored.append((hits, sk["id"]))
    scored.sort(key=lambda x: (-x[0], x[1]))
    return [sid for _, sid in scored[:limit]]


def context_block(skill_ids: list[str]) -> str:
    """Full steps of captured skills (so direct-LLM runs can follow them too)."""
    want = set(skill_ids or [])
    parts = []
    for sk in captured_skills():
        if sk["id"] in want:
            body = sk["text"]
            end = body.find("\n---", 3) if body.startswith("---") else -1
            body = body[end + 4:].strip() if end > 0 else body
            parts.append(f"### Captured skill `{sk['id']}`\n{body[:_MAX_BODY]}")
    return ("## Captured workflow skills (follow these steps)\n\n" + "\n\n".join(parts)) if parts else ""

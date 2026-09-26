"""Agent Hub's own agent loop: any configured model (any vendor, any API style) can act as an agent.

The model reads the conversation, decides what the user needs and either answers or asks for ONE tool at a time
with a plain JSON object ``{"tool": "...", "args": {...}, "why": "..."}``.  The Hub runs the tool, returns the result
and asks again, until the model answers in ordinary Markdown.  The protocol is text-only on purpose: it works with
every chat endpoint (OpenAI-compatible, Anthropic-compatible, reasoning models) whether or not the vendor supports
native function calling.

Tools: web_search, read_url, pubmed_search, list_files, read_file (Hub workspace, read-only), list_skills,
run_skill (starts a runnable skill such as ``literature-review`` in the background — its progress card shows in the
chat) and skill_status.  Nothing here writes files outside a skill's own output directory or runs shell commands.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

MAX_STEPS = 8
RESULT_CHARS = 6000
_TEXT_EXT = {".md", ".txt", ".csv", ".tsv", ".json", ".yaml", ".yml", ".py", ".r", ".R", ".tex", ".bib", ".html",
             ".xml", ".log", ".ini", ".toml", ".js", ".ts", ".sh"}


# ── tools ─────────────────────────────────────────────────────────────


class Tools:
    """Tool implementations; ``session_id`` / ``workspace`` scope them to the current chat."""

    def __init__(self, *, session_id: str = "", workspace: str = "", question: str = "",
                 on_skill_run: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.session_id = session_id
        self.workspace = Path(workspace).expanduser().resolve() if workspace else None
        self.question = question
        self.on_skill_run = on_skill_run
        self.sources: list[dict[str, Any]] = []

    # descriptions shown to the model (name → (args, what it does))
    SPEC = {
        "web_search": ('{"query": "search words"}', "search the web; returns titles, URLs and snippets"),
        "read_url": ('{"url": "https://…"}', "read a web page (or a paper's abstract via Europe PMC)"),
        "pubmed_search": ('{"query": "PubMed query", "max": 8}', "search PubMed; returns PMID, title, journal, "
                                                                   "year and abstract excerpts"),
        "list_files": ('{"path": "."}', "list files in the Hub workspace folder"),
        "read_file": ('{"path": "relative/path.txt"}', "read a text file from the Hub workspace"),
        "list_skills": ("{}", "list the runnable skills (multi-stage pipelines) and their inputs"),
        "run_skill": ('{"skill": "id", "topic": "…", "profile": "name", "smoke": false}',
                      "start a runnable skill in the background (e.g. literature-review writes a full cited review "
                      "as Word); its live progress card appears in the chat"),
        "skill_status": ('{"run_id": "…"}', "stage / result of a skill run started earlier"),
    }

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        fn = getattr(self, f"t_{name}", None)
        if name not in self.SPEC or fn is None:
            return {"error": f"unknown tool {name!r}; available: {', '.join(self.SPEC)}"}
        try:
            return fn(**{k: v for k, v in (args or {}).items() if isinstance(k, str)})
        except TypeError as exc:
            return {"error": f"bad arguments for {name}: {exc}"}
        except Exception as exc:  # noqa: BLE001 — the model sees the failure and can adapt
            return {"error": f"{type(exc).__name__}: {exc}"[:400]}

    def t_web_search(self, query: str = "", limit: int = 6, **_: Any) -> dict[str, Any]:
        from . import websearch

        res = websearch.search_web(str(query)[:300], limit=max(1, min(int(limit or 6), 10)), deep=False)
        rows = [{"title": r.get("title"), "url": r.get("url"), "snippet": (r.get("snippet") or "")[:300]}
                for r in (res.get("results") or [])[:10]]
        self.sources += [{"title": r["title"], "url": r["url"], "snippet": r["snippet"]} for r in rows]
        return {"results": rows, "error": res.get("error") or ""} if not rows else {"results": rows}

    def t_read_url(self, url: str = "", **_: Any) -> dict[str, Any]:
        from . import page_fetch

        row = page_fetch.fetch_page(str(url), self.question)
        if row.get("ok") or row.get("text"):
            self.sources.append({"title": row.get("title") or url, "url": url,
                                 "snippet": " ".join(row.get("passages") or [])[:500]})
        return {"url": url, "title": row.get("title"), "passages": (row.get("passages") or [])[:4],
                "text": (row.get("text") or "")[:3000], "error": row.get("error") or ""}

    def t_pubmed_search(self, query: str = "", max: int = 8, **_: Any) -> dict[str, Any]:  # noqa: A002
        from . import review_writer as rw

        pmids = rw.pubmed_search(str(query)[:400], retmax=max if isinstance(max, int) and 0 < max <= 20 else 8)
        recs = rw.pubmed_fetch(pmids) if pmids else []
        rows = [{"pmid": r["pmid"], "title": r["title"], "journal": r["journal"], "year": r["year"],
                 "doi": r.get("doi"), "abstract": (r.get("abstract") or "")[:700]} for r in recs]
        self.sources += [{"title": r["title"], "url": f"https://pubmed.ncbi.nlm.nih.gov/{r['pmid']}/",
                          "snippet": r["abstract"][:400]} for r in rows]
        return {"count": len(rows), "papers": rows}

    def _ws_path(self, path: str) -> Path:
        if not self.workspace:
            raise PermissionError("no Hub workspace folder is set (Control Center → workspace)")
        p = (self.workspace / str(path or ".")).resolve()
        if p != self.workspace and self.workspace not in p.parents:
            raise PermissionError("path is outside the Hub workspace")
        return p

    def t_list_files(self, path: str = ".", **_: Any) -> dict[str, Any]:
        root = self._ws_path(path)
        items = []
        for f in sorted(root.iterdir())[:200] if root.is_dir() else []:
            if f.name.startswith("."):
                continue
            items.append({"name": f.name + ("/" if f.is_dir() else ""), "bytes": f.stat().st_size if f.is_file() else None})
        return {"path": str(root.relative_to(self.workspace)) if root != self.workspace else ".", "items": items}

    def t_read_file(self, path: str = "", **_: Any) -> dict[str, Any]:
        p = self._ws_path(path)
        if not p.is_file():
            return {"error": f"not a file: {path}"}
        if p.suffix.lower() not in {e.lower() for e in _TEXT_EXT}:
            return {"error": f"only text files can be read ({p.suffix or 'no extension'})"}
        text = p.read_text(encoding="utf-8", errors="replace")
        return {"path": path, "chars": len(text), "text": text[:20000], "truncated": len(text) > 20000}

    def t_list_skills(self, **_: Any) -> dict[str, Any]:
        from . import skills
        from .skills import _parse_skill_md

        rows = []
        for s in skills.list_skills().get("skills") or []:
            meta = _parse_skill_md(Path(s["path"]) / "SKILL.md")
            if not meta.get("entry"):
                continue
            prof_dir = Path(s["path"]) / "profiles"
            rows.append({"id": s["id"], "description": meta.get("description") or "", "triggers": meta.get("triggers") or "",
                         "profiles": sorted(p.stem for p in prof_dir.glob("*.y*ml")) if prof_dir.is_dir() else []})
        return {"skills": rows}

    def t_run_skill(self, skill: str = "", topic: str = "", profile: str = "", smoke: bool = False, **extra: Any) -> dict[str, Any]:
        from . import skill_runner

        args: dict[str, Any] = {k: v for k, v in {"topic": topic, "profile": profile, "smoke": bool(smoke)}.items() if v}
        for k in ("min_refs", "max_cards", "fresh"):
            if k in extra and extra[k] not in (None, ""):
                args[k] = extra[k]
        if not args.get("topic") and not args.get("profile"):
            return {"error": "give a topic (English works best) or a profile"}
        display = f"/skill {skill} " + " ".join(f"{k}={v}" for k, v in args.items())
        run = skill_runner.start_run(str(skill), args, session_id=self.session_id, display=display, announce=False)
        info = {"run_id": run["id"], "skill": skill, "args": run["args"], "status": run["status"],
                "out": run["out"]}
        if self.on_skill_run:
            self.on_skill_run(info)
        return {**info, "note": "running in the background; the progress card in the chat shows each stage"}

    def t_skill_status(self, run_id: str = "", **_: Any) -> dict[str, Any]:
        from . import skill_runner

        r = skill_runner.get_run(str(run_id))
        return {k: r.get(k) for k in ("id", "skill", "status", "stage", "summary", "error", "outputs")}


# ── the loop ──────────────────────────────────────────────────────────


def system_prompt(tools: Tools, *, skills_hint: str = "") -> str:
    lines = [f"- {name} {args}: {desc}" for name, (args, desc) in Tools.SPEC.items()]
    return (
        "## Agent mode (Agent Hub)\n"
        "Work out from the conversation what the user actually needs and get it done, using tools when they help. "
        "To use a tool, reply with ONLY one JSON object and nothing else:\n"
        '{"tool": "<name>", "args": {...}, "why": "<one short sentence>"}\n'
        "You will get the tool's result and can call another tool. When you have what you need, reply with the "
        "final answer in normal Markdown (no JSON). Use tools only when they add something (current facts, "
        "literature, the user's files, a long pipeline); answer simple questions directly. Never invent tool "
        "results, papers or numbers; cite what the tools returned.\n"
        "When the user wants a deliverable that a runnable skill produces (e.g. a literature review / 综述 → "
        "run_skill literature-review with an English topic), start it with run_skill and then tell the user it is "
        "running, what it will produce and roughly how long it takes — do not write the deliverable yourself.\n"
        "Tools:\n" + "\n".join(lines) + (f"\n{skills_hint}" if skills_hint else "")
    )


def parse_action(text: str) -> dict[str, Any] | None:
    """A tool request in the model's reply, or None when the reply is the final answer."""
    s = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*(\{.*\})\s*```$", s, re.S)
    if m:
        s = m.group(1)
    if not s.startswith("{"):
        return None
    try:
        obj = json.loads(s)
    except json.JSONDecodeError:
        from .review_writer import extract_json

        try:
            obj = extract_json(s)
        except ValueError:
            return None
    if isinstance(obj, dict) and isinstance(obj.get("tool"), str) and obj["tool"] != "final":
        args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
        return {"tool": obj["tool"].strip(), "args": args, "why": str(obj.get("why") or "")[:200]}
    if isinstance(obj, dict) and obj.get("tool") == "final":
        return {"tool": "final", "answer": str(obj.get("answer") or (obj.get("args") or {}).get("answer") or "")}
    return None


def _clip(obj: Any) -> str:
    s = json.dumps(obj, ensure_ascii=False)
    return s if len(s) <= RESULT_CHARS else s[:RESULT_CHARS] + "…(truncated)"


def run(llm: Callable[[list[dict[str, str]]], str], messages: list[dict[str, str]], tools: Tools, *,
        on_step: Callable[[str, dict[str, Any]], None] | None = None, max_steps: int = MAX_STEPS,
        cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """``messages`` = system context + history + user turn; returns ``{answer, steps, sources, skill_runs}``."""
    convo = list(messages)
    steps: list[dict[str, Any]] = []
    skill_runs: list[dict[str, Any]] = []
    answer = ""
    for i in range(max_steps):
        if cancelled and cancelled():
            break
        reply = llm(convo)
        act = parse_action(reply)
        if act is None:
            answer = reply.strip()
            break
        if act["tool"] == "final":
            answer = act.get("answer") or ""
            break
        if on_step:
            on_step("tool", {"name": act["tool"], "args": act["args"], "why": act["why"], "step": i + 1})
        result = tools.call(act["tool"], act["args"])
        if act["tool"] == "run_skill" and result.get("run_id"):
            skill_runs.append(result)
        steps.append({"tool": act["tool"], "args": act["args"], "why": act["why"],
                      "ok": not result.get("error"), "error": result.get("error") or ""})
        if on_step:
            on_step("result", {"name": act["tool"], "ok": not result.get("error"), "error": result.get("error") or "",
                               "summary": _summary(act["tool"], result), "step": i + 1})
        convo.append({"role": "assistant", "content": json.dumps({"tool": act["tool"], "args": act["args"]},
                                                                  ensure_ascii=False)})
        convo.append({"role": "user", "content": f"TOOL RESULT ({act['tool']}):\n{_clip(result)}\n\n"
                                                 "Call another tool, or give the final answer in Markdown."})
    else:
        convo.append({"role": "user", "content": "Tool budget reached. Give the final answer now in Markdown, "
                                                 "based only on the results above."})
        answer = llm(convo).strip()
        if parse_action(answer):
            answer = ""
    return {"answer": answer, "steps": steps, "sources": tools.sources, "skill_runs": skill_runs}


def _summary(name: str, result: dict[str, Any]) -> str:
    if result.get("error"):
        return str(result["error"])[:160]
    if name == "web_search":
        return f"{len(result.get('results') or [])} results"
    if name == "pubmed_search":
        return f"{result.get('count', 0)} papers"
    if name == "read_url":
        return str(result.get("title") or result.get("url") or "")[:120]
    if name == "list_files":
        return f"{len(result.get('items') or [])} items"
    if name == "read_file":
        return f"{result.get('chars', 0)} characters"
    if name == "list_skills":
        return ", ".join(s["id"] for s in result.get("skills") or []) or "none"
    if name == "run_skill":
        return f"started {result.get('skill')} ({result.get('run_id')})"
    if name == "skill_status":
        return f"{result.get('status')}: {str(result.get('stage') or '')[:100]}"
    return "ok"

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
        self.started: list[dict[str, Any]] = []  # skill runs started in this turn (one per turn)

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
        "stop_skill": ('{"run_id": "…"}', "stop a running skill run when the user asks to stop / cancel it "
                                        "(omit run_id for the run started in this chat)"),
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
                         "profiles": sorted(p.stem for p in prof_dir.glob("*.y*ml")) if prof_dir.is_dir() else [],
                         "profile_topics": _profile_topics(prof_dir)})
        return {"skills": rows}

    def _resolve_skill(self, skill: str) -> tuple[str, list[str]]:
        """The runnable skill the model meant ("literature_review", "Literature Review", "综述" → literature-review)."""
        rows = self.t_list_skills()["skills"]
        ids = [r["id"] for r in rows]
        norm = lambda x: re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(x).lower())  # noqa: E731
        want = norm(skill)
        for r in rows:
            if want and want in (norm(r["id"]), norm(r["id"]).replace("skill", "")):
                return r["id"], ids
        for r in rows:  # a trigger word or a unique partial id
            trig = [norm(t) for t in re.split(r"[,，;/]", str(r.get("triggers") or "")) if t.strip()]
            if want and (want in trig or want.replace("skill", "") in trig):
                return r["id"], ids
        partial = [r["id"] for r in rows if want and (want in norm(r["id"]) or norm(r["id"]) in want)]
        if len(partial) == 1:
            return partial[0], ids
        if not want and len(rows) == 1:
            return rows[0]["id"], ids
        return "", ids

    def t_run_skill(self, skill: str = "", topic: str = "", profile: str = "", smoke: Any = False, **extra: Any) -> dict[str, Any]:
        from . import skill_runner

        nested = extra.pop("args", None)  # {"skill": …, "args": {"topic": …}} — accept the nested shape too
        if isinstance(nested, dict):
            topic = topic or str(nested.get("topic") or "")
            profile = profile or str(nested.get("profile") or "")
            smoke = smoke or nested.get("smoke", False)
            extra = {**nested, **extra}
        for alt in ("query", "title", "subject", "theme", "question", "prompt"):  # topic under another name
            if not topic and isinstance(extra.get(alt), str):
                topic = extra[alt]
        smoke = smoke if isinstance(smoke, bool) else str(smoke).strip().lower() in ("1", "true", "yes", "on", "smoke")
        smoke = smoke or wants_trial(self.question)  # "先小规模试跑" is the user's call, not the model's
        if self.started:  # models sometimes repeat the call; never start the same pipeline twice in one turn
            return {**self.started[0], "error": f"already started {self.started[0]['skill']} "
                                                f"({self.started[0]['run_id']}) in this turn; give the final answer now"}
        if self.question and not wants_deliverable(self.question):
            return {"error": "the user asked a question, not for a pipeline run — answer it with the research tools "
                             "(pubmed_search for literature / PMIDs, web_search, read_url); start a skill only when "
                             "the user asks for its deliverable (e.g. 写一篇综述 / write a review)"}
        resolved, ids = self._resolve_skill(skill or extra.get("id") or extra.get("name") or "")
        if not resolved:
            return {"error": f"no runnable skill {skill!r}; available: {', '.join(ids) or 'none installed'}"}
        args: dict[str, Any] = {k: v for k, v in {"topic": str(topic).strip(), "profile": str(profile).strip(),
                                                   "smoke": smoke}.items() if v}
        for k in ("min_refs", "max_cards", "fresh"):
            if k in extra and extra[k] not in (None, "", False):
                args[k] = extra[k]
        if not args.get("topic") and not args.get("profile"):
            return {"error": "give a topic (English works best) or a profile"}
        note = ""
        if args.get("topic") and args.get("profile"):  # a saved profile is for its own topic, not any review
            ptopic = next((r.get("profile_topics", {}).get(args["profile"], "") for r in self.t_list_skills()["skills"]
                           if r["id"] == resolved), "")
            if ptopic and not topics_overlap(args["topic"], ptopic):
                note = (f"profile {args['profile']!r} is for another topic ({ptopic[:100]}); not used — the skill "
                        "plans a profile for this topic. ")
                args.pop("profile")
        display = f"/skill {resolved} " + " ".join(f"{k}={v}" for k, v in args.items())
        run = skill_runner.start_run(resolved, args, session_id=self.session_id, display=display, announce=False)
        info = {"run_id": run["id"], "skill": resolved, "args": run["args"], "status": run["status"],
                "out": run["out"]}
        self.started.append(info)
        if self.on_skill_run:
            self.on_skill_run(info)
        return {**info, "note": note + "Started in the background; the progress card in the chat shows each stage "
                                       "and the Word file when done. Now give the final answer (what is running, what "
                                       "it will produce, that the card tracks it) — do not poll skill_status."}

    def t_stop_skill(self, run_id: str = "", **_: Any) -> dict[str, Any]:
        from . import skill_runner

        if self.question and not wants_stop(self.question):
            return {"error": "the user did not ask to stop a run; only stop a skill when asked (停止 / 取消 / stop)"}
        rid = str(run_id or "").strip()
        if not rid:  # the latest run of this chat that is still going
            rid = next((r["id"] for r in skill_runner.list_runs(50) if r.get("status") == "running"
                        and (not self.session_id or r.get("session_id") == self.session_id)), "")
        if not rid:
            return {"error": "no running skill run in this chat"}
        r = skill_runner.stop_run(rid)
        return {k: r.get(k) for k in ("id", "skill", "status", "stage")} | {
            "note": "stopping; the progress card shows 已停止 and any partial files when the process has exited"}

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
        "results, papers or numbers; cite what the tools returned. Never say you started, ran, searched, listed or "
        "read anything unless a TOOL RESULT in this conversation shows it — to do it, send the JSON. Do not put "
        "any text before or after the JSON. Search results already shown above were fetched automatically and may "
        "miss the literature: when the user asks for papers, literature, evidence or PMIDs, call pubmed_search.\n"
        "When the user wants a deliverable that a runnable skill produces (e.g. a literature review / 综述 → "
        "run_skill literature-review with an English topic; only when they ask for that deliverable, never for a "
        "question about the literature), start it with run_skill and then tell the user it is "
        "running, what it will produce and roughly how long it takes — do not write the deliverable yourself.\n"
        "Tools:\n" + "\n".join(lines) + f"\n{skills_hint or skills_line(tools)}"
    )


def _profile_topics(prof_dir: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not prof_dir.is_dir():
        return out
    for p in sorted(prof_dir.glob("*.y*ml")):
        m = re.search(r"^topic:\s*(?:>-?|\|-?)?\s*(.*?)(?=^\S|\Z)", p.read_text(encoding="utf-8", errors="replace"), re.S | re.M)
        out[p.stem] = " ".join((m.group(1) if m else "").replace("'", "").replace('"', "").split())[:240]
    return out


_STOP = set("a an and as at by for from in into of on or the to with review role roles its their between via "
            "systematic critical comparison analysis".split())


def topics_overlap(a: str, b: str) -> bool:
    """Is topic ``a`` the topic of profile ``b``? Named entities (THBS4, GDF15, EasyMultiProfiler …) decide when the
    request has any; otherwise at least half of its content words must appear in the profile's topic."""
    ids = lambda t: {w.lower() for w in re.findall(r"\b(?=\w*\d)[A-Za-z0-9-]{3,}\b|\b[A-Z][A-Z0-9-]{2,}\b|\b[A-Z][a-z]+[A-Z]\w*\b", t)}  # noqa: E731
    words = lambda t: {w for w in re.findall(r"[a-z0-9][a-z0-9-]{2,}", t.lower()) if w not in _STOP}  # noqa: E731
    want_ids = ids(a)
    if want_ids:
        return bool(want_ids & (ids(b) | words(b)))
    wa = words(a)
    return bool(wa) and len(wa & words(b)) * 2 >= len(wa)


# the user asks for something to be produced or run (not just a question): 写/撰写/生成… / write, draft, run …
_DELIVER = re.compile(r"写|撰写|起草|生成|制作|做(一|个|篇|份)|出(一|个|篇|份)|整理成|试跑|跑(一下|一遍|个)|运行|启动|执行"
                      r"|\b(write|draft|compose|produce|generate|prepare|create|run|start|launch)\b", re.I)


def wants_deliverable(question: str) -> bool:
    return bool(_DELIVER.search(question or ""))


_STOP_ASK = re.compile(r"停止|停掉|停下|终止|取消|中止|别跑了|不要跑了|\b(stop|cancel|abort|halt|kill)\b", re.I)


def wants_stop(question: str) -> bool:
    return bool(_STOP_ASK.search(question or ""))


_TRIAL = re.compile(r"试跑|小规模|先试|试一下|测试一下|快速版|\b(smoke|trial run|quick (?:run|test)|dry run)\b", re.I)


def wants_trial(question: str) -> bool:
    return bool(_TRIAL.search(question or ""))


def skills_line(tools: Tools) -> str:
    """The installed runnable skill ids, so the model calls run_skill with a real id."""
    try:
        rows = tools.t_list_skills()["skills"]
    except Exception:  # noqa: BLE001
        return ""
    if not rows:
        return "Runnable skills installed: none."
    return "Runnable skills installed (use these exact ids with run_skill): " + "; ".join(
        f"{r['id']}" + (" (saved profiles, use one ONLY when the user's topic is that same topic, otherwise omit "
                        "profile: " + "; ".join(f"{k} = {v[:120]}" for k, v in r["profile_topics"].items()) + ")"
                        if r.get("profile_topics") else "") for r in rows) + "."


def parse_action(text: str) -> dict[str, Any] | None:
    """A tool request in the model's reply, or None when the reply is the final answer.

    Models sometimes put a sentence before the JSON ("我先列出工作区文件。{"tool": …}"): a known tool request
    anywhere in the reply still counts, so the step is taken instead of showing raw JSON to the user."""
    s = (text or "").strip()
    m = re.match(r"^```(?:json)?\s*(\{.*\})\s*```$", s, re.S)
    if m:
        s = m.group(1)
    obj: Any = None
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            from .review_writer import extract_json

            try:
                obj = extract_json(s)
            except ValueError:
                obj = None
    if not (isinstance(obj, dict) and isinstance(obj.get("tool"), str)):
        obj = _embedded_action(s)
    if isinstance(obj, dict) and isinstance(obj.get("tool"), str) and obj["tool"] != "final":
        args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
        return {"tool": obj["tool"].strip(), "args": args, "why": str(obj.get("why") or "")[:200]}
    if isinstance(obj, dict) and obj.get("tool") == "final":
        return {"tool": "final", "answer": str(obj.get("answer") or (obj.get("args") or {}).get("answer") or "")}
    return None


def _embedded_action(s: str) -> dict[str, Any] | None:
    """The first ``{"tool": "<known tool>", …}`` object inside prose (or a fenced block inside prose)."""
    dec = json.JSONDecoder()
    for m in re.finditer(r"\{\s*\"tool\"\s*:", s):
        try:
            obj, _end = dec.raw_decode(s, m.start())
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and obj.get("tool") in Tools.SPEC:
            return obj
    return None


# a reply that says it did / is doing something although no tool ran ("技能已启动", "我先列出…")
_CLAIM = re.compile(r"已(经)?(启动|开始|运行|检索|搜索|读取|列出)|正在(为你|帮你)?(启动|运行|检索|搜索|读取)|我(先|来|将)(为你|帮你)?"
                    r"(启动|运行|列出|读取|检索|搜索|查)|\b(I(?:'ve| have)? (?:started|launched|searched|read)|"
                    r"let me (?:start|run|search|list|read|check))\b", re.I)


def claims_action(text: str) -> bool:
    s = text or ""
    return bool(_CLAIM.search(s)) or any(re.search(rf"`?\b{re.escape(n)}\b`?", s) for n in Tools.SPEC)


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
    nudged = False
    for i in range(max_steps):
        if cancelled and cancelled():
            break
        reply = llm(convo)
        act = parse_action(reply)
        if act is None and not steps and not nudged and claims_action(reply):
            # the model described an action instead of requesting it: say so once and let it call the tool
            nudged = True
            convo.append({"role": "assistant", "content": reply})
            convo.append({"role": "user", "content": "No tool has run yet — nothing was started, searched or read. "
                                                     "If a tool is needed, reply now with ONLY the JSON object "
                                                     '{"tool": …, "args": {…}, "why": …}; otherwise give the final '
                                                     "answer without claiming any action."})
            continue
        if act is None:
            answer = reply.strip()
            break
        if act["tool"] == "final":
            answer = act.get("answer") or ""
            break
        if on_step:
            on_step("tool", {"name": act["tool"], "args": act["args"], "why": act["why"], "step": i + 1})
        result = tools.call(act["tool"], act["args"])
        if act["tool"] == "run_skill" and result.get("run_id") and not result.get("error"):
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
    if name == "stop_skill":
        return f"{result.get('id')}: {result.get('status')}"
    if name == "skill_status":
        return f"{result.get('status')}: {str(result.get('stage') or '')[:100]}"
    return "ok"

"""Runnable skills: a skill whose SKILL.md names an ``entry`` script is executed by the Hub.

- ``start_run`` launches the entry (Hub Python, Hub package on ``PYTHONPATH``) in the background; every stdout
  line is kept so the UI can poll progress (``get_run(run_id, since=n)``), and the run is recorded in the session.
- ``export_skill_zip`` packs an installed skill for transfer; the receiving Hub installs it with the existing
  ``/api/skills/upload`` (``skills.install_skill_zip``).
- ``author_skill`` has the Hub's configured model write the skill's SKILL.md from the pipeline it wraps (and a
  finished run, if any), then installs and loads it.
"""

from __future__ import annotations

import io
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any, Callable

from .config import REPO_ROOT, STATE_DIR

RUNS_DIR = STATE_DIR / "skill-runs"
_RUNS: dict[str, dict[str, Any]] = {}
_PROCS: dict[str, subprocess.Popen] = {}
_LOCK = threading.Lock()
_SKIP = {"__pycache__", "checkpoints", ".git"}
_KEY_RE = re.compile(r"sk-[A-Za-z0-9_\-]{16,}")


def _mask(text: str) -> str:
    return _KEY_RE.sub(lambda m: m.group(0)[:6] + "…" + m.group(0)[-4:], text)


# ── skills with an entry ──────────────────────────────────────────────


def skill_path(skill_id: str) -> Path:
    from . import skills

    for s in skills.list_skills().get("skills") or []:
        if s.get("id") == skill_id and s.get("path"):
            return Path(s["path"])
    raise FileNotFoundError(f"skill not installed: {skill_id}")


def skill_entry(skill_id: str) -> tuple[Path, Path]:
    """(skill dir, entry script) — the entry must be a .py file inside the skill directory."""
    from .skills import _parse_skill_md

    root = skill_path(skill_id)
    entry = str(_parse_skill_md(root / "SKILL.md").get("entry") or "").strip()
    if not entry:
        raise ValueError(f"skill {skill_id} has no entry (SKILL.md frontmatter 'entry: run.py')")
    script = (root / entry).resolve()
    if root.resolve() not in script.parents or script.suffix != ".py" or not script.is_file():
        raise ValueError(f"skill {skill_id}: entry must be a .py file inside the skill ({entry})")
    return root, script


def parse_args(text: str | list[str] | dict[str, Any]) -> list[str]:
    """Chat-style arguments → argv: ``profile=x smoke`` → ``--profile x --smoke``; plain words → ``--topic "…"``."""
    if isinstance(text, dict):
        argv: list[str] = []
        for k, v in text.items():
            flag = "--" + str(k).replace("_", "-")
            if v is True:
                argv.append(flag)
            elif v not in (None, False, ""):
                argv += [flag, str(v)]
        return argv
    if isinstance(text, list):
        return [str(x) for x in text]
    argv, words = [], []
    for tok in shlex.split(text or ""):
        if tok.startswith("--"):
            argv.append(tok)
        elif re.fullmatch(r"[a-z][a-z_-]*=.+", tok):
            k, v = tok.split("=", 1)
            argv += ["--" + k.replace("_", "-"), v]
        elif tok in ("smoke", "fresh"):
            argv.append("--" + tok)
        elif argv and argv[-1].startswith("--") and not words and argv[-1] not in ("--smoke", "--fresh"):
            argv.append(tok)  # value of a preceding --flag
        else:
            words.append(tok)
    if words:
        argv += ["--topic", " ".join(words)]
    return argv


# ── runs ──────────────────────────────────────────────────────────────


def _save(run: dict[str, Any]) -> None:
    d = RUNS_DIR / run["id"]
    d.mkdir(parents=True, exist_ok=True)
    (d / "run.json").write_text(json.dumps({k: v for k, v in run.items() if k != "lines"}, ensure_ascii=False,
                                           indent=1), encoding="utf-8")


def _outputs(out: Path) -> list[dict[str, Any]]:
    if not out.exists():
        return []
    return [{"name": f.name, "bytes": f.stat().st_size} for f in sorted(out.iterdir()) if f.is_file()]


def start_run(skill_id: str, args: Any = "", *, session_id: str = "", out_dir: str | Path | None = None,
              on_line: Callable[[str], None] | None = None, display: str = "",
              announce: bool = True) -> dict[str, Any]:
    root, script = skill_entry(skill_id)
    run_id = f"{re.sub(r'[^a-z0-9-]+', '-', skill_id.lower())}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"
    argv = parse_args(args)
    if "--out" in argv[:-1]:  # an explicit output directory (relative = under the Hub root) replaces the default
        i = argv.index("--out")
        out_dir = argv[i + 1] if Path(argv[i + 1]).is_absolute() else REPO_ROOT / argv[i + 1]
        del argv[i:i + 2]
    out = Path(out_dir) if out_dir else RUNS_DIR / run_id / "out"
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-u", str(script), "--out", str(out), *argv]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), os.environ.get("PYTHONPATH", "")]).strip(os.pathsep),
           "PYTHONUNBUFFERED": "1"}
    run = {"id": run_id, "skill": skill_id, "args": argv, "session_id": session_id, "out": str(out),
           "status": "running", "started_at": time.time(), "finished_at": None, "returncode": None,
           "stage": "starting", "lines": [], "outputs": [], "summary": None}
    with _LOCK:
        _RUNS[run_id] = run
    _save(run)
    if session_id and announce:  # an agent-started run is announced by the agent's own reply
        try:
            from . import sessions as store

            store.append_messages(session_id, {"role": "user", "content": display or f"/skill {skill_id} "
                                               + " ".join(argv), "skill_run": run_id, "ts": time.time()})
        except Exception:  # noqa: BLE001
            pass
    proc = subprocess.Popen(cmd, cwd=str(root), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                            bufsize=1, encoding="utf-8", errors="replace")
    _PROCS[run_id] = proc
    log_file = RUNS_DIR / run_id / "run-log.txt"

    def pump() -> None:
        with open(log_file, "a", encoding="utf-8") as fh:
            for raw in proc.stdout or []:
                line = _mask(raw.rstrip("\n"))
                fh.write(line + "\n")
                fh.flush()
                with _LOCK:
                    run["lines"].append(line)
                    if line.startswith("RESULT:"):
                        try:
                            run["summary"] = json.loads(line.split(" ", 2)[2])
                        except (IndexError, json.JSONDecodeError):
                            pass
                    elif re.match(r"^\[\s*\d+s\]\s+\S", line):
                        run["stage"] = re.sub(r"^\[\s*\d+s\]\s+", "", line)[:160]
                if on_line:
                    on_line(line)
        rc = proc.wait()
        with _LOCK:
            run.update(status="done" if rc == 0 else "failed", returncode=rc, finished_at=time.time(),
                       outputs=_outputs(out))
            if rc != 0 and run["lines"]:
                run["error"] = next((ln for ln in reversed(run["lines"]) if ln.strip()), "")[:400]
        _PROCS.pop(run_id, None)
        _save(run)
        if session_id:
            _record_in_session(run)

    threading.Thread(target=pump, name=f"skill-run-{run_id}", daemon=True).start()
    return get_run(run_id)


def _record_in_session(run: dict[str, Any]) -> None:
    from . import sessions as store

    summ = run.get("summary") or {}
    lines = [f"**Skill `{run['skill']}` — {run['status']}** (run `{run['id']}`)"]
    if summ:
        chk = summ.get("citation_check") or {}
        lines.append(f"{summ.get('title', '')}\n\n{summ.get('sections')} sections · {summ.get('words')} words · "
                     f"{chk.get('cited')} references cited · {summ.get('llm_calls')} model calls ({summ.get('model')})")
    if run.get("error"):
        lines.append(f"Error: {run['error']}")
    for o in run.get("outputs") or []:
        lines.append(f"- [{o['name']}](/api/skill-runs/{run['id']}/file?name={o['name']})")
    try:
        store.append_messages(run["session_id"], {"role": "assistant", "content": "\n".join(lines),
                                                  "skill_run": run["id"], "ts": time.time()})
    except Exception:  # noqa: BLE001 — the run itself is recorded on disk either way
        pass


def get_run(run_id: str, since: int = 0) -> dict[str, Any]:
    with _LOCK:
        run = _RUNS.get(run_id)
        if run is not None:
            out = {k: v for k, v in run.items() if k != "lines"}
            out["lines"] = run["lines"][since:]
            out["next"] = len(run["lines"])
            return out
    f = RUNS_DIR / run_id / "run.json"
    if not f.exists():
        raise FileNotFoundError(run_id)
    out = json.loads(f.read_text(encoding="utf-8"))
    log = RUNS_DIR / run_id / "run-log.txt"
    lines = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
    out["lines"], out["next"] = lines[since:], len(lines)
    return out


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    rows = []
    for f in sorted(RUNS_DIR.glob("*/run.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
        try:
            rows.append(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return rows


def stop_run(run_id: str) -> dict[str, Any]:
    proc = _PROCS.get(run_id)
    if proc and proc.poll() is None:
        proc.terminate()
    return get_run(run_id)


def run_file(run_id: str, name: str) -> Path:
    info = get_run(run_id)
    out = Path(info["out"]).resolve()
    f = (out / name).resolve()
    if f.parent != out or not f.is_file():
        raise FileNotFoundError(name)
    return f


# ── transfer ──────────────────────────────────────────────────────────


def export_skill_zip(skill_id: str) -> bytes:
    """The installed skill as a zip with one top-level folder (``install_skill_zip`` keeps its name)."""
    root = skill_path(skill_id)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(root.rglob("*")):
            rel = f.relative_to(root)
            if f.is_file() and not (set(rel.parts) & _SKIP) and f.suffix != ".pyc":
                zf.write(f, f"{skill_id}/{rel.as_posix()}")
    return buf.getvalue()


# ── authoring by the Hub's model ──────────────────────────────────────

AUTHOR_SYSTEM = ("You are Agent Hub's skill author. You turn a working pipeline into a reusable, transferable skill "
                 "description (SKILL.md) that another scientist or another Agent Hub can follow exactly.")


def _pipeline_context(source: Path, run_dir: Path | None) -> str:
    from . import review_writer as rw

    parts = [f"PIPELINE MODULE (ali/review_writer.py) DOCSTRING\n{rw.__doc__ or ''}",
             f"run() DOCSTRING\n{rw.run.__doc__ or ''}",
             "STAGES (checkpointed in order): profile, queries, records, screened, outline, drafts, reviews, gaps (missing "
             "literature named by the reviewers → PubMed → new evidence cards), revised, "
             "integrated, audited, table, abstract, response",
             "PROFILE FIELDS: " + ", ".join(rw.DEFAULT_PROFILE)]
    entry = source / "run.py"
    if entry.exists():
        doc = re.search(r'^"""(.*?)"""', entry.read_text(encoding="utf-8"), re.S)
        parts.append(f"ENTRY run.py DOCSTRING\n{doc.group(1) if doc else ''}")
    profs = sorted(p.stem for p in (source / "profiles").glob("*.y*ml")) if (source / "profiles").exists() else []
    parts.append("BUNDLED PROFILES: " + ", ".join(profs))
    if (source / "SKILL.md").exists():
        parts.append("CURRENT SKILL.md\n" + (source / "SKILL.md").read_text(encoding="utf-8")[:4000])
    if run_dir and run_dir.exists():
        for name in ("summary.json", "run-log.txt"):
            f = run_dir / name
            if f.exists():
                parts.append(f"FINISHED RUN {name}\n" + f.read_text(encoding="utf-8", errors="replace")[-3000:])
        audit = run_dir / "citation_audit.json"
        if audit.exists():
            try:
                n = sum(len(x.get("issues") or []) for x in json.loads(audit.read_text(encoding="utf-8")))
                parts.append(f"FINISHED RUN citation audit: {n} unsupported citations corrected")
            except (OSError, json.JSONDecodeError):
                pass
    return "\n\n".join(parts)


def _frontmatter(md: str) -> tuple[dict[str, str], str]:
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n?(.*)", md, re.S)
    if not m:
        return {}, md
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip("\"'")
    return meta, m.group(2)


class AuthorCheckError(ValueError):
    """The model's SKILL.md failed the Hub's self-check; ``draft`` is the rejected text."""

    def __init__(self, message: str, draft: str) -> None:
        super().__init__(message)
        self.draft = draft


def cli_flags(script: Path) -> set[str]:
    """The ``--flags`` an entry script really defines (argparse ``add_argument("--x"``), plus ``--help``."""
    text = script.read_text(encoding="utf-8")
    return set(re.findall(r"add_argument\(\s*[\"'](--[a-z][a-z0-9-]*)", text)) | {"--help"}


def unknown_flags(markdown: str, real: set[str]) -> list[str]:
    return sorted(set(re.findall(r"(?<![\w-])(--[a-z][a-z0-9-]*)", markdown)) - real)


def author_skill(skill_id: str = "literature-review", *, source: str | Path | None = None,
                 run_dir: str | Path | None = None, llm: Callable[..., str] | None = None,
                 load: bool = True) -> dict[str, Any]:
    """The Hub's model writes SKILL.md for the pipeline; the package (entry + profiles) is installed with it."""
    from . import audit, skills
    from . import review_writer as rw

    src = Path(source) if source else REPO_ROOT / "skills" / skill_id
    if run_dir and not Path(run_dir).is_absolute():
        run_dir = REPO_ROOT / run_dir
    if not (src / "run.py").exists():
        raise FileNotFoundError(f"skill source has no run.py: {src}")
    llm = llm or rw.HubLLM()
    model = f"{getattr(llm, 'provider', '')}/{getattr(llm, 'model', '')}".strip("/")
    reply = llm(AUTHOR_SYSTEM, (
        "Write the SKILL.md for the pipeline below. Start with frontmatter between --- lines with exactly these "
        f"keys: name ({skill_id}), description (one line, ≤ 220 characters), triggers (comma-separated phrases in "
        "English and Chinese that should activate the skill), entry (run.py). Then Markdown sections: '# <title>', "
        "'## When to use', '## Inputs' (CLI arguments and profile fields, with examples), '## Steps' (numbered, one "
        "per stage, what each produces), '## Outputs', '## Quality gates' (what is checked and the pass criteria), "
        "'## Recovery' (checkpoints / resume / smoke), '## Transfer' (how to export and install on another Agent Hub "
        "and what it needs there). Be precise and faithful to the pipeline; do not invent features. The ONLY "
        f"command-line options are {', '.join(sorted(cli_flags(src / 'run.py')))}; profile fields are YAML keys "
        "(`featured:`) inside a profile file, not command-line options.\n\n"
        + _pipeline_context(src, Path(run_dir) if run_dir else None)), max_tokens=12000, temperature=0.2)
    real = cli_flags(src / "run.py")
    bad = unknown_flags(reply, real)
    for _ in range(3):  # self-check: the skill may only document options the entry really has
        if not bad:
            break
        reply = llm(AUTHOR_SYSTEM, (
            f"Your SKILL.md documents command-line options that run.py does not have: {', '.join(bad)}. The ONLY "
            f"command-line options are: {', '.join(sorted(real))}. Profile fields (e.g. featured, coi_statement, "
            "seed_pmids, focus_terms) are YAML keys inside a profile file, written like `featured:`. Rewrite every "
            "passage that mentions another double-dash option so that no other double-dash option appears anywhere "
            "(also not as a counter-example), and return the whole SKILL.md again, nothing else."
            f"\n\n{reply}"), max_tokens=12000, temperature=0.1)
        bad = unknown_flags(reply, real)
    if bad:
        raise AuthorCheckError(f"authored SKILL.md still documents non-existent options: {', '.join(bad)}", reply)
    reply = re.sub(r"^\s*```(?:markdown|md)?\s*\n|\n\s*```\s*$", "", reply.strip())  # a fenced whole reply
    meta, body = _frontmatter(reply)
    body = body.strip()
    if not body.lstrip().startswith("#"):
        raise ValueError("model reply is not a SKILL.md body")
    meta = {"name": skill_id, "description": (meta.get("description") or skills._parse_skill_md(src / "SKILL.md")
                                               .get("description") or skill_id)[:240],
            "triggers": meta.get("triggers") or "literature review, 综述", "entry": "run.py",
            "origin": "agent-hub-authored", "authored_by": model,
            "authored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    markdown = "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n" + body.strip() + "\n"
    tmp = Path(tempfile.mkdtemp(prefix="skill-author-")) / skill_id
    shutil.copytree(src, tmp, ignore=shutil.ignore_patterns(*_SKIP, "*.pyc"))
    (tmp / "SKILL.md").write_text(markdown, encoding="utf-8")
    result = skills.install_skill_dir(tmp, name=skill_id)
    shutil.rmtree(tmp.parent, ignore_errors=True)
    if load:
        skills.load_skill_to_hub(skill_id)
    audit.log_event("skill_authored", {"id": skill_id, "model": model, "path": result.get("path")})
    return {"ok": True, "id": skill_id, "path": result.get("path"), "markdown": markdown, "model": model,
            "entry": "run.py", "checked_flags": sorted(real)}

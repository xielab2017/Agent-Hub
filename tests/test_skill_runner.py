"""Runnable skills: argument parsing, background runs with live log lines, export → import, Hub authoring."""

from __future__ import annotations

import contextlib
import io
import json
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ali import skill_runner  # noqa: E402

TOY_ENTRY = '''
import argparse, json, pathlib, time
ap = argparse.ArgumentParser(); ap.add_argument("--out"); ap.add_argument("--topic", default=""); ap.add_argument("--smoke", action="store_true")
a = ap.parse_args()
print("[     0s] queries: 3", flush=True)
print("sk-" + "A" * 24, flush=True)  # a key-like string must be masked in the log
pathlib.Path(a.out, "review.docx").write_bytes(b"docx")
print("[     1s] citations: ok", flush=True)
print("RESULT: PASS " + json.dumps({"title": "T: " + a.topic, "sections": 2, "words": 10, "llm_calls": 3,
                                    "model": "stub", "citation_check": {"cited": 8}, "smoke": a.smoke}), flush=True)
'''


@contextlib.contextmanager
def hub(tmp: Path):
    """One isolated Hub: its own skills root, run dir, hub-loaded list and session store."""
    from ali import skills

    root = tmp / "skills"
    root.mkdir(parents=True, exist_ok=True)
    loaded: list[str] = []
    messages: list[tuple[str, dict]] = []
    with mock.patch.object(skills, "install_skills_root", lambda: root), \
            mock.patch.object(skills, "skill_dirs", lambda: [root]), \
            mock.patch.object(skills, "ensure_state_dirs", lambda: None), \
            mock.patch.object(skills, "get_hub_loaded", lambda: list(loaded)), \
            mock.patch.object(skills, "set_hub_loaded", lambda ids: loaded.__init__(ids) or {"ok": True}), \
            mock.patch.object(skill_runner, "RUNS_DIR", tmp / "runs"), \
            mock.patch("ali.sessions.append_messages", lambda sid, *m: messages.extend((sid, x) for x in m)), \
            mock.patch("ali.audit.log_event", lambda *a, **k: None):
        yield root, loaded, messages


def _toy_skill(root: Path, entry: str = "run.py") -> Path:
    d = root / "toy"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: toy\ndescription: toy skill\nentry: {entry}\n---\n\n# Toy\n")
    (d / "run.py").write_text(TOY_ENTRY)
    (d / "profiles").mkdir()
    (d / "profiles" / "a.yaml").write_text("topic: A\n")
    return d


def test_parse_args():
    assert skill_runner.parse_args("profile=multiomics-emp smoke") == ["--profile", "multiomics-emp", "--smoke"]
    assert skill_runner.parse_args("THBS4 in muscle ageing") == ["--topic", "THBS4 in muscle ageing"]
    assert skill_runner.parse_args("--profile thbs4 --fresh") == ["--profile", "thbs4", "--fresh"]
    assert skill_runner.parse_args('min_refs=45 "GDF15 in ageing"') == ["--min-refs", "45", "--topic", "GDF15 in ageing"]
    assert skill_runner.parse_args({"profile": "x", "smoke": True, "fresh": False}) == ["--profile", "x", "--smoke"]


def test_run_streams_lines_masks_keys_lists_outputs_and_records_in_session():
    with tempfile.TemporaryDirectory() as tmp, hub(Path(tmp)) as (root, _loaded, messages):
        _toy_skill(root)
        run = skill_runner.start_run("toy", "smoke GDF15 in ageing", session_id="s1", display="/skill toy smoke GDF15")
        assert run["status"] == "running" and run["args"] == ["--smoke", "--topic", "GDF15 in ageing"]
        for _ in range(100):
            info = skill_runner.get_run(run["id"])
            if info["status"] != "running":
                break
            time.sleep(0.05)
        assert info["status"] == "done", info
        assert info["summary"]["title"] == "T: GDF15 in ageing" and info["summary"]["smoke"] is True
        assert info["stage"] == "citations: ok"
        assert not any("A" * 20 in ln for ln in info["lines"])  # masked
        assert [o["name"] for o in info["outputs"]] == ["review.docx"]
        assert skill_runner.get_run(run["id"], since=2)["lines"][0] == "[     1s] citations: ok"
        assert skill_runner.run_file(run["id"], "review.docx").read_bytes() == b"docx"
        with pytest.raises(FileNotFoundError):
            skill_runner.run_file(run["id"], "../run.json")
        roles = [m["role"] for _sid, m in messages]
        assert roles == ["user", "assistant"] and "/api/skill-runs/" in messages[1][1]["content"]
        assert skill_runner.list_runs()[0]["id"] == run["id"]


def test_explicit_out_replaces_the_default_output_dir():
    with tempfile.TemporaryDirectory() as tmp, hub(Path(tmp)) as (root, _l, _m):
        _toy_skill(root)
        target = Path(tmp) / "mine"
        run = skill_runner.start_run("toy", f"out={target} topic=X")
        assert run["out"] == str(target) and "--out" not in run["args"]
        for _ in range(100):
            if skill_runner.get_run(run["id"])["status"] != "running":
                break
            time.sleep(0.05)
        assert (target / "review.docx").exists()


def test_entry_must_be_a_python_file_inside_the_skill():
    with tempfile.TemporaryDirectory() as tmp, hub(Path(tmp)) as (root, _l, _m):
        _toy_skill(root, entry="../outside.py")
        with pytest.raises(ValueError):
            skill_runner.skill_entry("toy")
        with pytest.raises(FileNotFoundError):
            skill_runner.skill_entry("missing")


def test_export_then_install_on_another_hub():
    from ali import skills

    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        with hub(Path(a)) as (root_a, _l, _m):
            d = _toy_skill(root_a)
            (d / "__pycache__").mkdir()
            (d / "__pycache__" / "x.pyc").write_bytes(b"x")
            data = skill_runner.export_skill_zip("toy")
        names = zipfile.ZipFile(io.BytesIO(data)).namelist()
        assert sorted(names) == ["toy/SKILL.md", "toy/profiles/a.yaml", "toy/run.py"]
        with hub(Path(b)) as (root_b, _l, _m):
            z = Path(b) / "toy.zip"
            z.write_bytes(data)
            res = skills.install_skill_zip(z)
            assert res["id"] == "toy"
            _root, script = skill_runner.skill_entry("toy")  # runnable on the receiving Hub
            assert script == (root_b / "toy" / "run.py").resolve()


def test_author_skill_installs_model_written_skill_md_with_the_package():
    class Llm:
        provider, model = "stub", "stub-model"

        def __init__(self):
            self.prompts = []

        def __call__(self, system, user, **kw):
            self.prompts.append(user)
            return ("```markdown\n---\nname: literature-review\ndescription: Write reviews.\ntriggers: review, 综述\n"
                    "entry: evil.py\n---\n\n# Literature review\n\n## When to use\nAlways.\n```")

    with tempfile.TemporaryDirectory() as tmp, hub(Path(tmp)) as (root, loaded, _m):
        src = Path(tmp) / "src" / "literature-review"
        src.mkdir(parents=True)
        (src / "run.py").write_text("print('x')\n")
        (src / "SKILL.md").write_text("---\nname: literature-review\ndescription: base\n---\n# base\n")
        (src / "profiles").mkdir()
        (src / "profiles" / "p.yaml").write_text("topic: P\n")
        run_dir = Path(tmp) / "run"
        run_dir.mkdir()
        (run_dir / "summary.json").write_text(json.dumps({"references": 59}))
        llm = Llm()
        res = skill_runner.author_skill("literature-review", source=src, run_dir=run_dir, llm=llm)
        md = (root / "literature-review" / "SKILL.md").read_text()
        assert "entry: run.py" in md and "evil.py" not in md  # the entry is fixed by the Hub, not the model
        assert "origin: agent-hub-authored" in md and "authored_by: stub/stub-model" in md
        assert "# Literature review" in md and "```" not in md
        assert (root / "literature-review" / "profiles" / "p.yaml").exists()
        assert loaded == ["literature-review"] and res["model"] == "stub/stub-model"
        assert '"references": 59' in llm.prompts[0] and "BUNDLED PROFILES: p" in llm.prompts[0]


def test_bundled_literature_review_skill_cli():
    skill = ROOT / "skills" / "literature-review"
    out = subprocess.run([sys.executable, str(skill / "run.py"), "--help"], capture_output=True, text=True,
                         env={"PYTHONPATH": str(ROOT)}, timeout=60)
    assert out.returncode == 0 and "--profile" in out.stdout
    sys.path.insert(0, str(skill))
    import run as entry  # noqa: E402

    assert entry.find_profile("multiomics-emp").name == "multiomics-emp.yaml"
    prof = entry.read_profile(entry.find_profile("multiomics-emp"))
    assert prof["featured"]["pmid"] == "40932530" and prof["plan"] is False
    assert len(prof["reviewers"]) == 3 and len(prof["table"]["columns"]) == 3

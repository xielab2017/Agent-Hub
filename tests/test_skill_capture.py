"""Tests for saving a session as a reusable skill and re-activating it."""

from __future__ import annotations

import contextlib
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@contextlib.contextmanager
def sandbox():
    """Temp sessions dir, provenance dir, skills root and hub-loaded list."""
    from ali import provenance, skills
    from ali import sessions as store

    loaded: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        (tmp_p / "sessions").mkdir()
        (tmp_p / "skills").mkdir()
        with mock.patch.object(store, "SESSIONS_DIR", tmp_p / "sessions"), \
                mock.patch.object(store, "ensure_state_dirs", lambda: None), \
                mock.patch.object(provenance, "PROV_DIR", tmp_p / "prov"), \
                mock.patch.object(skills, "install_skills_root", lambda: tmp_p / "skills"), \
                mock.patch.object(skills, "ensure_state_dirs", lambda: None), \
                mock.patch.object(skills, "get_hub_loaded", lambda: list(loaded)), \
                mock.patch.object(skills, "set_hub_loaded", lambda ids: loaded.__init__(ids) or {"ok": True}), \
                mock.patch("ali.audit.log_event", lambda *a, **k: None):
            yield tmp_p, loaded


def _session_with_reply():
    from ali import provenance
    from ali import sessions as store

    s = store.create_session(title="scRNA QC")
    store.append_messages(
        s.id,
        {"role": "user", "content": "帮我整理一份关于单细胞 RNA-seq 质控步骤的清单"},
        {"id": "a1", "role": "assistant",
         "content": "## 概览\n质控要点。\n## 步骤\n1. 过滤低质量细胞\n```python\n# not a heading\n```\n## 参考\n- [1]",
         "route": {"tier": "C2", "route_key": "office", "execution_mode": "workflow", "skills": ["scanpy-qc"]},
         "review": {"ok": True, "skipped": False, "warn": 0, "info": 1}},
    )
    rec = provenance.build_record(
        session_id=s.id, message_id="a1", user_message="q", final_text="a",
        route_info={"tier": "C2", "route_key": "office", "skills": ["scanpy-qc"], "execution_mode": "workflow",
                    "_search": {"query": "scRNA-seq QC", "engines": ["europepmc"], "sources": [{"n": 1, "url": "https://x"}]}},
        tools=[{"name": "web_search", "preview": "scRNA-seq QC"}],
    )
    provenance.save_record(rec)
    return s.id, rec


def test_extract_triggers_mixes_english_genes_and_chinese_segments():
    from ali.skill_capture import extract_triggers

    trig = extract_triggers("帮我整理一份关于单细胞 RNA-seq 质控步骤的清单，重点看 TP53")
    assert "RNA-seq" in trig and "TP53" in trig and "单细胞" in trig
    assert "帮我" not in trig and "关于" not in trig
    trig2 = extract_triggers("总结 TP53 突变频率 doi:10.1038/nature12373 https://example.org/x 是多少")
    assert trig2 == ["TP53", "突变频率"]


def test_draft_contains_steps_output_format_and_provenance():
    from ali.skill_capture import ORIGIN, draft_from_session

    with sandbox():
        sid, rec = _session_with_reply()
        d = draft_from_session(sid)
    md = d["markdown"]
    assert md.startswith("---\nname: ")
    assert f"origin: {ORIGIN}" in md and "triggers: " in md
    assert "on route **C2·office**" in md
    assert "`scanpy-qc`" in md
    assert "engines: europepmc" in md and "Cite every claim inline as [n]" in md
    assert "Tool `web_search`" in md
    assert "- 概览" in md and "- 步骤" in md and "not a heading" not in md
    assert rec["integrity"]["record_sha256"] in md
    assert d["source"] == {"session_id": sid, "message_id": "a1"}
    assert d["slug"] and d["slug"] == d["slug"].lower()


def test_draft_errors():
    import pytest
    from ali import sessions as store
    from ali.skill_capture import draft_from_session

    with sandbox():
        with pytest.raises(FileNotFoundError):
            draft_from_session("nope")
        s = store.create_session(title="empty")
        with pytest.raises(ValueError):
            draft_from_session(s.id)
        sid, _ = _session_with_reply()
        with pytest.raises(FileNotFoundError):
            draft_from_session(sid, "missing-id")


def test_save_never_overwrites_and_loads_into_hub():
    from ali.skill_capture import draft_from_session, save_skill

    with sandbox() as (tmp, loaded):
        sid, _ = _session_with_reply()
        d = draft_from_session(sid, name="scRNA QC checklist")
        a = save_skill(d["slug"], d["markdown"])
        b = save_skill(d["slug"], d["markdown"] + "\nv2")
        assert a["id"] == "scrna-qc-checklist" and b["id"] == "scrna-qc-checklist-2" and b["renamed"]
        assert (tmp / "skills" / a["id"] / "SKILL.md").read_text(encoding="utf-8").strip() == d["markdown"].strip()
        assert "v2" in (tmp / "skills" / b["id"] / "SKILL.md").read_text(encoding="utf-8")
        assert loaded == ["scrna-qc-checklist", "scrna-qc-checklist-2"]
        c = save_skill("../../etc", "no front matter", load=False)
        assert c["id"] == "etc" and (tmp / "skills" / "etc" / "SKILL.md").read_text(encoding="utf-8").startswith("---")
        assert "etc" not in loaded


def test_captured_skill_matches_future_requests_and_injects_steps():
    from ali import skill_capture

    with sandbox():
        sid, _ = _session_with_reply()
        d = skill_capture.draft_from_session(sid, name="scRNA QC checklist")
        saved = skill_capture.save_skill(d["slug"], d["markdown"])
        assert skill_capture.match_captured("新的数据：单细胞 RNA-seq 质控怎么做？") == [saved["id"]]
        assert skill_capture.match_captured("帮我写一封邮件") == []
        block = skill_capture.context_block([saved["id"]])
        assert block.startswith("## Captured workflow skills") and "## Steps" in block and "origin:" not in block
        # unloading stops auto-activation
        from ali import skills

        with mock.patch.object(skills, "get_hub_loaded", lambda: []):
            assert skill_capture.match_captured("单细胞 RNA-seq 质控") == []

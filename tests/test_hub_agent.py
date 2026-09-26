"""Hub agent: any configured model decides from context which tools / skills to use."""

from __future__ import annotations

import json
import queue
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from ali import hub_agent  # noqa: E402


def scripted(*replies):
    """A fake model that returns the given replies in order and records what it was sent."""
    seen = []
    it = iter(replies)

    def llm(convo):
        seen.append([dict(m) for m in convo])
        return next(it)

    llm.seen = seen
    return llm


def test_parse_action_variants():
    assert hub_agent.parse_action('{"tool": "web_search", "args": {"query": "x"}, "why": "facts"}')["tool"] == "web_search"
    assert hub_agent.parse_action('```json\n{"tool": "read_url", "args": {"url": "https://a"}}\n```')["args"] == {"url": "https://a"}
    assert hub_agent.parse_action('{"tool": "final", "answer": "done"}') == {"tool": "final", "answer": "done"}
    assert hub_agent.parse_action("Here is the answer: {not json}") is None
    assert hub_agent.parse_action("THBS4 is a matricellular protein.") is None
    assert hub_agent.parse_action('{"result": 3}') is None  # JSON that is not a tool request is an answer


def test_multi_step_tool_use_then_answer(monkeypatch):
    from ali import review_writer as rw

    monkeypatch.setattr(rw, "pubmed_search", lambda q, retmax=8: ["111", "222"])
    monkeypatch.setattr(rw, "pubmed_fetch", lambda pmids: [
        {"pmid": p, "title": f"Paper {p}", "journal": "J", "year": "2024", "doi": "", "abstract": "THBS4 finding"}
        for p in pmids])
    llm = scripted('{"tool": "pubmed_search", "args": {"query": "THBS4 muscle"}, "why": "find papers"}',
                   "Two papers were found [PMID 111, 222].")
    steps = []
    res = hub_agent.run(llm, [{"role": "user", "content": "THBS4 在肌肉里有什么研究？"}], hub_agent.Tools(),
                        on_step=lambda k, d: steps.append((k, d["name"])))
    assert res["answer"].startswith("Two papers") and res["steps"][0]["tool"] == "pubmed_search"
    assert steps == [("tool", "pubmed_search"), ("result", "pubmed_search")]
    assert len(res["sources"]) == 2 and res["sources"][0]["url"].endswith("/111/")
    last = llm.seen[1][-1]["content"]
    assert last.startswith("TOOL RESULT (pubmed_search)") and "Paper 111" in last


def test_unknown_tool_and_errors_are_returned_to_the_model():
    llm = scripted('{"tool": "rm_rf", "args": {}}', '{"tool": "read_file", "args": {"path": "../../etc/passwd"}}',
                   "I cannot do that.")
    with tempfile.TemporaryDirectory() as ws:
        res = hub_agent.run(llm, [{"role": "user", "content": "x"}], hub_agent.Tools(workspace=ws))
    assert res["answer"] == "I cannot do that."
    assert "unknown tool" in res["steps"][0]["error"] and "outside the Hub workspace" in res["steps"][1]["error"]


def test_workspace_files_are_listed_and_read():
    with tempfile.TemporaryDirectory() as ws:
        (Path(ws) / "notes.md").write_text("# Plan\nRun the THBS4 review.\n")
        (Path(ws) / "data.bin").write_bytes(b"\x00\x01")
        tools = hub_agent.Tools(workspace=ws)
        assert {i["name"] for i in tools.call("list_files", {})["items"]} == {"notes.md", "data.bin"}
        assert "THBS4 review" in tools.call("read_file", {"path": "notes.md"})["text"]
        assert "only text files" in tools.call("read_file", {"path": "data.bin"})["error"]


def test_step_budget_forces_a_final_answer():
    llm = scripted(*(['{"tool": "list_skills", "args": {}}'] * 3 + ["Final after budget."]))
    with mock.patch("ali.skills.list_skills", lambda: {"skills": []}):
        res = hub_agent.run(llm, [{"role": "user", "content": "x"}], hub_agent.Tools(), max_steps=3)
    assert res["answer"] == "Final after budget." and len(res["steps"]) == 3


def test_review_request_starts_the_literature_review_skill():
    """'写一篇综述' → the model calls run_skill; the run starts and the UI is told (skill_run event)."""
    import test_skill_runner as tsr
    from ali import skill_runner

    with tempfile.TemporaryDirectory() as tmp, tsr.hub(Path(tmp)) as (root, _loaded, messages):
        tsr._toy_skill(root)
        started = []
        llm = scripted('{"tool": "list_skills", "args": {}, "why": "find a pipeline"}',
                       '{"tool": "run_skill", "args": {"skill": "toy", "topic": "GDF15 in ageing", "smoke": true}}',
                       "已启动综述 Skill，完成后会在进度卡片里给出 Word 下载。")
        tools = hub_agent.Tools(session_id="s9", on_skill_run=started.append)
        res = hub_agent.run(llm, [{"role": "user", "content": "帮我写一篇 GDF15 与衰老的综述"}], tools)
        assert res["answer"].startswith("已启动") and started and started[0]["skill"] == "toy"
        assert started[0]["args"] == ["--topic", "GDF15 in ageing", "--smoke"]
        listed = json.loads(llm.seen[1][-1]["content"].split("\n")[1])
        assert listed["skills"][0]["id"] == "toy"
        for _ in range(100):
            if skill_runner.get_run(started[0]["run_id"])["status"] != "running":
                break
            time.sleep(0.05)
        assert skill_runner.get_run(started[0]["run_id"])["status"] == "done"
        roles = [m["role"] for _sid, m in messages]
        assert roles == ["assistant"]  # no duplicate "/skill" user line: the agent's reply announces it


def test_hub_agent_reply_streams_answer_and_tool_events(monkeypatch):
    from ali import streaming

    q: queue.Queue = queue.Queue()
    replies = iter(['{"tool": "web_search", "args": {"query": "MiniMax M3"}, "why": "current facts"}',
                    "MiniMax-M3 is MiniMax's current flagship model."])
    monkeypatch.setattr("ali.llm_client.stream_chat", lambda *a, **k: next(replies))
    monkeypatch.setattr("ali.websearch.search_web", lambda q, limit=6, deep=False: {"results": [
        {"title": "MiniMax M3", "url": "https://example.org/m3", "snippet": "flagship"}]})
    monkeypatch.setattr("ali.providers.connection_base_url", lambda cfg, pid: "https://api.example/v1")
    monkeypatch.setattr("ali.secrets.resolve_api_key", lambda cfg, provider="": {"key": "sk-test", "present": True})
    monkeypatch.setattr(streaming.store, "get_session", lambda sid: None)
    parts: list[str] = []
    route = {"provider": "deepseek", "model": "deepseek-chat", "base_url": "https://api.example/v1",
             "route_key": "office"}
    ok = streaming._hub_agent_reply(q, "s1", "MiniMax M3 是什么？", "", parts, route_info=route, preamble="ctx")
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    names = [e[0] if isinstance(e, tuple) else e.get("event") for e in events]
    assert ok and "".join(parts).startswith("MiniMax-M3 is")
    assert route["agent_steps"][0]["tool"] == "web_search" and route["agent_sources"][0]["url"] == "https://example.org/m3"
    assert names.count("token") >= 1 and "tool" in names


def test_engine_selection_uses_hub_agent_for_plain_models():
    from ali.streaming import _chat_engine_for_runtime as pick

    assert pick("agent", "direct", hub_agent=True) == "hub-agent"
    assert pick("agent", "auto", hub_agent=True) == "hub-agent"
    assert pick("agent", "direct", hub_agent=False) == "direct"
    assert pick("direct", "direct", hub_agent=True) == "direct"  # 快聊 stays a plain reply
    assert pick("agent", "direct", simple_chat=True, hub_agent=True) == "direct"  # greetings stay fast
    assert pick("agent", "hermes", hub_agent=True) == "hermes"
    assert pick("agent", "claude-code", hub_agent=True) == "claude-code"


def test_tool_json_after_prose_is_still_a_tool_request():
    """MiniMax-M3 (CI run 36208901199): '我先列出工作区文件…{"tool": "list_files", …}' was shown as the answer."""
    act = hub_agent.parse_action('我先列出工作区文件，再读取 `notes.md` 的内容。{"tool": "list_files", "args": {"path": "."}, '
                                 '"why": "列出工作区当前文件"}')
    assert act["tool"] == "list_files" and act["args"] == {"path": "."}
    fenced = 'Let me check.\n```json\n{"tool": "read_file", "args": {"path": "notes.md"}}\n```'
    assert hub_agent.parse_action(fenced)["tool"] == "read_file"
    assert hub_agent.parse_action('Use {"tool": "rm_rf"} carefully.') is None  # unknown tool inside prose: an answer


def test_claimed_action_without_a_tool_call_gets_one_nudge():
    """MiniMax-M3 answered '技能已启动…' without calling run_skill; the loop must make it actually call the tool."""
    llm = scripted("好的！我来为你启动 literature-review skill（smoke=true）。技能已启动，预计 2–5 分钟完成。",
                   '{"tool": "list_files", "args": {}}', "工作区里有 notes.md。")
    with tempfile.TemporaryDirectory() as ws:
        (Path(ws) / "notes.md").write_text("x")
        res = hub_agent.run(llm, [{"role": "user", "content": "x"}], hub_agent.Tools(workspace=ws))
    assert [s["tool"] for s in res["steps"]] == ["list_files"] and res["answer"] == "工作区里有 notes.md。"
    assert "No tool has run yet" in llm.seen[1][-1]["content"]
    plain = scripted("THBS4 is a matricellular protein.")
    assert hub_agent.run(plain, [{"role": "user", "content": "x"}], hub_agent.Tools())["answer"].startswith("THBS4")
    assert len(plain.seen) == 1  # an ordinary answer is not nudged
    twice = scripted("我先列出文件。", "我先列出文件。")
    assert hub_agent.run(twice, [{"role": "user", "content": "x"}], hub_agent.Tools())["answer"] == "我先列出文件。"


def test_run_skill_accepts_loose_ids_and_argument_shapes():
    """MiniMax-M3 (CI run 36209115132) called run_skill twice and no run started: accept the shapes models use."""
    import test_skill_runner as tsr

    with tempfile.TemporaryDirectory() as tmp, tsr.hub(Path(tmp)) as (root, _loaded, _messages):
        tsr._toy_skill(root)
        tools = hub_agent.Tools(session_id="s9")
        assert "toy" in hub_agent.skills_line(tools)
        r = tools.call("run_skill", {"skill": "Toy", "args": {"topic": "GDF15 in ageing", "smoke": "true"}})
        assert r.get("run_id") and r["skill"] == "toy" and r["args"] == ["--topic", "GDF15 in ageing", "--smoke"]
        r = hub_agent.Tools().call("run_skill", {"skill": "toy_skill", "query": "GDF15", "smoke": "false"})
        assert r.get("run_id") and "--smoke" not in r["args"]
        bad = hub_agent.Tools().call("run_skill", {"skill": "grant-writer", "topic": "x"})
        assert "no runnable skill" in bad["error"] and "toy" in bad["error"]


def test_saved_profile_is_used_only_for_its_own_topic():
    """MiniMax-M3 (CI run 36209331150) attached the multi-omics profile to a GDF15 review."""
    topics = hub_agent._profile_topics(ROOT / "skills" / "literature-review" / "profiles")
    assert "EasyMultiProfiler" in topics["multiomics-emp"] and "THBS4" in topics["thbs4"]
    assert not hub_agent.topics_overlap("GDF15 in ageing and metabolism", topics["thbs4"])
    assert not hub_agent.topics_overlap("GDF15 in aging and metabolic regulation", topics["multiomics-emp"])
    assert hub_agent.topics_overlap("THBS4 in muscle ageing", topics["thbs4"])
    assert hub_agent.topics_overlap("multi-omics analysis software", topics["multiomics-emp"])
    import test_skill_runner as tsr

    with tempfile.TemporaryDirectory() as tmp, tsr.hub(Path(tmp)) as (root, _loaded, _messages):
        prof = tsr._toy_skill(root) / "profiles"
        (prof / "omics.yaml").write_text("topic: Multi-omics software with EasyMultiProfiler\\nplan: false\\n")
        r = hub_agent.Tools().call("run_skill", {"skill": "toy", "topic": "GDF15 in ageing", "profile": "omics"})
        assert "--profile" not in r["args"] and "not used" in r["note"]
        r = hub_agent.Tools().call("run_skill", {"skill": "toy", "topic": "EasyMultiProfiler review", "profile": "omics"})
        assert "--profile" in r["args"]


def test_a_literature_question_does_not_start_a_skill():
    """MiniMax-M3 (CI run 36209611472) answered 'THBS4 … 有哪些研究证据？请查一下文献' by starting a full review."""
    assert not hub_agent.wants_deliverable("THBS4 在骨骼肌衰老中有哪些研究证据？请查一下文献，简要总结并给出 PMID。")
    assert not hub_agent.wants_deliverable("工作区里有哪些文件？读一下 notes.md 并告诉我下一步该做什么。")
    assert hub_agent.wants_deliverable("帮我写一篇关于 GDF15 与衰老和代谢的英文综述，先小规模试跑一下看看效果。")
    assert hub_agent.wants_deliverable("Please draft a review on GDF15 and ageing")
    r = hub_agent.Tools(question="THBS4 有哪些研究证据？").call("run_skill", {"skill": "literature-review", "topic": "THBS4"})
    assert "not for a pipeline run" in r["error"] and "pubmed_search" in r["error"]


def test_one_skill_run_per_turn_and_trial_from_the_users_words():
    """CI run 36209611472: run_skill was called three times and the user's '先小规模试跑' was dropped."""
    import test_skill_runner as tsr

    with tempfile.TemporaryDirectory() as tmp, tsr.hub(Path(tmp)) as (root, _loaded, _messages):
        tsr._toy_skill(root)
        call = '{"tool": "run_skill", "args": {"skill": "toy", "topic": "GDF15 in ageing"}}'
        llm = scripted(call, call, "已启动。")
        res = hub_agent.run(llm, [{"role": "user", "content": "x"}],
                            hub_agent.Tools(question="帮我写一篇 GDF15 综述，先小规模试跑一下"))
        assert len(res["skill_runs"]) == 1 and "--smoke" in res["skill_runs"][0]["args"]
        assert "already started" in res["steps"][1]["error"]


def test_stop_skill_stops_this_chats_run_only_when_asked():
    import test_skill_runner as tsr
    from ali import skill_runner

    with tempfile.TemporaryDirectory() as tmp, tsr.hub(Path(tmp)) as (root, _loaded, _messages):
        (tsr._toy_skill(root) / "run.py").write_text(tsr.SLOW_ENTRY)
        run = skill_runner.start_run("toy", "GDF15", session_id="s7")
        refused = hub_agent.Tools(session_id="s7", question="进度怎么样？").call("stop_skill", {})
        assert "did not ask to stop" in refused["error"] and skill_runner.get_run(run["id"])["status"] == "running"
        assert "no running" in hub_agent.Tools(session_id="other", question="停止").call("stop_skill", {})["error"]
        r = hub_agent.Tools(session_id="s7", question="停止刚才的综述").call("stop_skill", {})
        assert r["id"] == run["id"]
        assert tsr._wait(run["id"])["status"] == "stopped"

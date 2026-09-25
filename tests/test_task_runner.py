"""Tests for multi-step tasks (plan → run step → gate → next step) and steer carry-over."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent


@contextlib.contextmanager
def sandbox():
    from ali import sessions as store
    from ali import task_runner

    with tempfile.TemporaryDirectory() as tmp:
        tmp_p = Path(tmp)
        (tmp_p / "sessions").mkdir()
        with mock.patch.object(store, "SESSIONS_DIR", tmp_p / "sessions"), \
                mock.patch.object(store, "ensure_state_dirs", lambda: None), \
                mock.patch.object(task_runner, "TASKS_DIR", tmp_p / "tasks"), \
                mock.patch("ali.audit.log_event", lambda *a, **k: None):
            yield store


def _reply(store, sid, content, review=None, error=False):
    msg = {"role": "assistant", "content": content, "review": review or {"ok": True, "warn": 0, "info": 0}}
    if error:
        msg["error"] = True
    s = store.append_messages(sid, {"role": "user", "content": "step"}, msg)
    return s.messages[-1]["id"]


# ── planning ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,source,titles", [
    ("调研 TP53 突变：1. 检索最新文献 2. 核对突变频率数据 3. 写一份总结报告", "numbered",
     ["检索最新文献", "核对突变频率数据", "写一份总结报告"]),
    ("做质控：第一步整理样本信息，第二步计算QC指标，第三步给出过滤阈值", "ordinal",
     ["整理样本信息", "计算QC指标", "给出过滤阈值", "汇总与下一步"]),
    ("首先查一下 PD-L1 抑制剂的临床试验，然后比较疗效数据，最后给出结论", "sequence",
     ["查一下 PD-L1 抑制剂的临床试验", "比较疗效数据", "给出结论"]),
    ("1) 读数据\n2) 画图\n3) 写报告", "numbered", ["读数据", "画图", "写报告"]),
    ("分析 2024 年新能源汽车销量趋势", "research-template", ["检索资料", "核对数据", "整理总结", "下一步建议"]),
    ("写一封给合作方的邀请邮件", "general-template", ["明确需求与方案", "执行并产出初稿", "自查与完善", "交付与下一步"]),
])
def test_plan_steps(text, source, titles):
    from ali.task_runner import plan_steps

    plan = plan_steps(text)
    assert plan["source"] == source
    assert [s["title"] for s in plan["steps"]] == titles


def test_plan_details_goal_search_flags_and_limits():
    from ali.task_runner import MAX_STEPS, plan_steps

    p = plan_steps("调研 TP53 突变：1. 检索最新文献 2. 核对数据")
    assert p["goal"] == "调研 TP53 突变"
    assert [s["web_search"] for s in p["steps"]] == [True, False, False]
    assert plan_steps("Python 3.5 和 3.6 的区别")["source"] == "general-template"  # decimals aren't steps
    many = " ".join(f"{i}. 做第{i}件事" for i in range(1, 13))
    assert len(plan_steps(many)["steps"]) == MAX_STEPS
    given = plan_steps("x", steps=["a", "b"])
    assert given["source"] == "given" and [s["title"] for s in given["steps"]] == ["a", "b", "汇总与下一步"]


def test_summarize_reply_sections():
    from ali.task_runner import summarize_reply

    md = "正文\n## 本步结论\n- A 为 50% [1]\n- B\n## 待解决\n- 缺少 2024 数据\n"
    out = summarize_reply(md)
    assert out["summary"] == "- A 为 50% [1]\n- B" and out["open_issues"] == "- 缺少 2024 数据"
    assert summarize_reply("## 标题\n纯文本 **加粗**")["summary"] == "标题 纯文本 加粗"


# ── lifecycle ──────────────────────────────────────────────────────────


def test_auto_task_runs_steps_in_order_and_carries_context():
    from ali import task_runner

    with sandbox() as store:
        sid = store.create_session(title="t").id
        res = task_runner.create_task(sid, "调研 TP53：1. 检索文献 2. 核对数据 3. 写总结")
        task = res["task"]
        assert res["next"]["step"] == 1 and res["next"]["total"] == 3
        assert "【当前步骤 1/3】检索文献" in res["next"]["prompt"] and res["next"]["web_search"] is True
        assert task["steps"][0]["status"] == "running"

        m1 = _reply(store, sid, "## 本步结论\n- TP53 突变约 50% [1]\n## 待解决\n- 缺中国人群数据")
        r2 = task_runner.advance(task["id"], message_id=m1)
        assert r2["status"] == "next" and r2["step"] == 2
        assert "TP53 突变约 50% [1]" in r2["prompt"] and "【上一步待解决】- 缺中国人群数据" in r2["prompt"]
        assert r2["display"].startswith("▶ 步骤 2/3：核对数据")

        # a duplicate advance for the same finished step must not skip ahead
        m2 = _reply(store, sid, "## 本步结论\n- 数据一致")
        r3 = task_runner.advance(task["id"], message_id=m2)
        assert r3["step"] == 3
        m3 = _reply(store, sid, "最终总结")
        done = task_runner.advance(task["id"], message_id=m3)
        assert done["status"] == "done" and done["task"]["done_steps"] == 3
        assert task_runner.advance(task["id"])["status"] == "done"
        assert task_runner.active_for_session(sid) is None


def test_review_warnings_block_auto_until_forced():
    from ali import task_runner

    with sandbox() as store:
        sid = store.create_session(title="t").id
        task = task_runner.create_task(sid, "1. a 2. b")["task"]
        bad = {"ok": False, "warn": 2, "info": 0, "issues": [
            {"kind": "untraceable_number", "severity": "warn", "text": "63%"},
            {"kind": "unlisted_url", "severity": "info", "text": "x"}]}
        m1 = _reply(store, sid, "结论 63%", review=bad)
        r = task_runner.advance(task["id"], message_id=m1)
        assert r["status"] == "blocked" and r["reason"] == "review" and r["issues"] == ["untraceable_number: 63%"]
        assert task_runner.get_task(task["id"])["status"] == "blocked"
        assert task_runner.active_for_session(sid)["id"] == task["id"]
        forced = task_runner.advance(task["id"], force=True)
        assert forced["status"] == "next" and forced["step"] == 2


def test_confirm_mode_waits_after_each_step():
    from ali import task_runner

    with sandbox() as store:
        sid = store.create_session(title="t").id
        task = task_runner.create_task(sid, "1. a 2. b", mode="confirm")["task"]
        m1 = _reply(store, sid, "ok")
        w = task_runner.advance(task["id"], message_id=m1)
        assert w["status"] == "waiting" and w["upcoming"].startswith("▶ 步骤 2/3")
        assert task_runner.advance(task["id"], force=True)["step"] == 2
        task_runner.set_mode(task["id"], "auto")
        with pytest.raises(ValueError):
            task_runner.set_mode(task["id"], "nope")


def test_error_reply_blocks_and_stop_skips_rest():
    from ali import task_runner

    with sandbox() as store:
        sid = store.create_session(title="t").id
        task = task_runner.create_task(sid, "1. a 2. b 3. c")["task"]
        m1 = _reply(store, sid, "**Error:** boom", error=True)
        first = task_runner.advance(task["id"], message_id=m1)
        assert (first["status"], first["reason"]) == ("blocked", "error")
        again = task_runner.advance(task["id"])
        assert (again["status"], again["reason"]) == ("blocked", "error")  # stays blocked until forced or stopped
        st = task_runner.stop(task["id"])
        assert st["status"] == "stopped"
        assert [s["status"] for s in st["task"]["steps"]] == ["blocked", "skipped", "skipped", "skipped"]
        assert task_runner.advance(task["id"])["status"] == "stopped"


def test_errors_for_unknown_ids():
    from ali import task_runner

    with sandbox() as store:
        with pytest.raises(FileNotFoundError):
            task_runner.create_task("nope", "x")
        sid = store.create_session(title="t").id
        with pytest.raises(ValueError):
            task_runner.create_task(sid, "  ")
        with pytest.raises(FileNotFoundError):
            task_runner.advance("task-missing")
        t = task_runner.create_task(sid, "1. a 2. b")["task"]
        with pytest.raises(FileNotFoundError):
            task_runner.advance(t["id"], message_id="no-such-message")


def test_running_step_without_reply_does_not_advance():
    from ali import task_runner

    with sandbox() as store:
        sid = store.create_session(title="t").id
        t = task_runner.create_task(sid, "1. a 2. b")["task"]
        # a run for this step is in flight: nothing to do yet
        with mock.patch.object(task_runner, "_live_run", return_value=True):
            assert task_runner.advance(t["id"])["status"] == "running"
        # no run (page reload / gateway restart): the same step is handed out again, not skipped
        again = task_runner.advance(t["id"])
        assert again["status"] == "next" and again["resumed"] and again["step"] == 1 and "a" in again["prompt"]
        skipped = task_runner.advance(t["id"], force=True)
        assert skipped["step"] == 2 and skipped["task"]["steps"][0]["status"] == "skipped"


# ── steer carry-over ───────────────────────────────────────────────────


def test_steer_typed_during_run_is_carried_to_next_turn():
    from ali import pending_intent, streaming

    sid = "sess-steer"
    pending_intent._PENDING[sid] = {"steer": "只看 2023 年以后的数据"}
    with mock.patch.object(streaming, "inject_steer", lambda *a, **k: None):
        streaming.drain_queued_after_done(sid)
    assert pending_intent.take_carried(sid) == "- 只看 2023 年以后的数据"
    assert pending_intent.take_carried(sid) == ""


# ── end to end (real chat pipeline, isolated state) ────────────────────

E2E = r"""
import json, sys, time
sys.path.insert(0, sys.argv[1])
from ali import sessions as store, streaming, task_runner, pending_intent

real_direct = streaming._direct_llm_reply

def fake_direct(q, session_id, msg_text, model, parts, *, route_info=None, preamble=""):
    # stands in for a configured model (no network in tests)
    text = "## 本步结论\n- 完成：" + msg_text.splitlines()[1][:40]
    parts.append(text)
    streaming._put(q, "token", {"text": text})
    return True

streaming._direct_llm_reply = fake_direct

def run_step(sid, nxt):
    before = len([m for m in store.get_session(sid).messages if m.get("role") == "assistant"])
    streaming.start_chat(sid, nxt["prompt"], display_message=nxt["display"], task_id=tid,
                         task_step=nxt["step"], web_search=False)
    deadline = time.time() + 60
    while time.time() < deadline:
        msgs = [m for m in store.get_session(sid).messages if m.get("role") == "assistant"]
        if len(msgs) > before:
            return msgs[-1]
        time.sleep(0.1)
    raise SystemExit("step timed out")

s = store.create_session(title="task e2e")
res = task_runner.create_task(s.id, "整理报告：1. 列出要点 2. 写成段落 3. 给出标题")
tid = res["task"]["id"]
nxt = res["next"]
seen = []
while True:
    if nxt["step"] == 2:
        pending_intent.carry_steer(s.id, "用英文写")  # user typed guidance mid-task
    msg = run_step(s.id, nxt)
    seen.append({"step": nxt["step"], "has_review": bool(msg.get("review")), "has_prov": bool(msg.get("provenance")),
                 "task_route": (msg.get("route") or {}).get("task_id"), "steer": (msg.get("route") or {}).get("steer_applied")})
    out = task_runner.advance(tid, message_id=msg["id"])
    if out["status"] != "next":
        break
    nxt = out
users = [m.get("content") for m in store.get_session(s.id).messages if m.get("role") == "user"]

# Without a model the Hub can only show its demo notice: the task must stop, not "finish".
streaming._direct_llm_reply = real_direct
s2 = store.create_session(title="task demo")
res2 = task_runner.create_task(s2.id, "整理报告：1. 列出要点 2. 写成段落")
tid = res2["task"]["id"]
demo_msg = run_step(s2.id, res2["next"])
demo = task_runner.advance(tid, message_id=demo_msg["id"])
print(json.dumps({"final": out["status"], "seen": seen, "users": users,
                  "done_steps": out["task"]["done_steps"], "total": len(out["task"]["steps"]),
                  "demo_flag": demo_msg.get("demo"), "demo_status": demo["status"], "demo_reason": demo.get("reason")},
                 ensure_ascii=False))
"""


def test_task_end_to_end_through_chat_pipeline():
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env.update({
            "HERMES_ALI_STATE_DIR": str(Path(tmp) / "state"),
            "AGENT_CLI_HOME": str(Path(tmp) / "agent-cli"),
            "HERMES_HOME": str(Path(tmp) / "hermes"),
            "HOME": tmp,
            "HERMES_ALI_AGENT_DIR": str(Path(tmp) / "no-agent"),
        })
        proc = subprocess.run([sys.executable, "-c", E2E, str(ROOT)], env=env, capture_output=True, text=True, timeout=180)
    assert proc.returncode == 0, proc.stderr[-2000:]
    out = json.loads(proc.stdout.strip().splitlines()[-1])
    assert out["final"] == "done" and out["done_steps"] == out["total"] == 4
    assert [s["step"] for s in out["seen"]] == [1, 2, 3, 4]
    assert all(s["has_review"] and s["has_prov"] and s["task_route"] for s in out["seen"])
    assert out["seen"][1]["steer"] == "- 用英文写" and not out["seen"][2]["steer"]
    assert out["users"][0].startswith("▶ 步骤 1/4：列出要点")
    assert out["demo_flag"] is True and out["demo_status"] == "blocked" and out["demo_reason"] == "error"

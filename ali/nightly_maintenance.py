"""Low-risk nightly memory extraction and evolution proposals."""

from __future__ import annotations
import json
import time
from datetime import date
from pathlib import Path
from typing import Any
from .home import ensure_home
from .sessions import list_sessions

def _dirs() -> tuple[Path, Path, Path, Path]:
    root = Path.home() / ".hermes" / "ali"
    memory, proposals, digests = root / "memory", root / "evolution" / "proposals", root / "digests"
    for p in (memory, proposals, digests): p.mkdir(parents=True, exist_ok=True)
    return root, memory, proposals, digests

def status() -> dict[str, Any]:
    path = ensure_home()["state"] / "nightly_maintenance.json"
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError): return {"status": "never", "proposal_count": 0}

def run() -> dict[str, Any]:
    today = date.today().isoformat(); _root, memory, proposals, digests = _dirs()
    sessions = list_sessions(include_archived=True)[:40]
    payload = {"date": today, "runtime": "local-rules", "runtime_note": "Hermes/Claw runtime unavailable; local fallback used.", "core_facts": [x.get("summary") for x in sessions if x.get("summary")][:20], "repeated_issues": ["检查 provider/model 与 Base URL 是否匹配", "保持输出为 Markdown 分段并带整体汇总"], "sessions": len(sessions), "ts": time.time()}
    mem = memory / f"{today}.json"; mem.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proposal = proposals / f"{today}.md"
    proposal.write_text("# Agent Hub 夜间自治提案 " + today + "\n\n## 建议\n\n- 检查模型、Provider 与 Base URL 的一致性。\n- 保持输出结构化，并继续限制跨文件夹上下文长度。\n\n本文件仅为人工审核提案，不会自动修改生产代码。\n", encoding="utf-8")
    digest = digests / f"{today}.md"; digest.write_text("# 晨间简报 " + today + "\n\n- 会话摘要：" + str(len(sessions)) + "\n- 提案：" + str(proposal) + "\n- 状态：运行时不可用，已使用本地规则回退。\n", encoding="utf-8")
    out = {"ok": True, "status": "ok", "runtime": "local-rules", "last_run": time.time(), "proposal_count": 1, "memory": str(mem), "proposal": str(proposal), "digest": str(digest)}
    (ensure_home()["state"] / "nightly_maintenance.json").write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        from .schedule import push_notification
        push_notification(title="夜间自治维护已完成", title_en="Nightly maintenance completed", kind="maintenance", summary="已生成记忆摘要和人工审核提案", task_id="nightly-maintenance")
    except Exception: pass
    return out

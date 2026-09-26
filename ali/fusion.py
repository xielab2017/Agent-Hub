"""Fused answers: one question to several chosen models at once, merged into one reply.

Every selected source (``provider::model`` — an API vendor or an agent account) answers in parallel with the same
Hub context; a synthesizer model then writes one answer that keeps what the members agree on and names where they
differ.  Each member's own answer is kept on the message (``route.fusion.members``).
"""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

API_TIMEOUT = 240.0
AGENT_TIMEOUT = 600.0

SYNTH_SYSTEM = (
    "You merge answers from several AI models into one reply for the user. Use only what the answers (and any "
    "evidence in the context) contain — do not add new facts. Keep what they agree on; where they disagree, say so "
    "and state which view is better supported and why, instead of averaging. Keep citations / PMIDs / numbers that "
    "a model gave exactly as written. Answer in the user's language, in Markdown. End with a short section titled "
    "'各模型一致 / 分歧' (or 'Agreement / disagreement' for English questions) naming the models by their letters."
)


def label(src: dict[str, Any]) -> str:
    """Human name of a source: ``MiniMax-M3``, ``Claude 订阅 · opus``, ``Cursor 账号``."""
    from .connections import AGENT_ACCOUNTS

    pid, model = src.get("provider") or "", src.get("model") or ""
    if pid in AGENT_ACCOUNTS:
        base = AGENT_ACCOUNTS[pid]["label"].split("（")[0]
        return f"{base} · {model}" if model else base
    return model or pid


def resolve(sources: list[str], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    from .connections import is_agent, split_source

    out, seen = [], set()
    for s in sources:
        pid, model = split_source(s)
        if not pid or s in seen:
            continue
        seen.add(s)
        out.append({"source": s, "provider": pid, "model": model, "kind": "agent" if is_agent(pid) else "api"})
    for m in out:
        m["label"] = label(m)
    return out


def _ask_api(member: dict[str, Any], messages: list[dict[str, str]], cfg: dict[str, Any]) -> str:
    from . import llm_client
    from .providers import connection
    from .streaming import strip_model_think_tags

    c = connection(cfg, member["provider"])
    if not c["api_key"] and member["provider"] != "local-ollama":
        raise RuntimeError("no API key saved for this vendor")
    text = llm_client.stream_chat(c["base_url"], c["api_key"], model=member["model"], messages=messages,
                                  timeout=API_TIMEOUT, verify_tls=c["verify_tls"], temperature=0.3, max_tokens=4000)
    return strip_model_think_tags(str(text or "")).strip()


def _ask_agent(member: dict[str, Any], question: str, preamble: str, hub_session: str,
               cancelled: Callable[[], bool] | None) -> str:
    from . import agent_cli

    r = agent_cli.run(member["provider"], question, hub_session=f"{hub_session}#fusion" if hub_session else "",
                      system=preamble, model=member["model"], cancelled=cancelled, timeout=AGENT_TIMEOUT)
    if r.get("error") and not r.get("text"):
        raise RuntimeError(r["error"])
    return str(r.get("text") or "").strip()


def synthesizer(members: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    """Who writes the fused answer: ali.fusion_synthesizer, else the first chosen API source, else the Hub's
    reasoning-tier vendor (an agent account never synthesizes: it is an HTTP call)."""
    from .connections import is_agent, split_source
    from .providers import connection, hub_model

    pick = str((cfg.get("ali") or {}).get("fusion_synthesizer") or "")
    if pick and not is_agent(split_source(pick)[0]):
        pid, model = split_source(pick)
    else:
        first = next((m for m in members if m["kind"] == "api"), None)
        if first:
            pid, model = first["provider"], first["model"]
        else:
            hm = hub_model(cfg, "reasoning")
            if not hm.get("provider") or hm.get("error"):
                return {}
            return {"provider": hm["provider"], "model": hm["model"], "base_url": hm["base_url"],
                    "api_key": hm["api_key"], "verify_tls": hm["verify_tls"], "label": hm["model"] or hm["provider"]}
    c = connection(cfg, pid)
    return {"provider": pid, "model": model, "base_url": c["base_url"], "api_key": c["api_key"],
            "verify_tls": c["verify_tls"], "label": model or pid}


def run(question: str, sources: list[str], *, preamble: str = "", history: list[dict[str, str]] | None = None,
        cfg: dict[str, Any] | None = None, hub_session: str = "",
        on_event: Callable[[str, Any], None] | None = None,
        cancelled: Callable[[], bool] | None = None) -> dict[str, Any]:
    """Ask every source in parallel, then merge.  ``on_event(kind, data)``: member_start / member_done / token."""
    from . import llm_client
    from .settings import load_campus_config
    from .streaming import strip_model_think_tags

    cfg = cfg or load_campus_config()
    members = resolve(sources, cfg)
    emit = on_event or (lambda k, d: None)
    base_msgs: list[dict[str, str]] = ([{"role": "system", "content": preamble}] if preamble else []) \
        + list(history or []) + [{"role": "user", "content": question}]

    def work(m: dict[str, Any]) -> None:
        t0 = time.time()
        emit("member_start", {"label": m["label"], "source": m["source"]})
        try:
            m["answer"] = (_ask_agent(m, question, preamble, hub_session, cancelled) if m["kind"] == "agent"
                           else _ask_api(m, base_msgs, cfg))
            m["ok"] = bool(m["answer"])
            m["error"] = "" if m["ok"] else "empty answer"
        except Exception as exc:  # noqa: BLE001 — one member failing must not stop the others
            m.update(ok=False, answer="", error=f"{type(exc).__name__}: {exc}"[:300])
        m["seconds"] = round(time.time() - t0, 1)
        emit("member_done", {k: m.get(k) for k in ("label", "source", "ok", "error", "seconds")})

    threads = [threading.Thread(target=work, args=(m,), daemon=True) for m in members]
    for t in threads:
        t.start()
    for t in threads:
        t.join(AGENT_TIMEOUT + 30)
    good = [m for m in members if m.get("ok")]
    result: dict[str, Any] = {"members": [{k: m.get(k) for k in ("source", "label", "kind", "ok", "seconds", "error",
                                                              "answer")} for m in members],
                              "synthesizer": "", "answer": "", "error": ""}
    if not good:
        result["error"] = "no model answered: " + "; ".join(f"{m['label']}: {m.get('error')}" for m in members)
        return result
    if len(good) == 1:
        failed = [m["label"] for m in members if not m.get("ok")]
        note = f"\n\n> 仅 {good[0]['label']} 给出了回答（{', '.join(failed)} 未成功），未能融合。" if failed else ""
        result.update(answer=good[0]["answer"] + note, synthesizer=good[0]["label"])
        emit("token", result["answer"])
        return result
    syn = synthesizer(members, cfg)
    letters = "ABCDEFGH"
    block = "\n\n".join(f"### [{letters[i]}] {m['label']}\n{m['answer']}" for i, m in enumerate(good))
    failed = [f"{m['label']} ({m.get('error')})" for m in members if not m.get("ok")]
    user = (f"User question:\n{question}\n\nAnswers from {len(good)} models:\n\n{block}"
            + (f"\n\n(Models that failed: {', '.join(failed)})" if failed else "")
            + "\n\nWrite the merged answer now.")
    msgs = ([{"role": "system", "content": preamble}] if preamble else []) + [
        {"role": "system", "content": SYNTH_SYSTEM}, {"role": "user", "content": user}]
    if not syn:
        result.update(answer=block, synthesizer="", error="no API model available to merge the answers")
        emit("token", block)
        return result
    result["synthesizer"] = syn["label"]
    try:  # collected, cleaned of <think> text, then streamed (raw tokens could carry the model's reasoning)
        text = llm_client.stream_chat(syn["base_url"], syn["api_key"], model=syn["model"], messages=msgs,
                                      timeout=API_TIMEOUT, verify_tls=syn["verify_tls"], temperature=0.2,
                                      max_tokens=6000)
    except Exception as exc:  # noqa: BLE001 — merging failed: show the members' answers one after another
        result.update(answer=block, error=f"merge failed: {exc}"[:300])
        emit("token", block)
        return result
    answer = strip_model_think_tags(str(text or "")).strip()
    for i in range(0, len(answer), 64):
        emit("token", answer[i:i + 64])
    result["answer"] = answer
    return result

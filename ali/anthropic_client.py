"""Anthropic Messages API client for Anthropic-compatible gateways.

MiniMax (``https://api.minimax.cn/anthropic``, ``https://api.minimaxi.com/anthropic``,
``https://api.minimax.io/anthropic``) and other vendors expose the Messages API
next to — or instead of — an OpenAI-compatible one; Coding Plan keys are
meant for it.  ``llm_client`` routes any base URL ending in ``/anthropic`` here,
so the rest of the Hub keeps calling ``stream_chat`` / ``list_models``.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any, Callable
from urllib.parse import urlparse

ANTHROPIC_VERSION = "2023-06-01"
DEFAULT_MAX_TOKENS = 4096


def is_anthropic_base(base_url: str) -> bool:
    u = (base_url or "").strip().rstrip("/").lower()
    if not u:
        return False
    path = urlparse(u).path
    return path.endswith("/anthropic") or "/anthropic/" in path + "/" or urlparse(u).netloc == "api.anthropic.com"


def _root(base_url: str) -> str:
    u = (base_url or "").strip().rstrip("/")
    for suffix in ("/v1/messages", "/messages", "/v1"):
        if u.lower().endswith(suffix):
            u = u[: -len(suffix)]
    return u


def messages_url(base_url: str) -> str:
    return _root(base_url) + "/v1/messages"


def to_anthropic(messages: list[dict[str, Any]]) -> tuple[str, list[dict[str, str]]]:
    """OpenAI-style messages → (system, alternating user/assistant turns)."""
    system_parts: list[str] = []
    turns: list[dict[str, str]] = []
    for m in messages or []:
        role = m.get("role")
        content = m.get("content")
        if isinstance(content, list):
            content = " ".join(str(p.get("text") or "") for p in content if isinstance(p, dict))
        content = str(content or "")
        if role == "system":
            if content.strip():
                system_parts.append(content)
            continue
        if role not in ("user", "assistant") or not content.strip():
            continue
        if turns and turns[-1]["role"] == role:  # the API wants alternating turns
            turns[-1]["content"] += "\n\n" + content
        else:
            turns.append({"role": role, "content": content})
    if turns and turns[0]["role"] != "user":
        turns.insert(0, {"role": "user", "content": "(continuing the conversation)"})
    return "\n\n".join(system_parts), turns


def _headers(api_key: str, *, stream: bool) -> dict[str, str]:
    h = {
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
        "anthropic-version": ANTHROPIC_VERSION,
        "User-Agent": "Agent-Hub/1.4",
    }
    if api_key:
        h["x-api-key"] = api_key
        h["Authorization"] = f"Bearer {api_key}"  # some gateways read this one instead
    return h


def _body(model: str, messages: list[dict[str, Any]], *, stream: bool, temperature: float | None,
          max_tokens: int | None) -> dict[str, Any]:
    system, turns = to_anthropic(messages)
    body: dict[str, Any] = {"model": model, "messages": turns, "stream": stream,
                            "max_tokens": int(max_tokens) if max_tokens and int(max_tokens) > 0 else DEFAULT_MAX_TOKENS}
    if system:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = float(temperature)
    return body


def _open(url: str, body: dict[str, Any], api_key: str, *, stream: bool, timeout: float, verify_tls: bool) -> Any:
    from .llm_client import _ssl_context

    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"),
                                 headers=_headers(api_key, stream=stream), method="POST")
    return urllib.request.urlopen(req, timeout=timeout, context=_ssl_context(verify_tls))


def _raise_http(exc: urllib.error.HTTPError, url: str, model: str) -> None:
    from .llm_client import RETRY_STATUS, _format_http_error

    err = RuntimeError(_format_http_error(exc, url=url, model=model))
    if exc.code in RETRY_STATUS:
        err.status = exc.code  # type: ignore[attr-defined]
        err.retry_after = (exc.headers or {}).get("Retry-After") if exc.headers else None  # type: ignore[attr-defined]
    raise err from exc


def _error_text(obj: Any) -> str:
    from .llm_client import provider_error

    if isinstance(obj, dict) and obj.get("type") == "error":
        e = obj.get("error") or {}
        return f"{e.get('type') or 'error'}: {e.get('message') or e}"
    return provider_error(obj)


def stream(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, Any]],
    timeout: float = 120,
    verify_tls: bool = True,
    on_token: Callable[[str], None] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    meta: dict[str, Any] | None = None,
) -> str:
    """Streamed Messages call; visible text only (thinking blocks are not shown)."""
    meta = meta if meta is not None else {}
    url = messages_url(base_url)
    body = _body(model, messages, stream=True, temperature=temperature, max_tokens=max_tokens)
    parts: list[str] = []
    completed = False
    try:
        with _open(url, body, api_key, stream=True, timeout=timeout, verify_tls=verify_tls) as resp:
            try:
                resp.fp.raw._sock.settimeout(min(45.0, max(8.0, float(timeout) / 3)))
            except Exception:  # noqa: BLE001
                pass
            if "json" in str(resp.headers.get("Content-Type") or "") and "event-stream" not in str(resp.headers.get("Content-Type") or ""):
                obj = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
                return _from_message(obj, url, model, on_token)
            last = time.time()
            while True:
                try:
                    line = resp.readline()
                except Exception:  # noqa: BLE001 — socket timeout / reset
                    break
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text.startswith("data:"):
                    if parts and time.time() - last > 60:
                        break
                    continue
                payload = text[5:].strip()
                if payload == "[DONE]":
                    completed = True
                    break
                try:
                    obj = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                last = time.time()
                kind = obj.get("type")
                if kind == "error" or (isinstance(obj, dict) and obj.get("base_resp")):
                    err = _error_text(obj)
                    if err:
                        raise RuntimeError(f"{err} url={url} model={model}")
                if kind == "content_block_delta":
                    d = obj.get("delta") or {}
                    if d.get("type") == "text_delta" and d.get("text"):
                        parts.append(d["text"])
                        if on_token:
                            on_token(d["text"])
                elif kind == "message_delta":
                    stop = (obj.get("delta") or {}).get("stop_reason")
                    if stop:
                        meta["stop_reason"] = stop
                elif kind == "message_stop":
                    completed = True
                    break
    except urllib.error.HTTPError as exc:
        _raise_http(exc, url, model)
    if parts and not completed:
        meta["truncated"] = True
    if meta.get("stop_reason") == "max_tokens":
        meta["truncated"] = True
    if not parts:
        return chat_once(base_url, api_key, model=model, messages=messages, timeout=timeout,
                         verify_tls=verify_tls, on_token=on_token, temperature=temperature, max_tokens=max_tokens)
    return "".join(parts)


def _from_message(obj: Any, url: str, model: str, on_token: Callable[[str], None] | None) -> str:
    err = _error_text(obj)
    if err:
        raise RuntimeError(f"{err} url={url} model={model}")
    text = "".join(str(b.get("text") or "") for b in (obj.get("content") or []) if isinstance(b, dict) and b.get("type") == "text")
    if text and on_token:
        for i in range(0, len(text), 40):
            on_token(text[i:i + 40])
    return text


def chat_once(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, Any]],
    timeout: float = 120,
    verify_tls: bool = True,
    on_token: Callable[[str], None] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    url = messages_url(base_url)
    body = _body(model, messages, stream=False, temperature=temperature, max_tokens=max_tokens)
    try:
        with _open(url, body, api_key, stream=False, timeout=timeout, verify_tls=verify_tls) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as exc:
        _raise_http(exc, url, model)
    return _from_message(obj, url, model, on_token)


def list_models(base_url: str, api_key: str, *, timeout: float = 30, verify_tls: bool = True) -> dict[str, Any]:
    from .llm_client import _ssl_context

    url = _root(base_url) + "/v1/models"
    req = urllib.request.Request(url, headers={k: v for k, v in _headers(api_key, stream=False).items()
                                               if k != "Content-Type"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context(verify_tls)) as resp:
            obj = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        err = _error_text(obj)
        if err:
            return {"ok": False, "error": err, "models": [], "url": url}
        models = sorted({str(m.get("id")) for m in (obj.get("data") or []) if isinstance(m, dict) and m.get("id")},
                        key=str.lower)
        return {"ok": True, "models": models, "count": len(models), "url": url}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}", "models": [], "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "models": [], "url": url}

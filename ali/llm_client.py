"""OpenAI-compatible HTTP client: list models + stream chat (stdlib only)."""

from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any, Callable, Iterator
from urllib.parse import urljoin


def _normalize_base(base_url: str) -> str:
    """Normalize OpenAI-compatible base so urljoin(..., 'chat/completions') is correct.

    Accepts common user mistakes: trailing slash, pasted full .../chat/completions,
    or host-only URL missing /v1.
    """
    u = (base_url or "").strip()
    if not u:
        return ""
    # Strip accidental full chat path (would otherwise become .../chat/completions/chat/completions)
    for suffix in ("/chat/completions", "/completions"):
        if u.rstrip("/").lower().endswith(suffix):
            u = u.rstrip("/")[: -len(suffix)]
            break
    u = u.rstrip("/")
    # Host-only or path without version → append /v1 (OpenAI-compatible default)
    lower = u.lower()
    if "://" in lower:
        path = lower.split("://", 1)[1]
        path = path.split("/", 1)[1] if "/" in path else ""
        if not path:
            u = u + "/v1"
    return u + "/"


def chat_completions_url(base_url: str) -> str:
    return urljoin(_normalize_base(base_url), "chat/completions")


def _ssl_context(verify_tls: bool = True) -> ssl.SSLContext | None:
    if verify_tls:
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _request(
    method: str,
    url: str,
    *,
    api_key: str = "",
    body: dict[str, Any] | None = None,
    timeout: float = 60,
    verify_tls: bool = True,
    stream: bool = False,
) -> Any:
    data = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "Hermes-ALI/1.1",
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    ctx = _ssl_context(verify_tls)
    # stream: return raw response
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def list_models(
    base_url: str,
    api_key: str,
    *,
    timeout: float = 30,
    verify_tls: bool = True,
) -> dict[str, Any]:
    base = _normalize_base(base_url)
    if not base:
        return {"ok": False, "error": "base_url empty", "models": []}
    url = urljoin(base, "models")
    try:
        with _request("GET", url, api_key=api_key, timeout=timeout, verify_tls=verify_tls) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        payload = json.loads(raw)
        items = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(items, list):
            # some gateways return {models:[...]} 
            items = payload.get("models") if isinstance(payload, dict) else []
        models: list[str] = []
        for it in items or []:
            if isinstance(it, str):
                models.append(it)
            elif isinstance(it, dict):
                mid = it.get("id") or it.get("name") or it.get("model")
                if mid:
                    models.append(str(mid))
        models = sorted(set(models), key=lambda s: s.lower())
        return {"ok": True, "models": models, "count": len(models), "url": url}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            detail = str(exc)
        return {"ok": False, "error": f"HTTP {exc.code}: {detail}", "models": [], "url": url}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "models": [], "url": url}


def suggest_slots(models: list[str]) -> dict[str, str]:
    """Heuristic pick for C0/C1/Vision/C3/embed from a live model list."""
    lower_map = {m.lower(): m for m in models}

    def pick(preds: list[Callable[[str], bool]], fallback_substrings: list[str] | None = None) -> str:
        for m in models:
            ml = m.lower()
            if any(p(ml) for p in preds):
                return m
        if fallback_substrings:
            for sub in fallback_substrings:
                for ml, orig in lower_map.items():
                    if sub in ml:
                        return orig
        return models[0] if models else ""

    embed = pick(
        [lambda s: "embed" in s],
        ["embed"],
    )
    vision = pick(
        [lambda s: any(x in s for x in ("vision", "vl", "llava", "gpt-4o", "gemini-2.0-flash", "4o"))],
        ["vision", "vl"],
    )
    reasoning = pick(
        [lambda s: any(x in s for x in ("r1", "reason", "o3", "o4", "opus", "deepseek-reasoner", "thinking"))],
        ["r1", "reason", "o3"],
    )
    fast = pick(
        [lambda s: any(x in s for x in ("mini", "haiku", "8b", "7b", "flash-lite", "nano", "small"))],
        ["mini", "8b", "flash"],
    )
    main = pick(
        [
            lambda s: any(x in s for x in ("70b", "72b", "sonnet", "gpt-4o", "gpt-4.1", "qwen2.5-72", "pro", "nemotron"))
            and "embed" not in s
            and "vision" not in s
        ],
        ["70b", "sonnet", "gpt-4o", "instruct"],
    )
    # avoid duplicates where possible
    if main == fast and len(models) > 1:
        for m in models:
            if m != fast and "embed" not in m.lower():
                main = m
                break
    return {
        "fast": fast,
        "main": main or fast,
        "vision": vision or main or fast,
        "reasoning": reasoning or main or fast,
        "embedding": embed,
        "reranker": "",
        "qwen_fast": fast,
        "qwen_main": main or fast,
        "qwen_vl": vision or main or fast,
        "deepseek_reasoning": reasoning or main or fast,
    }


def _format_http_error(
    exc: urllib.error.HTTPError,
    *,
    url: str = "",
    model: str = "",
) -> str:
    detail = ""
    try:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
    except Exception:  # noqa: BLE001
        detail = str(exc)
    # Try to surface provider JSON message
    hint = detail
    try:
        obj = json.loads(detail)
        err = obj.get("error") if isinstance(obj, dict) else None
        if isinstance(err, dict):
            hint = str(err.get("message") or err.get("code") or detail)
        elif isinstance(err, str):
            hint = err
        elif isinstance(obj, dict) and obj.get("message"):
            hint = str(obj.get("message"))
    except Exception:  # noqa: BLE001
        pass
    where = f" url={url}" if url else ""
    who = f" model={model}" if model else ""
    if exc.code == 401:
        return (
            "HTTP 401 Unauthorized — API Key 无效，或密钥与后端厂商不匹配。"
            "OpenRouter 密钥以 sk-or- 开头（后端须选 openrouter）；"
            "NVIDIA 密钥以 nvapi- 开头（后端须选 nvidia-nim）。"
            f"{where}{who} 详情: {hint[:300]}"
        )
    if exc.code == 400:
        return (
            f"HTTP 400 Bad Request — 请求被模型服务拒绝（常见原因：模型 ID 无效、上下文过长、或参数不兼容）。"
            f"{where}{who} 详情: {hint[:500]}"
        )
    if exc.code == 404:
        return (
            "HTTP 404 — 模型服务未找到该接口或模型。"
            "请检查：① Base URL 是否为 OpenAI 兼容根（如 …/v1，不要重复 /chat/completions）；"
            "② Hybrid 模式下模型 ID 是否匹配当前厂商（NVIDIA 需 org/model，如 deepseek-ai/deepseek-v4-flash）；"
            "③ 厂商与 API Key 是否一致。"
            f"{where}{who} 详情: {hint[:300]}"
        )
    return f"HTTP {exc.code}: {hint[:500]}{where}{who}"


def stream_chat(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, str]],
    timeout: float = 120,
    verify_tls: bool = True,
    on_token: Callable[[str], None] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """Stream chat completions; returns full assistant text."""
    base = _normalize_base(base_url)
    if not base:
        raise ValueError("base_url empty")
    if not model:
        raise ValueError("model empty")
    # Cap oversized system / history to avoid provider 400s
    messages = _trim_messages(messages)
    url = chat_completions_url(base_url)
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": True,
        "temperature": 0.7 if temperature is None else float(temperature),
    }
    if max_tokens is not None:
        try:
            mt = int(max_tokens)
            if mt > 0:
                body["max_tokens"] = mt
        except (TypeError, ValueError):
            pass
    # DeepSeek V4 reasoning-capable ids spend budget on reasoning_content first;
    # tiny max_tokens yields empty visible content.
    mid = (model or "").lower()
    if "deepseek-v4" in mid or mid.endswith("-reasoner"):
        cur = int(body.get("max_tokens") or 0)
        if cur and cur < 256:
            body["max_tokens"] = 256
        elif not cur:
            body["max_tokens"] = 2048
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}" if api_key else "",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "Agent-Hub/1.4",
        },
        method="POST",
    )
    # Drop empty Authorization
    if not api_key:
        req.remove_header("Authorization")

    ctx = _ssl_context(verify_tls)
    parts: list[str] = []
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            while True:
                line = resp.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").strip()
                if not text or text.startswith(":"):
                    continue
                if text.startswith("data:"):
                    payload = text[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        obj = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    delta = ""
                    choices = obj.get("choices") or []
                    if choices:
                        d = choices[0].get("delta") or {}
                        delta = d.get("content") or ""
                        if not delta and choices[0].get("message"):
                            delta = (choices[0]["message"].get("content") or "")
                    if delta:
                        parts.append(delta)
                        if on_token:
                            on_token(delta)
    except urllib.error.HTTPError as exc:
        msg = _format_http_error(exc, url=url, model=model)
        if exc.code == 401:
            raise RuntimeError(msg) from exc
        # Non-stream fallback (some gateways reject SSE but accept JSON)
        if exc.code in (400, 404, 415, 422):
            try:
                return _chat_once(
                    base_url,
                    api_key,
                    model=model,
                    messages=messages,
                    timeout=timeout,
                    verify_tls=verify_tls,
                    on_token=on_token,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception as fallback_exc:  # noqa: BLE001
                raise RuntimeError(f"{msg} | 非流式重试失败: {fallback_exc}") from fallback_exc
        raise RuntimeError(msg) from exc

    if not parts:
        # Some endpoints ignore stream=true
        return _chat_once(
            base_url,
            api_key,
            model=model,
            messages=messages,
            timeout=timeout,
            verify_tls=verify_tls,
            on_token=on_token,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    return "".join(parts)


def _trim_messages(messages: list[dict[str, str]], *, max_chars: int = 100_000) -> list[dict[str, str]]:
    """Keep request size reasonable for campus gateways that 400 on huge prompts."""
    out = [dict(m) for m in messages if isinstance(m, dict)]
    total = sum(len(str(m.get("content") or "")) for m in out)
    if total <= max_chars:
        return out
    # Shrink system first, then older history
    for m in out:
        if m.get("role") == "system":
            c = str(m.get("content") or "")
            if len(c) > 12_000:
                m["content"] = c[:12_000] + "\n…(system truncated)…"
    # Drop middle history if still large
    while len(out) > 3 and sum(len(str(m.get("content") or "")) for m in out) > max_chars:
        # keep first system + last user
        mid = len(out) // 2
        if out[mid].get("role") != "user" or mid < len(out) - 1:
            out.pop(mid)
        else:
            break
    return out


def _chat_once(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, str]],
    timeout: float = 120,
    verify_tls: bool = True,
    on_token: Callable[[str], None] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    url = chat_completions_url(base_url)
    body: dict[str, Any] = {
        "model": model,
        "messages": _trim_messages(messages),
        "stream": False,
        "temperature": 0.7 if temperature is None else float(temperature),
    }
    if max_tokens is not None:
        try:
            mt = int(max_tokens)
            if mt > 0:
                body["max_tokens"] = mt
        except (TypeError, ValueError):
            pass
    mid = (model or "").lower()
    if "deepseek-v4" in mid or mid.endswith("-reasoner"):
        cur = int(body.get("max_tokens") or 0)
        if cur and cur < 256:
            body["max_tokens"] = 256
        elif not cur:
            body["max_tokens"] = 2048
    try:
        with _request("POST", url, api_key=api_key, body=body, timeout=timeout, verify_tls=verify_tls) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_format_http_error(exc, url=url, model=model)) from exc
    obj = json.loads(raw)
    content = ""
    choices = obj.get("choices") or []
    if choices:
        content = ((choices[0].get("message") or {}).get("content")) or ""
    if content and on_token:
        # fake stream in chunks
        chunk = 40
        for i in range(0, len(content), chunk):
            on_token(content[i : i + chunk])
    return content

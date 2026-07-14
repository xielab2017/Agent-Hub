"""Reply-language policy: match the user's language unless they override."""

from __future__ import annotations

import re
from typing import Any

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_EN_OVERRIDE = re.compile(
    r"(?:用英文|用英语|英文回答|英语回答|in\s+english|respond\s+in\s+english|answer\s+in\s+english|output\s+in\s+english)",
    re.I,
)
_ZH_OVERRIDE = re.compile(
    r"(?:用中文|中文回答|简体中文|繁體中文|in\s+chinese|respond\s+in\s+chinese|answer\s+in\s+chinese)",
    re.I,
)
_OTHER = re.compile(
    r"(?:用日语|用日文|in\s+japanese|用韩语|in\s+korean|en\s+français|in\s+french|in\s+german|auf\s+deutsch)",
    re.I,
)


def detect_reply_language(message: str, cfg: dict[str, Any] | None = None) -> str:
    """Return language code: zh | en | other (follow message)."""
    text = message or ""
    if _EN_OVERRIDE.search(text):
        return "en"
    if _ZH_OVERRIDE.search(text):
        return "zh"
    if _OTHER.search(text):
        return "follow"
    if _CJK_RE.search(text):
        return "zh"
    # Prefer UI language only when message has no clear signal
    ali = (cfg or {}).get("ali") if isinstance((cfg or {}).get("ali"), dict) else {}
    pref = str((ali or {}).get("language") or "").lower()
    if pref in ("zh", "en"):
        # Still: English-only message → English
        if not _CJK_RE.search(text) and re.search(r"[A-Za-z]{3,}", text):
            return "en"
        return pref
    if re.search(r"[A-Za-z]{3,}", text) and not _CJK_RE.search(text):
        return "en"
    return "zh"


def language_system_rule(message: str, cfg: dict[str, Any] | None = None) -> str:
    lang = detect_reply_language(message, cfg)
    if lang == "zh":
        return (
            "## Working language\n"
            "The user wrote in Chinese. Reply in Simplified Chinese (简体中文).\n"
            "Only switch language if the user explicitly requests another language "
            "(e.g. 「用英文」「in English」)."
        )
    if lang == "en":
        return (
            "## Working language\n"
            "Reply in English. Only switch if the user explicitly requests another language."
        )
    return (
        "## Working language\n"
        "Match the language the user asked for in this message."
    )

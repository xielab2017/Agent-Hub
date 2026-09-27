"""Main-page chrome: versions, i18n keys, live stream visibility, fused login+API copy."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _i18n_keys(block: str) -> set[str]:
    return set(re.findall(r'"([^"]+)":\s*"', block))


def test_stream_live_pre_is_not_hidden():
    css = (ROOT / "static" / "style.css").read_text(encoding="utf-8")
    assert ":not(.stream-live-pre)" in css
    assert re.search(r"\.stream-live-pre\s*\{[^}]*display:\s*block", css, re.S)


def test_chat_title_is_not_a_static_i18n_node():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    title = re.search(r'<h2 id="chat-title"[^>]*>', html)
    assert title and "data-i18n" not in title.group(0)


def test_connections_tab_is_login_and_api():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    assert 'data-i18n="control.connections"' in html
    assert '"control.connections": "API 与登录"' in js
    assert '"control.connections": "APIs & sign-in"' in js
    assert "sources.hint" in js and "sources.openConnections" in js
    assert "function paintSessionPane" in js
    assert "function applyStaticChromeI18n" in js


def test_i18n_zh_en_share_chrome_keys():
    js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    zh = re.search(r"const I18N = \{\s*zh: \{([\s\S]*?)\n  \},\s*en: \{", js)
    en = re.search(r"\n  en: \{([\s\S]*?)\n  \},\n\};", js)
    assert zh and en
    needed = {
        "nav.archive",
        "nav.archiveBack",
        "nav.searchSessions",
        "nav.newFolder",
        "chat.loading",
        "chat.you",
        "composer.drop",
        "model.auto",
        "sources.hint",
        "control.connections",
        "sub.popout",
    }
    zh_keys, en_keys = _i18n_keys(zh.group(1)), _i18n_keys(en.group(1))
    assert needed <= zh_keys
    assert needed <= en_keys

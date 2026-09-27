"""中/EN switching: every user-facing string in the shipped HTML is switchable, and both dictionaries agree.

A string baked straight into ``static/index.html`` cannot follow the 中 / EN toggle, and a key that exists in
only one dictionary falls back to the other language. Both used to happen (the session search box, the archive
and folder buttons, the workspace browser, the sub-agent window), so they are checked here rather than by eye.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "static" / "index.html"
POPOUT = ROOT / "static" / "subagent-window.html"
APP_JS = ROOT / "static" / "app.js"

CJK = re.compile(r"[\u4e00-\u9fff]")
I18N_ATTRS = ("data-i18n", "data-i18n-html", "data-i18n-placeholder", "data-i18n-title", "data-i18n-aria")
TEXT_ATTRS = ("placeholder", "title", "aria-label")
# Which i18n attribute has to be present for Chinese in a given place to be switchable.
ATTR_FOR = {"placeholder": "data-i18n-placeholder", "title": "data-i18n-title", "aria-label": "data-i18n-aria"}

# The 中 / EN toggle names both languages on purpose; the logo's alt text is the university's own name.
ALLOWED_FIXED_CJK = ("中 / EN", "深圳理工大学")


def _dicts() -> tuple[dict[str, str], dict[str, str]]:
    """The zh and en halves of ``const I18N = {…}`` in app.js, as key → value."""
    src = APP_JS.read_text(encoding="utf-8")
    start = src.index("const I18N = {")
    end = src.index("\n};", start)
    block = src[start:end]
    zh_part, _, en_part = block.partition("\n  en: {")
    entry = re.compile(r'^\s{4}"([^"]+)":\s*(.+?),?$', re.M)
    return ({m.group(1): m.group(2) for m in entry.finditer(zh_part)},
            {m.group(1): m.group(2) for m in entry.finditer(en_part)})


def _tags(html: str) -> list[str]:
    return re.findall(r"<[a-zA-Z][^>]*>", html, re.S)


def test_both_dictionaries_cover_the_same_keys():
    zh, en = _dicts()
    assert zh and en
    assert not (set(zh) - set(en)), f"missing from en: {sorted(set(zh) - set(en))}"
    assert not (set(en) - set(zh)), f"missing from zh: {sorted(set(en) - set(zh))}"


def test_every_key_the_html_asks_for_exists():
    zh, en = _dicts()
    html = INDEX.read_text(encoding="utf-8")
    used = set()
    for attr in I18N_ATTRS:
        used.update(re.findall(rf'{attr}="([^"]+)"', html))
    assert used
    missing = sorted(k for k in used if k not in zh or k not in en)
    assert not missing, f"index.html uses keys that no dictionary defines: {missing}"


def test_no_chinese_in_the_html_is_stuck_in_one_language():
    """Chinese text, placeholders, titles and labels each need the matching i18n attribute."""
    stuck: list[str] = []
    for tag in _tags(INDEX.read_text(encoding="utf-8")):
        attrs = dict(re.findall(r'([a-zA-Z][a-zA-Z0-9_-]*)="([^"]*)"', tag))
        for name in TEXT_ATTRS:
            value = attrs.get(name, "")
            if CJK.search(value) and ATTR_FOR[name] not in attrs and value not in ALLOWED_FIXED_CJK:
                stuck.append(f"{name}={value!r} in {tag[:70]}")
    # Element text: a Chinese default is fine only when the node also carries data-i18n / data-i18n-html.
    for match in re.finditer(r"<([a-zA-Z][a-zA-Z0-9]*)\b([^>]*)>([^<]*)<", INDEX.read_text(encoding="utf-8"), re.S):
        tag, raw_attrs, text = match.group(1), match.group(2), match.group(3).strip()
        if not CJK.search(text) or text in ALLOWED_FIXED_CJK:
            continue
        if "data-i18n" in raw_attrs:
            continue
        stuck.append(f"text {text!r} in <{tag}{raw_attrs[:50]}>")
    assert not stuck, "not switchable by 中/EN:\n  " + "\n  ".join(stuck)


def test_the_subagent_window_translates_itself():
    """It opens as its own window, so it carries its own dictionary and reads the stored language."""
    html = POPOUT.read_text(encoding="utf-8")
    assert 'localStorage.getItem("hermes_ali_lang")' in html
    # The same token key the main window writes — the wrong one made every request here 401.
    assert 'localStorage.getItem("hermes_ali_token")' in html
    zh = dict(re.findall(r'(\w+): "([^"]*)"', html[html.index("zh: {"):html.index("en: {")]))
    en = dict(re.findall(r'(\w+): "([^"]*)"', html[html.index("en: {"):html.index("};", html.index("en: {"))]))
    assert zh and set(zh) == set(en), f"zh/en mismatch: {set(zh) ^ set(en)}"
    used = set(re.findall(r'data-i18n="([^"]+)"', html)) | set(re.findall(r'T\("([^"]+)"\)', html))
    assert used and not (used - set(zh)), f"undefined keys: {sorted(used - set(zh))}"


def test_taxonomy_and_core_skills_have_english_labels():
    """The skill picker falls back to the Chinese label when an entry has no English one."""
    from ali.skills import CORE_SKILL_HINTS, SKILL_TAXONOMY

    for cat in SKILL_TAXONOMY:
        assert cat.get("label_en"), cat["id"]
        for sub in cat["subs"]:
            assert sub.get("label_en"), sub["id"]
    for hint in CORE_SKILL_HINTS:
        assert hint.get("label_en"), hint["id"]

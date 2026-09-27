"""One version everywhere, so a downloaded Hub shows it and browsers do not keep old cached assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

HTML_FILES = ("index.html", "subagent-window.html")


def test_version_strings_agree():
    import ali
    from ali.config import VERSION

    assert ali.__version__ == VERSION
    assert re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1) == VERSION
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"badge/version-{VERSION}-" in readme and f"当前版本：**v{VERSION}**" in readme
    assert f"## v{VERSION} " in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_html_has_no_hardcoded_version():
    """The shipped HTML carries a placeholder only — the server fills in the running version."""
    for name in HTML_FILES:
        html = (ROOT / "static" / name).read_text(encoding="utf-8")
        assert "__APP_VERSION__" in html, name
        assert not re.search(r"\?v=[0-9][0-9.]*\b", html), f"{name} still pins an asset version"
        assert not re.search(r"\bv[0-9]+\.[0-9]+\.[0-9]+\b", html), f"{name} still spells out a version"


def test_server_renders_one_version_into_the_html():
    from ali import routes
    from ali.config import VERSION

    for name in HTML_FILES:
        rendered = routes.render_html((ROOT / "static" / name).read_text(encoding="utf-8"))
        assert routes.VERSION_PLACEHOLDER not in rendered, name
        assert set(re.findall(r"\?v=([0-9][0-9.]*)", rendered)) == {VERSION}, name
    index = routes.render_html((ROOT / "static" / "index.html").read_text(encoding="utf-8"))
    assert f'id="version-label">v{VERSION}<' in index


def test_sync_version_script_agrees():
    import sync_version

    assert sync_version.current_version()
    assert sync_version.check(sync_version.current_version()) == []

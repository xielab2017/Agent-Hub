"""One version everywhere, so a downloaded Hub shows it and browsers do not keep old cached assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_version_strings_agree():
    import ali
    from ali.config import VERSION

    assert ali.__version__ == VERSION
    assert re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(), re.M).group(1) == VERSION
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    assert set(re.findall(r"\?v=([0-9][0-9.]*)", html)) == {VERSION}
    assert f'id="version-label">v{VERSION}<' in html
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"badge/version-{VERSION}-" in readme and f"当前版本：**v{VERSION}**" in readme
    assert f"## v{VERSION} " in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")

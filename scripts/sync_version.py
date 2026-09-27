#!/usr/bin/env python3
"""One version everywhere — read it, or set it in every file that must repeat it.

    python scripts/sync_version.py            # print the current version and check every file
    python scripts/sync_version.py 5.6.0      # rewrite every file to 5.6.0

``ali/config.VERSION`` is the source of truth. Files that cannot import it (``pyproject.toml`` for the build
backend, README badges, the CHANGELOG heading) keep a literal; this script keeps those literals in step and
``tests/test_version.py`` fails the build when they drift. The served HTML has no literal at all: it carries
``__APP_VERSION__`` and ``ali.routes.render_html`` fills it in.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def current_version() -> str:
    from ali.config import VERSION

    return str(VERSION)


def _sub(path: Path, pattern: str, repl: str, *, count: int = 0) -> int:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, repl, text, count=count)
    if new != text:
        path.write_text(new, encoding="utf-8")
    return n


def set_version(version: str) -> None:
    _sub(ROOT / "ali" / "config.py", r'^VERSION = "[^"]+"', f'VERSION = "{version}"', count=1)
    _sub(ROOT / "pyproject.toml", r'^version = "[^"]+"', f'version = "{version}"', count=1)
    readme = ROOT / "README.md"
    _sub(readme, r"badge/version-[0-9][0-9.]*-", f"badge/version-{version}-")
    _sub(readme, r"当前版本：\*\*v[0-9][0-9.]*\*\*", f"当前版本：**v{version}**")
    _sub(readme, r'"version": "[0-9][0-9.]*"', f'"version": "{version}"')


def check(version: str) -> list[str]:
    """Every place that repeats the version agrees with ``ali.config.VERSION``."""
    problems: list[str] = []

    def want(label: str, ok: bool) -> None:
        if not ok:
            problems.append(label)

    import ali

    want("ali.__version__", ali.__version__ == version)
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    want("pyproject.toml", re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1) == version)
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    want("README badge", f"badge/version-{version}-" in readme)
    want("README 当前版本", f"当前版本：**v{version}**" in readme)
    want("CHANGELOG heading", f"## v{version} " in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    for name in ("index.html", "subagent-window.html"):
        html = (ROOT / "static" / name).read_text(encoding="utf-8")
        want(f"{name} placeholder", "__APP_VERSION__" in html)
        want(f"{name} has no literal version", not re.search(r"\?v=[0-9][0-9.]*\b", html))
    return problems


def main(argv: list[str]) -> int:
    if argv and argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    if argv:
        version = argv[0].lstrip("v")
        if not VERSION_RE.match(version):
            print(f"not a version: {argv[0]}", file=sys.stderr)
            return 2
        set_version(version)
        print(f"set {version} in ali/config.py, pyproject.toml, README.md")
        print("remaining by hand: a `## v%s — <date>` section in CHANGELOG.md" % version)
    version = current_version()
    problems = check(version)
    print(f"version {version}: " + ("all files agree" if not problems else "MISMATCH"))
    for p in problems:
        print("  ✗", p)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

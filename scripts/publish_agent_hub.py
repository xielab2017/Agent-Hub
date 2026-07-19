#!/usr/bin/env python3
"""Interactive, cross-platform publisher for Agent Hub contributors."""

from __future__ import annotations

import getpass
import hashlib
import hmac
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


class PublishError(RuntimeError):
    pass


def git(*args: str, capture: bool = False, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise PublishError(detail or f"git {' '.join(args)} failed")
    return (result.stdout or "").strip()


def admin_hash_path() -> Path:
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "hermes-ali"
    else:
        base = Path.home() / ".hermes" / "ali"
    return base / "publish-admin.sha256"


def configured_admin_hash() -> str:
    env_hash = os.environ.get("AGENT_HUB_ADMIN_PASSWORD_SHA256", "").strip().lower()
    if env_hash:
        return env_hash
    path = admin_hash_path()
    if path.is_file():
        return path.read_text(encoding="utf-8").strip().lower()
    return ""


def verify_admin() -> None:
    expected = configured_admin_hash()
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise PublishError(
            "Admin password is not configured on this computer. "
            f"Configure AGENT_HUB_ADMIN_PASSWORD_SHA256 or {admin_hash_path()}."
        )
    entered = getpass.getpass("管理员密码 / Admin password: ")
    actual = hashlib.sha256(entered.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise PublishError("管理员密码错误 / Invalid admin password.")


def read_version() -> str:
    config = (ROOT / "ali" / "config.py").read_text(encoding="utf-8")
    match = re.search(r'^VERSION\s*=\s*"(\d+\.\d+\.\d+)"', config, re.MULTILINE)
    if not match:
        raise PublishError("Could not read VERSION from ali/config.py.")
    return match.group(1)


def next_patch(version: str) -> str:
    match = VERSION_RE.fullmatch(version)
    if not match:
        raise PublishError(f"Unsupported version: {version}")
    major, minor, patch = (int(value) for value in match.groups())
    return f"{major}.{minor}.{patch + 1}"


def replace_checked(path: Path, pattern: str, replacement: str, *, flags: int = 0) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, flags=flags)
    if count == 0:
        raise PublishError(f"Version marker not found in {path.relative_to(ROOT)}")
    path.write_text(updated, encoding="utf-8")


def bump_version(old: str, new: str) -> None:
    replace_checked(
        ROOT / "ali" / "config.py",
        rf'^VERSION\s*=\s*"{re.escape(old)}"',
        f'VERSION = "{new}"',
        flags=re.MULTILINE,
    )
    replace_checked(
        ROOT / "pyproject.toml",
        rf'^version\s*=\s*"{re.escape(old)}"',
        f'version = "{new}"',
        flags=re.MULTILINE,
    )
    replace_checked(
        ROOT / "static" / "app.js",
        r'^const LOGO_VER\s*=\s*"\d+\.\d+\.\d+";',
        f'const LOGO_VER = "{new}";',
        flags=re.MULTILINE,
    )

    index_path = ROOT / "static" / "index.html"
    index = index_path.read_text(encoding="utf-8")
    index = re.sub(r"(?<=\?v=)\d+\.\d+\.\d+", new, index)
    index = re.sub(r'(<div class="brand-sub" id="version-label">)v\d+\.\d+\.\d+(</div>)', rf"\g<1>v{new}\2", index)
    index_path.write_text(index, encoding="utf-8")

    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    readme = re.sub(r"version-\d+\.\d+\.\d+-", f"version-{new}-", readme, count=1)
    readme = re.sub(r'确认健康检查里显示 `"version": "\d+\.\d+\.\d+"`', f'确认健康检查里显示 `"version": "{new}"`', readme, count=1)
    readme = re.sub(r"当前版本：\*\*v\d+\.\d+\.\d+\*\*", f"当前版本：**v{new}**", readme, count=1)
    readme_path.write_text(readme, encoding="utf-8")


def safe_slug(raw: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._-]+", "-", raw.strip().lower()).strip("-.")
    return value[:32] or "contributor"


def stash_local_changes() -> bool:
    if not git("status", "--porcelain", "--untracked-files=normal", capture=True):
        return False
    print("临时保存本地修改 / Saving local changes...")
    git("stash", "push", "--include-untracked", "-m", f"agent-hub-publish-{datetime.now():%Y%m%d-%H%M%S}")
    return True


def restore_local_changes(stashed: bool) -> None:
    if not stashed:
        return
    print("恢复本地修改 / Restoring local changes...")
    result = subprocess.run(["git", "stash", "pop", "--index"], cwd=ROOT, check=False)
    if result.returncode != 0:
        raise PublishError("Local changes are preserved in git stash but need conflict resolution.")


def choose_role() -> str:
    print("选择发布身份 / Choose publish role")
    print("  1. 一般用户：创建新分支并推送 / Contributor: create and push a branch")
    print("  2. 管理员：验证密码后直接推送 main / Admin: verify password and push main")
    choice = input("请输入 1 或 2 / Enter 1 or 2: ").strip()
    if choice == "1":
        return "contributor"
    if choice == "2":
        return "admin"
    raise PublishError("Invalid role selection.")


def confirm_changes(version: str, branch: str) -> str:
    print("\n即将提交以下修改 / Changes to publish:\n")
    status = git("status", "--short", capture=True)
    print(status or "(none)")
    if not status:
        raise PublishError("No changes to publish.")

    suspicious = []
    for line in status.splitlines():
        if not line.startswith("?? "):
            continue
        name = line[3:].strip().lower()
        if re.search(r"(^|[/\\.])(env|credentials?|private[-_]?key|api[-_]?key|token)([/\\.]|$)", name):
            suspicious.append(line[3:].strip())
    if suspicious:
        raise PublishError("Potential secret files must be reviewed manually: " + ", ".join(suspicious))

    answer = input(f"\n确认提交到 {branch}，版本 v{version}？[y/N]: ").strip().lower()
    if answer not in {"y", "yes"}:
        raise PublishError("Publish cancelled. Version changes remain in the working tree for review.")
    default_message = f"chore: publish v{version}"
    message = input(f"提交说明 / Commit message [{default_message}]: ").strip() or default_message
    return message


def main() -> int:
    os.chdir(ROOT)
    print("=" * 46)
    print("  Agent Hub - GitHub publisher")
    print("=" * 46)
    print(f"Folder: {ROOT}\n")

    try:
        git("rev-parse", "--is-inside-work-tree", capture=True)
        if git("branch", "--show-current", capture=True) != "main":
            raise PublishError("Start the publisher from the main branch.")
        git("remote", "get-url", "origin", capture=True)

        role = choose_role()
        if role == "admin":
            verify_admin()

        stashed = stash_local_changes()
        print("同步 GitHub main / Updating GitHub main...")
        try:
            git("fetch", "--prune", "origin")
            git("pull", "--ff-only", "origin", "main")
        except Exception:
            restore_local_changes(stashed)
            raise

        current_version = read_version()
        target_version = next_patch(current_version)
        if role == "contributor":
            author = git("config", "user.name", capture=True, check=False) or getpass.getuser()
            branch = f"contrib/{safe_slug(author)}/v{target_version}-{datetime.now():%Y%m%d-%H%M%S}"
            git("switch", "-c", branch)
        else:
            branch = "main"

        restore_local_changes(stashed)
        current_version = read_version()
        target_version = next_patch(current_version)
        bump_version(current_version, target_version)

        message = confirm_changes(target_version, branch)
        git("add", "--all")
        # Keep Git's conflict-marker check without rejecting Markdown hard
        # line breaks or harmless blank lines at the end of generated files.
        git(
            "-c",
            "core.whitespace=-blank-at-eol,-blank-at-eof,-space-before-tab",
            "diff",
            "--cached",
            "--check",
        )
        git("commit", "-m", message)
        git("push", "--set-upstream", "origin", branch)

        print("\n发布完成 / Publish complete")
        print(f"Branch : {branch}")
        print(f"Version: v{target_version}")
        print(f"Commit : {git('rev-parse', '--short', 'HEAD', capture=True)}")
        if role == "contributor":
            print("请在 GitHub 为该分支创建 Pull Request。")
        return 0
    except PublishError as exc:
        print(f"\n发布未完成 / Publish stopped: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

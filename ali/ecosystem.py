"""Ecosystem packages — OpenSquilla, OpenScience, Obsidian, Notion — parallel under Agent-CLI home."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import threading
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from .home import ecosystem_dir, ensure_home, os_profile

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.RLock()

# Curated packs that Hub enables by default (no Control Center click required).
# Soft-activate when not cloned; full activate when installed.
AUTO_ACTIVATE_IDS: tuple[str, ...] = (
    "opensquilla",
    "openscience",
    "scientific-agent-skills",
)

ECOSYSTEM: list[dict[str, Any]] = [
    {
        "id": "opensquilla",
        "label": "OpenSquilla",
        "label_zh": "OpenSquilla（省 Token 路由）",
        "desc": "Token-efficient SquillaRouter — C0–C3 local routing to cheapest capable model.",
        "desc_zh": "本地 SquillaRouter：按复杂度把请求分到最便宜且够用的模型，省 Token。",
        "homepage": "https://github.com/OpenSquilla/opensquilla",
        "docs": "https://opensquilla.ai/",
        "category": "routing",
        "auto_activate": True,
        "git": "https://github.com/OpenSquilla/opensquilla.git",
        "post_posix": ["pip3 install -e ."],
        "post_windows": ["pip install -e ."],
    },
    {
        "id": "openscience",
        "label": "OpenScience",
        "label_zh": "OpenScience",
        "desc": "ai4s-research/open-science — open science workflows under Agent Hub ecosystem.",
        "desc_zh": "OpenScience（ai4s-research/open-science），安装到生态并行目录 ecosystem/openscience。",
        "homepage": "https://github.com/ai4s-research/open-science",
        "docs": "https://github.com/ai4s-research/open-science",
        "category": "science",
        "auto_activate": True,
        "git": "https://github.com/ai4s-research/open-science.git",
        "post_posix": [],
        "post_windows": [],
    },
    {
        "id": "scientific-agent-skills",
        "label": "Scientific Agent Skills",
        "label_zh": "Scientific Agent Skills",
        "desc": "K-Dense scientific-agent-skills pack under ecosystem/scientific-agent-skills.",
        "desc_zh": "科学 Agent Skills 库，安装到生态并行目录 ecosystem/scientific-agent-skills。",
        "homepage": "https://github.com/K-Dense-AI/scientific-agent-skills",
        "docs": "https://github.com/K-Dense-AI/scientific-agent-skills",
        "category": "science",
        "auto_activate": True,
        "git": "https://github.com/K-Dense-AI/scientific-agent-skills.git",
        "post_posix": [],
        "post_windows": [],
    },
    {
        "id": "obsidian_kit",
        "label": "Obsidian Knowledge Kit",
        "label_zh": "Obsidian 知识库套件",
        "desc": "Download & install Obsidian app for your OS + vault inbox templates.",
        "desc_zh": "按系统自动下载安装 Obsidian 桌面版，并生成校园知识库金库模板。",
        "homepage": "https://obsidian.md/",
        "docs": "https://help.obsidian.md/",
        "category": "knowledge",
        "scaffold": True,
        "install_app": True,
    },
    {
        "id": "notion_kit",
        "label": "Notion Bridge Kit",
        "label_zh": "Notion 桥接套件",
        "desc": "Notion API helper stubs + env template for knowledge sync.",
        "desc_zh": "Notion API 桥接模板（需自备 Integration Token）。",
        "homepage": "https://developers.notion.com/",
        "docs": "https://developers.notion.com/docs/getting-started",
        "category": "knowledge",
        "scaffold": True,
    },
    {
        "id": "hermes-self-evolution",
        "label": "Hermes Agent Self-Evolution",
        "label_zh": "Hermes 自我进化引擎（Nous）",
        "desc": "NousResearch/hermes-agent-self-evolution — DSPy+GEPA skill evolution pack (optional local engine).",
        "desc_zh": "Nous 自我进化引擎（DSPy+GEPA）。Hub「自我进化」默认走引导式评审；装此包后可在本机跑完整 GEPA。",
        "homepage": "https://github.com/NousResearch/hermes-agent-self-evolution",
        "docs": "https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/README.md",
        "category": "evolution",
        "auto_activate": False,
        "git": "https://github.com/NousResearch/hermes-agent-self-evolution.git",
        "post_posix": [],
        "post_windows": [],
    },
]


def _find_obsidian_app() -> str:
    system = platform.system()
    candidates: list[Path] = []
    if system == "Darwin":
        candidates = [
            Path("/Applications/Obsidian.app"),
            Path.home() / "Applications" / "Obsidian.app",
        ]
    elif system == "Windows":
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidates = [
            Path(local) / "Obsidian" / "Obsidian.exe" if local else Path(),
            Path(pf) / "Obsidian" / "Obsidian.exe",
        ]
    else:
        which = shutil.which("obsidian")
        if which:
            return which
        candidates = [
            Path.home() / ".local" / "bin" / "Obsidian.AppImage",
            Path("/usr/bin/obsidian"),
        ]
    for c in candidates:
        if c and c.exists():
            return str(c)
    return ""


def _latest_obsidian_version() -> str:
    url = "https://raw.githubusercontent.com/obsidianmd/obsidian-releases/master/desktop-releases.json"
    try:
        req = Request(url, headers={"User-Agent": "Agent-Hub"})
        with urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        ver = str(data.get("latestVersion") or "").strip()
        if ver:
            return ver.lstrip("v")
    except Exception:  # noqa: BLE001
        pass
    return "1.12.7"


def _download_file(url: str, dest: Path, log) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log.write(f"$ download {url}\n")
    log.flush()
    req = Request(url, headers={"User-Agent": "Agent-Hub"})
    with urlopen(req, timeout=300) as resp, dest.open("wb") as out:
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
    log.write(f"# saved {dest} ({dest.stat().st_size} bytes)\n")
    log.flush()


def _install_obsidian_app(dest: Path, log) -> dict[str, Any]:
    """Download latest Obsidian for this OS and install when possible."""
    existing = _find_obsidian_app()
    if existing:
        log.write(f"# Obsidian already installed: {existing}\n")
        (dest / "app_path.txt").write_text(existing + "\n", encoding="utf-8")
        return {"app": existing, "skipped": True, "version": ""}

    version = _latest_obsidian_version()
    system = platform.system()
    machine = platform.machine().lower()
    downloads = dest / "downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/obsidianmd/obsidian-releases/releases/download/v{version}"
    app_path = ""

    if system == "Darwin":
        # Prefer Homebrew when available (handles arch / updates)
        if shutil.which("brew"):
            log.write("$ brew install --cask obsidian\n")
            log.flush()
            r = subprocess.run(
                ["brew", "install", "--cask", "obsidian"],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=900,
            )
            if r.returncode == 0:
                app_path = _find_obsidian_app() or "/Applications/Obsidian.app"
        if not app_path:
            dmg = downloads / f"Obsidian-{version}.dmg"
            _download_file(f"{base}/Obsidian-{version}.dmg", dmg, log)
            mount_point = Path(f"/Volumes/AgentHub-Obsidian-{version}")
            log.write(f"$ hdiutil attach {dmg} -nobrowse -mountpoint {mount_point}\n")
            log.flush()
            subprocess.run(
                ["hdiutil", "attach", str(dmg), "-nobrowse", "-quiet", "-mountpoint", str(mount_point)],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=120,
                check=False,
            )
            src = mount_point / "Obsidian.app"
            if not src.is_dir():
                # fallback: find first .app under mount
                apps = list(mount_point.glob("*.app"))
                src = apps[0] if apps else src
            target_root = Path("/Applications")
            if not os.access(target_root, os.W_OK):
                target_root = Path.home() / "Applications"
                target_root.mkdir(parents=True, exist_ok=True)
            target = target_root / "Obsidian.app"
            if target.exists():
                shutil.rmtree(target)
            log.write(f"$ cp -R {src} {target}\n")
            log.flush()
            shutil.copytree(src, target)
            subprocess.run(
                ["hdiutil", "detach", str(mount_point), "-quiet"],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=60,
                check=False,
            )
            app_path = str(target)
    elif system == "Windows":
        exe = downloads / f"Obsidian-{version}.exe"
        _download_file(f"{base}/Obsidian-{version}.exe", exe, log)
        log.write(f"$ {exe} /S\n")
        log.flush()
        r = subprocess.run(
            [str(exe), "/S"],
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=900,
            check=False,
        )
        time.sleep(3)
        app_path = _find_obsidian_app() or str(exe)
        if r.returncode not in (0, None) and not _find_obsidian_app():
            log.write(f"# installer exit {r.returncode}; binary kept at {exe}\n")
    else:
        # Linux AppImage (arm64 when needed)
        name = f"Obsidian-{version}-arm64.AppImage" if "arm" in machine or "aarch" in machine else f"Obsidian-{version}.AppImage"
        appimage = downloads / name
        try:
            _download_file(f"{base}/{name}", appimage, log)
        except Exception:  # noqa: BLE001
            name = f"Obsidian-{version}.AppImage"
            appimage = downloads / name
            _download_file(f"{base}/{name}", appimage, log)
        appimage.chmod(appimage.stat().st_mode | 0o111)
        bin_dir = Path.home() / ".local" / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)
        target = bin_dir / "Obsidian.AppImage"
        shutil.copy2(appimage, target)
        target.chmod(target.stat().st_mode | 0o111)
        # convenience symlink
        link = bin_dir / "obsidian"
        try:
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(target)
        except OSError:
            pass
        app_path = str(target)

    if app_path:
        (dest / "app_path.txt").write_text(app_path + "\n", encoding="utf-8")
        (dest / "app_version.txt").write_text(version + "\n", encoding="utf-8")
        log.write(f"# Obsidian installed: {app_path} (v{version})\n")
    else:
        raise RuntimeError("Obsidian install finished but app path not found")
    return {"app": app_path, "version": version, "skipped": False}


def _activation_map(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    eco = cfg.get("ecosystem") or {}
    if not isinstance(eco, dict):
        return {}
    active = eco.get("activated") or {}
    return active if isinstance(active, dict) else {}


def _detect(item: dict[str, Any]) -> dict[str, Any]:
    dest = ecosystem_dir(item["id"])
    installed = False
    if dest.is_dir():
        try:
            installed = any(dest.iterdir())
        except OSError:
            installed = False
    info: dict[str, Any] = {"installed": installed, "path": str(dest)}
    if item.get("id") == "obsidian_kit":
        app = _find_obsidian_app()
        info["app"] = app
        info["app_installed"] = bool(app)
        info["installed"] = bool(app) or installed
        try:
            ver = (dest / "app_version.txt").read_text(encoding="utf-8").strip()
            if ver:
                info["version"] = ver
        except OSError:
            pass
    activated = bool((_activation_map().get(item["id"]) or {}).get("active"))
    # Soft-activated curated packs count as activated even before git clone.
    info["activated"] = activated
    info["soft"] = bool(activated and not installed and item.get("auto_activate"))
    return info


def ensure_auto_activated() -> dict[str, Any]:
    """Enable curated OpenSquilla / OpenScience packs on boot and list refresh.

    Installed packs get a full ``activate()`` wire-up; missing packs get a soft
    curated flag so routing/skills treat them as enabled without downloading.
    """
    ensure_home()
    results: list[dict[str, Any]] = []
    for eco_id in AUTO_ACTIVATE_IDS:
        meta = next((e for e in ECOSYSTEM if e["id"] == eco_id), None)
        if not meta:
            continue
        existing = (_activation_map().get(eco_id) or {})
        if existing.get("user_opt_out"):
            results.append({"id": eco_id, "status": "opt_out"})
            continue
        if existing.get("active"):
            # Re-wire install-dependent bits if the tree appeared since soft-activate
            det = _detect(meta)
            if det.get("installed") and existing.get("soft"):
                try:
                    activate(eco_id, active=True)
                    results.append({"id": eco_id, "status": "upgraded", "soft": False})
                except Exception as exc:  # noqa: BLE001
                    results.append({"id": eco_id, "status": "error", "error": str(exc)})
            else:
                results.append({"id": eco_id, "status": "already", "soft": bool(existing.get("soft"))})
            continue
        try:
            out = activate(eco_id, active=True)
            soft = bool((out.get("detect") or {}).get("soft"))
            results.append({"id": eco_id, "status": "activated", "soft": soft})
        except Exception as exc:  # noqa: BLE001
            results.append({"id": eco_id, "status": "error", "error": str(exc)})
    return {"ok": True, "results": results}


def list_ecosystem(*, ensure_auto: bool = True) -> dict[str, Any]:
    ensure_home()
    if ensure_auto:
        ensure_auto_activated()
    items = []
    for e in ECOSYSTEM:
        items.append({**{k: v for k, v in e.items()}, "detect": _detect(e)})
    return {"ok": True, "home": str(ensure_home()["ecosystem"]), "items": items, "os": os_profile()}


def activate(eco_id: str, *, active: bool = True) -> dict[str, Any]:
    """Wire an ecosystem package into Hub config so workflows use it.

    Curated ``auto_activate`` packs may be soft-activated without a local clone
    (routing/skills flags only). Other packs still require install first.
    """
    from .settings import load_campus_config, save_campus_config

    meta = next((e for e in ECOSYSTEM if e["id"] == eco_id), None)
    if not meta:
        raise ValueError(f"unknown ecosystem: {eco_id}")
    det = _detect(meta)
    installed = bool(det.get("installed"))
    soft = bool(active and not installed and meta.get("auto_activate"))
    if active and not installed and not meta.get("auto_activate"):
        raise ValueError(f"not installed: {eco_id} — install first")

    dest = ecosystem_dir(eco_id)
    cfg = load_campus_config()
    eco = dict(cfg.get("ecosystem") or {})
    activated = dict(eco.get("activated") or {})
    entry: dict[str, Any] = {
        "active": bool(active),
        "path": str(dest),
        "id": eco_id,
        "soft": soft,
    }
    applied: dict[str, Any] = {}

    if active:
        entry.pop("user_opt_out", None)
        if eco_id == "opensquilla":
            # Token-saving flags only — do NOT flip a concrete backend (DeepSeek/…) into hybrid
            routing = dict(cfg.get("routing") or {})
            routing["use_opensquilla"] = True
            routing["token_saving"] = True
            cfg["routing"] = routing
            ali = dict(cfg.get("ali") or {})
            ali["opensquilla_path"] = str(dest)
            ali["default_route"] = ali.get("default_route") or "auto"
            cfg["ali"] = ali
            applied = {"mode": cfg.get("mode"), "routing.use_opensquilla": True, "soft": soft}
        elif eco_id == "openscience":
            ali = dict(cfg.get("ali") or {})
            ali["openscience_path"] = str(dest)
            ali["openscience_active"] = True
            cfg["ali"] = ali
            applied = {"openscience_path": str(dest), "soft": soft}
            # Register SKILL.md trees into Hub skills so chat can use them
            if installed:
                try:
                    from . import skills as skills_mod
                    from .home import skill_dir

                    link = skill_dir("openscience")
                    if not link.exists() and dest.is_dir():
                        try:
                            link.symlink_to(dest, target_is_directory=True)
                            applied["skills_link"] = str(link)
                        except OSError:
                            # Fallback: copy first-level skill dirs that have SKILL.md
                            n = 0
                            for skill_md in dest.rglob("SKILL.md"):
                                if n >= 40:
                                    break
                                try:
                                    skills_mod.install_skill_dir(skill_md.parent)
                                    n += 1
                                except (OSError, ValueError, FileNotFoundError):
                                    continue
                            applied["skills_copied"] = n
                    loaded = []
                    for skill_md in (dest.rglob("SKILL.md") if dest.is_dir() else []):
                        sid = skill_md.parent.name
                        try:
                            skills_mod.load_skill_to_hub(sid)
                            loaded.append(sid)
                        except ValueError:
                            continue
                        if len(loaded) >= 12:
                            break
                    if loaded:
                        applied["hub_loaded"] = loaded
                except Exception:  # noqa: BLE001
                    pass
        elif eco_id == "scientific-agent-skills":
            skills_src = dest / "skills"
            ali = dict(cfg.get("ali") or {})
            ali["scientific_skills_path"] = str(skills_src if skills_src.is_dir() else dest)
            ali["scientific_skills_active"] = True
            cfg["ali"] = ali
            applied = {"scientific_skills_path": ali["scientific_skills_path"], "soft": soft}
            if installed:
                try:
                    from . import skills as skills_mod
                    from .home import skill_dir

                    link = skill_dir("scientific-agent-skills")
                    if not link.exists() and dest.is_dir():
                        link.symlink_to(dest, target_is_directory=True)
                        applied["skills_link"] = str(link)
                    loaded = []
                    root = skills_src if skills_src.is_dir() else dest
                    for skill_md in root.rglob("SKILL.md"):
                        sid = skill_md.parent.name
                        try:
                            skills_mod.load_skill_to_hub(sid)
                            loaded.append(sid)
                        except ValueError:
                            continue
                        if len(loaded) >= 12:
                            break
                    if loaded:
                        applied["hub_loaded"] = loaded
                except OSError:
                    pass
        elif eco_id == "obsidian_kit":
            obs = dict(cfg.get("obsidian") or {})
            obs["vault_path"] = str(dest)
            obs["ai_inbox"] = obs.get("ai_inbox") or "00_Inbox/AI_Candidates"
            if not obs.get("allowed_roots"):
                obs["allowed_roots"] = [
                    "00_Inbox",
                    "10_Projects",
                    "20_Science",
                    "90_Archive",
                ]
            cfg["obsidian"] = obs
            applied = {"vault_path": str(dest), "ai_inbox": obs["ai_inbox"]}
        elif eco_id == "notion_kit":
            ali = dict(cfg.get("ali") or {})
            ali["notion_kit_path"] = str(dest)
            ali["notion_active"] = True
            cfg["ali"] = ali
            applied = {"notion_kit_path": str(dest)}
        elif eco_id == "hermes-self-evolution":
            ali = dict(cfg.get("ali") or {})
            ali["hermes_self_evolution_path"] = str(dest)
            ali["hermes_self_evolution_active"] = True
            cfg["ali"] = ali
            applied = {
                "hermes_self_evolution_path": str(dest),
                "note": "Optional GEPA engine; Hub guided evolution works without it.",
            }
        activated[eco_id] = entry
    else:
        # Keep a tombstone for curated packs so boot/list auto-activate respects opt-out.
        if meta.get("auto_activate") or eco_id in AUTO_ACTIVATE_IDS:
            activated[eco_id] = {
                "active": False,
                "id": eco_id,
                "path": str(dest),
                "user_opt_out": True,
            }
        else:
            activated.pop(eco_id, None)
        if eco_id == "opensquilla":
            routing = dict(cfg.get("routing") or {})
            routing["use_opensquilla"] = False
            routing["token_saving"] = False
            cfg["routing"] = routing
        elif eco_id == "openscience":
            ali = dict(cfg.get("ali") or {})
            ali["openscience_active"] = False
            cfg["ali"] = ali
        elif eco_id == "scientific-agent-skills":
            ali = dict(cfg.get("ali") or {})
            ali["scientific_skills_active"] = False
            cfg["ali"] = ali
        elif eco_id == "obsidian_kit":
            obs = dict(cfg.get("obsidian") or {})
            if str(obs.get("vault_path") or "") == str(dest):
                obs["vault_path"] = ""
            cfg["obsidian"] = obs
        elif eco_id == "notion_kit":
            ali = dict(cfg.get("ali") or {})
            ali["notion_active"] = False
            cfg["ali"] = ali
        elif eco_id == "hermes-self-evolution":
            ali = dict(cfg.get("ali") or {})
            ali["hermes_self_evolution_active"] = False
            cfg["ali"] = ali

    eco["activated"] = activated
    cfg["ecosystem"] = eco
    save_campus_config(cfg)
    return {
        "ok": True,
        "id": eco_id,
        "active": bool(active),
        "applied": applied,
        "detect": _detect(meta),
        "note_zh": ("已激活" if active else "已取消激活") + f"：{meta.get('label_zh') or meta.get('label')}",
        "note_en": ("Activated" if active else "Deactivated") + f": {meta.get('label')}",
        **list_ecosystem(ensure_auto=False),
    }


def ecosystem_context_block(cfg: dict[str, Any] | None = None) -> str:
    """System-context hints for activated ecosystem packages."""
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    ali = cfg.get("ali") or {}
    lines: list[str] = []
    activated = _activation_map(cfg)
    if (activated.get("opensquilla") or {}).get("active") or (cfg.get("routing") or {}).get("use_opensquilla"):
        path = ali.get("opensquilla_path") or str(ecosystem_dir("opensquilla"))
        lines.append(
            f"OpenSquilla token-saving routing is ACTIVE (path={path}). "
            "Prefer cheapest capable model tier (C0–C3); avoid over-routing to expensive models."
        )
    if ali.get("openscience_active") or (activated.get("openscience") or {}).get("active"):
        path = ali.get("openscience_path") or str(ecosystem_dir("openscience"))
        lines.append(
            f"OpenScience toolkit is ACTIVE at {path}. "
            "For data analysis / open-science tasks, use workflows and skills under that tree when relevant."
        )
    if ali.get("scientific_skills_active") or (activated.get("scientific-agent-skills") or {}).get("active"):
        path = ali.get("scientific_skills_path") or str(ecosystem_dir("scientific-agent-skills") / "skills")
        lines.append(
            f"Scientific Agent Skills pack is ACTIVE ({path}). "
            "Prefer those lab/research skills for vibe-coding / Codex-style science workflows."
        )
    if ali.get("hermes_self_evolution_active") or (activated.get("hermes-self-evolution") or {}).get("active"):
        path = ali.get("hermes_self_evolution_path") or str(ecosystem_dir("hermes-self-evolution"))
        lines.append(
            f"Nous hermes-agent-self-evolution pack is available at {path}. "
            "Hub guided self-evolution (Control Center → 生态/Claws → 自我进化) uses Hub LLM by default; "
            "optional local GEPA lives in that tree."
        )
    obs = cfg.get("obsidian") or {}
    if (activated.get("obsidian_kit") or {}).get("active") or obs.get("vault_path"):
        if obs.get("vault_path"):
            lines.append(
                f"Obsidian knowledge kit ACTIVE — vault={obs['vault_path']}; "
                f"AI inbox={obs.get('ai_inbox') or '00_Inbox/AI_Candidates'}."
            )
    if not lines:
        return ""
    return "## Ecosystem (activated)\n" + "\n".join(f"- {x}" for x in lines)


def _scaffold_obsidian(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "00_Inbox" / "AI_Candidates").mkdir(parents=True, exist_ok=True)
    (dest / "10_Projects").mkdir(parents=True, exist_ok=True)
    (dest / "20_Science").mkdir(parents=True, exist_ok=True)
    (dest / "90_Archive").mkdir(parents=True, exist_ok=True)
    (dest / "README.md").write_text(
        "# Obsidian Knowledge Kit (Agent Hub)\n\n"
        "1. Obsidian desktop app is installed (or detected) by Agent Hub.\n"
        "2. Open this folder as a vault, or set Control Center → Obsidian vault_path here.\n"
        "3. AI writes only to `00_Inbox/AI_Candidates` until approved.\n",
        encoding="utf-8",
    )


def _scaffold_notion(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    (dest / ".env.example").write_text(
        "NOTION_TOKEN=secret_xxx\nNOTION_PARENT_PAGE_ID=\n",
        encoding="utf-8",
    )
    (dest / "README.md").write_text(
        "# Notion Bridge Kit (Agent-CLI)\n\n"
        "1. Create a Notion integration and copy the token.\n"
        "2. Copy `.env.example` → `.env` and fill values.\n"
        "3. Use Agent-CLI knowledge workflows to push reviewed notes.\n",
        encoding="utf-8",
    )


def start_install(eco_id: str) -> dict[str, Any]:
    meta = next((e for e in ECOSYSTEM if e["id"] == eco_id), None)
    if not meta:
        raise ValueError(f"unknown ecosystem: {eco_id}")
    ensure_home()
    dest = ecosystem_dir(eco_id)
    log_dir = ensure_home()["logs"]
    job_id = str(uuid.uuid4())
    log_path = log_dir / f"eco-{job_id}.log"
    step_defs = [
        {"id": "prepare", "label_zh": "准备", "label_en": "Prepare", "pct": 10},
        {"id": "install", "label_zh": "下载安装", "label_en": "Install", "pct": 55},
        {"id": "verify", "label_zh": "测试验证", "label_en": "Verify", "pct": 85},
        {"id": "done", "label_zh": "完成", "label_en": "Done", "pct": 100},
    ]
    job: dict[str, Any] = {
        "id": job_id,
        "eco_id": eco_id,
        "kind": "ecosystem",
        "status": "running",
        "step": "prepare",
        "pct": 5,
        "steps": step_defs,
        "log_path": str(log_path),
        "dest": str(dest),
        "started_at": time.time(),
        "finished_at": None,
        "error": None,
        "verify": None,
        "debug": [],
    }
    with _lock:
        _jobs[job_id] = job

    def _set_step(step_id: str, pct: int | None = None) -> None:
        job["step"] = step_id
        for s in step_defs:
            if s["id"] == step_id and pct is None:
                job["pct"] = s["pct"]
                return
        if pct is not None:
            job["pct"] = pct

    def _verify(log) -> dict[str, Any]:
        info = _detect(meta)
        ok = bool(info.get("installed"))
        if eco_id == "obsidian_kit":
            ok = bool(info.get("app_installed") or info.get("installed"))
        log.write(f"\n# verify: ok={ok} path={info.get('path')} app={info.get('app') or ''}\n")
        log.flush()
        return {"ok": ok, "detect": info}

    def _run() -> None:
        try:
            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"# install ecosystem {eco_id} → {dest}\n")
                _set_step("prepare", 12)
                _set_step("install", 30)
                if meta.get("scaffold"):
                    if eco_id == "obsidian_kit":
                        _scaffold_obsidian(dest)
                        if meta.get("install_app"):
                            job["pct"] = 50
                            info = _install_obsidian_app(dest, log)
                            job["app"] = info.get("app")
                            job["version"] = info.get("version")
                    else:
                        _scaffold_notion(dest)
                    log.write("# scaffolded\n")
                else:
                    git = meta.get("git")
                    if not git:
                        raise ValueError("no git url")
                    if dest.exists():
                        shutil.rmtree(dest)
                    log.write(f"$ git clone {git} {dest}\n")
                    log.flush()
                    r = subprocess.run(
                        ["git", "clone", "--depth", "1", git, str(dest)],
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        timeout=600,
                    )
                    if r.returncode != 0:
                        raise RuntimeError("git clone failed")
                    posts = (
                        meta.get("post_windows")
                        if platform.system() == "Windows"
                        else meta.get("post_posix")
                    )
                    for cmd in posts or []:
                        log.write(f"$ {cmd}\n")
                        log.flush()
                        r2 = subprocess.run(
                            cmd,
                            shell=True,
                            cwd=str(dest),
                            stdout=log,
                            stderr=subprocess.STDOUT,
                            text=True,
                            timeout=900,
                            env={**os.environ, "AGENT_CLI_HOME": str(ensure_home()["root"])},
                        )
                        if r2.returncode != 0:
                            log.write(f"# post-step exit {r2.returncode} (continuing)\n")
                _set_step("verify", 88)
                log.write("\n# step: verify\n")
                verify = _verify(log)
                if not verify.get("ok"):
                    # light debug: ensure dest readable
                    try:
                        dest.mkdir(parents=True, exist_ok=True)
                        job["debug"] = ["ensured dest exists", f"path={dest}"]
                        log.write(f"# debug: ensured {dest}\n")
                    except OSError as exc:
                        job["debug"] = [str(exc)]
                    verify = _verify(log)
                job["verify"] = verify
                if not verify.get("ok"):
                    job["status"] = "failed"
                    job["step"] = "verify"
                    job["error"] = "verify failed — install present but not working"
                    job["finished_at"] = time.time()
                    job["pct"] = 90
                    log.write("# VERIFY FAILED\n")
                    return
                _set_step("done", 100)
                job["status"] = "ok"
                job["finished_at"] = time.time()
                log.write("# done — verified\n")
                if meta.get("auto_activate") or eco_id in AUTO_ACTIVATE_IDS:
                    try:
                        activate(eco_id, active=True)
                        log.write(f"# auto-activated {eco_id}\n")
                    except Exception as exc:  # noqa: BLE001
                        log.write(f"# auto-activate skipped: {exc}\n")
        except Exception as exc:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(exc)
            job["finished_at"] = time.time()

    threading.Thread(target=_run, daemon=True, name=f"eco-{eco_id}").start()
    return {"ok": True, "job": dict(job)}


def job_status(job_id: str) -> dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
    if not job:
        raise FileNotFoundError(job_id)
    out = dict(job)
    try:
        out["log"] = Path(job["log_path"]).read_text(encoding="utf-8", errors="replace")[-10000:]
    except OSError:
        out["log"] = ""
    return {"ok": True, "job": out}

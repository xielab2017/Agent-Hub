"""Multi-agent / Claw runtime catalog — detect, install recipes, auto-optimize."""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import STATE_DIR, ensure_state_dirs, hermes_home
from .settings import load_campus_config, save_campus_config

INSTALL_LOG_DIR = STATE_DIR / "install-logs"
CLAW_META_FILE = STATE_DIR / "claw-meta.json"
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.RLock()
_VERSION_TOKEN_RE = re.compile(
    r"(?:^|[\s:])v?(\d{4}\.\d{1,2}\.\d{1,2}|\d+\.\d+(?:\.\d+)?(?:[-+][0-9A-Za-z.]+)?)",
    re.I,
)

# Curated runtimes. install.commands are the ONLY scripts Agent-CLI will execute.
RUNTIMES: list[dict[str, Any]] = [
    {
        "id": "direct",
        "family": "builtin",
        "label": "Direct LLM",
        "label_zh": "直连模型",
        "desc": "OpenAI-compatible chat without a local agent runtime. Works with all providers.",
        "desc_zh": "不依赖本地 Agent，直连任意 OpenAI 兼容模型；聊天窗口默认兜底。",
        "homepage": "",
        "docs": "",
        "detect": {"whiches": [], "always": True},
        "install": {"kind": "none"},
        "optimize": {
            "ali.agent_runtime": "direct",
            "ali.default_route": "auto",
            "note_zh": "所有厂商模型通用；在「后端/模型」配置即可。",
            "note_en": "Universal model path — configure Backend / Models only.",
        },
    },
    {
        "id": "hermes",
        "family": "hermes",
        "label": "Hermes Agent",
        "label_zh": "Hermes Agent",
        "desc": "NousResearch Hermes — skills, tools, SOUL.md, campus office workflows.",
        "desc_zh": "NousResearch Hermes：Skill / 工具 / SOUL.md / 校园办公工作流。",
        "homepage": "https://github.com/NousResearch/hermes-agent",
        "docs": "https://hermes-agent.nousresearch.com/docs/getting-started/installation",
        "detect": {
            "whiches": ["hermes"],
            "paths": [
                "~/.hermes/hermes-agent/run_agent.py",
                "~/.hermes/config.yaml",
                "~/.hermes/SOUL.md",
            ],
        },
        "install": {
            "kind": "script",
            "posix": [
                "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser"
            ],
            "windows": [
                "iex (irm https://hermes-agent.nousresearch.com/install.ps1)"
            ],
            "verify": ["hermes", "--version"],
        },
        "optimize": {
            "ali.agent_runtime": "hermes",
            "ali.default_route": "auto",
            "mode": "single",
            "note_zh": "启用 Hermes 运行时 + Auto 路由；建议配置 SOUL 与 Skills。",
            "note_en": "Activate Hermes runtime + Auto routing; configure SOUL and Skills.",
        },
    },
    {
        "id": "openclaw",
        "family": "claw",
        "label": "OpenClaw",
        "label_zh": "OpenClaw",
        "desc": "Personal AI assistant OS — gateway, channels, skills (Node).",
        "desc_zh": "个人 AI 助手运行时：Gateway / 通道 / Skills（Node）。",
        "homepage": "https://github.com/openclaw/openclaw",
        "docs": "https://docs.openclaw.ai/install",
        "detect": {"whiches": ["openclaw"], "paths": ["~/.openclaw"]},
        "install": {
            "kind": "script",
            "posix": ["curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard"],
            "windows": ["iwr -useb https://openclaw.ai/install.ps1 | iex"],
            "alt_posix": [
                "npm install -g openclaw@latest",
                "openclaw onboard --install-daemon",
            ],
            "verify": ["openclaw", "--version"],
        },
        "optimize": {
            "ali.agent_runtime": "openclaw",
            "backend.type": "openrouter",
            "note_zh": "OpenClaw 常用 OpenRouter/多模型；安装后请运行 openclaw onboard。",
            "note_en": "OpenClaw often uses multi-model routers; run openclaw onboard after install.",
        },
    },
    {
        "id": "nanobot",
        "family": "claw",
        "label": "NanoBot",
        "label_zh": "NanoBot",
        "desc": "HKUDS nanobot — lightweight OpenClaw-inspired Python agent.",
        "desc_zh": "HKUDS nanobot：轻量 Python Agent（OpenClaw 精神）。",
        "homepage": "https://github.com/HKUDS/nanobot",
        "docs": "https://github.com/HKUDS/nanobot",
        "detect": {"whiches": ["nanobot"]},
        "install": {
            "kind": "script",
            "posix": ["pip3 install -U nanobot-ai", "nanobot onboard"],
            "windows": ["pip install -U nanobot-ai", "nanobot onboard"],
            "alt_posix": ["uv tool install nanobot-ai"],
            "verify": ["nanobot", "--help"],
        },
        "optimize": {
            "ali.agent_runtime": "nanobot",
            "note_zh": "轻量 Agent；模型仍走控制中心后端配置。",
            "note_en": "Lightweight agent; models still use Control Center backend.",
        },
    },
    {
        "id": "nano_claw",
        "family": "claw",
        "label": "nano-claw",
        "label_zh": "nano-claw",
        "desc": "TypeScript nano-claw (hustcc) — Node port of nanobot.",
        "desc_zh": "TypeScript nano-claw（hustcc）：nanobot 的 Node 实现。",
        "homepage": "https://github.com/hustcc/nano-claw",
        "docs": "https://github.com/hustcc/nano-claw",
        "detect": {"whiches": ["nano-claw"]},
        "install": {
            "kind": "script",
            "posix": ["npm install -g nano-claw", "nano-claw onboard"],
            "windows": ["npm install -g nano-claw", "nano-claw onboard"],
            "verify": ["nano-claw", "--version"],
        },
        "optimize": {
            "ali.agent_runtime": "nano_claw",
            "note_zh": "Node 轻量 Claw；适合本地快速试验。",
            "note_en": "Node lightweight claw for local experiments.",
        },
    },
    {
        "id": "qqclaw",
        "family": "claw",
        "label": "QQClaw (QQ Bot)",
        "label_zh": "QQClaw（QQ 机器人）",
        "desc": "OpenClaw + Tencent QQ Bot channel plugin.",
        "desc_zh": "基于 OpenClaw 的腾讯 QQ 机器人通道（需先装 OpenClaw）。",
        "homepage": "https://github.com/tencent-connect/openclaw-qqbot",
        "docs": "https://github.com/tencent-connect/openclaw-qqbot",
        "detect": {
            "whiches": ["openclaw"],
            "hint": "plugin @tencent-connect/openclaw-qqbot",
        },
        "requires": ["openclaw"],
        "install": {
            "kind": "script",
            "posix": [
                "openclaw plugins install @tencent-connect/openclaw-qqbot@latest",
            ],
            "windows": [
                "openclaw plugins install @tencent-connect/openclaw-qqbot@latest",
            ],
            "notes_zh": "首次还需：openclaw channels add --channel qqbot --token 'AppID:AppSecret' 后 gateway restart。",
            "notes_en": "Then: openclaw channels add --channel qqbot --token 'AppID:AppSecret' && openclaw gateway restart",
            "one_liner_docs": "https://raw.githubusercontent.com/tencent-connect/openclaw-qqbot/main/scripts/upgrade-via-npm.sh",
        },
        "optimize": {
            "ali.agent_runtime": "openclaw",
            "note_zh": "QQClaw 复用 OpenClaw 运行时；在 OpenClaw 里配 QQ 通道。",
            "note_en": "QQClaw reuses OpenClaw runtime; configure QQ channel there.",
        },
    },
    {
        "id": "aliyun_claw",
        "family": "claw",
        "label": "Alibaba Cloud OpenClaw",
        "label_zh": "阿里云 OpenClaw",
        "desc": "OpenClaw on Alibaba Cloud Simple Application Server marketplace image + QQ integration guides.",
        "desc_zh": "阿里云轻量应用服务器 OpenClaw 镜像与 QQ 集成（官方文档）。",
        "homepage": "https://help.aliyun.com/zh/simple-application-server/use-cases/openclaw-qq-integration",
        "docs": "https://developer.aliyun.com/article/1720844",
        "detect": {"whiches": ["openclaw"], "cloud": True},
        "install": {
            "kind": "link",
            "posix": [],
            "windows": [],
            "marketplace_hint_zh": "阿里云控制台 → 轻量应用服务器 → 应用镜像 → OpenClaw；本地仍可用 OpenClaw 官方安装脚本。",
            "fallback_posix": ["curl -fsSL https://openclaw.ai/install.sh | bash -s -- --no-onboard"],
        },
        "optimize": {
            "ali.agent_runtime": "openclaw",
            "backend.type": "openai",  # often DashScope / Qwen via compatible endpoint
            "note_zh": "阿里云场景常用通义/百炼兼容端点；后端选 OpenAI 兼容并填 DashScope base_url。",
            "note_en": "Aliyun setups often use Qwen-compatible endpoints; set OpenAI-compatible base_url.",
        },
    },
    {
        "id": "nanoclaw",
        "family": "claw",
        "label": "NanoClaw (container)",
        "label_zh": "NanoClaw（容器）",
        "desc": "nanocoai/nanoclaw — Dockerized claw with Claude Code harness.",
        "desc_zh": "nanocoai/nanoclaw：Docker 化 Claw（Claude Code 工具链）。",
        "homepage": "https://github.com/nanocoai/nanoclaw",
        "docs": "https://github.com/nanocoai/nanoclaw",
        "detect": {"whiches": [], "paths": []},
        "install": {
            "kind": "script",
            "posix": [
                "git clone https://github.com/nanocoai/nanoclaw.git ~/nanoclaw && cd ~/nanoclaw && bash nanoclaw.sh"
            ],
            "windows": [],
            "notes_en": "Requires Docker Desktop / Engine. Prefer interactive terminal for first setup.",
            "notes_zh": "需要 Docker；首次安装建议在终端交互完成。",
            "interactive": True,
        },
        "optimize": {
            "ali.agent_runtime": "direct",
            "note_zh": "容器 Claw 独立运行；Agent-CLI 仍可用 Direct LLM 对话同一模型。",
            "note_en": "Container claw runs separately; Agent-CLI Direct LLM can share providers.",
        },
    },
]


def get_runtime(runtime_id: str) -> dict[str, Any] | None:
    for r in RUNTIMES:
        if r["id"] == runtime_id:
            return r
    return None


def _expand(p: str) -> Path:
    return Path(p).expanduser()


def _which(cmd: str) -> str | None:
    return shutil.which(cmd)


def detect_runtime(meta: dict[str, Any]) -> dict[str, Any]:
    det = meta.get("detect") or {}
    if det.get("always"):
        return {"installed": True, "detail": "builtin", "bin": ""}
    bins = []
    for w in det.get("whiches") or []:
        path = _which(w)
        if path:
            bins.append({"name": w, "path": path})
    path_hits = []
    for p in det.get("paths") or []:
        ep = _expand(p)
        if ep.exists():
            path_hits.append(str(ep))
    installed = bool(bins) or bool(path_hits)
    # qqclaw: openclaw present is weak signal only
    if meta["id"] == "qqclaw":
        installed = bool(_which("openclaw"))
    return {
        "installed": installed,
        "bins": bins,
        "paths": path_hits,
        "detail": "found" if installed else "not found",
        "cloud": bool(det.get("cloud")),
    }


def _normalize_version_text(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    if not line:
        return ""
    # Prefer an explicit "v1.2.3" / "version 1.2.3" token when present.
    for m in _VERSION_TOKEN_RE.finditer(line):
        token = m.group(1)
        # Skip lone years that are not dotted versions
        if token.count(".") >= 1:
            return token
    # Fall back to a short first line (CLIs often print a banner)
    if len(line) > 96:
        line = line[:93] + "…"
    return line


def _run_version_cmd(argv: list[str], *, timeout: float = 6.0) -> str:
    if not argv:
        return ""
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if proc.returncode != 0:
        return ""
    out = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    # Reject obvious runtime/engine requirement banners (not the claw version)
    low = out.lower()
    if "is required" in low and ("node.js" in low or "nodejs" in low):
        return ""
    return _normalize_version_text(out)


def _read_package_json_version(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ""
    if not isinstance(data, dict):
        return ""
    ver = str(data.get("version") or "").strip()
    return ver


def _iter_package_json_candidates(runtime_id: str) -> list[Path]:
    from .home import runtime_dir

    pdir = runtime_dir(runtime_id)
    names = {
        "hermes": ["hermes-agent", "hermes"],
        "openclaw": ["openclaw"],
        "aliyun_claw": ["openclaw"],
        "qqclaw": ["@tencent-connect/openclaw-qqbot", "openclaw-qqbot", "openclaw"],
        "nano_claw": ["nano-claw", "nano_claw"],
        "nanobot": ["nanobot-ai", "nanobot"],
        "nanoclaw": ["nanoclaw"],
    }.get(runtime_id, [runtime_id.replace("_", "-"), runtime_id])
    cands: list[Path] = []
    # Prefer nested package under node_modules (npm --prefix installs)
    for name in names:
        cands.append(pdir / "node_modules" / name / "package.json")
    cands.append(pdir / "package.json")
    if runtime_id == "hermes":
        cands.insert(0, pdir / "hermes-agent" / "package.json")
        cands.append(_expand("~/.hermes/hermes-agent/package.json"))
    if runtime_id == "nanoclaw":
        cands.append(Path.home() / "nanoclaw" / "package.json")
    if runtime_id in ("aliyun_claw", "qqclaw"):
        oc = runtime_dir("openclaw")
        cands.append(oc / "node_modules" / "openclaw" / "package.json")
        cands.append(oc / "package.json")
    # Deduce existing unique paths
    seen: set[str] = set()
    out: list[Path] = []
    for p in cands:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def _parallel_bin_candidates(runtime_id: str, names: list[str]) -> list[Path]:
    from .home import runtime_dir

    pdir = runtime_dir(runtime_id)
    bins: list[Path] = []
    for name in names:
        bins.extend(
            [
                pdir / "bin" / name,
                pdir / "node_modules" / ".bin" / name,
                pdir / "hermes-agent" / "bin" / name,
            ]
        )
    if runtime_id in ("aliyun_claw", "qqclaw"):
        oc = runtime_dir("openclaw")
        for name in ("openclaw",):
            bins.extend([oc / "bin" / name, oc / "node_modules" / ".bin" / name])
    if runtime_id == "nanoclaw":
        bins.append(Path.home() / "nanoclaw" / "nanoclaw.sh")
    return bins


def _bin_names_for_runtime(meta: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for w in (meta.get("detect") or {}).get("whiches") or []:
        if w and w not in names:
            names.append(str(w))
    verify = (meta.get("install") or {}).get("verify") or []
    if isinstance(verify, list) and verify:
        first = str(verify[0] or "").strip()
        if first and first not in names and not first.startswith("-"):
            names.insert(0, first)
    rid = meta.get("id") or ""
    extras = {
        "hermes": ["hermes"],
        "openclaw": ["openclaw"],
        "nanobot": ["nanobot"],
        "nano_claw": ["nano-claw"],
        "qqclaw": ["openclaw"],
        "aliyun_claw": ["openclaw"],
    }.get(str(rid), [])
    for e in extras:
        if e not in names:
            names.append(e)
    return names


def detect_runtime_version(runtime_id: str) -> dict[str, Any]:
    """Best-effort version probe: parallel bin → PATH → package.json → pip."""
    meta = get_runtime(runtime_id)
    if not meta:
        return {"version": "", "source": "", "raw": ""}
    if runtime_id == "direct":
        from .config import VERSION

        return {"version": str(VERSION), "source": "hub", "raw": str(VERSION)}

    names = _bin_names_for_runtime(meta)
    # Node claws: Hub parallel package.json is more trustworthy than a failing
    # local bin (engine mismatch) or an older global PATH install.
    prefer_pkg_when_parallel = runtime_id in {
        "openclaw",
        "nano_claw",
        "qqclaw",
        "aliyun_claw",
        "nanoclaw",
    }

    # 1) Parallel-dir binaries first (Hub-managed installs)
    for bin_path in _parallel_bin_candidates(runtime_id, names):
        if not bin_path.is_file():
            continue
        ver = _run_version_cmd([str(bin_path), "--version"])
        if ver:
            return {"version": ver, "source": "parallel-bin", "raw": ver, "bin": str(bin_path)}

    # 2) Parallel package.json for Node claws when Hub tree exists
    if prefer_pkg_when_parallel and _parallel_present(runtime_id):
        for pkg in _iter_package_json_candidates(runtime_id):
            if not pkg.is_file():
                continue
            ver = _read_package_json_version(pkg)
            if ver:
                return {"version": ver, "source": "package.json", "raw": ver, "path": str(pkg)}

    # 3) Global PATH bins
    for name in names:
        path = _which(name)
        if not path:
            continue
        ver = _run_version_cmd([path, "--version"])
        if ver:
            return {"version": ver, "source": "path", "raw": ver, "bin": path}
        verify = (meta.get("install") or {}).get("verify") or []
        if isinstance(verify, list) and len(verify) >= 2 and str(verify[0]) == name:
            argv = [path] + [str(x) for x in verify[1:]]
            ver = _run_version_cmd(argv)
            if ver and (_VERSION_TOKEN_RE.search(ver) or "--version" in " ".join(argv)):
                return {"version": ver, "source": "path-verify", "raw": ver, "bin": path}

    # 4) package.json under parallel / known trees (fallback)
    for pkg in _iter_package_json_candidates(runtime_id):
        if not pkg.is_file():
            continue
        ver = _read_package_json_version(pkg)
        if ver:
            return {"version": ver, "source": "package.json", "raw": ver, "path": str(pkg)}

    # 5) pip show for Python claws (nanobot)
    if runtime_id == "nanobot":
        for pip_cmd in ("pip3", "pip"):
            if not _which(pip_cmd):
                continue
            try:
                proc = subprocess.run(
                    [pip_cmd, "show", "nanobot-ai"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
            except (OSError, subprocess.TimeoutExpired):
                continue
            if proc.returncode != 0:
                continue
            for line in (proc.stdout or "").splitlines():
                if line.lower().startswith("version:"):
                    ver = line.split(":", 1)[1].strip()
                    if ver:
                        return {"version": ver, "source": "pip", "raw": ver}

    # 6) Alias claws inherit OpenClaw version when local probe is empty
    if runtime_id in ("aliyun_claw", "qqclaw"):
        parent = detect_runtime_version("openclaw")
        if parent.get("version"):
            return {**parent, "source": f"via-openclaw:{parent.get('source') or ''}"}

    return {"version": "", "source": "", "raw": ""}


def _load_claw_meta_store() -> dict[str, Any]:
    """Merge campus `ali.claw_meta` with optional STATE_DIR/claw-meta.json."""
    store: dict[str, Any] = {}
    try:
        if CLAW_META_FILE.is_file():
            data = json.loads(CLAW_META_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                claws = data.get("claws") if isinstance(data.get("claws"), dict) else data
                if isinstance(claws, dict):
                    for k, v in claws.items():
                        if isinstance(v, dict):
                            store[str(k)] = dict(v)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    try:
        cfg = load_campus_config()
        ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
        campus = ali.get("claw_meta") if isinstance(ali.get("claw_meta"), dict) else {}
        for k, v in campus.items():
            if isinstance(v, dict):
                cur = store.get(str(k)) or {}
                cur.update(v)
                store[str(k)] = cur
    except Exception:  # noqa: BLE001
        pass
    return store


def get_claw_meta(runtime_id: str) -> dict[str, Any]:
    store = _load_claw_meta_store()
    meta = store.get(runtime_id) if isinstance(store.get(runtime_id), dict) else {}
    return {
        "version": str(meta.get("version") or "").strip(),
        "last_upgraded_at": str(meta.get("last_upgraded_at") or "").strip(),
        "last_installed_at": str(meta.get("last_installed_at") or "").strip(),
    }


def record_claw_meta(
    runtime_id: str,
    *,
    version: str = "",
    upgraded: bool = False,
    installed: bool = False,
) -> dict[str, Any]:
    """Persist claw version / last upgrade (and optional install) timestamps."""
    runtime_id = (runtime_id or "").strip()
    if not runtime_id or runtime_id == "direct":
        return {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ensure_state_dirs()

    # STATE_DIR JSON (always writable)
    file_store: dict[str, Any] = {"version": 1, "claws": {}}
    try:
        if CLAW_META_FILE.is_file():
            raw = json.loads(CLAW_META_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                claws = raw.get("claws") if isinstance(raw.get("claws"), dict) else {
                    k: v for k, v in raw.items() if isinstance(v, dict) and k != "version"
                }
                file_store["claws"] = dict(claws)
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    entry = dict(file_store["claws"].get(runtime_id) or {})
    if version:
        entry["version"] = str(version).strip()
    if upgraded:
        entry["last_upgraded_at"] = now
    if installed:
        entry["last_installed_at"] = now
        if not entry.get("last_upgraded_at"):
            # First Hub install counts as baseline "upgrade" time for display fallback
            pass
    file_store["claws"][runtime_id] = entry
    try:
        CLAW_META_FILE.write_text(json.dumps(file_store, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except OSError:
        pass

    # Mirror into campus config ali.claw_meta
    try:
        cfg, ali = _ali_cfg()
        claw_meta = ali.setdefault("claw_meta", {})
        if not isinstance(claw_meta, dict):
            claw_meta = {}
            ali["claw_meta"] = claw_meta
        cur = dict(claw_meta.get(runtime_id) or {})
        cur.update(entry)
        claw_meta[runtime_id] = cur
        save_campus_config(cfg)
    except Exception:  # noqa: BLE001
        pass
    return dict(entry)


def _parallel_present(runtime_id: str) -> bool:
    from .home import runtime_dir

    pdir = runtime_dir(runtime_id)
    try:
        return pdir.is_dir() and any(pdir.iterdir())
    except OSError:
        return False


def _runtime_present(runtime_id: str) -> bool:
    """True if claw is on PATH or has its native home / known paths (not parallel cache)."""
    meta = get_runtime(runtime_id)
    if not meta:
        return False
    if (meta.get("detect") or {}).get("always"):
        return True
    if detect_runtime(meta).get("installed"):
        return True
    if runtime_id == "nanoclaw":
        return (Path.home() / "nanoclaw").is_dir()
    if runtime_id in ("aliyun_claw", "qqclaw"):
        return _runtime_present("openclaw")
    return False


def upgrade_supported(runtime_id: str) -> dict[str, Any]:
    """Whether one-click upgrade applies; includes commands or skip reason."""
    meta = get_runtime(runtime_id)
    if not meta:
        return {"supported": False, "reason": f"unknown runtime: {runtime_id}", "commands": []}
    if runtime_id == "direct":
        return {"supported": False, "reason": "Direct LLM has nothing to upgrade", "commands": [], "installed": True}
    inst = meta.get("install") or {}
    kind = inst.get("kind")
    if kind in (None, "none"):
        return {"supported": False, "reason": "this runtime has no upgrade path", "commands": []}
    try:
        cmds = upgrade_commands(runtime_id)
    except ValueError as exc:
        return {"supported": False, "reason": str(exc), "commands": []}
    if not cmds:
        return {"supported": False, "reason": "no upgrade commands for this OS", "commands": []}
    return {"supported": True, "reason": "", "commands": cmds, "installed": _runtime_present(runtime_id)}


# When active=auto: try user preference first, then this fallback chain.
_AUTO_FALLBACK = ("hermes", "openclaw", "nanobot", "nano_claw", "direct")
_DEFAULT_AUTO_RUNTIME = "hermes"


def _normalize_auto_runtime(prefer: str | None) -> str:
    prefer = (prefer or "").strip() or _DEFAULT_AUTO_RUNTIME
    if prefer == "auto" or not get_runtime(prefer):
        return _DEFAULT_AUTO_RUNTIME
    return prefer


def normalize_auto_runtime(prefer: str | None) -> str:
    """Public alias: normalize `ali.auto_runtime` preference."""
    return _normalize_auto_runtime(prefer)


def _runtime_available(row: dict[str, Any]) -> bool:
    """Installed/detected, or always-on builtins like direct."""
    det = row.get("detect") or {}
    if det.get("installed"):
        return True
    rid = row.get("id")
    meta = get_runtime(str(rid or ""))
    return bool(meta and (meta.get("detect") or {}).get("always"))


def _resolve_auto(items: list[dict[str, Any]], auto_prefer: str) -> str:
    prefer = _normalize_auto_runtime(auto_prefer)
    row = next((x for x in items if x["id"] == prefer), None)
    if row and _runtime_available(row):
        return prefer
    for cand in _AUTO_FALLBACK:
        if cand == prefer:
            continue
        row = next((x for x in items if x["id"] == cand), None)
        if row and _runtime_available(row):
            return cand
    return "direct"


def list_runtimes() -> dict[str, Any]:
    from .home import ensure_home, native_claw_home, os_profile, runtime_dir

    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    active = (ali.get("agent_runtime") or "auto").strip() or "auto"
    auto_runtime = _normalize_auto_runtime(str(ali.get("auto_runtime") or ""))
    osinfo = os_profile()
    items = []
    for r in RUNTIMES:
        d = detect_runtime(r)
        pdir = runtime_dir(r["id"])
        parallel = False
        try:
            parallel = pdir.is_dir() and any(pdir.iterdir())
        except OSError:
            parallel = False
        # Parallel cache is NOT "installed" — only PATH / native homes count
        if parallel:
            d = dict(d)
            d["parallel_path"] = str(pdir)
            d["parallel_cache"] = True
        native = native_claw_home(r["id"])
        if r["id"] == "nanoclaw" and (Path.home() / "nanoclaw").is_dir():
            d = dict(d)
            d["installed"] = True
            d["paths"] = list(d.get("paths") or []) + [str(Path.home() / "nanoclaw")]
        if r["id"] in ("aliyun_claw", "qqclaw") and _runtime_present("openclaw"):
            d = dict(d)
            d["installed"] = True
            d["detail"] = d.get("detail") or "via openclaw"
        try:
            cmds = install_commands(r["id"]) if (r.get("install") or {}).get("kind") not in (None, "none") else []
        except ValueError:
            cmds = []
        up = upgrade_supported(r["id"])
        linked = (active == r["id"]) or (active == "auto" and auto_runtime == r["id"])
        meta_store = get_claw_meta(r["id"])
        ver_info: dict[str, Any] = {"version": "", "source": ""}
        if d.get("installed") or r["id"] == "direct":
            try:
                ver_info = detect_runtime_version(r["id"])
            except Exception:  # noqa: BLE001
                ver_info = {"version": "", "source": ""}
        live_ver = str(ver_info.get("version") or "").strip()
        cached_ver = str(meta_store.get("version") or "").strip()
        version = live_ver or cached_ver
        last_upgraded_at = str(meta_store.get("last_upgraded_at") or "").strip()
        last_installed_at = str(meta_store.get("last_installed_at") or "").strip()
        items.append(
            {
                "id": r["id"],
                "family": r.get("family"),
                "label": r.get("label"),
                "label_zh": r.get("label_zh"),
                "desc": r.get("desc"),
                "desc_zh": r.get("desc_zh"),
                "homepage": r.get("homepage"),
                "docs": r.get("docs"),
                "requires": r.get("requires") or [],
                "install_kind": (r.get("install") or {}).get("kind"),
                "install": {
                    "posix": (r.get("install") or {}).get("posix") or [],
                    "windows": (r.get("install") or {}).get("windows") or [],
                    "alt_posix": (r.get("install") or {}).get("alt_posix") or [],
                    "resolved_commands": cmds,
                    "target_dir": str(native) if native else str(pdir),
                    "native_home": str(native) if native else "",
                    "notes_zh": (r.get("install") or {}).get("notes_zh") or "",
                    "notes_en": (r.get("install") or {}).get("notes_en") or "",
                    "interactive": bool((r.get("install") or {}).get("interactive")),
                    "marketplace_hint_zh": (r.get("install") or {}).get("marketplace_hint_zh") or "",
                    "one_liner_docs": (r.get("install") or {}).get("one_liner_docs") or "",
                },
                "upgrade": {
                    "supported": bool(up.get("supported")),
                    "reason": up.get("reason") or "",
                    "commands": up.get("commands") or [],
                    "installed": bool(up.get("installed") if "installed" in up else d.get("installed")),
                },
                "optimize": r.get("optimize") or {},
                "detect": d,
                "linked": linked,
                "native_home": str(native) if native else "",
                "version": version,
                "version_source": str(ver_info.get("source") or ("cached" if cached_ver and not live_ver else "")),
                "last_upgraded_at": last_upgraded_at,
                "last_installed_at": last_installed_at,
            }
        )
    resolved = active
    if active == "auto":
        resolved = _resolve_auto(items, auto_runtime)
    linked_id = active if active != "auto" else auto_runtime
    return {
        "ok": True,
        "active": active,
        "auto_runtime": auto_runtime,
        "resolved": resolved,
        "linked": linked_id,
        "platform": osinfo["system"],
        "os": osinfo,
        "agent_cli_home": str(ensure_home()["root"]),
        "mode": "native-claws",
        "runtimes": items,
        "app_name": "Agent Hub",
        "note_zh": "Hub 为操作界面；安装/LLM/Soul 写入各 Claw 原生目录；聊天默认快路径 Direct 流式。",
        "note_en": "Hub is the control UI; install/LLM/soul write to native claw homes; chat defaults to fast Direct streaming.",
    }


def _ali_cfg() -> tuple[dict[str, Any], dict[str, Any]]:
    cfg = load_campus_config()
    ali = cfg.setdefault("ali", {})
    if not isinstance(ali, dict):
        ali = {}
        cfg["ali"] = ali
    return cfg, ali


def connect_runtime(runtime_id: str) -> dict[str, Any]:
    """Link one claw for Hub use: pin active + sync LLM/soul/skills into native home."""
    runtime_id = (runtime_id or "").strip()
    if not runtime_id or runtime_id == "auto":
        raise ValueError("choose a concrete runtime to connect (not auto)")
    if not get_runtime(runtime_id):
        raise ValueError(f"unknown runtime: {runtime_id}")
    cfg, ali = _ali_cfg()
    ali["agent_runtime"] = runtime_id
    ali["auto_runtime"] = runtime_id
    save_campus_config(cfg)
    claw_sync: dict[str, Any] = {}
    llm_sync: dict[str, Any] = {}
    skills_sync: dict[str, Any] = {}
    try:
        from . import soul as soul_mod

        claw_sync = soul_mod.sync_soul_to_claw(runtime_id)
    except Exception:  # noqa: BLE001
        claw_sync = {"ok": False}
    try:
        llm_sync = sync_hub_llm(runtime_id, cfg)
    except Exception as exc:  # noqa: BLE001
        llm_sync = {"ok": False, "error": str(exc)}
    try:
        from . import skills as skills_mod

        if hasattr(skills_mod, "sync_skills_to_claw"):
            skills_sync = skills_mod.sync_skills_to_claw(runtime_id)
    except Exception as exc:  # noqa: BLE001
        skills_sync = {"ok": False, "error": str(exc)}
    out = list_runtimes()
    out["claw_sync"] = claw_sync
    out["llm_sync"] = llm_sync
    out["skills_sync"] = skills_sync
    return out


def disconnect_runtime(runtime_id: str | None = None) -> dict[str, Any]:
    """Unlink a claw: fall back to auto → direct so unused claws aren't preferred."""
    runtime_id = (runtime_id or "").strip()
    cfg, ali = _ali_cfg()
    active = (ali.get("agent_runtime") or "auto").strip() or "auto"
    auto_prefer = _normalize_auto_runtime(str(ali.get("auto_runtime") or ""))
    target = runtime_id or (active if active != "auto" else auto_prefer)
    if target and target != "auto":
        if active == target:
            ali["agent_runtime"] = "auto"
        if auto_prefer == target:
            ali["auto_runtime"] = "direct"
    else:
        ali["agent_runtime"] = "auto"
        ali["auto_runtime"] = "direct"
    save_campus_config(cfg)
    return list_runtimes()


def set_active_runtime(runtime_id: str) -> dict[str, Any]:
    runtime_id = (runtime_id or "auto").strip()
    if runtime_id != "auto" and not get_runtime(runtime_id):
        raise ValueError(f"unknown runtime: {runtime_id}")
    cfg, ali = _ali_cfg()
    ali["agent_runtime"] = runtime_id
    save_campus_config(cfg)
    claw_sync: dict[str, Any] = {}
    try:
        from . import soul as soul_mod

        # Sync soul into the runtime that will actually be used
        data = list_runtimes()
        target = str(data.get("resolved") or runtime_id)
        if target and target not in ("auto", "direct"):
            claw_sync = soul_mod.sync_soul_to_claw(target)
    except Exception:  # noqa: BLE001
        claw_sync = {"ok": False}
    out = list_runtimes()
    out["claw_sync"] = claw_sync
    return out


def set_auto_runtime(runtime_id: str) -> dict[str, Any]:
    """Persist personal preference for what `auto` resolves to first."""
    prefer = _normalize_auto_runtime(runtime_id)
    cfg, ali = _ali_cfg()
    ali["auto_runtime"] = prefer
    save_campus_config(cfg)
    claw_sync: dict[str, Any] = {}
    try:
        from . import soul as soul_mod

        data = list_runtimes()
        if str(data.get("active") or "") == "auto":
            target = str(data.get("resolved") or prefer)
            if target and target not in ("auto", "direct"):
                claw_sync = soul_mod.sync_soul_to_claw(target)
    except Exception:  # noqa: BLE001
        claw_sync = {"ok": False}
    out = list_runtimes()
    out["claw_sync"] = claw_sync
    return out


def apply_optimize(runtime_id: str) -> dict[str, Any]:
    meta = get_runtime(runtime_id)
    if not meta:
        raise ValueError(f"unknown runtime: {runtime_id}")
    opt = dict(meta.get("optimize") or {})
    note_zh = opt.pop("note_zh", "")
    note_en = opt.pop("note_en", "")
    cfg = load_campus_config()
    for key, val in opt.items():
        parts = key.split(".")
        cur: Any = cfg
        for i, p in enumerate(parts[:-1]):
            if not isinstance(cur.get(p), dict):
                cur[p] = {}
            cur = cur[p]
        cur[parts[-1]] = val
    save_campus_config(cfg)
    return {
        "ok": True,
        "runtime": runtime_id,
        "applied": opt,
        "note_zh": note_zh,
        "note_en": note_en,
        **list_runtimes(),
    }


def install_commands(runtime_id: str) -> list[str]:
    """OS-aware install commands targeting each claw's **native** home / PATH."""
    from .home import os_profile

    meta = get_runtime(runtime_id)
    if not meta:
        raise ValueError(f"unknown runtime: {runtime_id}")
    inst = meta.get("install") or {}
    kind = inst.get("kind")
    osinfo = os_profile()

    if kind in (None, "none"):
        return []
    if kind == "link":
        if osinfo["kind"] == "windows":
            return []
        return list(inst.get("fallback_posix") or [])

    # Prefer catalog official installers (native ~/.hermes, ~/.openclaw, PATH bins)
    if osinfo["kind"] == "windows":
        cmds = list(inst.get("windows") or [])
    else:
        cmds = list(inst.get("posix") or [])
    if not cmds and runtime_id == "qqclaw":
        cmds = ["openclaw plugins install @tencent-connect/openclaw-qqbot@latest"]
    if not cmds:
        raise ValueError("no install command for this OS — open docs link instead")
    return cmds


def _is_soft_upgrade_step(cmd: str) -> bool:
    """Non-critical upgrade steps may fail (EACCES on global npm, missing PATH bin, etc.)."""
    c = (cmd or "").strip()
    if not c:
        return True
    low = c.lower()
    if "|| true" in low or "||true" in low:
        return True
    if "soft-continue" in low:
        return True
    if "--version" in low or "--help" in low:
        return True
    # Optional global installs — often blocked without sudo / writable npm prefix
    if "npm install -g " in low or "npm i -g " in low or "npm install --global " in low:
        return True
    # User/global pip without --target (parallel --target is the critical path)
    if ("pip install" in low or "pip3 install" in low) and "--target" not in low:
        return True
    # Hub bin symlink / copy helpers
    if "ln -sfn" in low or (r"\bin" in c and "copy-item" in low):
        return True
    return False


def upgrade_commands(runtime_id: str) -> list[str]:
    """OS-aware one-click upgrade against native installs / PATH binaries."""
    from .home import os_profile

    meta = get_runtime(runtime_id)
    if not meta:
        raise ValueError(f"unknown runtime: {runtime_id}")
    inst = meta.get("install") or {}
    kind = inst.get("kind")
    if kind in (None, "none"):
        raise ValueError("this runtime has no upgrade path")
    if kind == "link" and runtime_id == "aliyun_claw":
        return upgrade_commands("openclaw")
    if (inst.get("interactive")) and runtime_id == "nanoclaw":
        if os_profile()["kind"] == "windows":
            raise ValueError("NanoClaw upgrade is POSIX/Docker only — use WSL or a Linux host")
        home = Path.home() / "nanoclaw"
        return [
            f'test -d "{home}" && cd "{home}" && git pull --ff-only'
            f' && (docker compose pull 2>/dev/null || docker-compose pull 2>/dev/null || true)',
        ]

    osinfo = os_profile()
    win = osinfo["kind"] == "windows"
    base = install_commands(runtime_id)

    if runtime_id == "hermes":
        if win:
            return base + [
                'if (Get-Command hermes -ErrorAction SilentlyContinue) { hermes update 2>$null; hermes --version }',
            ]
        return base + [
            'command -v hermes >/dev/null 2>&1 && (hermes update 2>/dev/null || hermes --version) || true',
        ]
    if runtime_id == "openclaw":
        if win:
            return [
                "npm install -g openclaw@latest; if ($LASTEXITCODE -ne 0) { Write-Host '# soft-continue: global npm (EACCES ok)' }",
                "openclaw --version 2>$null; exit 0",
            ]
        return [
            "npm install -g openclaw@latest || true",
            "(openclaw --version 2>/dev/null || true)",
        ]
    if runtime_id == "nanobot":
        if win:
            return [
                "pip install -U nanobot-ai; if ($LASTEXITCODE -ne 0) { Write-Host '# soft-continue: global pip ok' }",
                "nanobot --help 2>$null; exit 0",
            ]
        return [
            "python3 -m pip install -U nanobot-ai || true",
            "nanobot --help || true",
        ]
    if runtime_id == "nano_claw":
        if win:
            return [
                "npm install -g nano-claw@latest; if ($LASTEXITCODE -ne 0) { Write-Host '# soft-continue: global npm ok' }",
                "nano-claw --version 2>$null; exit 0",
            ]
        return [
            "npm install -g nano-claw@latest || true",
            "(nano-claw --version 2>/dev/null || true)",
        ]
    if runtime_id == "qqclaw":
        return [
            "openclaw plugins install @tencent-connect/openclaw-qqbot@latest",
            "openclaw --version || true",
        ]

    return base


def start_install(runtime_id: str) -> dict[str, Any]:
    return _start_runtime_job(runtime_id, action="install")


def start_upgrade(runtime_id: str) -> dict[str, Any]:
    """One-click upgrade for an installed claw/runtime."""
    meta = get_runtime(runtime_id)
    if not meta:
        raise ValueError(f"unknown runtime: {runtime_id}")
    if runtime_id == "direct":
        raise ValueError("Direct LLM has nothing to upgrade")
    if not _runtime_present(runtime_id):
        if runtime_id == "nanoclaw":
            raise ValueError("NanoClaw folder not found (~/nanoclaw) — install first")
        raise ValueError("runtime not installed — use 一键安装 first")
    return _start_runtime_job(runtime_id, action="upgrade")


def _start_runtime_job(runtime_id: str, *, action: str = "install") -> dict[str, Any]:
    """Run curated install/upgrade commands in background; return job id."""
    meta = get_runtime(runtime_id)
    if not meta:
        raise ValueError(f"unknown runtime: {runtime_id}")
    for req in meta.get("requires") or []:
        if not _runtime_present(req):
            raise ValueError(f"requires {req} to be installed first")
    if action == "upgrade":
        cmds = upgrade_commands(runtime_id)
    else:
        cmds = install_commands(runtime_id)
    if not cmds:
        raise ValueError("this runtime is docs/link only — open homepage to install")
    if action == "install" and (meta.get("install") or {}).get("interactive"):
        raise ValueError("interactive installer — copy commands and run in a terminal")

    ensure_state_dirs()
    INSTALL_LOG_DIR.mkdir(parents=True, exist_ok=True)
    job_id = str(uuid.uuid4())
    log_path = INSTALL_LOG_DIR / f"{job_id}.log"
    if action == "upgrade":
        step_defs = [
            {"id": "prepare", "label_zh": "准备升级", "label_en": "Prepare upgrade", "pct": 10},
            {"id": "install", "label_zh": "拉取最新版", "label_en": "Fetch latest", "pct": 55},
            {"id": "verify", "label_zh": "测试验证", "label_en": "Verify", "pct": 85},
            {"id": "done", "label_zh": "升级完成", "label_en": "Upgraded", "pct": 100},
        ]
    else:
        step_defs = [
            {"id": "prepare", "label_zh": "准备", "label_en": "Prepare", "pct": 10},
            {"id": "install", "label_zh": "安装", "label_en": "Install", "pct": 55},
            {"id": "verify", "label_zh": "测试验证", "label_en": "Verify", "pct": 85},
            {"id": "done", "label_zh": "完成", "label_en": "Done", "pct": 100},
        ]
    job = {
        "id": job_id,
        "runtime_id": runtime_id,
        "kind": "runtime",
        "action": action,
        "status": "running",
        "step": "prepare",
        "pct": 5,
        "steps": step_defs,
        "commands": cmds,
        "log_path": str(log_path),
        "started_at": time.time(),
        "finished_at": None,
        "exit_code": None,
        "error": None,
        "verify": None,
        "debug": [],
    }
    with _jobs_lock:
        _jobs[job_id] = job

    def _set_step(step_id: str, pct: int | None = None) -> None:
        job["step"] = step_id
        for s in step_defs:
            if s["id"] == step_id and pct is None:
                job["pct"] = s["pct"]
                break
        if pct is not None:
            job["pct"] = pct

    def _verify_once(log) -> dict[str, Any]:
        det = detect_runtime(meta)
        from .home import native_claw_home

        native = native_claw_home(runtime_id)
        ok = bool(det.get("installed"))
        if runtime_id == "nanoclaw":
            ok = ok or (Path.home() / "nanoclaw").is_dir()
        if runtime_id in ("aliyun_claw", "qqclaw"):
            oc = get_runtime("openclaw")
            ok = ok or bool(oc and detect_runtime(oc).get("installed"))
        info = {
            "ok": ok,
            "detect": det,
            "native_home": str(native) if native else "",
            "detail": det.get("detail") or ("native ok" if ok else "not detected"),
        }
        log.write(f"\n# verify: ok={ok} detail={info['detail']}\n")
        log.flush()
        return info

    def _debug_fix(log) -> list[str]:
        notes: list[str] = []
        from .home import runtime_dir

        pdir = runtime_dir(runtime_id)
        try:
            if pdir.is_dir():
                for bin_dir in (pdir / "bin", pdir / "node_modules" / ".bin"):
                    if bin_dir.is_dir():
                        for child in bin_dir.iterdir():
                            try:
                                mode = child.stat().st_mode
                                child.chmod(mode | 0o111)
                                notes.append(f"chmod +x {child.name}")
                            except OSError:
                                continue
        except OSError as exc:
            notes.append(f"chmod skip: {exc}")
        which_names = (meta.get("detect") or {}).get("whiches") or []
        for name in which_names:
            path = _which(name)
            if path:
                notes.append(f"found on PATH: {name} → {path}")
        log.write("\n# debug attempts:\n")
        for n in notes:
            log.write(f"#  - {n}\n")
        log.flush()
        return notes

    def _run() -> None:
        try:
            with log_path.open("w", encoding="utf-8") as log:
                log.write(f"# Agent Hub {action} job {job_id}\n# runtime={runtime_id}\n")
                _set_step("prepare", 12)
                log.write("# step: prepare\n")
                log.flush()
                _set_step("install", 25)
                total = max(len(cmds), 1)
                for i, cmd in enumerate(cmds):
                    log.write(f"\n$ {cmd}\n")
                    log.flush()
                    job["pct"] = min(75, 25 + int(50 * (i / total)))
                    proc = subprocess.run(
                        cmd,
                        shell=True,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        text=True,
                        env={**os.environ, "CI": "1", "AGENT_CLI_INSTALL": "1", "AGENT_CLI_UPGRADE": "1" if action == "upgrade" else "0"},
                        timeout=1800,
                    )
                    if proc.returncode != 0:
                        # upgrade: soft-fail non-critical steps (global npm/pip often EACCES;
                        # version probes; explicit || true / soft-continue markers)
                        soft = action == "upgrade" and _is_soft_upgrade_step(cmd)
                        if soft:
                            log.write(
                                f"\n# soft-continue exit {proc.returncode} "
                                f"(non-critical upgrade step)\n"
                            )
                            log.flush()
                            continue
                        job["status"] = "failed"
                        job["step"] = "install"
                        job["exit_code"] = proc.returncode
                        job["error"] = f"command failed: {cmd}"
                        job["finished_at"] = time.time()
                        job["pct"] = job.get("pct") or 40
                        log.write(f"\n# exit {proc.returncode}\n")
                        return
                _set_step("verify", 88)
                log.write(f"\n# step: verify (after {action})\n")
                verify = _verify_once(log)
                if not verify.get("ok"):
                    notes = _debug_fix(log)
                    job["debug"] = notes
                    verify = _verify_once(log)
                job["verify"] = verify
                if not verify.get("ok"):
                    job["status"] = "failed"
                    job["step"] = "verify"
                    job["error"] = f"verify failed — runtime not working after {action}; see log"
                    job["finished_at"] = time.time()
                    job["pct"] = 90
                    log.write("\n# VERIFY FAILED\n")
                    return
                _set_step("done", 100)
                job["status"] = "ok"
                job["exit_code"] = 0
                job["finished_at"] = time.time()
                # Persist version + last upgrade/install time for Control Center Claws UI
                try:
                    ver_info = detect_runtime_version(runtime_id)
                    ver = str(ver_info.get("version") or "").strip()
                    meta = record_claw_meta(
                        runtime_id,
                        version=ver,
                        upgraded=(action == "upgrade"),
                        installed=(action == "install"),
                    )
                    job["claw_meta"] = meta
                    log.write(
                        f"\n# claw_meta version={ver or '—'} "
                        f"last_upgraded_at={meta.get('last_upgraded_at') or '—'}\n"
                    )
                except Exception as meta_exc:  # noqa: BLE001
                    log.write(f"\n# claw_meta persist skipped: {meta_exc}\n")
                log.write(f"\n# done — {action} verified\n")
        except Exception as exc:  # noqa: BLE001
            job["status"] = "failed"
            job["error"] = str(exc)
            job["finished_at"] = time.time()
            try:
                with log_path.open("a", encoding="utf-8") as log:
                    log.write(f"\n# error: {exc}\n")
            except OSError:
                pass

    threading.Thread(target=_run, daemon=True, name=f"{action}-{runtime_id}").start()
    return {"ok": True, "job": {k: v for k, v in job.items()}}


def install_job_status(job_id: str) -> dict[str, Any]:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        # try read log only
        path = INSTALL_LOG_DIR / f"{job_id}.log"
        if path.is_file():
            return {"ok": True, "job": {"id": job_id, "status": "unknown", "log": path.read_text(encoding="utf-8", errors="replace")[-8000:]}}
        raise FileNotFoundError(job_id)
    out = dict(job)
    try:
        out["log"] = Path(job["log_path"]).read_text(encoding="utf-8", errors="replace")[-12000:]
    except OSError:
        out["log"] = ""
    return {"ok": True, "job": out}


def peek_runtime() -> dict[str, str]:
    """Fast runtime resolve for chat hot path — no version probes / install recipes."""
    cfg = load_campus_config()
    ali = cfg.get("ali") if isinstance(cfg.get("ali"), dict) else {}
    active = (ali.get("agent_runtime") or "auto").strip() or "auto"
    auto_runtime = _normalize_auto_runtime(str(ali.get("auto_runtime") or ""))
    linked = active if active != "auto" else auto_runtime

    def _avail(rid: str) -> bool:
        if rid == "direct":
            return True
        meta = get_runtime(rid)
        if not meta:
            return False
        if (meta.get("detect") or {}).get("always"):
            return True
        if detect_runtime(meta).get("installed"):
            return True
        if rid == "nanoclaw":
            return (Path.home() / "nanoclaw").is_dir()
        if rid in ("aliyun_claw", "qqclaw"):
            oc = get_runtime("openclaw")
            return bool(oc and detect_runtime(oc).get("installed"))
        return False

    if active != "auto":
        resolved = active if _avail(active) else ("direct" if active == "direct" else (active if get_runtime(active) else "direct"))
        # Pinned claw stays selected even if detect flaps — Hub is the control UI
        if get_runtime(active):
            resolved = active
    else:
        prefer = auto_runtime
        if _avail(prefer):
            resolved = prefer
        else:
            resolved = "direct"
            for cand in _AUTO_FALLBACK:
                if _avail(cand):
                    resolved = cand
                    break
    return {
        "active": active,
        "auto_runtime": auto_runtime,
        "resolved": resolved,
        "linked": linked,
    }


def resolved_runtime_id() -> str:
    return str(peek_runtime().get("resolved") or "direct")


# Hub provider id → OpenClaw / NanoBot provider slug used in their configs
_CLAW_PROVIDER_MAP = {
    "openrouter": "openrouter",
    "openai": "openai",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "nvidia-nim": "openai",  # OpenAI-compatible NIM endpoint via env/base_url
    "campus-openai-compatible": "openai",
    "local-ollama": "openai",
    "gemini": "google",
    "google": "google",
    "minimax": "minimax",
    "moonshot": "moonshot",
    "kimi": "moonshot",
}


def _resolve_hub_llm(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve Hub Control Center provider / API key / model for claw sync."""
    from .secrets import resolve_api_key
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    backend = cfg.get("backend") or {}
    pid = str(backend.get("type") or "").strip()
    if pid == "hybrid":
        hybrid = cfg.get("hybrid") or {}
        office = hybrid.get("office") or hybrid.get("main") or {}
        if isinstance(office, dict) and office.get("provider"):
            pid = str(office["provider"])
        else:
            pid = "openrouter"
    key_info = resolve_api_key(cfg, provider=pid)
    api_key = str(key_info.get("key") or "").strip()
    env_name = str(key_info.get("env_name") or backend.get("api_key_env") or "").strip()
    base_url = str(backend.get("base_url") or "").strip()
    models = cfg.get("models") or {}
    use_model = str(
        models.get("main") or models.get("qwen_main") or models.get("fast") or ""
    ).strip()
    return {
        "provider_id": pid,
        "api_key": api_key,
        "env_name": env_name,
        "base_url": base_url,
        "model": use_model,
        "masked": key_info.get("masked") or "",
        "claw_provider": _CLAW_PROVIDER_MAP.get(pid, "openai"),
    }


def _env_updates_for_hub(cred: dict[str, Any]) -> dict[str, str]:
    updates: dict[str, str] = {}
    env_name = str(cred.get("env_name") or "").strip()
    api_key = str(cred.get("api_key") or "")
    base_url = str(cred.get("base_url") or "").strip()
    if env_name and api_key:
        updates[env_name] = api_key
    if api_key:
        updates.setdefault("OPENAI_API_KEY", api_key)
    if base_url:
        updates["OPENAI_BASE_URL"] = base_url
        updates["OPENAI_API_BASE"] = base_url
    pid = cred.get("provider_id") or ""
    if pid == "openrouter" and api_key:
        updates["OPENROUTER_API_KEY"] = api_key
    if pid == "nvidia-nim" and api_key:
        updates["NVIDIA_API_KEY"] = api_key
    if pid == "anthropic" and api_key:
        updates["ANTHROPIC_API_KEY"] = api_key
    if pid in ("gemini", "google") and api_key:
        updates["GOOGLE_API_KEY"] = api_key
        updates["GEMINI_API_KEY"] = api_key
    if pid == "deepseek" and api_key:
        updates["DEEPSEEK_API_KEY"] = api_key
    if pid in ("moonshot", "kimi") and api_key:
        updates["MOONSHOT_API_KEY"] = api_key
    if pid == "minimax" and api_key:
        updates["MINIMAX_API_KEY"] = api_key
    return updates


def _sync_openclaw_homes(cred: dict[str, Any]) -> list[str]:
    """Write Hub keys into native OpenClaw home (~/.openclaw) only."""
    from .hermes_cli import _merge_dotenv

    written: list[str] = []
    updates = _env_updates_for_hub(cred)
    home = Path.home() / ".openclaw"
    try:
        home.mkdir(parents=True, exist_ok=True)
        _merge_dotenv(home / ".env", updates)
        written.append(str(home / ".env"))
    except OSError:
        pass

    # Upsert auth-profiles for the active OpenClaw agent (main)
    claw_prov = str(cred.get("claw_provider") or "openai")
    api_key = str(cred.get("api_key") or "")
    if api_key:
        auth_path = Path.home() / ".openclaw" / "agents" / "main" / "agent" / "auth-profiles.json"
        try:
            auth_path.parent.mkdir(parents=True, exist_ok=True)
            data: dict[str, Any] = {"version": 1, "profiles": {}, "lastGood": {}}
            if auth_path.is_file():
                try:
                    loaded = json.loads(auth_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        data = loaded
                except (OSError, json.JSONDecodeError):
                    pass
            profiles = data.setdefault("profiles", {})
            if not isinstance(profiles, dict):
                profiles = {}
                data["profiles"] = profiles
            profile_id = f"{claw_prov}:hub"
            profiles[profile_id] = {
                "type": "api_key",
                "provider": claw_prov,
                "key": api_key,
            }
            last_good = data.setdefault("lastGood", {})
            if not isinstance(last_good, dict):
                last_good = {}
                data["lastGood"] = last_good
            last_good[claw_prov] = profile_id
            auth_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            try:
                os.chmod(auth_path, 0o600)
            except OSError:
                pass
            written.append(str(auth_path))
        except OSError:
            pass

    # Soft-set default model in openclaw.json when present (non-destructive)
    model = str(cred.get("model") or "").strip()
    cfg_path = Path.home() / ".openclaw" / "openclaw.json"
    if model and cfg_path.is_file():
        try:
            oc = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(oc, dict):
                agents = oc.setdefault("agents", {})
                if isinstance(agents, dict):
                    defaults = agents.setdefault("defaults", {})
                    if isinstance(defaults, dict):
                        m = defaults.get("model")
                        primary = f"{claw_prov}/{model}" if "/" not in model else model
                        if isinstance(m, dict):
                            m["primary"] = primary
                        else:
                            defaults["model"] = {"primary": primary}
                        cfg_path.write_text(
                            json.dumps(oc, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8",
                        )
                        written.append(str(cfg_path))
        except (OSError, json.JSONDecodeError, TypeError):
            pass
    return written


def _sync_nanobot_homes(cred: dict[str, Any]) -> list[str]:
    """Merge Hub provider into native NanoBot ~/.nanobot only."""
    from .hermes_cli import _merge_dotenv

    written: list[str] = []
    updates = _env_updates_for_hub(cred)
    home = Path.home() / ".nanobot"
    try:
        home.mkdir(parents=True, exist_ok=True)
        _merge_dotenv(home / ".env", updates)
        written.append(str(home / ".env"))
    except OSError:
        pass

    claw_prov = str(cred.get("claw_provider") or "openai")
    api_key = str(cred.get("api_key") or "")
    base_url = str(cred.get("base_url") or "").strip()
    model = str(cred.get("model") or "").strip()
    cfg_path = Path.home() / ".nanobot" / "config.json"
    try:
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = {}
        if cfg_path.is_file():
            try:
                loaded = json.loads(cfg_path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        providers = data.setdefault("providers", {})
        if not isinstance(providers, dict):
            providers = {}
            data["providers"] = providers
        pid = cred.get("provider_id") or ""
        if pid in ("campus-openai-compatible", "local-ollama", "nvidia-nim") or (
            claw_prov == "openai" and base_url and pid not in ("openai",)
        ):
            target = "custom"
            entry: dict[str, Any] = {"apiKey": api_key or "no-key"}
            if base_url:
                entry["apiBase"] = base_url
        else:
            target = claw_prov
            entry = {"apiKey": api_key}
            if base_url and target in ("openai", "custom"):
                entry["apiBase"] = base_url
        providers[target] = {**(providers.get(target) or {}), **entry}
        if model:
            agents = data.setdefault("agents", {})
            if not isinstance(agents, dict):
                agents = {}
                data["agents"] = agents
            defaults = agents.setdefault("defaults", {})
            if isinstance(defaults, dict):
                defaults["provider"] = target
                defaults["model"] = model
        cfg_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(cfg_path, 0o600)
        except OSError:
            pass
        written.append(str(cfg_path))
    except OSError:
        pass
    return written


def _sync_generic_env(runtime_id: str, cred: dict[str, Any], extra_homes: list[Path] | None = None) -> list[str]:
    """Write Hub LLM env into native claw homes only (no parallel runtimes/)."""
    from .hermes_cli import _merge_dotenv
    from .home import native_claw_home

    written: list[str] = []
    updates = _env_updates_for_hub(cred)
    homes: list[Path] = []
    native = native_claw_home(runtime_id)
    if native:
        homes.append(native)
    if extra_homes:
        homes.extend(extra_homes)
    # de-dupe
    seen: set[str] = set()
    uniq: list[Path] = []
    for h in homes:
        key = str(h)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(h)
    for home in uniq:
        try:
            home.mkdir(parents=True, exist_ok=True)
            _merge_dotenv(home / ".env", updates)
            side = home / "hub-llm.json"
            side.write_text(
                json.dumps(
                    {
                        "provider": cred.get("provider_id"),
                        "claw_provider": cred.get("claw_provider"),
                        "model": cred.get("model"),
                        "base_url": cred.get("base_url") or "",
                        "env_name": cred.get("env_name") or "",
                        "synced_by": "Agent Hub",
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            written.append(str(home / ".env"))
        except OSError:
            continue
    return written


def sync_hub_llm(runtime_id: str = "", cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Sync Hub LLM provider/keys/models into the selected claw/runtime config.

    Targets the currently selected runtime (or resolved auto). Hermes keeps using
    the dedicated Hermes sync; OpenClaw-family, NanoBot, and others get .env /
    config merges. Direct LLM already uses Hub settings (no-op success).
    """
    from .hermes_cli import sync_hub_to_hermes
    from .settings import load_campus_config

    cfg = cfg or load_campus_config()
    data = list_runtimes()
    rid = (runtime_id or "").strip()
    if not rid or rid == "auto":
        rid = str(data.get("resolved") or data.get("active") or "direct")
    if rid == "auto":
        rid = "direct"

    meta = get_runtime(rid)
    if not meta and rid != "direct":
        return {
            "ok": False,
            "runtime": rid,
            "error": f"unknown runtime: {rid}",
            "error_zh": f"未知运行时：{rid}",
            "error_en": f"Unknown runtime: {rid}",
        }

    label = (meta or {}).get("label_zh") or (meta or {}).get("label") or rid
    cred = _resolve_hub_llm(cfg)

    if not cred.get("api_key") and cred.get("provider_id") not in ("local-ollama",):
        msg_zh = (
            f"未找到可用的 API Key，无法同步到 {label}。"
            "请在控制中心「后端」粘贴密钥并保存，再点「同步 LLM」。"
        )
        msg_en = (
            f"No API key found — cannot sync to {label}. "
            "Paste a key in Control Center → Backend, Save, then Sync LLM."
        )
        return {
            "ok": False,
            "runtime": rid,
            "error": msg_zh,
            "error_zh": msg_zh,
            "error_en": msg_en,
            "provider": cred.get("provider_id"),
        }

    # Hermes — dedicated path (managed + ~/.hermes)
    if rid == "hermes":
        result = sync_hub_to_hermes(cfg)
        result = dict(result)
        result["runtime"] = "hermes"
        if result.get("ok"):
            result["note_zh"] = result.get("note_zh") or "已同步 LLM 到 Hermes"
            result["note_en"] = result.get("note_en") or "Synced LLM to Hermes"
        return result

    # Direct — Hub already owns the keys
    if rid == "direct":
        return {
            "ok": True,
            "runtime": "direct",
            "provider": cred.get("provider_id"),
            "model": cred.get("model"),
            "masked": cred.get("masked"),
            "targets": [],
            "note_zh": "直连模型已使用控制中心 Provider / API Key，无需额外同步。",
            "note_en": "Direct LLM already uses Control Center provider/API key — nothing else to sync.",
        }

    written: list[str] = []
    family = (meta or {}).get("family") or ""

    try:
        if rid in ("openclaw", "qqclaw", "aliyun_claw") or (
            family == "claw" and rid.startswith("aliyun")
        ):
            written = _sync_openclaw_homes(cred)
        elif rid == "nanobot":
            written = _sync_nanobot_homes(cred)
        elif rid == "nano_claw":
            written = _sync_generic_env(
                rid,
                cred,
                extra_homes=[Path.home() / ".nano-claw", Path.home() / ".nanoclaw"],
            )
        elif rid == "nanoclaw":
            written = _sync_generic_env(
                rid,
                cred,
                extra_homes=[Path.home() / "nanoclaw", Path.home() / ".nanoclaw"],
            )
        else:
            written = _sync_generic_env(rid, cred)
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "runtime": rid,
            "error": str(exc),
            "error_zh": f"同步 LLM 到 {label} 失败：{exc}",
            "error_en": f"Sync LLM to {label} failed: {exc}",
        }

    if not written:
        return {
            "ok": False,
            "runtime": rid,
            "error_zh": f"未能写入 {label} 配置目录（可能未安装）。",
            "error_en": f"Could not write {label} config dirs (runtime may be missing).",
            "provider": cred.get("provider_id"),
        }

    return {
        "ok": True,
        "runtime": rid,
        "provider": cred.get("provider_id"),
        "claw_provider": cred.get("claw_provider"),
        "model": cred.get("model"),
        "masked": cred.get("masked"),
        "targets": written,
        "note_zh": f"已同步 LLM 到 {label}：provider={cred.get('provider_id')} model={cred.get('model') or '(unset)'}",
        "note_en": f"Synced LLM to {label}: provider={cred.get('provider_id')} model={cred.get('model') or '(unset)'}",
    }

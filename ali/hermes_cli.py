"""Run Hermes via its own CLI / venv (avoids importing Hermes under system Python 3.9)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import discover_agent_dirs, hermes_home
from .home import runtime_dir

# Env vars that must not leak across OpenRouter ↔ NVIDIA in a Hermes subprocess.
_VENDOR_KEY_ENVS = (
    "OPENROUTER_API_KEY",
    "NVIDIA_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY",
)

# Agent-CLI provider id → hermes --provider name (Hermes first-class ids)
_PROVIDER_MAP = {
    "openrouter": "openrouter",
    "openai": "openai",
    "anthropic": "anthropic",
    "deepseek": "deepseek",
    "nvidia-nim": "nvidia",
    "campus-openai-compatible": "custom",
    "local-ollama": "custom",
    "gemini": "gemini",
    "google": "gemini",
    "minimax": "minimax",
    "moonshot": "kimi-coding",
    "kimi": "kimi-coding",
}

_MCP_MARKER_BEGIN = "# --- Agent Hub MCP (managed) ---"
_MCP_MARKER_END = "# --- end Agent Hub MCP ---"


def find_hermes_bin() -> Path | None:
    which = shutil.which("hermes")
    if which:
        return Path(which)
    for cand in (
        hermes_home() / "hermes-agent" / "venv" / "bin" / "hermes",
        hermes_home() / "venv" / "bin" / "hermes",
        hermes_home() / "bin" / "hermes",
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    for d in discover_agent_dirs():
        for cand in (
            d / "venv" / "bin" / "hermes",
            d / "venv" / "Scripts" / "hermes.exe",
            d / "hermes",
        ):
            if cand.is_file() and os.access(cand, os.X_OK):
                return cand
    # Legacy parallel cache
    for cand in (
        runtime_dir("hermes") / "hermes-agent" / "venv" / "bin" / "hermes",
    ):
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    return None


def _migrate_parallel_hermes_home_once(native: Path) -> None:
    """If Hub previously wrote into runtimes/hermes/hermes-home, copy missing files once."""
    legacy = runtime_dir("hermes") / "hermes-home"
    if not legacy.is_dir() or legacy.resolve() == native.resolve():
        return
    marker = native / ".hub-migrated-from-parallel"
    if marker.is_file():
        return
    try:
        native.mkdir(parents=True, exist_ok=True)
        for name in (".env", "config.yaml", "SOUL.md"):
            src, dst = legacy / name, native / name
            if src.is_file() and not dst.is_file():
                shutil.copy2(src, dst)
        legacy_skills = legacy / "skills"
        native_skills = native / "skills"
        if legacy_skills.is_dir():
            native_skills.mkdir(parents=True, exist_ok=True)
            for child in legacy_skills.iterdir():
                dest = native_skills / child.name
                if not dest.exists():
                    if child.is_dir():
                        shutil.copytree(child, dest, dirs_exist_ok=True)
                    elif child.is_file():
                        shutil.copy2(child, dest)
        marker.write_text(
            f"migrated from {legacy}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


def hermes_managed_home() -> Path:
    """Operational HERMES_HOME — always the native Hermes home (~/.hermes)."""
    p = hermes_home()
    p.mkdir(parents=True, exist_ok=True)
    (p / "skills").mkdir(parents=True, exist_ok=True)
    _migrate_parallel_hermes_home_once(p)
    return p


def hermes_cli_status(*, probe_version: bool = False) -> dict[str, Any]:
    bin_path = find_hermes_bin()
    version = ""
    if bin_path and probe_version:
        try:
            proc = subprocess.run(
                [str(bin_path), "--version"],
                capture_output=True,
                text=True,
                timeout=8,
                env={**os.environ, "PYTHONPATH": "", "PYTHONHOME": ""},
            )
            version = (proc.stdout or proc.stderr or "").strip().splitlines()[0] if proc.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            version = ""
    return {
        "available": bin_path is not None,
        "bin": str(bin_path) if bin_path else "",
        "version": version,
        "managed_home": str(hermes_managed_home()),
        "native_home": str(hermes_home()),
    }


def _hermes_provider_name(provider_id: str) -> str:
    return _PROVIDER_MAP.get((provider_id or "").strip(), "custom")


def _patch_provider_tls_yaml(path: Path, *, base_url: str, verify_tls: bool) -> None:
    """Maintain one URL-scoped TLS entry understood by Hermes/httpx.

    Hermes resolves ``providers.*.ssl_verify`` by exact base URL, so this
    affects only the LLM endpoint selected by Agent Hub. Secure mode removes
    the managed exception instead of setting any process-global TLS override.
    """
    try:
        import yaml
    except ImportError as exc:
        if not verify_tls:
            raise RuntimeError("PyYAML required to configure Hermes TLS policy") from exc
        return

    data: dict[str, Any] = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            data = loaded
    providers = data.get("providers")
    if not isinstance(providers, dict):
        providers = {}
        data["providers"] = providers

    managed_key = "agent-hub-tls"
    if verify_tls or not (base_url or "").strip():
        providers.pop(managed_key, None)
    else:
        providers[managed_key] = {
            "base_url": str(base_url).strip(),
            "ssl_verify": False,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=str(path.parent), delete=False
    ) as tmp:
        yaml.safe_dump(data, tmp, allow_unicode=True, sort_keys=False)
        tmp_path = Path(tmp.name)
    os.chmod(tmp_path, mode)
    os.replace(tmp_path, path)


def _write_managed_env(
    *,
    env_name: str,
    api_key: str,
    base_url: str = "",
    model: str = "",
    provider_id: str = "",
    verify_tls: bool = True,
) -> Path:
    home = hermes_managed_home()
    hermes_provider = _hermes_provider_name(provider_id)
    lines = [
        "# Managed by Agent Hub — do not mix OpenRouter and NVIDIA keys here",
        f"{env_name}={api_key}",
    ]
    if hermes_provider == "nvidia" and api_key and env_name != "NVIDIA_API_KEY":
        lines.append(f"NVIDIA_API_KEY={api_key}")
    if hermes_provider == "openrouter" and api_key and env_name != "OPENROUTER_API_KEY":
        lines.append(f"OPENROUTER_API_KEY={api_key}")
    if base_url and hermes_provider == "custom":
        lines.append(f"OPENAI_BASE_URL={base_url}")
        if env_name != "OPENAI_API_KEY":
            lines.append(f"OPENAI_API_KEY={api_key}")
    env_path = home / ".env"
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        os.chmod(env_path, 0o600)
    except OSError:
        pass

    cfg_path = home / "config.yaml"
    # Patch model block only — preserve mcp_servers and other Hermes settings
    _patch_model_yaml(
        cfg_path,
        model=model or "openai/gpt-4o-mini",
        provider=hermes_provider,
        base_url=base_url if hermes_provider == "custom" else "",
    )
    _patch_provider_tls_yaml(cfg_path, base_url=base_url, verify_tls=verify_tls)
    try:
        from . import mcp_hub

        merge_mcp_servers_into_config(cfg_path, mcp_hub.active_servers_for_hermes())
    except Exception:  # noqa: BLE001
        pass
    return home


def build_hermes_env(
    *,
    env_name: str,
    api_key: str,
    base_url: str = "",
    model: str = "",
    provider_id: str = "",
    verify_tls: bool = True,
) -> dict[str, str]:
    """Subprocess env with only the active vendor key (no OpenRouter↔NVIDIA bleed)."""
    home = _write_managed_env(
        env_name=env_name or "OPENAI_API_KEY",
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider_id=provider_id,
        verify_tls=verify_tls,
    )
    env = {k: v for k, v in os.environ.items() if k not in _VENDOR_KEY_ENVS}
    env["PYTHONPATH"] = ""
    env["PYTHONHOME"] = ""
    env["HERMES_HOME"] = str(home)
    slot = (env_name or "OPENAI_API_KEY").strip()
    if slot and api_key:
        env[slot] = api_key
    hermes_provider = _hermes_provider_name(provider_id)
    if hermes_provider == "custom" and api_key:
        env["OPENAI_API_KEY"] = api_key
        if base_url:
            env["OPENAI_BASE_URL"] = base_url
    if hermes_provider == "nvidia" and api_key:
        env["NVIDIA_API_KEY"] = api_key
    if hermes_provider == "openrouter" and api_key:
        env["OPENROUTER_API_KEY"] = api_key
    return env


def run_hermes_chat(
    prompt: str,
    *,
    model: str = "",
    provider_id: str = "",
    api_key: str = "",
    env_name: str = "",
    base_url: str = "",
    workspace: str = "",
    timeout: float = 180,
    verify_tls: bool = True,
) -> dict[str, Any]:
    bin_path = find_hermes_bin()
    if not bin_path:
        raise FileNotFoundError("hermes CLI not found — install Hermes runtime first")
    if not api_key and provider_id not in ("local-ollama",):
        raise ValueError("API key required for Hermes CLI chat")

    env = build_hermes_env(
        env_name=env_name or "OPENAI_API_KEY",
        api_key=api_key,
        base_url=base_url,
        model=model,
        provider_id=provider_id,
        verify_tls=verify_tls,
    )
    cmd = [str(bin_path), "chat", "-q", prompt, "-Q"]
    if model:
        cmd.extend(["-m", model])
    hermes_provider = _hermes_provider_name(provider_id)
    if hermes_provider and hermes_provider != "custom":
        cmd.extend(["--provider", hermes_provider])

    cwd = workspace if workspace and Path(workspace).is_dir() else None
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        cwd=cwd,
    )
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        raise RuntimeError(err or out or f"hermes exited {proc.returncode}")
    text = out
    if not text and err:
        text = err
    return {
        "ok": True,
        "text": text,
        "bin": str(bin_path),
        "provider": hermes_provider,
        "hermes_home": env.get("HERMES_HOME"),
    }


def clean_hermes_text(text: str) -> str:
    """Drop think tags, reasoning banners / skill JSON dumps from Hermes CLI output."""
    s = text or ""
    think = r"think(?:ing)?|reasoning|redacted_reasoning|thought"
    s = re.sub(rf"<\s*(?:{think})\b[^>]*>[\s\S]*?<\s*/\s*(?:{think})\s*>", "", s, flags=re.I)
    s = re.sub(rf"<\s*(?:{think})\b[^>]*>[\s\S]*$", "", s, flags=re.I)
    s = re.sub(r"┌─[\s\S]*?┐[\s\S]*?└─+┘", "", s)
    s = re.sub(r"╭─[\s\S]*?╯", "", s)
    s = re.sub(r"```(?:json|javascript|js)?\s*\{[\s\S]*?\"skill\"\s*:[\s\S]*?\}\s*```", "", s, flags=re.I)
    s = re.sub(r"\{\s*\"skill\"\s*:\s*\"[^\"]+\"[\s\S]*?\}", "", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()


def hermes_config_homes() -> list[Path]:
    """Homes Hermes may read — native ~/.hermes only (Hub is control plane)."""
    home = hermes_managed_home()
    return [home]


def _merge_dotenv(path: Path, updates: dict[str, str]) -> None:
    """Upsert KEY=value lines; preserve unrelated entries."""
    existing: dict[str, str] = {}
    order: list[str] = []
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                raw = line.rstrip("\n")
                if not raw.strip() or raw.lstrip().startswith("#") or "=" not in raw:
                    order.append(raw)
                    continue
                k, _, v = raw.partition("=")
                k = k.strip()
                if k:
                    existing[k] = v
                    order.append(f"__KEY__:{k}")
                else:
                    order.append(raw)
        except OSError:
            order = []
            existing = {}

    for k, v in updates.items():
        if not k:
            continue
        existing[k] = v
        marker = f"__KEY__:{k}"
        if marker not in order:
            order.append(marker)

    lines: list[str] = []
    if not any(
        x.startswith("# Managed by Agent Hub") or x.startswith("# Managed by Agent-CLI")
        for x in order
        if not x.startswith("__KEY__:")
    ):
        lines.append("# Managed by Agent Hub — provider keys synced from Control Center")
    seen_keys: set[str] = set()
    for item in order:
        if item.startswith("__KEY__:"):
            k = item.split(":", 1)[1]
            if k in seen_keys:
                continue
            seen_keys.add(k)
            lines.append(f"{k}={existing.get(k, '')}")
        else:
            lines.append(item)
    for k, v in updates.items():
        if k not in seen_keys:
            lines.append(f"{k}={v}")
            seen_keys.add(k)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _patch_model_yaml(path: Path, *, model: str, provider: str, base_url: str = "") -> None:
    """Update model.default / provider / base_url without wiping the rest of config.yaml."""
    model_line = model or "openai/gpt-4o-mini"
    provider_line = provider or "auto"
    stub = (
        "model:\n"
        f'  default: "{model_line}"\n'
        f'  provider: "{provider_line}"\n'
    )
    if base_url and provider_line == "custom":
        stub += f'  base_url: "{base_url}"\n'

    if not path.is_file():
        path.write_text(stub, encoding="utf-8")
        return

    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        path.write_text(stub, encoding="utf-8")
        return

    if not re.search(r"(?m)^model:\s*$", text) and not re.search(r"(?m)^model:\s+\S", text):
        path.write_text(stub + "\n" + text, encoding="utf-8")
        return

    def _set_under_model(src: str, key: str, value: str) -> str:
        pattern = rf"(?m)^model:\s*\n((?:[ \t]+.*\n)*)"
        m = re.search(pattern, src)
        if not m:
            return src
        block = m.group(0)
        key_re = rf"(?m)^([ \t]+){re.escape(key)}:\s*.*$"
        if re.search(key_re, block):
            new_block = re.sub(key_re, rf'\1{key}: "{value}"', block, count=1)
        else:
            new_block = re.sub(r"(?m)^(model:\s*\n)", rf'\1  {key}: "{value}"\n', block, count=1)
        return src[: m.start()] + new_block + src[m.end() :]

    text = _set_under_model(text, "default", model_line)
    text = _set_under_model(text, "provider", provider_line)
    if base_url and provider_line == "custom":
        text = _set_under_model(text, "base_url", base_url)
    path.write_text(text, encoding="utf-8")


def merge_mcp_servers_into_config(path: Path, servers: dict[str, Any]) -> None:
    """Replace Hub-managed MCP marker block (or append) with current servers."""
    block_lines = [_MCP_MARKER_BEGIN, "mcp_servers:"]
    if not servers:
        block_lines.append("  {}")
    else:
        for sid, entry in servers.items():
            block_lines.append(f"  {sid}:")
            for k, v in entry.items():
                if k == "args" and isinstance(v, list):
                    block_lines.append("    args:")
                    for a in v:
                        block_lines.append(f'      - "{a}"')
                elif k == "env" and isinstance(v, dict):
                    block_lines.append("    env:")
                    for ek, ev in v.items():
                        block_lines.append(f'      {ek}: "{ev}"')
                elif k == "headers" and isinstance(v, dict):
                    block_lines.append("    headers:")
                    for hk, hv in v.items():
                        block_lines.append(f'      {hk}: "{hv}"')
                else:
                    if isinstance(v, bool):
                        block_lines.append(f"    {k}: {'true' if v else 'false'}")
                    elif isinstance(v, (int, float)):
                        block_lines.append(f"    {k}: {v}")
                    else:
                        block_lines.append(f'    {k}: "{v}"')
    block_lines.append(_MCP_MARKER_END)
    block = "\n".join(block_lines) + "\n"

    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            text = ""
    else:
        text = ""

    if _MCP_MARKER_BEGIN in text and _MCP_MARKER_END in text:
        text = re.sub(
            re.escape(_MCP_MARKER_BEGIN) + r"[\s\S]*?" + re.escape(_MCP_MARKER_END),
            block.rstrip(),
            text,
            count=1,
        )
    else:
        text = (text.rstrip() + "\n\n" + block) if text.strip() else block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def sync_hub_to_hermes(
    cfg: dict[str, Any] | None = None,
    *,
    model: str = "",
    provider_id: str = "",
) -> dict[str, Any]:
    """Write Hub provider + API key + model into Hermes homes (.env + config.yaml)."""
    from .secrets import resolve_api_key
    from .settings import load_campus_config, resolve_backend_verify_tls

    cfg = cfg or load_campus_config()
    backend = cfg.get("backend") or {}
    pid = (provider_id or backend.get("type") or "").strip()
    if pid == "hybrid":
        hybrid = cfg.get("hybrid") or {}
        office = hybrid.get("office") or hybrid.get("main") or {}
        if isinstance(office, dict) and office.get("provider"):
            pid = str(office["provider"])
        else:
            pid = "openrouter"

    key_info = resolve_api_key(cfg, provider=pid)
    api_key = key_info.get("key") or ""
    env_name = str(key_info.get("env_name") or backend.get("api_key_env") or "").strip()
    base_url = str(backend.get("base_url") or "").strip()
    models = cfg.get("models") or {}
    use_model = (
        (model or "").strip()
        or str(models.get("main") or models.get("qwen_main") or models.get("fast") or "").strip()
    )

    hermes_provider = _hermes_provider_name(pid)
    verify_tls = resolve_backend_verify_tls(cfg, {"provider": pid, "route_key": "office"})
    errors: list[str] = []
    written: list[str] = []

    if not api_key and pid not in ("local-ollama",):
        msg_zh = (
            "未找到可用的 API Key，无法同步到 Hermes。"
            "请在控制中心「后端」粘贴密钥并保存，再点「同步到 Hermes」。"
        )
        msg_en = (
            "No API key found — cannot sync to Hermes. "
            "Paste a key in Control Center → Backend, Save, then Sync to Hermes."
        )
        return {
            "ok": False,
            "error": msg_zh,
            "error_zh": msg_zh,
            "error_en": msg_en,
            "provider": pid,
            "hermes_provider": hermes_provider,
        }

    updates: dict[str, str] = {}
    if env_name and api_key:
        updates[env_name] = api_key
    if hermes_provider == "custom" and api_key:
        updates["OPENAI_API_KEY"] = api_key
        if base_url:
            updates["OPENAI_BASE_URL"] = base_url
    if hermes_provider == "nvidia" and api_key:
        updates["NVIDIA_API_KEY"] = api_key
    if hermes_provider == "openrouter" and api_key:
        updates["OPENROUTER_API_KEY"] = api_key

    managed = hermes_managed_home()
    for home in hermes_config_homes():
        try:
            if home.resolve() == managed.resolve():
                _write_managed_env(
                    env_name=env_name or "OPENAI_API_KEY",
                    api_key=api_key,
                    base_url=base_url,
                    model=use_model,
                    provider_id=pid,
                    verify_tls=verify_tls,
                )
            else:
                _merge_dotenv(home / ".env", updates)
                _patch_model_yaml(
                    home / "config.yaml",
                    model=use_model,
                    provider=hermes_provider,
                    base_url=base_url,
                )
                _patch_provider_tls_yaml(
                    home / "config.yaml",
                    base_url=base_url,
                    verify_tls=verify_tls,
                )
            written.append(str(home))
        except OSError as exc:
            errors.append(f"{home}: {exc}")

    if errors and not written:
        msg_zh = "同步 Hermes 失败：" + "; ".join(errors)
        msg_en = "Hermes sync failed: " + "; ".join(errors)
        return {
            "ok": False,
            "error": msg_zh,
            "error_zh": msg_zh,
            "error_en": msg_en,
            "errors": errors,
        }

    return {
        "ok": True,
        "provider": pid,
        "hermes_provider": hermes_provider,
        "model": use_model,
        "env_name": env_name,
        "homes": written,
        "errors": errors,
        "masked": key_info.get("masked") or "",
        "note_zh": f"已同步到 Hermes：provider={hermes_provider} model={use_model or '(unset)'}",
        "note_en": f"Synced to Hermes: provider={hermes_provider} model={use_model or '(unset)'}",
    }


def explain_provider_error(err: str) -> dict[str, str]:
    """Map opaque Hermes CLI errors to Hub ZH/EN guidance."""
    low = (err or "").lower()
    if "no llm provider" in low or "hermes model" in low or "hermes setup" in low:
        return {
            "zh": (
                "Hermes 未读到 LLM 配置。请在控制中心保存 API Key 后点击「同步到 Hermes」，"
                "或确认后端 Provider 与密钥匹配（例如 NVIDIA=nvapi-…，OpenRouter=sk-or-…）。"
            ),
            "en": (
                "Hermes has no LLM provider. Save your API key in Control Center, then "
                "Sync to Hermes — or match provider + key (NVIDIA=nvapi-…, OpenRouter=sk-or-…)."
            ),
        }
    return {"zh": err or "Hermes 错误", "en": err or "Hermes error"}

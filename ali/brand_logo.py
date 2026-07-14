"""Custom UI logos (sidebar + empty-state) — stored under STATE_DIR/brand."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from .config import STATE_DIR, STATIC_DIR, ensure_state_dirs
from .settings import load_campus_config, save_campus_config

DEFAULT_LOGO = "/brand/suat-logo-color.png"
MAX_BYTES = 2 * 1024 * 1024
ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
SLOTS = ("sidebar", "empty")
SLOT_ALIASES = {
    "sidebar": "sidebar",
    "empty": "empty",
    "both": "both",
    "left": "sidebar",
    "center": "empty",
    "newchat": "empty",
    "new_chat": "empty",
}

PRESETS: list[dict[str, str]] = [
    {"id": "suat-color", "src": "/brand/suat-logo-color.png", "label_zh": "SUAT 彩标（默认）", "label_en": "SUAT color (default)"},
    {"id": "whiteboard", "src": "/brand/whiteboard.svg", "label_zh": "白板", "label_en": "Whiteboard"},
]

_SAFE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,80}$")
_BUILTIN_SRC = re.compile(r"^/brand/[a-zA-Z0-9._-]+\.(?:png|jpe?g|webp|svg)$")
_CUSTOM_SRC = re.compile(r"^/brand/custom/[a-zA-Z0-9._-]+\.(?:png|jpe?g|webp|svg)$")


def brand_custom_dir() -> Path:
    ensure_state_dirs()
    root = STATE_DIR / "brand"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _ext_of(filename: str) -> str:
    return Path(filename or "").suffix.lower()


def _normalize_slot(slot: str) -> str:
    key = str(slot or "both").strip().lower()
    out = SLOT_ALIASES.get(key)
    if not out:
        raise ValueError("slot must be sidebar, empty, or both")
    return out


def _targets(slot: str) -> tuple[str, ...]:
    s = _normalize_slot(slot)
    return SLOTS if s == "both" else (s,)


def normalize_logo_url(raw: Any) -> str:
    """Return a safe logo URL, or empty string for factory default."""
    url = str(raw or "").strip()
    if not url:
        return ""
    # Drop cache-buster for validation; keep path only
    path = url.split("?", 1)[0]
    if path == DEFAULT_LOGO or _BUILTIN_SRC.match(path) or _CUSTOM_SRC.match(path):
        return path
    return ""


def effective_logo_url(raw: Any) -> str:
    url = normalize_logo_url(raw)
    return url or DEFAULT_LOGO


def logo_urls_from_config(cfg: dict[str, Any] | None = None) -> dict[str, str]:
    data = cfg if isinstance(cfg, dict) else load_campus_config()
    ali = data.get("ali") if isinstance(data.get("ali"), dict) else {}
    return {
        "logo_sidebar": normalize_logo_url(ali.get("logo_sidebar")),
        "logo_empty": normalize_logo_url(ali.get("logo_empty")),
    }


def public_logo_state(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    urls = logo_urls_from_config(cfg)
    return {
        "logo_sidebar": urls["logo_sidebar"],
        "logo_empty": urls["logo_empty"],
        "logo_sidebar_src": effective_logo_url(urls["logo_sidebar"]),
        "logo_empty_src": effective_logo_url(urls["logo_empty"]),
        "default": DEFAULT_LOGO,
        "presets": PRESETS,
        "max_bytes": MAX_BYTES,
        "allowed_ext": sorted(ALLOWED_EXT),
    }


def resolve_custom_file(name: str) -> Path | None:
    name = str(name or "").strip().lstrip("/")
    if "/" in name or "\\" in name or not _SAFE_NAME.match(name):
        return None
    if _ext_of(name) not in ALLOWED_EXT:
        return None
    root = brand_custom_dir().resolve()
    dest = (root / name).resolve()
    if not str(dest).startswith(str(root)) or not dest.is_file():
        return None
    return dest


def _cache_bust(url: str) -> str:
    path = url.split("?", 1)[0]
    if path.startswith("/brand/custom/"):
        name = path[len("/brand/custom/") :]
        fp = resolve_custom_file(name)
        if fp:
            try:
                return f"{path}?t={int(fp.stat().st_mtime)}"
            except OSError:
                pass
    return f"{path}?t={int(time.time())}"


def _set_logo_urls(sidebar: str | None = None, empty: str | None = None) -> dict[str, Any]:
    cfg = load_campus_config()
    ali = dict(cfg.get("ali") or {})
    if sidebar is not None:
        ali["logo_sidebar"] = normalize_logo_url(sidebar)
    if empty is not None:
        ali["logo_empty"] = normalize_logo_url(empty)
    cfg["ali"] = ali
    saved = save_campus_config(cfg)
    state = public_logo_state(saved)
    state["ok"] = True
    state["logo_sidebar_src"] = _cache_bust(state["logo_sidebar_src"])
    state["logo_empty_src"] = _cache_bust(state["logo_empty_src"])
    return state


def apply_preset(preset_id: str, slot: str = "both") -> dict[str, Any]:
    pid = str(preset_id or "").strip()
    preset = next((p for p in PRESETS if p["id"] == pid), None)
    if not preset:
        raise ValueError(f"unknown preset: {pid}")
    src = preset["src"]
    # Selecting the factory default clears custom prefs
    value = "" if src == DEFAULT_LOGO else src
    mapped: dict[str, str | None] = {}
    for target in _targets(slot):
        mapped[target] = value
    return _set_logo_urls(
        sidebar=mapped.get("sidebar"),
        empty=mapped.get("empty"),
    )


def reset_logos(slot: str = "both") -> dict[str, Any]:
    mapped: dict[str, str | None] = {}
    for target in _targets(slot):
        mapped[target] = ""
        # Best-effort cleanup of custom files for that slot
        root = brand_custom_dir()
        for p in root.glob(f"{target}.*"):
            if p.suffix.lower() in ALLOWED_EXT:
                try:
                    p.unlink()
                except OSError:
                    pass
    return _set_logo_urls(
        sidebar=mapped.get("sidebar"),
        empty=mapped.get("empty"),
    )


def save_upload(data: bytes, filename: str, slot: str = "both") -> dict[str, Any]:
    if not data:
        raise ValueError("empty upload")
    if len(data) > MAX_BYTES:
        raise ValueError(f"logo too large (max {MAX_BYTES // (1024 * 1024)}MB)")
    ext = _ext_of(filename)
    if ext not in ALLOWED_EXT:
        raise ValueError("allowed types: png, jpg, jpeg, webp, svg")
    # Light magic sniff for raster formats
    if ext != ".svg":
        head = data[:16]
        if ext == ".png" and not head.startswith(b"\x89PNG"):
            raise ValueError("invalid PNG file")
        if ext in {".jpg", ".jpeg"} and not head.startswith(b"\xff\xd8\xff"):
            raise ValueError("invalid JPEG file")
        if ext == ".webp" and not (len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"):
            raise ValueError("invalid WEBP file")
    else:
        text = data[:256].decode("utf-8", errors="ignore").lstrip().lower()
        if "<svg" not in text:
            raise ValueError("invalid SVG file")

    root = brand_custom_dir()
    mapped: dict[str, str | None] = {}
    for target in _targets(slot):
        # Remove previous files for this slot (any ext)
        for old in root.glob(f"{target}.*"):
            if old.suffix.lower() in ALLOWED_EXT:
                try:
                    old.unlink()
                except OSError:
                    pass
        dest = root / f"{target}{ext}"
        dest.write_bytes(data)
        mapped[target] = f"/brand/custom/{target}{ext}"
    return _set_logo_urls(
        sidebar=mapped.get("sidebar"),
        empty=mapped.get("empty"),
    )


def builtin_static_exists(rel: str) -> bool:
    name = rel.lstrip("/")
    if name.startswith("brand/"):
        name = name[len("brand/") :]
    return (STATIC_DIR / "brand" / name).is_file()

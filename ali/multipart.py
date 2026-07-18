"""Minimal multipart/form-data parser (stdlib only)."""

from __future__ import annotations

from typing import Any


def is_zip_upload(file_part: dict[str, Any]) -> bool:
    """True if multipart file looks like a ZIP (name, content-type, or PK magic)."""
    name = (file_part.get("filename") or "").lower()
    ctype = (file_part.get("content_type") or "").lower()
    data = file_part.get("data") or b""
    if name.endswith(".zip"):
        return True
    if "zip" in ctype or ctype in ("application/x-zip-compressed", "application/octet-stream"):
        if data[:2] == b"PK":
            return True
    if data[:2] == b"PK":
        return True
    return False


def parse_multipart(handler) -> dict[str, Any]:
    """Return {fields: {name: str}, files: [{name, filename, content_type, data, relative_path?}]}."""
    ctype = handler.headers.get("Content-Type") or ""
    if "multipart/form-data" not in ctype:
        return {"fields": {}, "files": []}
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {"fields": {}, "files": []}
    if length > 80 * 1024 * 1024:
        raise ValueError("upload too large (max 80MB)")
    raw = handler.rfile.read(length)
    boundary = ""
    for part in ctype.split(";"):
        part = part.strip()
        if part.lower().startswith("boundary="):
            boundary = part.split("=", 1)[1].strip().strip('"')
            break
    if not boundary:
        raise ValueError("missing multipart boundary")
    marker = ("--" + boundary).encode("utf-8")
    chunks = raw.split(marker)
    fields: dict[str, str] = {}
    files: list[dict[str, Any]] = []
    for chunk in chunks:
        if not chunk or chunk in (b"--\r\n", b"--", b"\r\n", b"--\r\n\r\n"):
            continue
        if chunk.startswith(b"--"):
            continue
        if chunk.startswith(b"\r\n"):
            chunk = chunk[2:]
        if chunk.endswith(b"\r\n"):
            chunk = chunk[:-2]
        header_blob, sep, body = chunk.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = {}
        for line in header_blob.decode("utf-8", errors="replace").split("\r\n"):
            if ":" in line:
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        disp = headers.get("content-disposition", "")
        name = ""
        filename = None
        for token in disp.split(";"):
            token = token.strip()
            if token.startswith("name="):
                name = token.split("=", 1)[1].strip().strip('"')
            elif token.startswith("filename="):
                filename = token.split("=", 1)[1].strip().strip('"')
        if filename is not None:
            files.append(
                {
                    "name": name or "file",
                    "filename": filename,
                    "content_type": headers.get("content-type", "application/octet-stream"),
                    "data": body,
                }
            )
        else:
            fields[name or "field"] = body.decode("utf-8", errors="replace")
    return {"fields": fields, "files": files}

"""Extract readable text from office/tabular files (stdlib only)."""

from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}


def extract_file_text(path: Path | str, *, max_bytes: int = 12000) -> dict[str, Any]:
    """Return text excerpt for supported files; never invent content."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "path": str(p), "error": "not a file"}
    suf = p.suffix.lower()
    try:
        if suf in (".xlsx", ".xlsm"):
            text = _xlsx_to_text(p, max_chars=max_bytes)
            return {"ok": True, "path": str(p), "kind": "xlsx", "content": text, "truncated": len(text) >= max_bytes}
        if suf == ".xls":
            return {
                "ok": False,
                "path": str(p),
                "kind": "xls",
                "error": "legacy .xls is binary; please re-save as .xlsx or .csv",
            }
        if suf == ".csv":
            raw = p.read_bytes()[: max_bytes * 2]
            text = raw.decode("utf-8", errors="replace")
            if "\x00" in text[:200]:
                text = raw.decode("gb18030", errors="replace")
            return {"ok": True, "path": str(p), "kind": "csv", "content": text[:max_bytes], "truncated": p.stat().st_size > max_bytes}
        if suf in (".tsv", ".txt", ".md", ".json", ".yaml", ".yml", ".py", ".r", ".R"):
            raw = p.read_bytes()[:max_bytes]
            return {
                "ok": True,
                "path": str(p),
                "kind": "text",
                "content": raw.decode("utf-8", errors="replace"),
                "truncated": p.stat().st_size > max_bytes,
            }
        if suf in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf", ".docx", ".zip"):
            return {"ok": False, "path": str(p), "kind": suf.lstrip("."), "skipped": True, "reason": "binary"}
        # fallback text attempt
        raw = p.read_bytes()[:min(max_bytes, 4000)]
        if b"\x00" in raw[:512]:
            return {"ok": False, "path": str(p), "skipped": True, "reason": "binary"}
        return {
            "ok": True,
            "path": str(p),
            "kind": "text",
            "content": raw.decode("utf-8", errors="replace"),
            "truncated": p.stat().st_size > max_bytes,
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": str(p), "error": str(exc)}


def _col_row(cell_ref: str) -> tuple[int, int]:
    col = 0
    row = 0
    for ch in cell_ref:
        if ch.isalpha():
            col = col * 26 + (ord(ch.upper()) - 64)
        elif ch.isdigit():
            row = row * 10 + int(ch)
    return max(col - 1, 0), max(row - 1, 0)


def _shared_strings(z: zipfile.ZipFile) -> list[str]:
    try:
        data = z.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    out: list[str] = []
    for si in root.findall("m:si", _NS):
        parts = [t.text or "" for t in si.findall(".//m:t", _NS)]
        out.append("".join(parts))
    return out


def _sheet_rows(z: zipfile.ZipFile, sheet_path: str, shared: list[str], *, max_rows: int = 80, max_cols: int = 40) -> list[list[str]]:
    root = ET.fromstring(z.read(sheet_path))
    grid: dict[tuple[int, int], str] = {}
    max_r, max_c = 0, 0
    for c in root.findall(".//m:c", _NS):
        ref = c.get("r") or ""
        if not ref:
            continue
        col, row = _col_row(ref)
        if row >= max_rows or col >= max_cols:
            continue
        max_r = max(max_r, row)
        max_c = max(max_c, col)
        t = c.get("t")
        v_el = c.find("m:v", _NS)
        if v_el is None or v_el.text is None:
            is_el = c.find("m:is", _NS)
            if is_el is not None:
                parts = [t2.text or "" for t2 in is_el.findall(".//m:t", _NS)]
                grid[(row, col)] = "".join(parts)
            continue
        val = v_el.text
        if t == "s":
            try:
                val = shared[int(val)]
            except (ValueError, IndexError):
                pass
        elif t == "b":
            val = "TRUE" if val == "1" else "FALSE"
        grid[(row, col)] = val
    rows: list[list[str]] = []
    for r in range(max_r + 1):
        rows.append([grid.get((r, c), "") for c in range(max_c + 1)])
    return rows


def _list_sheets(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Return [(name, path_in_zip), ...]."""
    try:
        wb = ET.fromstring(z.read("xl/workbook.xml"))
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    except KeyError:
        return [("Sheet1", "xl/worksheets/sheet1.xml")]
    rid_to_target: dict[str, str] = {}
    for rel in rels:
        rid = rel.get("Id")
        target = rel.get("Target") or ""
        if rid and target:
            if not target.startswith("xl/"):
                target = "xl/" + target.lstrip("/")
            rid_to_target[rid] = target
    sheets: list[tuple[str, str]] = []
    for sh in wb.findall("m:sheets/m:sheet", _NS):
        name = sh.get("name") or "Sheet"
        rid = sh.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        path = rid_to_target.get(rid or "", "")
        if path:
            sheets.append((name, path))
    return sheets or [("Sheet1", "xl/worksheets/sheet1.xml")]


def _xlsx_to_text(path: Path, *, max_chars: int = 12000, max_sheets: int = 3) -> str:
    lines: list[str] = [f"[Excel] {path.name}"]
    with zipfile.ZipFile(path, "r") as z:
        shared = _shared_strings(z)
        for name, sheet_path in _list_sheets(z)[:max_sheets]:
            lines.append(f"--- sheet: {name} ---")
            try:
                rows = _sheet_rows(z, sheet_path, shared)
            except KeyError:
                lines.append("(sheet missing)")
                continue
            buf = io.StringIO()
            writer = csv.writer(buf)
            for row in rows:
                if any(cell.strip() for cell in row):
                    writer.writerow(row)
            chunk = buf.getvalue().strip()
            if chunk:
                lines.append(chunk)
            else:
                lines.append("(empty)")
            if sum(len(x) for x in lines) >= max_chars:
                break
    text = "\n".join(lines)
    if len(text) > max_chars:
        return text[:max_chars] + "\n… [truncated]"
    return text


def read_xlsx_matrix(path: Path | str, *, max_rows: int = 120, max_cols: int = 40) -> dict[str, Any]:
    """Read first sheet of an .xlsx into a list of row lists."""
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": "not a file", "path": str(p)}
    try:
        with zipfile.ZipFile(p, "r") as z:
            shared = _shared_strings(z)
            sheets = _list_sheets(z)
            name, sheet_path = sheets[0]
            rows = _sheet_rows(z, sheet_path, shared, max_rows=max_rows, max_cols=max_cols)
        return {"ok": True, "path": str(p), "sheet": name, "rows": rows}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "path": str(p)}


def _col_letter(idx: int) -> str:
    n = idx + 1
    s = ""
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx_matrix(path: Path | str, rows: list[list[str]], *, sheet_name: str = "Sheet1") -> dict[str, Any]:
    """Write a minimal .xlsx (shared strings + one sheet) using stdlib only."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    # collect shared strings
    shared: list[str] = []
    index: dict[str, int] = {}

    def sid(val: str) -> int:
        if val not in index:
            index[val] = len(shared)
            shared.append(val)
        return index[val]

    sheet_rows_xml: list[str] = []
    for r_i, row in enumerate(rows):
        cells = []
        for c_i, raw in enumerate(row):
            val = "" if raw is None else str(raw)
            ref = f"{_col_letter(c_i)}{r_i + 1}"
            if val == "":
                continue
            if re.fullmatch(r"-?\d+(\.\d+)?", val):
                cells.append(f'<c r="{ref}"><v>{escape(val)}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="s"><v>{sid(val)}</v></c>')
        sheet_rows_xml.append(f'<row r="{r_i + 1}">{"".join(cells)}</row>')

    sst_items = [f"<si><t>{escape(s)}</t></si>" for s in shared]
    sst = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">{"".join(sst_items)}</sst>'
    )
    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(sheet_rows_xml)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<sheets><sheet name="{escape(sheet_name)}" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    wb_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/sharedStrings" '
        'Target="sharedStrings.xml"/>'
        "</Relationships>"
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/sharedStrings.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'
        "</Types>"
    )
    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        "</Relationships>"
    )

    with zipfile.ZipFile(p, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", root_rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)
        z.writestr("xl/sharedStrings.xml", sst)
    return {"ok": True, "path": str(p), "rows": len(rows), "shared_strings": len(shared)}

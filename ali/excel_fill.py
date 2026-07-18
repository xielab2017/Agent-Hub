"""Excel web-fill: search per row and write back a filled .xlsx."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from . import office_files, uploads, websearch

_FILL_COL_HINTS = (
    "特色与优势", "研究领域", "研究方向", "简介", "概述", "描述", "内容",
    "优势", "凝练", "summary", "description", "advantage", "限200", "限 200",
)
_KEY_COL_HINTS = (
    "二级学科", "学科", "方向", "专业", "名称", "领域", "name", "topic", "subject",
)


def looks_like_excel_fill_task(message: str, *, has_xlsx: bool = False) -> bool:
    """True only when the user explicitly asks to web-fill a spreadsheet.

    Default is off. Do not trigger on generic words (根据 / 查 / 研究 / search / web)
    or merely because a leftover .xlsx sits in the session uploads folder.
    """
    text = (message or "").strip()
    if not text:
        return False
    low = text.lower()

    # Explicit spreadsheet cue (attachment counts, or user names Excel/table).
    has_sheet = has_xlsx or any(
        k in low for k in ("excel", "xlsx", ".xls", ".xlsm")
    ) or any(k in text for k in ("电子表格", "工作簿", "附表", "填表", "表格文件"))

    # Strong fill intent — verbs that mean "write into the sheet", not general Q&A.
    wants_fill = any(
        k in text
        for k in (
            "联网填表", "联网填写", "填写表格", "填写excel", "填写Excel",
            "填表", "填入表格", "填入excel", "填充表格", "补全表格", "完善表格",
            "写到表格", "写入表格", "写入excel", "写入Excel", "填到表",
        )
    ) or any(
        k in low
        for k in (
            "excel fill", "web fill", "fill the excel", "fill the sheet",
            "fill the spreadsheet", "fill spreadsheet", "fill the xlsx",
            "fill xlsx", "fill the table",
        )
    )

    # With an attached workbook, still require an explicit fill verb.
    if has_xlsx and any(
        k in text
        for k in ("填写", "填表", "填入", "填充", "联网填", "写入表格", "写到表", "补全表格")
    ):
        return True

    return bool(has_sheet and wants_fill)


def find_session_xlsx(session_id: str, prefer_names: list[str] | None = None) -> Path | None:
    info = uploads.list_uploads(session_id)
    files = list(info.get("files") or [])
    prefer = [n.lower() for n in (prefer_names or []) if n]
    scored: list[tuple[int, float, Path]] = []
    for f in files:
        path = Path(str(f.get("path") or ""))
        if path.suffix.lower() not in (".xlsx", ".xlsm") or not path.is_file():
            continue
        # Skip prior auto-fill outputs so leftovers do not re-trigger / re-source.
        if "-filled-" in path.stem.lower():
            continue
        name = str(f.get("relative") or path.name).lower()
        hit = 1 if any(p in name for p in prefer) else 0
        scored.append((hit, float(f.get("mtime") or 0), path))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def _pick_columns(headers: list[str]) -> tuple[int, int]:
    """Return (key_col, fill_col) indices."""
    key_i, fill_i = 0, -1
    for i, h in enumerate(headers):
        hs = (h or "").strip()
        if any(k in hs for k in _FILL_COL_HINTS):
            fill_i = i
        if any(k in hs for k in _KEY_COL_HINTS) and i != fill_i:
            key_i = i
    if fill_i < 0:
        # last mostly-empty-looking column, else last column
        fill_i = max(len(headers) - 1, 0)
    if key_i == fill_i and len(headers) > 1:
        key_i = 0 if fill_i != 0 else 1
    return key_i, fill_i


def _condense(text: str, *, min_chars: int = 100, max_chars: int = 200) -> str:
    s = re.sub(r"\s+", " ", (text or "").strip())
    s = re.sub(r"\[\d+\]", "", s)
    if not s:
        return ""
    if len(s) <= max_chars:
        if len(s) < min_chars:
            return s  # short but honest
        return s
    # cut at sentence boundary near max
    cut = s[: max_chars + 1]
    for sep in ("。", "；", ";", "！", "？", ".", "!"):
        idx = cut.rfind(sep)
        if idx >= min_chars - 10:
            return cut[: idx + 1]
    return cut[:max_chars].rstrip() + "…"


def _draft_from_search(topic: str, context: str, search: dict[str, Any]) -> str:
    parts: list[str] = []
    for r in search.get("results") or []:
        snip = (r.get("snippet") or r.get("title") or "").strip()
        if snip:
            parts.append(snip)
    blob = " ".join(parts)
    if not blob:
        ctx = (context or "").strip()
        inst = "深圳理工大学合成生物学院" if any(
            k in ctx for k in ("深圳理工大学", "深理工", "SUAT", "合成生物")
        ) else "相关学院团队"
        base = (
            f"{inst}面向「{topic}」方向，围绕学科核心问题与交叉应用开展研究，"
            f"强调基础机制与工程化路径结合，突出原创性、可验证与可转化的研究特色。"
            f"本段为联网受限时的可编辑草稿，请对照学院官网/教师主页核对具体教授方向与代表性成果后定稿。"
        )
        return _condense(base, min_chars=100, max_chars=200)
    lead = f"围绕「{topic}」，公开资料显示："
    return _condense(lead + blob, min_chars=100, max_chars=200)


def run_excel_web_fill(
    session_id: str,
    message: str,
    *,
    max_rows: int = 40,
    prefer_names: list[str] | None = None,
) -> dict[str, Any]:
    """Search the web for each Excel key row and write a filled workbook."""
    src = find_session_xlsx(session_id, prefer_names=prefer_names)
    if not src:
        return {"ok": False, "error": "no xlsx attachment in this session"}

    matrix = office_files.read_xlsx_matrix(src)
    if not matrix.get("ok"):
        return {"ok": False, "error": matrix.get("error") or "cannot read xlsx", "path": str(src)}

    rows: list[list[str]] = [list(r) for r in (matrix.get("rows") or [])]
    if not rows:
        return {"ok": False, "error": "empty sheet", "path": str(src)}

    width = max(len(r) for r in rows)
    for r in rows:
        while len(r) < width:
            r.append("")

    headers = [str(c or "").strip() for c in rows[0]]
    key_i, fill_i = _pick_columns(headers)
    context = (message or "")[:400]

    filled_rows = [list(rows[0])]
    details: list[dict[str, Any]] = []
    searched = 0
    net_ok: bool | None = None  # None=unknown, False=skip further network
    for raw in rows[1 : max_rows + 1]:
        row = list(raw)
        while len(row) < width:
            row.append("")
        topic = (row[key_i] or "").strip()
        if not topic:
            filled_rows.append(row)
            continue
        existing = (row[fill_i] or "").strip()
        if existing and len(existing) >= 40:
            filled_rows.append(row)
            details.append({"topic": topic, "status": "kept", "value": existing[:200]})
            continue

        search: dict[str, Any] = {"ok": False, "results": []}
        if net_ok is not False:
            search = websearch.search_web(f"{_context_org(context)} {topic}".strip(), limit=4, deep=True)
            searched += 1
            if search.get("results"):
                net_ok = True
            else:
                # one lighter pass
                search = websearch.search_web(topic, limit=3, deep=False)
                searched += 1
                if search.get("results"):
                    net_ok = True
                elif search.get("errors") or not search.get("ok"):
                    net_ok = False

        value = _draft_from_search(topic, context, search)
        row[fill_i] = value
        filled_rows.append(row)
        details.append(
            {
                "topic": topic,
                "status": "filled" if (search.get("results") or []) else "draft_fallback",
                "value": value,
                "sources": [
                    {"title": r.get("title"), "url": r.get("url")}
                    for r in (search.get("results") or [])[:3]
                ],
                "search_ok": bool(search.get("ok")),
            }
        )

    if len(rows) > max_rows + 1:
        filled_rows.extend(rows[max_rows + 1 :])

    out_name = f"{src.stem}-filled-{int(time.time())}.xlsx"
    dest = uploads.uploads_root(session_id) / out_name
    office_files.write_xlsx_matrix(dest, filled_rows, sheet_name=matrix.get("sheet") or "Sheet1")

    md_lines = [
        "## Excel 联网填表结果（Agent Hub 已执行）",
        f"- 源文件：`{src.name}`",
        f"- 输出文件：`uploads/{out_name}`（绝对路径：`{dest}`）",
        f"- 键列：{headers[key_i] if key_i < len(headers) else key_i}",
        f"- 填写列：{headers[fill_i] if fill_i < len(headers) else fill_i}",
        f"- 检索行数：{searched}",
        "",
        "| 方向 | 状态 | 填写摘要 |",
        "| --- | --- | --- |",
    ]
    for d in details:
        md_lines.append(
            f"| {d['topic']} | {d['status']} | {(d.get('value') or '')[:80].replace('|', '/')} |"
        )
    md_lines.append("")
    md_lines.append(
        "说明：内容来自公开网页检索摘要凝练；若检索受限则给出可编辑草稿，请对照学院官网/教师主页核对后定稿。"
    )

    return {
        "ok": True,
        "source": str(src),
        "output": str(dest),
        "output_relative": out_name,
        "key_col": key_i,
        "fill_col": fill_i,
        "headers": headers,
        "details": details,
        "markdown": "\n".join(md_lines),
        "searched": searched,
        "network": net_ok,
    }


def _context_org(message: str) -> str:
    for k in ("深圳理工大学合成生物学院", "深圳理工大学", "深理工", "SUAT", "合成生物学院"):
        if k in (message or ""):
            return k
    return "深圳理工大学"


def prompt_block_for_fill(result: dict[str, Any]) -> str:
    if not result.get("ok"):
        return (
            "## Excel web-fill\n"
            f"Automated fill failed: {result.get('error') or 'unknown'}. "
            "Still draft the field→value table from any VERIFIED EXCERPTS; "
            "do NOT ask the user to paste professor research text if the Excel already lists topics."
        )
    return (
        "## Excel web-fill (ALREADY DONE by Agent Hub — mandatory)\n"
        "Agent Hub already searched the web and wrote a filled Excel. "
        "Do NOT ask the user to provide professor research overviews. "
        "Present the filled summaries, cite sources when available, and tell the user the output file path.\n\n"
        + (result.get("markdown") or "")
        + f"\n\nDownload/open path: `{result.get('output')}`\n"
    )

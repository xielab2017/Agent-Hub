"""Bounded, read-only discovery for local omics datasets."""

from __future__ import annotations

import csv
import hashlib
import ntpath
import os
import posixpath
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Optional

from .emp_models import DatasetFile, DatasetManifest, new_id


DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_FILES = 500
DEFAULT_PREVIEW_BYTES = 512 * 1024
DEFAULT_PREVIEW_ROWS = 20
DEFAULT_SAMPLE_ID_ROWS = 5000
DEFAULT_CHECKSUM_BYTES = 64 * 1024 * 1024
DEFAULT_METADATA_ROWS = 5000
DEFAULT_METADATA_COLUMNS = 100
DEFAULT_METADATA_LEVELS = 50
DEFAULT_METADATA_VALUE_LENGTH = 128
TABLE_EXTENSIONS = {".csv", ".tsv", ".txt"}
IGNORED_DIRS = {
    ".git", ".hg", ".svn", ".venv", "venv", "env", "node_modules",
    "__pycache__", ".idea", ".vscode", ".trellis",
}
SENSITIVE_NAMES = re.compile(r"(?:secret|credential|password|private[_-]?key|\.env)", re.I)


class DiscoveryError(ValueError):
    pass


def path_is_within_text(candidate: str, root: str, *, platform: str = "posix") -> bool:
    """Cross-platform lexical containment helper used by config validation tests."""
    module = ntpath if platform == "windows" else posixpath
    candidate_norm = module.normcase(module.abspath(module.normpath(candidate)))
    root_norm = module.normcase(module.abspath(module.normpath(root)))
    try:
        return module.commonpath([candidate_norm, root_norm]) == root_norm
    except ValueError:
        return False


def resolve_allowed_path(raw: str | Path, allowed_roots: Iterable[str | Path]) -> Path:
    candidate = Path(raw).expanduser()
    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise DiscoveryError(f"path not found: {candidate}") from exc
    except OSError as exc:
        raise DiscoveryError(f"cannot resolve path: {candidate}") from exc

    roots: list[Path] = []
    for root in allowed_roots:
        try:
            roots.append(Path(root).expanduser().resolve(strict=True))
        except OSError:
            continue
    if not roots:
        raise DiscoveryError("no allowed roots are configured")
    for root in roots:
        try:
            if os.path.commonpath([os.path.normcase(str(resolved)), os.path.normcase(str(root))]) == os.path.normcase(str(root)):
                return resolved
        except ValueError:
            continue
    raise DiscoveryError("path is outside the allowed roots")


def _sha256(path: Path, max_bytes: int) -> str:
    if path.stat().st_size > max_bytes:
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _delimiter(sample: str, suffix: str) -> str:
    if suffix == ".tsv":
        return "\t"
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;").delimiter
    except csv.Error:
        return "\t" if sample.count("\t") > sample.count(",") else ","


def _preview_table(path: Path, *, max_bytes: int, max_rows: int) -> tuple[str, list[list[str]], Optional[int], Optional[int], bool]:
    with path.open("rb") as handle:
        raw = handle.read(max_bytes + 1)
    truncated = len(raw) > max_bytes
    text = raw[:max_bytes].decode("utf-8-sig", errors="replace")
    delimiter = _delimiter(text[:8192], path.suffix.lower())
    rows: list[list[str]] = []
    try:
        reader = csv.reader(text.splitlines(), delimiter=delimiter)
        for row in reader:
            rows.append([str(cell).strip() for cell in row])
            if len(rows) >= max_rows:
                break
    except csv.Error:
        rows = []
    columns = max((len(row) for row in rows), default=0) or None
    line_count = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    estimated_rows = None if truncated else max(0, line_count - 1)
    return delimiter, rows, estimated_rows, columns, truncated


def _role_for_name(path: Path) -> str:
    name = path.name.lower()
    if path.suffix.lower() == ".bam":
        return "bam"
    if path.suffix.lower() in {".bed", ".narrowpeak", ".broadpeak"}:
        return "peak"
    if any(token in name for token in ("metadata", "meta_data", "mapping", "sample_info", "phenotype")):
        return "metadata"
    if any(token in name for token in ("taxonomy", "tax_table", "taxa")):
        return "taxonomy"
    if any(token in name for token in ("clinical", "patient")):
        return "clinical"
    if any(token in name for token in ("count", "abundance", "otu", "asv", "feature", "expression", "level-")):
        return "assay"
    return "unknown"


def _omics_type(files: list[DatasetFile]) -> str:
    names = " ".join(item.path.lower() for item in files)
    if any(token in names for token in ("16s", "otu", "asv", "taxonomy", "abundance")):
        return "microbiome_16s"
    if any(token in names for token in ("rnaseq", "rna-seq", "transcript", "counts")):
        return "transcriptomics"
    if any(token in names for token in ("metabol", "metabo")):
        return "metabolomics"
    if any(item.role in {"bam", "peak"} for item in files):
        return "chipseq"
    if any(item.role == "clinical" for item in files):
        return "clinical"
    return "unknown"


def _sample_values(
    file: DatasetFile,
    *,
    assay_columns: bool,
    workspace: Optional[Path] = None,
    max_rows: int = DEFAULT_SAMPLE_ID_ROWS,
) -> list[str]:
    if not file.preview:
        return []
    if assay_columns:
        return [value for value in file.preview[0][1:] if value]
    if workspace is not None and file.delimiter:
        values: list[str] = []
        try:
            with (workspace / file.path).open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
                reader = csv.reader(handle, delimiter=file.delimiter)
                next(reader, None)
                for row in reader:
                    if row and str(row[0]).strip():
                        values.append(str(row[0]).strip())
                    if len(values) >= max_rows:
                        break
            return values
        except (OSError, csv.Error):
            pass
    return [row[0] for row in file.preview[1:] if row and row[0]]


def _pair_files(files: list[DatasetFile], workspace: Path) -> tuple[str, str, dict[str, Any], list[str]]:
    warnings: list[str] = []
    assay = next((item for item in files if item.role == "assay"), None)
    metadata = next((item for item in files if item.role in {"metadata", "clinical"}), None)
    tables = [item for item in files if Path(item.path).suffix.lower() in TABLE_EXTENSIONS]
    if assay is None and tables:
        assay = max(tables, key=lambda item: item.columns or 0)
        assay.role = "assay"
    if metadata is None:
        metadata = next((item for item in tables if item is not assay), None)
        if metadata is not None:
            metadata.role = "metadata"
    if assay is None:
        warnings.append("No assay matrix was identified.")
        return "unknown", "", {}, warnings
    if metadata is None:
        warnings.append("No metadata table was identified.")
        return "features_in_rows", "", {}, warnings

    metadata_ids = set(_sample_values(metadata, assay_columns=False, workspace=workspace))
    assay_columns = set(_sample_values(assay, assay_columns=True))
    assay_rows = set(_sample_values(assay, assay_columns=False, workspace=workspace))
    column_matches = assay_columns & metadata_ids
    row_matches = assay_rows & metadata_ids
    features_in_rows = len(column_matches) >= len(row_matches)
    assay_ids = assay_columns if features_in_rows else assay_rows
    matched = sorted(assay_ids & metadata_ids)
    if not matched:
        warnings.append("Assay and metadata sample identifiers did not match in the bounded preview.")
    elif len(matched) < len(metadata_ids):
        warnings.append(f"{len(metadata_ids) - len(matched)} metadata sample(s) were not matched in the preview.")
    sample_id_column = metadata.preview[0][0] if metadata.preview and metadata.preview[0] else ""
    return (
        "features_in_rows" if features_in_rows else "features_in_columns",
        sample_id_column,
        {
            "assay": len(assay_ids),
            "metadata": len(metadata_ids),
            "matched": len(matched),
            "assay_only": sorted(assay_ids - metadata_ids)[:50],
            "metadata_only": sorted(metadata_ids - assay_ids)[:50],
        },
        warnings,
    )


def _metadata_summary(
    files: list[DatasetFile],
    workspace: Path,
    *,
    max_rows: int = DEFAULT_METADATA_ROWS,
    max_columns: int = DEFAULT_METADATA_COLUMNS,
    max_levels: int = DEFAULT_METADATA_LEVELS,
) -> dict[str, Any]:
    metadata = next((item for item in files if item.role in {"metadata", "clinical"}), None)
    if metadata is None or not metadata.delimiter:
        return {}
    try:
        path = resolve_allowed_path(workspace / metadata.path, [workspace])
        with path.open("r", encoding="utf-8-sig", errors="replace", newline="") as handle:
            reader = csv.reader(handle, delimiter=metadata.delimiter)
            headers = [str(value).strip() for value in (next(reader, []) or [])][:max_columns]
            if not headers:
                return {}
            counts = [Counter() for _ in headers]
            non_empty = [0 for _ in headers]
            overflow = [False for _ in headers]
            rows_scanned = 0
            truncated = False
            for row in reader:
                if rows_scanned >= max_rows:
                    truncated = True
                    break
                rows_scanned += 1
                for index in range(min(len(row), len(headers))):
                    value = str(row[index]).strip()
                    if not value:
                        continue
                    non_empty[index] += 1
                    if len(value) > DEFAULT_METADATA_VALUE_LENGTH:
                        overflow[index] = True
                        continue
                    if value not in counts[index] and len(counts[index]) >= max_levels:
                        overflow[index] = True
                        continue
                    counts[index][value] += 1
    except (OSError, csv.Error, DiscoveryError):
        return {}

    categorical: dict[str, Any] = {}
    for index, header in enumerate(headers):
        if index == 0 or not header or overflow[index] or not counts[index]:
            continue
        unique = len(counts[index])
        if unique > 20 and unique / max(1, non_empty[index]) > 0.5:
            continue
        categorical[header] = {
            "levels": [
                {"value": value, "count": count}
                for value, count in counts[index].items()
            ],
            "truncated": truncated,
        }
    return {
        "columns": headers,
        "categorical": categorical,
        "rows_scanned": rows_scanned,
        "truncated": truncated,
    }


def select_manifest_pairing(
    manifest: DatasetManifest,
    *,
    assay_path: str,
    metadata_path: str,
) -> DatasetManifest:
    """Select one assay/metadata pair and recompute bounded sample matching."""
    assay_path = str(assay_path or "").replace("\\", "/")
    metadata_path = str(metadata_path or "").replace("\\", "/")
    if not assay_path or not metadata_path or assay_path == metadata_path:
        raise DiscoveryError("assay and metadata must be different manifest files")
    by_path = {item.path: item for item in manifest.files}
    assay = by_path.get(assay_path)
    metadata = by_path.get(metadata_path)
    if assay is None or metadata is None:
        raise DiscoveryError("selected pairing file is not in the manifest")
    if Path(assay.path).suffix.lower() not in TABLE_EXTENSIONS or Path(metadata.path).suffix.lower() not in TABLE_EXTENSIONS:
        raise DiscoveryError("Phase 1 pairing requires tabular assay and metadata files")
    for item in manifest.files:
        if item.role in {"assay", "metadata"}:
            item.role = "unknown"
    assay.role = "assay"
    metadata.role = "metadata"
    workspace = Path(manifest.workspace).resolve(strict=True)
    orientation, sample_id_column, overlap, warnings = _pair_files(manifest.files, workspace)
    manifest.orientation = orientation
    manifest.sample_id_column = sample_id_column
    manifest.sample_overlap = overlap
    manifest.metadata_summary = _metadata_summary(manifest.files, workspace)
    retained = [warning for warning in manifest.warnings if "sample" not in warning.lower() and "assay" not in warning.lower()]
    manifest.warnings = list(dict.fromkeys(retained + warnings))
    return manifest


def scan_dataset(
    root: str | Path,
    *,
    allowed_roots: Iterable[str | Path],
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_files: int = DEFAULT_MAX_FILES,
    preview_bytes: int = DEFAULT_PREVIEW_BYTES,
    preview_rows: int = DEFAULT_PREVIEW_ROWS,
    checksum_bytes: int = DEFAULT_CHECKSUM_BYTES,
    experiment_name: str = "",
) -> DatasetManifest:
    workspace = resolve_allowed_path(root, allowed_roots)
    if not workspace.is_dir():
        raise DiscoveryError("scan path must be a directory")
    if max_depth < 0 or max_depth > 10:
        raise DiscoveryError("max_depth must be between 0 and 10")

    discovered: list[DatasetFile] = []
    warnings: list[str] = []
    for current, dirs, names in os.walk(workspace, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(workspace).parts)
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not name.startswith(".")]
        if depth >= max_depth:
            dirs[:] = []
        for name in sorted(names):
            if len(discovered) >= max_files:
                warnings.append(f"File scan stopped at the configured limit ({max_files}).")
                break
            if name.startswith(".") or SENSITIVE_NAMES.search(name):
                continue
            path = current_path / name
            try:
                resolved = resolve_allowed_path(path, [workspace])
                if not resolved.is_file():
                    continue
                stat = resolved.stat()
            except (DiscoveryError, OSError):
                continue
            role = _role_for_name(resolved)
            delimiter = ""
            preview: list[list[str]] = []
            rows: Optional[int] = None
            columns: Optional[int] = None
            if resolved.suffix.lower() in TABLE_EXTENSIONS:
                delimiter, preview, rows, columns, truncated = _preview_table(
                    resolved, max_bytes=preview_bytes, max_rows=preview_rows
                )
                if truncated:
                    warnings.append(f"Preview truncated for {resolved.name}.")
            digest = _sha256(resolved, checksum_bytes)
            if not digest:
                warnings.append(f"Checksum deferred for large file {resolved.name}.")
            discovered.append(
                DatasetFile(
                    role=role,
                    path=resolved.relative_to(workspace).as_posix(),
                    size=stat.st_size,
                    mtime=stat.st_mtime,
                    sha256=digest,
                    delimiter=delimiter,
                    rows=rows,
                    columns=columns,
                    # Persist only the schema row. Sample values remain local and are
                    # re-read by bounded validation helpers when needed.
                    preview=preview[:1],
                )
            )
        if len(discovered) >= max_files:
            break

    if not discovered:
        raise DiscoveryError("no supported data files were found")
    orientation, sample_id_column, overlap, pair_warnings = _pair_files(discovered, workspace)
    warnings.extend(pair_warnings)
    label = experiment_name.strip() or re.sub(r"[^A-Za-z0-9_-]+", "_", workspace.name).strip("_") or "study"
    manifest = DatasetManifest(
        manifest_id=new_id("manifest"),
        workspace=str(workspace),
        omics_type=_omics_type(discovered),
        experiment_name=label,
        files=discovered,
        orientation=orientation,
        sample_id_column=sample_id_column,
        sample_overlap=overlap,
        metadata_summary=_metadata_summary(discovered, workspace),
        warnings=list(dict.fromkeys(warnings)),
    )
    return manifest

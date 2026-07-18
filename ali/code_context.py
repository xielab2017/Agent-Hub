"""Code-context detection for student uploads.

When a student drops a `.R`, `.py`, `.ipynb`, or similar file into the chat,
we want the LLM to know:
  * which language the file is in (R, Python, Julia, bash, …)
  * which packages / libraries it depends on (so the LLM cites the right API
    instead of guessing)
  * short, pasteable hints about how those packages are typically used in
    bioinformatics & multi-omics workflows

The output is a compact dict the chat pipeline can inject as a system
preamble section.  Everything is heuristic — no AST parsing, no execution.
The goal is to give the LLM enough signal to be a good code reviewer, not
to be a full static analyzer.

Public API:
  detect_language(filename: str, text: str) -> str        # "r" | "python" | …
  detect_r_packages(text: str) -> list[str]               # unique, sorted
  detect_python_packages(text: str) -> list[str]
  build_code_context(attachments: list[dict]) -> dict     # full profile
  format_code_context_md(ctx: dict) -> str                # LLM-friendly
  attach_code_context(preamble: str, ctx: dict) -> str    # splice helper
"""

from __future__ import annotations

import os
import re
from typing import Any

# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

# Extension → language.  Keep this small and explicit; we only need enough
# fidelity to pick the right package-extraction rules downstream.
_EXT_LANG = {
    ".r": "r", ".R": "r",
    ".rmd": "r", ".Rmd": "r",
    ".py": "python", ".PY": "python",
    ".ipynb": "python",  # default; cell-level detection is overkill
    ".jl": "julia",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    ".js": "javascript", ".ts": "typescript",
    ".sql": "sql",
    ".snakefile": "snakemake",
    ".smk": "snakemake",
    ".nf": "nextflow",
}

# Snippet heuristics — fall back to these when the extension is missing
# (e.g. paste in chat, no filename).
_SNIPPET_LANG = [
    ("r", [
        r"^\s*library\s*\(",
        r"^\s*require\s*\(",
        r"^\s*BiocManager::install\b",
        r"^\s*#'\s*",
        r"^\s*[A-Za-z_.][A-Za-z0-9_.]*\s*<-\s*function\b",
        r"\bdata\.frame\s*\(",
        r"\bmutate\s*\(",
        r"\bfilter\s*\(",
        r"\bggplot\s*\(",
        r"\btidyverse\b",
        r"\bDESeq2\b|\bedgeR\b|\blimma\b|\bphyloseq\b|\bseurat\b",
    ]),
    ("python", [
        r"^\s*import\s+\w+",
        r"^\s*from\s+\w+\s+import\b",
        r"^\s*def\s+\w+\s*\(",
        r"^\s*async\s+def\s+\w+",
        r"^\s*class\s+\w+[(:]",
        r"^\s*@\w+\s*$",
        r"\bpd\.DataFrame\s*\(",
        r"\bnp\.array\s*\(",
        r"\bscanpy\b|\bsc\.pp\.|\bsc\.tl\.",
        r"\bAnnData\s*\(",
    ]),
    ("julia", [
        r"^\s*using\s+\w+",
        r"^\s*function\s+\w+",
        r"\bend\b\s*$",
    ]),
    ("bash", [
        r"^#!.*\b(?:bash|sh|zsh|fish)\b",
        r"^\s*(?:sudo\s+)?(?:apt|yum|dnf|pacman|brew|samtools|bwa|hisat2|STAR)\b",
    ]),
    ("sql", [
        r"^\s*SELECT\b",
        r"^\s*FROM\s+\w+",
        r"^\s*WHERE\b",
    ]),
    ("snakemake", [
        r"^\s*rule\s+\w+\s*:",
        r"^\s*input\s*:",
        r"^\s*output\s*:",
    ]),
]


def detect_language(filename: str = "", text: str = "") -> str:
    """Return the most likely language id (r, python, julia, bash, …).

    Filename extension wins when present.  Otherwise we walk the snippet
    regexes in order and return the first language with at least 2 hits
    (single hits are too noisy on a 3-line paste).
    """
    if filename:
        ext = os.path.splitext(filename)[1]
        if ext in _EXT_LANG:
            return _EXT_LANG[ext]
        # Some workflow files use a non-standard extension (Snakefile w/o .smk).
        base = os.path.basename(filename).lower()
        if base in {"snakefile", "workflow"}:
            return "snakemake"
    text = text or ""
    if not text.strip():
        return ""
    hits: dict[str, int] = {}
    for lang, patterns in _SNIPPET_LANG:
        for pat in patterns:
            hits[lang] = hits.get(lang, 0) + len(re.findall(pat, text, re.M | re.I))
    # Pick the language with the highest hit count, but require >= 2 hits to
    # avoid false positives on single-line pastes.
    if not hits:
        return ""
    best = max(hits.items(), key=lambda kv: kv[1])
    return best[0] if best[1] >= 2 else ""


# ---------------------------------------------------------------------------
# Package detection
# ---------------------------------------------------------------------------

# R — library(X) / require(X) / requireNamespace("X") / BiocManager::install("X")
_R_LIB_RE = re.compile(r"^\s*(?:library|require|requireNamespace|requireNamespaceIfAvailable)\s*\(\s*[\"']?([A-Za-z0-9.]+)[\"']?\s*[,)]", re.M)
# BiocManager::install() — accept either a direct string or a c("a", "b") list.
_R_BIOC_RE = re.compile(
    r"BiocManager::install\s*\(\s*(?:c\s*\(\s*)?[\"']([A-Za-z0-9.]+)[\"']",
    re.M,
)
# Match every additional quoted name inside a c("a", "b", ...) list.
_R_BIOC_LIST_RE = re.compile(
    r"BiocManager::install\s*\(\s*c\s*\(([^)]*)\)",
    re.M,
)
_R_PACMAN_RE = re.compile(r"(?:^|\s)(?:pacman::)?p_load\s*\(\s*([^\)]+)\)", re.M)
_R_REMOTE_RE = re.compile(r"remotes::install_(?:github|gitlab|url|bioc|version)\s*\(\s*[\"']([^\"']+)", re.M)
# Quoted token inside any R-style list — used to pull the rest of a c(...)
# we already matched the head of.
_R_QUOTED_RE = re.compile(r"[\"']([A-Za-z0-9.]+)[\"']")

# Curated hints for the most common bioinformatics / multi-omics R packages.
# We list the *primary* intent so the LLM can frame its review accordingly.
_R_PACKAGE_HINTS: dict[str, str] = {
    "DESeq2": "RNA-seq 差异表达 (负二项 GLM)",
    "edgeR": "RNA-seq 差异表达 (经验贝叶斯)",
    "limma": "微阵列 / 差异表达 (voom)",
    "phyloseq": "微生物组 16S 群落分析",
    "microbiome": "微生物组 (phyloseq 上层封装)",
    "ALDEx2": "微生物组 差异丰度 (composition-aware)",
    "ancombc": "微生物组 差异丰度 (ANCOM-BC)",
    "Seurat": "单细胞 RNA-seq (Seurat v4/v5)",
    "SingleR": "单细胞 细胞类型自动注释",
    "scran": "单细胞 标准化 / 降维 / 聚类",
    "scater": "单细胞 QC / 可视化",
    "MAST": "单细胞 差异表达",
    "clusterProfiler": "GO / KEGG 富集分析",
    "org.Hs.eg.db": "人类基因注释 (org.db)",
    "org.Mm.eg.db": "小鼠基因注释 (org.db)",
    "TxDb.Hsapiens.UCSC.hg38.knownGene": "人类 hg38 转录本注释",
    "ChIPseeker": "ChIP-seq 峰注释",
    "DiffBind": "ChIP-seq 差异结合分析",
    "VariantAnnotation": "VCF 注释 / 处理",
    " GenomicRanges": "基因组区间操作",
    "GenomicFeatures": "基因组特征 (TxDb)",
    "ComplexHeatmap": "热图 / 复杂可视化",
    "pheatmap": "热图",
    "ggplot2": "出版级可视化",
    "dplyr": "数据处理 (tidyverse)",
    "tidyr": "数据整理 (tidyverse)",
    "readr": "文件读取 (tidyverse)",
    "tidyverse": "tidyverse 集合",
    "BiocManager": "Bioconductor 包管理",
    "SummarizedExperiment": "通用实验数据容器",
    "MultiAssayExperiment": "多组学整合容器",
    "mixOmics": "多组学 (DIABLO / PLS)",
    "MOFA2": "多组学因子分析 (MOFA+)",
    "MsExperiment": "质谱实验数据",
    "xcms": "代谢组学 (质谱)",
    "MetaboAnalystR": "代谢组学 (MetaboAnalyst)",
    "flowCore": "流式细胞分析",
    "CyTOF": "质谱流式",
}

# Python — import X / from X import Y / from X.Y import Z.  Skip stdlib.
_PY_IMPORT_RE = re.compile(r"^\s*import\s+([A-Za-z_][A-Za-z0-9_]*)(?:\s+as\s+(\w+))?", re.M)
_PY_FROM_RE = re.compile(r"^\s*from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import\b", re.M)

_STDLIB_HINT = {
    "os", "sys", "re", "io", "json", "math", "time", "datetime", "pathlib",
    "collections", "itertools", "functools", "typing", "argparse", "logging",
    "subprocess", "threading", "multiprocessing", "urllib", "http", "csv",
    "xml", "html", "unittest", "warnings", "copy", "pickle", "tempfile",
    "shutil", "glob", "fnmatch", "random", "string", "textwrap", "traceback",
    "inspect", "dataclasses", "enum", "abc", "contextlib",
}

_PY_PACKAGE_HINTS: dict[str, str] = {
    "numpy": "数值计算 (ndarray / linalg)",
    "pandas": "表格数据 (DataFrame)",
    "polars": "高性能 DataFrame",
    "scipy": "科学计算 (stats, signal, optimize)",
    "scikit-learn": "通用机器学习 (sklearn)",
    "sklearn": "通用机器学习 (sklearn)",
    "statsmodels": "统计建模 / GLM",
    "matplotlib": "基础可视化",
    "seaborn": "统计可视化 (基于 matplotlib)",
    "plotly": "交互可视化",
    "scanpy": "单细胞 RNA-seq (AnnData)",
    "anndata": "单细胞 标注数据容器",
    "scvi-tools": "单细胞 深度学习 (scVI / scANVI)",
    "pynndescent": "近似最近邻 (UMAP / 降维前置)",
    "umap-learn": "UMAP 降维",
    "leidenalg": "Leiden 社区检测",
    "igraph": "图算法 (community detection)",
    "pysal": "空间转录组",
    "squidpy": "空间转录组",
    "gget": "基因数据库 (Ensembl / NCBI)",
    "pyensembl": "Ensembl 基因注释",
    "biopython": "Bio 序列处理",
    "Bio": "BioPython 命名空间",
    "pysam": "BAM/SAM/VCF 读取",
    "pybedtools": "BEDTools Python 接口",
    "pyBigWig": "BigWig 读取",
    "deeptools": "ChIP-seq / ATAC-seq 可视化",
    "macs3": "ChIP-seq 峰调用 (MACS3)",
    "multiqc": "QC 报告汇总",
    "snakemake": "Snakemake 工作流",
    "nextflow": "Nextflow 工作流 (Python API)",
    "cwltool": "CWL 工作流",
    "kallisto": "RNA 定量 (kallisto / bustools)",
    "kb_python": "kallisto-bustools 单细胞",
    "pertpy": "单细胞 扰动分析",
    "celltypist": "单细胞 细胞类型自动注释",
    "sctransform": "单细胞 标准化 (vst)",
    "decoupler": "通路 / 调控子活性评分",
    "pydeseq2": "DESeq2 Python 移植",
    "diffxpy": "单细胞 差异表达",
    "scrublet": "双细胞检测 (单细胞)",
    "doubletdetection": "双细胞检测 (单细胞)",
    "metabolomics": "代谢组学 (Python)",
    "pyteomics": "蛋白质组学 (质谱)",
    "alphapept": "蛋白质组学 (DDA)",
    "alphafold": "蛋白结构预测",
    "esm": "蛋白语言模型 (Meta ESM)",
    "torch": "深度学习 (PyTorch)",
    "tensorflow": "深度学习 (TF)",
    "transformers": "HF Transformers (蛋白 / DNA LLM)",
    "datasets": "HF Datasets",
    "accelerate": "HF Accelerate",
    "wandb": "实验追踪 (W&B)",
    "mlflow": "实验追踪 (MLflow)",
    "jupyter": "Notebook",
    "ipykernel": "Jupyter kernel",
}


def _filter_packages(raw: list[str], hints: dict[str, str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for name in raw:
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


def detect_r_packages(text: str) -> list[str]:
    """Extract R packages referenced by library()/require()/BiocManager::install()."""
    if not text:
        return []
    pkgs: list[str] = []
    for m in _R_LIB_RE.finditer(text):
        pkgs.append(m.group(1))
    for m in _R_BIOC_RE.finditer(text):
        pkgs.append(m.group(1))
    # BiocManager::install(c("a", "b", "c")) — pull every quoted name out.
    for m in _R_BIOC_LIST_RE.finditer(text):
        for inner in _R_QUOTED_RE.findall(m.group(1)):
            pkgs.append(inner)
    for m in _R_PACMAN_RE.finditer(text):
        for chunk in m.group(1).split(","):
            name = chunk.strip().strip("\"'")
            if name:
                pkgs.append(name)
    for m in _R_REMOTE_RE.finditer(text):
        # remotes::install_github("user/repo") → take the user as a hint
        slug = m.group(1).split("/")[0]
        if slug:
            pkgs.append(slug)
    return _filter_packages(pkgs, _R_PACKAGE_HINTS)


def detect_python_packages(text: str) -> list[str]:
    """Extract top-level Python package names from import statements.

    Stdlib modules are kept (some bioinformatics tools use them as the
    public API) but we surface them lower-priority in the hint dict.  The
    main heuristic: if the top-level name appears in `_PY_PACKAGE_HINTS`,
    keep it; otherwise keep it but flag in a separate "other" bucket.
    """
    if not text:
        return []
    pkgs: list[str] = []
    for m in _PY_IMPORT_RE.finditer(text):
        name = m.group(1)
        if name:
            pkgs.append(name)
    for m in _PY_FROM_RE.finditer(text):
        top = m.group(1).split(".")[0]
        if top and top not in ("__future__",):
            pkgs.append(top)
    return _filter_packages(pkgs, _PY_PACKAGE_HINTS)


# ---------------------------------------------------------------------------
# Aggregator + formatter
# ---------------------------------------------------------------------------

# R packages that almost always imply a Bioconductor context — useful
# for the LLM to know whether to mention BiocManager / release versions.
_BIOC_PREFIXES = (
    "DESeq2", "edgeR", "limma", "phyloseq", "SingleR", "Seurat",
    "clusterProfiler", "ChIPseeker", "DiffBind", "VariantAnnotation",
    "GenomicRanges", "GenomicFeatures", "SummarizedExperiment",
    "MultiAssayExperiment", "TxDb.", "Org.", "org.", "msa", "Biostrings",
    "ShortRead", "rtracklayer", "AnnotationDbi", "ComplexHeatmap",
    "msqc", "scater", "scran", "MAST", "MOFA2", "mixOmics", "xcms",
    "MsExperiment", "MetaboAnalystR", "SpatialExperiment",
)


def _is_bioc(pkg: str) -> bool:
    return any(pkg.startswith(pre) for pre in _BIOC_PREFIXES)


def build_code_context(attachments: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Build a code context profile from a list of attachments.

    Each attachment is a dict with at least:
        {"name": str, "text": str, "language": str?}

    The output shape:
        {
          "files": [
            {"name", "language", "packages": [...], "hints": {...},
             "is_bioc": bool, "package_count": int, "char_count": int}
          ],
          "languages": {"r": int, "python": int, ...},
          "packages": {"r": [...], "python": [...]},
          "package_hints": {"DESeq2": "RNA-seq 差异表达 ...", ...},
          "bioc": bool,
          "summary_zh": str,
          "summary_en": str,
        }
    """
    attachments = attachments or []
    files: list[dict[str, Any]] = []
    lang_counts: dict[str, int] = {}
    r_pkgs: list[str] = []
    py_pkgs: list[str] = []
    hint_used: dict[str, str] = {}
    bioc_seen = False

    for att in attachments:
        if not isinstance(att, dict):
            continue
        name = str(att.get("name") or "")
        text = str(att.get("text") or "")
        lang = str(att.get("language") or detect_language(name, text))
        file_entry: dict[str, Any] = {
            "name": name,
            "language": lang,
            "char_count": len(text),
            "packages": [],
            "package_hints": {},
            "is_bioc": False,
        }
        if lang == "r":
            pkgs = detect_r_packages(text)
            file_entry["packages"] = pkgs
            r_pkgs.extend(pkgs)
            for p in pkgs:
                hint = _R_PACKAGE_HINTS.get(p)
                if hint:
                    file_entry["package_hints"][p] = hint
                    hint_used[p] = hint
                if _is_bioc(p):
                    file_entry["is_bioc"] = True
                    bioc_seen = True
        elif lang == "python":
            pkgs = detect_python_packages(text)
            file_entry["packages"] = pkgs
            py_pkgs.extend(pkgs)
            for p in pkgs:
                hint = _PY_PACKAGE_HINTS.get(p)
                if hint:
                    file_entry["package_hints"][p] = hint
                    hint_used[p] = hint
        if lang:
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
        files.append(file_entry)

    return {
        "files": files,
        "languages": lang_counts,
        "packages": {"r": sorted(set(r_pkgs)), "python": sorted(set(py_pkgs))},
        "package_hints": hint_used,
        "bioc": bioc_seen,
        "summary_zh": _summary_zh(files, lang_counts, r_pkgs, py_pkgs, hint_used, bioc_seen),
        "summary_en": _summary_en(files, lang_counts, r_pkgs, py_pkgs, hint_used, bioc_seen),
    }


def _summary_zh(
    files: list[dict[str, Any]],
    lang_counts: dict[str, int],
    r_pkgs: list[str],
    py_pkgs: list[str],
    hint_used: dict[str, str],
    bioc_seen: bool,
) -> str:
    if not files:
        return ""
    parts: list[str] = []
    if lang_counts:
        lang_str = "、".join(f"{lang}×{n}" for lang, n in sorted(lang_counts.items(), key=lambda kv: -kv[1]))
        parts.append(f"已识别语言：{lang_str}")
    if r_pkgs:
        uniq = sorted(set(r_pkgs))
        listed = "、".join(uniq[:10]) + ("…" if len(uniq) > 10 else "")
        parts.append(f"R 包：{listed}")
        if bioc_seen:
            parts.append("检测到 Bioconductor 包（提醒：版本与 BiocManager::install() 兼容性）")
    if py_pkgs:
        uniq = sorted(set(py_pkgs))
        listed = "、".join(uniq[:10]) + ("…" if len(uniq) > 10 else "")
        parts.append(f"Python 包：{listed}")
    if hint_used:
        # Surface up to 5 most relevant hints so the LLM anchors on them.
        sample = list(hint_used.items())[:5]
        hint_lines = "; ".join(f"{k}={v}" for k, v in sample)
        parts.append(f"主要意图：{hint_lines}")
    parts.append("请基于上述包的官方 API 给出可直接执行的建议；不要替学生重写整个分析，只指出需要修改的片段并解释生信概念")
    parts.append("")  # empty final segment so the join+trailing 。 reads cleanly
    return "。".join(p for p in parts if p) + "。"


def _summary_en(
    files: list[dict[str, Any]],
    lang_counts: dict[str, int],
    r_pkgs: list[str],
    py_pkgs: list[str],
    hint_used: dict[str, str],
    bioc_seen: bool,
) -> str:
    if not files:
        return ""
    parts: list[str] = []
    if lang_counts:
        lang_str = ", ".join(f"{lang}×{n}" for lang, n in sorted(lang_counts.items(), key=lambda kv: -kv[1]))
        parts.append(f"Detected languages: {lang_str}")
    if r_pkgs:
        uniq = sorted(set(r_pkgs))
        listed = ", ".join(uniq[:10]) + ("…" if len(uniq) > 10 else "")
        parts.append(f"R packages: {listed}")
        if bioc_seen:
            parts.append("Bioconductor packages detected (note BiocManager::install() version compatibility)")
    if py_pkgs:
        uniq = sorted(set(py_pkgs))
        listed = ", ".join(uniq[:10]) + ("…" if len(uniq) > 10 else "")
        parts.append(f"Python packages: {listed}")
    if hint_used:
        sample = list(hint_used.items())[:5]
        hint_lines = "; ".join(f"{k}={v}" for k, v in sample)
        parts.append(f"Primary intent: {hint_lines}")
    parts.append("Cite the official API of the packages above; do not rewrite the whole analysis — point at the lines that need changes and explain the biology.")
    return ". ".join(parts) + "."


def format_code_context_md(ctx: dict[str, Any], *, lang: str = "zh") -> str:
    """Format the code context for inclusion in the system preamble.

    Returns an empty string when there are no files / no detected language.
    Otherwise returns a short, LLM-friendly block.
    """
    if not ctx or not ctx.get("files"):
        return ""
    files = ctx.get("files") or []
    languages = ctx.get("languages") or {}
    if not languages:
        return ""
    summary = ctx.get("summary_zh") if lang.startswith("zh") else ctx.get("summary_en")
    if not summary:
        return ""
    file_lines: list[str] = []
    for f in files:
        if not isinstance(f, dict) or not f.get("language"):
            continue
        name = f.get("name") or "(unnamed)"
        lang_id = f.get("language")
        packages = f.get("packages") or []
        if packages:
            pkgs_str = "、".join(packages[:8]) + ("…" if len(packages) > 8 else "")
        else:
            pkgs_str = "（未识别到包引用）"
        hint_lines: list[str] = []
        for pkg, hint in list((f.get("package_hints") or {}).items())[:4]:
            hint_lines.append(f"  - {pkg}: {hint}")
        hint_block = "\n".join(hint_lines)
        file_lines.append(
            f"- **{name}** ({lang_id}, {f.get('char_count') or 0} chars)\n"
            f"  - 包 / packages: {pkgs_str}\n"
            f"{hint_block}"
        )
    header = "## 学生代码上下文 / Student code context" if lang == "zh+en" or lang.startswith("zh") else "## Student code context"
    return (
        f"{header}\n"
        f"{summary}\n\n"
        "Files:\n"
        + "\n".join(file_lines)
        + "\n"
    )


def attach_code_context(preamble: str, ctx: dict[str, Any], *, lang: str = "zh") -> str:
    """Splice the code-context block into a system preamble.

    Inserts the block immediately after any existing '## 学生代码上下文'
    marker; if the marker is missing, prepends the block.  The preamble
    is otherwise left untouched.
    """
    block = format_code_context_md(ctx, lang=lang)
    if not block:
        return preamble
    marker = "## 学生代码上下文"
    marker_en = "## Student code context"
    if marker in preamble:
        return preamble.replace(marker, block, 1)
    if marker_en in preamble:
        return preamble.replace(marker_en, block, 1)
    return block + "\n" + preamble


# ---------------------------------------------------------------------------
# Convenience: scan files on disk
# ---------------------------------------------------------------------------

def scan_file(path: str) -> dict[str, Any]:
    """Read a single file (utf-8 with replacement) and return one
    attachment dict ready to feed into `build_code_context`."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return {"name": os.path.basename(path), "text": "", "language": ""}
    return {
        "name": os.path.basename(path),
        "text": text,
        "language": detect_language(path, text),
    }


__all__ = [
    "detect_language",
    "detect_r_packages",
    "detect_python_packages",
    "build_code_context",
    "format_code_context_md",
    "attach_code_context",
    "scan_file",
]

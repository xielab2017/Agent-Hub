"""Tests for the code-context detection module.

Covers:
  * Language detection by extension + body heuristics (R / Python / Julia / bash / SQL / Snakemake).
  * R package extraction (library/require/BiocManager::install/remotes::install_github).
  * Python package extraction (import / from-import) with stdlib kept but
    surfaced in the context without a hint when not in the curated dict.
  * `build_code_context` aggregator: language counts, package lists, hint
    surfacing, Bioconductor flag, per-file metadata.
  * `format_code_context_md` — LLM-facing markdown, with a Chinese summary
    and per-file hint bullets.
  * `attach_code_context` — splice helper used by the chat pipeline.
  * End-to-end "student uploads .R + .py, asks for help" — the resulting
    context block is wired into the grounding preamble.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Language detection ────────────────────────────────────────────────


def test_detect_language_by_extension():
    from ali.code_context import detect_language
    assert detect_language("deseq2.R", "") == "r"
    assert detect_language("script.py", "") == "python"
    assert detect_language("analysis.Rmd", "") == "r"
    assert detect_language("pipeline.smk", "") == "snakemake"
    assert detect_language("Snakefile", "") == "snakemake"
    assert detect_language("run.sh", "") == "bash"
    assert detect_language("query.sql", "") == "sql"
    assert detect_language("notebook.ipynb", "") == "python"


def test_detect_language_from_body_when_no_extension():
    from ali.code_context import detect_language
    r_body = (
        "library(DESeq2)\n"
        "library(ggplot2)\n"
        "dds <- DESeqDataSetFromMatrix(countData = counts, colData = coldata)\n"
        "res <- results(dds)\n"
        "ggplot(res, aes(x = log2FoldChange, y = -log10(pvalue))) + geom_point()\n"
    )
    py_body = (
        "import scanpy as sc\n"
        "import pandas as pd\n"
        "from pydeseq2.dds import DeseqDataSet\n"
        "import numpy as np\n"
        "adata = sc.read_10x_h5('filtered_feature_bc_matrix.h5')\n"
    )
    assert detect_language("", r_body) == "r"
    assert detect_language("", py_body) == "python"
    assert detect_language("pasted.txt", r_body) == "r"


def test_detect_language_too_short_to_classify():
    from ali.code_context import detect_language
    # A single import is not enough — too noisy on 1-line pastes.
    assert detect_language("", "import os\n") == ""
    assert detect_language("", "x = 1\n") == ""


def test_detect_language_empty_input():
    from ali.code_context import detect_language
    assert detect_language("", "") == ""
    assert detect_language("unknown.xyz", "") == ""


# ── R package detection ──────────────────────────────────────────────


def test_detect_r_packages_library_and_require():
    from ali.code_context import detect_r_packages
    text = """
library(DESeq2)
library(ggplot2)
require(phyloseq)
requireNamespace("clusterProfiler")
"""
    pkgs = detect_r_packages(text)
    assert "DESeq2" in pkgs
    assert "ggplot2" in pkgs
    assert "phyloseq" in pkgs
    assert "clusterProfiler" in pkgs
    # Dedupe: assert no duplicate entries.
    assert len(pkgs) == len(set(pkgs))


def test_detect_r_packages_biocmanager():
    from ali.code_context import detect_r_packages
    text = 'BiocManager::install("org.Hs.eg.db")\nBiocManager::install(c("TxDb.Hsapiens.UCSC.hg38.knownGene", "ChIPseeker"))'
    pkgs = detect_r_packages(text)
    assert "org.Hs.eg.db" in pkgs
    assert "TxDb.Hsapiens.UCSC.hg38.knownGene" in pkgs
    assert "ChIPseeker" in pkgs


def test_detect_r_packages_pacman_p_load():
    from ali.code_context import detect_r_packages
    text = 'pacman::p_load(dplyr, tidyr, ggplot2, DESeq2)'
    pkgs = detect_r_packages(text)
    for p in ("dplyr", "tidyr", "ggplot2", "DESeq2"):
        assert p in pkgs


def test_detect_r_packages_remotes_github():
    from ali.code_context import detect_r_packages
    text = 'remotes::install_github("satijalab/seurat")\nremotes::install_github("mhahsler/rEMM")'
    pkgs = detect_r_packages(text)
    # We surface the user slug as a hint; downstream can resolve to a real
    # package name when the student actually loads it.
    assert "satijalab" in pkgs
    assert "mhahsler" in pkgs


def test_detect_r_packages_empty_or_pure_python():
    from ali.code_context import detect_r_packages
    assert detect_r_packages("") == []
    assert detect_r_packages("print('hello')") == []


# ── Python package detection ─────────────────────────────────────────


def test_detect_python_packages_import():
    from ali.code_context import detect_python_packages
    text = """
import scanpy as sc
import pandas as pd
import numpy as np
import os
import sys
"""
    pkgs = detect_python_packages(text)
    assert "scanpy" in pkgs
    assert "pandas" in pkgs
    assert "numpy" in pkgs
    assert "os" in pkgs
    assert "sys" in pkgs


def test_detect_python_packages_from_import():
    from ali.code_context import detect_python_packages
    text = """
from pydeseq2.dds import DeseqDataSet
from sklearn.ensemble import RandomForestClassifier
from Bio import SeqIO
"""
    pkgs = detect_python_packages(text)
    assert "pydeseq2" in pkgs
    assert "sklearn" in pkgs
    assert "Bio" in pkgs


def test_detect_python_packages_skips_dunder_future():
    from ali.code_context import detect_python_packages
    pkgs = detect_python_packages("from __future__ import annotations\nimport numpy as np")
    assert "__future__" not in pkgs
    assert "numpy" in pkgs


def test_detect_python_packages_dedupes():
    from ali.code_context import detect_python_packages
    text = "import numpy as np\nimport numpy\nimport numpy as np"
    pkgs = detect_python_packages(text)
    assert pkgs.count("numpy") == 1


# ── Aggregator + hints ────────────────────────────────────────────────


def test_build_code_context_single_r_file():
    from ali.code_context import build_code_context
    r_text = """
library(DESeq2)
library(ggplot2)
dds <- DESeqDataSetFromMatrix(countData = counts, colData = coldata, design = ~condition)
dds <- DESeq(dds)
res <- results(dds)
ggplot(as.data.frame(res), aes(log2FoldChange, -log10(pvalue))) + geom_point()
"""
    ctx = build_code_context([{"name": "deseq2.R", "text": r_text}])
    assert ctx["languages"] == {"r": 1}
    assert "DESeq2" in ctx["packages"]["r"]
    assert "ggplot2" in ctx["packages"]["r"]
    assert ctx["bioc"] is True
    # Hints are surfaced for known packages
    assert "DESeq2" in ctx["package_hints"]
    assert "RNA-seq" in ctx["package_hints"]["DESeq2"]
    # Per-file metadata
    file0 = ctx["files"][0]
    assert file0["language"] == "r"
    assert "DESeq2" in file0["packages"]


def test_build_code_context_mixed_r_and_python():
    from ali.code_context import build_code_context
    r_text = "library(Seurat)\nlibrary(DESeq2)\nres <- results(dds)"
    py_text = "import scanpy as sc\nimport pandas as pd\nsc.pp.normalize_total(adata)"
    ctx = build_code_context([
        {"name": "seurat.R", "text": r_text},
        {"name": "scanpy.py", "text": py_text},
    ])
    assert ctx["languages"] == {"r": 1, "python": 1}
    assert "Seurat" in ctx["packages"]["r"]
    assert "DESeq2" in ctx["packages"]["r"]
    assert "scanpy" in ctx["packages"]["python"]
    assert "pandas" in ctx["packages"]["python"]
    assert ctx["bioc"] is True
    # Both languages have hints
    assert "Seurat" in ctx["package_hints"]
    assert "scanpy" in ctx["package_hints"]


def test_build_code_context_empty_input():
    from ali.code_context import build_code_context
    ctx = build_code_context([])
    assert ctx["files"] == []
    assert ctx["languages"] == {}
    assert ctx["bioc"] is False


def test_build_code_context_ignores_unknown_files():
    from ali.code_context import build_code_context
    ctx = build_code_context([
        {"name": "notes.txt", "text": "Meeting at 3pm. Bring a USB."},
        {"name": "data.csv", "text": "gene,fc\nA,1.2\nB,0.8"},
    ])
    assert ctx["languages"] == {}
    assert ctx["package_hints"] == {}


def test_build_code_context_summary_mentions_bioc():
    from ali.code_context import build_code_context
    r_text = "library(DESeq2)\nlibrary(limma)\nres <- results(dds)"
    ctx = build_code_context([{"name": "rna_seq.R", "text": r_text}])
    assert "Bioconductor" in ctx["summary_zh"]
    assert "DESeq2" in ctx["summary_zh"]
    assert "limma" in ctx["summary_zh"]
    assert "Bioconductor" in ctx["summary_en"]


def test_build_code_context_summary_caps_long_lists():
    from ali.code_context import build_code_context
    r_text = "\n".join(f"library(pkg{i})" for i in range(20))
    ctx = build_code_context([{"name": "many.R", "text": r_text}])
    # The summary should truncate to ~10 items + "…".
    assert "…" in ctx["summary_zh"] or len(ctx["packages"]["r"]) <= 10


# ── Markdown formatter ────────────────────────────────────────────────


def test_format_code_context_md_returns_empty_when_no_languages():
    from ali.code_context import build_code_context, format_code_context_md
    ctx = build_code_context([])
    assert format_code_context_md(ctx, lang="zh") == ""


def test_format_code_context_md_includes_per_file_hints():
    from ali.code_context import build_code_context, format_code_context_md
    r_text = "library(DESeq2)\nlibrary(clusterProfiler)\nres <- results(dds)"
    ctx = build_code_context([{"name": "de.R", "text": r_text}])
    md = format_code_context_md(ctx, lang="zh")
    assert "学生代码上下文" in md
    assert "DESeq2" in md
    assert "clusterProfiler" in md
    assert "GO / KEGG" in md or "富集" in md
    assert "**de.R**" in md


def test_format_code_context_md_english_summary():
    from ali.code_context import build_code_context, format_code_context_md
    r_text = "library(DESeq2)\ndds <- DESeq(dds)"
    ctx = build_code_context([{"name": "de.R", "text": r_text}])
    md = format_code_context_md(ctx, lang="en")
    assert "Student code context" in md
    assert "DESeq2" in md
    assert "Bioconductor" in md


# ── attach_code_context ──────────────────────────────────────────────


def test_attach_code_context_splices_at_marker():
    from ali.code_context import attach_code_context, build_code_context
    ctx = build_code_context([{"name": "de.R", "text": "library(DESeq2)"}])
    preamble = "## 学生代码上下文\nOriginal preamble body"
    out = attach_code_context(preamble, ctx, lang="zh")
    assert "DESeq2" in out
    # The original body is preserved (the splice replaces the marker line only).
    assert "Original preamble body" in out
    # The block lives at the marker position, not appended after everything.
    marker_idx = out.index("## 学生代码上下文")
    assert "DESeq2" in out[marker_idx:]


def test_attach_code_context_prepends_when_marker_absent():
    from ali.code_context import attach_code_context, build_code_context
    ctx = build_code_context([{"name": "de.R", "text": "library(DESeq2)"}])
    preamble = "You are a helpful assistant."
    out = attach_code_context(preamble, ctx, lang="zh")
    assert "DESeq2" in out
    # The code context block must come before the original preamble.
    assert out.index("学生代码上下文") < out.index("You are a helpful assistant")


def test_attach_code_context_no_op_when_no_languages():
    from ali.code_context import attach_code_context, build_code_context
    ctx = build_code_context([{"name": "notes.txt", "text": "Meeting at 3pm"}])
    preamble = "Original preamble"
    out = attach_code_context(preamble, ctx, lang="zh")
    assert out == "Original preamble"


# ── End-to-end via grounding.build_grounded_preamble ─────────────────


def test_grounding_injects_code_context_for_r_script(monkeypatch):
    """When the user attaches an R script, the LLM-facing preamble
    should contain the code-context block (language, packages, hints)."""
    from ali import grounding

    # Stub out workspace + upload readers so we control what excerpts
    # are produced.  The grounding pipeline merges both — text excerpts
    # come from the workspace, upload excerpts from session uploads.
    # We put the R script in BOTH readers so the code-context branch
    # sees it no matter which path the test triggers.
    r_excerpt = {
        "relative": "deseq2.R",
        "path": "/tmp/deseq2.R",
        "content": "library(DESeq2)\nlibrary(ggplot2)\ndds <- DESeq(dds)",
        "bytes_read": 60,
        "truncated": False,
        "kind": "text",
    }

    def fake_read_text_excerpts(*args, **kwargs):
        return [dict(r_excerpt)]

    def fake_read_upload_excerpts(*args, **kwargs):
        return [dict(r_excerpt)]

    monkeypatch.setattr(grounding, "read_text_excerpts", fake_read_text_excerpts)
    monkeypatch.setattr(grounding, "read_upload_excerpts", fake_read_upload_excerpts)

    preamble, meta = grounding.build_grounded_preamble(
        {"model": "stub", "provider": "stub"},
        {"workspace": ""},
        # `[Attachments]` is the marker the grounding pipeline uses to
        # decide whether to read workspace / upload excerpts even when no
        # workspace folder is set.  We include it so the fake readers are
        # actually invoked and the code-context branch has data to chew on.
        message="[Attachments] 请帮我看看这段 R 代码",
        session_id="test_session",
    )
    # The preamble now carries the code context block.
    assert "学生代码上下文" in preamble
    assert "DESeq2" in preamble
    assert "ggplot2" in preamble
    # And it tells the LLM to base suggestions on the official API.
    assert "API" in preamble


def test_grounding_skips_code_context_for_csv_only(monkeypatch):
    """A pure CSV upload must NOT trigger code-context injection — we
    don't want a confusing "Detected languages: …" block when the
    student just dropped a data file."""
    from ali import grounding

    def fake_read_text_excerpts(*args, **kwargs):
        return []

    def fake_read_upload_excerpts(*args, **kwargs):
        return [
            {
                "relative": "counts.csv",
                "path": "/tmp/counts.csv",
                "content": "gene,control,treat\ngeneA,100,180\ngeneB,50,40",
                "bytes_read": 60,
                "truncated": False,
                "kind": "text",
            }
        ]

    monkeypatch.setattr(grounding, "read_text_excerpts", fake_read_text_excerpts)
    monkeypatch.setattr(grounding, "read_upload_excerpts", fake_read_upload_excerpts)

    preamble, meta = grounding.build_grounded_preamble(
        {"model": "stub", "provider": "stub"},
        {"workspace": ""},
        message="counts.csv 帮我看下",
        session_id="test_session",
    )
    assert "学生代码上下文" not in preamble

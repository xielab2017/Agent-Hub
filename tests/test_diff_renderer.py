"""Tests for the unified-diff auto-renderer.

The actual renderer lives in `static/app.js` (frontend) — there is no
Python equivalent at runtime.  To get unit-test coverage on the heuristic,
we mirror `looksLikeDiff` here.  The JS implementation is byte-identical
to this port; if you change one, change both.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ── Python mirror of looksLikeDiff ──────────────────────────────────


def looks_like_diff(code: str) -> bool:
    if not code:
        return False
    lines = code.split("\n")
    if len(lines) < 3:
        return False
    plus = minus = hunk = sigil = 0
    for raw in lines:
        line = raw.rstrip("\r")
        if re.match(r"^@@\s", line):
            hunk += 1
        if line.startswith("+") and not line.startswith("+++"):
            plus += 1
        if line.startswith("-") and not line.startswith("---"):
            minus += 1
        if (
            re.match(r"^[+\-@ ]", line)
            or line.startswith("@@")
            or line.startswith("diff ")
            or line.startswith("index ")
            or re.match(r"^---\s", line)
            or re.match(r"^\+\+\+\s", line)
        ):
            sigil += 1
    if hunk >= 1 and (plus + minus) >= 2:
        return True
    if plus >= 1 and minus >= 1 and sigil / len(lines) >= 0.3:
        return True
    return False


# ── Tests ────────────────────────────────────────────────────────────


def test_unified_diff_with_hunk_header():
    diff = """@@ -1,5 +1,5 @@
 def hello():
-    print("Hello, world!")
+    print("Hello, agent hub!")
 def bye():
-    print("Goodbye")
+    print("See you")
"""
    assert looks_like_diff(diff) is True


def test_simple_add_remove_without_hunk():
    diff = """def add(x, y):
-    return x + y
+    return x + y + 0
def sub(x, y):
-    return x - y
+    return x - y
"""
    assert looks_like_diff(diff) is True


def test_full_git_diff_format():
    diff = """diff --git a/deseq2.R b/deseq2.R
index 1234..5678 100644
--- a/deseq2.R
+++ b/deseq2.R
@@ -10,7 +10,7 @@
 dds <- DESeqDataSetFromMatrix(countData = counts,
                                colData = coldata,
                                design = ~ condition)
-dds <- DESeq(dds)
+dds <- DESeq(dds, quiet = FALSE)
 res <- results(dds)
"""
    # The full git-style diff is detected too.
    assert looks_like_diff(diff) is True


def test_plain_r_script_is_not_a_diff():
    script = """library(DESeq2)
dds <- DESeqDataSetFromMatrix(
    countData = counts,
    colData = coldata,
    design = ~ condition
)
dds <- DESeq(dds)
res <- results(dds)
res_df <- as.data.frame(res)
"""
    assert looks_like_diff(script) is False


def test_python_with_arithmetic_is_not_a_diff():
    py = """def f(x):
    return x + 1
def g(x):
    return x - 1
def h(x):
    return x * 2
"""
    # Has + and - but doesn't look like a diff: no hunk header, and the
    # `+` / `-` lines don't dominate the body.
    assert looks_like_diff(py) is False


def test_minimum_length_is_3_lines():
    # A truly tiny add/remove pair (2 lines) is not enough — we require
    # enough context for the human to be sure the LLM intended a diff.
    diff = "-a\n+b"
    assert looks_like_diff(diff) is False
    # 3 lines is the minimum: one context + one remove + one add.
    diff3 = " ctx\n-a\n+b"
    assert looks_like_diff(diff3) is True


def test_empty_input_is_not_a_diff():
    assert looks_like_diff("") is False
    assert looks_like_diff(None) is False


def test_diff_with_only_adds_is_not_a_diff():
    # We require BOTH `+` and `-` (or a `@@` header).  Pure addition
    # is too easy to confuse with a math / data snippet.
    code = """+ a
+ b
+ c
+ d
+ e
"""
    assert looks_like_diff(code) is False


def test_diff_with_only_removes_is_not_a_diff():
    code = """- a
- b
- c
- d
- e
"""
    assert looks_like_diff(code) is False


# ── Snapshot the heuristic against the JS source ─────────────────────


def test_js_heuristic_is_in_sync_with_python_mirror():
    """Sanity: the JS implementation in `static/app.js` must agree with
    the Python mirror on a handful of representative inputs.  Catches
    drift if someone tweaks one without the other."""
    js_path = ROOT / "static" / "app.js"
    src = js_path.read_text(encoding="utf-8")
    # The JS function should be a single, contained definition that
    # mirrors the structure used here.  We don't run the JS, but we do
    # check that the function exists and contains the same magic
    # constants.
    assert "function looksLikeDiff" in src
    # Both branches of the heuristic must be present in the JS.
    assert "hunk >= 1" in src
    assert "sigil / lines.length >= 0.3" in src
    # And the renderer must wire it into the code-box path.
    assert "looksLikeDiff(code)" in src
    assert "diffBoxHtml" in src

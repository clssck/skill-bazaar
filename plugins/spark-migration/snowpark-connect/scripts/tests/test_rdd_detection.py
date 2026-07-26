"""Unit tests for the RDD *detection* improvements in ``analyze_pyspark`` —
the ``RDD_EXCLUSIVE_METHODS`` ungating in ``has_rdd_usage`` and the file-scope
RDD import / type-annotation markers emitted by the block extractor.

These import ``analyze_pyspark`` directly, which pulls in the full SCOS
dependency stack (rag / snowflake). When that stack is absent (local dev
without the connectors installed) the whole module is skipped — CI runs it for
real, mirroring the existing ``test_decidability_gate`` / ``test_self_consistency``
suites.

Run from the ``snowpark-connect/`` directory:

    pytest scripts/tests/test_rdd_detection.py
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip(
    "snowflake.snowpark",
    reason="RDD detection tests need the full SCOS dependency stack (CI only)",
)

from analyze_pyspark import (  # noqa: E402
    RDD_EXCLUSIVE_METHODS,
    RDD_METHODS,
    RDD_NO_EQUIVALENT,
    RDD_PATTERNS,
    build_rdd_conversion_guidance,
    extract_code_blocks_from_source,
    has_rdd_usage,
    load_api_compatibility,
)

_DATA = Path(__file__).resolve().parents[1] / "data" / "api_compatibility.csv"


def _methods():
    _, methods = load_api_compatibility(_DATA)
    return methods


def _file_flagged(src: str) -> bool:
    """True if any extracted block of ``src`` is flagged as RDD usage."""
    return any(has_rdd_usage(b.code)[0] for b in extract_code_blocks_from_source(src, _methods()))


# --------------------------------------------------------------------------- #
# RDD_EXCLUSIVE_METHODS ungating: flagged WITHOUT a co-located .rdd/sc. token.
# This is the dataflow gap — an RDD bound to a variable / parameter and operated
# on in a separate statement.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code",
    [
        "out = rdd.reduceByKey(add)",
        "x = data.map(f).groupByKey()",
        "kv = rdd.mapValues(lambda v: v + 1)",
        "idx = rdd.zipWithIndex()",
        "u = rdd.zipWithUniqueId()",
        "s = rdd.sortByKey()",
        "p = rdd.mapPartitions(fn)",
        "t = rdd.takeOrdered(5)",
        "rdd.saveAsTextFile('out')",
        "agg = rdd.aggregateByKey(0)(seq, comb)",
    ],
)
def test_exclusive_methods_flagged_without_token(code):
    is_rdd, why = has_rdd_usage(code)
    assert is_rdd, f"expected RDD flag for {code!r}"
    assert "RDD-exclusive" in why


# --------------------------------------------------------------------------- #
# Ambiguous names (DataFrame homonyms) stay gated — no false positives.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "code",
    [
        'df.select("a").filter("a > 1")',
        "n = df.count()",
        "rows = df.collect()",
        "d = df.distinct()",
        "u = df1.union(df2)",
        "j = df1.join(df2, 'k')",
        "cfg = settings.values()",  # dict.values(), not RDD
    ],
)
def test_ambiguous_methods_not_flagged_without_token(code):
    assert not has_rdd_usage(code)[0], f"false positive on {code!r}"


@pytest.mark.parametrize(
    "code",
    [
        "x = df.rdd.map(f)",
        "y = sc.parallelize(d).collect()",
    ],
)
def test_ambiguous_methods_flagged_with_rdd_token(code):
    assert has_rdd_usage(code)[0]


def test_exclusive_is_subset_of_rdd_methods():
    assert RDD_EXCLUSIVE_METHODS <= set(RDD_METHODS)


# --------------------------------------------------------------------------- #
# File-scope markers: RDD imports + RDD type annotations become flagged blocks
# even though they form no assignment/expression block.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src",
    [
        "from pyspark import RDD\n",
        "from pyspark.rdd import RDD, PipelinedRDD\n",
        "import pyspark.rdd\n",
        "my_rdd: RDD = build()\n",
        "def process(x: RDD) -> RDD:\n    return x\n",
        "def to_pairs(items) -> RDD:\n    return items\n",
    ],
)
def test_file_scope_imports_and_annotations_detected(src):
    assert _file_flagged(src), f"no RDD-flagged block for {src!r}"


# --------------------------------------------------------------------------- #
# Regressions: plain DataFrame code and a bare ``import pyspark`` must NOT be
# flagged as RDD (no spurious markers, gate intact).
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "src",
    [
        'import pyspark\ndf = spark.range(10)\nout = df.select("id").filter("id > 1")\n',
        'res = df.groupBy("k").count()\n',
        'from pyspark.sql import functions as F\nx = df.withColumn("y", F.col("z"))\n',
    ],
)
def test_plain_dataframe_not_flagged(src):
    assert not _file_flagged(src), f"unexpected RDD flag for {src!r}"


# --------------------------------------------------------------------------- #
# Actionable conversion guidance: the RDD issue must NAME the detected op(s) and
# direct the fixer to rewrite convertible ops (never TODO), reserving TODOs for
# the genuinely no-equivalent set — never the old generic "Convert to DataFrame
# operations. RDD operations are not supported" string.
# --------------------------------------------------------------------------- #
def test_convertible_rdd_op_directs_rewrite_not_todo():
    g = build_rdd_conversion_guidance("out = df.rdd.reduceByKey(add)")
    assert g["rdd_class"] == "convertible"
    assert g["suggested_fixer_action"], "convertible op must supply a rewrite directive"
    # Names the op, points at the reference, and directs a rewrite (not a punt).
    assert "reduceByKey" in g["fix"], g["fix"]
    assert "rdd-conversion.md" in g["fix"], g["fix"]
    assert "APPLY the rewrite" in g["fix"], g["fix"]
    assert "TODO" not in g["suggested_fixer_action"], "the action must be a rewrite, not a TODO"
    assert "are not supported" not in g["fix"].lower()


def test_no_equivalent_rdd_op_gets_todo_and_no_action():
    g = build_rdd_conversion_guidance("x = rdd.glom()")
    assert g["rdd_class"] == "no_equivalent"
    assert g["suggested_fixer_action"] is None, "no-equivalent op must not supply a rewrite"
    assert "TODO" in g["fix"]
    assert "glom" in g["fix"]


def test_mixed_rdd_block_rewrites_convertible_and_todos_rest():
    g = build_rdd_conversion_guidance("a = rdd.reduceByKey(add)\nb = rdd.glom()")
    assert g["rdd_class"] == "mixed"
    assert g["suggested_fixer_action"], "mixed block must still direct the convertible rewrite"
    # Both ops named; convertible rewritten, no-equivalent TODO'd.
    assert "reduceByKey" in g["fix"] and "glom" in g["fix"], g["fix"]
    assert "TODO" in g["fix"]


def test_bare_rdd_attribute_gets_removable_hop_guidance():
    g = build_rdd_conversion_guidance("pairs = df.rdd\n")
    assert g["rdd_class"] == "convertible"
    assert ".rdd" in g["fix"]
    assert "TODO" not in g["suggested_fixer_action"], "a bare .rdd hop is removable, not a TODO"
    assert "are not supported" not in g["fix"].lower()


def test_no_equivalent_set_is_subset_of_detected_names():
    """Belt-and-suspenders to the ast-based sync test: exercised against the
    imported module objects. Every no-equivalent token must be a real RDD name."""
    known = {m.lower() for m in RDD_METHODS} | {
        p.strip().lstrip(".").rstrip("(").lower() for p in RDD_PATTERNS
    }
    unknown = sorted(t for t in RDD_NO_EQUIVALENT if t not in known)
    assert not unknown, f"RDD_NO_EQUIVALENT has unknown tokens: {unknown}"

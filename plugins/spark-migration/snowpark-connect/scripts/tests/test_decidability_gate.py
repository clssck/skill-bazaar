"""Tests for the analyzer's decidability gate (analyze_pyspark.py).

The gate emits structurally-certain trigger findings without an LLM
round-trip, while keeping behavioral / fuzzy / recipe-touched blocks on the
LLM path. These tests exercise the partition logic directly with synthetic
block items (no Snowflake session, no real Cortex call).
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from analyze_pyspark import (  # noqa: E402
    _block_is_fully_decidable,
    _build_decidable_result,
    _partition_decidable_blocks,
)


@dataclass
class _Block:
    line_start: int = 10
    line_end: int = 12
    code: str = "out = df.rdd.map(lambda r: r)"
    cell_id: int | None = None
    language: str = "python"


def _candidate(*, decidable: bool, score: float = 0.95, fuzzy: bool = False) -> dict:
    return {
        "match_kind": "rag_similar" if fuzzy else "trigger_exact",
        "score": score,
        "root_cause": "RDD API is unsupported in SCOS.",
        "decidable": decidable,
    }


def _item(*, candidates: list[dict], scos_issues: list | None = None) -> dict:
    return {
        "block": _Block(),
        "matching_patterns": candidates,
        "scos_issues": scos_issues or [],
    }


# --- _block_is_fully_decidable ---------------------------------------------


def test_all_decidable_exact_triggers_is_decidable() -> None:
    item = _item(candidates=[_candidate(decidable=True), _candidate(decidable=True)])
    assert _block_is_fully_decidable(item) is True


def test_low_severity_decidable_still_decidable() -> None:
    # Severity (score) is irrelevant to decidability — a low-severity
    # unsupported API is still a guaranteed true positive.
    item = _item(candidates=[_candidate(decidable=True, score=0.45)])
    assert _block_is_fully_decidable(item) is True


def test_any_nondecidable_candidate_blocks_bypass() -> None:
    item = _item(candidates=[_candidate(decidable=True), _candidate(decidable=False)])
    assert _block_is_fully_decidable(item) is False


def test_fuzzy_candidate_never_decidable() -> None:
    item = _item(candidates=[_candidate(decidable=True, fuzzy=True)])
    assert _block_is_fully_decidable(item) is False


def test_soft_rule_issue_blocks_bypass() -> None:
    item = _item(candidates=[_candidate(decidable=True)], scos_issues=[{"risk": 0.8}])
    assert _block_is_fully_decidable(item) is False


def test_no_candidates_not_decidable() -> None:
    assert _block_is_fully_decidable(_item(candidates=[])) is False


# --- _build_decidable_result -----------------------------------------------


def test_build_decidable_result_shape() -> None:
    res = _build_decidable_result(Path("/tmp/f.py"), _item(candidates=[_candidate(decidable=True)]), 0.3)
    assert res is not None
    assert res["final_risk"] == 0.95
    assert res["confidence"] == "HIGH"
    assert res["kind"] == "llm_only"
    assert res["source"] == "trigger_decidable"
    assert res["fix"] is None
    assert res["lines"] == "10-12"
    assert res["language"] == "python"


def test_build_decidable_result_below_threshold_dropped() -> None:
    res = _build_decidable_result(
        Path("/tmp/f.py"), _item(candidates=[_candidate(decidable=True, score=0.2)]), 0.3
    )
    assert res is None


# --- _partition_decidable_blocks -------------------------------------------


def test_partition_emits_decidable_keeps_rest() -> None:
    decidable = _item(candidates=[_candidate(decidable=True)])
    behavioral = _item(candidates=[_candidate(decidable=False)])
    emitted, remaining = _partition_decidable_blocks(
        [decidable, behavioral], file_recipe_edits=[], file_path=Path("/tmp/f.py"), risk_threshold=0.3
    )
    assert len(emitted) == 1 and emitted[0]["source"] == "trigger_decidable"
    assert remaining == [behavioral]


def test_partition_keeps_recipe_touched_block_on_llm_path() -> None:
    # A decidable block that a Phase 0.5 recipe touched must stay on the LLM
    # path so the model can still propose a suggested_fixer_action.
    decidable = _item(candidates=[_candidate(decidable=True)])  # block at lines 10-12
    recipe_edits = [{"recipe_id": "some_annotate", "src_line": 11}]
    emitted, remaining = _partition_decidable_blocks(
        [decidable], file_recipe_edits=recipe_edits, file_path=Path("/tmp/f.py"), risk_threshold=0.3
    )
    assert emitted == []
    assert remaining == [decidable]

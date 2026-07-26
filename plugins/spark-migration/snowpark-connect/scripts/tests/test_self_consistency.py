"""Tests for the self-consistency merge logic in ``analyze_pyspark.py``.

The merge layer is pure (no LLM, no Snowflake), so we can exercise it directly
with synthetic ``runs`` dicts that mirror the shape of
``predict_compatibility_batch`` output.
"""

from __future__ import annotations

import pytest

from analyze_pyspark import (
    _disagreeing_block_ids,
    _merge_self_consistency_runs,
)


def _r(block_id: str, risk: float, *, root_cause: str = "rc", confidence: str = "HIGH"):
    """Build a single-block result dict shaped like the LLM response."""
    return {
        "block_id": block_id,
        "final_risk": risk,
        "root_cause": root_cause,
        "explanation": f"explain-{block_id}@{risk}",
        "fix": f"fix-{block_id}",
        "confidence": confidence,
    }


def _run(*entries):
    """Build a ``run`` dict (block_id -> result) from N entries."""
    return {e["block_id"]: e for e in entries}


# --- _disagreeing_block_ids -------------------------------------------------


def test_disagreement_when_some_runs_emit_and_others_dont():
    runs = [
        _run(_r("1", 0.9), _r("2", 0.1)),
        _run(_r("1", 0.2), _r("2", 0.05)),  # block 1 flipped, block 2 agrees no-emit
    ]
    assert _disagreeing_block_ids(runs, threshold=0.3) == {"1"}


def test_no_disagreement_when_all_runs_agree():
    runs = [
        _run(_r("1", 0.9), _r("2", 0.05)),
        _run(_r("1", 0.85), _r("2", 0.10)),
    ]
    assert _disagreeing_block_ids(runs, threshold=0.3) == set()


def test_missing_block_in_one_run_counts_as_disagreement():
    """A block present in run A but missing in run B should be flagged so the
    tiebreaker re-asks for it."""
    runs = [
        _run(_r("1", 0.9)),
        _run(),  # block 1 missing entirely
    ]
    assert _disagreeing_block_ids(runs, threshold=0.3) == {"1"}


def test_single_run_yields_no_disagreements():
    runs = [_run(_r("1", 0.9))]
    assert _disagreeing_block_ids(runs, threshold=0.3) == set()


# --- _merge_self_consistency_runs ------------------------------------------


def test_unanimous_emit_keeps_full_confidence_and_records_vote_count():
    runs = [
        _run(_r("1", 0.9, confidence="HIGH")),
        _run(_r("1", 0.85, confidence="HIGH")),
        _run(_r("1", 0.95, confidence="HIGH")),
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert "1" in out
    assert out["1"]["confidence"] == "HIGH"  # unanimous, no downgrade
    assert out["1"]["vote_count"] == "3/3 emit"
    # median of [0.85, 0.9, 0.95] -> 0.9
    assert out["1"]["final_risk"] == pytest.approx(0.9)


def test_majority_emit_downgrades_confidence_one_tier():
    runs = [
        _run(_r("1", 0.9, confidence="HIGH")),
        _run(_r("1", 0.8, confidence="HIGH")),
        _run(_r("1", 0.05, confidence="HIGH")),  # disagrees
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert "1" in out
    assert out["1"]["vote_count"] == "2/3 emit"
    assert out["1"]["confidence"] == "MEDIUM"  # downgraded HIGH -> MEDIUM
    # median of the two emit-votes [0.8, 0.9] -> 0.9 (upper of the two)
    assert out["1"]["final_risk"] == pytest.approx(0.9)


def test_minority_emit_drops_block_entirely():
    runs = [
        _run(_r("1", 0.9)),  # only 1 of 3 says emit
        _run(_r("1", 0.05)),
        _run(_r("1", 0.10)),
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert "1" not in out  # majority said don't emit


def test_tie_drops_block_to_err_on_side_of_quiet():
    """1-of-2 emit is a tie (votes_emit * 2 == k) -> drop, per the docstring."""
    runs = [
        _run(_r("1", 0.9)),
        _run(_r("1", 0.05)),
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert "1" not in out


def test_two_of_three_emit_with_tied_high_risks():
    """Two emit-votes at 0.9 with one no-vote at 0.0 — emit at risk=0.9."""
    runs = [
        _run(_r("1", 0.9, confidence="MEDIUM")),
        _run(_r("1", 0.9, confidence="MEDIUM")),
        _run(_r("1", 0.0, confidence="MEDIUM")),
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert "1" in out
    assert out["1"]["vote_count"] == "2/3 emit"
    assert out["1"]["confidence"] == "LOW"  # MEDIUM -> LOW because not unanimous


def test_handles_multiple_blocks_independently():
    runs = [
        _run(_r("a", 0.9), _r("b", 0.1), _r("c", 0.8)),
        _run(_r("a", 0.85), _r("b", 0.05), _r("c", 0.0)),  # c flips
        _run(_r("a", 0.95), _r("b", 0.05), _r("c", 0.7)),  # c agrees with run 1
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert set(out.keys()) == {"a", "c"}  # b never emitted
    assert out["a"]["vote_count"] == "3/3 emit"
    assert out["c"]["vote_count"] == "2/3 emit"


def test_single_run_returned_unchanged():
    runs = [_run(_r("1", 0.9), _r("2", 0.1))]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert out == runs[0]  # passthrough, no vote_count added


def test_root_cause_sourced_from_median_run():
    """When picking ``root_cause``/``fix``, choose the run whose risk is closest
    to the median so the narrative matches the reported risk number."""
    runs = [
        _run(_r("1", 0.5, root_cause="MEDIAN_RC")),
        _run(_r("1", 0.95, root_cause="HIGH_RC")),
        _run(_r("1", 0.31, root_cause="LOW_RC")),
    ]
    out = _merge_self_consistency_runs(runs, threshold=0.3)
    assert out["1"]["final_risk"] == pytest.approx(0.5)
    assert out["1"]["root_cause"] == "MEDIAN_RC"


def test_empty_runs_returns_empty_dict():
    assert _merge_self_consistency_runs([], threshold=0.3) == {}


# --- predict_compatibility_batch_self_consistent (adaptive band mode) -------
#
# These tests exercise the K=1-first / band-only-revote logic directly.
# We monkeypatch ``predict_compatibility_batch_with_retry`` so no real
# LLM is involved — the test asserts that the right blocks reach the
# 2nd / 3rd pass and the merge produces the expected outcome.


@pytest.fixture
def patched_batch(monkeypatch):
    """Replace ``predict_compatibility_batch_with_retry`` with a stub that
    returns the next pre-canned response per call. Records call args."""
    import analyze_pyspark as ap

    state = {"calls": []}
    queue: list[dict[str, dict]] = []

    def fake_batch(session, batch_items, **_):
        state["calls"].append({
            "block_ids": [it["block_id"] for it in batch_items],
        })
        if not queue:
            raise AssertionError(
                f"unexpected extra batch call (no queued response). "
                f"calls so far: {state['calls']}"
            )
        return queue.pop(0)

    monkeypatch.setattr(ap, "predict_compatibility_batch_with_retry", fake_batch)
    return ap, state, queue


def test_adaptive_skips_2nd_pass_when_all_clear_cut(patched_batch):
    ap, state, queue = patched_batch
    # First pass: every block well above threshold (0.85, curated KB shape).
    # No band block, so no second call expected.
    queue.append(_run(_r("a", 0.85), _r("b", 0.90), _r("c", 0.95)))
    items = [{"block_id": "a"}, {"block_id": "b"}, {"block_id": "c"}]
    out = ap.predict_compatibility_batch_self_consistent(
        session=None, batch_items=items, min_k=1, max_k=3, threshold=0.3
    )
    # Exactly one batch call.
    assert len(state["calls"]) == 1
    # All three blocks present and emit at first-pass risk.
    assert set(out) == {"a", "b", "c"}
    assert out["a"]["final_risk"] == 0.85


def test_adaptive_revotes_only_band_blocks(patched_batch):
    ap, state, queue = patched_batch
    # First pass: 'a' clear-cut (0.85), 'b' in band (0.30), 'c' clear-cut low (0.05).
    queue.append(_run(_r("a", 0.85), _r("b", 0.30), _r("c", 0.05)))
    # Second pass should be called with ONLY 'b' (the band block).
    queue.append(_run(_r("b", 0.40)))
    items = [{"block_id": "a"}, {"block_id": "b"}, {"block_id": "c"}]
    out = ap.predict_compatibility_batch_self_consistent(
        session=None, batch_items=items, min_k=1, max_k=2, threshold=0.3
    )
    assert len(state["calls"]) == 2
    assert state["calls"][0]["block_ids"] == ["a", "b", "c"]
    assert state["calls"][1]["block_ids"] == ["b"]  # band-only second pass
    # 'a' clear-cut emit (kept), 'b' lands via 2-vote majority emit,
    # 'c' clear-cut no-emit (dropped by merge — both passes scored < threshold).
    assert set(out) == {"a", "b"}
    assert "c" not in out


def test_adaptive_tiebreaker_only_on_disagreeing_band_blocks(patched_batch):
    ap, state, queue = patched_batch
    # First pass: 'a' clear-cut, 'b' in band emit, 'c' in band no-emit.
    queue.append(_run(_r("a", 0.85), _r("b", 0.40), _r("c", 0.25)))
    # Second pass on ['b','c']: b drops below threshold (now disagreeing),
    # c stays below (still no-emit).
    queue.append(_run(_r("b", 0.10), _r("c", 0.20)))
    # Tiebreaker should target ONLY 'b' (the disagreeing band block).
    queue.append(_run(_r("b", 0.50)))
    items = [{"block_id": "a"}, {"block_id": "b"}, {"block_id": "c"}]
    out = ap.predict_compatibility_batch_self_consistent(
        session=None, batch_items=items, min_k=1, max_k=3, threshold=0.3
    )
    assert len(state["calls"]) == 3
    assert state["calls"][2]["block_ids"] == ["b"]
    # 'a' stays via first-pass; 'c' drops (votes 0.25 then 0.20, both below);
    # 'b' lands via majority of the 3 votes (0.40 emit, 0.10 no-emit, 0.50 emit).
    assert "a" in out
    assert "c" not in out  # 0/2 emit votes → drop
    assert "b" in out


def test_adaptive_max_k_one_returns_first_pass_directly(patched_batch):
    ap, state, queue = patched_batch
    queue.append(_run(_r("a", 0.85), _r("b", 0.30)))  # b is in band
    items = [{"block_id": "a"}, {"block_id": "b"}]
    out = ap.predict_compatibility_batch_self_consistent(
        session=None, batch_items=items, min_k=1, max_k=1, threshold=0.3
    )
    # Hard cap K=1 → no second pass even with a band block present.
    assert len(state["calls"]) == 1
    assert "a" in out and "b" in out


def test_legacy_fixed_k_path_preserved(patched_batch):
    """When min_k>=2, the old code path runs K full-batch passes (no band
    optimization), so callers explicitly opting into legacy semantics get
    the pre-2026-06 behaviour back."""
    ap, state, queue = patched_batch
    queue.append(_run(_r("a", 0.85), _r("b", 0.20)))
    queue.append(_run(_r("a", 0.85), _r("b", 0.40)))
    items = [{"block_id": "a"}, {"block_id": "b"}]
    out = ap.predict_compatibility_batch_self_consistent(
        session=None, batch_items=items, min_k=2, max_k=2, threshold=0.3
    )
    # Two full-batch calls (legacy), both with all block_ids.
    assert len(state["calls"]) == 2
    assert state["calls"][0]["block_ids"] == ["a", "b"]
    assert state["calls"][1]["block_ids"] == ["a", "b"]
    assert "a" in out


def test_adaptive_band_bounds_from_env(monkeypatch, patched_batch):
    """Env-configurable band — narrowing the band excludes blocks that
    would otherwise be revoted."""
    monkeypatch.setenv("SCOS_SC_BAND_LO", "0.40")
    monkeypatch.setenv("SCOS_SC_BAND_HI", "0.50")
    ap, state, queue = patched_batch
    # Block 'b' at 0.30 used to be in band [0.20, 0.50]; now [0.40, 0.50]
    # excludes it, so no 2nd pass should fire.
    queue.append(_run(_r("a", 0.85), _r("b", 0.30)))
    items = [{"block_id": "a"}, {"block_id": "b"}]
    out = ap.predict_compatibility_batch_self_consistent(
        session=None, batch_items=items, min_k=1, max_k=3, threshold=0.3
    )
    assert len(state["calls"]) == 1
    # 'b' at 0.30 is below threshold 0.30? Actually 0.30 == threshold; merge
    # uses `>= threshold` for emit, so 0.30 emits. Just sanity-check 'a'.
    assert "a" in out

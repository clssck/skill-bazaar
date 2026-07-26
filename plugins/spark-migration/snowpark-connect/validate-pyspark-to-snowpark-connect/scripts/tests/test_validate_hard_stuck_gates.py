"""Regression tests for validate.py hard_stuck gates and summary recovery."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

import validate  # noqa: E402


def _trial(status="pending", **kw):
    return {"status": status, "phase_a_iters": [], "phase_b_iters": [], **kw}


def test_advance_phase_sets_phase_a_complete_milestone():
    st = {"phase": "init", "trials": {
        "a": {"status": "passed", "phase_a_iters": [{"iter": 1}]},
    }}
    validate._advance_phase(st)
    assert st["phase"] == "phase_a_done"
    assert st["milestones"]["phase_a_complete"] is True
    assert not st["milestones"].get("phase_b_complete")


def test_advance_phase_sets_both_milestones_on_phase_b():
    st = {"phase": "phase_a_done", "milestones": {"phase_a_complete": True}, "trials": {
        "a": {"status": "passed", "phase_a_iters": [{"iter": 1}], "phase_b_iters": [{"iter": 1}]},
    }}
    validate._advance_phase(st)
    assert st["phase"] == "phase_b_done"
    assert st["milestones"]["phase_a_complete"] is True
    assert st["milestones"]["phase_b_complete"] is True


def test_advance_phase_noop_when_not_all_terminal():
    st = {"phase": "init", "trials": {"a": {"status": "pending", "phase_a_iters": []}}}
    validate._advance_phase(st)
    assert st["phase"] == "init"
    assert not st.get("milestones")


def test_advance_phase_emits_milestone_event(tmp_path):
    (tmp_path / "Validation").mkdir(parents=True)
    st = {"phase": "init", "trials": {"a": {"status": "passed", "phase_a_iters": [{"iter": 1}]}}}
    validate._advance_phase(st, tmp_path)
    events_path = tmp_path / "Validation" / "events.jsonl"
    assert events_path.is_file()
    kinds = [json.loads(l) for l in events_path.read_text().splitlines() if l.strip()]
    assert any(e.get("kind") == "milestone_completed" and e.get("milestone") == "phase_a_complete"
               for e in kinds)


def _state(**trials):
    return {"schema_version": validate.SCHEMA_VERSION, "phase": "init", "trials": trials,
            "fixer_dispatches": []}


def _save(tmp_path: Path, state: dict) -> None:
    val = tmp_path / "Validation"
    val.mkdir(parents=True, exist_ok=True)
    (val / "state.json").write_text(json.dumps(state) + "\n")


def _record_status(tmp_path: Path, **kwargs):
    args = SimpleNamespace(
        conv_root=str(tmp_path),
        trial_id=kwargs.get("trial_id", "a"),
        status=kwargs.get("status", "hard_stuck"),
        final_iter=kwargs.get("final_iter"),
        reason=kwargs.get("reason", "stuck"),
        analysis_repair_exhausted=kwargs.get("analysis_repair_exhausted", False),
        harness_repair_exhausted=kwargs.get("harness_repair_exhausted", False),
        patch_repair_exhausted=kwargs.get("patch_repair_exhausted", False),
        phase=None,
    )
    try:
        validate.cmd_record_trial_status(args)
    except SystemExit as exc:
        return exc.code
    return 0


# --- summary auto-recovery -------------------------------------------------


def test_recover_pending_promotes_passes_only():
    st = {"trials": {
        "ok": _trial(
            "pending",
            phase_a_iters=[{"iter": 1, "passing": 1, "failing": 0}],
            phase_b_iters=[{"iter": 1, "passing": 2, "failing": 0}],
        ),
        "bad": _trial("pending", phase_b_iters=[{"iter": 1, "passing": 0, "failing": 1}]),
    }}
    n = validate._recover_pending_trials(st)
    assert n == 1
    assert st["trials"]["ok"]["status"] == "passed"
    assert st["trials"]["bad"]["status"] == "pending"


def test_recover_pending_no_baseline_when_no_phase_a():
    st = {"trials": {
        "ep": _trial("pending", phase_b_iters=[{"iter": 1, "passing": 1, "failing": 0}]),
    }}
    validate._recover_pending_trials(st)
    assert st["trials"]["ep"]["status"] == "passed_no_baseline"


def test_recover_pending_no_baseline_when_phase_a_failed():
    """Phase A iters exist but none passed — still passed_no_baseline, not passed."""
    st = {"trials": {
        "ep": _trial(
            "pending",
            phase_a_iters=[{"iter": 1, "passing": 0, "failing": 1}],
            phase_b_iters=[{"iter": 1, "passing": 1, "failing": 0}],
        ),
    }}
    validate._recover_pending_trials(st)
    assert st["trials"]["ep"]["status"] == "passed_no_baseline"


def test_recover_pending_promotes_phase_a_skipped():
    st = {"trials": {
        "ep": _trial(
            "phase_a_skipped",
            phase_b_iters=[{"iter": 2, "passing": 1, "failing": 0}],
        ),
    }}
    n = validate._recover_pending_trials(st)
    assert n == 1
    assert st["trials"]["ep"]["status"] == "passed_no_baseline"


# --- record-iter fix_category tagging --------------------------------------


def test_record_iter_tags_existing_iter(tmp_path):
    _save(tmp_path, _state(a=_trial(phase_b_iters=[{"iter": 2, "passing": 0, "failing": 1}])))
    validate._record_iter_impl(
        tmp_path, "a", "B", 2, 0, 1, fix_category="analysis_repair",
    )
    st = validate._load_state(tmp_path)
    assert st["trials"]["a"]["phase_b_iters"][0]["fix_category"] == "analysis_repair"


def test_record_iter_tag_idempotent(tmp_path, capsys):
    _save(tmp_path, _state(a=_trial(
        phase_b_iters=[{"iter": 1, "passing": 0, "failing": 1, "fix_category": "patch_failure"}],
    )))
    validate._record_iter_impl(tmp_path, "a", "B", 1, 0, 1, fix_category="patch_failure")
    out = capsys.readouterr().out
    assert "no-op" in out
    st = validate._load_state(tmp_path)
    assert len(st["trials"]["a"]["phase_b_iters"]) == 1


# --- hard_stuck gate -------------------------------------------------------


def test_hard_stuck_without_any_exhaustion_rejected(tmp_path):
    _save(tmp_path, _state(a=_trial()))
    assert _record_status(tmp_path) == 2


def test_hard_stuck_analysis_repair_requires_recorded_attempt(tmp_path):
    _save(tmp_path, _state(a=_trial()))
    assert _record_status(tmp_path, analysis_repair_exhausted=True, reason="gap") == 2


def test_hard_stuck_analysis_repair_single_attempt_allowed(tmp_path):
    _save(tmp_path, _state(a=_trial(
        phase_b_iters=[{"iter": 1, "fix_category": "analysis_repair"}],
    )))
    assert _record_status(tmp_path, analysis_repair_exhausted=True, reason="gap") == 0
    st = validate._load_state(tmp_path)
    assert st["trials"]["a"]["status"] == "hard_stuck"


def test_hard_stuck_harness_repair_single_attempt_allowed(tmp_path):
    _save(tmp_path, _state(a=_trial(
        phase_b_iters=[{"iter": 1, "fix_category": "harness_failure"}],
    )))
    assert _record_status(tmp_path, harness_repair_exhausted=True, reason="kit bug") == 0


def test_hard_stuck_patch_repair_single_attempt_allowed(tmp_path):
    _save(tmp_path, _state(a=_trial(
        phase_b_iters=[{"iter": 1, "fix_category": "patch_failure"}],
    )))
    assert _record_status(tmp_path, patch_repair_exhausted=True, reason="no patch") == 0


def test_hard_stuck_with_fixer_dispatch_allowed(tmp_path):
    st = _state(a=_trial())
    st["fixer_dispatches"] = [{"trials_affected": ["a"]}]
    _save(tmp_path, st)
    assert _record_status(tmp_path, reason="no progress") == 0


# --- last-resort --reason requirement + surfacing -------------------------


def test_phase_a_skipped_requires_reason(tmp_path):
    _save(tmp_path, _state(a=_trial("pending")))
    assert _record_status(tmp_path, trial_id="a", status="phase_a_skipped", reason=None) == 2
    # blank/whitespace is also rejected
    assert _record_status(tmp_path, trial_id="a", status="phase_a_skipped", reason="  ") == 2


def test_hard_stuck_requires_reason_even_with_dispatch(tmp_path):
    st = _state(a=_trial())
    st["fixer_dispatches"] = [{"trials_affected": ["a"]}]
    _save(tmp_path, st)
    # gate is satisfied (dispatch), but a blank reason is still rejected
    assert _record_status(tmp_path, trial_id="a", status="hard_stuck", reason=None) == 2


def test_phase_a_skipped_stores_dedicated_reason(tmp_path):
    _save(tmp_path, _state(a=_trial("pending")))
    assert _record_status(
        tmp_path, trial_id="a", status="phase_a_skipped",
        reason="QUALIFY clause unsupported in local PySpark",
    ) == 0
    st = validate._load_state(tmp_path)
    # stored in the dedicated field, NOT hard_stuck_reason
    assert st["trials"]["a"]["phase_a_skip_reason"] == "QUALIFY clause unsupported in local PySpark"
    assert "hard_stuck_reason" not in st["trials"]["a"]


def test_phase_a_skip_reason_preserved_on_promotion(tmp_path):
    # a phase_a_skipped trial with a skip reason, promoted to pnb, keeps the reason
    st = {"trials": {
        "ep": _trial(
            "phase_a_skipped",
            phase_a_skip_reason="MERGE INTO unsupported in local PySpark",
            phase_b_iters=[{"iter": 1, "passing": 1, "failing": 0}],
        ),
    }}
    validate._recover_pending_trials(st)
    assert st["trials"]["ep"]["status"] == "passed_no_baseline"
    assert st["trials"]["ep"]["phase_a_skip_reason"] == "MERGE INTO unsupported in local PySpark"


# --- baseline_produced label (requires a PASSING Phase A iter) ------------


def test_phase_a_baseline_produced_requires_passing_iter():
    passed = {"phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}]}
    failed = {"phase_a_iters": [{"iter": 1, "passing": 0, "failing": 1}]}
    empty = {"phase_a_iters": []}
    assert validate._phase_a_baseline_produced(passed) is True
    # a Phase A that only ever FAILED is NOT a produced baseline (was mislabeled before)
    assert validate._phase_a_baseline_produced(failed) is False
    assert validate._phase_a_baseline_produced(empty) is False


# --- passed_no_baseline is derived, never set directly --------------------


def test_record_status_rejects_direct_passed_no_baseline(tmp_path):
    # The model must mark phase_a_skipped; Phase B auto-promotes to pnb. Marking
    # pnb directly is rejected so a no-baseline verdict always carries a reason.
    _save(tmp_path, _state(a=_trial(
        phase_a_iters=[{"iter": 1, "passing": 1, "failing": 0}],
    )))
    assert _record_status(tmp_path, status="passed_no_baseline", reason="x") == 2


def test_infer_pass_status_skip_reason_beats_empty_baseline():
    # Phase A recorded a passing (but empty/unusable) capture AND the trial was
    # explicitly skipped -> must promote to pnb, not passed.
    t = {
        "status": "phase_a_skipped",
        "phase_a_skip_reason": "connector read returned 0 rows locally",
        "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}],
        "phase_b_iters": [{"iter": 1, "passing": 1, "failing": 0}],
    }
    assert validate._infer_pass_status(t) == "passed_no_baseline"


def test_skip_reason_surfaced_in_verdict_after_promotion():
    # After phase_a_skipped -> pnb promotion, the report verdict.reason must carry
    # the model-provided skip reason (this is what was silently dropped before).
    trial = {
        "status": "phase_a_skipped",
        "phase_a_skip_reason": "JDBC src1 returned 0 rows in local PySpark",
        "phase_b_iters": [{"iter": 1, "passing": 1, "failing": 0}],
    }
    assert validate._recover_pending_trials({"trials": {"ep": trial}}) == 1
    assert trial["status"] == "passed_no_baseline"
    # exercise the real report verdict-reason builder (used by cmd_build_index)
    assert validate._verdict_reason(trial) == "JDBC src1 returned 0 rows in local PySpark"


def test_verdict_reason_variants():
    # hard_stuck and passed each surface their own reason; pending is blank
    assert validate._verdict_reason(
        {"status": "hard_stuck", "hard_stuck_reason": "no workaround"}
    ) == "no workaround"
    assert validate._verdict_reason({"status": "passed"}) == "matched baseline"
    assert validate._verdict_reason({"status": "pending"}) == ""


def test_trial_lacks_baseline_matches_infer_pass_status():
    # A promoted passed_no_baseline trial that recorded a passing Phase A iter must
    # still report as having NO baseline (Phase A verdict + has_baseline), consistent
    # with _infer_pass_status — not mislabeled baseline_produced.
    promoted = {
        "status": "passed_no_baseline",
        "phase_a_skip_reason": "connector read returned 0 rows locally",
        "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}],
    }
    assert validate._phase_a_baseline_produced(promoted) is True
    assert validate._trial_lacks_baseline(promoted) is True
    assert validate._trial_lacks_baseline({"status": "phase_a_skipped"}) is True
    # a genuine passed trial with a real baseline is NOT lacking one
    real = {"status": "passed", "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}]}
    assert validate._trial_lacks_baseline(real) is False

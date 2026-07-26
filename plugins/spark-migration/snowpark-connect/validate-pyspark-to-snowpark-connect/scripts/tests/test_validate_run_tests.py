"""Tests for validate.py run-tests subcommand.

Run: uv run --project <skill>/.. python -m pytest scripts/tests/ -q
"""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import validate  # noqa: E402

SCHEMA_VERSION = validate.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_state(trials: dict) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "phase": "init",
        "trials": trials,
    }


def _write_state(conv_root: Path, state: dict) -> None:
    val = conv_root / "Validation"
    val.mkdir(parents=True, exist_ok=True)
    (val / "state.json").write_text(json.dumps(state), encoding="utf-8")


def _make_venv(conv_root: Path, phase: str) -> Path:
    venv_name = ".venv-source" if phase == "a" else ".venv-scos"
    venv_python = conv_root / "Validation" / "shared" / venv_name / "bin" / "python"
    venv_python.parent.mkdir(parents=True, exist_ok=True)
    venv_python.write_text("#!/bin/sh\nexec python3 \"$@\"\n")
    return venv_python


def _fake_report(tests_dir: Path, trial_outcomes: dict) -> dict:
    """Build a minimal pytest-json-report dict for the given {trial_id: outcome} map."""
    tests = []
    for tid, outcome in trial_outcomes.items():
        tests.append({"nodeid": f"{tests_dir}/test_{tid}.py::test_main", "outcome": outcome})
    return {"tests": tests}


def _run_cmd(conv_root, phase, iter_n, verify_all=False, trial_id=None):
    return validate.cmd_run_tests(SimpleNamespace(
        conv_root=str(conv_root),
        phase=phase,
        iter=iter_n,
        verify_all=verify_all,
        trial_id=trial_id,
    ))


# ---------------------------------------------------------------------------
# Test 1: deselect set excludes terminal trials in Phase B
# ---------------------------------------------------------------------------

def test_deselect_terminal_trials_phase_b(tmp_path):
    """Phase B: passed + hard_stuck trials are deselected; pending trial runs."""
    state = _make_state({
        "trial_a": {"status": "passed"},
        "trial_b": {"status": "hard_stuck"},
        "trial_c": {"status": "pending"},
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)

    report = _fake_report(tmp_path / "Validation" / "tests", {"trial_c": "passed"})
    report_path = results_dir / "pytest_3.json"

    captured_cmd = {}

    def fake_run(cmd, env=None, **kwargs):
        captured_cmd["cmd"] = cmd
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 3)
    assert exc.value.code == 0

    cmd = captured_cmd["cmd"]
    k_idx = cmd.index("-k")
    k_expr = cmd[k_idx + 1]
    # Both terminal trials must be excluded
    assert "test_trial_a" in k_expr
    assert "test_trial_b" in k_expr
    # Pending trial must NOT be excluded
    assert "test_trial_c" not in k_expr


# ---------------------------------------------------------------------------
# Test 2: --verify-all skips deselect
# ---------------------------------------------------------------------------

def test_verify_all_skips_deselect(tmp_path):
    """--verify-all: no -k flag in pytest command, all trials run."""
    state = _make_state({
        "trial_passed": {"status": "passed"},
        "trial_pending": {"status": "pending"},
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "a")

    results_dir = tmp_path / "Validation" / "results" / "phase_a"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_1.json"

    report = _fake_report(
        tmp_path / "Validation" / "tests",
        {"trial_passed": "passed", "trial_pending": "passed"},
    )

    captured_cmd = {}

    def fake_run(cmd, env=None, **kwargs):
        captured_cmd["cmd"] = cmd
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "a", 1, verify_all=True)
    assert exc.value.code == 0

    assert "-k" not in captured_cmd["cmd"]


# ---------------------------------------------------------------------------
# Test 3: record-iter emitted for pending trials only
# ---------------------------------------------------------------------------

def test_record_iter_emitted_for_ran_trials(tmp_path):
    """record-iter is called for trials that ran (not deselected)."""
    state = _make_state({
        "ep_ok": {"status": "passed"},
        "ep_run": {"status": "pending"},
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_2.json"

    report = _fake_report(
        tmp_path / "Validation" / "tests",
        {"ep_run": "passed"},  # ep_ok was deselected, not in report
    )

    def fake_run(cmd, env=None, **kwargs):
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    recorded = []

    def fake_record_iter_impl(conv_root, trial_id, phase, iter_n, passing, failing,
                              fix_category=None, _extra_entry=None):
        recorded.append({"trial_id": trial_id, "passing": passing, "failing": failing})

    with patch("subprocess.run", side_effect=fake_run):
        with patch.object(validate, "_record_iter_impl", side_effect=fake_record_iter_impl):
            with pytest.raises(SystemExit) as exc:
                _run_cmd(tmp_path, "b", 2)
    assert exc.value.code == 0

    assert len(recorded) == 1
    assert recorded[0]["trial_id"] == "ep_run"
    assert recorded[0]["passing"] == 1
    assert recorded[0]["failing"] == 0


# ---------------------------------------------------------------------------
# Test 4: phase_a_skipped deselected in Phase A but NOT in Phase B
# ---------------------------------------------------------------------------

def test_phase_a_skipped_deselect_semantics(tmp_path):
    """phase_a_skipped is terminal for Phase A but not for Phase B."""
    state = _make_state({
        "skipped_ep": {"status": "phase_a_skipped"},
        "pending_ep": {"status": "pending"},
    })
    _write_state(tmp_path, state)

    captured = {}

    def fake_run(cmd, env=None, **kwargs):
        captured["cmd"] = cmd
        # Write minimal report so no record-iter is attempted
        report_path.write_text(json.dumps({"tests": []}), encoding="utf-8")
        return MagicMock(returncode=0)

    # --- Phase A: phase_a_skipped should be deselected ---
    _make_venv(tmp_path, "a")
    results_dir_a = tmp_path / "Validation" / "results" / "phase_a"
    results_dir_a.mkdir(parents=True, exist_ok=True)
    report_path = results_dir_a / "pytest_1.json"

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit):
            _run_cmd(tmp_path, "a", 1)

    k_idx = captured["cmd"].index("-k")
    k_expr = captured["cmd"][k_idx + 1]
    assert "test_skipped_ep" in k_expr, "phase_a_skipped should be deselected in Phase A"

    # --- Phase B: phase_a_skipped should NOT be deselected ---
    captured.clear()
    _make_venv(tmp_path, "b")
    results_dir_b = tmp_path / "Validation" / "results" / "phase_b"
    results_dir_b.mkdir(parents=True, exist_ok=True)
    report_path = results_dir_b / "pytest_1.json"

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit):
            _run_cmd(tmp_path, "b", 1)

    assert "-k" not in captured["cmd"], (
        "phase_a_skipped must NOT be deselected in Phase B"
    )


# ---------------------------------------------------------------------------
# Test 5: --trial-id runs only the selected trial, even if terminal
# ---------------------------------------------------------------------------

def test_trial_id_runs_only_selected_trial_even_if_terminal(tmp_path):
    state = _make_state({
        "target_ep": {"status": "passed"},
        "other_ep": {"status": "pending"},
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_4.json"
    report = _fake_report(tmp_path / "Validation" / "tests", {"target_ep": "passed"})

    captured_cmd = {}

    def fake_run(cmd, env=None, **kwargs):
        captured_cmd["cmd"] = cmd
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 4, trial_id="target_ep")
    assert exc.value.code == 0

    cmd = captured_cmd["cmd"]
    k_idx = cmd.index("-k")
    k_expr = cmd[k_idx + 1]
    assert "test_other_ep" in k_expr
    assert "test_target_ep" not in k_expr


# ---------------------------------------------------------------------------
# Test 6: verify-all failure reopens a previously passed trial
# ---------------------------------------------------------------------------

def test_verify_all_failure_reopens_passed_trial(tmp_path):
    state = _make_state({
        "ep": {
            "status": "passed",
            "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}],
            "phase_b_iters": [{"iter": 1, "passing": 1, "failing": 0}],
            "final_iter": 1,
        },
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_5.json"
    report = _fake_report(tmp_path / "Validation" / "tests", {"ep": "failed"})

    def fake_run(cmd, env=None, **kwargs):
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 5, verify_all=True)
    assert exc.value.code == 1

    st = json.loads((tmp_path / "Validation" / "state.json").read_text())
    assert st["trials"]["ep"]["status"] == "pending"
    assert "final_iter" not in st["trials"]["ep"]


def test_trial_id_pass_refreshes_hard_stuck_trial(tmp_path):
    state = _make_state({
        "ep": {
            "status": "hard_stuck",
            "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}],
            "phase_b_iters": [{"iter": 2, "passing": 0, "failing": 1}],
            "hard_stuck_reason": "old reason",
            "final_iter": 2,
        },
        "other_ep": {"status": "pending"},
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_6.json"
    report = _fake_report(tmp_path / "Validation" / "tests", {"ep": "passed"})

    def fake_run(cmd, env=None, **kwargs):
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 6, trial_id="ep")
    assert exc.value.code == 0

    st = json.loads((tmp_path / "Validation" / "state.json").read_text())
    assert st["trials"]["ep"]["status"] == "passed"
    assert st["trials"]["ep"]["final_iter"] == 6
    assert "hard_stuck_reason" not in st["trials"]["ep"]


# ---------------------------------------------------------------------------
# Test 8: missing venv → clear error, non-zero exit
# ---------------------------------------------------------------------------

def test_missing_venv_exits_nonzero(tmp_path):
    """If the venv doesn't exist, die with exit code 2."""
    state = _make_state({"some_trial": {"status": "pending"}})
    _write_state(tmp_path, state)
    # deliberately do NOT create the venv

    with pytest.raises(SystemExit) as exc:
        _run_cmd(tmp_path, "b", 1)
    assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Test 9: Phase B pass auto-promotes trial status
# ---------------------------------------------------------------------------

def test_run_tests_auto_promotes_passed(tmp_path):
    state = _make_state({
        "ep": {
            "status": "pending",
            "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}],
            "phase_b_iters": [],
        },
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_3.json"
    report = _fake_report(tmp_path / "Validation" / "tests", {"ep": "passed"})

    def fake_run(cmd, env=None, **kwargs):
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 3)
    assert exc.value.code == 0

    st = json.loads((tmp_path / "Validation" / "state.json").read_text())
    assert st["trials"]["ep"]["status"] == "passed"
    assert st["trials"]["ep"]["final_iter"] == 3


def test_trial_id_unknown_exits_nonzero(tmp_path):
    state = _make_state({"ep": {"status": "pending"}})
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    with pytest.raises(SystemExit) as exc:
        _run_cmd(tmp_path, "b", 1, trial_id="missing_ep")
    assert exc.value.code == 2


def test_run_tests_auto_promotes_passed_no_baseline(tmp_path):
    state = _make_state({
        "ep": {"status": "phase_a_skipped", "phase_b_iters": []},
    })
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_1.json"
    report = _fake_report(tmp_path / "Validation" / "tests", {"ep": "passed"})

    def fake_run(cmd, env=None, **kwargs):
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=0)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 1)
    assert exc.value.code == 0

    st = json.loads((tmp_path / "Validation" / "state.json").read_text())
    assert st["trials"]["ep"]["status"] == "passed_no_baseline"


def test_run_tests_does_not_auto_promote_failures(tmp_path):
    state = _make_state({"ep": {"status": "pending", "phase_b_iters": []}})
    _write_state(tmp_path, state)
    _make_venv(tmp_path, "b")

    results_dir = tmp_path / "Validation" / "results" / "phase_b"
    results_dir.mkdir(parents=True, exist_ok=True)
    report_path = results_dir / "pytest_2.json"
    report = _fake_report(tmp_path / "Validation" / "tests", {"ep": "failed"})

    def fake_run(cmd, env=None, **kwargs):
        report_path.write_text(json.dumps(report), encoding="utf-8")
        return MagicMock(returncode=1)

    with patch("subprocess.run", side_effect=fake_run):
        with pytest.raises(SystemExit) as exc:
            _run_cmd(tmp_path, "b", 2)
    assert exc.value.code == 1

    st = json.loads((tmp_path / "Validation" / "state.json").read_text())
    assert st["trials"]["ep"]["status"] == "pending"


def test_reopen_clears_phase_a_skip_reason(tmp_path):
    # Reopening a passed_no_baseline trial must drop its stale phase_a_skip_reason so
    # that a fresh Phase A yielding a real baseline promotes to passed, not
    # passed_no_baseline.
    state = _make_state({
        "ep": {
            "status": "passed_no_baseline",
            "phase_a_skip_reason": "connector read returned 0 rows locally",
            "phase_a_iters": [{"iter": 1, "passing": 1, "failing": 0}],
            "phase_b_iters": [{"iter": 1, "passing": 1, "failing": 0}],
            "final_iter": 1,
        },
    })
    _write_state(tmp_path, state)
    reopened = validate._maybe_reopen_trial_after_phase_b_failure(
        tmp_path, "ep", phase="B", iter_n=2, passing=0, failing=1,
        allow_terminal_refresh=True,
    )
    assert reopened is True
    st = json.loads((tmp_path / "Validation" / "state.json").read_text())
    assert st["trials"]["ep"]["status"] == "pending"
    assert "phase_a_skip_reason" not in st["trials"]["ep"]

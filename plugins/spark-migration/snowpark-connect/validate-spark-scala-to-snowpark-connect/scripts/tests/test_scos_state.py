"""Tests for scos_state.py — the ported ScosState state machine (P4a core).

Covers the invariants that matter most: phase advancement, the record-trial-status
hard gate (incl. the hard_stuck fixer-dispatch requirement), run_index comparison
verdict, manual-review materialization, pending recovery, and atomic state I/O.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

import scos_state as s  # noqa: E402


def _trial(status="pending", **kw):
    return {"status": status, "phase_a_iters": [], "phase_b_iters": [], **kw}


# --- advance_phase ---------------------------------------------------------

def test_advance_phase_empty_trials_unchanged():
    st = {"phase": "init", "trials": {}}
    assert s.advance_phase(st)["phase"] == "init"


def test_advance_phase_not_all_terminal_unchanged():
    st = {"phase": "init", "trials": {"a": _trial("pending"), "b": _trial("passed")}}
    assert s.advance_phase(st)["phase"] == "init"


def test_advance_phase_init_to_phase_a_done():
    st = {"phase": "init", "trials": {
        "a": _trial("passed", phase_a_iters=[{"iter": 1}]),  # has A, no B
    }}
    assert s.advance_phase(st)["phase"] == "phase_a_done"


def test_advance_phase_to_phase_b_done():
    st = {"phase": "phase_a_done", "trials": {
        "a": _trial("passed", phase_a_iters=[{"i": 1}], phase_b_iters=[{"i": 1}]),
    }}
    assert s.advance_phase(st)["phase"] == "phase_b_done"


def test_phase_a_skipped_and_hard_stuck_do_not_block():
    st = {"phase": "init", "trials": {
        "a": _trial("phase_a_skipped"),              # counts as haveA & haveB
        "b": _trial("hard_stuck", phase_a_iters=[{}]),  # hard_stuck doesn't block haveB
    }}
    assert s.advance_phase(st)["phase"] == "phase_b_done"


# --- comparison_verdict ----------------------------------------------------

def test_comparison_verdict_branches():
    assert s.comparison_verdict({"status": "passed"}) == "match"
    assert s.comparison_verdict({"status": "passed_no_baseline"}) == "unverified"
    assert s.comparison_verdict({"status": "pending", "documented_divergences": [{"c": 1}]}) == "cosmetic_divergence"
    assert s.comparison_verdict({"status": "hard_stuck"}) == "real_divergence"
    assert s.comparison_verdict({"status": "pending"}) == "pending"


# --- apply_trial_status (hard gate) ----------------------------------------

def _state(**trials):
    return {"schema_version": 1, "phase": "init", "trials": trials, "fixer_dispatches": []}


def test_invalid_status_rejected():
    st = _state(a=_trial())
    _, code, err, _ = s.apply_trial_status(st, "a", "bogus")
    assert code == 2 and "invalid status" in err


def test_unknown_trial_rejected():
    _, code, err, _ = s.apply_trial_status(_state(a=_trial()), "zzz", "passed")
    assert code == 2 and "not in state.trials" in err


def test_hard_stuck_without_dispatch_rejected():
    st = _state(a=_trial())
    _, code, err, _ = s.apply_trial_status(st, "a", "hard_stuck")
    assert code == 2 and "no fixer dispatch" in err


def test_hard_stuck_with_dispatch_allowed():
    st = _state(a=_trial())
    st["fixer_dispatches"] = [{"trials_affected": ["a"]}]
    new, code, err, noop = s.apply_trial_status(st, "a", "hard_stuck", reason="stuck")
    assert err is None and new["trials"]["a"]["status"] == "hard_stuck"
    assert new["trials"]["a"]["hard_stuck_reason"] == "stuck"


# --- analysis-repair-exhausted gate (item 3) -------------------------------

def test_hard_stuck_repair_exhausted_needs_two_rounds():
    # one repair round + no dispatch → rejected even with the flag
    st = _state(a=_trial(phase_b_iters=[{"iter": 1, "fix_category": "analysis_repair"}]))
    _, code, err, _ = s.apply_trial_status(st, "a", "hard_stuck",
                                           analysis_repair_exhausted=True)
    assert code == 2 and "after only 1 schema-repair round" in err


def test_hard_stuck_repair_exhausted_two_rounds_allowed():
    st = _state(a=_trial(phase_b_iters=[
        {"iter": 1, "fix_category": "analysis_repair"},
        {"iter": 2, "fix_category": "schema_gap"}]))
    new, code, err, _ = s.apply_trial_status(st, "a", "hard_stuck",
                                             analysis_repair_exhausted=True, reason="gap")
    assert err is None and new["trials"]["a"]["status"] == "hard_stuck"


def test_hard_stuck_flag_without_repair_iters_rejected():
    # flag set but no recorded repair rounds → still rejected
    st = _state(a=_trial())
    _, code, err, _ = s.apply_trial_status(st, "a", "hard_stuck",
                                           analysis_repair_exhausted=True)
    assert code == 2 and "after only 0 schema-repair round" in err


# --- passed_no_baseline anti-gaming gate (item 2) --------------------------

def test_passed_no_baseline_rejected_when_baseline_exists():
    st = _state(a=_trial(phase_a_iters=[{"iter": 1, "passing": 3, "failing": 0}]))
    _, code, err, _ = s.apply_trial_status(st, "a", "passed_no_baseline")
    assert code == 2 and "Phase A produced a baseline" in err


def test_passed_no_baseline_allowed_without_baseline():
    # phase_a_skipped-style: no passing phase_a iter → allowed
    st = _state(a=_trial(phase_a_iters=[{"iter": 1, "passing": 0, "failing": 2}]))
    new, code, err, _ = s.apply_trial_status(st, "a", "passed_no_baseline")
    assert err is None and new["trials"]["a"]["status"] == "passed_no_baseline"


def test_passed_no_baseline_escape_with_flag():
    st = _state(a=_trial(phase_a_iters=[{"iter": 1, "passing": 3, "failing": 0}]))
    new, code, err, _ = s.apply_trial_status(st, "a", "passed_no_baseline",
                                             baseline_not_comparable=True)
    assert err is None and new["trials"]["a"]["status"] == "passed_no_baseline"


def test_passed_clears_hard_stuck_reason():
    st = _state(a=_trial("pending", hard_stuck_reason="old"))
    new, _, err, _ = s.apply_trial_status(st, "a", "passed")
    assert err is None and "hard_stuck_reason" not in new["trials"]["a"]


def test_idempotent_noop_for_terminal_same():
    st = _state(a=_trial("passed"))
    _, code, err, noop = s.apply_trial_status(st, "a", "passed")
    assert noop is True and code == 0 and err is None


# --- manual review + recovery ----------------------------------------------

def test_materialize_manual_review(tmp_path):
    st = {"phase": "init", "trials": {"ep1": _trial("pending")}}
    pb = tmp_path / "Validation/results/phase_b/ep1"
    pb.mkdir(parents=True)
    (pb / "_manual_review.json").write_text("{}")
    (pb / "_index.json").write_text("{}")
    out = s.materialize_manual_review_statuses(tmp_path, st)
    assert out["trials"]["ep1"]["status"] == "passed_no_baseline"


def test_recover_pending_trials():
    st = {"trials": {
        "ok": _trial("pending", phase_a_iters=[{}], phase_b_iters=[{"passing": 3, "failing": 0}]),
        "bad": _trial("pending", phase_b_iters=[{"passing": 0, "failing": 2}]),
    }}
    out, n = s.recover_pending_trials(st)
    assert n == 2
    assert out["trials"]["ok"]["status"] == "passed"
    assert out["trials"]["bad"]["status"] == "hard_stuck"


# --- state I/O + CLI -------------------------------------------------------

def test_write_atomic_roundtrip_and_event(tmp_path):
    st = {"schema_version": 1, "phase": "init", "trials": {}}
    s.save_state(tmp_path, st)
    assert s.load_state(tmp_path) == st
    s.append_event(s.validation_root(tmp_path), {"kind": "x"})
    line = (tmp_path / "Validation/events.jsonl").read_text().strip()
    rec = json.loads(line)
    assert rec["kind"] == "x" and "ts" in rec


def test_cli_record_trial_status(tmp_path):
    st = _state(a=_trial())
    s.save_state(tmp_path, st)
    rc = s.main(["record-trial-status", "--conv-root", str(tmp_path), "--trial-id", "a", "--status", "passed"])
    assert rc == 0
    assert s.load_state(tmp_path)["trials"]["a"]["status"] == "passed"
    # hard_stuck with no dispatch -> exit 2
    rc2 = s.main(["record-trial-status", "--conv-root", str(tmp_path), "--trial-id", "a", "--status", "hard_stuck"])
    assert rc2 == 2


# --- helpers ---------------------------------------------------------------

def test_project_slug_and_normalize_sink():
    assert s.project_slug("My Project!") == "my_project"
    assert s.project_slug("123abc") == "p_123abc"
    assert s.normalize_sink_name("db.schema.MyTable") == "MyTable"
    assert s.normalize_sink_name("s3://bucket/path/out.parquet") == "out"


def test_ensure_entrypoints_list_dict_and_list():
    assert s.ensure_entrypoints_list({"entrypoints": [{"id": "a"}]}) == [{"id": "a"}]
    out = s.ensure_entrypoints_list({"entrypoints": {"a": {"x": 1}, "b": "str"}})
    assert {"id": "a", "x": 1} in out and {"id": "b"} in out


# --- init / select-entrypoints / status ------------------------------------

def _init_workspace(tmp_path):
    (tmp_path / "Output").mkdir()
    src = tmp_path / "src.scala"
    src.write_text("object X")
    rc = s.main(["init", "--conv-root", str(tmp_path), "--connection", "conn",
                 "--original-source", str(src)])
    assert rc == 0
    return s.load_state(tmp_path)


def test_init_creates_state_and_dirs(tmp_path):
    st = _init_workspace(tmp_path)
    assert st["schema_version"] == 1 and st["phase"] == "init"
    assert st["config"]["connection_name"] == "conn"
    assert (tmp_path / "Validation/results/phase_b").is_dir()
    assert (tmp_path / "Validation/source/src.scala").is_file()
    assert len(st["run_id"]) == 8


def test_init_idempotent_skip(tmp_path):
    _init_workspace(tmp_path)
    # set a milestone so the idempotency guard triggers
    st = s.load_state(tmp_path)
    st["milestones"]["synth_survey"] = True
    s.save_state(tmp_path, st)
    rid = st["run_id"]
    src = tmp_path / "src.scala"
    rc = s.main(["init", "--conv-root", str(tmp_path), "--connection", "conn",
                 "--original-source", str(src)])
    assert rc == 0 and s.load_state(tmp_path)["run_id"] == rid  # unchanged


# --- init source/Output layout alignment (item 1) --------------------------

def test_init_rejects_misaligned_source(tmp_path):
    # Output nests under an extra wrapper dir the copied source lacks → patches
    # would silently miss one side. init must refuse (exit 2).
    (tmp_path / "Output/proj/src").mkdir(parents=True)
    (tmp_path / "Output/proj/src/Job.scala").write_text("object Job\n")
    src = tmp_path / "orig"
    (src / "src").mkdir(parents=True)
    (src / "src/Job.scala").write_text("object Job\n")
    rc = s.main(["init", "--conv-root", str(tmp_path), "--connection", "c",
                 "--original-source", str(src)])
    assert rc == 2


def test_init_accepts_aligned_source(tmp_path):
    (tmp_path / "Output/src").mkdir(parents=True)
    (tmp_path / "Output/src/Job.scala").write_text("object Job\n")
    src = tmp_path / "orig"
    (src / "src").mkdir(parents=True)
    (src / "src/Job.scala").write_text("object Job\n")
    rc = s.main(["init", "--conv-root", str(tmp_path), "--connection", "c",
                 "--original-source", str(src)])
    assert rc == 0
    assert (tmp_path / "Validation/source/src/Job.scala").is_file()


def test_init_wipes_stale_source_before_copy(tmp_path):
    (tmp_path / "Output/src").mkdir(parents=True)
    (tmp_path / "Output/src/Job.scala").write_text("object Job\n")
    src = tmp_path / "orig"
    (src / "src").mkdir(parents=True)
    (src / "src/Job.scala").write_text("object Job\n")
    # plant a stale file from a hypothetical prior failed init
    stale = tmp_path / "Validation/source/old"
    stale.mkdir(parents=True)
    (stale / "Leftover.scala").write_text("object Leftover\n")
    rc = s.main(["init", "--conv-root", str(tmp_path), "--connection", "c",
                 "--original-source", str(src), "--force"])
    assert rc == 0
    assert not (tmp_path / "Validation/source/old/Leftover.scala").exists()


def _write_analysis(tmp_path, candidates):
    p = tmp_path / "Validation/shared/analysis.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"entrypoint_candidates": candidates}))


def test_select_entrypoints(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}, {"id": "ep2"}, {"id": "ep3"}])
    rc = s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1,ep3"])
    assert rc == 0
    st = s.load_state(tmp_path)
    assert set(st["trials"]) == {"ep1", "ep3"}
    assert st["milestones"]["entrypoints_selected"] is True
    analysis = json.loads((tmp_path / "Validation/shared/analysis.json").read_text())
    assert [e["id"] for e in analysis["entrypoints"]] == ["ep1", "ep3"]


def test_select_entrypoints_max_exceeded(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}, {"id": "ep2"}])
    rc = s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1,ep2", "--max", "1"])
    assert rc == 2


def test_scope_entrypoints_reports_kept_and_removed(tmp_path, capsys):
    # stateless subset filter (no init/state.json required)
    _write_analysis(tmp_path, [{"id": "ep1"}, {"id": "ep2"}, {"id": "ep3"}])
    rc = s.main(["scope-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1,ep3"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "kept ['ep1', 'ep3']" in out, out
    assert "removed 1 unselected candidate(s)" in out, out
    analysis = json.loads((tmp_path / "Validation/shared/analysis.json").read_text())
    assert [e["id"] for e in analysis["entrypoints"]] == ["ep1", "ep3"]
    assert [e["id"] for e in analysis["entrypoint_candidates"]] == ["ep1", "ep3"]


def test_clear_trial_outputs_removes_stale_state(tmp_path):
    trial_dir = tmp_path / "phase_a" / "ep1"
    (trial_dir / "tables").mkdir(parents=True)
    (trial_dir / "artifacts").mkdir()
    (trial_dir / "diffs").mkdir()
    (trial_dir / "stage_snapshot").mkdir()
    for rel in (
        "_harness_status.json", "_index.json", "_manual_review.json",
        "workload_error.txt", "capture_error.txt",
        "tables/out.parquet", "artifacts/wb.xlsx", "diffs/out.json",
        "stage_snapshot/t.csv", "out_diff.json",
    ):
        (trial_dir / rel).write_text("stale", encoding="utf-8")

    s._clear_trial_outputs(trial_dir)

    # dir still exists (recreated) but is empty of stale state
    assert trial_dir.is_dir()
    assert list(trial_dir.iterdir()) == []


def test_clear_trial_outputs_only_touches_given_dir(tmp_path):
    # the phase_a baseline must NOT be cleared when clearing phase_b
    phase_a = tmp_path / "phase_a" / "ep1"
    phase_b = tmp_path / "phase_b" / "ep1"
    (phase_a / "tables").mkdir(parents=True)
    (phase_a / "tables" / "base.parquet").write_text("keep", encoding="utf-8")
    (phase_b / "tables").mkdir(parents=True)
    (phase_b / "tables" / "old.parquet").write_text("stale", encoding="utf-8")

    s._clear_trial_outputs(phase_b)

    assert (phase_a / "tables" / "base.parquet").exists()  # baseline untouched
    assert not (phase_b / "tables").exists()


def test_status_exit_codes(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    assert s.main(["status", "--conv-root", str(tmp_path)]) == 1  # pending
    s.main(["record-fixer-dispatch", "--conv-root", str(tmp_path), "--trial-id", "ep1",
            "--error-class", "x", "--error-hash", "h", "--outcome", "no_change"])
    s.main(["record-trial-status", "--conv-root", str(tmp_path), "--trial-id", "ep1",
            "--status", "hard_stuck", "--reason", "stuck"])
    assert s.main(["status", "--conv-root", str(tmp_path)]) == 2  # blocked


# --- record-iter / milestone / patch -------------------------------------

def test_record_iter_and_phase_advance(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    rc = s.main(["record-iter", "--conv-root", str(tmp_path), "--trial-id", "ep1",
                 "--phase", "A", "--iter", "1", "--passing", "3", "--failing", "0"])
    assert rc == 0
    st = s.load_state(tmp_path)
    assert st["trials"]["ep1"]["phase_a_iters"][0]["passing"] == 3
    assert st["phase_a"]["iter"] == 1
    assert (tmp_path / "Validation/events.jsonl").is_file()
    # no-op on duplicate iter
    assert s.main(["record-iter", "--conv-root", str(tmp_path), "--trial-id", "ep1",
                   "--phase", "A", "--iter", "1"]) == 0
    # passed -> phase advances to phase_a_done (terminal, has A, no B)
    s.main(["record-trial-status", "--conv-root", str(tmp_path), "--trial-id", "ep1", "--status", "passed"])
    assert s.load_state(tmp_path)["phase"] == "phase_a_done"


def test_record_milestone_validation(tmp_path):
    _init_workspace(tmp_path)
    assert s.main(["record-milestone", "--conv-root", str(tmp_path), "--milestone", "bogus"]) == 2
    assert s.main(["record-milestone", "--conv-root", str(tmp_path), "--milestone", "workload_built"]) == 0
    assert s.load_state(tmp_path)["milestones"]["workload_built"] is True


def test_record_patch(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    s.main(["record-patch", "--conv-root", str(tmp_path), "--trial-id", "ep1",
            "--phase", "phase_a", "--file", "F.scala", "--reason", "fix"])
    st = s.load_state(tmp_path)
    assert st["trials"]["ep1"]["phase_a_patches"][0]["file"] == "F.scala"


# --- document-divergence / migrate / mark-empty / unselected-dep -----------

def test_document_divergence_updates_state_and_analysis(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    rc = s.main(["document-divergence", "--conv-root", str(tmp_path), "--trial-id", "ep1",
                 "--sink-id", "out_tbl", "--column", "amt", "--reason", "float drift"])
    assert rc == 0
    st = s.load_state(tmp_path)
    div = st["trials"]["ep1"]["documented_divergences"][0]
    assert div["column"] == "AMT" and div["sink_id"] == "out_tbl"
    analysis = json.loads((tmp_path / "Validation/shared/analysis.json").read_text())
    assert "ep1.out_tbl" in analysis["expected_divergences"]
    assert analysis["expected_divergences"]["ep1.out_tbl"][0]["scope"] == "data"


def test_mark_unselected_dependency_passes_review(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    rc = s.main(["mark-unselected-dependency", "--conv-root", str(tmp_path),
                 "--trial-id", "ep1", "--reason", "depends on unselected ep2"])
    assert rc == 0
    st = s.load_state(tmp_path)
    assert st["trials"]["ep1"]["status"] == "passed_no_baseline"
    assert st["fixer_dispatches"][0]["error_class"] == "unselected_dependency"


def test_migrate_divergences_ambiguous(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    st = s.load_state(tmp_path)
    st["trials"]["ep1"]["documented_divergences"] = [{"sink_id": "write_001", "column": "X"}]
    s.save_state(tmp_path, st)
    # no phase_a write_ dir -> ambiguous -> exit 1
    assert s.main(["migrate-divergences", "--conv-root", str(tmp_path)]) == 1


# --- build-index + summary gate --------------------------------------------

def test_build_index_run_index(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    s.main(["document-divergence", "--conv-root", str(tmp_path), "--trial-id", "ep1",
            "--sink-id", "t", "--column", "c", "--reason", "r"])
    assert s.main(["build-index", "--conv-root", str(tmp_path)]) == 0
    ri = json.loads((tmp_path / "Validation/run_index.json").read_text())
    assert ri["run"]["run_id"]
    ep = ri["entrypoints"][0]
    assert ep["id"] == "ep1"
    assert ep["comparison"]["verdict"] == "cosmetic_divergence"  # pending + documented div


def test_summary_exit4_when_events_missing(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    # no record-iter -> no events.jsonl -> gate fails
    assert s.main(["summary", "--conv-root", str(tmp_path)]) == 4


def test_summary_exit0_when_all_outputs_present(tmp_path):
    _init_workspace(tmp_path)
    _write_analysis(tmp_path, [{"id": "ep1"}])
    s.main(["select-entrypoints", "--conv-root", str(tmp_path), "--ids", "ep1"])
    s.main(["record-iter", "--conv-root", str(tmp_path), "--trial-id", "ep1",
            "--phase", "A", "--iter", "1", "--passing", "1", "--failing", "0"])
    assert s.main(["summary", "--conv-root", str(tmp_path)]) == 0
    summ = json.loads((tmp_path / "Validation/results/summary.json").read_text())
    assert summ["decision"]["overall"] in ("partial", "passed", "blocked")
    assert (tmp_path / "Validation/results/REPORT.md").is_file()


# --- commit (git) ----------------------------------------------------------

def test_commit(tmp_path):
    import subprocess
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t.io"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "Output").mkdir()
    (tmp_path / "Output/x.txt").write_text("hi")
    rc = s.main(["commit", "--conv-root", str(tmp_path), "--message", "msg",
                 "--kind", "test-patch", "--print-sha-only"])
    assert rc == 0
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True)
    assert "[TEST-PATCH] msg" in log.stdout
    # nothing-to-commit path
    assert s.main(["commit", "--conv-root", str(tmp_path), "--message", "again",
                   "--kind", "test-patch"]) == 0


# --- P1: branch + harvest delivery model -----------------------------------

def _git_init_repo(tmp_path):
    import subprocess
    run = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, capture_output=True, text=True, check=True)
    run("init", "-q")
    run("config", "user.email", "t@t.io")
    run("config", "user.name", "t")
    run("checkout", "-q", "-b", "main")
    (tmp_path / "Output").mkdir()
    (tmp_path / "Output/x.txt").write_text("base\n")
    (tmp_path / "Output/conf.txt").write_text("base\n")
    run("add", "-A")
    run("commit", "-q", "-m", "baseline")
    return run


def _init_on_branch(tmp_path):
    """git repo on 'main' + scos init → cuts validation/<rid>."""
    _git_init_repo(tmp_path)
    src = tmp_path / "src.scala"
    src.write_text("object X")
    assert s.main(["init", "--conv-root", str(tmp_path), "--connection", "c",
                   "--original-source", str(src)]) == 0
    return s.load_state(tmp_path)


def _branch(tmp_path):
    import subprocess
    return subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                          cwd=tmp_path, capture_output=True, text=True).stdout.strip()


def test_init_cuts_validation_branch(tmp_path):
    st = _init_on_branch(tmp_path)
    assert st["git"]["original_branch"] == "main"
    assert st["git"]["validation_branch"] == f"validation/{st['run_id']}"
    assert st["git"]["harvested"] is False
    assert _branch(tmp_path) == f"validation/{st['run_id']}"
    # source baseline committed on the validation branch
    import subprocess
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True)
    assert "[VALIDATION] import Phase-A source baseline" in log.stdout


def test_commit_migration_fix_prefix_and_trailer(tmp_path):
    import subprocess
    _init_on_branch(tmp_path)
    (tmp_path / "Output/x.txt").write_text("real fix\n")
    assert s.main(["commit", "--conv-root", str(tmp_path), "--message", "fix join",
                   "--kind", "migration-fix", "--trial-ids", "ep1"]) == 0
    body = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=tmp_path,
                          capture_output=True, text=True).stdout
    assert body.startswith("[MIGRATION-FIX] fix join")
    assert "SCOS-Trials: ep1" in body


def test_commit_migration_fix_rejects_scos_leak(tmp_path):
    _init_on_branch(tmp_path)
    (tmp_path / "Output/x.txt").write_text('val t = sys.env("SCOS_DATABASE_NAME")\n')
    with pytest.raises(SystemExit) as e:
        s.main(["commit", "--conv-root", str(tmp_path), "--message", "leak",
                "--kind", "migration-fix"])
    assert e.value.code == 2
    # but the SAME edit is allowed as a test-patch
    assert s.main(["commit", "--conv-root", str(tmp_path), "--message", "harness wiring",
                   "--kind", "test-patch"]) == 0


def test_harvest_cherry_picks_migration_fix_only(tmp_path):
    import subprocess
    st = _init_on_branch(tmp_path)
    vb = st["git"]["validation_branch"]
    # [TEST-PATCH] on a different file (harness wiring — must NOT reach deliverable)
    (tmp_path / "Output/conf.txt").write_text('env = "SCOS_OUTPUT_SCHEMA"\n')
    assert s.main(["commit", "--conv-root", str(tmp_path), "--message", "wire env",
                   "--kind", "test-patch"]) == 0
    # [MIGRATION-FIX] on x.txt (real fix — must reach deliverable)
    (tmp_path / "Output/x.txt").write_text("real fix\n")
    assert s.main(["commit", "--conv-root", str(tmp_path), "--message", "fix dialect",
                   "--kind", "migration-fix", "--trial-ids", "ep1"]) == 0
    # harvest preconditions: summary.json + run_index.json
    ws = tmp_path / "Validation"
    (ws / "results").mkdir(parents=True, exist_ok=True)
    (ws / "results/summary.json").write_text("{}")
    (ws / "run_index.json").write_text("{}")

    assert s.main(["harvest", "--conv-root", str(tmp_path)]) == 0
    assert _branch(tmp_path) == "main"
    assert s.load_state(tmp_path)["git"]["harvested"] is True
    # deliverable has the migration fix but NOT the test patch
    assert (tmp_path / "Output/x.txt").read_text() == "real fix\n"
    assert (tmp_path / "Output/conf.txt").read_text() == "base\n"
    log = subprocess.run(["git", "log", "--oneline"], cwd=tmp_path, capture_output=True, text=True).stdout
    assert "[MIGRATION-FIX] fix dialect" in log
    assert "[TEST-PATCH] wire env" not in log


def test_harvest_no_validation_branch_errors(tmp_path):
    _init_workspace(tmp_path)  # non-git workspace → no git branch recorded
    assert s.main(["harvest", "--conv-root", str(tmp_path)]) == 1


def test_build_index_attributes_migration_fix_commits(tmp_path):
    _init_on_branch(tmp_path)
    (tmp_path / "Output/x.txt").write_text("real fix\n")
    assert s.main(["commit", "--conv-root", str(tmp_path), "--message", "fix",
                   "--kind", "migration-fix", "--trial-ids", "ep1"]) == 0
    st = s.load_state(tmp_path)
    st["trials"] = {"ep1": {"status": "passed", "phase_b_iters": []}}
    s.save_state(tmp_path, st)
    s.build_index(tmp_path)
    idx = json.loads((tmp_path / "Validation/run_index.json").read_text())
    ep = next(e for e in idx["entrypoints"] if e["id"] == "ep1")
    fixes = ep["phase_b"]["migration_fix_commits"]
    assert len(fixes) == 1 and fixes[0]["subject"] == "fix"


# --- auto-provision helpers ------------------------------------------------

def test_needs_provision_when_golden_schemas_missing():
    st = {
        "trials": {"ep1": _trial()},
        "snowflake": {"provisioned": False, "golden_schemas": {}},
    }
    assert s._needs_provision(st) is True


def test_needs_provision_false_when_all_trials_have_golden():
    st = {
        "trials": {"ep1": _trial()},
        "snowflake": {
            "provisioned": True,
            "golden_schemas": {"ep1": {"schema": "GOLDEN_EP1"}},
        },
    }
    assert s._needs_provision(st) is False

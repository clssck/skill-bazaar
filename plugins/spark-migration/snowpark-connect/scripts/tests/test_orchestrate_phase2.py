"""Tests for orchestrate_phases.py Phase 2 planning vs fallback separation.

Regression guard: the default (planning) invocation must be side-effect-free —
it computes the dispatch plan but must NOT mutate any source files. The
deterministic fallback only runs under --run-fallback (Phase 2a), after the
fixer sub-agents complete.
"""

from __future__ import annotations

import json
from pathlib import Path

import orchestrate_phases as op


def _make_state(tmp_path: Path, src: str) -> tuple[Path, Path]:
    conv = tmp_path / "Conversion-SCOS-test"
    out = conv / "Output"
    out.mkdir(parents=True)
    scala = out / "M.scala"
    scala.write_text(src, encoding="utf-8")
    state = {
        "manifest": ["M.scala"],
        "migrated_dir": str(out),
        "conversion_root": str(conv),
        # skill_directory intentionally omitted — planning must not need it.
    }
    sp = conv / "migration_state.json"
    sp.write_text(json.dumps(state), encoding="utf-8")
    return sp, scala


def test_phase2_planning_is_side_effect_free(tmp_path):
    src = "object M {\n  val spark = SparkSession.builder().getOrCreate()\n}\n"
    sp, scala = _make_state(tmp_path, src)

    rc = op.orchestrate_phase2(str(sp), budget=80000, language="scala",
                               max_parallel=4, run_fallback_flag=False)

    assert rc == 0
    # The source file must be byte-for-byte unchanged (no header/import injection).
    assert scala.read_text(encoding="utf-8") == src
    # The plan must have been persisted for the coordinator.
    state = json.loads(sp.read_text())
    assert "phase2_chunks" in state and state["phase2_chunks"]
    # Planning must NOT have created fixer-progress/coverage bookkeeping.
    assert "orchestrator_coverage_verified" not in state


def test_phase2_planning_handles_fresh_state_without_full_rewrite(tmp_path):
    # On a fresh state (no files_done / pending_files), planning must still not
    # transform anything — this is the exact scenario that previously caused the
    # fallback to generically rewrite the entire manifest.
    src = "object M\n"
    sp, scala = _make_state(tmp_path, src)
    op.orchestrate_phase2(str(sp), budget=80000, language="scala",
                          max_parallel=4, run_fallback_flag=False)
    assert scala.read_text(encoding="utf-8") == src

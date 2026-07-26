# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Deferred SEED/ITER commit behaviour in body-mode frontier selection.

The per-model save runs with ``defer_commit=True`` so the cross-model frontier
stamp (``is_frontier`` / ``test_score``) can land on the real lineage runs
before they are committed.  ``_select_best_from_frontier`` therefore owns the
commit of those deferred runs in a ``finally`` — the runs must be committed
whether the function returns normally OR raises, so they never linger in
RUNNING state.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from snowflake_ai_optimize.core.experiment import (
    ParetoCandidateInfo,
    commit_experiment_run,
    commit_runs,
)
from snowflake_ai_optimize.gepa.optimize_body import (
    ModelOptimizationResult,
    _commit_deferred_model_runs,
    _select_best_from_frontier,
)


class _FakeSession:
    """Records the SQL statements issued, with optional simulated failure."""

    def __init__(self, *, fail_on: str | None = None):
        self.statements: list[str] = []
        self._fail_on = fail_on

        class _SQLBuilder:
            def __init__(s, sql, parent):
                s.sql = sql
                s.parent = parent

            def collect(s):
                s.parent.statements.append(s.sql)
                if s.parent._fail_on and s.parent._fail_on in s.sql:
                    raise RuntimeError(f"Simulated failure on: {s.sql}")
                return []

        self._SQLBuilder = _SQLBuilder

    def sql(self, sql: str):
        return self._SQLBuilder(sql, self)


def _completed_model(
    model: str = "m1",
    *,
    pending: list[str] | None = None,
    run_names: tuple[str, ...] = ("M1_SEED", "M1_ITER_1"),
) -> ModelOptimizationResult:
    candidates = [
        ParetoCandidateInfo(
            run_name=run_names[0],
            model=model,
            estimated_cost=0.001,
            score=0.60,
            prompt_text="SEED BODY",
        ),
        ParetoCandidateInfo(
            run_name=run_names[1],
            model=model,
            estimated_cost=0.004,
            score=0.85,
            prompt_text="ITER BODY",
        ),
    ]
    return ModelOptimizationResult(
        model=model,
        status="completed",
        elapsed_seconds=1.0,
        best_val_score=0.85,
        seed_val_score=0.60,
        pareto_candidates=candidates,
        pending_commit_runs=list(pending if pending is not None else run_names),
    )


def _config(*, test_table: str | None):
    return SimpleNamespace(
        experiment_name="DB.SC.EXP",
        test_table=test_table,
        max_frontier_candidates=7,
        # Consumed by write_consolidated_seed in _select_best_from_frontier.
        function_name="DB.SC.FN",
        seed_body="SEED BODY",
        metric_name="exact_match",
        custom_metric_udf=None,
    )


def _commits(session: _FakeSession) -> list[str]:
    return [s for s in session.statements if "COMMIT RUN" in s]


class TestSelectBestCommitsDeferredRuns:
    def test_commits_on_happy_path_without_test_table(self):
        """No test table: frontier is stamped and all deferred runs commit."""
        session = _FakeSession()
        model_results = [_completed_model()]

        result = _select_best_from_frontier(
            session=session,
            config=_config(test_table=None),
            model_results=model_results,
            metric_evaluator=MagicMock(),
            run_id="run1",
        )

        assert result.best_model == "m1"
        commits = _commits(session)
        assert any("M1_SEED" in s for s in commits)
        assert any("M1_ITER_1" in s for s in commits)
        # The markers are drained so a repeat commit would be a no-op.
        assert model_results[0].pending_commit_runs is None

    def test_commits_when_test_eval_raises(self):
        """Regression: if the frontier test-eval raises, the deferred SEED/ITER
        runs must STILL be committed (via the finally) rather than lingering in
        RUNNING state.
        """  # noqa: D205
        session = _FakeSession()
        model_results = [_completed_model()]

        with (
            patch(
                "snowflake_ai_optimize.gepa.optimize_body."
                "_test_eval_frontier_candidates",
                side_effect=RuntimeError("all frontier candidates failed test-eval"),
            ),
            pytest.raises(RuntimeError, match="test-eval"),
        ):
            _select_best_from_frontier(
                session=session,
                config=_config(test_table="DB.SC.TEST"),
                model_results=model_results,
                metric_evaluator=MagicMock(),
                run_id="run1",
            )

        commits = _commits(session)
        assert any("M1_SEED" in s for s in commits), (
            "deferred SEED run must be committed even though test-eval raised"
        )
        assert any("M1_ITER_1" in s for s in commits), (
            "deferred ITER run must be committed even though test-eval raised"
        )
        assert model_results[0].pending_commit_runs is None

    def test_commits_when_frontier_is_empty(self):
        """An empty frontier raises RuntimeError, but the deferred runs (which
        carry valid valset/cost metrics) must still be committed.
        """  # noqa: D205
        session = _FakeSession()
        # A completed model with no pareto candidates yields an empty frontier.
        mr = _completed_model()
        mr.pareto_candidates = []
        model_results = [mr]

        with pytest.raises(RuntimeError, match="No Pareto frontier"):
            _select_best_from_frontier(
                session=session,
                config=_config(test_table=None),
                model_results=model_results,
                metric_evaluator=MagicMock(),
                run_id="run1",
            )

        commits = _commits(session)
        assert any("M1_SEED" in s for s in commits)
        assert any("M1_ITER_1" in s for s in commits)


class TestCommitDeferredModelRuns:
    def test_drains_and_commits_completed_models(self):
        session = _FakeSession()
        model_results = [
            _completed_model("m1", run_names=("M1_SEED", "M1_ITER_1")),
            _completed_model("m2", run_names=("M2_SEED", "M2_ITER_1")),
        ]

        _commit_deferred_model_runs(session, "DB.SC.EXP", model_results)

        commits = _commits(session)
        assert len(commits) == 4
        for mr in model_results:
            assert mr.pending_commit_runs is None

    def test_second_call_is_a_noop(self):
        session = _FakeSession()
        model_results = [_completed_model()]

        _commit_deferred_model_runs(session, "DB.SC.EXP", model_results)
        first = len(_commits(session))
        _commit_deferred_model_runs(session, "DB.SC.EXP", model_results)
        assert len(_commits(session)) == first

    def test_skips_failed_models(self):
        session = _FakeSession()
        failed = ModelOptimizationResult(
            model="m2",
            status="failed",
            elapsed_seconds=0.0,
            error="boom",
            pending_commit_runs=["M2_SEED"],
        )
        _commit_deferred_model_runs(session, "DB.SC.EXP", [failed])
        assert _commits(session) == []


class TestCommitRunStatus:
    """``commit_experiment_run`` / ``commit_runs`` WITH STATUS support.

    A failed model has no separate ``<MODEL>_FAILED`` run in the global run
    structure; its own runs are committed with ``STATUS='FAILED'`` instead.
    """

    def test_default_commit_has_no_status_clause(self):
        session = _FakeSession()
        commit_experiment_run(session, "DB.SC.EXP", "ITER_1")
        stmt = _commits(session)[0]
        assert stmt == "ALTER EXPERIMENT DB.SC.EXP COMMIT RUN ITER_1"
        assert "WITH STATUS" not in stmt

    def test_failed_status_appends_clause(self):
        session = _FakeSession()
        commit_experiment_run(session, "DB.SC.EXP", "ITER_1", status="FAILED")
        assert _commits(session) == [
            "ALTER EXPERIMENT DB.SC.EXP COMMIT RUN ITER_1 WITH STATUS='FAILED'"
        ]

    def test_status_is_uppercased(self):
        session = _FakeSession()
        commit_experiment_run(session, "DB.SC.EXP", "ITER_1", status="failed")
        assert _commits(session)[0].endswith("WITH STATUS='FAILED'")

    def test_unknown_status_rejected(self):
        session = _FakeSession()
        with pytest.raises(ValueError, match="Unsupported COMMIT RUN status"):
            commit_experiment_run(session, "DB.SC.EXP", "ITER_1", status="DROP")
        assert _commits(session) == []

    def test_commit_runs_passes_status_through(self):
        session = _FakeSession()
        commit_runs(session, "DB.SC.EXP", ["SEED", "ITER_1"], status="FAILED")
        commits = _commits(session)
        assert len(commits) == 2
        assert all(s.endswith("WITH STATUS='FAILED'") for s in commits)

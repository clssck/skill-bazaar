# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Unit tests for the EXECUTE_AI_FUNCTION_EVAL_OPTS SPROC handler.

Covers SPEC parsing / validation (pure helpers), top-level dispatch
(evaluation vs optimization vs neither), and the spec -> engine mapping for
both paths, with ``evaluate``, ``save_evaluation_to_experiment`` and
``run_optimization`` mocked out.
"""

from __future__ import annotations

import sys
import threading
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import handlers.execute_eval_opts_handler as handler
from handlers.execute_eval_opts_handler import (
    _first_metric,
    _parse_specification,
    _resolve_arg_param_names,
    _resolve_dataset,
    _resolve_function_name,
    _resolve_metric,
    _resolve_num_eval_runs,
    execute_ai_function_eval_opts,
)

EVAL_SPEC = """
function:
  function_name: "db.sch.answer(VARCHAR, VARCHAR)"
metrics:
  - name: exact_match
dataset:
  name: db.sch.qa
  column_mapping:
    argument_mapping:
      question: question_col
      context: context_col
    ground_truth: expected_col
evaluation:
  num_eval_runs: 1
"""

OPT_SPEC = """
function:
  function_name: "db.sch.answer(VARCHAR)"
metrics:
  - name: exact_match
dataset:
  name: db.sch.train
  column_mapping:
    argument_mapping:
      q: q_col
    ground_truth: gt
  holdout_data: db.sch.holdout
optimization:
  models: [mistral-7b]
  budget: demo
  optimize_mode: body
  validation_fraction: 0.5
"""


class TestSpecHelpers:
    """Pure helpers raise plain ValueError (undecorated)."""

    def test_parse_specification_empty(self):
        with pytest.raises(ValueError, match="required and cannot be empty"):
            _parse_specification("")

    def test_parse_specification_non_mapping(self):
        with pytest.raises(ValueError, match="must be a YAML mapping"):
            _parse_specification("- a\n- b")

    def test_first_metric_list_and_mapping(self):
        assert (
            _first_metric({"metrics": [{"name": "fuzzy_match"}]})["name"]
            == "fuzzy_match"
        )
        assert (
            _first_metric({"metrics": {"name": "exact_match"}})["name"] == "exact_match"
        )

    def test_first_metric_missing(self):
        with pytest.raises(ValueError, match="metrics is required"):
            _first_metric({})

    def test_resolve_function_name_query_text_rejected(self):
        with pytest.raises(ValueError, match="Builtin AI function"):
            _resolve_function_name(
                {
                    "function": {
                        "query_text": "AI_COMPLETE(...)",
                    }
                }
            )

    def test_resolve_dataset_requires_ground_truth(self):
        spec = {
            "dataset": {"name": "t", "column_mapping": {"argument_mapping": {"a": "c"}}}
        }
        with pytest.raises(ValueError, match="ground_truth is required"):
            _resolve_dataset(spec)

    def test_resolve_dataset_ok(self):
        spec = {
            "dataset": {
                "name": "db.sch.t",
                "column_mapping": {
                    "argument_mapping": {"a": "c1", "b": "c2"},
                    "ground_truth": "gt",
                },
            }
        }
        table, cols, label, arg_keys = _resolve_dataset(spec)
        assert (table, cols, label) == ("db.sch.t", ["c1", "c2"], "gt")
        assert arg_keys == ["a", "b"]

    def test_resolve_dataset_rejects_non_mapping(self):
        # A bare-string dataset is accepted by the GS structural schema but not yet
        # by the engine, so the sproc requires a mapping with column_mapping.
        with pytest.raises(ValueError, match="dataset is required"):
            _resolve_dataset({"dataset": "db.sch.t"})

    def test_resolve_dataset_requires_name(self):
        spec = {
            "dataset": {
                "column_mapping": {"argument_mapping": {"a": "c"}, "ground_truth": "gt"}
            }
        }
        with pytest.raises(ValueError, match=r"dataset\.name is required"):
            _resolve_dataset(spec)

    def test_resolve_dataset_requires_argument_mapping(self):
        spec = {
            "dataset": {"name": "db.sch.t", "column_mapping": {"ground_truth": "gt"}}
        }
        with pytest.raises(ValueError, match="argument_mapping is required"):
            _resolve_dataset(spec)

    def test_resolve_metric_normalizes_llm_judge(self):
        assert _resolve_metric({"name": "llm-judge"})[0] == "llm_judge"

    def test_resolve_metric_custom_requires_udf(self):
        with pytest.raises(ValueError, match="custom_udf is required"):
            _resolve_metric({"name": "custom"})

    def test_resolve_metric_builds_options(self):
        _, _, _model, opts = _resolve_metric(
            {"name": "llm-judge", "aggregation": "mean"}
        )
        assert opts == {"aggregation": "mean"}

    def test_resolve_num_eval_runs_defaults_to_one(self):
        # Missing evaluation section, or an evaluation section without the key.
        assert _resolve_num_eval_runs({}) == 1
        assert _resolve_num_eval_runs({"evaluation": {}}) == 1
        assert _resolve_num_eval_runs({"evaluation": {"num_eval_runs": None}}) == 1

    def test_resolve_num_eval_runs_reads_positive_int(self):
        assert _resolve_num_eval_runs({"evaluation": {"num_eval_runs": 1}}) == 1
        assert _resolve_num_eval_runs({"evaluation": {"num_eval_runs": 5}}) == 5

    @pytest.mark.parametrize("bad", [0, -1, -5])
    def test_resolve_num_eval_runs_rejects_non_positive(self, bad):
        with pytest.raises(ValueError, match="positive integer"):
            _resolve_num_eval_runs({"evaluation": {"num_eval_runs": bad}})

    @pytest.mark.parametrize("bad", [True, 1.5, "3", "abc", [3]])
    def test_resolve_num_eval_runs_rejects_non_int(self, bad):
        # bool is an int subclass and floats/strings are never coerced silently.
        with pytest.raises(ValueError, match="positive integer"):
            _resolve_num_eval_runs({"evaluation": {"num_eval_runs": bad}})


class TestResolveArgParamNames:
    """Argument-key -> parameter-name resolution (named + positional $N)."""

    def _patch_describe(self, monkeypatch, arg_names):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=list(arg_names)),
        )

    def test_named_keys_resolve_to_ddl_casing(self, monkeypatch):
        self._patch_describe(monkeypatch, ["TEXT", "LABEL"])
        # Lowercase spec keys resolve to the function's declared (upper) casing
        # so the eval alias `col AS "TEXT"` matches the inlined body's `TEXT`.
        result = _resolve_arg_param_names(MagicMock(), "db.sch.f", ["text", "label"])
        assert result == ["TEXT", "LABEL"]

    def test_named_key_without_match_falls_back(self, monkeypatch):
        self._patch_describe(monkeypatch, ["a", "b"])
        # A named key with no matching parameter is returned unchanged.
        result = _resolve_arg_param_names(MagicMock(), "db.sch.f", ["arg1", "arg2"])
        assert result == ["arg1", "arg2"]

    def test_positional_resolves_via_describe_function(self, monkeypatch):
        self._patch_describe(monkeypatch, ["a", "b"])
        result = _resolve_arg_param_names(MagicMock(), "db.sch.multiply", ["$1", "$2"])
        assert result == ["a", "b"]

    def test_mixed_positional_and_named(self, monkeypatch):
        self._patch_describe(monkeypatch, ["a", "b"])
        result = _resolve_arg_param_names(MagicMock(), "db.sch.f", ["$1", "b"])
        assert result == ["a", "b"]


class TestDispatchAndMapping:
    """End-to-end dispatch + mapping with the engine + optimizer mocked."""

    @pytest.fixture(autouse=True)
    def _install_fake_snowflake_module(self):
        fake_module = types.ModuleType("_snowflake")

        class SnowflakeUserException(Exception):
            pass

        fake_module.SnowflakeUserException = SnowflakeUserException
        self.SnowflakeUserException = SnowflakeUserException
        sys.modules["_snowflake"] = fake_module
        yield
        sys.modules.pop("_snowflake", None)

    @pytest.fixture
    def mocks(self, monkeypatch):
        calls: dict = {}

        def fake_evaluate(
            session,
            function_name,
            test_table,
            input_columns,
            label_column,
            metric_name,
            **kwargs,
        ):
            calls["evaluate"] = {
                "function_name": function_name,
                "test_table": test_table,
                "input_columns": input_columns,
                "label_column": label_column,
                "metric_name": metric_name,
                **kwargs,
            }
            return SimpleNamespace(score=0.5, details=[{}, {}], cost_measurement=None)

        def fake_save(session, experiment_name, **kwargs):
            calls["save"] = {"experiment_name": experiment_name, **kwargs}

        def fake_run_optimization(
            session,
            function_name,
            training_table,
            label_column,
            input_columns,
            metric_name,
            models,
            reflection_model,
            **kwargs,
        ):
            calls["run_optimization"] = {
                "function_name": function_name,
                "training_table": training_table,
                "label_column": label_column,
                "input_columns": input_columns,
                "metric_name": metric_name,
                "models": models,
                "reflection_model": reflection_model,
                **kwargs,
            }
            return {"best_model": models[0], "seed_run": "seed"}

        monkeypatch.setattr(handler, "evaluate", fake_evaluate)
        monkeypatch.setattr(handler, "save_evaluation_to_experiment", fake_save)
        monkeypatch.setattr(handler, "run_optimization", fake_run_optimization)
        return calls

    def test_dispatch_evaluation(self, mocks, monkeypatch):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp", "run_name": "r1"}, EVAL_SPEC
        )
        assert result["status"] == "SUCCEEDED"
        assert result["experiment"] == "db.sch.exp"
        assert result["run"] == "r1"
        assert result["metrics"] == {"exact_match": 0.5}
        assert "evaluate" in mocks and "run_optimization" not in mocks
        ev = mocks["evaluate"]
        assert ev["function_name"] == "db.sch.answer(VARCHAR, VARCHAR)"
        assert ev["test_table"] == "db.sch.qa"
        assert ev["input_columns"] == ["question_col", "context_col"]
        assert ev["label_column"] == "expected_col"
        # Lowercase argument_mapping keys resolve to the function's declared
        # (upper-cased) parameter names so the eval alias matches the inlined body.
        assert ev["input_arg_names"] == ["QUESTION", "CONTEXT"]
        # Eval path records run-level metrics only, no per-row eval_detail.json.
        assert mocks["save"]["upload_details"] is False

    def test_dispatch_optimization(self, mocks, monkeypatch):
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(arg_names=["Q"]),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp", "run_name": "r1"}, OPT_SPEC
        )
        assert result["status"] == "SUCCEEDED"
        assert result["experiment"] == "db.sch.exp"
        assert result["best_model"] == "mistral-7b"  # from run_optimization result
        assert "run_optimization" in mocks and "evaluate" not in mocks
        opt = mocks["run_optimization"]
        assert opt["function_name"] == "db.sch.answer(VARCHAR)"
        assert opt["training_table"] == "db.sch.train"
        assert opt["input_columns"] == ["q_col"]
        assert opt["label_column"] == "gt"
        # Lowercase key `q` resolves to the function's declared param `Q`.
        assert opt["input_arg_names"] == ["Q"]
        assert opt["metric_name"] == "exact_match"
        assert opt["models"] == ["mistral-7b"]
        assert opt["reflection_model"] == "mistral-7b"  # defaulted to models[0]
        assert opt["auto_budget"] == "demo"
        assert opt["optimize_mode"] == "body"
        assert opt["validation_fraction"] == 0.5
        assert opt["test_table"] == "db.sch.holdout"  # from dataset.holdout_data
        assert opt["experiment_name"] == "db.sch.exp"

    def test_dispatch_optimization_positional_mapping(self, mocks, monkeypatch):
        """Positional ($N) argument_mapping resolves to parameter names through the
        full handler dispatch (not just the resolver unit): $1/$2 -> the function's
        params, via DESCRIBE FUNCTION, then handed to the optimizer.
        """  # noqa: D205
        spec = (
            "function:\n"
            '  function_name: "db.sch.answer(VARCHAR, VARCHAR)"\n'
            "metrics:\n"
            "  - name: exact_match\n"
            "dataset:\n"
            "  name: db.sch.train\n"
            "  column_mapping:\n"
            "    argument_mapping:\n"
            "      $1: text_col\n"
            "      $2: lang_col\n"
            "    ground_truth: gt\n"
            "optimization:\n"
            "  models: [mistral-7b]\n"
            "  budget: demo\n"
            "  optimize_mode: body\n"
        )
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["sentence", "language"]
            ),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        opt = mocks["run_optimization"]
        # Columns preserve the mapping's values (index-aligned to the keys)...
        assert opt["input_columns"] == ["text_col", "lang_col"]
        # ...and the positional $1/$2 keys resolved to the function's params.
        assert opt["input_arg_names"] == ["sentence", "language"]

    def test_dispatch_optimization_mixed_positional_and_named(self, mocks, monkeypatch):
        """A mix of a named key and a positional $N key resolves correctly through
        dispatch, index-aligned with the mapped columns.
        """  # noqa: D205
        spec = (
            "function:\n"
            '  function_name: "db.sch.answer(VARCHAR, VARCHAR)"\n'
            "metrics:\n"
            "  - name: exact_match\n"
            "dataset:\n"
            "  name: db.sch.train\n"
            "  column_mapping:\n"
            "    argument_mapping:\n"
            "      sentence: text_col\n"
            "      $2: lang_col\n"
            "    ground_truth: gt\n"
            "optimization:\n"
            "  models: [mistral-7b]\n"
            "  budget: demo\n"
        )
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["sentence", "language"]
            ),
        )
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, spec
        )
        assert result["status"] == "SUCCEEDED"
        opt = mocks["run_optimization"]
        assert opt["input_columns"] == ["text_col", "lang_col"]
        assert opt["input_arg_names"] == ["sentence", "language"]

    def test_dispatch_neither_raises(self, mocks):
        spec = "function:\n  function_name: db.sch.f(VARCHAR)\nmetrics:\n  - name: exact_match\ndataset:\n  name: t\n  column_mapping:\n    argument_mapping: {a: c}\n    ground_truth: gt\n"
        with pytest.raises(
            self.SnowflakeUserException, match=r"evaluation.*optimization"
        ):
            execute_ai_function_eval_opts(MagicMock(), {"experiment_name": "e"}, spec)

    def test_missing_experiment_name_raises(self, mocks):
        with pytest.raises(
            self.SnowflakeUserException, match="experiment_name is required"
        ):
            execute_ai_function_eval_opts(MagicMock(), {}, EVAL_SPEC)

    def test_optimization_requires_models(self, mocks):
        spec = OPT_SPEC.replace("  models: [mistral-7b]\n", "")
        with pytest.raises(
            self.SnowflakeUserException, match="must be a non-empty list"
        ):
            execute_ai_function_eval_opts(MagicMock(), {"experiment_name": "e"}, spec)


class TestMultiEvalRuns:
    """``evaluation.num_eval_runs`` > 1 -> N parallel EVAL_1..EVAL_N runs."""

    @pytest.fixture(autouse=True)
    def _install_fake_snowflake_module(self):
        fake_module = types.ModuleType("_snowflake")

        class SnowflakeUserException(Exception):
            pass

        fake_module.SnowflakeUserException = SnowflakeUserException
        self.SnowflakeUserException = SnowflakeUserException
        sys.modules["_snowflake"] = fake_module
        yield
        sys.modules.pop("_snowflake", None)

    def _record_fakes(self, monkeypatch, *, evaluate_hook=None):
        """Install thread-safe recording fakes for evaluate + save.

        ``evaluate_hook(run_id)`` (if given) runs inside each fake ``evaluate``
        so tests can observe/synchronize concurrent execution.
        """
        lock = threading.Lock()
        calls: dict = {"evaluate": [], "save": []}

        def fake_evaluate(
            session,
            function_name,
            test_table,
            input_columns,
            label_column,
            metric_name,
            **kwargs,
        ):
            if evaluate_hook is not None:
                evaluate_hook(kwargs.get("run_id"))
            with lock:
                calls["evaluate"].append(
                    {
                        "function_name": function_name,
                        "metric_name": metric_name,
                        **kwargs,
                    }
                )
            return SimpleNamespace(score=0.5, details=[{}, {}], cost_measurement=None)

        def fake_save(session, experiment_name, **kwargs):
            with lock:
                calls["save"].append({"experiment_name": experiment_name, **kwargs})

        monkeypatch.setattr(handler, "evaluate", fake_evaluate)
        monkeypatch.setattr(handler, "save_evaluation_to_experiment", fake_save)
        # Argument-name resolution DESCRIBEs the function; return the EVAL_SPEC
        # function's params so resolution succeeds against a mock session.
        monkeypatch.setattr(
            handler,
            "describe_function",
            lambda session, function_name: SimpleNamespace(
                arg_names=["QUESTION", "CONTEXT"]
            ),
        )
        return calls

    def _spec(self, num_eval_runs: int) -> str:
        return EVAL_SPEC.replace(
            "  num_eval_runs: 1", f"  num_eval_runs: {num_eval_runs}"
        )

    def test_creates_eval_1_to_n_runs(self, monkeypatch):
        calls = self._record_fakes(monkeypatch)
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(4)
        )

        assert result["status"] == "SUCCEEDED"
        assert result["experiment"] == "db.sch.exp"
        # Runs are reported deterministically as EVAL_1..EVAL_N.
        assert result["runs"] == ["EVAL_1", "EVAL_2", "EVAL_3", "EVAL_4"]
        # Multi-run uses the "runs" list, not the single-run "run" key.
        assert "run" not in result
        assert result["metrics"] == {
            "EVAL_1": {"exact_match": 0.5},
            "EVAL_2": {"exact_match": 0.5},
            "EVAL_3": {"exact_match": 0.5},
            "EVAL_4": {"exact_match": 0.5},
        }
        assert result["num_examples"] == 2

        # One evaluate + one save per run, each carrying its own EVAL_i run name.
        assert len(calls["evaluate"]) == 4
        assert len(calls["save"]) == 4
        assert {c["run_id"] for c in calls["evaluate"]} == {
            "EVAL_1",
            "EVAL_2",
            "EVAL_3",
            "EVAL_4",
        }
        assert {c["run_name"] for c in calls["save"]} == {
            "EVAL_1",
            "EVAL_2",
            "EVAL_3",
            "EVAL_4",
        }
        # Eval path still records run-level metrics only.
        assert all(c["upload_details"] is False for c in calls["save"])

    @pytest.mark.parametrize("num_runs, expected_workers", [(5, 3), (2, 2)])
    def test_parallelism_worker_count(self, monkeypatch, num_runs, expected_workers):
        # Capture max_workers while still driving the real ThreadPoolExecutor:
        # capped at 3, but never more than the number of runs requested.
        captured: dict = {}
        real_tpe = handler.ThreadPoolExecutor

        def spy_tpe(*args, **kwargs):
            captured["max_workers"] = kwargs.get(
                "max_workers", args[0] if args else None
            )
            return real_tpe(*args, **kwargs)

        monkeypatch.setattr(handler, "ThreadPoolExecutor", spy_tpe)
        self._record_fakes(monkeypatch)

        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(num_runs)
        )
        assert captured["max_workers"] == expected_workers
        assert result["runs"] == [f"EVAL_{i}" for i in range(1, num_runs + 1)]

    def test_runs_execute_concurrently(self, monkeypatch):
        # Barrier of 3 only releases once three workers are in-flight together,
        # deterministically proving >=3 concurrent runs (and, with the worker
        # cap, exactly 3). 6 runs = two clean groups of 3.
        barrier = threading.Barrier(3)
        lock = threading.Lock()
        state = {"current": 0, "peak": 0}

        def hook(_run_id):
            with lock:
                state["current"] += 1
                state["peak"] = max(state["peak"], state["current"])
            barrier.wait(timeout=10)
            with lock:
                state["current"] -= 1

        self._record_fakes(monkeypatch, evaluate_hook=hook)
        result = execute_ai_function_eval_opts(
            MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(6)
        )
        assert result["runs"] == [f"EVAL_{i}" for i in range(1, 7)]
        # Peak concurrency reaches the cap but never exceeds it.
        assert state["peak"] == 3

    def test_num_eval_runs_one_is_single_run(self, monkeypatch):
        # Default (1) keeps the legacy single-run shape + caller-provided name.
        calls = self._record_fakes(monkeypatch)
        result = execute_ai_function_eval_opts(
            MagicMock(),
            {"experiment_name": "db.sch.exp", "run_name": "r1"},
            self._spec(1),
        )
        assert result["run"] == "r1"
        assert "runs" not in result
        assert result["metrics"] == {"exact_match": 0.5}
        assert len(calls["evaluate"]) == 1
        assert calls["evaluate"][0]["run_id"] == "r1"

    @pytest.mark.parametrize("bad", [0, -1])
    def test_invalid_num_eval_runs_surface_error(self, monkeypatch, bad):
        self._record_fakes(monkeypatch)
        with pytest.raises(self.SnowflakeUserException, match="positive integer"):
            execute_ai_function_eval_opts(
                MagicMock(), {"experiment_name": "db.sch.exp"}, self._spec(bad)
            )

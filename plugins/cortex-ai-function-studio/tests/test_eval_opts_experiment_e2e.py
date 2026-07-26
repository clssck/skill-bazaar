# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""End-to-end coverage for spec-driven evaluation across many YAML input types.

Drives ``EXECUTE_AI_FUNCTION_EVAL_OPTS`` with 10 different evaluation SPEC
YAMLs (a matrix over metric, named vs positional ``$N`` argument mapping,
``metrics`` as list vs mapping, and ``num_eval_runs``), reads each generated
experiment back into a ``{experiment: {run: {metrics, parameters, metadata}}}``
tree, displays it (volatile values redacted), and asserts the tree's structure
and invariants — including that ``num_eval_runs`` > 1 yields EVAL_1..EVAL_N.

Run::

    uv run --group test pytest tests/test_eval_opts_experiment_e2e.py \
        -v -m e2e --connection sfctest-udaif
"""

from __future__ import annotations

import json

import pytest
import yaml

from handlers.execute_eval_opts_handler import (
    _EVAL_RUN_NAME_PREFIX,
    execute_ai_function_eval_opts,
)
from snowflake_ai_optimize.core.udf_ddl import generate_sql
from snowflake_ai_optimize.core.udf_types import InputParam, OutputField, UDFSpec

_INPUT_COLUMN = "TEXT"
_GROUND_TRUTH_COLUMN = "EXPECTED_LABEL"

# ---------------------------------------------------------------------------
# The 10 evaluation SPEC input types
# ---------------------------------------------------------------------------
# Each config is one distinct YAML shape. ``metric`` is the spec metric name;
# ``metric_engine`` is the canonical name recorded as the run's ``metric_name``
# parameter (``llm-judge`` normalizes to ``llm_judge``).
EVAL_SPEC_CONFIGS: list[dict] = [
    {
        "label": "exact_match / named / list / single",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "exact_match / named / mapping / 2 runs",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "named",
        "metrics_as_mapping": True,
        "num_eval_runs": 2,
    },
    {
        "label": "fuzzy_match / named / list / single",
        "metric": "fuzzy_match",
        "metric_engine": "fuzzy_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "fuzzy_match / positional / list / 3 runs",
        "metric": "fuzzy_match",
        "metric_engine": "fuzzy_match",
        "arg_kind": "positional",
        "metrics_as_mapping": False,
        "num_eval_runs": 3,
    },
    {
        "label": "contains_match / named / list / single",
        "metric": "contains_match",
        "metric_engine": "contains_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 1,
    },
    {
        "label": "contains_match / named / list / 2 runs",
        "metric": "contains_match",
        "metric_engine": "contains_match",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "num_eval_runs": 2,
    },
    {
        "label": "exact_match / positional / list / 5 runs",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "positional",
        "metrics_as_mapping": False,
        # 5 > max parallelism (3): exercises the bounded thread pool live.
        "num_eval_runs": 5,
    },
    {
        "label": "exact_match / positional / mapping / single",
        "metric": "exact_match",
        "metric_engine": "exact_match",
        "arg_kind": "positional",
        "metrics_as_mapping": True,
        "num_eval_runs": 1,
    },
    {
        "label": "llm-judge / named / list / judge_model / single",
        "metric": "llm-judge",
        "metric_engine": "llm_judge",
        "arg_kind": "named",
        "metrics_as_mapping": False,
        "judge_model": "llama3.1-8b",
        "num_eval_runs": 1,
    },
    {
        "label": "llm-judge / named / mapping / judge_model / 2 runs",
        "metric": "llm-judge",
        "metric_engine": "llm_judge",
        "arg_kind": "named",
        "metrics_as_mapping": True,
        "judge_model": "llama3.1-8b",
        "num_eval_runs": 2,
    },
]

# Single-run specs record this run name (multi-run specs use EVAL_1..EVAL_N).
_SINGLE_RUN_NAME = "EVAL"


def _argument_mapping(arg_kind: str) -> dict[str, str]:
    """Build the dataset argument_mapping for a named or positional spec."""
    if arg_kind == "positional":
        return {"$1": _INPUT_COLUMN}
    return {_INPUT_COLUMN: _INPUT_COLUMN}


def build_eval_spec(config: dict, *, function_signature: str, table: str) -> str:
    """Render one evaluation SPEC config to inline YAML text."""
    metric_entry: dict = {"name": config["metric"]}
    if config.get("judge_model") is not None:
        metric_entry["judge_model"] = config["judge_model"]

    spec = {
        "function": {"function_name": function_signature},
        "metrics": metric_entry if config["metrics_as_mapping"] else [metric_entry],
        "dataset": {
            "name": table,
            "column_mapping": {
                "argument_mapping": _argument_mapping(config["arg_kind"]),
                "ground_truth": _GROUND_TRUTH_COLUMN,
            },
        },
        "evaluation": {"num_eval_runs": config["num_eval_runs"]},
    }
    return yaml.safe_dump(spec, sort_keys=False)


def expected_run_names(config: dict) -> list[str]:
    """Return the run names a spec should produce, in deterministic order."""
    num_eval_runs = config["num_eval_runs"]
    if num_eval_runs <= 1:
        return [_SINGLE_RUN_NAME]
    return [f"{_EVAL_RUN_NAME_PREFIX}_{i}" for i in range(1, num_eval_runs + 1)]


def build_experiment_tree(session, experiment_name: str) -> dict:
    """Read an experiment's runs into a per-run metrics/parameters/metadata map."""

    def to_number(value: object) -> float | str | None:
        if value is None:
            return None
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return str(value)

    tree: dict = {}
    runs = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    for run in runs:
        run_name = run["name"]
        # SHOW RUNS metadata is external data; tolerate a malformed field.
        try:
            metadata = json.loads(run["metadata"]) if run["metadata"] else {}
        except (json.JSONDecodeError, TypeError):
            metadata = {}

        metric_rows = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        metrics = {m["name"]: to_number(m["value"]) for m in metric_rows}

        param_rows = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {run_name}"
        ).collect()
        parameters = {
            p["name"]: (None if p["value"] is None else str(p["value"]))
            for p in param_rows
        }

        tree[run_name] = {
            "metrics": metrics,
            "parameters": parameters,
            "metadata": metadata,
        }
    return tree


# ---------------------------------------------------------------------------
# Display normalization (redact nondeterministic values to stable tokens)
# ---------------------------------------------------------------------------
_NUMBER_TOKEN = "<number>"
_REDACTED_TOKEN = "<redacted>"
_STABLE_METADATA_KEYS = {"status"}
# Parameter names whose values vary run-to-run (timings, token/char counts).
_VOLATILE_PARAM_SUFFIXES = (
    "_seconds",
    "_tokens",
    "_chars",
    "_dollars",
    "_calls",
    "_count",
)


def normalize_tree_for_display(tree: dict) -> dict:
    """Return a copy of the tree with nondeterministic values redacted.

    Metric values become ``<number>``, volatile parameters and non-status
    metadata become ``<redacted>``. The result depends only on the tree's
    *shape and deterministic fields*, so it is identical across runs that
    differ solely in scores/timings/timestamps.
    """
    display: dict = {}
    for experiment_name, runs in tree.items():
        display[experiment_name] = {}
        for run_name, body in runs.items():
            metrics = dict.fromkeys(body.get("metrics", {}), _NUMBER_TOKEN)
            parameters = {
                name: (
                    _REDACTED_TOKEN
                    if name.endswith(_VOLATILE_PARAM_SUFFIXES)
                    else value
                )
                for name, value in body.get("parameters", {}).items()
            }
            metadata = {
                key: (value if key in _STABLE_METADATA_KEYS else _REDACTED_TOKEN)
                for key, value in body.get("metadata", {}).items()
            }
            display[experiment_name][run_name] = {
                "metrics": metrics,
                "parameters": parameters,
                "metadata": metadata,
            }
    return display


# ---------------------------------------------------------------------------
# Deterministic (offline) tests for the config matrix + display normalizer
# ---------------------------------------------------------------------------


def _fake_run_body(
    *,
    score: float,
    elapsed: float,
    created_on: str = "2026-07-10T00:00:00Z",
    estimated_cost: float | None = None,
) -> dict:
    """Build a run body matching what the eval path records (for offline tests)."""
    metrics: dict = {"score": score}
    if estimated_cost is not None:
        metrics["estimated_cost"] = estimated_cost
    return {
        "metrics": metrics,
        "parameters": {
            "function_impl": "",
            "model": "llama3.1-8b",
            "iteration": "0",
            "is_full_eval": "true",
            "status": "completed",
            "function_name": "db.sch.f(VARCHAR)",
            "metric_name": "exact_match",
            "custom_metric_udf": "",
            "num_examples": "4",
            "elapsed_seconds": str(elapsed),
        },
        "metadata": {"status": "FINISHED", "created_on": created_on},
    }


def _fake_tree(score: float, elapsed: float, created_on: str, cost: float) -> dict:
    """A representative two-experiment tree (single-run + multi-run)."""
    return {
        "db.sch.EXP_1": {
            "EVAL": _fake_run_body(score=score, elapsed=elapsed, created_on=created_on)
        },
        "db.sch.EXP_2": {
            "EVAL_1": _fake_run_body(
                score=score, elapsed=elapsed, created_on=created_on, estimated_cost=cost
            ),
            "EVAL_2": _fake_run_body(
                score=score, elapsed=elapsed, created_on=created_on, estimated_cost=cost
            ),
        },
    }


class TestTreeHelpers:
    """Offline checks for the config matrix and the display normalizer."""

    def test_configs_cover_ten_input_types(self):
        assert len(EVAL_SPEC_CONFIGS) == 10
        # Every config renders to parseable YAML with the required sections.
        for config in EVAL_SPEC_CONFIGS:
            spec_text = build_eval_spec(
                config, function_signature="db.sch.f(VARCHAR)", table="db.sch.t"
            )
            spec = yaml.safe_load(spec_text)
            assert "evaluation" in spec and "function" in spec and "dataset" in spec
            assert spec["evaluation"]["num_eval_runs"] == config["num_eval_runs"]

    def test_normalizer_stable_across_nondeterministic_values(self):
        # Two trees differing ONLY in nondeterministic values normalize to the
        # identical display — the robustness guarantee.
        tree_a = _fake_tree(0.5, 1.23, "2026-07-10T00:00:00Z", 0.001)
        tree_b = _fake_tree(0.875, 42.9, "2026-12-31T23:59:59Z", 0.99)
        assert normalize_tree_for_display(tree_a) == normalize_tree_for_display(tree_b)

    def test_normalizer_redacts_volatile_but_keeps_deterministic(self):
        display = normalize_tree_for_display(
            _fake_tree(0.5, 1.23, "2026-07-10T00:00:00Z", 0.001)
        )
        run = display["db.sch.EXP_1"]["EVAL"]
        assert run["metrics"]["score"] == _NUMBER_TOKEN
        assert run["parameters"]["elapsed_seconds"] == _REDACTED_TOKEN
        # deterministic fields survive redaction
        assert run["parameters"]["metric_name"] == "exact_match"
        assert run["parameters"]["model"] == "llama3.1-8b"
        assert run["parameters"]["num_examples"] == "4"
        assert run["metadata"]["status"] == "FINISHED"
        assert run["metadata"]["created_on"] == _REDACTED_TOKEN


# ---------------------------------------------------------------------------
# Live end-to-end test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def eval_env(session, cleanup_stale, run_key):
    """Provision a classifier UDF + labeled dataset; drop everything after."""
    db = session.get_current_database().strip('"')
    schema = session.get_current_schema().strip('"')

    def fq(name: str) -> str:
        return f"{db}.{schema}.{name}"

    cleanup_stale(
        session,
        db,
        schema,
        tables=["TEST_EVALOPTS_DATA"],
        functions=["TEST_EVALOPTS_CLASSIFY"],
        experiments=["TEST_EVALOPTS_EXP"],
    )

    func = f"TEST_EVALOPTS_CLASSIFY_{run_key}"
    table = f"TEST_EVALOPTS_DATA_{run_key}"
    func_fqn = fq(func)
    table_fqn = fq(table)

    udf_spec = UDFSpec(
        database=db,
        schema=schema,
        function_name=func,
        model="llama3.1-8b",
        function_intention="Classify text sentiment as positive or negative",
        inputs=[InputParam(name=_INPUT_COLUMN, sql_type="VARCHAR")],
        outputs=[
            OutputField(
                name="label", json_type="string", description="positive or negative"
            )
        ],
        system_prompt=(
            "Classify the sentiment of the text as positive or negative. "
            "Answer with exactly 'positive' or 'negative'."
        ),
        user_prompt_template="{TEXT}",
    )
    session.sql(generate_sql(udf_spec)).collect()

    session.sql(
        f"CREATE OR REPLACE TABLE {table_fqn} "
        f"({_INPUT_COLUMN} VARCHAR, {_GROUND_TRUTH_COLUMN} VARCHAR)"
    ).collect()
    rows = [
        ("I love this product!", "positive"),
        ("Great experience overall", "positive"),
        ("Terrible, worst purchase ever", "negative"),
        ("Awful quality and bad service", "negative"),
    ]
    values = ", ".join(f"('{text}', '{label}')" for text, label in rows)
    session.sql(f"INSERT INTO {table_fqn} VALUES {values}").collect()

    experiment_names = [
        fq(f"TEST_EVALOPTS_EXP_{run_key}_{i}")
        for i in range(1, len(EVAL_SPEC_CONFIGS) + 1)
    ]

    yield {
        "function_signature": f"{func_fqn}(VARCHAR)",
        "table": table_fqn,
        "row_count": len(rows),
        "experiment_names": experiment_names,
    }

    session.sql(f"DROP FUNCTION IF EXISTS {func_fqn}(VARCHAR)").collect()
    session.sql(f"DROP TABLE IF EXISTS {table_fqn}").collect()
    for experiment_name in experiment_names:
        session.sql(f"DROP EXPERIMENT IF EXISTS {experiment_name}").collect()


@pytest.mark.e2e
class TestEvalOptsExperimentsE2E:
    """Run 10 eval SPEC types, build the experiment tree, and validate it."""

    def test_ten_eval_specs_build_valid_experiment_tree(self, session, eval_env):
        function_signature = eval_env["function_signature"]
        table = eval_env["table"]
        row_count = eval_env["row_count"]
        experiment_names = eval_env["experiment_names"]

        tree: dict = {}
        for config, experiment_name in zip(
            EVAL_SPEC_CONFIGS, experiment_names, strict=True
        ):
            spec_text = build_eval_spec(
                config, function_signature=function_signature, table=table
            )
            params: dict = {"experiment_name": experiment_name}
            if config["num_eval_runs"] <= 1:
                params["run_name"] = _SINGLE_RUN_NAME

            result = execute_ai_function_eval_opts(session, params, spec_text)
            assert result["status"] == "SUCCEEDED", (
                f"{config['label']} did not succeed: {result}"
            )

            # The handler's own report of which runs it created.
            if config["num_eval_runs"] <= 1:
                assert result["run"] == _SINGLE_RUN_NAME
            else:
                assert result["runs"] == expected_run_names(config), (
                    f"{config['label']} run names mismatch: {result.get('runs')}"
                )

            tree[experiment_name] = build_experiment_tree(session, experiment_name)

        # ---- Display the generated experiment tree (stable / redacted) ----
        print(
            "\nGenerated experiment tree (nondeterministic values redacted):\n"
            + json.dumps(normalize_tree_for_display(tree), indent=2, sort_keys=True)
        )

        # ---- Per-spec structural + invariant assertions ----
        assert len(tree) == len(EVAL_SPEC_CONFIGS)
        for config, experiment_name in zip(
            EVAL_SPEC_CONFIGS, experiment_names, strict=True
        ):
            runs = tree[experiment_name]
            assert set(runs) == set(expected_run_names(config)), (
                f"{config['label']} produced runs {sorted(runs)}, "
                f"expected {expected_run_names(config)}"
            )
            for run_name, body in runs.items():
                params = body["parameters"]
                assert body["metadata"]["status"] == "FINISHED", (
                    f"{config['label']} run {run_name} not committed"
                )
                assert params["status"] == "completed"
                assert params["metric_name"] == config["metric_engine"]
                assert params["num_examples"] == str(row_count)
                assert params["model"], (
                    f"{config['label']} run {run_name} missing model"
                )
                assert params["function_name"] == function_signature
                assert "iteration" in params
                score = body["metrics"]["score"]
                assert score is not None and 0.0 <= float(score) <= 1.0, (
                    f"{config['label']} run {run_name} score out of range: {score}"
                )

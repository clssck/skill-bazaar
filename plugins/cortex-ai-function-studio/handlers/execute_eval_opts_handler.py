# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""SPROC entry point for EXECUTE_AI_FUNCTION_EVAL_OPTS.

A single spec-driven entry point that runs **either** an evaluation **or** an
optimization job, dispatching on the input SPECIFICATION's top-level marker
section — matching the canonical experiment-spec JSON Schemas (both share
``function`` / ``metrics`` / ``dataset``; the eval spec adds a required
``evaluation`` section, the opt spec adds a required ``optimization`` section):

* ``evaluation`` present   -> evaluation  (score the function; run-level metrics)
* ``optimization`` present -> optimization (GEPA optimize the function)

The SPEC YAML text is passed in as ``specification`` (``EXECUTE EXPERIMENT``
supplies it; the procedure does not read the experiment object itself). Bundled
into the ``caifs_eval_opts`` module (built from the optimize source set, a
superset that includes the eval engine + GEPA), so the SPROC handler is
``caifs_eval_opts.execute_ai_function_eval_opts``.
"""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import yaml
from snowflake.snowpark import Session

# run_optimization lives in the same concatenated bundle (optimize source set).
from handlers.optimize_handler import run_optimization
from snowflake_ai_optimize.core.evaluation import evaluate
from snowflake_ai_optimize.core.experiment import save_evaluation_to_experiment
from snowflake_ai_optimize.core.metrics.llm_judge import LLM_JUDGE_DEFAULT_MODEL
from snowflake_ai_optimize.core.sproc_decorators import (
    surface_sproc_error,
    with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc,
    with_custom_ai_function_query_tag,
)
from snowflake_ai_optimize.core.sql_utils import (
    describe_function,
    resolve_param_name,
)

# Metric names whose spec key differs from the engine's canonical name.
_METRIC_NAME_NORMALIZE = {"llm-judge": "llm_judge"}

# Cap concurrent eval fan-out (num_eval_runs > 1) to protect the account.
_MAX_EVAL_PARALLELISM = 3

# Run-name prefix for the num_eval_runs > 1 fan-out: EVAL_1 .. EVAL_N.
_EVAL_RUN_NAME_PREFIX = "EVAL"


def _parse_specification(specification: str) -> dict:
    """Parse the SPEC (inline YAML text) into a dict.

    Raises ValueError on empty / non-mapping specs so the SPROC surfaces a
    clear error instead of a downstream ``NoneType`` failure.
    """
    if not specification or not specification.strip():
        raise ValueError("specification is required and cannot be empty")
    try:
        spec = yaml.safe_load(specification)
    except yaml.YAMLError as exc:
        raise ValueError(f"specification is not valid YAML: {exc}") from exc
    if not isinstance(spec, dict):
        raise ValueError("specification must be a YAML mapping")
    return spec


def _first_metric(spec: dict) -> dict:
    """Return the first eval/opt metric mapping from the SPEC.

    Accepts either a ``metrics:`` list (uses the first entry) or a single
    ``metrics:`` mapping.
    """
    metrics = spec.get("metrics")
    if isinstance(metrics, dict):
        return metrics
    if isinstance(metrics, list) and metrics:
        first = metrics[0]
        if not isinstance(first, dict):
            raise ValueError("each metrics entry must be a mapping")
        return first
    raise ValueError("specification.metrics is required (a metric with a 'name')")


def _resolve_function_name(spec: dict) -> str:
    """Extract the user AI function signature from the SPEC.

    Per the spec schema a function is identified by exactly one of
    ``function_name`` or ``query_text``. Only ``function_name`` (a user AI
    function) is supported today; ``query_text`` is not yet supported by the
    engine and is rejected with a clear message.
    """
    function = spec.get("function")
    if not isinstance(function, dict):
        raise ValueError("specification.function is required")

    function_name = function.get("function_name")
    if function.get("query_text") and not function_name:
        raise ValueError(
            "Builtin AI function evaluation (query_text) is not yet supported; "
            "provide a user AI function via function.function_name"
        )
    if not function_name:
        raise ValueError("specification.function.function_name is required")
    return str(function_name)


def _resolve_dataset(spec: dict) -> tuple[str, list, str, list]:
    """Resolve (table, input_columns, label_column, arg_keys) from the dataset.

    ``input_columns`` are the dataset column names (the ``argument_mapping``
    values); ``arg_keys`` are the corresponding keys (a parameter name, or a
    positional marker ``$N``), aligned by index. The evaluation engine (incl.
    llm_judge, which grades predicted vs. expected) and the optimizer both
    require a ground-truth column, so ``ground_truth`` is required.
    """
    dataset = spec.get("dataset")
    if not isinstance(dataset, dict):
        raise ValueError("specification.dataset is required (a mapping with 'name')")
    table = dataset.get("name")
    if not table:
        raise ValueError("specification.dataset.name is required")
    column_mapping = dataset.get("column_mapping") or {}
    argument_mapping = column_mapping.get("argument_mapping") or {}
    if not argument_mapping:
        raise ValueError(
            "specification.dataset.column_mapping.argument_mapping is required"
        )
    # Keys (parameter name or "$N") and values (columns) are index-aligned.
    arg_keys = list(argument_mapping.keys())
    input_columns = list(argument_mapping.values())
    ground_truth = column_mapping.get("ground_truth")
    if not ground_truth:
        raise ValueError(
            "specification.dataset.column_mapping.ground_truth is required "
            "(reference-free scoring is not yet supported)"
        )
    return str(table), input_columns, str(ground_truth), arg_keys


def _resolve_arg_param_names(
    session: Session, function_name: str, arg_keys: list
) -> list[str]:
    """Map ``argument_mapping`` keys to AI-function parameter names.

    Each key is resolved against the function's actual parameters, read via
    ``describe_function`` (which resolves the name — with or without an overload
    signature — through ``SHOW FUNCTIONS``, so a bare ``DB.SCHEMA.FUNC`` works):
    a positional ``$N`` key resolves to the Nth parameter, and a named key is
    matched case-insensitively to a declared parameter and resolved to the DDL's
    exact casing. This matters because the eval engine aliases each dataset
    column to the resolved name (``col AS <name>``) while the inlined UDF body
    references parameters by their declared, typically upper-cased, names — a
    case mismatch (e.g. mapping key ``text`` vs. parameter ``TEXT``) would
    otherwise yield ``invalid identifier``. A named key with no matching
    parameter falls back to itself.
    """
    keys = [str(k) for k in arg_keys]
    param_names = describe_function(session, function_name).arg_names
    return [resolve_param_name(k, param_names) for k in keys]


def _resolve_metric(metric: dict) -> tuple[str, str | None, str, dict[str, Any]]:
    """Resolve (metric_name, custom_udf, judge_model, metric_options)."""
    raw_metric_name = metric.get("name")
    if not raw_metric_name:
        raise ValueError("specification.metrics[].name is required")
    metric_name = _METRIC_NAME_NORMALIZE.get(raw_metric_name, raw_metric_name)

    custom_metric_udf = metric.get("custom_udf")
    if metric_name == "custom" and not custom_metric_udf:
        raise ValueError("metrics.custom_udf is required when metric name is 'custom'")

    judge_model = metric.get("judge_model") or LLM_JUDGE_DEFAULT_MODEL
    metric_options: dict[str, Any] = {}
    if metric.get("aggregation"):
        metric_options["aggregation"] = metric["aggregation"]
    return metric_name, custom_metric_udf, judge_model, metric_options


def _resolve_num_eval_runs(spec: dict) -> int:
    """Resolve ``evaluation.num_eval_runs`` (how many eval runs to execute).

    Defaults to 1 when omitted. Must be a positive integer; anything else
    (including a boolean, a float, or a non-numeric string) is rejected with a
    clear error rather than silently coerced.
    """
    evaluation = spec.get("evaluation")
    raw = evaluation.get("num_eval_runs") if isinstance(evaluation, dict) else None
    if raw is None:
        return 1
    # bool is an int subclass, so reject it before the int check (True -> 1).
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise ValueError(
            "specification.evaluation.num_eval_runs must be a positive integer"
        )
    return raw


@surface_sproc_error()
@with_ai_sql_error_handling_use_fail_on_error_disabled_for_sproc()
@with_custom_ai_function_query_tag("SPROC_EXECUTE_AI_FUNCTION_EVAL_OPTS")
def execute_ai_function_eval_opts(
    session: Session,
    evaluation_params: dict,
    specification: str,
) -> dict:
    """SPROC entry point for ``EXECUTE_AI_FUNCTION_EVAL_OPTS``.

    Dispatches on the SPEC's top-level marker section: ``evaluation`` -> run an
    evaluation job; ``optimization`` -> run an optimization job.

    Args:
        session: Caller's-rights Snowpark session.
        evaluation_params: OBJECT carrying ``experiment_name`` (required) and an
            optional ``run_name``.
        specification: eval or opt SPEC as inline YAML text.

    Returns:
        VARIANT with ``experiment`` + ``status`` plus the job's result
        (eval: ``run``/``metrics``; opt: the optimization result).
    """
    if not isinstance(evaluation_params, dict):
        raise ValueError("evaluation_params must be an OBJECT")
    experiment_name = evaluation_params.get("experiment_name")
    if not experiment_name or not str(experiment_name).strip():
        raise ValueError("evaluation_params.experiment_name is required")
    experiment_name = str(experiment_name)

    spec = _parse_specification(specification)

    if "evaluation" in spec:
        return _run_evaluation(session, experiment_name, evaluation_params, spec)
    if "optimization" in spec:
        return _run_optimization(session, experiment_name, evaluation_params, spec)
    raise ValueError(
        "specification must contain a top-level 'evaluation' or 'optimization' section"
    )


def _run_evaluation(
    session: Session, experiment_name: str, evaluation_params: dict, spec: dict
) -> dict:
    """Score the function; single run or EVAL_1..EVAL_N per ``num_eval_runs``."""
    function_name = _resolve_function_name(spec)
    test_table, input_columns, label_column, arg_keys = _resolve_dataset(spec)
    input_arg_names = _resolve_arg_param_names(session, function_name, arg_keys)
    metric_name, custom_metric_udf, model_name, metric_options = _resolve_metric(
        _first_metric(spec)
    )
    num_eval_runs = _resolve_num_eval_runs(spec)

    eval_kwargs: dict[str, Any] = {
        "function_name": function_name,
        "test_table": test_table,
        "input_columns": input_columns,
        "label_column": label_column,
        "metric_name": metric_name,
        "model_name": model_name,
        "metric_options": metric_options,
        "custom_metric_udf": custom_metric_udf,
        "input_arg_names": input_arg_names,
    }

    # Single-run keeps the caller-provided run name and the pre-existing (flat)
    # return shape that EXECUTE EXPERIMENT callers already depend on.
    if num_eval_runs <= 1:
        run_name = str(
            evaluation_params.get("run_name") or f"run_{int(time.time() * 1000)}"
        )
        outcome = _evaluate_and_save(session, experiment_name, run_name, **eval_kwargs)
        return {
            "experiment": experiment_name,
            "run": run_name,
            "status": "SUCCEEDED",
            "metrics": {metric_name: outcome["score"]},
            "num_examples": outcome["num_examples"],
        }

    run_names = [f"{_EVAL_RUN_NAME_PREFIX}_{i}" for i in range(1, num_eval_runs + 1)]
    outcomes: dict[str, dict[str, Any]] = {}
    max_workers = min(_MAX_EVAL_PARALLELISM, num_eval_runs)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_run = {
            executor.submit(
                _evaluate_and_save, session, experiment_name, run_name, **eval_kwargs
            ): run_name
            for run_name in run_names
        }
        for future in as_completed(future_to_run):
            run_name = future_to_run[future]
            # Re-raises any per-run failure so the SPROC surfaces a clear error.
            outcomes[run_name] = future.result()

    return {
        "experiment": experiment_name,
        "runs": run_names,
        "status": "SUCCEEDED",
        "metrics": {rn: {metric_name: outcomes[rn]["score"]} for rn in run_names},
        "num_examples": outcomes[run_names[0]]["num_examples"],
    }


def _evaluate_and_save(
    session: Session,
    experiment_name: str,
    run_name: str,
    *,
    function_name: str,
    test_table: str,
    input_columns: list,
    label_column: str,
    metric_name: str,
    model_name: str,
    metric_options: dict[str, Any],
    custom_metric_udf: str | None,
    input_arg_names: list[str],
) -> dict[str, Any]:
    """Run one evaluation and persist it as a single experiment run."""
    start_time = time.time()
    result = evaluate(
        session,
        function_name,
        test_table,
        input_columns,
        label_column,
        metric_name,
        model_name=model_name,
        metric_options=metric_options or None,
        custom_metric_udf=custom_metric_udf,
        run_id=run_name,
        input_arg_names=input_arg_names,
    )
    elapsed = time.time() - start_time

    save_evaluation_to_experiment(
        session,
        experiment_name,
        function_name=function_name,
        metric_name=metric_name,
        model_name=model_name,
        score=result.score,
        num_examples=len(result.details),
        eval_details=result.details,
        run_name=run_name,
        custom_metric_udf=custom_metric_udf or "",
        elapsed_seconds=elapsed,
        cost_info=result.cost_measurement,
        # Run-level metrics only; per-row eval_detail.json artifact is out of scope.
        upload_details=False,
    )

    return {
        "run": run_name,
        "score": result.score,
        "num_examples": len(result.details),
    }


def _run_optimization(
    session: Session, experiment_name: str, evaluation_params: dict, spec: dict
) -> dict:
    """Optimization path: GEPA-optimize the function against the dataset."""
    optimization = spec.get("optimization")
    if not isinstance(optimization, dict):
        raise ValueError("specification.optimization must be a mapping")
    models = optimization.get("models")
    if not isinstance(models, list) or not models:
        raise ValueError("specification.optimization.models must be a non-empty list")

    function_name = _resolve_function_name(spec)
    training_table, input_columns, label_column, arg_keys = _resolve_dataset(spec)
    input_arg_names = _resolve_arg_param_names(session, function_name, arg_keys)
    metric_name, custom_metric_udf, _judge_model, metric_options = _resolve_metric(
        _first_metric(spec)
    )

    # reflection_model is required by run_optimization; default to the first model.
    reflection_model = optimization.get("reflection_model") or models[0]
    dataset = spec.get("dataset") or {}
    holdout = dataset.get("holdout_data")
    run_id = evaluation_params.get("run_name") or f"run_{int(time.time() * 1000)}"

    # Only pass optional knobs when present so run_optimization defaults apply.
    opt_kwargs: dict[str, Any] = {
        "test_table": str(holdout) if holdout else None,
        "metric_options": metric_options or None,
        "custom_metric_udf": custom_metric_udf,
        "run_id": str(run_id),
        "experiment_name": experiment_name,
        "input_arg_names": input_arg_names,
    }
    if optimization.get("budget"):
        opt_kwargs["auto_budget"] = optimization["budget"]
    if optimization.get("validation_fraction") is not None:
        opt_kwargs["validation_fraction"] = optimization["validation_fraction"]
    if optimization.get("optimize_mode"):
        opt_kwargs["optimize_mode"] = optimization["optimize_mode"]
    if optimization.get("temperature") is not None:
        opt_kwargs["temperature"] = optimization["temperature"]
    if optimization.get("max_tokens") is not None:
        opt_kwargs["max_tokens"] = optimization["max_tokens"]
    if optimization.get("aggregation_metric"):
        opt_kwargs["aggregation_metric"] = optimization["aggregation_metric"]

    result = run_optimization(
        session,
        function_name,
        training_table,
        label_column,
        input_columns,
        metric_name,
        models,
        reflection_model,
        **opt_kwargs,
    )

    out: dict[str, Any] = (
        dict(result) if isinstance(result, dict) else {"result": result}
    )
    out["experiment"] = experiment_name
    out["status"] = "SUCCEEDED"
    return out

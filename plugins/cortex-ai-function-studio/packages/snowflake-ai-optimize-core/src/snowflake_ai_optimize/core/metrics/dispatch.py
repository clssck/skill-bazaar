# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Metric dispatch — routes metric names to their implementations.

Changes when metrics are added or removed from the system.
"""

from collections.abc import Callable
from typing import Any

from snowflake.snowpark import Session

from snowflake_ai_optimize.core.metrics.builtin import (
    contains_match_core,
    exact_match_core,
    fuzzy_match_core,
    redaction_match_core,
)
from snowflake_ai_optimize.core.metrics.custom_udf import (
    call_custom_metric_udf,
    call_custom_metric_udf_batch,
)
from snowflake_ai_optimize.core.metrics.llm_judge import (
    llm_judge_batch,
    llm_judge_core,
)

PredictionExecutor = Callable[[list[dict[str, object]]], list[object]]


def compute_metric(
    metric_name: str,
    expected: str,
    predicted: str,
    session: Session | None = None,
    custom_metric_udf: str | None = None,
    **kwargs: Any,
) -> tuple[float, str]:
    """Dispatch to built-in or custom metric function.

    Args:
        metric_name: Name of the metric to use
        expected: Expected output value
        predicted: Predicted output value
        session: Snowpark session (required for llm_judge and custom metrics)
        custom_metric_udf: Fully qualified name of a Python UDF that
            implements the custom metric. The UDF must accept
            ``(EXPECTED VARCHAR, PREDICTED VARCHAR)`` and return VARIANT
            with ``score`` (float) and ``feedback`` (string) keys.
        **kwargs: Metric-specific options

    """
    metric_functions: dict[str, Callable[..., tuple[float, str]]] = {
        "exact_match": exact_match_core,
        "fuzzy_match": fuzzy_match_core,
        "contains_match": contains_match_core,
        "redaction_match": redaction_match_core,
        "llm_judge": llm_judge_core,
    }
    metric_fn = metric_functions.get(metric_name)
    if metric_fn is not None:
        return metric_fn(expected, predicted, session, **kwargs)

    if custom_metric_udf:
        if session is None:
            raise ValueError("custom_metric_udf requires a session")
        return call_custom_metric_udf(custom_metric_udf, expected, predicted, session)

    raise ValueError(
        f"Unknown metric: {metric_name}. "
        f"Available built-in: {', '.join(sorted(metric_functions.keys()))}. "
        f"For custom metrics, provide fully qualified custom_metric_udf name."
    )


# Registry of metrics that have optimized batch implementations.
BATCH_FUNCTIONS: dict[str, Callable[..., list[tuple[float, str]]]] = {
    "llm_judge": llm_judge_batch,
}


def compute_metric_batch(
    metric_name: str,
    items: list[tuple[str, str]],
    session: Session | None = None,
    custom_metric_udf: str | None = None,
    **kwargs: Any,
) -> list[tuple[float, str]]:
    """Batch evaluate multiple (expected, predicted) pairs.

    Uses optimized batch implementation if available, otherwise falls back
    to sequential evaluation.

    Args:
        metric_name: Name of the metric to use
        items: List of (expected, predicted) tuples
        session: Snowpark session (required for llm_judge and custom metrics)
        custom_metric_udf: Fully qualified name of a custom metric UDF
        **kwargs: Metric-specific options

    Returns:
        List of (score, feedback) tuples in same order as input

    """
    if metric_name in BATCH_FUNCTIONS:
        if session is None:
            raise ValueError("batched functions require a session")
        return BATCH_FUNCTIONS[metric_name](items, session, **kwargs)

    if custom_metric_udf:
        if session is None:
            raise ValueError("custom_metric_udf requires a session")
        return call_custom_metric_udf_batch(custom_metric_udf, items, session)

    return [
        compute_metric(metric_name, exp, pred, session, **kwargs) for exp, pred in items
    ]

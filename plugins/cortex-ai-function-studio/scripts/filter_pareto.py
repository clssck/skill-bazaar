# Copyright (c) 2026 Snowflake Inc. All rights reserved.
# Licensed under the Snowflake Skills License.
# Refer to the LICENSE file in the root of this repository for full terms.

"""Filter optimization results to pareto-optimal options.

Pareto-optimal means no other option is both cheaper AND has a higher score.
This ensures users only see meaningful trade-offs between cost and quality.

Cost formula: cost = input_price × prompt_chars + output_price × avg_output_chars.

Example usage:
    # From a Snowflake experiment (fetches everything automatically):
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/filter_pareto.py \
        --experiment MY_DB.MY_SCHEMA.MY_EXP --connection my_conn --format table

    # From explicit JSON (legacy / non-experiment runs):
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/filter_pareto.py \
        --json '[{"model": "llama3.1-8b", "score": 0.82}, ...]' \
        --prompt-chars 200 --avg-output-chars 10

    # BYOM/SPCS services can provide explicit relative costs in the result rows.
    uv run --project <SKILL_DIR> python <SKILL_DIR>/scripts/filter_pareto.py \
        --json '[{"model": "DB.SCHEMA.MY_SERVICE", "score": 0.82, \
"relative_cost": 0.4}]' \
        --prompt-chars 200 --avg-output-chars 10

    # Via stdin
    echo '[...]' | uv run --project <SKILL_DIR> \
        python <SKILL_DIR>/scripts/filter_pareto.py \
        --prompt-chars 200 --avg-output-chars 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from snowflake.snowpark import Session

# Load model costs from models.json in the core package (relative to llama3.1-8b = 1.0)
_MODELS_JSON_PATH = (
    Path(__file__).resolve().parent.parent
    / "packages"
    / "snowflake-ai-optimize-core"
    / "src"
    / "snowflake_ai_optimize"
    / "core"
    / "models.json"
)
with open(_MODELS_JSON_PATH) as f:
    MODELS = json.load(f)


def get_model_cost(
    model_name: str,
    prompt_chars: int,
    avg_output_chars: int,
    explicit_cost: float | int | str | None = None,
) -> float:
    """Calculate model cost based on prompt length and average output length.

    cost = input_price × prompt_chars + output_price × avg_output_chars.

    Args:
        model_name: Name of the model.
        prompt_chars: Character length of the system prompt.
        avg_output_chars: Average output character length from test data.
        explicit_cost: Optional caller-provided relative cost. Used for BYOM/SPCS
            service models that are not present in models.json.

    Returns:
        Cost estimate (float).
    """
    if explicit_cost is not None:
        try:
            cost = float(explicit_cost)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Explicit cost for model {model_name} must be numeric."
            ) from exc
        if cost < 0:
            raise ValueError(
                f"Explicit cost for model {model_name} must be non-negative."
            )
        return cost

    if model_name not in MODELS:
        raise ValueError(
            f"Model {model_name} not supported, add to {_MODELS_JSON_PATH} or "
            "include a numeric relative_cost/estimated_cost in the result row."
        )
    model = MODELS[model_name]
    return float(
        prompt_chars * model["input_cost"] + avg_output_chars * model["output_cost"]
    )


def filter_pareto_optimal(
    results: list[dict], prompt_chars: int, avg_output_chars: int
) -> list[dict]:
    """Filter to pareto-optimal results based on cost and score.

    An option is pareto-optimal if no other option has:
    - Lower or equal cost AND strictly higher score, OR
    - Strictly lower cost AND higher or equal score

    Args:
        results: List of dicts with 'model' and 'score'.
        prompt_chars: Prompt character length for cost calculation.
        avg_output_chars: Average output character length for cost calculation.

    Returns:
        List of pareto-optimal results, sorted by relative_cost ascending.
    """
    if not results:
        raise ValueError("No results provided")

    if prompt_chars <= 0:
        raise ValueError("Prompt length must be greater than 0")

    if avg_output_chars < 0:
        raise ValueError("Average output length must be non-negative")

    # Calculate relative cost for each result without mutating the caller's
    # input rows. BYOM/SPCS service models may not be in models.json; allow
    # callers to pass a measured or estimated cost on each result row instead.
    enriched_results: list[dict] = []
    for r in results:
        explicit_cost = r.get("relative_cost", r.get("estimated_cost"))
        enriched = dict(r)
        enriched["relative_cost"] = get_model_cost(
            enriched["model"], prompt_chars, avg_output_chars, explicit_cost
        )
        enriched_results.append(enriched)

    # Sort by (cost ascending, score descending)
    # - Cost ascending: process cheapest options first
    # - Score descending: within same cost, process highest score first
    #   This ensures lower-scoring options at the same cost are correctly
    #   identified as dominated and skipped
    sorted_results = sorted(
        enriched_results, key=lambda x: (x["relative_cost"], -x["score"])
    )

    # Single-pass pareto filter using a "sweep line" approach:
    # As we move from cheap to expensive, we track the best score seen so far.
    # A result is pareto-optimal only if its score exceeds all cheaper options.
    # If score <= max_score_so_far, a cheaper option dominates it (same or
    # better score at lower cost), so we skip it.
    pareto_optimal = []
    max_score_so_far = -1

    for result in sorted_results:
        if result["score"] > max_score_so_far:
            pareto_optimal.append(result)
            max_score_so_far = result["score"]

    return pareto_optimal


def format_results_table(
    results: list[dict],
    seed_score: float | None = None,
) -> str:
    """Format pareto-optimal results as a markdown table.

    Args:
        results: Pareto-optimal results from filter_pareto_optimal().
        seed_score: Original score to calculate improvement.

    Returns:
        Markdown table string.
    """
    if not results:
        return "No results to display."

    lines = []

    lines.extend(
        [
            "| # | Model | Score | Improvement | Relative Cost |",
            "|---|-------|-------|-------------|---------------|",
        ]
    )

    # Find min cost for labeling
    min_cost = min(r["relative_cost"] for r in results) if results else 1.0

    for i, r in enumerate(results, 1):
        score_pct = f"{r['score'] * 100:.1f}%"
        if seed_score is not None:
            improvement = f"+{(r['score'] - seed_score) * 100:.1f}%"
        else:
            improvement = "-"

        # Format cost as multiplier, mark cheapest
        cost_val = r["relative_cost"]
        if cost_val == min_cost:
            cost_label = f"{cost_val:.1f}x (cheapest)"
        else:
            cost_label = f"{cost_val:.1f}x"

        lines.append(
            f"| {i} | {r['model']} | {score_pct} | {improvement} | {cost_label} |"
        )

    return "\n".join(lines)


def fetch_experiment_results(session: Session, experiment_name: str) -> dict:
    """Fetch optimization results from a Snowflake experiment.

    Reads BEST and SEED run parameters/metrics to reconstruct the inputs
    needed for Pareto filtering without any manual SQL queries.

    Args:
        session: Active Snowpark Session.
        experiment_name: Fully-qualified experiment name (DB.SCHEMA.EXP).

    Returns:
        Dict with keys:
            results:          list[dict] — one entry per model with
                              'model', 'score', and 'relative_cost'
                              (cost computed from best-body length and
                              avg_output_chars stored on the SEED run).
            seed_score:       float | None — seed score from the first model.
            avg_output_chars: int | None — from the SEED run parameters.
            prompt_chars:     int | None — len(best_body) from the BEST run.
    """
    rows = session.sql(f"SHOW RUNS IN EXPERIMENT {experiment_name}").collect()
    run_names = [r["name"] for r in rows]

    best_runs = [n for n in run_names if n.endswith("_BEST")]
    if not best_runs:
        raise ValueError(
            f"No BEST runs found in experiment {experiment_name}. "
            "Has the optimization completed?"
        )

    results = []
    seed_score: float | None = None
    avg_output_chars: int | None = None
    prompt_chars_by_model: dict[str, int] = {}

    for best_run in best_runs:
        model_prefix = best_run[: -len("_BEST")]
        seed_run = f"{model_prefix}_SEED"

        # -- BEST run --
        best_params_rows = session.sql(
            f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {best_run}"
        ).collect()
        best_pv = {r["name"]: r["value"] for r in best_params_rows}

        best_metrics_rows = session.sql(
            f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {best_run}"
        ).collect()
        best_mv = {r["name"]: float(r["value"]) for r in best_metrics_rows}

        model = best_pv["model"]
        score_source = best_pv["score_source"]
        best_body = best_pv["function_impl"]

        if score_source == "test" and "test_score" in best_mv:
            score = best_mv["test_score"]
        else:
            if "valset_score" not in best_mv:
                raise ValueError(
                    f"BEST run '{best_run}' missing 'valset_score' metric; "
                    f"available: {list(best_mv)}"
                )
            score = best_mv["valset_score"]

        best_body_len = len(best_body)
        prompt_chars_by_model[model] = best_body_len

        # -- SEED run --
        seed_avg_output_chars: int | None = None
        if seed_run in run_names:
            seed_params_rows = session.sql(
                f"SHOW RUN PARAMETERS IN EXPERIMENT {experiment_name} RUN {seed_run}"
            ).collect()
            seed_pv = {r["name"]: r["value"] for r in seed_params_rows}

            seed_metrics_rows = session.sql(
                f"SHOW RUN METRICS IN EXPERIMENT {experiment_name} RUN {seed_run}"
            ).collect()
            seed_mv = {r["name"]: float(r["value"]) for r in seed_metrics_rows}

            raw_avg = seed_pv.get("avg_output_chars")
            if raw_avg is not None:
                seed_avg_output_chars = int(raw_avg)
                if avg_output_chars is None:
                    avg_output_chars = seed_avg_output_chars

            if seed_score is None:
                if score_source == "test" and "test_score" in seed_mv:
                    seed_score = seed_mv["test_score"]
                elif "valset_score" in seed_mv:
                    seed_score = seed_mv["valset_score"]

        # Compute per-model cost using this model's actual best-body length.
        # For BYOM/SPCS models not in models.json, fall back to the stored
        # estimated_cost or relative_cost written by the optimizer.
        stored_cost_str = best_pv.get("estimated_cost") or best_pv.get("relative_cost")
        stored_cost = float(stored_cost_str) if stored_cost_str is not None else None

        if stored_cost is None and seed_avg_output_chars is None:
            print(
                f"Warning: avg_output_chars missing from SEED run for model '{model}' "
                f"in experiment {experiment_name}. Output token costs will be estimated "
                "as zero — cost comparisons may be inaccurate. "
                "Consider running the manual fallback with "
                "AVG(LENGTH(<label_column>)) from your test table.",
                file=sys.stderr,
            )
        effective_avg = (
            seed_avg_output_chars if seed_avg_output_chars is not None else 0
        )
        relative_cost = get_model_cost(
            model, best_body_len, effective_avg, explicit_cost=stored_cost
        )

        results.append(
            {
                "model": model,
                "score": score,
                "relative_cost": relative_cost,
            }
        )

    return {
        "results": results,
        "seed_score": seed_score,
        "avg_output_chars": avg_output_chars,
        # Experiment mode computes and stores per-row relative costs directly.
        # ``filter_pareto_optimal`` therefore no longer depends on a single
        # shared prompt length in this path. We still surface one representative
        # value for callers that want metadata, but only when all BEST runs
        # share the same prompt/body length.
        "prompt_chars": (
            next(iter(prompt_chars_by_model.values()), None)
            if len(set(prompt_chars_by_model.values())) <= 1
            else None
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Filter optimization results to pareto-optimal options"
    )

    # -- Experiment mode (fetches everything from Snowflake) --
    parser.add_argument(
        "--experiment",
        type=str,
        help="Fully-qualified experiment name (DB.SCHEMA.EXP). "
        "When provided, all results and cost inputs are fetched automatically.",
    )
    parser.add_argument(
        "--connection",
        type=str,
        default="default",
        help="Named Snowflake connection from ~/.snowflake/connections.toml "
        "(default: 'default'). Only used with --experiment.",
    )

    # -- Manual / legacy mode --
    parser.add_argument("--json", type=str, help="JSON array of results")
    parser.add_argument(
        "--prompt-chars",
        type=int,
        help="Length of system prompt in characters (required without --experiment)",
    )
    parser.add_argument(
        "--avg-output-chars",
        type=int,
        help="Average length of expected output in characters (required without --experiment)",
    )

    parser.add_argument(
        "--seed-score",
        type=float,
        help="Original seed score for improvement calculation "
        "(auto-fetched when using --experiment)",
    )
    parser.add_argument(
        "--format", choices=["json", "table"], default="json", help="Output format"
    )
    args = parser.parse_args()

    seed_score = args.seed_score

    if args.experiment:
        # -- Experiment mode: fetch everything from Snowflake --
        from snowflake_ai_optimize.core.session import create_session_from_connection

        session = create_session_from_connection(args.connection)
        fetched = fetch_experiment_results(session, args.experiment)
        results = fetched["results"]
        if seed_score is None:
            seed_score = fetched["seed_score"]
        # Results already have relative_cost set; pass sentinel values for the
        # required prompt_chars/avg_output_chars params (unused when all rows
        # carry an explicit relative_cost).
        prompt_chars = fetched["prompt_chars"] or 1
        avg_output_chars = fetched["avg_output_chars"] or 0
    else:
        # -- Manual mode: require --json/stdin and explicit cost params --
        if args.prompt_chars is None:
            parser.error("--prompt-chars is required when --experiment is not provided")
        if args.avg_output_chars is None:
            parser.error(
                "--avg-output-chars is required when --experiment is not provided"
            )

        data = json.loads(args.json) if args.json else json.load(sys.stdin)

        results = [data] if isinstance(data, dict) else data
        prompt_chars = args.prompt_chars
        avg_output_chars = args.avg_output_chars

    pareto = filter_pareto_optimal(results, prompt_chars, avg_output_chars)

    if args.format == "table":
        print(format_results_table(pareto, seed_score))
    else:
        print(json.dumps({"pareto_optimal": pareto}, indent=2))


if __name__ == "__main__":
    main()

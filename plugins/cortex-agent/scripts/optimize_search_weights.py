#!/usr/bin/env python3
"""
Bayesian Optimization for Cortex Search Service scoring_config weights.

This script finds optimal weights for the scoring_config.functions.weights
parameters (texts, vectors, reranker) using Bayesian Optimization.

Usage with pre-computed labels:
    python optimize_search_weights.py \
        --service "DATABASE.SCHEMA.SERVICE_NAME" \
        --queries relevance_labels.json \
        --connection my_connection \
        --n-trials 50

Usage with on-the-fly LLM scoring (no pre-computed labels needed):
    python optimize_search_weights.py \
        --service "DATABASE.SCHEMA.SERVICE_NAME" \
        --queries queries.json \
        --score-unjudged \
        --cache-file cache.json \
        --n-trials 50

The --cache-file option persists scored documents to disk, so subsequent
runs are fast once the cache warms up. This makes pre-computing labels optional.

The queries JSON file should have the format:
{
    "queries": [
        {
            "query": "search query text",
            "relevant_docs": {  // optional if using --score-unjudged
                "doc_id_or_text": relevance_score,  // 0-3 scale
                ...
            }
        },
        ...
    ]
}

Or just queries (when using --score-unjudged):
{
    "queries": [
        {"query": "search query text"},
        ...
    ]
}
"""
import argparse
import json
import math
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

import snowflake.connector

# Try to import optuna, fall back to helpful error message
try:
    import optuna
    from optuna.samplers import TPESampler
except ImportError:
    print("Error: optuna is required. Install with: pip install optuna")
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm is required. Install with: pip install tqdm")
    sys.exit(1)


# Default LLM model for on-the-fly relevance scoring
DEFAULT_LLM_MODEL = "llama3.1-70b"

# Prompt for scoring unjudged documents
RELEVANCE_PROMPT = """Score the relevance of this document for the query on a scale of 0-3:
- 0: Completely irrelevant
- 1: Somewhat related but doesn't address the query
- 2: Mostly relevant but may miss some aspects
- 3: Perfectly relevant

Query: {query}
Document: {document}

Respond with ONLY a single number (0, 1, 2, or 3):"""


def execute_cortex_search(
    conn: snowflake.connector.SnowflakeConnection,
    service: str,
    query: str,
    columns: List[str],
    limit: int = 10,
    scoring_config: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Execute a Cortex Search query and return results."""
    sql_template = f"""
        SELECT PARSE_JSON(
            SNOWFLAKE.CORTEX.SEARCH_PREVIEW(
                '{service}',
                %s
            )
        )['results'] as results;
    """

    payload: Dict[str, Any] = {
        "query": query,
        "columns": columns,
        "limit": limit,
    }

    if scoring_config:
        payload["scoring_config"] = scoring_config

    cursor = conn.cursor()
    try:
        payload_json = json.dumps(payload)
        cursor.execute(sql_template, (payload_json,))
        for row in cursor:
            if row[0]:
                return json.loads(row[0])
        return []
    finally:
        cursor.close()


def compute_dcg(relevances: List[float], k: int) -> float:
    """Compute Discounted Cumulative Gain at k."""
    dcg = 0.0
    for i, rel in enumerate(relevances[:k]):
        dcg += rel / math.log2(i + 2)  # i+2 because positions are 1-indexed
    return dcg


def compute_ndcg(relevances: List[float], ideal_relevances: List[float], k: int) -> float:
    """Compute Normalized Discounted Cumulative Gain at k."""
    dcg = compute_dcg(relevances, k)
    idcg = compute_dcg(sorted(ideal_relevances, reverse=True), k)
    if idcg == 0:
        return 0.0
    return dcg / idcg


def compute_recall(retrieved_relevant: int, total_relevant: int) -> float:
    """Compute recall."""
    if total_relevant == 0:
        return 0.0
    return retrieved_relevant / total_relevant


def compute_precision(retrieved_relevant: int, retrieved_total: int) -> float:
    """Compute precision."""
    if retrieved_total == 0:
        return 0.0
    return retrieved_relevant / retrieved_total


def normalize_relevant_docs(
    relevant_docs: Optional[Union[List[str], Dict[str, float]]]
) -> Dict[str, float]:
    """Normalize relevant_docs to a dict of doc -> relevance score."""
    if relevant_docs is None:
        return {}
    if isinstance(relevant_docs, list):
        # Binary relevance: all listed docs have relevance 1.0
        return {doc: 1.0 for doc in relevant_docs}
    return relevant_docs


def score_with_llm(
    conn: snowflake.connector.SnowflakeConnection,
    query: str,
    document: str,
    model: str = DEFAULT_LLM_MODEL,
) -> float:
    """Score a document's relevance using Cortex LLM."""
    prompt = RELEVANCE_PROMPT.format(
        query=query,
        document=document[:2000],  # Truncate long documents
    )

    escaped_prompt = prompt.replace("'", "''")
    sql = f"""
        SELECT SNOWFLAKE.CORTEX.COMPLETE(
            '{model}',
            '{escaped_prompt}'
        ) as response;
    """

    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        if row and row[0]:
            response = row[0].strip()
            # Extract score from response
            match = re.search(r'[0-3]', response)
            if match:
                return float(match.group())
        return 0.0
    except Exception:
        return 0.0
    finally:
        cursor.close()


def match_doc_to_relevance(
    text: str,
    relevant_docs: Dict[str, float],
) -> Tuple[float, bool]:
    """
    Match a retrieved document to known relevant docs.

    Returns (relevance_score, was_matched).
    """
    for doc, rel in relevant_docs.items():
        # Fuzzy matching: check containment in either direction
        if doc in text or text in doc or doc.lower() == text.lower():
            return rel, True
    return 0.0, False


def evaluate_search_results(
    results: List[Dict[str, Any]],
    relevant_docs: Dict[str, float],
    text_column: str,
    k: int = 10,
    conn: Optional[snowflake.connector.SnowflakeConnection] = None,
    query: Optional[str] = None,
    score_unjudged: bool = False,
    llm_model: str = DEFAULT_LLM_MODEL,
    unjudged_cache: Optional[Dict[str, float]] = None,
    cache_file: Optional[str] = None,
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Evaluate search results against ground truth.

    Args:
        results: Search results from Cortex Search
        relevant_docs: Known relevance judgments
        text_column: Column containing document text
        k: Number of results to evaluate
        conn: Snowflake connection (required if score_unjudged=True)
        query: Query text (required if score_unjudged=True)
        score_unjudged: Whether to score unjudged docs with LLM
        llm_model: Model to use for scoring unjudged docs
        unjudged_cache: Cache for unjudged doc scores (modified in place)
        cache_file: File to save cache to immediately after LLM calls

    Returns:
        Tuple of (metrics dict, updated unjudged_cache)
    """
    if unjudged_cache is None:
        unjudged_cache = {}

    # Extract retrieved doc texts
    retrieved_texts = [r.get(text_column, "") for r in results[:k]]

    # Compute relevances for retrieved docs
    relevances = []
    retrieved_relevant = 0
    unjudged_count = 0

    for text in retrieved_texts:
        rel, was_matched = match_doc_to_relevance(text, relevant_docs)

        if was_matched:
            relevances.append(rel)
            if rel > 0:
                retrieved_relevant += 1
        elif score_unjudged and conn and query:
            # Score unjudged document with LLM
            # Check cache first
            cache_key = f"{query[:50]}::{text[:100]}"
            if cache_key in unjudged_cache:
                rel = unjudged_cache[cache_key]
            else:
                rel = score_with_llm(conn, query, text, llm_model)
                unjudged_cache[cache_key] = rel
                unjudged_count += 1

                # Save cache immediately after each LLM call
                if cache_file:
                    with open(cache_file, "w") as f:
                        json.dump(unjudged_cache, f)

            relevances.append(rel)
            if rel > 0:
                retrieved_relevant += 1
        else:
            # Unjudged doc treated as irrelevant
            relevances.append(0.0)

    # Ideal relevances (sorted descending)
    # If we have pre-computed relevant_docs, use those for ideal
    # Otherwise (when scoring unjudged), use the scores we computed
    if relevant_docs:
        ideal_relevances = sorted(relevant_docs.values(), reverse=True)
        total_relevant = len(relevant_docs)
    else:
        # No pre-computed labels - use the LLM-scored relevances as ideal
        # This measures how well results are ranked, not absolute recall
        ideal_relevances = sorted(relevances, reverse=True)
        total_relevant = sum(1 for r in relevances if r > 0)

    # Compute metrics
    ndcg = compute_ndcg(relevances, ideal_relevances, k)
    recall = compute_recall(retrieved_relevant, max(total_relevant, 1))
    precision = compute_precision(retrieved_relevant, len(retrieved_texts))

    return {
        f"ndcg@{k}": ndcg,
        f"recall@{k}": recall,
        f"precision@{k}": precision,
        "unjudged_scored": unjudged_count,
    }, unjudged_cache


class SearchWeightOptimizer:
    """Bayesian optimizer for Cortex Search scoring weights."""

    def __init__(
        self,
        conn: snowflake.connector.SnowflakeConnection,
        service: str,
        queries: List[Dict[str, Any]],
        columns: List[str],
        text_column: str,
        limit: int = 10,
        metric: str = "ndcg",
        optimize_reranker: bool = True,
        weight_min: float = 0.1,
        weight_max: float = 10.0,
        score_unjudged: bool = False,
        llm_model: str = DEFAULT_LLM_MODEL,
        verbose: bool = True,
    ):
        self.conn = conn
        self.service = service
        self.queries = queries
        self.columns = columns
        self.text_column = text_column
        self.limit = limit
        self.metric = metric
        self.optimize_reranker = optimize_reranker
        self.weight_min = weight_min
        self.weight_max = weight_max
        self.score_unjudged = score_unjudged
        self.llm_model = llm_model
        self.verbose = verbose

        # Track best results
        self.best_score = -float("inf")
        self.best_weights = None
        self.trial_history: List[Dict[str, Any]] = []

        # Cache for unjudged document scores (persists across trials)
        self.unjudged_cache: Dict[str, float] = {}
        self.cache_file: Optional[str] = None
        self._cache_size_at_last_save: int = 0

        # Progress tracking
        self.trial_pbar: Optional[tqdm] = None
        self.current_trial: int = 0
        self.n_trials: int = 0

    def load_cache(self, cache_file: str) -> int:
        """Load relevance cache from disk. Returns number of entries loaded."""
        self.cache_file = cache_file
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    self.unjudged_cache = json.load(f)
                self._cache_size_at_last_save = len(self.unjudged_cache)
                return len(self.unjudged_cache)
            except (json.JSONDecodeError, IOError):
                return 0
        return 0

    def save_cache(self, force: bool = False) -> bool:
        """Save relevance cache to disk if there are new entries.
        
        Args:
            force: Save even if no new entries
            
        Returns:
            True if cache was saved, False otherwise
        """
        if not self.cache_file:
            return False
            
        current_size = len(self.unjudged_cache)
        if not force and current_size == self._cache_size_at_last_save:
            return False  # No new entries
            
        if current_size > 0:
            with open(self.cache_file, "w") as f:
                json.dump(self.unjudged_cache, f)
            self._cache_size_at_last_save = current_size
            return True
        return False

    def build_scoring_config(
        self,
        texts: float,
        vectors: float,
        reranker: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Build the scoring_config for a Cortex Search query."""
        weights = {
            "texts": texts,
            "vectors": vectors,
        }
        if reranker is not None:
            weights["reranker"] = reranker

        # Note: weights go directly under scoring_config, not under functions
        return {"weights": weights}

    def evaluate_weights(
        self,
        texts: float,
        vectors: float,
        reranker: Optional[float] = None,
    ) -> float:
        """Evaluate a weight configuration across all queries."""
        scoring_config = self.build_scoring_config(
            texts, vectors, reranker
        )

        all_metrics: Dict[str, List[float]] = {
            f"ndcg@{self.limit}": [],
            f"recall@{self.limit}": [],
            f"precision@{self.limit}": [],
        }
        total_unjudged_scored = 0

        # Create query progress bar (nested under trial bar)
        query_iter = self.queries
        if self.verbose and self.trial_pbar is not None:
            query_iter = tqdm(
                self.queries,
                desc="  Queries",
                leave=False,
                position=1,
                ncols=80,
                bar_format="{desc}: {n}/{total} [{elapsed}<{remaining}]",
            )

        for query_data in query_iter:
            query_text = query_data["query"]
            relevant_docs = normalize_relevant_docs(query_data.get("relevant_docs"))

            try:
                results = execute_cortex_search(
                    self.conn,
                    self.service,
                    query_text,
                    self.columns,
                    self.limit,
                    scoring_config,
                )

                metrics, self.unjudged_cache = evaluate_search_results(
                    results=results,
                    relevant_docs=relevant_docs,
                    text_column=self.text_column,
                    k=self.limit,
                    conn=self.conn if self.score_unjudged else None,
                    query=query_text if self.score_unjudged else None,
                    score_unjudged=self.score_unjudged,
                    llm_model=self.llm_model,
                    unjudged_cache=self.unjudged_cache,
                    cache_file=self.cache_file,
                )

                for key, value in metrics.items():
                    if key in all_metrics:
                        all_metrics[key].append(value)
                    elif key == "unjudged_scored":
                        total_unjudged_scored += value

            except Exception as e:
                if self.verbose:
                    tqdm.write(f"  Warning: Query failed: {e}")
                # Append 0 for failed queries
                for key in all_metrics:
                    all_metrics[key].append(0.0)

        # Compute average metrics
        avg_metrics = {k: sum(v) / len(v) if v else 0.0 for k, v in all_metrics.items()}

        # Log unjudged scoring stats
        if self.score_unjudged and self.verbose and total_unjudged_scored > 0:
            tqdm.write(f"    (scored {total_unjudged_scored} new docs, cache: {len(self.unjudged_cache)})")

        # Return the target metric
        if self.metric == "ndcg":
            return avg_metrics[f"ndcg@{self.limit}"]
        elif self.metric == "recall":
            return avg_metrics[f"recall@{self.limit}"]
        elif self.metric == "precision":
            return avg_metrics[f"precision@{self.limit}"]
        else:
            raise ValueError(f"Unknown metric: {self.metric}")

    def objective(self, trial: optuna.Trial) -> float:
        """Optuna objective function."""
        texts = trial.suggest_float(
            "texts", self.weight_min, self.weight_max, log=True
        )
        vectors = trial.suggest_float(
            "vectors", self.weight_min, self.weight_max, log=True
        )

        reranker = None
        if self.optimize_reranker:
            reranker = trial.suggest_float(
                "reranker", self.weight_min, self.weight_max, log=True
            )

        score = self.evaluate_weights(texts, vectors, reranker)

        # Track progress
        weights = {
            "texts": round(texts, 3),
            "vectors": round(vectors, 3),
        }
        if reranker is not None:
            weights["reranker"] = round(reranker, 3)

        self.trial_history.append({"weights": weights, "score": score})

        is_new_best = False
        if score > self.best_score:
            self.best_score = score
            self.best_weights = weights
            is_new_best = True

        # Update trial progress bar
        if self.trial_pbar is not None:
            self.trial_pbar.update(1)
            self.trial_pbar.set_postfix({
                "best": f"{self.best_score:.4f}",
                "current": f"{score:.4f}",
            })

        # Always log trial result
        if self.verbose:
            marker = "★" if is_new_best else " "
            weights_str = f"t:{weights['texts']:.2f}, v:{weights['vectors']:.2f}"
            if 'reranker' in weights:
                weights_str += f", r:{weights['reranker']:.2f}"
            tqdm.write(
                f"  {marker} Trial {trial.number:3d}: {self.metric}={score:.4f}  [{weights_str}]"
            )

        return score

    def optimize(
        self,
        n_trials: int = 50,
        timeout: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> Tuple[Dict[str, float], float]:
        """
        Run Bayesian optimization to find optimal weights.

        Args:
            n_trials: Number of optimization trials
            timeout: Optional timeout in seconds
            seed: Random seed for reproducibility

        Returns:
            Tuple of (best_weights, best_score)
        """
        self.n_trials = n_trials

        if self.verbose:
            print(f"\n{'='*60}")
            print("BAYESIAN OPTIMIZATION")
            print(f"{'='*60}")
            print(f"  Service:        {self.service}")
            print(f"  Metric:         {self.metric}@{self.limit}")
            print(f"  Queries:        {len(self.queries)}")
            print(f"  Trials:         {n_trials}")
            print(f"  Weight range:   [{self.weight_min}, {self.weight_max}]")
            print(f"  Reranker:       {'optimizing' if self.optimize_reranker else 'disabled'}")
            if self.score_unjudged:
                print(f"  Unjudged docs:  LLM scoring (model: {self.llm_model})")
                print(f"  Cache size:     {len(self.unjudged_cache)} entries")
            else:
                print("  Unjudged docs:  treated as irrelevant")
            print(f"{'='*60}\n")

        sampler = TPESampler(seed=seed)
        study = optuna.create_study(
            direction="maximize",
            sampler=sampler,
        )

        # Suppress optuna's own logging and progress bar
        optuna.logging.set_verbosity(optuna.logging.WARNING)

        # Create our own progress bar
        if self.verbose:
            self.trial_pbar = tqdm(
                total=n_trials,
                desc="Trials",
                position=0,
                ncols=100,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {postfix}]",
            )
            self.trial_pbar.set_postfix({"best": "N/A", "current": "N/A"})

        try:
            study.optimize(
                self.objective,
                n_trials=n_trials,
                timeout=timeout,
                show_progress_bar=False,  # We handle our own progress bar
            )
        finally:
            if self.trial_pbar is not None:
                self.trial_pbar.close()
                self.trial_pbar = None

        best_weights = study.best_params
        best_score = study.best_value

        # Final cache save (force even if no new entries, to confirm)
        if self.cache_file:
            self.save_cache(force=True)
            if self.verbose:
                print(f"\nFinal cache: {len(self.unjudged_cache)} entries saved to {self.cache_file}")

        if self.verbose:
            print(f"\n{'='*60}")
            print("OPTIMIZATION COMPLETE")
            print(f"{'='*60}")
            print(f"Best {self.metric}@{self.limit}: {best_score:.4f}")
            print(f"Best weights: {json.dumps(best_weights, indent=2)}")
            print(f"\nTo use these weights, add to your search query:")
            print(json.dumps(self.build_scoring_config(**best_weights), indent=2))

        return best_weights, best_score


def load_queries(queries_path: str) -> List[Dict[str, Any]]:
    """Load queries from a JSON file."""
    with open(queries_path, "r") as f:
        data = json.load(f)

    if "queries" in data:
        return data["queries"]
    elif isinstance(data, list):
        return data
    else:
        raise ValueError(
            "Invalid queries format. Expected {'queries': [...]} or a list of query objects."
        )


def main():
    parser = argparse.ArgumentParser(
        description="Optimize Cortex Search scoring_config weights using Bayesian Optimization"
    )
    parser.add_argument(
        "--service",
        required=True,
        help="Fully qualified Cortex Search service name (DATABASE.SCHEMA.SERVICE)",
    )
    parser.add_argument(
        "--queries",
        required=True,
        help="Path to JSON file with queries and relevance labels",
    )
    parser.add_argument(
        "--connection",
        default=None,
        help="Snowflake connection name (defaults to SNOWFLAKE_CONNECTION_NAME env var or 'default')",
    )
    parser.add_argument(
        "--columns",
        nargs="+",
        default=["TEXT"],
        help="Columns to retrieve from search results (default: TEXT)",
    )
    parser.add_argument(
        "--text-column",
        default=None,
        help="Column containing document text for matching (defaults to first column)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of results to retrieve per query (default: 10)",
    )
    parser.add_argument(
        "--metric",
        choices=["ndcg", "recall", "precision"],
        default="ndcg",
        help="Metric to optimize (default: ndcg)",
    )
    parser.add_argument(
        "--n-trials",
        type=int,
        default=50,
        help="Number of optimization trials (default: 50)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Optional timeout in seconds",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducibility",
    )
    parser.add_argument(
        "--no-reranker",
        action="store_true",
        help="Don't optimize the reranker weight (only optimize texts and vectors)",
    )
    parser.add_argument(
        "--weight-min",
        type=float,
        default=0.1,
        help="Minimum weight value (default: 0.1)",
    )
    parser.add_argument(
        "--weight-max",
        type=float,
        default=10.0,
        help="Maximum weight value (default: 10.0)",
    )
    parser.add_argument(
        "--score-unjudged",
        action="store_true",
        help="Score unjudged documents with LLM (slower initially, fast once cache warms)",
    )
    parser.add_argument(
        "--llm-model",
        default=DEFAULT_LLM_MODEL,
        help=f"LLM model for scoring unjudged docs (default: {DEFAULT_LLM_MODEL})",
    )
    parser.add_argument(
        "--cache-file",
        default=None,
        help="File to persist relevance cache (enables fast subsequent runs)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional output file for results (JSON)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress verbose output",
    )

    args = parser.parse_args()

    connection_name = args.connection or os.getenv("SNOWFLAKE_CONNECTION_NAME") or "default"
    text_column = args.text_column or args.columns[0]

    # Load queries
    print(f"Loading queries from: {args.queries}")
    queries = load_queries(args.queries)
    print(f"Loaded {len(queries)} queries")

    # Connect to Snowflake
    print(f"Connecting to Snowflake using connection: {connection_name}")
    conn = snowflake.connector.connect(connection_name=connection_name)

    try:
        optimizer = SearchWeightOptimizer(
            conn=conn,
            service=args.service,
            queries=queries,
            columns=args.columns,
            text_column=text_column,
            limit=args.limit,
            metric=args.metric,
            optimize_reranker=not args.no_reranker,
            weight_min=args.weight_min,
            weight_max=args.weight_max,
            score_unjudged=args.score_unjudged,
            llm_model=args.llm_model,
            verbose=not args.quiet,
        )

        # Load cache if specified
        if args.cache_file:
            loaded = optimizer.load_cache(args.cache_file)
            if loaded > 0:
                print(f"Loaded {loaded} cached relevance scores from: {args.cache_file}")

        best_weights, best_score = optimizer.optimize(
            n_trials=args.n_trials,
            timeout=args.timeout,
            seed=args.seed,
        )

        # Save results if output file specified
        if args.output:
            results = {
                "best_weights": best_weights,
                "best_score": best_score,
                "metric": f"{args.metric}@{args.limit}",
                "scoring_config": optimizer.build_scoring_config(**best_weights),
                "trial_history": optimizer.trial_history,
                "config": {
                    "service": args.service,
                    "n_trials": args.n_trials,
                    "limit": args.limit,
                    "columns": args.columns,
                    "text_column": text_column,
                    "optimize_reranker": not args.no_reranker,
                    "weight_range": [args.weight_min, args.weight_max],
                },
            }
            with open(args.output, "w") as f:
                json.dump(results, f, indent=2)
            print(f"\nResults saved to: {args.output}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()


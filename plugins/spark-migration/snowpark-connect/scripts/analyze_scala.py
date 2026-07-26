# flake8: noqa: T201

"""
SCOS Migration Agent - Scala Spark Compatibility Analyzer

Analyze Scala Spark scripts for potential SCOS compatibility issues.
Detection is AST-primary: when a JVM/sbt toolchain is available,
``scala_ast_facts.py`` extracts line-tagged Scalameta facts once over
the workload and all structural/behavioral checks run on those facts
(no comment/string false-positives). When no toolchain is present or
``SCOS_NO_AST_FACTS=1`` is set, the analyzer falls back to regex-based
pattern detection — emitting identical issue rows either way.

Produces the same JSON output format as analyze_pyspark.py.

Usage:
    python analyze_scala.py --path /path/to/script.scala
    python analyze_scala.py --path /path/to/scripts/
"""

import argparse
import csv
import json
import logging
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from code_normalization import normalize_code_lightweight
from notebook_io import detect_format, is_notebook, parse_notebook, walk_filtered
from rag import BaseRAG
from scos_session import (
    DEFAULT_LLM_MODEL,
    add_connectivity_args,
    build_rag,
    is_non_retryable_llm_error,
    open_session,
    verify_cortex_complete_access,
)
from snowflake.snowpark import Session

logger = logging.getLogger(__name__)

try:
    from snowflake.cortex import CompleteOptions, complete as cortex_complete
except ModuleNotFoundError:  # pragma: no cover - depends on host env packaging
    CompleteOptions = None  # type: ignore[assignment]
    cortex_complete = None  # type: ignore[assignment]

# Condition-aware decidability: mirrors analyze_pyspark.apply_condition_resolution.
# Loaded once; silently disabled when static_condition_pass is absent.
try:
    from static_condition_pass import _load_conditional_fns as _sc_load_cond, _scan_sql as _sc_scan_sql
    _COND_FNS: dict[str, str] = _sc_load_cond(None)
except Exception:  # pragma: no cover
    _COND_FNS = {}

DEFAULT_LLM_BATCH_SIZE = 5
DEFAULT_PARALLEL_WORKERS = 8

# File-level concurrency (independent files analyzed in parallel). Default 1
# (serial) because total Cortex/RAG concurrency ≈ DEFAULT_FILE_WORKERS ×
# parallel_workers, and multiplying the per-file workers on top of the intra-file
# workers (8) overwhelms the remote RAG endpoint with 429 rate-limit errors.
# File-level parallelism is therefore OPT-IN via --file-workers; only raise it in
# environments without RAG rate limits.
DEFAULT_FILE_WORKERS = 1

DATA_DIR = Path(__file__).parent / "data"


def load_safe_apis(json_path: Path | None = None) -> set[str]:
    """Load the result-identical safe-API allowlist shared with the PySpark
    analyzer (``data/safe_apis.json``). The patterns are Spark relational-level
    method names (``select``, ``filter``, ``groupBy`` …) that SCOS maps
    identically regardless of the Scala/Python frontend, so the list is reused
    as-is. Returns an empty set (⇒ every block analyzed) if the file is missing
    or malformed.
    """
    if json_path is None:
        json_path = DATA_DIR / "safe_apis.json"
    if not json_path.exists():
        logger.warning("Safe-API allowlist not found at %s — all blocks will be analyzed", json_path)
        return set()
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        return {entry["pattern"] for entry in data.get("apis", [])}
    except (json.JSONDecodeError, KeyError, OSError) as exc:
        logger.warning("Failed to parse safe-API allowlist %s: %s — all blocks analyzed", json_path, exc)
        return set()


def is_block_safe(block_functions: list[str], safe_apis: set[str]) -> bool:
    """True when EVERY method call in a block is on the safe-API allowlist, so
    the block is result-identical on SCOS and needs no RAG/LLM analysis."""
    if not safe_apis or not block_functions:
        return False
    return all(func in safe_apis for func in block_functions)


def _condition_verdicts_for_file(file_facts: dict) -> dict[str, str]:
    """Return {fn_name: 'met'|'cleared'|'indeterminate'} for conditional KB rules.

    Uses the ScosMigrateFacts calls list to detect .over() chains (in_window)
    and the spark_sql strings via sqlglot (both conditions). Mirrors
    analyze_pyspark.apply_condition_resolution but consumes Scalameta facts
    instead of Python ast output.
    """
    if not _COND_FNS or not file_facts:
        return {}
    calls = file_facts.get("calls") or []
    # recv_leaf of every .over() call is the leaf name of the chained receiver,
    # e.g. collect_list(col("x")).over(win) → recv_leaf="collect_list"
    over_receivers = {c["recv_leaf"].lower() for c in calls if c.get("method") == "over"}
    over_exists = any(c.get("method") == "over" for c in calls)
    rank = {"met": 3, "indeterminate": 2, "cleared": 1}
    verdict: dict[str, str] = {}
    for c in calls:
        fn = (c.get("method") or "").lower()
        if fn not in _COND_FNS:
            continue
        cond = _COND_FNS[fn]
        if cond == "in_window":
            if fn in over_receivers:
                v = "met"
            elif not over_exists:
                v = "cleared"
            else:
                v = "indeterminate"
        else:  # distinct_arg: no Scala DataFrame API form → fall through to SQL scan
            v = "indeterminate"
        cur = verdict.get(fn)
        if cur is None or rank[v] > rank[cur]:
            verdict[fn] = v
    # SQL strings: use the shared sqlglot pass for both conditions
    for sql_entry in (file_facts.get("spark_sql") or []):
        sql = sql_entry.get("text") if isinstance(sql_entry, dict) else sql_entry
        if not sql:
            continue
        for o in _sc_scan_sql(sql, _COND_FNS, "<scala>"):
            fn = o["function"]
            v = "met" if o["met"] is True else ("cleared" if o["met"] is False else "indeterminate")
            cur = verdict.get(fn)
            if cur is None or rank[v] > rank[cur]:
                verdict[fn] = v
    return verdict


PROMPT_PREDICT_COMPATIBILITY_BATCH = """
You are analyzing multiple Scala Spark code blocks for compatibility issues when running on Snowflake SCOS (Snowpark Connect for Spark).
Your goal is to analyze each code block and determine if it will actually fail on SCOS.

## INPUT DATA
You are provided with {num_blocks} code blocks. Each block contains:
1. `block_id`: Unique identifier.
2. `input_code`: The Scala Spark code snippet to analyze.
3. `preliminary_assessment`: Rule-based warnings (e.g., "API X is unsupported").
4. `matching_patterns`: Similar failing test cases from our database.

## ANALYSIS PROCESS (Apply to EACH block)
1. **Analyze Input**: Understand the intent and syntax of the `input_code`.
2. **Verify RAG Matches**: Compare `input_code` with `matching_patterns`.
   - Do the failing patterns share the *exact same* root cause as the input?
3. **Verify Rule-Based Warnings**: Check if the `preliminary_assessment` is valid.

## RISK SCORING RULES:
- If the similar test cases use DIFFERENT operations/patterns → final_risk 0.0 to 0.1
- If there are NO compatibility issues → final_risk 0.0
- If similar test cases use the SAME problematic pattern → final_risk 0.5 to 1.0
- Only assign high risk (>0.5) if confident the code will ACTUALLY fail
- If no similar test cases but SCOS Issues Risk > 0, use it as final_risk

BE CONSISTENT: If explanation says "should work correctly", final_risk MUST be < 0.1

## CODE BLOCKS TO ANALYZE

{code_blocks_text}

## OUTPUT FORMAT
Return ONLY a valid JSON array with EXACTLY {num_blocks} items (one per block, in order).
No text before or after the JSON.

[
    {{
        "block_id": "<the block_id from the input>",
        "analysis_thought_process": "<Step-by-step reasoning>",
        "final_risk": <0.0-1.0 float>,
        "root_cause": "<root cause or null if safe>",
        "explanation": "<1-2 sentence summary>",
        "fix": "<specific fix or null>",
        "confidence": "<HIGH|MEDIUM|LOW>"
    }},
    ...
]
"""

# Scala RDD access patterns
RDD_PATTERNS = [
    r"\.sparkContext",
    r"\.rdd\b",
    r"\.javaRDD\b",
    r"\.toJavaRDD\b",
    r"import\s+org\.apache\.spark\.rdd",
    r"import\s+org\.apache\.spark\.SparkContext",
    r"\bsc\.parallelize\b",
    r"\bsc\.textFile\b",
    r"\bsc\.wholeTextFiles\b",
    r"\bsc\.hadoopFile\b",
    r"\bsc\.hadoopRDD\b",
    r"\bsc\.newAPIHadoopFile\b",
    r"\bsc\.newAPIHadoopRDD\b",
    r"\bsc\.sequenceFile\b",
    r"\bsc\.objectFile\b",
    r"\bsc\.emptyRDD\b",
    r"\bnew\s+SparkContext\b",
]

# Scala RDD method names
RDD_METHODS = {
    "map", "flatMap", "filter", "reduce", "reduceByKey", "groupByKey",
    "sortByKey", "sortBy", "join", "leftOuterJoin", "rightOuterJoin",
    "fullOuterJoin", "cogroup", "cartesian", "pipe", "foreach",
    "foreachPartition", "collect", "count", "first", "take", "takeSample",
    "takeOrdered", "saveAsTextFile", "saveAsSequenceFile", "saveAsObjectFile",
    "countByKey", "countByValue", "aggregate", "fold", "glom",
    "mapPartitions", "mapPartitionsWithIndex", "zip", "zipWithIndex",
    "zipWithUniqueId", "keyBy", "keys", "values", "lookup", "top",
    "mapValues", "flatMapValues", "combineByKey", "aggregateByKey",
    "foldByKey", "sampleByKey", "subtractByKey",
}

# Unsupported Scala imports
UNSUPPORTED_IMPORTS = {
    "org.apache.spark.ml": {
        "risk": 1.0,
        "reason": "Spark ML (org.apache.spark.ml) is not supported in SCOS",
        "category": "Unsupported Module",
    },
    "org.apache.spark.mllib": {
        "risk": 1.0,
        "reason": "Spark MLlib (org.apache.spark.mllib) is not supported in SCOS",
        "category": "Unsupported Module",
    },
    "org.apache.spark.streaming": {
        "risk": 1.0,
        "reason": "Spark Streaming (org.apache.spark.streaming) is not supported in SCOS",
        "category": "Unsupported Module",
    },
    "org.apache.spark.graphx": {
        "risk": 1.0,
        "reason": "GraphX (org.apache.spark.graphx) is not supported in SCOS",
        "category": "Unsupported Module",
    },
    "org.apache.spark.sql.catalyst": {
        "risk": 1.0,
        "reason": "Spark Catalyst internals (org.apache.spark.sql.catalyst) are not available via Spark Connect — replace with custom types",
        "category": "Unsupported Module",
    },
    "org.apache.hadoop": {
        "risk": 0.9,
        "reason": "Hadoop APIs (org.apache.hadoop) are not available in SCOS — remove HDFS/FileSystem usage and use Snowflake stages",
        "category": "Unsupported Module",
    },
    "org.apache.spark.sql.hive": {
        "risk": 1.0,
        "reason": "Hive integration (org.apache.spark.sql.hive) is not available in SCOS",
        "category": "Unsupported Module",
    },
    "com.hortonworks.spark.sql.hive": {
        "risk": 1.0,
        "reason": "Hive Warehouse Connector is not available in SCOS",
        "category": "Unsupported Module",
    },
    "za.co.absa.spline": {
        "risk": 1.0,
        "reason": "Spline data-lineage tracking (za.co.absa.spline) is not available in SCOS — remove lineage harvesting; use Snowflake ACCESS_HISTORY/lineage instead",
        "category": "Unsupported Module",
    },
}

UNSUPPORTED_FORMATS = {
    "avro": {"risk": 1.0, "reason": "Avro format is not supported in SCOS", "category": "Unsupported Format"},
    "orc": {"risk": 1.0, "reason": "ORC format is not supported in SCOS", "category": "Unsupported Format"},
    "delta": {"risk": 1.0, "reason": "Delta format is not supported in SCOS", "category": "Unsupported Format"},
}

NO_OP_APIS = {
    "hint": {"risk": 0.2, "reason": "DataFrame.hint() is ignored in SCOS", "category": "No-Op API"},
    "repartition": {"risk": 0.2, "reason": "DataFrame.repartition() is a no-op in SCOS", "category": "No-Op API"},
    "coalesce": {"risk": 0.2, "reason": "DataFrame.coalesce() is a no-op in SCOS", "category": "No-Op API"},
}

# Documented unsupported Dataset/DataFrame APIs (Snowpark Connect for Scala)
# All entries carry final_risk >= 0.7 per the authoritative unsupported-API list.
UNSUPPORTED_DF_APIS: dict[str, dict] = {
    "checkpoint": {
        "risk": 0.9,
        "reason": "checkpoint() is not supported in Snowpark Connect — use cache() instead",
        "category": "No-Op API",
        "how_to_fix": "df.checkpoint() → df.cache()",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "localCheckpoint": {
        "risk": 0.9,
        "reason": "localCheckpoint() is not supported in Snowpark Connect — use cache() instead",
        "category": "No-Op API",
        "how_to_fix": "df.localCheckpoint() → df.cache()",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "randomSplit": {
        "risk": 0.9,
        "reason": "randomSplit() is not supported in Snowpark Connect",
        "category": "No-Op API",
        "how_to_fix": "Use df.sample() with a fraction or filter by a random column expression instead",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "toJSON": {
        "risk": 0.85,
        "reason": "toJSON is not supported in Snowpark Connect — Dataset[String] is not available via Connect",
        "category": "No-Op API",
        "how_to_fix": "Use df.select(to_json(struct(col(\"*\")))) and write to a JSON stage file instead",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "withWatermark": {
        "risk": 0.95,
        "reason": "withWatermark() is a Structured Streaming API not supported in Snowpark Connect",
        "category": "No-Op API",
        "how_to_fix": "Remove watermark — SCOS is batch-only; refactor for batch processing",
        "ewi_code": "SPRKCNTSCL2000",
    },
    "writeStream": {
        "risk": 1.0,
        "reason": "writeStream is a Structured Streaming API not supported in Snowpark Connect",
        "category": "No-Op API",
        "how_to_fix": "Replace with df.write batch API (df.write.mode(...).parquet(...) etc.)",
        "ewi_code": "SPRKCNTSCL2000",
    },
    "dropDuplicatesWithinWatermark": {
        "risk": 0.95,
        "reason": "dropDuplicatesWithinWatermark() is a Structured Streaming API not supported in Snowpark Connect",
        "category": "No-Op API",
        "how_to_fix": "Use df.dropDuplicates() for batch deduplication instead",
        "ewi_code": "SPRKCNTSCL2000",
    },
    "reduce": {
        "risk": 0.9,
        "reason": "DataFrame.reduce() is a Java/Scala-specific action not available via Spark Connect",
        "category": "No-Op API",
        "how_to_fix": "Use df.agg(...) or df.groupBy().agg(...) aggregation functions instead",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "sortWithinPartitions": {
        "risk": 0.8,
        "reason": "sortWithinPartitions() is not available via Spark Connect — partitioning is managed by Snowflake",
        "category": "No-Op API",
        "how_to_fix": "Use df.orderBy() at the DataFrame level instead",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "queryExecution": {
        "risk": 0.9,
        "reason": "queryExecution is an internal Spark Catalyst API not available via Spark Connect",
        "category": "No-Op API",
        "how_to_fix": "Remove queryExecution usage — use high-level DataFrame API instead",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "sqlContext": {
        "risk": 0.85,
        "reason": "sqlContext is a deprecated alias for SparkSession; not available via Spark Connect",
        "category": "No-Op API",
        "how_to_fix": "Replace sqlContext with the SparkSession (spark) directly",
        "ewi_code": "SPRKCNTSCL3500",
    },
    "isEmpty": {
        "risk": 0.8,
        "reason": "DataFrame.isEmpty is not available via Spark Connect",
        "category": "No-Op API",
        "how_to_fix": "Use df.count() == 0 or df.limit(1).collect().isEmpty instead",
        "ewi_code": "SPRKCNTSCL1000",
    },
    "toLocalIterator": {
        "risk": 0.85,
        "reason": "toLocalIterator() is not available via Spark Connect",
        "category": "No-Op API",
        "how_to_fix": "Use df.collect().iterator for small datasets, or process data server-side",
        "ewi_code": "SPRKCNTSCL1000",
    },
}

# Behavioral difference patterns (BD-N entries from behavioral-differences.md)
# Each tuple: (regex_pattern, ewi_code, risk, reason, how_to_fix)
BEHAVIORAL_DIFFERENCE_PATTERNS: list[tuple[str, str, float, str, str]] = [
    (
        r"\.cast\s*\(|\bCAST\s*\(",
        "SPRKCNTSCL5001",
        0.7,
        "BD-2: failed casts return NULL silently in Spark but throw a runtime error in Snowflake",
        "Use TRY_* functions via selectExpr, e.g. selectExpr(\"TRY_TO_NUMBER(col) as col\") / TRY_TO_DATE(...)",
    ),
    (
        r"\bdatediff\s*\(",
        "SPRKCNTSCL5002",
        0.7,
        "BD-3: datediff parameter order differs — Spark: datediff(end, start); Snowflake requires explicit date part and reversed parameter order",
        "Use expr(\"DATEDIFF('day', start_col, end_col)\") for portable behavior",
    ),
    (
        r"(?<!\w)\.union\s*\(",
        "SPRKCNTSCL5003",
        0.6,
        "BD-4: .union() is position-based — if column orders differ between DataFrames, data is silently corrupted",
        "Replace .union() with .unionByName()",
    ),
    (
        r"\belement_at\s*\(",
        "SPRKCNTSCL5004",
        0.6,
        "BD-5: element_at is 1-indexed in Spark but may be 0-indexed under Spark Connect translation to Snowflake",
        "Verify indexing behavior; add a // SCOS: TODO - verify element_at indexing comment",
    ),
    (
        r"\bconcat_ws\s*\(",
        "SPRKCNTSCL5005",
        0.6,
        "BD-6: concat_ws skips nulls in Spark but returns NULL if any argument is null in Snowflake",
        "Wrap each argument with coalesce, e.g. concat_ws(\",\", coalesce(col(\"a\"), lit(\"\")))",
    ),
    (
        r"\bisnan\s*\(",
        "SPRKCNTSCL5007",
        0.7,
        "BD-8: Snowflake does not support NaN for float/double — isnan() values become NULL",
        "Replace isnan(col) with col.isNull",
    ),
    (
        r"\bregexp_replace\s*\(",
        "SPRKCNTSCL5008",
        0.5,
        "BD-9: regexp_replace uses Java regex in Spark but POSIX extended regex in Snowflake — lookahead/lookbehind not supported",
        r"Convert Java regex to POSIX: \d->[0-9], \w->[a-zA-Z0-9_], remove lookaheads",
    ),
    (
        r"\bgreatest\s*\(|\bleast\s*\(",
        "SPRKCNTSCL5009",
        0.6,
        "BD-10: greatest/least skip nulls in Spark (NULL only if all args null) but return NULL if any argument is null in Snowflake",
        "Wrap arguments with coalesce or filter nulls before applying greatest/least",
    ),
    (
        r"\bconcat\s*\(",
        "SPRKCNTSCL5010",
        0.6,
        "BD-11: concat skips nulls in Spark but returns NULL if any argument is null in Snowflake",
        "Wrap arguments with coalesce (same as BD-6)",
    ),
    (
        r"\bregexp_extract\s*\(",
        "SPRKCNTSCL5011",
        0.5,
        "BD-12: regexp_extract returns empty string on no-match in Spark but NULL in Snowflake",
        "Wrap with coalesce(regexp_extract(col, pattern, idx), lit(\"\"))",
    ),
    (
        r"\bfirst\s*\(|\blast\s*\(",
        "SPRKCNTSCL5012",
        0.5,
        "BD-13: first()/last() are non-deterministic in Snowflake without explicit ORDER BY in window",
        "Use Window.orderBy(...) with first()/last() for deterministic results",
    ),
    (
        r"\bround\s*\(|\bbround\s*\(",
        "SPRKCNTSCL5013",
        0.5,
        "BD-14: round() uses half-up rounding in Spark but half-even (banker's) rounding in Snowflake — round(2.5) is 3 vs 2",
        "For exact Spark behavior use conditional rounding: when(col % 1 === lit(0.5), ceil(col)).otherwise(round(col))",
    ),
    (
        r"\bexplode\s*\(|\bexplode_outer\s*\(|\bposexplode\s*\(",
        "SPRKCNTSCL5014",
        0.5,
        "BD-15: explode of null/empty arrays differs — Snowflake explode_outer requires FLATTEN(OUTER => TRUE)",
        "Use expr() with LATERAL FLATTEN(input => arr_col, OUTER => TRUE) for outer explode",
    ),
    (
        r"\bmonths_between\s*\(",
        "SPRKCNTSCL5016",
        0.5,
        "BD-17: months_between returns a fractional Double in Spark but a whole-month Integer in Snowflake",
        "Use expr(\"DATEDIFF('day', start_col, end_col) / 30.44\") if fractional precision is needed",
    ),
    (
        r"\.eqNullSafe\s*\(|<=>",
        "SPRKCNTSCL5017",
        0.5,
        "BD-18: null-safe equality (<=> / eqNullSafe) is not directly supported in Snowflake",
        "Use expr(\"EQUAL_NULL(a, b)\")",
    ),
    (
        r"\bsplit\s*\(",
        "SPRKCNTSCL5019",
        0.5,
        "BD-20: split() treats the delimiter as Java regex in Spark but as a literal string in Snowflake",
        r"Remove regex escaping for literal delimiters: split(col, \".\") not split(col, \"\\\\.\")",
    ),
    (
        r"\bapprox_count_distinct\s*\(",
        "SPRKCNTSCL5025",
        0.4,
        "BD-26: approx_count_distinct relative-standard-deviation precision is not configurable in Snowflake",
        "Drop the precision/rsd parameter; use COUNT(DISTINCT col) if exact control is needed",
    ),
    (
        r"\bdate_format\s*\(",
        "SPRKCNTSCL5026",
        0.6,
        "BD-27: date_format() token differences — Spark uses Java tokens (yyyy, HH, mm) while Snowflake uses SQL tokens (YYYY, HH24, MI)",
        "Translate tokens: yyyy->YYYY, HH->HH24, mm->MI, ss->SS, SSS->FF3",
    ),
    (
        r"\bcollect_list\s*\(|\bcollect_set\s*\(",
        "SPRKCNTSCL5027",
        0.5,
        "BD-28: collect_list/collect_set ordering is non-deterministic in Snowflake and nulls are excluded from array_agg by default",
        "Add explicit ordering if needed; filter null values manually before collecting",
    ),
    (
        r"\bbroadcast\s*\(|\.repartition\s*\(|\.coalesce\s*\(",
        "SPRKCNTSCL5028",
        0.4,
        "BD-29: distribution hints (broadcast/repartition/coalesce) may be silently ignored or cause errors in SCOS/Snowflake",
        "Remove distribution hints; add a // SCOS: TODO - verify broadcast/repartition behavior comment",
    ),
    # --- Previously undetected BDs (now flagged for human review) ---------
    (
        r'(?:col\([^)]*\)|\$"[^"]*")\s*/|\.divide\s*\(',
        "SPRKCNTSCL5000",
        0.7,
        "BD-1: a / 0 returns NULL silently in Spark (non-ANSI mode) but throws a 'Division by zero' error in Snowflake",
        "Guard divisions: when(col(\"b\") =!= lit(0), col(\"a\") / col(\"b\")).otherwise(lit(null))",
    ),
    (
        r"\.(?:asc|desc)\b",
        "SPRKCNTSCL5006",
        0.6,
        "BD-7: default NULL ordering is reversed — Spark ASC=nulls last / DESC=nulls first; Snowflake ASC=nulls first / DESC=nulls last",
        "Use explicit null ordering: col(\"x\").asc_nulls_last / col(\"y\").desc_nulls_first",
    ),
    (
        r'(?:===|=!=)\s*lit\(\s*"',
        "SPRKCNTSCL5015",
        0.4,
        "BD-16: string comparison is always binary/case-sensitive in Spark but collation-dependent (possibly case-insensitive) in Snowflake",
        "Make case handling explicit, e.g. upper(col(\"name\")) === lit(\"ABC\")",
    ),
    (
        r'\b(?:sum|count|avg|mean|min|max)\s*\(\s*(?:col\([^)]*\)|\$"[^"]*"|"[^"]*")\s*\)(?!\s*\.(?:alias|as|name)\b)',
        "SPRKCNTSCL5018",
        0.4,
        "BD-19: aggregation result columns are auto-named differently — Spark 'sum(revenue)' vs Snowflake upper-cased '\"SUM(REVENUE)\"'",
        "Always alias aggregations: agg(sum(col(\"revenue\")).alias(\"total_revenue\"))",
    ),
    (
        r'(?:col\([^)]*\)|\$"[^"]*")\s*/\s*(?:col\([^)]*\)|\$"[^"]*")',
        "SPRKCNTSCL5020",
        0.3,
        "BD-21: integer division returns a truncated int in Spark but a DECIMAL in Snowflake — result type/precision changes",
        "Wrap with floor() for truncated division: floor(col(\"a\") / col(\"b\"))",
    ),
    (
        r'\.cast\s*\(\s*"boolean"|\.cast\s*\(\s*BooleanType\b|(?i:\bas\s+boolean\b)',
        "SPRKCNTSCL5021",
        0.3,
        "BD-22: boolean casting from strings is more permissive in Snowflake (also accepts yes/no, on/off) than Spark",
        "Use explicit matching if strict true/false/1/0 parsing is required",
    ),
    (
        r"\b(?:substring|substr)\s*\(\s*[^,]+?,\s*0\b",
        "SPRKCNTSCL5022",
        0.4,
        "BD-23: substring position 0 is treated as 1 in Spark but returns an empty string in Snowflake",
        "Change the starting position from 0 to 1",
    ),
    (
        r"\.groupBy\s*\(",
        "SPRKCNTSCL5023",
        0.3,
        "BD-24: groupBy result ordering is truly non-deterministic in Snowflake (Spark is often incidentally consistent)",
        "Add an explicit orderBy after aggregation when ordering matters",
    ),
    (
        r"\bTimestampType\b|\bto_timestamp\s*\(|\bcurrent_timestamp\s*\(",
        "SPRKCNTSCL5024",
        0.3,
        "BD-25: timestamp precision differs — Spark microsecond vs Snowflake nanosecond",
        "Verify precision requirements; configure TIMESTAMP_OUTPUT_FORMAT if needed",
    ),
]

HIVE_DDL_PATTERNS = [
    (r"""(?i)\bspark\.sql\s*\(\s*["']MSCK\s+REPAIR\s+TABLE""", "MSCK REPAIR TABLE is Hive-specific and not supported in SCOS/Snowflake"),
    (r"""(?i)\bspark\.sql\s*\(\s*["']ALTER\s+TABLE\s+\S+\s+RECOVER\s+PARTITIONS""", "ALTER TABLE RECOVER PARTITIONS is Hive-specific and not supported in SCOS"),
    (r"""(?i)\bspark\.sql\s*\(\s*["']CREATE\s+(EXTERNAL\s+)?TABLE""", "Hive CREATE TABLE DDL may not be compatible with SCOS — use Snowflake SQL or DataFrame API"),
    (r"\.hadoopConfiguration\b", "sparkContext.hadoopConfiguration is not available in Spark Connect"),
    (r"\benableHiveSupport\b", "enableHiveSupport() is not available in SCOS — Hive metastore is not accessible"),
    (r"HiveContext\b", "HiveContext is not available in SCOS"),
    (
        r"""(?i)\bspark\.sql\s*\(\s*["']\s*USE\s+(DATABASE|SCHEMA|ROLE|WAREHOUSE)\b""",
        "spark.sql('USE ...') does not reliably update SCOS session context — use SnowflakeSession.useDatabase/useSchema/useRole/useWarehouse() instead (Rule 24)",
    ),
]


@dataclass
class ScalaCodeBlock:
    code: str
    line_start: int
    line_end: int
    block_type: str
    functions: list[str] = field(default_factory=list)
    cell_id: int | None = None  # Populated when block originates from a notebook cell
    # Language the block was authored in. Always "scala" for this analyzer;
    # present so downstream result rows can be merged with Python analyzer
    # output and filtered by language when a notebook mixes both.
    language: str = "scala"

    @property
    def normalized_code(self) -> str:
        return normalize_code_lightweight(self.code)


def find_scala_files(
    path: Path, notebook_index: dict[str, dict] | None = None
) -> list[Path]:
    """Find all Scala sources and notebooks under ``path``.

    Includes ``.scala`` files and every notebook format recognised by
    ``notebook_io``. Notebooks are filtered down to Scala-language cells by
    the extractor — Python / SQL / markdown cells are skipped here (handled
    by the Python sub-skill's analyzer or ignored, per cross-language rules).

    When ``notebook_index`` is provided (typically loaded from
    ``migration_state.json`` after Phase 0), notebook membership checks use
    the cached mapping instead of opening every candidate file.

    Additionally, when an index entry exposes ``code_cells_by_language``,
    notebooks with zero Scala code cells are excluded — the Scala analyzer
    would filter every cell out anyway, so we skip the notebook entirely to
    avoid the parse cost. Entries without that field are still included.
    """
    candidate_exts = {".scala", ".ipynb", ".python", ".py", ".sql"}

    def _index_entry(candidate: Path) -> dict | None:
        """Return the notebook_index entry for ``candidate``, if any."""
        if notebook_index is None:
            return None
        key = str(candidate)
        if key in notebook_index:
            return notebook_index[key]
        # The index is keyed by ``os.path.abspath(fpath)`` (see
        # ``notebook_io.scan_notebooks``), so we must match the same
        # normalization here. ``Path.resolve()`` would follow symlinks
        # and return the real path, which misses the abspath-keyed entry
        # whenever the workload is reached through a symlink.
        abs_key = os.path.abspath(key)
        if abs_key in notebook_index:
            return notebook_index[abs_key]
        return None

    def _is_notebook_cached(candidate: Path) -> bool:
        if notebook_index is not None:
            return _index_entry(candidate) is not None
        return is_notebook(str(candidate))

    def _has_scala_cells(candidate: Path) -> bool:
        """True if the notebook has >=1 Scala code cell, or if we don't know.

        Returning True when the index lacks ``code_cells_by_language`` keeps
        the optimization purely additive — we never drop notebooks on
        ambiguous input.
        """
        entry = _index_entry(candidate)
        if entry is None:
            return True
        counts = entry.get("code_cells_by_language")
        if not isinstance(counts, dict):
            return True
        return counts.get("scala", 0) > 0

    if path.is_file():
        if path.suffix.lower() == ".scala":
            return [path]
        if _is_notebook_cached(path) and _has_scala_cells(path):
            return [path]
        return []

    # Walk the tree once (filtered to skip .venv / __pycache__ / .git /
    # target / build / dist / node_modules) instead of running five
    # separate rglob passes per extension. walk_filtered prunes SKIP_DIRS
    # so sbt ``target/`` dirs full of compiled classfiles and generated
    # Scala never reach the notebook detector.
    results: list[Path] = []
    for root, _dirs, files in walk_filtered(str(path)):
        root_path = Path(root)
        for fname in files:
            ext = Path(fname).suffix.lower()
            if ext not in candidate_exts:
                continue
            candidate = root_path / fname
            if ext == ".scala":
                # .scala files may be plain Scala OR a Databricks exported-text
                # / native-JSON Scala notebook. Include them unconditionally —
                # plain .scala always has Scala, and a Scala-primary notebook
                # is almost always going to have Scala cells.
                results.append(candidate)
            elif _is_notebook_cached(candidate) and _has_scala_cells(candidate):
                results.append(candidate)
    return sorted(set(results))


def has_rdd_usage(code: str) -> tuple[bool, str | None]:
    for pattern in RDD_PATTERNS:
        if re.search(pattern, code):
            return True, f"Uses RDD pattern '{pattern}' which is not supported in SCOS"
    code_lower = code.lower()
    if ".rdd" in code_lower or "sparkcontext" in code_lower:
        for method in RDD_METHODS:
            if f".{method}(" in code:
                return True, f"RDD operation '.{method}()' is not supported in SCOS"
    return False, None


# RDD APIs with NO DataFrame equivalent — genuinely unsupported in Snowpark
# Connect (the client has no RDD layer): the .rdd accessor, partition
# introspection, partition-wise execution, SparkContext file ingestion,
# accumulator, and file-saving APIs with no equivalent.
_RDD_UNSUPPORTED_MARKERS = (
    ".rdd", ".javaRDD", ".toJavaRDD",
    "mapPartitions", "foreachPartition", "getNumPartitions", ".partitions",
    ".glom(", ".pipe(",
    "import org.apache.spark.rdd", "new SparkContext",
    "sc.textFile", "sc.wholeTextFiles", "sc.hadoopFile", "sc.hadoopRDD",
    "sc.newAPIHadoopFile", "sc.newAPIHadoopRDD", "sc.sequenceFile", "sc.objectFile",
    "sc.accumulator",
    "saveAsSequenceFile", "saveAsObjectFile",  # no equivalent in SCOS
)
# sc.parallelize / sc.emptyRDD have a supported createDataFrame equivalent.
_RDD_CONVERTIBLE_SOURCE_RE = re.compile(
    r"(?:sc|spark\.sparkContext)\.(?:parallelize|emptyRDD)\b"
)
# Key-based aggregation RDD ops that map cleanly onto DataFrame groupBy().agg().
# sortByKey / mapValues / flatMapValues removed — they need distinct guidance.
_RDD_PAIROP_METHODS = (
    "reduceByKey", "groupByKey", "aggregateByKey", "foldByKey",
    "combineByKey", "countByKey",
)
# Pair joins: RDD join ops → DataFrame join with an explicit key/join-type.
_RDD_PAIRJOIN_METHODS = (
    "leftOuterJoin", "rightOuterJoin", "fullOuterJoin", "cogroup", "cartesian",
    "subtractByKey",
)
# df.rdd.<METHOD>() where METHOD exists identically on DataFrame — drop the
# .rdd hop and call the method directly on the DataFrame. No closure needed.
# randomSplit intentionally excluded: df.randomSplit() is itself unsupported
# in SCOS (see UNSUPPORTED_DF_APIS) — route it to specific guidance instead.
_RDD_DROP_HOP_RE = re.compile(
    r"\.rdd\s*\.\s*(?:isEmpty|count|collect|first|take|toLocalIterator"
    r"|cache|persist|unpersist|union|distinct|intersection|subtract"
    r"|sample|repartition|coalesce)\b"
)


def _classify_rdd_usage(code: str) -> dict:
    """Bucket-aware guidance for an RDD-using block.

    * ``drop-the-hop`` — ``df.rdd.METHOD()`` where METHOD is available directly
      on DataFrame (no closure): drop the ``.rdd`` accessor and call the method
      on the DataFrame. Classified ``unsupported: False``.
    * ``unsupported`` — ``.rdd`` accessor used for partition introspection,
      ``mapPartitions``/``foreachPartition``, SparkContext file/accumulator APIs,
      saveAsSequenceFile/ObjectFile: no equivalent → annotate EWI + manual refactor.
    * ``convertible`` — specific patterns with supported DataFrame/hint forms.
    """
    # ── Drop-the-hop pre-check ────────────────────────────────────────────────
    # A block whose .rdd uses are ALL terminal methods that exist on DataFrame
    # directly is convertible without any closure analysis. Strip the matched
    # drop-hop calls; also strip bare .rdd used as arguments to those calls
    # (e.g. df1.rdd.union(df2.rdd) — both .rdd hops are dropped). If no bare
    # ".rdd" remains and no other unsupported marker is present, classify as
    # convertible. Mixed blocks (e.g. df.rdd.count() alongside df2.rdd.map(f))
    # fall through to unsupported conservatively.
    if _RDD_DROP_HOP_RE.search(code):
        stripped = _RDD_DROP_HOP_RE.sub("", code)
        # Also strip bare .rdd used as RDD arguments to the already-matched
        # drop-hop op (e.g. the second .rdd in df1.rdd.union(df2.rdd)).
        stripped = re.sub(r"\.rdd\s*(?=[,)\s]|$)", "", stripped)
        if ".rdd" not in stripped and not any(m in stripped for m in _RDD_UNSUPPORTED_MARKERS):
            return {
                "unsupported": False,
                "explanation": (
                    "The .rdd hop here leads to a method that exists directly on "
                    "DataFrame — drop the .rdd accessor and call the same method on "
                    "the DataFrame. No closure or RDD layer is needed."
                ),
                "fix": (
                    "Drop the .rdd accessor and call the method directly on the "
                    "DataFrame: df.rdd.count() \u2192 df.count(); df.rdd.isEmpty() \u2192 "
                    "df.isEmpty(); df.rdd.collect() \u2192 df.collect(); "
                    "df.rdd.first() \u2192 df.first(); df.rdd.take(n) \u2192 df.take(n); "
                    "df.rdd.toLocalIterator() \u2192 df.toLocalIterator(); "
                    "df.rdd.cache()/persist() \u2192 df.cache(); "
                    "df.rdd.unpersist() \u2192 df.unpersist(); "
                    "df.rdd.sample(wr,f) \u2192 df.sample(wr,f); "
                    "df1.rdd.union(df2.rdd) \u2192 df1.union(df2) (or unionByName); "
                    "df.rdd.distinct() \u2192 df.distinct(); "
                    "df1.rdd.intersection(df2.rdd) \u2192 df1.intersect(df2); "
                    "df1.rdd.subtract(df2.rdd) \u2192 df1.except(df2) (dedup) or "
                    "df1.exceptAll(df2) (multiset); "
                    "df.rdd.repartition(n) \u2192 df.repartition(n); "
                    "df.rdd.coalesce(n) \u2192 df.coalesce(n). "
                    "See references/scala/rdd-conversion.md Bucket B (drop-the-hop)."
                ),
            }

    # ── Genuinely unsupported ─────────────────────────────────────────────────
    if any(m in code for m in _RDD_UNSUPPORTED_MARKERS):
        return {
            "unsupported": True,
            "explanation": (
                "RDD / SparkContext APIs are not available in Snowpark Connect — "
                "the client has no RDD layer, so .rdd, partition introspection, "
                "mapPartitions/foreachPartition, SparkContext file APIs, "
                "sc.accumulator, and saveAsSequenceFile/ObjectFile have no equivalent."
            ),
            "fix": (
                "Annotate with EWI SPRKCNTSCL1500 and refactor manually using the "
                "DataFrame API. Do NOT fabricate an RDD shim (no nested "
                "createDataFrame, no Tuple1 wrapping, no .rdd re-introduction)."
            ),
        }

    # ── Convertible (specific recipes) ───────────────────────────────────────
    parts: list[str] = []

    if _RDD_CONVERTIBLE_SOURCE_RE.search(code):
        parts.append(
            "Replace sc.parallelize / sc.emptyRDD with spark.createDataFrame — Seq "
            "of tuples/case classes: createDataFrame(seq).toDF(names\u2026); Seq[Row] "
            "with a schema: createDataFrame(seq.asJava, schema). No Tuple1, no nesting."
        )
    if any(f".{m}(" in code for m in _RDD_PAIROP_METHODS):
        parts.append(
            "Rewrite grouping RDD ops: reduceByKey(_ + _) \u2192 groupBy(key).agg(sum(value)); "
            "groupByKey() \u2192 groupBy(key); countByKey() \u2192 groupBy(key).count(); "
            "aggregateByKey(z)(sf,cf) / foldByKey / combineByKey \u2192 groupBy(key).agg(...). "
            "See references/scala/rdd-conversion.md Bucket C."
        )
    if ".sortByKey(" in code:
        parts.append(
            "sortByKey() \u2192 df.orderBy(col(\"key\")); "
            "sortByKey(ascending=false) \u2192 df.orderBy(col(\"key\").desc). "
            "Replace the key column name with the actual column used as the pair key."
        )
    if ".sampleByKey(" in code:
        parts.append(
            "sampleByKey(withReplacement, fractions) \u2192 "
            "df.sampleBy(\"key\", fractions, seed). "
            "fractions is a Map[key, Double] in RDD; pass as a Column/Map in DataFrame."
        )
    if ".mapValues(" in code:
        parts.append(
            "mapValues(f) \u2192 df.withColumn(\"value\", <expr derived from closure f>). "
            "Translate the closure to a column expression: e.g. mapValues(_ * 2) \u2192 "
            "df.withColumn(\"value\", col(\"value\") * 2). "
            "First convert the parallelize source (above) so named columns exist."
        )
    if ".flatMapValues(" in code:
        parts.append(
            "flatMapValues(f) \u2192 df.withColumn(\"value\", <expr>).select(explode(col(\"value\"))). "
            "Translate f to a column expression that produces a collection, then explode."
        )
    if any(f".{m}(" in code for m in _RDD_PAIRJOIN_METHODS) or ".join(" in code:
        parts.append(
            "Rewrite RDD pair joins to DataFrame joins: "
            "rdd1.join(rdd2) \u2192 df1.join(df2, Seq(\"key\")); "
            "leftOuterJoin \u2192 df1.join(df2, Seq(\"key\"), \"left\"); "
            "rightOuterJoin \u2192 \"right\"; fullOuterJoin \u2192 \"outer\"; "
            "cartesian(rdd2) \u2192 df1.crossJoin(df2); "
            "cogroup(rdd2) \u2192 df1.join(df2, Seq(\"key\"), \"outer\") + collect_list per side; "
            "subtractByKey(rdd2) \u2192 df1.join(df2, Seq(\"key\"), \"left_anti\"). "
            "See references/scala/rdd-conversion.md Bucket C (pair joins)."
        )
    if ".keys(" in code:
        parts.append("keys() \u2192 df.select(col(\"key\")) (or the actual key column name).")
    if ".values(" in code:
        parts.append("values() \u2192 df.select(col(\"value\")) (or the actual value column name).")
    if ".takeOrdered(" in code:
        parts.append(
            "takeOrdered(n) \u2192 df.orderBy(col(\"key\").asc).limit(n).collect(). "
            "takeOrdered(n)(implicit ord) with a custom ordering \u2192 "
            "df.orderBy(<expr matching ord>).limit(n).collect()."
        )
    if ".top(" in code:
        parts.append(
            "top(n) \u2192 df.orderBy(col(\"key\").desc).limit(n).collect(). "
            "top(n)(implicit ord) with a custom ordering \u2192 "
            "df.orderBy(<expr matching ord reversed>).limit(n).collect()."
        )
    if ".zipWithIndex(" in code:
        parts.append(
            "zipWithIndex() \u2192 import org.apache.spark.sql.expressions.Window; "
            "val w = Window.orderBy(<deterministic_order_col>); "
            "df.withColumn(\"index\", row_number().over(w) - 1). "
            "NOTE: requires an explicit ordering column to be deterministic; "
            "the result is 0-based. If only a unique id is needed (not 0..N-1), "
            "prefer zipWithUniqueId \u2192 monotonically_increasing_id() instead."
        )
    if ".zipWithUniqueId(" in code:
        parts.append(
            "zipWithUniqueId() \u2192 df.withColumn(\"uid\", monotonically_increasing_id()). "
            "Produces unique but NOT contiguous ids; not stable across recompute/repartition."
        )
    if ".countByValue(" in code:
        parts.append(
            "countByValue() \u2192 df.groupBy(df.columns.map(col): _*).count().collect(). "
            "Or for a known column: df.groupBy(\"col\").count().collect()."
        )
    if ".saveAsTextFile(" in code:
        parts.append(
            "saveAsTextFile(path) \u2192 df.write.text(path). "
            "Use .mode(\"overwrite\") if the path may already exist."
        )
    if ".randomSplit(" in code:
        parts.append(
            "randomSplit(weights) — NOTE: df.randomSplit() is itself unsupported in SCOS. "
            "Alternative: call df.sample(fraction, seed) multiple times with complementary "
            "fractions, or add a random boolean column "
            "(df.withColumn(\"split\", rand() < fraction)) to partition logically."
        )
    if "sc.broadcast(" in code:
        parts.append(
            "sc.broadcast(v): for a scalar value use v directly (Snowpark Connect "
            "broadcasts small values automatically); for a join hint use "
            "df.hint(\"broadcast\") or import org.apache.spark.sql.functions.broadcast "
            "and wrap the DataFrame: broadcast(df)."
        )
    if not parts:
        parts.append("Convert to the DataFrame API (see references/scala/rdd-conversion.md).")
    return {
        "unsupported": False,
        "explanation": "RDD operations here have supported DataFrame equivalents in Snowpark Connect.",
        "fix": " ".join(parts),
    }


def check_unsupported_imports_scala(code: str) -> list[dict]:
    issues = []
    for module, info in UNSUPPORTED_IMPORTS.items():
        if f"import {module}" in code:
            issues.append({
                "api": module,
                "risk": info["risk"],
                "reason": info["reason"],
                "category": info["category"],
                # Exact unsupported import — a guaranteed divergence regardless of
                # context, so it can be emitted without LLM adjudication.
                "decidable": True,
            })
    return issues


def check_unsupported_formats_scala(code: str) -> list[dict]:
    issues = []
    code_lower = code.lower()
    for fmt, info in UNSUPPORTED_FORMATS.items():
        patterns = [f'.format("{fmt}")', f".format('{fmt}')"]
        for p in patterns:
            if p.lower() in code_lower:
                issues.append({
                    "format": fmt,
                    "risk": info["risk"],
                    "reason": info["reason"],
                    "category": info["category"],
                    "decidable": True,
                })
                break
    return issues


_DF_RECV_RE = re.compile(
    r"""(?:
        \b(?:df|dataFrame|dataset|spark)\b   # explicit spark/df vars
        |(?i:\w*[Dd]f\b|\w*[Dd]ataset\b|\w*[Dd]ataFrame\b)  # *Df / *Dataset / *DataFrame suffixes
    )""",
    re.VERBOSE,
)

# Methods that are genuinely unsupported on DataFrames but are perfectly fine
# on Scala stdlib types (String, Option, Map, Seq, Array, etc.).  Require a
# DataFrame-like receiver in the same code block before flagging them.
_DF_ONLY_METHODS = frozenset({"isEmpty"})


def check_noop_apis_scala(code: str) -> list[dict]:
    issues = []
    has_df_receiver = bool(_DF_RECV_RE.search(code))
    for method, info in NO_OP_APIS.items():
        if f".{method}(" in code:
            # For methods that are only unsupported on DataFrames, skip the
            # block entirely when there is no DataFrame-like receiver — avoids
            # false positives on String/Map/Option.isEmpty etc.
            if method in _DF_ONLY_METHODS and not has_df_receiver:
                continue
            issues.append({
                "api": method,
                "risk": info["risk"],
                "reason": info["reason"],
                "category": info["category"],
            })
    return issues


def check_hive_ddl_patterns_scala(code: str) -> list[dict]:
    issues = []
    for pattern, reason in HIVE_DDL_PATTERNS:
        if re.search(pattern, code):
            issues.append({
                "api": pattern,
                "risk": 0.9,
                "reason": reason,
                "category": "Unsupported Module",
                "decidable": True,
            })
    return issues


def check_unsupported_df_apis_scala(code: str) -> list[dict]:
    """Detect documented unsupported Dataset/DataFrame APIs (final_risk >= 0.7)."""
    issues = []
    for method, info in UNSUPPORTED_DF_APIS.items():
        # Use word-boundary aware pattern to avoid false positives
        if re.search(rf"\.{re.escape(method)}\b", code):
            issues.append({
                "api": method,
                "risk": info["risk"],
                "reason": info["reason"],
                "category": info["category"],
                "how_to_fix": info.get("how_to_fix"),
                "ewi_code": info.get("ewi_code"),
                "decidable": True,
            })
    return issues


def check_whole_file_unsupported_apis(
    file_path: Path, code: str
) -> list[dict]:
    """Scan the full file source for documented unsupported APIs.

    The block extractor only captures lines containing known Spark keywords.
    Calls like ``df.checkpoint()`` or ``df.isEmpty`` appear on lines without
    those keywords and are therefore missed by the per-block pipeline. This
    function performs a whole-file pass so those patterns are always flagged.

    Returns a list of result rows (same schema as ``analyze_file`` rows) for
    each unique API hit with ``final_risk >= 0.7``.
    """
    issues = check_unsupported_df_apis_scala(code)
    rows = []
    for issue in issues:
        if issue["risk"] < 0.7:
            continue
        # Find the first line that contains the method call for line reporting
        method = issue["api"]
        line_num = 1
        for i, line in enumerate(code.splitlines(), 1):
            if re.search(rf"\.{re.escape(method)}\b", line):
                line_num = i
                break
        rows.append({
            "file": str(file_path),
            "lines": f"{line_num}-{line_num}",
            "code": f".{method}(...)",
            "final_risk": issue["risk"],
            "root_cause": issue["reason"],
            "explanation": issue["reason"],
            "fix": issue.get("how_to_fix"),
            "suggested_fix": issue.get("how_to_fix"),
            "category": issue["category"],
            "confidence": "HIGH" if issue["risk"] >= 0.9 else "MEDIUM",
            "language": "scala",
        })
    return rows


def check_behavioral_differences_scala(code: str) -> list[dict]:
    """Detect behavioral difference patterns (BD-N from behavioral-differences.md)."""
    issues = []
    for pattern, ewi_code, risk, reason, how_to_fix in BEHAVIORAL_DIFFERENCE_PATTERNS:
        if re.search(pattern, code):
            issues.append({
                "api": pattern,
                "risk": risk,
                "reason": reason,
                "category": "Behavioral Difference",
                "how_to_fix": how_to_fix,
                "ewi_code": ewi_code,
            })
    return issues


def check_udf_patterns_scala(code: str) -> list[dict]:
    issues = []
    udf_patterns = [r"\.udf\b", r"spark\.udf\.register", r"functions\.udf\("]
    for p in udf_patterns:
        if re.search(p, code):
            issues.append({
                "api": "UDF",
                "risk": 0.5,
                "reason": (
                    "UDFs in Scala may have serialization issues on Snowflake's server-side worker. "
                    "Ensure all dependencies are self-contained or available in Snowflake's runtime."
                ),
                "category": "UDF Serialization",
            })
            break
    return issues


# --------------------------------------------------------------------------- #
# AST-facts-backed detection (Job 2)
#
# When the Scalameta extractor (scala_ast_facts.extract_facts) is available, the
# analyzer detects incompatibilities from AST facts instead of regex-scanning the
# raw block text. This eliminates the regex false-positives that match inside
# comments / string literals and handles multi-line constructs — the same
# precision PySpark gets from libcst.
#
# SCOPE: facts back every deterministic category that maps to AST nodes —
# unsupported imports, formats, Dataset APIs, no-op APIs, UDFs, RDD usage
# (structural), behavioral differences (call/member, infix operators, and
# arg-discriminated calls), and Hive-DDL (spark.sql DDL text + Hive member/ctor
# usage). The rule TABLES are reused verbatim, so each emitted issue dict (risk /
# reason / category / how_to_fix / ewi_code / decidable) is byte-identical to the
# regex detector's. The only residuals that still scan code are bare type-name
# references (TimestampType / BooleanType-as-text / HiveContext) and the
# negative-lookahead agg-without-alias context — non-call patterns that PySpark
# also handles by name/regex rather than AST. When facts are unavailable the
# analyzer falls back to the regex detectors verbatim — so the migrate flow never
# requires a JVM.
# --------------------------------------------------------------------------- #

# RDD member/import/ctor evidence, mirroring RDD_PATTERNS.
_RDD_MEMBERS = {"rdd", "javaRDD", "toJavaRDD", "sparkContext"}
_RDD_SC_CALLS = {"parallelize", "textFile", "hadoopRDD", "newAPIHadoopRDD",
                 "emptyRDD", "wholeTextFiles", "binaryFiles", "range"}
_RDD_IMPORT_PREFIXES = ("org.apache.spark.rdd", "org.apache.spark.SparkContext")


def _facts_in_range(file_facts: dict, lo: int, hi: int) -> dict:
    """Scope a file's AST facts to a block's 1-based line range [lo, hi].

    Mirrors the regex detectors, which run on ``block.code`` — so only facts on
    the block's own lines are considered (facts outside any block are not seen
    by either path, preserving parity).
    """
    def keep(items):
        return [x for x in (file_facts.get(items) or []) if lo <= x.get("line", -1) <= hi]
    return {
        "imports": keep("imports"),
        "calls": keep("calls"),
        "selects": keep("selects"),
        "new_types": keep("new_types"),
        "spark_sql": keep("spark_sql"),
    }


def has_rdd_usage_from_facts(facts: dict) -> tuple[bool, str | None]:
    """RDD/SparkContext detection from AST facts (mirrors has_rdd_usage)."""
    for s in facts.get("selects", []):
        if s.get("member") in _RDD_MEMBERS:
            return True, f"Uses RDD/SparkContext API '.{s['member']}' which is not supported in SCOS"
    for c in facts.get("calls", []):
        if c.get("recv_leaf") in ("sc", "sparkContext") and c.get("method") in _RDD_SC_CALLS:
            return True, f"Uses SparkContext API '{c['method']}' which is not supported in SCOS"
        if c.get("method") in _RDD_MEMBERS:
            return True, f"Uses RDD/SparkContext API '.{c['method']}' which is not supported in SCOS"
    for n in facts.get("new_types", []):
        if n.get("type") == "SparkContext":
            return True, "Uses 'new SparkContext' which is not supported in SCOS"
    for imp in facts.get("imports", []):
        if any(imp.get("ref", "").startswith(p) for p in _RDD_IMPORT_PREFIXES):
            return True, f"Imports '{imp['ref']}' (RDD/SparkContext) which is not supported in SCOS"
    return False, None


def check_scos_issues_from_facts(facts: dict) -> list[dict]:
    """Structural scos_issues from AST facts, reusing the rule tables verbatim.

    Produces the SAME issue dicts as the union of the regex detectors for:
    unsupported imports, formats, Dataset APIs, no-op APIs, and UDFs.
    """
    issues: list[dict] = []

    # Unsupported imports (mirrors check_unsupported_imports_scala).
    for imp in facts.get("imports", []):
        ref = imp.get("ref", "")
        for module, info in UNSUPPORTED_IMPORTS.items():
            if ref == module or ref.startswith(module + ".") or ref.startswith(module):
                issues.append({"api": module, "risk": info["risk"], "reason": info["reason"],
                               "category": info["category"], "decidable": True})
                break

    # Unsupported formats (mirrors check_unsupported_formats_scala).
    for c in facts.get("calls", []):
        if c.get("method") != "format":
            continue
        argl = [a.lower() for a in c.get("args", [])]
        for fmt, info in UNSUPPORTED_FORMATS.items():
            if fmt in argl:
                issues.append({"format": fmt, "risk": info["risk"], "reason": info["reason"],
                               "category": info["category"], "decidable": True})
                break

    # Unsupported Dataset/DataFrame APIs (mirrors check_unsupported_df_apis_scala).
    members = {c.get("method") for c in facts.get("calls", [])} | \
              {s.get("member") for s in facts.get("selects", [])}
    for method, info in UNSUPPORTED_DF_APIS.items():
        if method in members:
            issues.append({"api": method, "risk": info["risk"], "reason": info["reason"],
                           "category": info["category"], "how_to_fix": info.get("how_to_fix"),
                           "ewi_code": info.get("ewi_code"), "decidable": True})

    # No-op APIs (mirrors check_noop_apis_scala).
    call_methods = {c.get("method") for c in facts.get("calls", [])}
    for method, info in NO_OP_APIS.items():
        if method in call_methods:
            issues.append({"api": method, "risk": info["risk"], "reason": info["reason"],
                           "category": info["category"]})

    # UDF (mirrors check_udf_patterns_scala — emits at most one issue).
    udf_hit = (
        any(c.get("method") == "udf" for c in facts.get("calls", []))
        or any(c.get("method") == "register" and c.get("recv_leaf") == "udf"
               for c in facts.get("calls", []))
        or any(s.get("member") == "udf" for s in facts.get("selects", []))
    )
    if udf_hit:
        issues.append({
            "api": "UDF", "risk": 0.5,
            "reason": ("UDFs in Scala may have serialization issues on Snowflake's server-side worker. "
                       "Ensure all dependencies are self-contained or available in Snowflake's runtime."),
            "category": "UDF Serialization",
        })

    return issues


# Behavioral-difference patterns that map to a call/member NAME (Tier 1). Each
# fires when the name appears as a Scala call/member (AST fact) OR inside a SQL /
# expr string (regex over the extracted SQL text — parity with the regex path
# and with PySpark's `python_or_sql` KB rules). Patterns NOT listed here are
# operator/type/context based and stay on the regex path until later tiers.
_BD_CALL_TRIGGERS: dict[str, frozenset[str]] = {
    "SPRKCNTSCL5001": frozenset({"cast"}),
    "SPRKCNTSCL5002": frozenset({"datediff"}),
    "SPRKCNTSCL5003": frozenset({"union"}),
    "SPRKCNTSCL5004": frozenset({"element_at"}),
    "SPRKCNTSCL5005": frozenset({"concat_ws"}),
    "SPRKCNTSCL5007": frozenset({"isnan"}),
    "SPRKCNTSCL5008": frozenset({"regexp_replace"}),
    "SPRKCNTSCL5009": frozenset({"greatest", "least"}),
    "SPRKCNTSCL5010": frozenset({"concat"}),
    "SPRKCNTSCL5011": frozenset({"regexp_extract"}),
    "SPRKCNTSCL5012": frozenset({"first", "last"}),
    "SPRKCNTSCL5013": frozenset({"round", "bround"}),
    "SPRKCNTSCL5014": frozenset({"explode", "explode_outer", "posexplode"}),
    "SPRKCNTSCL5016": frozenset({"months_between"}),
    "SPRKCNTSCL5019": frozenset({"split"}),
    "SPRKCNTSCL5025": frozenset({"approx_count_distinct"}),
    "SPRKCNTSCL5026": frozenset({"date_format"}),
    "SPRKCNTSCL5027": frozenset({"collect_list", "collect_set"}),
    "SPRKCNTSCL5028": frozenset({"broadcast", "repartition", "coalesce"}),
    "SPRKCNTSCL5023": frozenset({"groupBy"}),
    "SPRKCNTSCL5006": frozenset({"asc", "desc"}),
}

# Call methods whose string arguments carry SQL / expression text the regex
# behavioral patterns are meant to scan (alongside spark.sql(...)).
_BD_SQL_METHODS = frozenset({"sql", "expr", "selectExpr", "filter", "where",
                             "when", "otherwise", "agg", "withColumn"})

# Behavioral patterns driven by infix operators (Tier 2). Detected from the
# `infix` AST facts (op + bounded operand syntax) instead of regex-over-code.
_BD_INFIX_EWIS = frozenset({
    "SPRKCNTSCL5000", "SPRKCNTSCL5015", "SPRKCNTSCL5017", "SPRKCNTSCL5020",
})
# Operand-shape probes mirror the original regex operand fragments: a column
# immediately before `/`, a column right after `/`, a `lit("...")` after ===.
_BD_COL_TAIL = re.compile(r'(?:col\([^)]*\)|\$"[^"]*")\s*$')
_BD_COL_HEAD = re.compile(r'^\s*(?:col\([^)]*\)|\$"[^"]*")')
_BD_LIT_STR_HEAD = re.compile(r'^\s*lit\(\s*"')

# Arg-discriminated behavioral patterns (Tier 3): call is the AST spine, the
# discriminator is an argument value/type. Detected by reconstructing the call
# text from AST arg facts and applying the ORIGINAL regex (guarantees parity,
# drops comment/string false positives). 5021 cast-to-boolean, 5022 substring-0.
_BD_SYNTH_EWIS = frozenset({"SPRKCNTSCL5021", "SPRKCNTSCL5022"})


def _behavioral_synth_text(facts: dict) -> str:
    """Reconstruct call text (`.m(args)` and `m(args)`) from AST arg facts so the
    arg-discriminated regexes match exactly as on real code, minus comment FPs."""
    parts: list[str] = []
    for c in facts.get("calls", []):
        m = c.get("method") or ""
        inner = ", ".join(c.get("arg_exprs") or [])
        parts.append(f".{m}({inner})")
        parts.append(f"{m}({inner})")
    return "\n".join(parts)


def _behavioral_infix_ewis(facts: dict) -> set[str]:
    """EWIs among {5000,5015,5017,5020} that fire from infix-operator AST facts."""
    fired: set[str] = set()
    for ix in facts.get("infix", []):
        op = ix.get("op")
        lhs = ix.get("lhs", "")
        rhs = ix.get("rhs", "")
        if op == "/":
            if _BD_COL_TAIL.search(lhs):
                fired.add("SPRKCNTSCL5000")           # column / anything
                if _BD_COL_HEAD.search(rhs):
                    fired.add("SPRKCNTSCL5020")        # column / column
        elif op == "<=>":
            fired.add("SPRKCNTSCL5017")
        elif op in ("===", "=!="):
            if _BD_LIT_STR_HEAD.search(rhs):
                fired.add("SPRKCNTSCL5015")
    call_methods = {c.get("method") for c in facts.get("calls", [])}
    if "divide" in call_methods:
        fired.add("SPRKCNTSCL5000")
    if "eqNullSafe" in call_methods:
        fired.add("SPRKCNTSCL5017")
    return fired


def check_behavioral_from_facts(facts: dict, code: str) -> list[dict]:
    """AST-facts behavioral-difference detection (mirrors check_behavioral_differences_scala).

    Migrated patterns fire from AST facts: call/member names (Tier 1) or infix
    operators (Tier 2), plus a regex over the extracted SQL/expr text (the hybrid
    PySpark uses for its ``python_or_sql`` rules). Patterns not yet migrated to
    facts fall back to the original regex over ``code`` — so no behavioral pattern
    is ever dropped.
    """
    call_or_member = {c.get("method") for c in facts.get("calls", [])} | \
                     {s.get("member") for s in facts.get("selects", [])}
    sql_parts = [s.get("text", "") for s in facts.get("spark_sql", [])]
    for c in facts.get("calls", []):
        if c.get("method") in _BD_SQL_METHODS:
            sql_parts.extend(c.get("args", []))
    sql_text = "\n".join(sql_parts)
    infix_ewis = _behavioral_infix_ewis(facts)
    synth_text = _behavioral_synth_text(facts) + "\n" + sql_text

    issues: list[dict] = []
    for pattern, ewi_code, risk, reason, how_to_fix in BEHAVIORAL_DIFFERENCE_PATTERNS:
        trigger = _BD_CALL_TRIGGERS.get(ewi_code)
        if trigger is not None:
            fires = bool(trigger & call_or_member) or bool(re.search(pattern, sql_text))
        elif ewi_code in _BD_INFIX_EWIS:
            fires = ewi_code in infix_ewis
        elif ewi_code in _BD_SYNTH_EWIS:
            fires = bool(re.search(pattern, synth_text))
        else:
            # Residual (bare type-name ref / chain-context patterns) — regex over
            # code, matching how PySpark itself handles these non-call patterns.
            fires = bool(re.search(pattern, code))
        if fires:
            issues.append({
                "api": pattern,
                "risk": risk,
                "reason": reason,
                "category": "Behavioral Difference",
                "how_to_fix": how_to_fix,
                "ewi_code": ewi_code,
            })
    return issues


def check_hive_from_facts(facts: dict, code: str) -> list[dict]:
    """AST-facts Hive-DDL detection (mirrors check_hive_ddl_patterns_scala).

    SQL DDL patterns (MSCK/ALTER RECOVER/CREATE TABLE/USE) are matched against
    `spark.sql("...")` text reconstructed from spark_sql facts — same regex, but
    only over genuine SQL (no comment/string FPs). `enableHiveSupport` and
    `hadoopConfiguration` fire from call/member facts. `HiveContext` (a bare
    type-name reference) stays a regex over code, matching how PySpark handles
    non-call type references.
    """
    synth_sql = "\n".join(
        f'spark.sql("{s.get("text", "")}")' for s in facts.get("spark_sql", [])
    )
    members = {c.get("method") for c in facts.get("calls", [])} | \
              {s.get("member") for s in facts.get("selects", [])}
    issues: list[dict] = []
    for pattern, reason in HIVE_DDL_PATTERNS:
        if "spark" in pattern and "sql" in pattern:
            fires = bool(re.search(pattern, synth_sql))
        elif "hadoopConfiguration" in pattern:
            fires = "hadoopConfiguration" in members
        elif "enableHiveSupport" in pattern:
            fires = "enableHiveSupport" in members
        else:  # HiveContext — bare type-name reference
            fires = bool(re.search(pattern, code))
        if fires:
            issues.append({
                "api": pattern,
                "risk": 0.9,
                "reason": reason,
                "category": "Unsupported Module",
                "decidable": True,
            })
    return issues


# Known leading magic directives that can precede Scala cell source.
# We replace the line with a ``// <preserved magic>`` placeholder so the
# downstream line-based heuristics never see the directive AND original line
# numbers are preserved 1:1.
_KNOWN_MAGIC_PREFIXES = (
    "%python", "%scala", "%sql", "%r", "%md", "%sh", "%fs", "%run", "%pyspark",
)


def _strip_leading_magic_directive(source: str) -> str:
    """Replace an optional leading ``%magic`` line with a ``//`` placeholder.

    The directive is replaced in place so line numbers reported by the Scala
    block extractor line up 1:1 with the original cell source.

    Unknown leading ``%`` lines are still replaced (so the heuristic
    line-based extractor doesn't mistake them for Scala syntax) but are
    annotated in the placeholder for traceability.
    """
    if not source:
        return source
    lines = source.split("\n", 1)
    first = lines[0].lstrip()
    rest = lines[1] if len(lines) > 1 else ""
    if not first.startswith("%") or first.startswith("%%"):
        return source

    first_word = first.split(None, 1)[0]
    is_known = any(first_word.startswith(prefix) for prefix in _KNOWN_MAGIC_PREFIXES)
    suffix = f" {first.strip()}" if not is_known else ""
    placeholder = f"// magic_directive_preserved:{first_word}{suffix}"
    if rest:
        return placeholder + "\n" + rest
    return placeholder


def _extract_scala_blocks_from_source(
    source: str,
    cell_id: int | None = None,
) -> list[ScalaCodeBlock]:
    """Run the line-based heuristic extractor on an in-memory Scala source.

    Returns blocks whose ``line_start`` / ``line_end`` are 1-based offsets
    within ``source`` (or within the cell for notebook cells, matching the
    ``cell:<id>:<line>`` convention).
    """
    analysis_source = _strip_leading_magic_directive(source)
    lines = analysis_source.splitlines()
    blocks: list[ScalaCodeBlock] = []

    spark_keywords = {
        "spark.", "session.", ".read", ".write", ".sql(", ".select(",
        ".filter(", ".where(", ".groupBy(", ".agg(", ".join(",
        ".withColumn(", ".drop(", ".show(", ".collect(",
        ".format(", ".load(", ".save(", ".option(",
        "SparkSession", "SparkContext", "SparkConf",
        "import org.apache.spark",
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if not stripped or stripped.startswith("//") or stripped.startswith("/*"):
            i += 1
            continue

        if any(kw in line for kw in spark_keywords):
            block_start = i
            block_lines = [line]

            # Accumulate continuation lines (chained method calls, open braces).
            j = i + 1
            while j < len(lines):
                next_line = lines[j].strip()
                prev_stripped = block_lines[-1].strip()
                if (
                    prev_stripped.endswith(".")
                    or prev_stripped.endswith(",")
                    or prev_stripped.endswith("{")
                    or prev_stripped.endswith("(")
                    or next_line.startswith(".")
                    or next_line.startswith(")")
                ):
                    block_lines.append(lines[j])
                    j += 1
                else:
                    break

            code = "\n".join(block_lines)
            funcs = list(set(re.findall(r"\.(\w+)\s*\(", code)))

            blocks.append(ScalaCodeBlock(
                code=code,
                line_start=block_start + 1,
                line_end=block_start + len(block_lines),
                block_type="statement",
                functions=funcs,
                cell_id=cell_id,
            ))
            i = j
        else:
            i += 1

    return blocks


def extract_scala_blocks(file_path: Path) -> list[ScalaCodeBlock]:
    """Extract code blocks from a Scala file or notebook.

    For notebooks, only Scala-language cells are extracted (per cross-language
    delegation rules — Python/SQL/markdown cells are handled elsewhere).
    Blocks from notebook cells carry ``cell_id`` so downstream reports tag
    them as ``cell:<id>:<line>``.
    """
    path_str = str(file_path)
    # Capture detection once and pass through to parse_notebook so the
    # notebook's 4 KiB head isn't re-read inside parse_notebook.
    info = detect_format(path_str)
    if info.get("format") != "not_notebook":
        try:
            nb = parse_notebook(path_str, info=info)
        except (ValueError, OSError) as e:
            logger.warning(f"Warning: Could not parse notebook {file_path}: {e}")
            return []

        blocks: list[ScalaCodeBlock] = []
        for cell in nb.cells:
            if cell.cell_type != "code":
                continue
            if cell.cell_language != "scala":
                continue
            blocks.extend(_extract_scala_blocks_from_source(cell.source, cell_id=cell.index))
        return blocks

    try:
        source = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return _extract_scala_blocks_from_source(source)


def _process_single_block(
    block: ScalaCodeBlock,
    scos_rag: BaseRAG,
    file_path: Path,
    similarity_threshold: float,
    safe_apis: set[str] | None = None,
    block_facts: dict | None = None,
    cond_verdicts: dict[str, str] | None = None,
) -> tuple[dict | None, dict | None]:
    # RDD detection: AST facts when available (no comment/string false positives),
    # else regex. _classify_rdd_usage stays on block.code (it shapes the guidance
    # text, not the detection).
    if block_facts is not None:
        is_rdd, rdd_reason = has_rdd_usage_from_facts(block_facts)
    else:
        is_rdd, rdd_reason = has_rdd_usage(block.code)
    if is_rdd:
        guidance = _classify_rdd_usage(block.code)
        result = {
            "file": str(file_path),
            "lines": f"{block.line_start}-{block.line_end}",
            "code": block.code,
            "final_risk": 1.0,
            "root_cause": rdd_reason,
            "explanation": guidance["explanation"],
            "fix": guidance["fix"],
            "suggested_fix": guidance["fix"],
            "category": "RDD",
            "ewi_code": "SPRKCNTSCL1500",
            "unsupported": guidance["unsupported"],
            "confidence": "HIGH",
        }
        if block.cell_id is not None:
            result["cell_id"] = block.cell_id
        result["language"] = block.language
        return (result, None)

    # Structural detection (imports / formats / Dataset APIs / no-op / UDF):
    # AST facts when available, else regex. Hive-DDL and behavioral-difference
    # patterns are operator/SQL-string detectors that stay on regex either way.
    if block_facts is not None:
        structural_issues = check_scos_issues_from_facts(block_facts)
    else:
        structural_issues = (
            check_unsupported_imports_scala(block.code)
            + check_unsupported_formats_scala(block.code)
            + check_noop_apis_scala(block.code)
            + check_udf_patterns_scala(block.code)
            + check_unsupported_df_apis_scala(block.code)
        )
    if block_facts is not None:
        hive_issues = check_hive_from_facts(block_facts, block.code)
        bd_issues = check_behavioral_from_facts(block_facts, block.code)
    else:
        hive_issues = check_hive_ddl_patterns_scala(block.code)
        bd_issues = check_behavioral_differences_scala(block.code)

    scos_issues = structural_issues + hive_issues + bd_issues
    scos_risk = max((i["risk"] for i in scos_issues), default=0)

    # Safe-API fast path: a block whose every method call is on the
    # result-identical allowlist and that raised no deterministic scos_issue is
    # compatible on SCOS — skip the RAG/LLM round-trip entirely (the
    # compatible-side complement to the decidable-failure bypass).
    if not scos_issues and is_block_safe(block.functions, safe_apis or set()):
        return None, None

    prediction = scos_rag.predict_failure(block.normalized_code)
    candidates = []
    for p in prediction.get("similar_patterns", []):
        if p.root_cause:
            candidates.append({
                "source": "UNIFIED_RAG",
                "code": p.code,
                "score": p.score,
                "root_cause": p.root_cause,
                "test_name": p.test_name,
                "additional_notes": p.additional_notes,
            })

    candidates.sort(key=lambda x: x["score"], reverse=True)
    candidates = [c for c in candidates if c["score"] >= similarity_threshold]

    # Condition-aware resolution: drop false-positive candidates whose condition
    # is provably unmet (cleared), mark confirmed ones decidable (skip LLM).
    if cond_verdicts and candidates:
        filtered = []
        for c in candidates:
            blob = ((c.get("code") or "") + " " + (c.get("root_cause") or "")
                    + " " + (c.get("test_name") or "")).lower()
            matched_fn = next(
                (fn for fn in cond_verdicts if re.search(r"\b" + re.escape(fn) + r"\b", blob)),
                None,
            )
            if matched_fn is None:
                filtered.append(c)
            elif cond_verdicts[matched_fn] == "cleared":
                pass  # condition provably unmet → drop
            else:
                if cond_verdicts[matched_fn] == "met":
                    c["decidable"] = True
                filtered.append(c)
        candidates = filtered

    matching_patterns = []
    failure_likelihood = 0.0
    if candidates:
        best_match = candidates[0]
        failure_likelihood = best_match["score"]
        matching_patterns.append(best_match)
        relative_threshold = failure_likelihood * 0.85
        for c in candidates[1:]:
            if len(matching_patterns) >= 3:
                break
            if c["score"] >= relative_threshold:
                matching_patterns.append(c)

    if not scos_issues and not matching_patterns:
        return None, None

    preliminary_risk = max(failure_likelihood, scos_risk)
    preliminary_assessment = {
        "scos_issues": scos_issues,
        "scos_risk": scos_risk,
        "rag_similarity": failure_likelihood,
    }

    return (
        None,
        {
            "block": block,
            "matching_patterns": matching_patterns,
            "preliminary_assessment": preliminary_assessment,
            "preliminary_risk": preliminary_risk,
            "scos_issues": scos_issues,
            "scos_risk": scos_risk,
            "failure_likelihood": failure_likelihood,
        },
    )


def _build_assessment_text(preliminary_assessment: dict) -> str:
    parts = []
    scos_issues = preliminary_assessment.get("scos_issues", [])
    if scos_issues:
        parts.append("SCOS Compatibility Issues:")
        for issue in scos_issues:
            name = issue.get("api") or issue.get("format", "unknown")
            parts.append(f"  - {name}: {issue['reason']} (Risk: {issue['risk'] * 100:.0f}%)")
    scos_risk = preliminary_assessment.get("scos_risk", 0)
    if scos_risk > 0:
        parts.append(f"\nSCOS Issues Risk: {scos_risk * 100:.0f}%")
    return "\n".join(parts) if parts else "No rule-based issues detected."


def _build_patterns_text(matching_patterns: list[dict]) -> str:
    if not matching_patterns:
        return "No similar failing test cases found above similarity threshold."
    parts = []
    for i, p in enumerate(matching_patterns, 1):
        parts.append(
            f"TEST CASE #{i} (Cosine similarity: {p.get('score', 0.0):.1%})\n"
            f"Test Name: {p.get('test_name', 'N/A')}\n"
            f"Code/SQL:\n```\n{p.get('code', '')}\n```\n"
            f"Root Cause: {p.get('root_cause', 'N/A')}\n"
            f"Additional Notes: {p.get('additional_notes', 'N/A')}"
        )
    return "\n\n".join(parts)


def predict_compatibility_batch(
    session: Session,
    batch_items: list[dict],
    model: str = DEFAULT_LLM_MODEL,
) -> dict[str, dict]:
    if cortex_complete is None or CompleteOptions is None:
        raise RuntimeError(
            "Batch LLM prediction failed: snowflake.cortex module is not installed"
        )
    if not batch_items:
        return {}

    code_blocks_parts = []
    for item in batch_items:
        assessment_text = _build_assessment_text(item.get("preliminary_assessment", {}))
        patterns_text = _build_patterns_text(item.get("matching_patterns", []))
        code_blocks_parts.append(
            f"### BLOCK {item['block_id']}\n\n```scala\n{item['input_code']}\n```\n\n"
            f"**Preliminary Assessment:**\n{assessment_text}\n\n"
            f"**Similar Failing Test Cases:**\n{patterns_text}\n\n---"
        )

    prompt = PROMPT_PREDICT_COMPATIBILITY_BATCH.format(
        code_blocks_text="\n\n".join(code_blocks_parts),
        num_blocks=len(batch_items),
    )

    try:
        options = CompleteOptions(temperature=0.0)
        response = cortex_complete(model, prompt, options=options, session=session)
        response = response.strip()
        if response.startswith("```"):
            lines = response.split("\n")
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            response = "\n".join(lines)

        results_list = json.loads(response)
        results_dict = {}
        for result in results_list:
            bid = result.get("block_id")
            if bid:
                results_dict[bid] = result
        return results_dict
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON from LLM: {response[:500]}...\nError: {e}")
    except Exception as e:
        raise RuntimeError(f"Batch LLM prediction failed: {e}")


_BATCH_MAX_RETRIES = 3


def predict_compatibility_batch_with_retry(
    session,
    batch_items,
    max_retries=_BATCH_MAX_RETRIES,
    *,
    require_llm: bool = False,
):
    """Wrapper with exponential backoff for transient LLM/network failures."""
    import time as _time
    for attempt in range(max_retries):
        try:
            return predict_compatibility_batch(session, batch_items)
        except (RuntimeError, ValueError) as exc:
            if is_non_retryable_llm_error(exc):
                logger.error("Batch LLM failed with non-retryable error: %s", exc)
                raise
            if attempt < max_retries - 1:
                delay = 5 * (2 ** attempt)
                logger.warning("Batch LLM attempt %d/%d failed: %s — retrying in %ds", attempt + 1, max_retries, exc, delay)
                _time.sleep(delay)
            else:
                if require_llm:
                    logger.error(
                        "Batch LLM failed after %d attempts in required LLM mode: %s",
                        max_retries,
                        exc,
                    )
                    raise
                logger.error(
                    "Batch LLM failed after %d attempts: %s — returning empty results",
                    max_retries,
                    exc,
                )
                return {}


def _block_is_fully_decidable_scala(item: dict) -> bool:
    """True when a block's findings can be emitted WITHOUT LLM adjudication.

    Mirrors ``analyze_pyspark._block_is_fully_decidable``: the bypass is
    deliberately conservative. It fires only when the block has at least one
    deterministic ``scos_issue``, EVERY ``scos_issue`` is a structurally-decidable
    exact trigger (an unsupported import/format/module or unsupported Dataset API
    — categories tagged ``decidable=True`` at their source), and there is no fuzzy
    RAG ``matching_patterns`` evidence. A single non-decidable issue (e.g. a
    behavioral-difference or UDF pattern) or any fuzzy match sends the whole block
    to the LLM as before.

    Decidability is independent of severity: a guaranteed unsupported API is a
    certain true positive even at low curated risk, whereas a behavioral pattern
    that merely matched a token is NOT decidable regardless of severity.
    """
    if item.get("matching_patterns"):
        return False
    scos_issues = item.get("scos_issues") or []
    if not scos_issues:
        return False
    return all(i.get("decidable") for i in scos_issues)


def _build_decidable_result_scala(
    file_path: Path, item: dict, risk_threshold: float
) -> dict | None:
    """Build a finished issue row for a fully-decidable block, in the same shape
    ``analyze_file`` produces for the LLM path. Returns None when the curated risk
    is below ``risk_threshold`` (treated as compatible and dropped).
    """
    block = item["block"]
    top_issue = max(item["scos_issues"], key=lambda x: x["risk"])
    final_risk = top_issue["risk"]
    if final_risk < risk_threshold:
        return None
    root_cause = top_issue["reason"]
    how_to_fix = top_issue.get("how_to_fix")
    row = {
        "file": str(file_path),
        "lines": f"{block.line_start}-{block.line_end}",
        "code": block.code,
        "final_risk": final_risk,
        "root_cause": root_cause,
        "explanation": f"Potential compatibility issue: {root_cause}",
        "fix": how_to_fix,
        "suggested_fix": how_to_fix,
        "category": top_issue.get("category"),
        # Decidable triggers are guaranteed divergences, so confidence is HIGH.
        "confidence": "HIGH",
        # Provenance: emitted deterministically from the exact-trigger tables, no LLM.
        "source": "trigger_decidable",
    }
    ewi_code = top_issue.get("ewi_code")
    if ewi_code:
        row["ewi_code"] = ewi_code
    if block.cell_id is not None:
        row["cell_id"] = block.cell_id
    row["language"] = block.language
    return row


def _partition_decidable_blocks_scala(
    blocks_to_analyze: list[dict], file_path: Path, risk_threshold: float
) -> tuple[list[dict], list[dict]]:
    """Split a file's flagged blocks into ``(decidable_results, remaining)``.

    ``decidable_results`` are finished issue rows emitted without the LLM;
    ``remaining`` still need LLM adjudication and stay on the batch path.
    """
    decidable_results: list[dict] = []
    remaining: list[dict] = []
    for item in blocks_to_analyze:
        if not _block_is_fully_decidable_scala(item):
            remaining.append(item)
            continue
        row = _build_decidable_result_scala(file_path, item, risk_threshold)
        if row is not None:
            decidable_results.append(row)
        # else: below threshold — treated as compatible, dropped silently.
    return decidable_results, remaining


def analyze_file(
    scos_rag: BaseRAG,
    file_path: Path,
    risk_threshold: float = 0.1,
    session: Session | None = None,
    similarity_threshold: float = 0.55,
    llm_batch_size: int = DEFAULT_LLM_BATCH_SIZE,
    parallel_workers: int = DEFAULT_PARALLEL_WORKERS,
    require_llm: bool = False,
    safe_apis: set[str] | None = None,
    file_facts: dict | None = None,
) -> list[dict]:
    results = []

    # Whole-file pass for documented unsupported APIs (final_risk >= 0.7).
    # The block extractor only captures lines with known Spark keywords; APIs
    # like df.checkpoint() / df.isEmpty appear on lines that would otherwise be
    # skipped. Running a full-source scan guarantees they are always flagged.
    try:
        full_source = file_path.read_text(encoding="utf-8")
        whole_file_rows = check_whole_file_unsupported_apis(file_path, full_source)
        for row in whole_file_rows:
            if row["final_risk"] >= risk_threshold:
                results.append(row)
    except OSError:
        pass

    blocks = extract_scala_blocks(file_path)
    if not blocks:
        return results

    blocks_to_analyze = []

    cond_verdicts = _condition_verdicts_for_file(file_facts) if file_facts else {}

    with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
        future_to_block = {
            executor.submit(
                _process_single_block, block, scos_rag, file_path, similarity_threshold, safe_apis,
                _facts_in_range(file_facts, block.line_start, block.line_end) if file_facts is not None else None,
                cond_verdicts or None,
            ): block
            for block in blocks
        }
        for future in as_completed(future_to_block):
            block = future_to_block[future]
            try:
                rdd_result, block_data = future.result()
                if rdd_result is not None:
                    results.append(rdd_result)
                elif block_data is not None:
                    blocks_to_analyze.append(block_data)
            except Exception as e:
                logger.error(f"Error processing block at lines {block.line_start}-{block.line_end}: {e}")
                raise

    # Bypass the LLM for fully-decidable blocks (exact unsupported triggers with
    # no fuzzy RAG evidence): emit them deterministically and send only the
    # genuinely ambiguous remainder to the batch LLM below.
    decidable_results, blocks_to_analyze = _partition_decidable_blocks_scala(
        blocks_to_analyze, file_path, risk_threshold
    )
    results.extend(decidable_results)

    import time as _time
    llm_results = {}

    if session and blocks_to_analyze:
        total_blocks = len(blocks_to_analyze)
        num_batches = (total_blocks + llm_batch_size - 1) // llm_batch_size
        logger.info(f"    Running LLM analysis: {total_blocks} blocks in {num_batches} batch(es)...")

        all_batch_items = []
        for batch_idx in range(0, total_blocks, llm_batch_size):
            batch = blocks_to_analyze[batch_idx:batch_idx + llm_batch_size]
            batch_num = batch_idx // llm_batch_size + 1
            batch_items = []
            for item in batch:
                block = item["block"]
                block_id = f"{block.line_start}-{block.line_end}"
                batch_items.append({
                    "block_id": block_id,
                    "input_code": block.normalized_code,
                    "matching_patterns": item["matching_patterns"],
                    "preliminary_assessment": item["preliminary_assessment"],
                })
            all_batch_items.append((batch_num, batch_items))

        def _process_batch(args):
            batch_num, batch_items = args
            _start = _time.time()
            result = predict_compatibility_batch_with_retry(
                session,
                batch_items,
                require_llm=require_llm,
            )
            _elapsed = _time.time() - _start
            return batch_num, result, _elapsed

        _llm_start = _time.time()
        with ThreadPoolExecutor(max_workers=parallel_workers) as executor:
            futures = {
                executor.submit(_process_batch, batch): batch[0]
                for batch in all_batch_items
            }
            for future in as_completed(futures):
                batch_num, batch_result, elapsed = future.result()
                logger.info(f"      Batch {batch_num}/{num_batches}: completed in {elapsed:.1f}s")
                llm_results.update(batch_result)

    for item in blocks_to_analyze:
        block = item["block"]
        block_id = f"{block.line_start}-{block.line_end}"
        matching_patterns = item["matching_patterns"]
        preliminary_risk = item["preliminary_risk"]
        scos_issues = item["scos_issues"]
        scos_risk = item["scos_risk"]
        failure_likelihood = item["failure_likelihood"]

        llm_result = llm_results.get(block_id)
        final_risk = preliminary_risk
        root_cause = None
        how_to_fix = None

        if llm_result:
            final_risk = llm_result.get("final_risk", preliminary_risk)
            root_cause = llm_result.get("root_cause")
            how_to_fix = llm_result.get("fix")

        if not root_cause:
            if matching_patterns:
                root_cause = matching_patterns[0].get("root_cause")
            if scos_issues and scos_risk >= failure_likelihood:
                top_issue = max(scos_issues, key=lambda x: x["risk"])
                root_cause = root_cause or top_issue["reason"]
                how_to_fix = how_to_fix or top_issue.get("how_to_fix")

        # Derive category from the highest-risk scos_issue (used in analysis.json rows)
        scos_category: str | None = None
        if scos_issues:
            _top_issue = max(scos_issues, key=lambda x: x["risk"])
            scos_category = _top_issue.get("category")

        if final_risk >= risk_threshold:
            explanation = (
                llm_result.get("explanation") if llm_result
                else f"Potential compatibility issue: {root_cause}"
            )
            confidence = (
                llm_result.get("confidence") if llm_result
                else ("HIGH" if final_risk >= 0.9 else "MEDIUM")
            )
            row = {
                "file": str(file_path),
                "lines": f"{block.line_start}-{block.line_end}",
                "code": block.code,
                "final_risk": final_risk,
                "root_cause": root_cause,
                "explanation": explanation,
                "fix": how_to_fix,
                "suggested_fix": how_to_fix,
                "category": scos_category,
                "confidence": confidence,
            }
            if block.cell_id is not None:
                row["cell_id"] = block.cell_id
            row["language"] = block.language
            results.append(row)

    return results


def print_json_results(results: list[dict]):
    print(json.dumps(results, indent=2))


def print_results(results: list[dict]):
    if not results:
        print("\nNo potential issues found above threshold.")
        return

    print("\n" + "=" * 80)
    print("SCALA SPARK ANALYSIS RESULTS")
    print("=" * 80)
    print(f"Code blocks with potential issues: {len(results)}")

    for r in results:
        final_risk = r["final_risk"]
        print(f"\n{'-' * 80}")
        print(f"  {r['file']}:{r['lines']} - Risk: {final_risk * 100:.1f}%")
        print(f"   Code: {r['code'][:200]}")
        if r.get("root_cause"):
            print(f"   Root Cause: {r['root_cause']}")
        if r.get("fix"):
            print(f"   Fix: {r['fix']}")
        if r.get("confidence"):
            print(f"   Confidence: {r['confidence']}")


def analyze_files_concurrently(
    files: list,
    analyze_one,
    file_workers: int,
    on_done=None,
) -> list[dict]:
    """Run ``analyze_one(file)`` over ``files`` with bounded file-level concurrency.

    Files are independent, so they are analyzed in parallel. Results are
    concatenated in **file order** (not completion order), so output is
    deterministic for a given input. ``future.result()`` is collected in file
    order, which also preserves the original fail-fast error semantics: the
    lowest-indexed file that raises surfaces its exception and aborts the run.

    ``on_done(i)`` (optional) is called after file ``i`` is collected, for
    progress logging by the caller.
    """
    n = len(files)
    if n == 0:
        return []
    workers = max(1, min(file_workers, n))
    per_file: list[list[dict]] = [[] for _ in range(n)]

    if workers == 1:
        for i, fp in enumerate(files):
            per_file[i] = analyze_one(fp)
            if on_done is not None:
                on_done(i)
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(analyze_one, fp) for fp in files]
            for i, fut in enumerate(futures):
                per_file[i] = fut.result()  # re-raises in file order (fail-fast)
                if on_done is not None:
                    on_done(i)

    out: list[dict] = []
    for results in per_file:
        out.extend(results or [])
    return out


def _enforce_ast_facts(require: bool, facts: "dict | None", no_ast_env: bool) -> None:
    """Exit 3 if --require-ast-facts is set but facts are unavailable."""
    if not require:
        return
    if no_ast_env:
        print(
            "ERROR: --require-ast-facts conflicts with SCOS_NO_AST_FACTS=1. "
            "Unset SCOS_NO_AST_FACTS to enable AST extraction.",
            file=sys.stderr,
        )
        sys.exit(3)
    if facts is None:
        print(
            "ERROR: --require-ast-facts set but AST facts extraction failed. "
            "Ensure sbt + JVM are on PATH and ScosMigrateFacts compiles "
            "(Phase 0.5 toolchain). Check stderr for extraction errors.",
            file=sys.stderr,
        )
        sys.exit(3)


def main():
    parser = argparse.ArgumentParser(description="Analyze Scala Spark scripts for SCOS compatibility issues")
    parser.add_argument("--path", type=str, required=True, help="Path to Scala file or directory")
    add_connectivity_args(parser)
    parser.add_argument("--risk-threshold", "-t", type=float, default=0.1, help="Minimum risk (0-1) to report")
    parser.add_argument("--similarity-threshold", "-s", type=float, default=0.55, help="Minimum cosine similarity")
    parser.add_argument("--batch-size", "-b", type=int, default=DEFAULT_LLM_BATCH_SIZE, help="Blocks per LLM call")
    parser.add_argument("--parallel-workers", "-p", type=int, default=DEFAULT_PARALLEL_WORKERS, help="Parallel workers")
    parser.add_argument(
        "--file-workers",
        type=int,
        default=DEFAULT_FILE_WORKERS,
        help=(
            "Number of files analyzed concurrently (independent per-file work). "
            f"Default {DEFAULT_FILE_WORKERS} (serial) to avoid 429 rate-limit errors "
            "from the remote RAG endpoint — total Cortex/RAG concurrency is roughly "
            "file-workers × parallel-workers (intra-file). Raise only in environments "
            "without RAG rate limits."
        ),
    )
    parser.add_argument("--output-format", choices=["text", "json"], default="text", help="Output format")
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help=(
            "Write JSON results directly to this file instead of stdout. "
            "Strongly preferred over shell redirection (`> file`): the Snowflake "
            "connector may print auth/SSO banners to stdout that would otherwise "
            "corrupt a redirected JSON file. Implies --output-format json."
        ),
    )
    parser.add_argument(
        "--require-llm",
        action="store_true",
        default=False,
        help=(
            "Fail fast unless CORTEX.COMPLETE is reachable with the selected "
            "connection."
        ),
    )
    parser.add_argument(
        "--notebook-index",
        type=str,
        default=None,
        help=(
            "Optional path to migration_state.json; when provided, the "
            "notebook_index stored there is used to skip per-candidate "
            "notebook-detection I/O when walking the workload."
        ),
    )
    parser.add_argument(
        "--require-ast-facts",
        action="store_true",
        default=False,
        help=(
            "Fail (exit 3) if Scalameta AST facts are unavailable — i.e. the "
            "ScosMigrateFacts extractor could not compile or run. Use in "
            "CI/production to enforce AST-based detection instead of silently "
            "falling back to regex. Incompatible with SCOS_NO_AST_FACTS=1."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    logger.setLevel(logging.INFO)

    path = Path(args.path).expanduser()
    if not path.exists():
        logger.error(f"Error: Path does not exist: {path}")
        sys.exit(1)

    notebook_index: dict[str, dict] | None = None
    if args.notebook_index:
        try:
            with open(args.notebook_index, "r", encoding="utf-8") as f:
                state = json.load(f)
            raw_index = state.get("notebook_index") or {}
            if isinstance(raw_index, dict):
                notebook_index = raw_index
                logger.info(f"Loaded notebook_index with {len(notebook_index)} entries from {args.notebook_index}")
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load notebook_index from {args.notebook_index}: {e}")

    files = find_scala_files(path, notebook_index=notebook_index)
    logger.info(f"Found {len(files)} Scala file(s) to analyze")

    session = open_session(args.connection)
    if args.require_llm:
        # The skill orchestrator runs `check_cortex_llm_access.py` as its own
        # preflight gate before invoking us. When that gate has already passed,
        # it sets `SCOS_LLM_PREFLIGHT_VERIFIED=1` so we skip a second billable
        # `CORTEX.COMPLETE` probe here. Direct CLI invocations (no env var)
        # still get the original fail-fast preflight.
        if os.environ.get("SCOS_LLM_PREFLIGHT_VERIFIED") == "1":
            logger.info(
                "CORTEX.COMPLETE preflight skipped: SCOS_LLM_PREFLIGHT_VERIFIED=1 "
                "(verified by skill orchestrator)."
            )
        else:
            verify_cortex_complete_access(session, model=DEFAULT_LLM_MODEL)
            logger.info("CORTEX.COMPLETE preflight passed for required LLM mode.")
    scos_rag: BaseRAG = build_rag(session, args.rag_backend)

    file_workers = max(1, min(args.file_workers, len(files))) if files else 1
    logger.info(
        f"\nAnalyzing {len(files)} Scala file(s) "
        f"(risk: {args.risk_threshold * 100:.0f}%, similarity: {args.similarity_threshold}, "
        f"batch: {args.batch_size}, intra-file workers: {args.parallel_workers}, "
        f"file workers: {file_workers})..."
    )

    safe_apis = load_safe_apis()

    # AST-facts detection (Job 2): extract Scalameta facts ONCE over the whole
    # workload. When the JVM/sbt toolchain is available the analyzer detects
    # structural incompatibilities (imports/formats/Dataset APIs/no-op/UDF/RDD)
    # from these facts — eliminating regex false-positives in comments/strings
    # and handling multi-line constructs. When unavailable (or disabled via
    # SCOS_NO_AST_FACTS=1) it returns None and the analyzer falls back to regex.
    ast_facts: dict | None = None
    if os.environ.get("SCOS_NO_AST_FACTS") != "1":
        try:
            import scala_ast_facts
            ast_facts = scala_ast_facts.extract_facts(path)
            if ast_facts is not None:
                logger.info(f"AST facts extracted for {len(ast_facts)} file(s) "
                            "(structural detection runs on Scalameta AST).")
            else:
                logger.info("AST facts unavailable (no JVM/sbt toolchain) — "
                            "structural detection falls back to regex.")
        except Exception as e:  # noqa: BLE001 - never let facts extraction break analysis
            logger.warning(f"AST facts extraction errored ({e}); falling back to regex.")
            ast_facts = None

    _enforce_ast_facts(
        args.require_ast_facts,
        ast_facts,
        os.environ.get("SCOS_NO_AST_FACTS") == "1",
    )

    def _analyze_one(fp: Path) -> list[dict]:
        file_facts = ast_facts.get(str(fp.resolve())) if ast_facts else None
        return analyze_file(
            scos_rag, fp,
            risk_threshold=args.risk_threshold,
            session=session,
            similarity_threshold=args.similarity_threshold,
            llm_batch_size=args.batch_size,
            parallel_workers=args.parallel_workers,
            require_llm=args.require_llm,
            safe_apis=safe_apis,
            file_facts=file_facts,
        )

    def _log_done(i: int) -> None:
        logger.info(f"  [{i + 1}/{len(files)}] {files[i].name}")

    all_results = analyze_files_concurrently(
        files, _analyze_one, file_workers, on_done=_log_done
    )

    all_results = sorted(all_results, key=lambda x: x["final_risk"], reverse=True)

    if args.output:
        # Write JSON straight to the file so connector/auth stdout banners can
        # never corrupt it (the `> file` redirect is fragile — see --output help).
        out_path = Path(args.output).expanduser()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, indent=2)
        logger.info(f"Wrote {len(all_results)} issue(s) as JSON to {out_path}")
    elif args.output_format == "json":
        print_json_results(all_results)
    else:
        print_results(all_results)

    session.close()


if __name__ == "__main__":
    main()

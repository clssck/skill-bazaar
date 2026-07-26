#!/usr/bin/env python3

import argparse
import os
import sys
from itertools import combinations
from typing import Any, Dict, List, Optional

import snowflake.connector
import yaml


def get_connection() -> snowflake.connector.SnowflakeConnection:
    connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME")
    if not connection_name:
        raise ValueError(
            "SNOWFLAKE_CONNECTION_NAME environment variable not set. "
            "Please set it to your Snowflake connection name."
        )

    try:
        conn = snowflake.connector.connect(connection_name=connection_name)
        return conn
    except Exception as e:
        raise Exception(f"Failed to connect to Snowflake: {e}")


def parse_table_name(full_table_name: str) -> tuple[str, str, str]:
    parts = full_table_name.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid table name: {full_table_name}. "
            "Expected format: database.schema.table"
        )
    return parts[0], parts[1], parts[2]


def get_columns(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> List[str]:
    cursor = conn.cursor()
    try:
        query = f"DESCRIBE TABLE {database}.{schema}.{table}"
        cursor.execute(query)
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    finally:
        cursor.close()


def get_columns_with_metadata(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> List[Dict[str, Any]]:
    cursor = conn.cursor()
    try:
        query = f"DESCRIBE TABLE {database}.{schema}.{table}"
        cursor.execute(query)
        rows = cursor.fetchall()
        columns = []
        for row in rows:
            columns.append(
                {
                    "name": row[0],
                    "data_type": row[1],
                    "nullable": row[3] == "Y",
                }
            )
        return columns
    finally:
        cursor.close()


def get_row_count(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    sample_limit: Optional[int] = None,
) -> int:
    cursor = conn.cursor()
    try:
        if sample_limit:
            query = (
                f"SELECT COUNT(*) FROM {database}.{schema}.{table} LIMIT {sample_limit}"
            )
        else:
            query = f"SELECT COUNT(*) FROM {database}.{schema}.{table}"
        cursor.execute(query)
        result = cursor.fetchone()
        return int(result[0])
    finally:
        cursor.close()


def get_null_percentage(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    column: str,
    sample_limit: Optional[int] = None,
) -> float:
    cursor = conn.cursor()
    try:
        limit_clause = f" LIMIT {sample_limit}" if sample_limit else ""
        query = f"""
        SELECT
            COUNT(*) as total,
            COUNT({column}) as non_null
        FROM {database}.{schema}.{table}{limit_clause}
        """
        cursor.execute(query)
        result = cursor.fetchone()
        total = result[0]
        non_null = result[1]
        if total == 0:
            return 1.0
        return float((total - non_null) / total)
    except Exception as e:
        print(
            f"Warning: Could not get null percentage for {column}: {e}", file=sys.stderr
        )
        return 1.0
    finally:
        cursor.close()


def filter_key_candidate_columns(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    columns_metadata: List[Dict[str, Any]],
    sample_limit: Optional[int] = None,
) -> List[str]:
    candidates = []

    print("Filtering columns for key candidates...", file=sys.stderr)

    for col_meta in columns_metadata:
        col_name = col_meta["name"]
        data_type = col_meta["data_type"].upper()
        is_nullable = col_meta["nullable"]

        score = 0
        reasons = []

        if "_ID" in col_name.upper() or col_name.upper().endswith("ID"):
            score += 3
            reasons.append("ID column")

        if "_KEY" in col_name.upper() or col_name.upper().endswith("KEY"):
            score += 3
            reasons.append("KEY column")

        if any(
            keyword in col_name.upper()
            for keyword in ["DATE", "TIME", "TIMESTAMP", "DS", "DT"]
        ):
            score += 2
            reasons.append("temporal column")

        if "NUMBER" in data_type or "INT" in data_type:
            score += 1
            reasons.append("numeric type")

        if "DATE" in data_type or "TIME" in data_type or "TIMESTAMP" in data_type:
            score += 2
            reasons.append("temporal type")

        if "VARCHAR" in data_type or "TEXT" in data_type:
            if any(
                keyword in col_name.upper()
                for keyword in ["NAME", "DESCRIPTION", "COMMENT", "TEXT", "CONTENT"]
            ):
                score -= 2
                reasons.append("likely descriptive text")
            else:
                score += 1
                reasons.append("string type")

        if "FLOAT" in data_type or "DOUBLE" in data_type or "DECIMAL" in data_type:
            score -= 1
            reasons.append("floating point (unlikely key)")

        if not is_nullable:
            score += 1
            reasons.append("NOT NULL")

        if score >= 2:
            null_pct = get_null_percentage(
                conn, database, schema, table, col_name, sample_limit
            )
            if null_pct > 0.1:
                score -= 2
                reasons.append(f"high null % ({null_pct:.1%})")

            if score >= 2:
                candidates.append(col_name)
                print(
                    f"  ✓ {col_name} (score={score}, reasons={', '.join(reasons)})",
                    file=sys.stderr,
                )
            else:
                print(
                    f"  ✗ {col_name} (score={score}, excluded due to: {', '.join(reasons)})",
                    file=sys.stderr,
                )
        else:
            print(f"  ✗ {col_name} (score={score}, insufficient)", file=sys.stderr)

    print(
        f"\nFiltered {len(candidates)} key candidates from {len(columns_metadata)} total columns",
        file=sys.stderr,
    )
    return candidates


def get_column_cardinality(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    column: str,
    sample_limit: Optional[int] = None,
) -> int:
    cursor = conn.cursor()
    try:
        limit_clause = f" LIMIT {sample_limit}" if sample_limit else ""
        query = f"SELECT APPROX_COUNT_DISTINCT({column}) FROM {database}.{schema}.{table}{limit_clause}"
        cursor.execute(query)
        result = cursor.fetchone()
        return int(result[0])
    except Exception as e:
        print(f"Warning: Could not get cardinality for {column}: {e}", file=sys.stderr)
        return 0
    finally:
        cursor.close()


def get_composite_cardinality(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    columns: List[str],
    sample_limit: Optional[int] = None,
) -> int:
    cursor = conn.cursor()
    try:
        column_list = ", ".join(columns)
        composite_expr = (
            f"TO_VARIANT(ARRAY_CONSTRUCT({column_list}))"
            if len(columns) > 1
            else columns[0]
        )
        limit_clause = f" LIMIT {sample_limit}" if sample_limit else ""
        query = f"SELECT APPROX_COUNT_DISTINCT({composite_expr}) FROM {database}.{schema}.{table}{limit_clause}"
        cursor.execute(query)
        result = cursor.fetchone()
        return int(result[0])
    except Exception as e:
        print(
            f"Warning: Could not get composite cardinality for {columns}: {e}",
            file=sys.stderr,
        )
        return 0
    finally:
        cursor.close()


def find_single_column_keys(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    columns: List[str],
    row_count: int,
    uniqueness_threshold: float = 0.95,
    sample_limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    candidates = []

    print(
        f"Analyzing {len(columns)} columns for single-column keys (threshold: {uniqueness_threshold:.1%})...",
        file=sys.stderr,
    )

    for i, column in enumerate(columns, 1):
        print(f"  [{i}/{len(columns)}] Checking {column}...", file=sys.stderr)
        distinct_count = get_column_cardinality(
            conn, database, schema, table, column, sample_limit
        )

        if row_count > 0:
            uniqueness_pct = distinct_count / row_count
            if uniqueness_pct >= uniqueness_threshold:
                candidates.append(
                    {
                        "columns": [column],
                        "distinct_count": distinct_count,
                        "row_count": row_count,
                        "uniqueness_percentage": round(uniqueness_pct * 100, 2),
                        "type": "single_column",
                    }
                )
                print(
                    f"    ✅ Found candidate: {column} (distinct={distinct_count}, rows={row_count}, uniqueness={uniqueness_pct:.2%})",
                    file=sys.stderr,
                )

    return candidates


def find_composite_keys(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    columns: List[str],
    row_count: int,
    max_cols: int = 3,
    uniqueness_threshold: float = 0.95,
    sample_limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    candidates = []

    for num_cols in range(2, max_cols + 1):
        combos = list(combinations(columns, num_cols))
        print(
            f"Analyzing {len(combos)} {num_cols}-column combinations (threshold: {uniqueness_threshold:.1%})...",
            file=sys.stderr,
        )

        for i, combo in enumerate(combos, 1):
            if i % 10 == 0:
                print(
                    f"  [{i}/{len(combos)}] Checking combinations...", file=sys.stderr
                )

            distinct_count = get_composite_cardinality(
                conn, database, schema, table, list(combo), sample_limit
            )

            if row_count > 0:
                uniqueness_pct = distinct_count / row_count
                if uniqueness_pct >= uniqueness_threshold:
                    candidates.append(
                        {
                            "columns": list(combo),
                            "distinct_count": distinct_count,
                            "row_count": row_count,
                            "uniqueness_percentage": round(uniqueness_pct * 100, 2),
                            "type": f"{num_cols}_column_composite",
                        }
                    )
                    print(
                        f"    ✅ Found candidate: {list(combo)} (distinct={distinct_count}, rows={row_count}, uniqueness={uniqueness_pct:.2%})",
                        file=sys.stderr,
                    )

    return candidates


def rank_candidates(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(
        candidates, key=lambda x: (-x["uniqueness_percentage"], len(x["columns"]))
    )


def infer_primary_keys(
    table_name: str,
    max_composite_cols: int = 3,
    hint_columns: Optional[List[str]] = None,
    uniqueness_threshold: float = 0.95,
    sample_limit: Optional[int] = 100000,
) -> Dict[str, Any]:
    conn = get_connection()
    database, schema, table = parse_table_name(table_name)

    try:
        columns = get_columns(conn, database, schema, table)
        print(f"Found {len(columns)} columns in {table_name}", file=sys.stderr)

        row_count = get_row_count(conn, database, schema, table, sample_limit)
        print(f"Row count: {row_count}", file=sys.stderr)
        if sample_limit:
            print(f"Using sample limit: {sample_limit} rows", file=sys.stderr)

        if row_count == 0:
            print("Warning: Table is empty, cannot infer primary keys", file=sys.stderr)
            return {
                "table": {
                    "database": database,
                    "schema": schema,
                    "table": table,
                    "full_name": table_name,
                },
                "row_count": 0,
                "candidates": [],
            }

        # Step 1: Test hint columns first (if provided) - explicit user intent
        composite_candidates = []
        if hint_columns:
            print(
                f"\nUsing {len(hint_columns)} hint columns provided: {hint_columns}",
                file=sys.stderr,
            )

            columns_upper = {col.upper(): col for col in columns}
            valid_hint_columns = []
            invalid_hint_columns = []

            for hint_col in hint_columns:
                hint_col_upper = hint_col.upper()
                if hint_col_upper in columns_upper:
                    valid_hint_columns.append(columns_upper[hint_col_upper])
                else:
                    invalid_hint_columns.append(hint_col)

            if invalid_hint_columns:
                print(
                    f"Warning: Invalid hint columns (not in table): {invalid_hint_columns}",
                    file=sys.stderr,
                )

            if valid_hint_columns:
                print(
                    f"Analyzing hint columns as composite key (case-corrected): {valid_hint_columns}...",
                    file=sys.stderr,
                )
                composite_candidates = find_composite_keys(
                    conn,
                    database,
                    schema,
                    table,
                    valid_hint_columns,
                    row_count,
                    max_composite_cols,
                    uniqueness_threshold,
                    sample_limit,
                )
            else:
                print("Error: No valid hint columns provided.", file=sys.stderr)

        # Step 2: Test single-column candidates
        # If hint columns are provided, only check those as single columns
        # Otherwise, check all columns
        if hint_columns:
            print(
                "\nSkipping exhaustive single-column check since hint columns were provided.",
                file=sys.stderr,
            )
            single_column_candidates = find_single_column_keys(
                conn,
                database,
                schema,
                table,
                valid_hint_columns if valid_hint_columns else [],
                row_count,
                uniqueness_threshold,
                sample_limit,
            )
        else:
            print(
                "\nChecking all columns for single-column keys (no hints provided)...",
                file=sys.stderr,
            )
            single_column_candidates = find_single_column_keys(
                conn,
                database,
                schema,
                table,
                columns,
                row_count,
                uniqueness_threshold,
                sample_limit,
            )

        # Step 3: Skip exhaustive composite search entirely
        # (expensive and rarely needed if we have hints or single-column keys)

        all_candidates = single_column_candidates + composite_candidates
        ranked_candidates = rank_candidates(all_candidates)

        analyzed_columns = hint_columns if hint_columns else columns

        result = {
            "table": {
                "database": database,
                "schema": schema,
                "table": table,
                "full_name": table_name,
            },
            "row_count": row_count,
            "total_columns": len(columns),
            "hint_columns": hint_columns,
            "analyzed_columns": len(analyzed_columns),
            "candidates": ranked_candidates,
        }

        return result

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Infer primary keys using COUNT DISTINCT cardinality analysis"
    )
    parser.add_argument(
        "--table",
        required=True,
        help="Fully qualified table name (database.schema.table)",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Output YAML file path",
    )
    parser.add_argument(
        "--max-composite-cols",
        type=int,
        default=3,
        help="Maximum number of columns in composite keys (default: 3)",
    )
    parser.add_argument(
        "--hint-columns",
        type=str,
        default=None,
        help="Comma-separated list of columns to test as primary key candidates (e.g., 'account_id,deployment,ds')",
    )
    parser.add_argument(
        "--uniqueness-threshold",
        type=float,
        default=0.95,
        help="Minimum uniqueness percentage to consider a key valid (default: 0.95 = 95%%)",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=100000,
        help="Maximum number of rows to sample for analysis (default: 100000). Set to 0 for full table scan.",
    )

    args = parser.parse_args()

    try:
        print(f"Inferring primary keys for {args.table}...", file=sys.stderr)

        hint_columns: Optional[List[str]] = None
        if args.hint_columns:
            hint_columns = [col.strip() for col in args.hint_columns.split(",")]
            print(f"Using hint columns: {hint_columns}", file=sys.stderr)

        print(f"Uniqueness threshold: {args.uniqueness_threshold:.1%}", file=sys.stderr)
        sample_limit = args.sample_limit if args.sample_limit > 0 else None
        result = infer_primary_keys(
            args.table,
            args.max_composite_cols,
            hint_columns,
            args.uniqueness_threshold,
            sample_limit,
        )

        with open(args.output, "w") as f:
            yaml.dump(result, f, default_flow_style=False, sort_keys=False)

        print(f"\n✅ Primary key inference completed: {args.output}", file=sys.stderr)
        print(f"   Row count: {result['row_count']}", file=sys.stderr)
        print(f"   Candidates found: {len(result['candidates'])}", file=sys.stderr)

        if result["candidates"]:
            print("\nTop candidates:", file=sys.stderr)
            for i, candidate in enumerate(result["candidates"][:5], 1):
                cols = ", ".join(candidate["columns"])
                print(
                    f"   {i}. [{cols}] (uniqueness: {candidate['uniqueness_percentage']:.2f}%)",
                    file=sys.stderr,
                )

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

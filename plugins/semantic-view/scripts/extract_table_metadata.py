#!/usr/bin/env python3
"""
Table Metadata Extractor

Extracts comprehensive table metadata from Snowflake for semantic view creation.

Retrieves:
- Column names, data types, nullability
- Sample values for each column
- Primary keys and unique constraints
- Foreign key relationships
- Table statistics

Usage:
    python extract_table_metadata.py --table <database>.<schema>.<table> --output metadata.yaml

Examples:
    python extract_table_metadata.py --table snowscience.snowml.cortex_analyst_logs --output logs_metadata.yaml
    python extract_table_metadata.py --table prod.sales.orders --output orders_metadata.yaml --sample-size 100
"""

import argparse
import os
import sys
from typing import Any, Dict, List

import snowflake.connector
import yaml


def get_connection() -> snowflake.connector.SnowflakeConnection:
    """Get Snowflake connection using connection name from environment."""
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
    """Parse fully qualified table name into database, schema, table."""
    parts = full_table_name.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"Invalid table name: {full_table_name}. "
            "Expected format: database.schema.table"
        )
    return parts[0], parts[1], parts[2]


def get_table_schema(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> List[Dict[str, Any]]:
    """Get table schema using DESCRIBE TABLE."""
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
                    "kind": row[2],
                    "nullable": row[3] == "Y",
                    "default": row[4],
                    "primary_key": row[5] == "Y",
                    "unique_key": row[6] == "Y",
                    "comment": row[8] if len(row) > 8 else None,
                }
            )

        return columns
    finally:
        cursor.close()


def get_sample_values(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
    column_name: str,
    sample_size: int = 10,
) -> List[Any]:
    """Get sample values for a column."""
    cursor = conn.cursor()
    try:
        query = f"""
        SELECT DISTINCT {column_name}
        FROM {database}.{schema}.{table}
        WHERE {column_name} IS NOT NULL
        LIMIT {sample_size}
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        return [row[0] for row in rows]
    except Exception as e:
        print(
            f"Warning: Could not get sample values for {column_name}: {e}",
            file=sys.stderr,
        )
        return []
    finally:
        cursor.close()


def get_primary_keys(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> List[str]:
    """Get primary key columns using SHOW PRIMARY KEYS."""
    cursor = conn.cursor()
    try:
        query = f"SHOW PRIMARY KEYS IN TABLE {database}.{schema}.{table}"
        cursor.execute(query)
        rows = cursor.fetchall()
        return [row[4] for row in rows]
    except Exception as e:
        print(f"Warning: Could not retrieve primary keys: {e}", file=sys.stderr)
        return []
    finally:
        cursor.close()


def get_unique_keys(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> List[List[str]]:
    """Get unique key constraints using SHOW UNIQUE KEYS."""
    cursor = conn.cursor()
    try:
        query = f"SHOW UNIQUE KEYS IN TABLE {database}.{schema}.{table}"
        cursor.execute(query)
        rows = cursor.fetchall()

        unique_key_groups: Dict[str, List[str]] = {}
        for row in rows:
            constraint_name = row[2]
            column_name = row[4]

            if constraint_name not in unique_key_groups:
                unique_key_groups[constraint_name] = []
            unique_key_groups[constraint_name].append(column_name)

        return list(unique_key_groups.values())
    except Exception as e:
        print(f"Warning: Could not retrieve unique keys: {e}", file=sys.stderr)
        return []
    finally:
        cursor.close()


def get_foreign_keys(
    conn: snowflake.connector.SnowflakeConnection,
    database: str,
    schema: str,
    table: str,
) -> List[Dict[str, Any]]:
    """Get foreign key relationships using SHOW IMPORTED KEYS."""
    cursor = conn.cursor()
    try:
        query = f"SHOW IMPORTED KEYS IN TABLE {database}.{schema}.{table}"
        cursor.execute(query)
        rows = cursor.fetchall()

        foreign_keys = []
        for row in rows:
            foreign_keys.append(
                {
                    "fk_database": row[0],
                    "fk_schema": row[1],
                    "fk_table": row[2],
                    "fk_column": row[3],
                    "pk_database": row[4],
                    "pk_schema": row[5],
                    "pk_table": row[6],
                    "pk_column": row[7],
                }
            )

        return foreign_keys
    except Exception as e:
        print(f"Warning: Could not retrieve foreign keys: {e}", file=sys.stderr)
        return []
    finally:
        cursor.close()


def classify_column(column: Dict[str, Any]) -> str:
    """Classify column as dimension, fact, or time_dimension."""
    data_type = column["data_type"].upper()
    name = column["name"].lower()

    if "DATE" in data_type or "TIME" in data_type or "TIMESTAMP" in data_type:
        return "time_dimension"

    if (
        "NUMBER" in data_type
        or "INT" in data_type
        or "FLOAT" in data_type
        or "DOUBLE" in data_type
        or "DECIMAL" in data_type
    ):
        if any(
            keyword in name
            for keyword in [
                "count",
                "total",
                "sum",
                "amount",
                "quantity",
                "qty",
                "price",
                "cost",
                "revenue",
                "credit",
            ]
        ):
            return "fact"
        return "dimension"

    return "dimension"


def extract_table_metadata(
    table_name: str,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """Extract complete table metadata."""
    conn = get_connection()
    database, schema, table = parse_table_name(table_name)

    try:
        columns = get_table_schema(conn, database, schema, table)

        primary_keys = get_primary_keys(conn, database, schema, table)
        unique_keys = get_unique_keys(conn, database, schema, table)
        foreign_keys = get_foreign_keys(conn, database, schema, table)

        for column in columns:
            column["classification"] = classify_column(column)

            if column["classification"] in ["dimension", "time_dimension"]:
                column["sample_values"] = get_sample_values(
                    conn, database, schema, table, column["name"], sample_size
                )

        metadata = {
            "table": {
                "database": database,
                "schema": schema,
                "table": table,
                "full_name": table_name,
            },
            "columns": columns,
            "primary_keys": primary_keys,
            "unique_keys": unique_keys,
            "foreign_keys": foreign_keys,
        }

        return metadata

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract table metadata from Snowflake for semantic view creation"
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
        "--sample-size",
        type=int,
        default=10,
        help="Number of sample values to extract per column (default: 10)",
    )

    args = parser.parse_args()

    try:
        print(f"Extracting metadata for {args.table}...", file=sys.stderr)
        metadata = extract_table_metadata(args.table, args.sample_size)

        with open(args.output, "w") as f:
            yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)

        print(f"✅ Metadata extracted successfully to {args.output}", file=sys.stderr)
        print(f"   Columns: {len(metadata['columns'])}", file=sys.stderr)
        print(f"   Primary Keys: {len(metadata['primary_keys'])}", file=sys.stderr)
        print(f"   Unique Keys: {len(metadata['unique_keys'])}", file=sys.stderr)
        print(f"   Foreign Keys: {len(metadata['foreign_keys'])}", file=sys.stderr)

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Eval SQL Pair Tool

Executes two SQL queries in parallel against Snowflake and outputs both results
to a file for comparison. Useful for comparing generated SQL vs ground truth SQL.

Usage (run from cortex2 root directory):
    # With SQL strings
    python3 snowpilot/semantic_view_autopilot/snova/skills/eval_sql_pair.py \
      --sql1 "SELECT * FROM table1" \
      --sql2 "SELECT * FROM table2" \
      --output results.txt \
      --connection snowhouse

    # With SQL from files
    python3 snowpilot/semantic_view_autopilot/snova/skills/eval_sql_pair.py \
      --sql1-file query1.sql \
      --sql2-file query2.sql \
      --output results.txt \
      --connection snowhouse

    # Mix and match (SQL1 from string, SQL2 from file)
    python3 snowpilot/semantic_view_autopilot/snova/skills/eval_sql_pair.py \
      --sql1 "SELECT * FROM table1" \
      --sql2-file query2.sql \
      --output results.txt

Output Format:
    The tool writes a structured text file with execution results only:

    ================================================================================
    SQL 1 RESULTS
    ================================================================================
    [Results from first SQL query]

    ================================================================================
    SQL 2 RESULTS
    ================================================================================
    [Results from second SQL query]
"""

import argparse
import asyncio
import csv
import sys
from io import StringIO

from sf_connection_utils import SnowflakeConnection
from snowflake.connector.util_text import split_statements


def execute_sql(conn: SnowflakeConnection, sql: str, label: str) -> str:
    """
    Execute SQL using snowflake.connector and return formatted results.

    Args:
        conn: SnowflakeConnection instance
        sql: SQL query to execute
        label: Label for logging (e.g., "SQL 1", "SQL 2")

    Returns:
        Formatted string with execution results
    """
    try:
        print(f"⚡ Executing {label}...")
        session = conn.get_snowflake_session()
        cursor = session.cursor()

        # Split statements
        statements = []
        for stmt in split_statements(StringIO(sql)):
            stmt = stmt[0].strip()
            if stmt:
                statements.append(stmt)

        if len(statements) == 0:
            return "No statements to execute."

        # Execute all but last statement
        for i in range(len(statements) - 1):
            cursor.execute(statements[i], timeout=180)

        # Execute last statement and collect output
        cursor.execute(statements[-1], timeout=180)

        # Check for query results
        if cursor.description is not None:
            MAX_ROWS = 1000
            MAX_BYTES = 20000

            columns = [col[0] for col in cursor.description]
            csv_output = StringIO()
            csv_writer = csv.writer(csv_output)
            csv_writer.writerow(columns)

            header = csv_output.getvalue()
            encoded_results_bytes: int = 0
            encoded_results: list[str] = []
            hit_row_limit, hit_byte_limit = False, False

            while True:
                if len(encoded_results) >= MAX_ROWS:
                    hit_row_limit = True
                    break

                row = cursor.fetchone()
                if row is None:
                    break

                row_values = [str(value) for value in row]

                csv_output = StringIO()
                csv_writer = csv.writer(csv_output)
                csv_writer.writerow(row_values)
                row_content = csv_output.getvalue()

                if encoded_results_bytes + len(row_content) + len(header) > MAX_BYTES:
                    hit_byte_limit = True
                    break

                encoded_results.append(row_content)
                encoded_results_bytes += len(row_content)

            if len(encoded_results) == 0:
                result = "Query executed successfully. No results returned."
            else:
                table_content = header + "".join(encoded_results)
                truncated = hit_row_limit or hit_byte_limit

                if truncated:
                    limit_reason = "row limit" if hit_row_limit else "size limit"
                    result = f"{len(encoded_results)} row(s) shown but more may have been returned (reached {limit_reason}).\n\n{table_content}\n[continued...]"
                else:
                    result = (
                        f"{len(encoded_results)} row(s) returned.\n\n{table_content}"
                    )
        else:
            # Non-query statement
            if cursor.rowcount >= 0:
                result = f"{cursor.rowcount} row(s) affected."
            else:
                result = "Statement executed successfully."

        print(f"✅ {label} executed successfully")
        return result

    except Exception as e:
        error_msg = f"❌ SQL Execution Error: {str(e)}"
        print(error_msg)
        return error_msg
    finally:
        if "cursor" in locals():
            cursor.close()


async def execute_parallel(
    conn: SnowflakeConnection, sql1: str, sql2: str
) -> tuple[str, str]:
    """
    Execute two SQL queries in parallel.

    Args:
        conn: SnowflakeConnection instance
        sql1: First SQL query
        sql2: Second SQL query

    Returns:
        Tuple of (results1, results2)
    """
    print("⚡ Starting parallel execution...")

    tasks = [
        asyncio.to_thread(execute_sql, conn, sql1, "SQL 1"),
        asyncio.to_thread(execute_sql, conn, sql2, "SQL 2"),
    ]

    results1, results2 = await asyncio.gather(*tasks)

    print("✅ Parallel execution completed")
    return results1, results2


def write_results(output_file: str, results1: str, results2: str) -> None:
    """
    Write both SQL query results to output file.

    Args:
        output_file: Path to output file
        results1: Results from first query
        results2: Results from second query
    """
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("=" * 80 + "\n")
        f.write("SQL 1 RESULTS\n")
        f.write("=" * 80 + "\n")
        f.write(results1 + "\n\n")

        f.write("=" * 80 + "\n")
        f.write("SQL 2 RESULTS\n")
        f.write("=" * 80 + "\n")
        f.write(results2 + "\n")

    print(f"✅ Results written to: {output_file}")


def load_sql_from_file(file_path: str) -> str:
    """Load SQL from a file."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"❌ Error reading SQL file {file_path}: {e}")
        sys.exit(1)


async def main_async(args: argparse.Namespace) -> None:
    """Main async execution function."""
    # Load SQL queries
    if args.sql1_file:
        sql1 = load_sql_from_file(args.sql1_file)
        print(f"📄 Loaded SQL 1 from: {args.sql1_file}")
    elif args.sql1:
        sql1 = args.sql1
    else:
        print("❌ Error: Must provide either --sql1 or --sql1-file")
        sys.exit(1)

    if args.sql2_file:
        sql2 = load_sql_from_file(args.sql2_file)
        print(f"📄 Loaded SQL 2 from: {args.sql2_file}")
    elif args.sql2:
        sql2 = args.sql2
    else:
        print("❌ Error: Must provide either --sql2 or --sql2-file")
        sys.exit(1)

    # Create connection
    try:
        conn = SnowflakeConnection(args.connection)
    except Exception as e:
        print(f"❌ Connection error: {e}")
        sys.exit(1)

    try:
        # Execute in parallel
        results1, results2 = await execute_parallel(conn, sql1, sql2)

        # Write results
        write_results(args.output, results1, results2)

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Execute two SQL queries in parallel and compare results"
    )

    # SQL input options
    parser.add_argument("--sql1", help="First SQL query (as string)")
    parser.add_argument("--sql1-file", help="Path to file containing first SQL query")
    parser.add_argument("--sql2", help="Second SQL query (as string)")
    parser.add_argument("--sql2-file", help="Path to file containing second SQL query")

    # Output and connection
    parser.add_argument(
        "--output", required=True, help="Output file path for comparison results"
    )
    parser.add_argument(
        "--connection", default="snowhouse", help="Snowflake connection name"
    )

    args = parser.parse_args()

    # Run async main
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

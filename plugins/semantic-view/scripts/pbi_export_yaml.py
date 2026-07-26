#!/usr/bin/env python3
"""
Extract semantic model YAML from a Power BI file via pbi_export.

Uses snowflake-connector-python directly to avoid SQL tool truncation on large
YAML outputs. The SYSTEM$CORTEX_ANALYST_SVA_TOOL response is double-nested JSON
- this script handles both parsing layers automatically.

Accepts both `.pbit` (template, JSON DataModelSchema) and `.pbix` (desktop,
XPress9-compressed VertiPaq); the parser auto-detects by ZIP contents.

Usage:
    python pbi_export_yaml.py <file_path> <semantic_model_name> <output_file> [options]

Examples:
    python pbi_export_yaml.py @STAGE/sales.pbit sales_model ./sales_model.yaml

    python pbi_export_yaml.py @STAGE/file.pbix my_model ./model.yaml \
        --target-database ANALYTICS --target-schema SEMANTIC \
        --skip-table-validation --no-measures

    SNOWFLAKE_CONNECTION_NAME=myconn python pbi_export_yaml.py \
        @STAGE/file.pbit model ./out.yaml --include-tables "Sales" "Customer"
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sf_connection_utils import SnowflakeConnection


def build_export_sql(params: dict) -> str:
    """Build the SQL statement that invokes pbi_export with the given params dict."""
    params_json = json.dumps(params, indent=4)
    return f"""SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${{"tool": "pbi_export", "parameters": {params_json}}}$$) AS result"""


def main():
    """Parse CLI args, invoke pbi_export via Snowflake, save the YAML and report stats."""
    parser = argparse.ArgumentParser(description="Export Power BI file to semantic model YAML")
    parser.add_argument("file_path", help="Stage path to Power BI file (@DB.SCHEMA.STAGE/file.pbit or .pbix)")
    parser.add_argument("semantic_model_name", help="Name for the semantic model (alphanumeric, _, -)")
    parser.add_argument("output_file", help="Local path to save the YAML output")
    parser.add_argument("--connection", default=None, help="Snowflake connection name (default: from SNOWFLAKE_CONNECTION_NAME or config default)")
    parser.add_argument("--target-database", default=None, help="Override target database for table references")
    parser.add_argument("--target-schema", default=None, help="Override target schema for table references")
    parser.add_argument("--include-tables", nargs="+", default=None, help="Filter to specific table display names (case-sensitive)")
    parser.add_argument("--include-columns", nargs="+", default=None, help="Filter to specific column names (physical AND calculated)")
    parser.add_argument("--include-measures", nargs="+", default=None, help="Filter to specific DAX measure names")
    parser.add_argument("--no-calculations", action="store_true", help="Drop all calculated columns (sets include_calculations=False)")
    parser.add_argument("--no-measures", action="store_true", help="Drop ALL DAX measures (sets include_measures_all=False)")
    parser.add_argument("--skip-table-validation", action="store_true", help="Skip the Snowflake validate_tables call")
    parser.add_argument("--generate-descriptions", action="store_true", help="Generate LLM descriptions for metrics")
    parser.add_argument("--model-name", default=None, help="LLM model for descriptions (default: ANTHROPIC_CLAUDE_SONNET_4)")
    args = parser.parse_args()

    params = {
        "file_path": args.file_path,
        "semantic_model_name": args.semantic_model_name,
    }
    if args.target_database:
        params["target_database"] = args.target_database
    if args.target_schema:
        params["target_schema"] = args.target_schema
    if args.include_tables:
        params["include_tables"] = args.include_tables
    if args.include_columns:
        params["include_columns"] = args.include_columns
    if args.include_measures:
        params["include_measures"] = args.include_measures
    if args.no_calculations:
        params["include_calculations"] = False
    if args.no_measures:
        params["include_measures_all"] = False
    if args.skip_table_validation:
        params["skip_table_validation"] = True
    if args.generate_descriptions:
        params["generate_descriptions"] = True
    if args.model_name:
        params["model_name"] = args.model_name

    connection_name = args.connection or os.environ.get("SNOWFLAKE_CONNECTION_NAME")
    if not connection_name:
        print("Error: No connection specified. Use --connection or set SNOWFLAKE_CONNECTION_NAME.", file=sys.stderr)
        sys.exit(1)

    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Connecting to Snowflake ({connection_name})...")
    sf = SnowflakeConnection(connection_name)
    conn = sf.get_snowflake_session()

    sql = build_export_sql(params)
    print(f"Running pbi_export for {args.file_path}...")

    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        raw = row[0]

        try:
            outer = json.loads(raw)
            inner = json.loads(outer["result"])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Error: Failed to parse pbi_export response: {e}", file=sys.stderr)
            print(f"Raw response (first 500 chars): {str(raw)[:500]}", file=sys.stderr)
            sys.exit(1)

        if not inner.get("success", False):
            print(f"Error from pbi_export: {inner.get('error', inner.get('message', 'unknown error'))}", file=sys.stderr)
            sys.exit(1)

        yaml_content = inner.get("yaml_content", "")
        if not yaml_content:
            print("Error: yaml_content is empty. Filters may be too restrictive.", file=sys.stderr)
            sys.exit(1)

        output_path.write_text(yaml_content)

        print(f"\nYAML saved to: {output_path}")
        print(f"  Model: {inner.get('semantic_model_name', 'N/A')}")
        print(f"  Tables: {inner.get('table_count', 0)}")
        print(f"  Columns: {inner.get('column_count', 0)}")
        print(f"  Relationships: {inner.get('relationship_count', 0)}")
        print(f"  Metrics: {inner.get('metric_count', 0)}")

        unsupported = inner.get("unsupported_measure_count", 0)
        if unsupported:
            print(f"  Unsupported DAX measures (dropped): {unsupported}")

        if inner.get("descriptions_generated"):
            print("  LLM descriptions: generated")

        m_query_warnings = inner.get("m_query_warnings", [])
        if m_query_warnings:
            print(f"  M-query warnings (tables dropped at parse time): {len(m_query_warnings)}")
            for w in m_query_warnings:
                print(f"    - {w}")

        validation_warnings = inner.get("validation_warnings", [])
        if validation_warnings:
            print(f"  Validation warnings (dropped by validate_tables): {len(validation_warnings)}")
            for w in validation_warnings:
                print(f"    - {w}")

        warnings = inner.get("warnings", [])
        builder_warnings = [
            w for w in warnings
            if w not in m_query_warnings and w not in validation_warnings
        ]
        if builder_warnings:
            print(f"  Builder warnings: {len(builder_warnings)}")
            for w in builder_warnings:
                print(f"    - {w}")

        errors = inner.get("errors", [])
        if errors:
            print(f"  Errors: {len(errors)}")
            for e in errors:
                print(f"    - {e}")

    finally:
        sf.close()


if __name__ == "__main__":
    main()

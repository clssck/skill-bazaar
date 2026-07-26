#!/usr/bin/env python3
"""
Extract semantic model YAML from a Tableau file via tableau_export.

Uses snowflake-connector-python directly to avoid SQL tool truncation on large
YAML outputs. The SYSTEM$CORTEX_ANALYST_SVA_TOOL response is double-nested JSON
— this script handles both parsing layers automatically.

Usage:
    python tableau_export_yaml.py <file_path> <semantic_model_name> <output_file> [options]

Examples:
    python tableau_export_yaml.py @STAGE/sales.twbx sales_model ./sales_model.yaml

    python tableau_export_yaml.py @STAGE/workbook.twb my_model ./model.yaml \
        --target-database ANALYTICS --target-schema SEMANTIC \
        --use-custom-sql-in-definition --extract-usage-context

    SNOWFLAKE_CONNECTION_NAME=myconn python tableau_export_yaml.py \
        @STAGE/file.twbx model ./out.yaml --include-worksheets "Sheet1" "Sheet2"
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from sf_connection_utils import SnowflakeConnection


def build_export_sql(params: dict) -> str:
    params_json = json.dumps(params, indent=4)
    return f"""SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${{"tool": "tableau_export", "parameters": {params_json}}}$$) AS result"""


def main():
    parser = argparse.ArgumentParser(description="Export Tableau file to semantic model YAML")
    parser.add_argument("file_path", help="Stage path to Tableau file (@DB.SCHEMA.STAGE/file.twbx)")
    parser.add_argument("semantic_model_name", help="Name for the semantic model")
    parser.add_argument("output_file", help="Local path to save the YAML output")
    parser.add_argument("--connection", default=None, help="Snowflake connection name (default: from SNOWFLAKE_CONNECTION_NAME or config default)")
    parser.add_argument("--target-database", default=None, help="Override target database for table references")
    parser.add_argument("--target-schema", default=None, help="Override target schema for table references")
    parser.add_argument("--datasource-name", default=None, help="Filter to specific datasource")
    parser.add_argument("--include-worksheets", nargs="+", default=None, help="Only columns used in these worksheets")
    parser.add_argument("--include-columns", nargs="+", default=None, help="Only these specific columns")
    parser.add_argument("--include-all-columns", action="store_true", help="Include all columns")
    parser.add_argument("--no-calculations", action="store_true", help="Exclude calculated fields")
    parser.add_argument("--use-custom-sql-in-definition", action="store_true", help="Embed custom SQL in YAML")
    parser.add_argument("--extract-usage-context", action="store_true", help="Extract worksheet/dashboard usage context")
    parser.add_argument("--generate-descriptions", action="store_true", help="Generate LLM descriptions")
    parser.add_argument("--model-name", default=None, help="LLM model for descriptions")
    parser.add_argument("--additional-files", nargs="+", default=None, help="Stage paths to additional files (e.g., .tds/.tdsx for published datasources). Currently only the first file is used.")
    parser.add_argument("--published-datasource-stub-name", default=None, help="Disambiguate which published datasource stub to merge (required when workbook has multiple)")
    args = parser.parse_args()

    params = {
        "file_path": args.file_path,
        "semantic_model_name": args.semantic_model_name,
    }
    if args.target_database:
        params["target_database"] = args.target_database
    if args.target_schema:
        params["target_schema"] = args.target_schema
    if args.datasource_name:
        params["datasource_name"] = args.datasource_name
    if args.include_worksheets:
        params["include_worksheets"] = args.include_worksheets
    if args.include_columns:
        params["include_columns"] = args.include_columns
    if args.include_all_columns:
        params["include_all_columns"] = True
    if args.no_calculations:
        params["include_calculations"] = False
    if args.use_custom_sql_in_definition:
        params["use_custom_sql_in_definition"] = True
    if args.extract_usage_context:
        params["extract_usage_context"] = True
    if args.generate_descriptions:
        params["generate_descriptions"] = True
    if args.model_name:
        params["model_name"] = args.model_name
    if args.additional_files:
        params["additional_files"] = args.additional_files
    if args.published_datasource_stub_name:
        params["published_datasource_stub_name"] = args.published_datasource_stub_name

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
    print(f"Running tableau_export for {args.file_path}...")

    try:
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        raw = row[0]

        try:
            outer = json.loads(raw)
            inner = json.loads(outer["result"])
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"Error: Failed to parse tableau_export response: {e}", file=sys.stderr)
            print(f"Raw response (first 500 chars): {str(raw)[:500]}", file=sys.stderr)
            sys.exit(1)

        if not inner.get("success", False):
            print(f"Error from tableau_export: {inner.get('error', 'unknown error')}", file=sys.stderr)
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

        custom_views = inner.get("custom_view_names", [])
        if custom_views:
            print(f"  Custom views required: {len(custom_views)}")
            for v in custom_views:
                print(f"    - {v}")

        warnings = inner.get("warnings", [])
        if warnings:
            print(f"  Warnings: {len(warnings)}")
            for w in warnings:
                print(f"    - {w}")

        errors = inner.get("errors", [])
        if errors:
            print(f"  Errors: {len(errors)}")
            for e in errors:
                print(f"    - {e}")

        usage_context = inner.get("usage_context", "")
        if usage_context:
            ctx_path = output_path.with_suffix(".usage_context.txt")
            ctx_path.write_text(usage_context)
            print(f"  Usage context saved to: {ctx_path}")

        custom_ddl = inner.get("custom_view_ddl", [])
        if custom_ddl:
            ddl_path = output_path.with_suffix(".custom_views.sql")
            ddl_path.write_text("\n\n".join(custom_ddl))
            print(f"  Custom view DDL saved to: {ddl_path}")

    finally:
        sf.close()


if __name__ == "__main__":
    main()

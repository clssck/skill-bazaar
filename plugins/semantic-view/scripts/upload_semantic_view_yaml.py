#!/usr/bin/env python3
"""
Upload semantic view YAML to Snowflake using SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML function.

Usage:
    python upload_semantic_view_yaml.py <yaml_file_path> <database.schema> [--verify-only]

Example:
    python upload_semantic_view_yaml.py "./semantic_model.yaml" "ENG_CORTEX_ANALYST.DEV"
    python upload_semantic_view_yaml.py "./semantic_model.yaml" "ENG_CORTEX_ANALYST.DEV" --verify-only
"""

import argparse
import os
import sys
from pathlib import Path

import snowflake.connector


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Upload semantic view YAML to Snowflake"
    )
    parser.add_argument(
        "yaml_file_path",
        help="Path to the semantic view YAML file",
    )
    parser.add_argument(
        "target_schema",
        help="Target database.schema for the semantic view (e.g., 'DB.SCHEMA')",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify the YAML without creating the semantic view",
    )
    parser.add_argument(
        "--connection",
        default="snowhouse",
        help="Snowflake connection name (default: snowhouse)",
    )

    args = parser.parse_args()

    # Validate YAML file exists
    yaml_file = Path(args.yaml_file_path)
    if not yaml_file.exists():
        print(f"❌ YAML file not found: {args.yaml_file_path}")
        sys.exit(1)

    # Read YAML content
    try:
        with open(yaml_file, "r", encoding="utf-8") as f:
            yaml_content = f.read()
    except Exception as e:
        print(f"❌ Failed to read YAML file: {e}")
        sys.exit(1)

    try:
        # Connect to Snowflake using same pattern as the agent
        conn = snowflake.connector.connect(
            connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or args.connection
        )

        cursor = conn.cursor()

        # Build the SQL command
        verify_param = "TRUE" if args.verify_only else "FALSE"
        sql = f"""
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  '{args.target_schema}',
  $$
{yaml_content}
$$,
  {verify_param}
);
"""

        mode = "Verifying" if args.verify_only else "Uploading"
        print(f"{mode} semantic view to: {args.target_schema}")
        print(f"YAML file: {yaml_file}")
        print(f"File size: {len(yaml_content)} characters")
        print()

        # Execute the system function
        cursor.execute(sql)
        result = cursor.fetchone()

        if result and result[0]:
            message = result[0]

            if args.verify_only:
                if "valid" in message.lower():
                    print("✅ Verification successful!")
                    print(f"   {message}")
                else:
                    print("⚠️  Verification completed with message:")
                    print(f"   {message}")
            else:
                if "successfully created" in message.lower():
                    print("✅ Semantic view uploaded successfully!")
                    print(f"   Location: {args.target_schema}")
                    print(f"   {message}")
                else:
                    print("⚠️  Upload completed with message:")
                    print(f"   {message}")

        else:
            print("❌ No response from Snowflake")
            sys.exit(1)

    except snowflake.connector.errors.ProgrammingError as e:
        print(f"❌ Snowflake error: {e}")
        print("   Check that:")
        print("   - The target schema exists and is accessible")
        print("   - You have CREATE SEMANTIC VIEW privilege on the schema")
        print("   - The YAML syntax is valid")
        print("   - All base tables referenced in the YAML exist")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    main()

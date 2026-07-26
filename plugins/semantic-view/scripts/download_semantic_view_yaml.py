#!/usr/bin/env python3
"""
Download semantic view YAML from Snowflake using SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW function.

Usage:
    python download_semantic_view_yaml.py <semantic_view_name> <output_directory>

Example:
    python download_semantic_view_yaml.py "ENG_CORTEX_ANALYST.DEV.MY_SEMANTIC_VIEW" "./output"
"""

import argparse
import os
import sys
from pathlib import Path

import snowflake.connector


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download semantic view YAML from Snowflake"
    )
    parser.add_argument(
        "semantic_view_name",
        help="Fully qualified semantic view name (e.g., 'DB.SCHEMA.VIEW_NAME')",
    )
    parser.add_argument("output_directory", help="Directory to save the YAML file")
    parser.add_argument(
        "--connection",
        default="snowhouse",
        help="Snowflake connection name (default: snowhouse)",
    )

    args = parser.parse_args()

    # Validate and create output directory
    output_dir = Path(args.output_directory)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename from semantic view name
    # Replace dots and special characters with underscores for safe filename
    safe_name = (
        args.semantic_view_name.replace(".", "_").replace('"', "").replace("'", "")
    )
    output_file = output_dir / f"{safe_name}_semantic_model.yaml"

    try:
        # Connect to Snowflake using same pattern as the agent
        conn = snowflake.connector.connect(
            connection_name=os.getenv("SNOWFLAKE_CONNECTION_NAME") or args.connection
        )

        cursor = conn.cursor()

        # Execute the system function to get YAML
        sql = f"SELECT SYSTEM$READ_YAML_FROM_SEMANTIC_VIEW('{args.semantic_view_name}')"
        print(f"Executing: {sql}")

        cursor.execute(sql)
        result = cursor.fetchone()

        if result and result[0]:
            yaml_content = result[0]

            # Write YAML content to file
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(yaml_content)

            print("✅ Successfully downloaded semantic view YAML")
            print(f"📁 Saved to: {output_file}")
            print(f"📊 File size: {len(yaml_content)} characters")

        else:
            print(
                f"❌ No YAML content returned for semantic view: {args.semantic_view_name}"
            )
            print(
                "   This could mean the semantic view doesn't exist or you don't have access to it."
            )
            sys.exit(1)

    except snowflake.connector.errors.ProgrammingError as e:
        print(f"❌ Snowflake error: {e}")
        print("   Check that:")
        print("   - The semantic view name is correct and fully qualified")
        print("   - You have access to the semantic view")
        print("   - Your connection has the necessary permissions")
        sys.exit(1)

    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)

    finally:
        if "conn" in locals():
            conn.close()


if __name__ == "__main__":
    main()

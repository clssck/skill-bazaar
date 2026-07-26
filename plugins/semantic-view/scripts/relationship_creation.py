#!/usr/bin/env python3
"""
Infer and create valid relationships between two tables in a semantic model.

This script reads a semantic model YAML, analyzes primary keys, and creates
valid relationships (many_to_one or one_to_one only) based on join columns.

Logic based on production FastGen relationship inference:
- Both sides have PK/UK on join columns → one_to_one
- Right side has PK/UK on join columns → many_to_one
- Left side has PK/UK on join columns → Swap tables → many_to_one
- Neither side has PK/UK → many_to_many → REJECTED

Usage:
    # Default behavior (with validation - recommended):
    SNOWFLAKE_CONNECTION_NAME=myconnection python relationship_creation.py \
        --semantic-model path/to/semantic_model.yaml \
        --left-table ORDERS \
        --right-table CUSTOMERS \
        --left-columns CUSTOMER_ID \
        --right-columns CUSTOMER_ID \
        --output path/to/output_relationship.yaml

    # Skip validation (not recommended):
    python relationship_creation.py \
        --semantic-model path/to/semantic_model.yaml \
        --left-table ORDERS \
        --right-table CUSTOMERS \
        --left-columns CUSTOMER_ID \
        --right-columns CUSTOMER_ID \
        --output path/to/output_relationship.yaml \
        --skip-validation
"""

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple

import yaml

try:
    import snowflake.connector
    from snowflake.connector import DictCursor

    SNOWFLAKE_AVAILABLE = True
except ImportError:
    SNOWFLAKE_AVAILABLE = False


def load_semantic_model(file_path: str) -> Any:
    """Load semantic model from YAML file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def get_table(semantic_model: Mapping[str, Any], table_name: str) -> Optional[Any]:
    """Find a table in the semantic model by name (case-insensitive)."""
    table_name_lower = table_name.lower()
    for table in semantic_model.get("tables", []):
        if table["name"].lower() == table_name_lower:
            return table
    return None


def get_primary_key_columns(table: Dict[str, Any]) -> Set[str]:
    """Extract primary key columns from a table (lowercase)."""
    pk_columns = set()
    if "primary_key" in table and table["primary_key"]:
        columns = table["primary_key"].get("columns", [])
        pk_columns = set(col.lower() for col in columns)
    return pk_columns


def get_unique_key_columns(table: Dict[str, Any]) -> List[Set[str]]:
    """Extract unique key column sets from a table (lowercase)."""
    unique_key_sets = []
    if "unique_keys" in table and table["unique_keys"]:
        for uk in table["unique_keys"]:
            columns = uk.get("columns", [])
            if columns:
                unique_key_sets.append(set(col.lower() for col in columns))
    return unique_key_sets


def get_all_constraint_sets(table: Dict[str, Any]) -> List[Set[str]]:
    """Get all unique constraint sets (PK + UKs) for a table."""
    constraint_sets = []

    # Add primary key
    pk_columns = get_primary_key_columns(table)
    if pk_columns:
        constraint_sets.append(pk_columns)

    # Add unique keys
    constraint_sets.extend(get_unique_key_columns(table))

    return constraint_sets


def has_constraint_on_columns(
    constraint_sets: List[Set[str]], join_columns: Set[str]
) -> bool:
    """
    Check if any constraint set is a subset of the join columns.

    This means the constraint (PK or UK) covers all the join columns,
    indicating uniqueness on those columns.
    """
    return any(
        constraint_set.issubset(join_columns) for constraint_set in constraint_sets
    )


def infer_relationship_type(
    left_table: Dict[str, Any],
    right_table: Dict[str, Any],
    left_columns: List[str],
    right_columns: List[str],
) -> Tuple[str, Dict[str, Any]]:
    """
    Infer relationship type based on primary/unique keys.

    Returns:
        Tuple of (relationship_type, relationship_dict or error_info)

    Logic:
        - Both sides have constraints → one_to_one
        - Right side has constraints → many_to_one
        - Left side has constraints → Swap and make many_to_one
        - Neither side has constraints → many_to_many → REJECTED
    """
    # Get constraint sets for both tables
    left_constraint_sets = get_all_constraint_sets(left_table)
    right_constraint_sets = get_all_constraint_sets(right_table)

    # Convert join columns to sets (lowercase)
    left_join_cols = set(col.lower() for col in left_columns)
    right_join_cols = set(col.lower() for col in right_columns)

    # Check if constraints exist on join columns
    left_has_constraint = has_constraint_on_columns(
        left_constraint_sets, left_join_cols
    )
    right_has_constraint = has_constraint_on_columns(
        right_constraint_sets, right_join_cols
    )

    left_table_name = left_table["name"]
    right_table_name = right_table["name"]

    # Case 1: Both sides have constraints → ONE_TO_ONE
    if left_has_constraint and right_has_constraint:
        relationship = {
            "name": f"{left_table_name}_TO_{right_table_name}",
            "left_table": left_table_name,
            "right_table": right_table_name,
            "join_type": "inner",
            "relationship_type": "one_to_one",
            "relationship_columns": [
                {"left_column": lc, "right_column": rc}
                for lc, rc in zip(left_columns, right_columns)
            ],
        }
        return "one_to_one", relationship

    # Case 2: Only right side has constraints → MANY_TO_ONE
    elif right_has_constraint:
        relationship = {
            "name": f"{left_table_name}_TO_{right_table_name}",
            "left_table": left_table_name,
            "right_table": right_table_name,
            "join_type": "inner",
            "relationship_type": "many_to_one",
            "relationship_columns": [
                {"left_column": lc, "right_column": rc}
                for lc, rc in zip(left_columns, right_columns)
            ],
        }
        return "many_to_one", relationship

    # Case 3: Only left side has constraints → SWAP and make MANY_TO_ONE
    elif left_has_constraint:
        relationship = {
            "name": f"{right_table_name}_TO_{left_table_name}",
            "left_table": right_table_name,  # Swapped
            "right_table": left_table_name,  # Swapped
            "join_type": "inner",
            "relationship_type": "many_to_one",
            "relationship_columns": [
                {"left_column": rc, "right_column": lc}  # Swapped
                for lc, rc in zip(left_columns, right_columns)
            ],
        }
        return "many_to_one (swapped)", relationship

    # Case 4: Neither side has constraints → MANY_TO_MANY → REJECTED
    else:
        error_info = {
            "error": "many_to_many",
            "message": "Relationship is many_to_many, which is not supported. Neither table has a primary key or unique key on the join columns.",
            "left_table": left_table_name,
            "right_table": right_table_name,
            "left_columns": left_columns,
            "right_columns": right_columns,
            "suggestion": "Add a primary key or unique key to one of the tables on the join columns, or use a junction table.",
        }
        return "many_to_many (rejected)", error_info


def validate_columns_exist(
    table: Dict[str, Any], columns: List[str]
) -> Tuple[bool, List[str]]:
    """
    Validate that all columns exist in the table.

    Returns:
        Tuple of (all_exist: bool, missing_columns: List[str])
    """
    # Get all column names from dimensions, facts, and time_dimensions
    table_columns = set()

    for dim in table.get("dimensions", []):
        table_columns.add(dim["name"].lower())

    for fact in table.get("facts", []):
        table_columns.add(fact["name"].lower())

    for time_dim in table.get("time_dimensions", []):
        table_columns.add(time_dim["name"].lower())

    # Check which columns are missing
    missing = [col for col in columns if col.lower() not in table_columns]

    return len(missing) == 0, missing


def get_physical_table_fqn(table: Dict[str, Any]) -> str:
    """Get fully qualified name of the physical table."""
    base_table = table.get("base_table", {})
    database = base_table.get("database", "")
    schema = base_table.get("schema", "")
    table_name = base_table.get("table", "")
    return f"{database}.{schema}.{table_name}"


def get_physical_column_name(
    table: Dict[str, Any], logical_column_name: str
) -> Optional[str]:
    """Get physical column name from logical column name."""
    logical_lower = logical_column_name.lower()

    # Search in dimensions
    for dim in table.get("dimensions", []):
        if dim["name"].lower() == logical_lower:
            return str(dim.get("expr", dim["name"]))

    # Search in facts
    for fact in table.get("facts", []):
        if fact["name"].lower() == logical_lower:
            return str(fact.get("expr", fact["name"]))

    # Search in time_dimensions
    for time_dim in table.get("time_dimensions", []):
        if time_dim["name"].lower() == logical_lower:
            return str(time_dim.get("expr", time_dim["name"]))

    return None


def validate_relationship_in_database(
    connection: Any,
    left_table: Dict[str, Any],
    right_table: Dict[str, Any],
    left_columns: List[str],
    right_columns: List[str],
) -> Tuple[bool, List[str]]:
    """
    Validate that the relationship actually works in the database.

    Checks:
    1. Tables exist
    2. Columns exist in tables
    3. Data types are compatible
    4. JOIN query executes without errors

    Returns:
        Tuple of (is_valid: bool, error_messages: List[str])
    """
    errors = []
    cursor = connection.cursor(DictCursor)

    try:
        # Get physical table names
        left_fqn = get_physical_table_fqn(left_table)
        right_fqn = get_physical_table_fqn(right_table)

        print("🔍 Validating against database...")
        print(f"   Left table: {left_fqn}")
        print(f"   Right table: {right_fqn}")

        # Check if left table exists
        try:
            cursor.execute(f"DESC TABLE {left_fqn}")
        except Exception as e:
            errors.append(
                f"Left table '{left_fqn}' does not exist or is not accessible: {str(e)}"
            )
            return False, errors

        # Check if right table exists
        try:
            cursor.execute(f"DESC TABLE {right_fqn}")
        except Exception as e:
            errors.append(
                f"Right table '{right_fqn}' does not exist or is not accessible: {str(e)}"
            )
            return False, errors

        # Get physical column names and validate they exist
        left_physical_cols = []
        for logical_col in left_columns:
            physical_col = get_physical_column_name(left_table, logical_col)
            if not physical_col:
                errors.append(
                    f"Cannot find physical column for logical column '{logical_col}' in left table"
                )
                return False, errors
            left_physical_cols.append(physical_col)

            # Check column exists in database
            try:
                cursor.execute(f"SELECT {physical_col} FROM {left_fqn} LIMIT 0")
            except Exception as e:
                errors.append(
                    f"Left column '{physical_col}' does not exist in table: {str(e)}"
                )
                return False, errors

        right_physical_cols = []
        for logical_col in right_columns:
            physical_col = get_physical_column_name(right_table, logical_col)
            if not physical_col:
                errors.append(
                    f"Cannot find physical column for logical column '{logical_col}' in right table"
                )
                return False, errors
            right_physical_cols.append(physical_col)

            # Check column exists in database
            try:
                cursor.execute(f"SELECT {physical_col} FROM {right_fqn} LIMIT 0")
            except Exception as e:
                errors.append(
                    f"Right column '{physical_col}' does not exist in table: {str(e)}"
                )
                return False, errors

        print("   ✅ Tables and columns exist")

        # Build JOIN condition
        join_conditions = []
        for left_col, right_col in zip(left_physical_cols, right_physical_cols):
            join_conditions.append(f"l.{left_col} = r.{right_col}")
        join_condition = " AND ".join(join_conditions)

        # Test the JOIN query
        test_query = f"""
        SELECT COUNT(*) as cnt
        FROM {left_fqn} l
        INNER JOIN {right_fqn} r
            ON {join_condition}
        LIMIT 1
        """

        print("   🔍 Testing JOIN query...")
        try:
            cursor.execute(test_query)
            result = cursor.fetchone()
            print("   ✅ JOIN query executed successfully")
            if result and result["CNT"] > 0:
                print(f"   ℹ️  Found {result['CNT']} matching rows")
        except Exception as e:
            errors.append(f"JOIN query failed: {str(e)}")
            return False, errors

        print("   ✅ Relationship is valid in the database")
        return True, []

    except Exception as e:
        errors.append(f"Validation error: {str(e)}")
        return False, errors
    finally:
        cursor.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create valid relationships between two tables in a semantic model"
    )
    parser.add_argument(
        "--semantic-model", required=True, help="Path to semantic model YAML file"
    )
    parser.add_argument(
        "--left-table",
        required=True,
        help="Left table name (logical name from semantic model)",
    )
    parser.add_argument(
        "--right-table",
        required=True,
        help="Right table name (logical name from semantic model)",
    )
    parser.add_argument(
        "--left-columns",
        required=True,
        nargs="+",
        help="Left table join columns (space-separated)",
    )
    parser.add_argument(
        "--right-columns",
        required=True,
        nargs="+",
        help="Right table join columns (space-separated)",
    )
    parser.add_argument(
        "--output", required=True, help="Output YAML file path for the relationship"
    )

    # Database validation arguments
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip database validation (not recommended)",
    )

    args = parser.parse_args()

    # Determine if we should validate
    should_validate = not args.skip_validation

    # Get connection name from environment
    connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME")

    # Validate validation arguments
    if should_validate:
        if not SNOWFLAKE_AVAILABLE:
            print("❌ Error: snowflake-connector-python is not installed")
            print("   Install it with: pip install snowflake-connector-python")
            print("   Or skip validation with --skip-validation")
            sys.exit(1)

        if not connection_name:
            print(
                "❌ Error: SNOWFLAKE_CONNECTION_NAME environment variable is required for validation"
            )
            print("   Set it with: export SNOWFLAKE_CONNECTION_NAME=myconnection")
            print("   Or skip validation with --skip-validation")
            sys.exit(1)

    # Validate input
    if len(args.left_columns) != len(args.right_columns):
        print("❌ Error: Number of left columns must equal number of right columns")
        sys.exit(1)

    # Load semantic model
    print(f"📖 Loading semantic model: {args.semantic_model}")
    semantic_model = load_semantic_model(args.semantic_model)

    # Find tables
    left_table = get_table(semantic_model, args.left_table)
    if not left_table:
        print(f"❌ Error: Left table '{args.left_table}' not found in semantic model")
        sys.exit(1)

    right_table = get_table(semantic_model, args.right_table)
    if not right_table:
        print(f"❌ Error: Right table '{args.right_table}' not found in semantic model")
        sys.exit(1)

    print(f"✅ Found left table: {left_table['name']}")
    print(f"✅ Found right table: {right_table['name']}")

    # Validate columns exist
    left_valid, left_missing = validate_columns_exist(left_table, args.left_columns)
    if not left_valid:
        print(f"❌ Error: Left table columns not found: {left_missing}")
        sys.exit(1)

    right_valid, right_missing = validate_columns_exist(right_table, args.right_columns)
    if not right_valid:
        print(f"❌ Error: Right table columns not found: {right_missing}")
        sys.exit(1)

    print(f"✅ Validated join columns: {args.left_columns} → {args.right_columns}")

    # Show primary keys
    left_pk = get_primary_key_columns(left_table)
    right_pk = get_primary_key_columns(right_table)

    print(f"\n📋 Left table primary key: {left_pk if left_pk else 'None'}")
    print(f"📋 Right table primary key: {right_pk if right_pk else 'None'}")

    # Infer relationship type
    print("\n🔍 Inferring relationship type...")
    rel_type, result = infer_relationship_type(
        left_table, right_table, args.left_columns, args.right_columns
    )

    # Handle result
    if "rejected" in rel_type:
        print(f"\n❌ Relationship REJECTED: {rel_type}")
        print(f"   Reason: {result['message']}")
        print(f"   Suggestion: {result['suggestion']}")
        print(
            "\nℹ️  Note: This is not an error - the script successfully determined that this relationship is not valid."
        )
        print("   Exit code: 2 (rejection, not failure)")
        sys.exit(2)

    print(f"\n✅ Relationship type inferred: {rel_type}")

    # Database validation (default behavior)
    if should_validate:
        print(f"\n🔌 Connecting to Snowflake using connection: {connection_name}")

        try:
            # Connect to Snowflake using connection name
            conn = snowflake.connector.connect(connection_name=connection_name)
            print("✅ Connected to Snowflake")

            # Validate the relationship
            is_valid, validation_errors = validate_relationship_in_database(
                conn, left_table, right_table, args.left_columns, args.right_columns
            )

            conn.close()

            if not is_valid:
                print("\n❌ Relationship validation FAILED:")
                for error in validation_errors:
                    print(f"   - {error}")
                sys.exit(1)

            print("\n✅ Relationship validation PASSED")

        except Exception as e:
            print(f"\n❌ Failed to connect to Snowflake: {str(e)}")
            sys.exit(1)
    else:
        print("\n⚠️  Skipping database validation (not recommended)")

    # Save relationship to output file
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        yaml.dump(result, f, default_flow_style=False, sort_keys=False)

    print(f"\n💾 Relationship saved to: {output_path}")
    print("\n📊 Relationship details:")
    print(yaml.dump(result, default_flow_style=False, sort_keys=False))

    print("\n✅ Done!")


if __name__ == "__main__":
    main()

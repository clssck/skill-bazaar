#!/usr/bin/env python3
"""
Semantic Model GET Tool

A unified tool for reading and extracting components from semantic model YAML files.
Always outputs results in YAML string format for easy consumption by agents.

When retrieving VQRs, SQL queries are automatically translated from logical table/column names
to fully qualified physical names and expressions.

Usage:
    python semantic_model_get.py --file <yaml_file> --component <component_type> [options]

Examples:
    # Get entire semantic model
    python semantic_model_get.py --file model.yaml --component model

    # Get model name
    python semantic_model_get.py --file model.yaml --component name

    # Get model description
    python semantic_model_get.py --file model.yaml --component description

    # Get custom instructions
    python semantic_model_get.py --file model.yaml --component custom_instructions

    # Get all module custom instructions
    python semantic_model_get.py --file model.yaml --component module_custom_instructions

    # Get specific module custom instructions
    python semantic_model_get.py --file model.yaml --component module_custom_instructions --module-name sql_generation

    # Get all tables
    python semantic_model_get.py --file model.yaml --component tables

    # Get specific table
    python semantic_model_get.py --file model.yaml --component table --table-name orders

    # Get all columns from a table
    python semantic_model_get.py --file model.yaml --component columns --table-name orders

    # Get columns by kind
    python semantic_model_get.py --file model.yaml --component columns --table-name orders --kind dimension

    # Get filters (treated as columns with kind='filter')
    python semantic_model_get.py --file model.yaml --component columns --table-name orders --kind filter

    # Get all relationships
    python semantic_model_get.py --file model.yaml --component relationships

    # Get all verified queries
    python semantic_model_get.py --file model.yaml --component verified_queries

    # Get all questions from VQRs
    python semantic_model_get.py --file model.yaml --component verified_queries --extract questions

    # Get all SQL queries from VQRs
    python semantic_model_get.py --file model.yaml --component verified_queries --extract sqls
"""

import argparse
import sys
from typing import Any, Dict, Optional, cast

import yaml
from semantic_view_sql_utils import (
    build_logical_to_physical_column_mapping,
    build_logical_to_physical_mapping,
    resolve_logical_to_physical_column_names,
    resolve_logical_to_physical_table_names,
)


class SemanticModelGetter:
    """Unified getter for semantic model components."""

    def __init__(self, yaml_file: str):
        """Initialize with semantic model YAML file."""
        self.yaml_file = yaml_file
        self.data = self._load_yaml()
        self._table_mapping: Optional[Dict[str, str]] = None
        self._column_mapping: Optional[Dict[str, Dict[str, str]]] = None

    def _load_yaml(self) -> dict[str, Any]:
        """Load and parse semantic model YAML file."""
        try:
            with open(self.yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if not data:
                raise ValueError("Empty YAML file")
            return cast(dict[str, Any], data)
        except FileNotFoundError:
            print(f"❌ Error: File not found: {self.yaml_file}", file=sys.stderr)
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"❌ Error parsing YAML: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error loading file: {e}", file=sys.stderr)
            sys.exit(1)

    def _get_table_mapping(self) -> Dict[str, str]:
        """
        Get or build the logical to physical table name mapping.
        Caches the result for subsequent calls.

        Returns:
            Dict mapping logical_name -> "database.schema.table"
        """
        if self._table_mapping is None:
            self._table_mapping = build_logical_to_physical_mapping(self.data)
        return self._table_mapping

    def _get_column_mapping(self) -> Dict[str, Dict[str, str]]:
        """
        Get or build the logical to physical column expression mapping.
        Caches the result for subsequent calls.

        Returns:
            Nested dict: {table_name: {column_name: physical_expression}}
        """
        if self._column_mapping is None:
            self._column_mapping = build_logical_to_physical_column_mapping(self.data)
        return self._column_mapping

    def _resolve_sql(self, sql: str) -> str:
        """
        Resolve logical table names and column names in SQL to physical expressions.

        Args:
            sql: SQL query with logical table and column names

        Returns:
            SQL query with physical table names and column expressions
        """
        table_mapping = self._get_table_mapping()
        column_mapping = self._get_column_mapping()

        if not table_mapping:
            # No table mapping available, return original SQL
            return sql

        # First resolve table names
        sql = resolve_logical_to_physical_table_names(sql, table_mapping)

        # Then resolve column names
        if column_mapping:
            sql = resolve_logical_to_physical_column_names(
                sql, table_mapping, column_mapping
            )

        return sql

    def get_entire_model(self) -> dict[str, Any]:
        """Get the entire semantic model."""
        return self.data

    def get_name(self) -> Optional[str]:
        """Get the model name."""
        return self.data.get("name")

    def get_description(self) -> Optional[str]:
        """Get the model description."""
        return self.data.get("description")

    def get_custom_instructions(self) -> Optional[str]:
        """Get custom instructions."""
        return self.data.get("custom_instructions")

    def get_module_custom_instructions(
        self, module_name: Optional[str] = None
    ) -> Optional[dict[str, Any]] | Optional[str]:
        """
        Get module-specific custom instructions.

        Args:
            module_name: Optional specific module name ('question_categorization' or 'sql_generation')

        Returns:
            If module_name provided: string of instructions for that module
            If module_name not provided: entire module_custom_instructions dict
        """
        module_instructions = self.data.get("module_custom_instructions")
        if not module_instructions:
            return None

        if module_name:
            return cast(Optional[str], module_instructions.get(module_name))

        return cast(Dict[str, Any], module_instructions)

    def get_tables(self) -> list[dict[str, Any]]:
        """Get all tables (lightweight: name, description, base_table only)."""
        tables = self.data.get("tables", [])
        lightweight_tables = []
        for table in tables:
            lightweight_tables.append(
                {
                    "name": table.get("name"),
                    "description": table.get("description"),
                    "base_table": table.get("base_table"),
                }
            )
        return lightweight_tables

    def get_table(self, table_name: str) -> Optional[dict[str, Any]]:
        """Get a specific table by name (full definition)."""
        tables = self.data.get("tables", [])
        for table in tables:
            if table.get("name") == table_name:
                return cast(dict[str, Any], table)
        return None

    def get_columns(
        self,
        table_name: str,
        column_name: Optional[str] = None,
        kind: Optional[str] = None,
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """
        Get columns from a table (includes dimensions, measures, metrics, time_dimensions, and filters).

        Args:
            table_name: Name of the table
            column_name: Optional specific column name
            kind: Optional filter by column kind (dimension, measure, time_dimension, metric, filter)

        Returns:
            List of columns, single column dict, or None
        """
        table = self.get_table(table_name)
        if not table:
            return None

        # Collect columns from different sections
        all_columns = []

        # Add from dimensions
        for dim in table.get("dimensions", []):
            col = dict(dim)
            col["kind"] = "dimension"
            all_columns.append(col)

        # Add from time_dimensions
        for time_dim in table.get("time_dimensions", []):
            col = dict(time_dim)
            col["kind"] = "time_dimension"
            all_columns.append(col)

        # Add from measures/facts
        for measure in table.get("measures", []):
            col = dict(measure)
            col["kind"] = "measure"
            all_columns.append(col)

        for fact in table.get("facts", []):
            col = dict(fact)
            col["kind"] = "fact"
            all_columns.append(col)

        # Add from metrics (table-level)
        for metric in table.get("metrics", []):
            col = dict(metric)
            col["kind"] = "metric"
            all_columns.append(col)

        # Add from filters (treat as columns with kind='filter')
        for filter_item in table.get("filters", []):
            col = dict(filter_item)
            col["kind"] = "filter"
            all_columns.append(col)

        # Filter by kind if specified
        if kind:
            all_columns = [col for col in all_columns if col.get("kind") == kind]

        # Filter by column name if specified
        if column_name:
            for col in all_columns:
                if col.get("name") == column_name:
                    return col
            return None

        return all_columns

    def get_filters(
        self, table_name: str, filter_name: Optional[str] = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """Get filters from a table."""
        table = self.get_table(table_name)
        if not table:
            return None

        filters = table.get("filters", [])

        if filter_name:
            for f in filters:
                if f.get("name") == filter_name:
                    return cast(dict[str, Any], f)
            return None

        return cast(list[dict[str, Any]], filters)

    def get_primary_key(self, table_name: str) -> Optional[dict[str, Any]]:
        """Get primary key definition from a table."""
        table = self.get_table(table_name)
        if not table:
            return None
        return table.get("primary_key")

    def get_relationships(self) -> list[dict[str, Any]]:
        """Get all relationships."""
        return cast(list[dict[str, Any]], self.data.get("relationships", []))

    def get_verified_queries(
        self, vqr_name: Optional[str] = None, vqr_id: Optional[int] = None
    ) -> list[dict[str, Any]] | dict[str, Any] | None:
        """
        Get verified queries with SQL automatically resolved to physical table names.

        Args:
            vqr_name: Optional name to filter by
            vqr_id: Optional ID (0-based index) to filter by
        """
        vqrs = self.data.get("verified_queries", [])

        # Helper function to resolve SQL in a VQR
        def resolve_vqr_sql(vqr: dict[str, Any]) -> dict[str, Any]:
            vqr_copy = vqr.copy()
            sql = vqr_copy.get("sql")
            if sql:
                vqr_copy["sql"] = self._resolve_sql(sql)
            return vqr_copy

        if vqr_id is not None:
            if 0 <= vqr_id < len(vqrs):
                return resolve_vqr_sql(vqrs[vqr_id])
            return None

        if vqr_name:
            for vqr in vqrs:
                if vqr.get("name") == vqr_name:
                    return resolve_vqr_sql(vqr)
            return None

        # Return all VQRs with resolved SQL
        return [resolve_vqr_sql(vqr) for vqr in vqrs]

    def get_vqr_questions(self) -> list[str]:
        """
        Get all questions from verified queries.

        Returns:
            List of question strings from all VQRs
        """
        vqrs = self.data.get("verified_queries", [])
        questions = []
        for vqr in vqrs:
            question = vqr.get("question")
            if question:
                questions.append(question)
        return questions

    def get_vqr_queries(self) -> list[str]:
        """
        Get all SQL queries from verified queries with physical table names resolved.

        Returns:
            List of SQL query strings from all VQRs with physical table names
        """
        vqrs = self.data.get("verified_queries", [])
        queries = []
        for vqr in vqrs:
            # VQRs can have either 'sql' or 'verified_query' field
            sql = vqr.get("sql")
            if sql:
                resolved_sql = self._resolve_sql(sql)
                queries.append(resolved_sql)
        return queries


def format_output(data: Any) -> str:
    """
    Format output as YAML string.

    Args:
        data: Data to format

    Returns:
        YAML formatted string
    """
    if data is None:
        return "result: null\n"

    # Return full data as YAML
    return cast(str, yaml.dump(data, default_flow_style=False, sort_keys=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Get components from semantic model YAML files. Always outputs in YAML format.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get entire semantic model
  %(prog)s --file model.yaml --component model

  # Get model name
  %(prog)s --file model.yaml --component name

  # Get model description
  %(prog)s --file model.yaml --component description

  # Get all tables
  %(prog)s --file model.yaml --component tables

  # Get specific table
  %(prog)s --file model.yaml --component table --table-name orders

  # Get columns from a table
  %(prog)s --file model.yaml --component columns --table-name orders

  # Get dimension columns only
  %(prog)s --file model.yaml --component columns --table-name orders --kind dimension

  # Get filters (as columns with kind='filter')
  %(prog)s --file model.yaml --component columns --table-name orders --kind filter
        """,
    )

    # Required arguments
    parser.add_argument(
        "--file", required=True, help="Path to semantic model YAML file"
    )
    parser.add_argument(
        "--component",
        required=True,
        choices=[
            "model",
            "name",
            "description",
            "custom_instructions",
            "module_custom_instructions",
            "tables",
            "table",
            "columns",
            "column",
            "primary_key",
            "relationships",
            "verified_queries",
            "verified_query",
        ],
        help="Component type to retrieve",
    )

    # Optional filter arguments
    parser.add_argument(
        "--table-name", help="Table name (required for table/column operations)"
    )
    parser.add_argument(
        "--column-name", help="Column name (for specific column lookup)"
    )
    parser.add_argument(
        "--kind",
        choices=["dimension", "time_dimension", "measure", "fact", "metric", "filter"],
        help="Filter columns by kind",
    )
    parser.add_argument(
        "--module-name",
        choices=["question_categorization", "sql_generation"],
        help="Module name for module_custom_instructions",
    )
    parser.add_argument("--vqr-name", help="Verified query name")
    parser.add_argument("--vqr-id", type=int, help="Verified query ID (0-based index)")
    parser.add_argument(
        "--extract",
        choices=["questions", "sqls"],
        help="Extract specific field from verified_queries (questions or SQL queries)",
    )

    args = parser.parse_args()

    # Validate required arguments for specific components
    if args.component in ["table", "columns", "column", "primary_key"]:
        if not args.table_name:
            parser.error(f"--table-name is required for component '{args.component}'")

    if args.component == "column":
        if not args.column_name:
            parser.error("--column-name is required for component 'column'")

    # Initialize getter
    getter = SemanticModelGetter(args.file)

    # Route to appropriate method
    result: Any = None

    try:
        if args.component == "model":
            result = getter.get_entire_model()

        elif args.component == "name":
            result = getter.get_name()

        elif args.component == "description":
            result = getter.get_description()

        elif args.component == "custom_instructions":
            result = getter.get_custom_instructions()

        elif args.component == "module_custom_instructions":
            result = getter.get_module_custom_instructions(module_name=args.module_name)

        elif args.component == "tables":
            result = getter.get_tables()

        elif args.component == "table":
            result = getter.get_table(args.table_name)
            if result is None:
                print(f"❌ Error: Table '{args.table_name}' not found", file=sys.stderr)
                sys.exit(1)

        elif args.component in ["columns", "column"]:
            result = getter.get_columns(
                args.table_name, column_name=args.column_name, kind=args.kind
            )
            if result is None:
                if args.column_name:
                    print(
                        f"❌ Error: Column '{args.column_name}' not found in table '{args.table_name}'",
                        file=sys.stderr,
                    )
                else:
                    print(
                        f"❌ Error: Table '{args.table_name}' not found", file=sys.stderr
                    )
                sys.exit(1)

        elif args.component == "primary_key":
            result = getter.get_primary_key(args.table_name)
            if result is None:
                print(
                    f"❌ Error: No primary key found for table '{args.table_name}' or table not found",
                    file=sys.stderr,
                )
                sys.exit(1)

        elif args.component == "relationships":
            result = getter.get_relationships()

        elif args.component in ["verified_queries", "verified_query"]:
            # Handle extraction of specific fields
            if args.extract and args.component == "verified_queries":
                if args.extract == "questions":
                    result = getter.get_vqr_questions()
                elif args.extract == "sqls":
                    result = getter.get_vqr_queries()
            else:
                result = getter.get_verified_queries(
                    vqr_name=args.vqr_name, vqr_id=args.vqr_id
                )
                if result is None and (args.vqr_name or args.vqr_id is not None):
                    identifier = args.vqr_name or f"ID {args.vqr_id}"
                    print(
                        f"❌ Error: Verified query '{identifier}' not found",
                        file=sys.stderr,
                    )
                    sys.exit(1)

        # Format and output
        output = format_output(result)
        print(output, end="")

    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

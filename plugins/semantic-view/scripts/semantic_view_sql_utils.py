#!/usr/bin/env python3
"""
Shared SQL Translation Utilities

Common functions for translating between logical and physical table/column names
in semantic model SQL queries. Used by both semantic_view_get.py and semantic_view_set.py.
"""

from typing import Any, Dict, cast

import sqlglot
from sqlglot import exp

# ============================================================================
# Table Mapping Builders
# ============================================================================


def build_logical_to_physical_mapping(
    semantic_model_data: Dict[str, Any]
) -> Dict[str, str]:
    """Build mapping from logical table names to physical FQNs."""
    mapping = {}
    tables = semantic_model_data.get("tables", [])

    for table in tables:
        logical_name = table.get("name")
        base_table = table.get("base_table", {})

        if logical_name and base_table:
            database = base_table.get("database", "")
            schema = base_table.get("schema", "")
            table_name = base_table.get("table", "")

            if database and schema and table_name:
                physical_fqn = f"{database}.{schema}.{table_name}"
                mapping[logical_name] = physical_fqn

    return mapping


def build_physical_to_logical_mapping(
    semantic_model_data: Dict[str, Any]
) -> Dict[str, str]:
    """Build mapping from physical FQNs to logical table names."""
    mapping = {}
    tables = semantic_model_data.get("tables", [])

    for table in tables:
        logical_name = table.get("name")
        base_table = table.get("base_table", {})

        if logical_name and base_table:
            database = base_table.get("database", "")
            schema = base_table.get("schema", "")
            table_name = base_table.get("table", "")

            if database and schema and table_name:
                physical_fqn = f"{database}.{schema}.{table_name}"
                mapping[physical_fqn] = logical_name

    return mapping


# ============================================================================
# Column Mapping Builders
# ============================================================================


def build_logical_to_physical_column_mapping(
    semantic_model_data: Dict[str, Any]
) -> Dict[str, Dict[str, str]]:
    """Build mapping: {table_name: {column_name: physical_expression}}."""
    column_mapping = {}
    tables = semantic_model_data.get("tables", [])

    for table in tables:
        table_name = table.get("name")
        if not table_name:
            continue

        table_columns = {}
        for section in [
            "dimensions",
            "time_dimensions",
            "measures",
            "facts",
            "metrics",
        ]:
            for col in table.get(section, []):
                col_name = col.get("name")
                col_expr = col.get("expr")
                if col_name and col_expr:
                    table_columns[col_name] = col_expr

        if table_columns:
            column_mapping[table_name] = table_columns

    return column_mapping


def build_physical_to_logical_column_mapping(
    semantic_model_data: Dict[str, Any]
) -> Dict[str, Dict[str, str]]:
    """Build mapping: {table_name: {physical_expression: column_name}}."""
    column_mapping = {}
    tables = semantic_model_data.get("tables", [])

    for table in tables:
        table_name = table.get("name")
        if not table_name:
            continue

        table_columns = {}
        for section in [
            "dimensions",
            "time_dimensions",
            "measures",
            "facts",
            "metrics",
        ]:
            for col in table.get(section, []):
                col_name = col.get("name")
                col_expr = col.get("expr")
                if col_name and col_expr:
                    table_columns[col_expr] = col_name

        if table_columns:
            column_mapping[table_name] = table_columns

    return column_mapping


# ============================================================================
# Helper Functions
# ============================================================================


def collect_cte_names(parsed_sql: exp.Expression) -> set[str]:
    cte_names = set()
    for cte in parsed_sql.find_all(exp.CTE):
        if cte.alias:
            cte_names.add(cte.alias)
    return cte_names


def is_already_qualified(table_node: exp.Table) -> bool:
    return bool(table_node.catalog and table_node.db)


def case_insensitive_lookup(key: str, mapping: Dict[str, str]) -> str | None:
    for variant in [key, key.lower(), key.upper()]:
        if variant in mapping:
            return mapping[variant]
    return None


def case_insensitive_column_lookup(
    column_name: str, columns_dict: Dict[str, str]
) -> str | None:
    for variant in [column_name, column_name.lower(), column_name.upper()]:
        if variant in columns_dict:
            return columns_dict[variant]
    return None


def build_fqn_from_table_node(table_node: exp.Table) -> str:
    if table_node.catalog and table_node.db and table_node.this:
        return f"{table_node.catalog}.{table_node.db}.{table_node.this}"
    elif table_node.db and table_node.this:
        return f"{table_node.db}.{table_node.this}"
    elif table_node.this:
        return str(table_node.this)
    else:
        return ""


# ============================================================================
# Table Name Resolution
# ============================================================================


def resolve_logical_to_physical_table_names(sql: str, mapping: Dict[str, str]) -> str:
    """Replace logical table names with physical FQNs in SQL."""
    try:
        parsed = sqlglot.parse_one(sql, dialect="snowflake")
        cte_names = collect_cte_names(parsed)

        for table_node in parsed.find_all(exp.Table):
            table_name = table_node.name
            if not table_name or table_name in cte_names:
                continue
            if is_already_qualified(table_node):
                continue

            physical_fqn = case_insensitive_lookup(table_name, mapping)
            if physical_fqn:
                parts = physical_fqn.split(".")
                if len(parts) == 3:
                    table_node.set("catalog", exp.Identifier(this=parts[0]))
                    table_node.set("db", exp.Identifier(this=parts[1]))
                    table_node.set("this", exp.Identifier(this=parts[2]))

        return cast(str, parsed.sql(dialect="snowflake"))

    except Exception as e:
        print(f"⚠️  Failed to translate logical→physical table names: {e}")
        return sql


def resolve_physical_to_logical_table_names(
    sql: str, reverse_mapping: Dict[str, str]
) -> str:
    """Replace physical table FQNs with logical table names in SQL."""
    try:
        parsed = sqlglot.parse_one(sql, dialect="snowflake")
        cte_names = collect_cte_names(parsed)

        for table_node in parsed.find_all(exp.Table):
            table_name = table_node.name
            if not table_name or table_name in cte_names:
                continue

            fqn = build_fqn_from_table_node(table_node)
            if not fqn:
                continue

            logical_name = case_insensitive_lookup(fqn, reverse_mapping)
            if logical_name:
                table_node.set("catalog", None)
                table_node.set("db", None)
                table_node.set("this", exp.Identifier(this=logical_name))

        return cast(str, parsed.sql(dialect="snowflake"))

    except Exception as e:
        print(f"⚠️  Failed to translate physical→logical table names: {e}")
        return sql


# ============================================================================
# Column Name Resolution
# ============================================================================


def resolve_logical_to_physical_column_names(
    sql: str, table_mapping: Dict[str, str], column_mapping: Dict[str, Dict[str, str]]
) -> str:
    """
    Replace logical column names with physical expressions in SQL.

    Behavior:
    - Columns from base tables → replaced with physical expressions
    - Columns from CTEs → kept as-is (they're CTE output columns)
    - Uses table context to identify which columns to translate
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect="snowflake")
        cte_names = collect_cte_names(parsed)

        # Build reverse table mapping
        reverse_table_mapping = {}
        for logical, physical in table_mapping.items():
            reverse_table_mapping[physical] = logical
            reverse_table_mapping[logical] = logical
            parts = physical.split(".")
            if len(parts) == 3:
                reverse_table_mapping[parts[2]] = logical

        # Build alias-to-table mapping
        alias_to_table = {}
        for table_node in parsed.find_all(exp.Table):
            table_name = table_node.name
            if table_name and table_name not in cte_names:
                alias = table_node.alias
                if alias:
                    alias_to_table[alias] = table_name

        def is_referencing_cte(column_node: exp.Column) -> bool:
            table_ref = column_node.table
            if not table_ref:
                current = column_node.parent
                while current:
                    if isinstance(current, exp.Select):
                        from_clause = current.args.get("from")
                        if from_clause and isinstance(from_clause, exp.From):
                            from_table = from_clause.this
                            if isinstance(from_table, exp.Table):
                                if from_table.name in cte_names:
                                    return True
                        break
                    current = current.parent
                return False
            return table_ref in cte_names

        for column_node in parsed.find_all(exp.Column):
            col_name = column_node.name
            if not col_name or is_referencing_cte(column_node):
                continue

            table_ref = column_node.table
            logical_table = None

            if table_ref:
                if table_ref in cte_names:
                    continue

                # Resolve alias to actual table name
                actual_table = alias_to_table.get(table_ref, table_ref)

                # Look up logical table name
                logical_table = reverse_table_mapping.get(actual_table)
                if not logical_table:
                    for key, val in reverse_table_mapping.items():
                        if key.upper() == actual_table.upper():
                            logical_table = val
                            break
            else:
                for tbl_name, tbl_columns in column_mapping.items():
                    if case_insensitive_column_lookup(col_name, tbl_columns):
                        logical_table = tbl_name
                        break

            if logical_table and logical_table in column_mapping:
                table_columns = column_mapping[logical_table]
                physical_expr = case_insensitive_column_lookup(col_name, table_columns)
                if physical_expr:
                    try:
                        physical_parsed = sqlglot.parse_one(
                            physical_expr, dialect="snowflake", into=exp.Column
                        )
                        column_node.replace(physical_parsed)
                    except Exception:
                        pass

        return cast(str, parsed.sql(dialect="snowflake"))

    except Exception as e:
        print(f"⚠️  Failed to translate logical→physical column names: {e}")
        return sql


def resolve_physical_to_logical_column_names(
    sql: str, table_mapping: Dict[str, str], column_mapping: Dict[str, Dict[str, str]]
) -> str:
    """
    Replace physical column expressions with logical column names in SQL.

    Behavior:
    - Columns with physical expressions from base tables → replaced with logical names
    - Columns from CTEs → kept as-is (they're CTE output columns)
    - Uses table context to identify which columns to translate
    """
    try:
        parsed = sqlglot.parse_one(sql, dialect="snowflake")
        cte_names = collect_cte_names(parsed)

        # Build logical table mapping
        logical_table_mapping = {}
        for physical, logical in table_mapping.items():
            logical_table_mapping[physical] = logical
            logical_table_mapping[logical] = logical
            parts = physical.split(".")
            if len(parts) == 3:
                logical_table_mapping[parts[2]] = logical

        # Build alias-to-table mapping
        alias_to_table = {}
        for table_node in parsed.find_all(exp.Table):
            table_name = table_node.name
            if table_name and table_name not in cte_names:
                alias = table_node.alias
                if alias:
                    alias_to_table[alias] = table_name

        def is_referencing_cte(column_node: exp.Column) -> bool:
            table_ref = column_node.table
            if not table_ref:
                current = column_node.parent
                while current:
                    if isinstance(current, exp.Select):
                        from_clause = current.args.get("from")
                        if from_clause and isinstance(from_clause, exp.From):
                            from_table = from_clause.this
                            if isinstance(from_table, exp.Table):
                                if from_table.name in cte_names:
                                    return True
                        break
                    current = current.parent
                return False
            return table_ref in cte_names

        for column_node in parsed.find_all(exp.Column):
            col_name = column_node.name
            if not col_name or is_referencing_cte(column_node):
                continue

            table_ref = column_node.table
            logical_table = None

            if table_ref:
                if table_ref in cte_names:
                    continue

                # Resolve alias to actual table name
                actual_table = alias_to_table.get(table_ref, table_ref)

                # Look up logical table name
                logical_table = logical_table_mapping.get(actual_table)
                if not logical_table:
                    for key, val in logical_table_mapping.items():
                        if key.upper() == actual_table.upper():
                            logical_table = val
                            break
            else:
                for tbl_name, tbl_columns in column_mapping.items():
                    if case_insensitive_column_lookup(col_name, tbl_columns):
                        logical_table = tbl_name
                        break

            if logical_table and logical_table in column_mapping:
                table_columns = column_mapping[logical_table]
                logical_name = case_insensitive_column_lookup(col_name, table_columns)
                if logical_name:
                    new_column = exp.Column(this=exp.Identifier(this=logical_name))
                    if column_node.table:
                        new_column.set("table", exp.Identifier(this=column_node.table))
                    column_node.replace(new_column)

        return cast(str, parsed.sql(dialect="snowflake"))

    except Exception as e:
        print(f"⚠️  Failed to translate physical→logical column names: {e}")
        return sql

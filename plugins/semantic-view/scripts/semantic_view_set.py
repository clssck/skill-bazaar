#!/usr/bin/env python3
"""
Semantic Model SET Tool

A unified tool for modifying semantic model YAML files through create, update,
and delete operations. Always outputs to a new file for safety.

Usage:
    python semantic_model_set.py --input-file <input.yaml> --output-file <output.yaml> --operations-json '<json_array>'

Examples:
    # Update model description
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_v2.yaml \
      --operations-json '[{"operation":"update","component":"description","value":"Updated description"}]'

    # Delete all VQRs (for audit mode)
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_no_vqrs.yaml \
      --operations-json '[{"operation":"delete","component":"verified_queries"}]'

    # Create module custom instructions for SQL generation
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_v2.yaml \
      --operations-json '[{"operation":"create","component":"module_custom_instructions","module_name":"sql_generation","value":"Always use LEFT JOINs"}]'

    # Update module custom instructions (append mode)
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_v2.yaml \
      --operations-json '[{"operation":"update","component":"module_custom_instructions","module_name":"sql_generation","value":"Use CURRENT_DATE() for dates","mode":"append"}]'

    # Update column description
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_v2.yaml \
      --operations-json '[{"operation":"update","component":"column","table_name":"orders","column_name":"amount","property":"description","value":"Order total in USD"}]'

    # Create new column
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_v2.yaml \
      --operations-json '[{"operation":"create","component":"column","table_name":"orders","data":{"name":"new_metric","kind":"metric","expr":"SUM(amount)"}}]'

    # Multiple operations at once
    python semantic_model_set.py \
      --input-file model.yaml \
      --output-file model_v2.yaml \
      --operations-json '[
        {"operation":"update","component":"description","value":"Updated model"},
        {"operation":"update","component":"table","table_name":"orders","property":"description","value":"Enhanced orders table"},
        {"operation":"delete","component":"verified_queries"}
      ]'
"""

import argparse
import json
import sys
from typing import Any, Dict, Optional, cast

import yaml
from semantic_view_sql_utils import (
    build_physical_to_logical_column_mapping,
    build_physical_to_logical_mapping,
    resolve_physical_to_logical_column_names,
    resolve_physical_to_logical_table_names,
)


class IndentedDumper(yaml.Dumper):
    """Custom YAML dumper with consistent indentation for lists."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:  # type: ignore[override]
        super().increase_indent(flow, False)  # type: ignore[no-untyped-call]


class SemanticModelSetter:
    """Unified setter for semantic model modifications."""

    def __init__(self, yaml_file: str):
        """Initialize with semantic model YAML file."""
        self.yaml_file = yaml_file
        self.data = self._load_yaml()
        self.operations_applied: list[str] = []
        self._physical_to_logical_mapping: Optional[Dict[str, str]] = None
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
            print(f"❌ Error: Input file not found: {self.yaml_file}", file=sys.stderr)
            sys.exit(1)
        except yaml.YAMLError as e:
            print(f"❌ Error parsing YAML file: {e}", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"❌ Error loading file: {e}", file=sys.stderr)
            sys.exit(1)

    def _save_yaml(self, output_file: str) -> None:
        """Save modified semantic model to output file."""
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                yaml.dump(
                    self.data,
                    f,
                    Dumper=IndentedDumper,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                    indent=2,
                    width=999999,
                )
        except Exception as e:
            print(f"❌ Error writing output file: {e}", file=sys.stderr)
            sys.exit(1)

    def _find_table(self, table_name: str) -> Optional[dict[str, Any]]:
        """Find table by name."""
        tables = self.data.get("tables", [])
        for table in tables:
            if table.get("name") == table_name:
                return cast(dict[str, Any], table)
        return None

    def _find_column_in_section(
        self, section: list[Any], column_name: str
    ) -> Optional[dict[str, Any]]:
        """Find column in a specific section (dimensions, measures, etc.)."""
        for col in section:
            if col.get("name") == column_name:
                return cast(dict[str, Any], col)
        return None

    def _find_column(
        self, table: dict[str, Any], column_name: str
    ) -> tuple[Optional[dict[str, Any]], Optional[str]]:
        """Find column in table and return (column, section_name)."""
        for section_name in [
            "dimensions",
            "time_dimensions",
            "measures",
            "facts",
            "metrics",
            "filters",
        ]:
            section = table.get(section_name, [])
            col = self._find_column_in_section(section, column_name)
            if col:
                return col, section_name
        return None, None

    def _find_relationship(self, relationship_name: str) -> Optional[dict[str, Any]]:
        """Find relationship by name."""
        relationships = self.data.get("relationships", [])
        for rel in relationships:
            if rel.get("name") == relationship_name:
                return cast(dict[str, Any], rel)
        return None

    def _find_vqr(
        self, vqr_name: Optional[str] = None, vqr_id: Optional[int] = None
    ) -> Optional[dict[str, Any]]:
        """Find VQR by name or ID."""
        vqrs = self.data.get("verified_queries", [])

        if vqr_id is not None:
            if 0 <= vqr_id < len(vqrs):
                return cast(dict[str, Any], vqrs[vqr_id])
            return None

        if vqr_name:
            for vqr in vqrs:
                if vqr.get("name") == vqr_name:
                    return cast(dict[str, Any], vqr)

        return None

    def _get_physical_to_logical_mapping(self) -> Dict[str, str]:
        """Build and cache physical to logical table name mapping."""
        if self._physical_to_logical_mapping is None:
            self._physical_to_logical_mapping = build_physical_to_logical_mapping(
                self.data
            )
        return self._physical_to_logical_mapping

    def _get_column_mapping(self) -> Dict[str, Dict[str, str]]:
        """Build and cache physical to logical column expression mapping."""
        if self._column_mapping is None:
            self._column_mapping = build_physical_to_logical_column_mapping(self.data)
        return self._column_mapping

    def _translate_vqr_sql(self, sql: str) -> str:
        """Translate physical table and column names to logical names."""
        table_mapping = self._get_physical_to_logical_mapping()
        column_mapping = self._get_column_mapping()

        if not table_mapping:
            return sql

        # First resolve table names
        sql = resolve_physical_to_logical_table_names(sql, table_mapping)

        # Then resolve column names if mapping available
        if column_mapping:
            sql = resolve_physical_to_logical_column_names(
                sql, table_mapping, column_mapping
            )

        return sql

    # CREATE operations
    def create_table(self, data: dict[str, Any]) -> None:
        """Create a new table."""
        if "tables" not in self.data:
            self.data["tables"] = []

        table_name = data.get("name")
        if not table_name:
            raise ValueError("Table data must include 'name' field")

        # Check if table already exists
        if self._find_table(table_name):
            raise ValueError(f"Table '{table_name}' already exists")

        self.data["tables"].append(data)
        self.operations_applied.append(f"Created table: {table_name}")

    def create_column(self, table_name: str, data: dict[str, Any]) -> None:
        """Create a new column in a table."""
        table = self._find_table(table_name)
        if not table:
            raise ValueError(f"Table '{table_name}' not found")

        column_name = data.get("name")
        if not column_name:
            raise ValueError("Column data must include 'name' field")

        kind = data.get("kind")
        if not kind:
            raise ValueError(
                "Column data must include 'kind' field (dimension, measure, metric, time_dimension, filter)"
            )

        # Check if column already exists
        existing_col, _ = self._find_column(table, column_name)
        if existing_col:
            raise ValueError(
                f"Column '{column_name}' already exists in table '{table_name}'"
            )

        # Map kind to section
        section_map = {
            "dimension": "dimensions",
            "time_dimension": "time_dimensions",
            "measure": "measures",
            "fact": "facts",
            "metric": "metrics",
            "filter": "filters",
        }

        section_name = section_map.get(kind)
        if not section_name:
            raise ValueError(f"Invalid column kind: {kind}")

        # Remove 'kind' from data as it's not part of the semantic model schema
        # Also remove 'data_type' if kind is 'metric' or 'filter' (they don't have data_type)
        column_data = {k: v for k, v in data.items() if k != "kind"}
        if kind in ("metric", "filter") and "data_type" in column_data:
            column_data = {k: v for k, v in column_data.items() if k != "data_type"}
            print(
                f"⚠️  Warning: Removed 'data_type' from {kind} '{column_name}' ({kind}s don't support data_type field)"
            )

        # Ensure section exists
        if section_name not in table:
            table[section_name] = []

        table[section_name].append(column_data)
        self.operations_applied.append(f"Created {kind}: {table_name}.{column_name}")

    def create_relationship(self, data: dict[str, Any]) -> None:
        """Create a new relationship."""
        if "relationships" not in self.data:
            self.data["relationships"] = []

        rel_name = data.get("name")
        if not rel_name:
            raise ValueError("Relationship data must include 'name' field")

        # Check if relationship already exists
        if self._find_relationship(rel_name):
            raise ValueError(f"Relationship '{rel_name}' already exists")

        self.data["relationships"].append(data)
        self.operations_applied.append(f"Created relationship: {rel_name}")

    def create_verified_query(self, data: dict[str, Any]) -> None:
        """Create a new verified query."""
        if "verified_queries" not in self.data:
            self.data["verified_queries"] = []

        vqr_name = data.get("name")
        if not vqr_name:
            raise ValueError("Verified query data must include 'name' field")

        # Check if VQR already exists
        if self._find_vqr(vqr_name=vqr_name):
            raise ValueError(f"Verified query '{vqr_name}' already exists")

        # Translate SQL from physical to logical table names if present
        if "sql" in data and data["sql"]:
            data["sql"] = self._translate_vqr_sql(data["sql"])

        self.data["verified_queries"].append(data)
        self.operations_applied.append(f"Created verified query: {vqr_name}")

    def create_custom_instructions(self, value: str) -> None:
        """Create custom instructions (only if they don't already exist)."""
        if "custom_instructions" in self.data and self.data["custom_instructions"]:
            raise ValueError(
                "Custom instructions already exist. Use 'update' operation to modify them."
            )

        self.data["custom_instructions"] = value
        self.operations_applied.append("Created custom instructions")

    def create_module_custom_instructions(self, module_name: str, value: str) -> None:
        """Create module-specific custom instructions."""
        if "module_custom_instructions" not in self.data:
            self.data["module_custom_instructions"] = {}

        if module_name in self.data["module_custom_instructions"]:
            raise ValueError(
                f"Module custom instructions for '{module_name}' already exist. Use 'update' operation to modify them."
            )

        self.data["module_custom_instructions"][module_name] = value
        self.operations_applied.append(
            f"Created module custom instructions for: {module_name}"
        )

    # UPDATE operations
    def update_name(self, value: str) -> None:
        """Update model name."""
        self.data["name"] = value
        self.operations_applied.append("Updated model name")

    def update_description(self, value: str) -> None:
        """Update model description."""
        self.data["description"] = value
        self.operations_applied.append("Updated model description")

    def update_custom_instructions(self, value: str, mode: str = "replace") -> None:
        """Update custom instructions."""
        if mode == "append":
            existing = self.data.get("custom_instructions", "")
            # Add newline separator if existing content exists
            if existing:
                self.data["custom_instructions"] = existing + "\n" + value
            else:
                self.data["custom_instructions"] = value
        else:
            self.data["custom_instructions"] = value
        self.operations_applied.append("Updated custom instructions")

    def update_module_custom_instructions(
        self, module_name: str, value: str, mode: str = "replace"
    ) -> None:
        """Update module-specific custom instructions."""
        if "module_custom_instructions" not in self.data:
            self.data["module_custom_instructions"] = {}

        if mode == "append":
            existing = self.data["module_custom_instructions"].get(module_name, "")
            # Add newline separator if existing content exists
            if existing:
                self.data["module_custom_instructions"][module_name] = (
                    existing + "\n" + value
                )
            else:
                self.data["module_custom_instructions"][module_name] = value
        else:
            self.data["module_custom_instructions"][module_name] = value

        self.operations_applied.append(
            f"Updated module custom instructions for: {module_name}"
        )

    def update_table(
        self, table_name: str, property: str, value: Any, mode: str = "replace"
    ) -> None:
        """Update a table property."""
        table = self._find_table(table_name)
        if not table:
            raise ValueError(f"Table '{table_name}' not found")

        if property == "synonyms" and mode == "append":
            if "synonyms" not in table:
                table["synonyms"] = []
            if isinstance(value, list):
                table["synonyms"].extend(value)
            else:
                table["synonyms"].append(value)
        else:
            table[property] = value

        self.operations_applied.append(f"Updated table {table_name}.{property}")

    def update_column(
        self,
        table_name: str,
        column_name: str,
        property: str,
        value: Any,
        mode: str = "replace",
    ) -> None:
        """Update a column property."""
        table = self._find_table(table_name)
        if not table:
            raise ValueError(f"Table '{table_name}' not found")

        column, section = self._find_column(table, column_name)
        if not column:
            raise ValueError(
                f"Column '{column_name}' not found in table '{table_name}'"
            )

        if property == "synonyms" and mode == "append":
            if "synonyms" not in column:
                column["synonyms"] = []
            if isinstance(value, list):
                column["synonyms"].extend(value)
            else:
                column["synonyms"].append(value)
        else:
            column[property] = value

        self.operations_applied.append(
            f"Updated column {table_name}.{column_name}.{property}"
        )

    def update_relationship(
        self, relationship_name: str, property: str, value: Any
    ) -> None:
        """Update a relationship property."""
        relationship = self._find_relationship(relationship_name)
        if not relationship:
            raise ValueError(f"Relationship '{relationship_name}' not found")

        relationship[property] = value
        self.operations_applied.append(
            f"Updated relationship {relationship_name}.{property}"
        )

    def update_verified_query(
        self, vqr_name: Optional[str], vqr_id: Optional[int], property: str, value: Any
    ) -> None:
        """Update a verified query property."""
        vqr = self._find_vqr(vqr_name=vqr_name, vqr_id=vqr_id)
        if not vqr:
            identifier = vqr_name or f"ID {vqr_id}"
            raise ValueError(f"Verified query '{identifier}' not found")

        # Translate SQL from physical to logical table names if updating SQL
        if property == "sql" and value:
            value = self._translate_vqr_sql(value)

        vqr[property] = value
        self.operations_applied.append(
            f"Updated verified query {vqr_name or vqr_id}.{property}"
        )

    # DELETE operations
    def delete_table(self, table_name: str) -> None:
        """Delete a table."""
        tables = self.data.get("tables", [])
        original_len = len(tables)

        self.data["tables"] = [t for t in tables if t.get("name") != table_name]

        if len(self.data["tables"]) == original_len:
            raise ValueError(f"Table '{table_name}' not found")

        self.operations_applied.append(f"Deleted table: {table_name}")

    def delete_column(self, table_name: str, column_name: str) -> None:
        """Delete a column from a table."""
        table = self._find_table(table_name)
        if not table:
            raise ValueError(f"Table '{table_name}' not found")

        column, section_name = self._find_column(table, column_name)
        if not column or not section_name:
            raise ValueError(
                f"Column '{column_name}' not found in table '{table_name}'"
            )

        # Remove from the appropriate section
        section = table.get(section_name, [])
        table[section_name] = [c for c in section if c.get("name") != column_name]

        self.operations_applied.append(f"Deleted column: {table_name}.{column_name}")

    def delete_relationship(self, relationship_name: str) -> None:
        """Delete a relationship."""
        relationships = self.data.get("relationships", [])
        original_len = len(relationships)

        self.data["relationships"] = [
            r for r in relationships if r.get("name") != relationship_name
        ]

        if len(self.data["relationships"]) == original_len:
            raise ValueError(f"Relationship '{relationship_name}' not found")

        self.operations_applied.append(f"Deleted relationship: {relationship_name}")

    def delete_verified_query(
        self, vqr_name: Optional[str], vqr_id: Optional[int]
    ) -> None:
        """Delete a specific verified query."""
        vqrs = self.data.get("verified_queries", [])
        original_len = len(vqrs)

        if vqr_id is not None:
            if 0 <= vqr_id < len(vqrs):
                del vqrs[vqr_id]
                identifier = f"ID {vqr_id}"
            else:
                raise ValueError(f"Verified query ID {vqr_id} out of range")
        elif vqr_name:
            self.data["verified_queries"] = [
                v for v in vqrs if v.get("name") != vqr_name
            ]
            identifier = vqr_name
        else:
            raise ValueError("Must provide vqr_name or vqr_id")

        if len(self.data["verified_queries"]) == original_len and vqr_name:
            raise ValueError(f"Verified query '{vqr_name}' not found")

        self.operations_applied.append(f"Deleted verified query: {identifier}")

    def delete_all_verified_queries(self) -> None:
        """Delete all verified queries."""
        count = len(self.data.get("verified_queries", []))
        self.data["verified_queries"] = []
        self.operations_applied.append(f"Deleted all verified queries ({count} total)")

    def delete_module_custom_instructions(self, module_name: str) -> None:
        """Delete module-specific custom instructions."""
        if "module_custom_instructions" not in self.data:
            raise ValueError("No module custom instructions found")

        module_instructions = self.data["module_custom_instructions"]
        if module_name not in module_instructions:
            raise ValueError(
                f"Module custom instructions for '{module_name}' not found"
            )

        del module_instructions[module_name]
        self.operations_applied.append(
            f"Deleted module custom instructions for: {module_name}"
        )

    def delete_all_module_custom_instructions(self) -> None:
        """Delete all module custom instructions."""
        count = len(self.data.get("module_custom_instructions", {}))
        self.data["module_custom_instructions"] = {}
        self.operations_applied.append(
            f"Deleted all module custom instructions ({count} modules)"
        )

    def apply_operation(self, operation: dict[str, Any]) -> None:
        """Apply a single operation."""
        op_type = operation.get("operation")
        component = operation.get("component")

        if not op_type or not component:
            raise ValueError(
                "Each operation must have 'operation' and 'component' fields"
            )

        # Route to appropriate handler
        if op_type == "create":
            if component == "custom_instructions":
                value = operation.get("value")
                if value is None:
                    raise ValueError(
                        "Custom instructions CREATE requires 'value' field"
                    )
                self.create_custom_instructions(value)
            elif component == "module_custom_instructions":
                module_name = operation.get("module_name")
                value = operation.get("value")
                if not module_name or value is None:
                    raise ValueError(
                        "Module custom instructions CREATE requires 'module_name' and 'value' fields"
                    )
                self.create_module_custom_instructions(module_name, value)
            else:
                data = operation.get("data")
                if not data:
                    raise ValueError("CREATE operation requires 'data' field")

                if component == "table":
                    self.create_table(data)
                elif component == "column":
                    table_name = operation.get("table_name")
                    if not table_name:
                        raise ValueError("Column CREATE requires 'table_name'")
                    self.create_column(table_name, data)
                elif component == "relationship":
                    self.create_relationship(data)
                elif component == "verified_query":
                    self.create_verified_query(data)
                else:
                    raise ValueError(f"CREATE not supported for component: {component}")

        elif op_type == "update":
            if component == "name":
                value = operation.get("value")
                if value is None:
                    raise ValueError("UPDATE requires 'value' field")
                self.update_name(value)
            elif component == "description":
                value = operation.get("value")
                if value is None:
                    raise ValueError("UPDATE requires 'value' field")
                self.update_description(value)
            elif component == "custom_instructions":
                value = operation.get("value")
                mode = operation.get("mode", "replace")
                if value is None:
                    raise ValueError("UPDATE requires 'value' field")
                self.update_custom_instructions(value, mode)
            elif component == "module_custom_instructions":
                module_name = operation.get("module_name")
                value = operation.get("value")
                mode = operation.get("mode", "replace")
                if not module_name or value is None:
                    raise ValueError(
                        "Module custom instructions UPDATE requires 'module_name' and 'value' fields"
                    )
                self.update_module_custom_instructions(module_name, value, mode)
            elif component == "table":
                table_name = operation.get("table_name")
                property = operation.get("property")
                value = operation.get("value")
                mode = operation.get("mode", "replace")
                if not table_name or not property or value is None:
                    raise ValueError(
                        "Table UPDATE requires 'table_name', 'property', and 'value'"
                    )
                self.update_table(table_name, property, value, mode)
            elif component == "column":
                table_name = operation.get("table_name")
                column_name = operation.get("column_name")
                property = operation.get("property")
                value = operation.get("value")
                mode = operation.get("mode", "replace")
                if not table_name or not column_name or not property or value is None:
                    raise ValueError(
                        "Column UPDATE requires 'table_name', 'column_name', 'property', and 'value'"
                    )
                self.update_column(table_name, column_name, property, value, mode)
            elif component == "relationship":
                relationship_name = operation.get("relationship_name")
                property = operation.get("property")
                value = operation.get("value")
                if not relationship_name or not property or value is None:
                    raise ValueError(
                        "Relationship UPDATE requires 'relationship_name', 'property', and 'value'"
                    )
                self.update_relationship(relationship_name, property, value)
            elif component == "verified_query":
                vqr_name = operation.get("vqr_name")
                vqr_id = operation.get("vqr_id")
                property = operation.get("property")
                value = operation.get("value")
                if not property or value is None:
                    raise ValueError("VQR UPDATE requires 'property' and 'value'")
                self.update_verified_query(vqr_name, vqr_id, property, value)
            else:
                raise ValueError(f"UPDATE not supported for component: {component}")

        elif op_type == "delete":
            if component == "table":
                table_name = operation.get("table_name")
                if not table_name:
                    raise ValueError("Table DELETE requires 'table_name'")
                self.delete_table(table_name)
            elif component == "column":
                table_name = operation.get("table_name")
                column_name = operation.get("column_name")
                if not table_name or not column_name:
                    raise ValueError(
                        "Column DELETE requires 'table_name' and 'column_name'"
                    )
                self.delete_column(table_name, column_name)
            elif component == "relationship":
                relationship_name = operation.get("relationship_name")
                if not relationship_name:
                    raise ValueError("Relationship DELETE requires 'relationship_name'")
                self.delete_relationship(relationship_name)
            elif component == "verified_query":
                vqr_name = operation.get("vqr_name")
                vqr_id = operation.get("vqr_id")
                self.delete_verified_query(vqr_name, vqr_id)
            elif component == "verified_queries":
                self.delete_all_verified_queries()
            elif component == "module_custom_instructions":
                module_name = operation.get("module_name")
                if module_name:
                    self.delete_module_custom_instructions(module_name)
                else:
                    # Delete all module custom instructions if no module_name specified
                    self.delete_all_module_custom_instructions()
            else:
                raise ValueError(f"DELETE not supported for component: {component}")

        else:
            raise ValueError(f"Unknown operation: {op_type}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Modify semantic model YAML files through create, update, and delete operations. Always outputs to new file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update model description
  %(prog)s --input-file model.yaml --output-file model_v2.yaml \\
    --operations-json '[{"operation":"update","component":"description","value":"Updated"}]'

  # Delete all VQRs
  %(prog)s --input-file model.yaml --output-file model_no_vqrs.yaml \\
    --operations-json '[{"operation":"delete","component":"verified_queries"}]'

  # Create module custom instructions
  %(prog)s --input-file model.yaml --output-file model_v2.yaml \\
    --operations-json '[{"operation":"create","component":"module_custom_instructions","module_name":"sql_generation","value":"Always use LEFT JOINs"}]'

  # Update module custom instructions (append)
  %(prog)s --input-file model.yaml --output-file model_v2.yaml \\
    --operations-json '[{"operation":"update","component":"module_custom_instructions","module_name":"sql_generation","value":"Use CURRENT_DATE()","mode":"append"}]'

  # Multiple operations
  %(prog)s --input-file model.yaml --output-file model_v2.yaml \\
    --operations-json '[
      {"operation":"update","component":"table","table_name":"orders","property":"description","value":"Updated"},
      {"operation":"create","component":"column","table_name":"orders","data":{"name":"new_col","kind":"dimension","expr":"col"}}
    ]'
        """,
    )

    parser.add_argument(
        "--input-file", required=True, help="Path to input semantic model YAML file"
    )
    parser.add_argument(
        "--output-file", required=True, help="Path to output semantic model YAML file"
    )
    parser.add_argument(
        "--operations-json", required=True, help="JSON array of operations to apply"
    )

    args = parser.parse_args()

    # Parse operations JSON
    try:
        operations = json.loads(args.operations_json)
        if not isinstance(operations, list):
            print("❌ Error: --operations-json must be a JSON array", file=sys.stderr)
            sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing operations JSON: {e}", file=sys.stderr)
        sys.exit(1)

    # Initialize setter
    setter = SemanticModelSetter(args.input_file)

    # Apply operations
    try:
        for i, operation in enumerate(operations):
            try:
                setter.apply_operation(operation)
            except Exception as e:
                print(f"❌ Error in operation {i + 1}: {e}", file=sys.stderr)
                sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

    # Save output
    setter._save_yaml(args.output_file)

    # Print summary
    print(f"✅ Applied {len(operations)} operation(s) successfully")
    for op in setter.operations_applied:
        print(f"  - {op}")
    print(f"\nOutput written to: {args.output_file}")


if __name__ == "__main__":
    main()

# Tool: semantic_view_get.py

**Description**: Retrieves components from semantic view YAML files. Always outputs in YAML format.

**Location**: `scripts/semantic_view_get.py`

## Parameters

- `--file`: Path to semantic view YAML (required)
- `--component`: Component to retrieve (required) - see table below
- `--table-name`: Table name (for table/column operations)
- `--column-name`: Column name (for specific column)
- `--kind`: Filter columns by kind (dimension, time_dimension, measure, fact, metric, filter)
- `--module-name`: Module name for module_custom_instructions (choices: `question_categorization`, `sql_generation`)
- `--vqr-name` / `--vqr-id`: VQR identifier
- `--extract`: Extract field from VQRs (choices: `questions`, `sqls`)

## Components

| Component                  | Required Args                   | Description                                                             |
| -------------------------- | ------------------------------- | ----------------------------------------------------------------------- |
| model                      | -                               | Entire semantic view                                                    |
| name                       | -                               | Model name                                                              |
| description                | -                               | Model description                                                       |
| custom_instructions        | -                               | Custom instructions                                                     |
| module_custom_instructions | -                               | All module-specific instructions (optional `--module-name` for specific module) |
| tables                     | -                               | All tables (lightweight: name, desc, base_table)                        |
| table                      | `--table-name`                  | Specific table (full definition)                                        |
| columns                    | `--table-name`                  | Columns from table (optional `--kind` filter)                           |
| column                     | `--table-name`, `--column-name` | Specific column                                                         |
| primary_key                | `--table-name`                  | Primary key definition                                                  |
| relationships              | -                               | All relationships                                                       |
| verified_queries           | -                               | All VQRs (optional `--extract`)                                         |
| verified_query             | `--vqr-name` or `--vqr-id`      | Specific VQR                                                            |

**Note**: Filters and metrics are accessed via `columns` with `--kind filter` or `--kind metric`

## Syntax Quick Reference

```bash
# Model-level
--component model|name|description|custom_instructions

# Module custom instructions
--component module_custom_instructions
--component module_custom_instructions --module-name sql_generation
--component module_custom_instructions --module-name question_categorization

# Tables
--component tables
--component table --table-name ORDERS
--component primary_key --table-name ORDERS

# Columns (kind: dimension, time_dimension, measure, fact, metric, filter)
--component columns --table-name ORDERS
--component columns --table-name ORDERS --kind dimension
--component column --table-name ORDERS --column-name AMOUNT

# Relationships
--component relationships

# VQRs
--component verified_queries
--component verified_queries --extract questions
--component verified_queries --extract sqls
--component verified_query --vqr-name "Total Sales"
--component verified_query --vqr-id 0
```

**Note**: VQR SQL queries are automatically translated from logical (e.g., `orders`) to fully qualified physical names (e.g., `PROD_DB.SALES.ORDERS`).

## Output Format

**YAML format**: Single items (object), lists (array), scalars (string value)

**Errors**: Non-zero exit, message to stderr: `❌ Error: Table 'X' not found`

## Strategy

- **Overview**: Use `tables` and `relationships` first (lightweight)
- **Detail**: Use `table` or `columns` for specific inspection
- **Audit**: Use `verified_queries --extract questions` to iterate
- **Debug**: Inspect specific columns related to failing queries

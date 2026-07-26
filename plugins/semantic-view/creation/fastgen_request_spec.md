# FastGen Request Specification

This document describes the JSON request schema for the `SYSTEM$CORTEX_ANALYST_FAST_GENERATION` system function, which automatically generates semantic models from SQL queries and table metadata.

## Schema Overview

```json
{
  "json_proto": {
    "name": "string (required)",
    "database": "string (required - target database for semantic view)",
    "schema": "string (required - target schema for semantic view)",
    "tables": [
      {
        "database": "string (required)",
        "schema": "string (required)",
        "table": "string (required)",
        "columnNames": ["string"] (required, non-empty)
      }
    ],
    "sqlSource": {
      "queries": [
        {
          "sqlText": "string (required)",
          "database": "string (optional)",
          "schema": "string (optional)",
          "correspondingQuestion": "string (optional)"
        }
      ]
    },
    "semanticDescription": "string (optional)",
    "metadata": {
      "warehouse": "string (required)"
    }
  }
}
```

## Required Fields

### `json_proto`
- **Type:** object
- **Description:** Wrapper object for all FastGen request parameters
- **Required:** Yes

### `name`
- **Type:** string
- **Description:** The name for the generated semantic model/view
- **Example:** `"sales_analytics"`

### `database`
- **Type:** string
- **Description:** Target database where the semantic view will be created
- **Example:** `"ANALYTICS_DB"`

### `schema`
- **Type:** string
- **Description:** Target schema where the semantic view will be created
- **Example:** `"SEMANTIC_MODELS"`

### `tables`
- **Type:** array of table objects
- **Description:** List of source tables to include in the semantic model
- **Minimum:** At least one table required

#### Table Object Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `database` | string | Yes | Snowflake database name for this table |
| `schema` | string | Yes | Snowflake schema name for this table |
| `table` | string | Yes | Table name |
| `columnNames` | array of strings | Yes | List of columns to include (non-empty, UPPERCASE for unquoted) |

### `metadata.warehouse`
- **Type:** string
- **Description:** Snowflake warehouse for FastGen execution
- **Example:** `"COMPUTE_WH"`
- **Note:** Get from `SELECT CURRENT_WAREHOUSE()` if not specified by user

## Optional Fields

### `sqlSource.queries`
- **Type:** array of query objects
- **Description:** SQL queries to generate Verified Query Results (VQRs)
- **Default:** Empty array (no VQRs generated)

#### Query Object Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `sqlText` | string | Yes | The SQL query text |
| `database` | string | No | Default database context for the query |
| `schema` | string | No | Default schema context for the query |
| `correspondingQuestion` | string | No | Natural language question the query answers |

### `semanticDescription`
- **Type:** string
- **Description:** High-level description of the semantic model's purpose
- **Example:** `"Analytics model for tracking sales performance across regions"`

## Identifier Normalization

**IMPORTANT**: All unquoted identifiers must be UPPERCASE (Snowflake default):

- `analytics` → `ANALYTICS`
- `my_table` → `MY_TABLE`
- `column_name` → `COLUMN_NAME`

To preserve case-sensitive identifiers, use escaped quotes in SQL:

- `"MixedCase"` → preserved as `MixedCase` 

## Examples

### Minimal Configuration (Tables Only)

```json
{
  "json_proto": {
    "name": "simple_model",
    "database": "ANALYTICS",
    "schema": "SEMANTIC",
    "tables": [
      {
        "database": "ANALYTICS",
        "schema": "PUBLIC",
        "table": "ORDERS",
        "columnNames": ["ORDER_ID", "CUSTOMER_ID", "ORDER_DATE", "TOTAL_AMOUNT"]
      }
    ],
    "metadata": {
      "warehouse": "COMPUTE_WH"
    }
  }
}
```

### Configuration with SQL Queries

```json
{
  "json_proto": {
    "name": "sales_analytics",
    "database": "SALES",
    "schema": "SEMANTIC_MODELS",
    "tables": [
      {
        "database": "SALES",
        "schema": "PUBLIC",
        "table": "ORDERS",
        "columnNames": ["ORDER_ID", "CUSTOMER_ID", "ORDER_DATE", "TOTAL_AMOUNT", "STATUS"]
      },
      {
        "database": "SALES",
        "schema": "PUBLIC",
        "table": "CUSTOMERS",
        "columnNames": ["CUSTOMER_ID", "NAME", "REGION", "SIGNUP_DATE"]
      }
    ],
    "sqlSource": {
      "queries": [
        {
          "sqlText": "SELECT c.REGION, SUM(o.TOTAL_AMOUNT) as revenue FROM SALES.PUBLIC.ORDERS o JOIN SALES.PUBLIC.CUSTOMERS c ON o.CUSTOMER_ID = c.CUSTOMER_ID GROUP BY c.REGION",
          "database": "SALES",
          "schema": "PUBLIC",
          "correspondingQuestion": "What is the total revenue by region?"
        }
      ]
    },
    "semanticDescription": "Sales analytics model for revenue and customer analysis",
    "metadata": {
      "warehouse": "COMPUTE_WH"
    }
  }
}
```

### Multi-Table Configuration for Relationship Inference

```json
{
  "json_proto": {
    "name": "employee_hierarchy",
    "database": "HR",
    "schema": "SEMANTIC",
    "tables": [
      {
        "database": "HR",
        "schema": "PUBLIC",
        "table": "EMPLOYEES",
        "columnNames": ["EMPLOYEE_ID", "NAME", "DEPARTMENT_ID", "MANAGER_ID"]
      },
      {
        "database": "HR",
        "schema": "PUBLIC",
        "table": "DEPARTMENTS",
        "columnNames": ["DEPARTMENT_ID", "DEPARTMENT_NAME", "BUDGET"]
      },
      {
        "database": "HR",
        "schema": "PUBLIC",
        "table": "PROJECTS",
        "columnNames": ["PROJECT_ID", "PROJECT_NAME", "LEAD_EMPLOYEE_ID"]
      }
    ],
    "metadata": {
      "warehouse": "COMPUTE_WH"
    }
  }
}
```

## Validation Checklist

Before calling FastGen, verify:

- [ ] Request is wrapped in `json_proto` object
- [ ] `name` is present and non-empty
- [ ] `database` is present (target database for semantic view)
- [ ] `schema` is present (target schema for semantic view)
- [ ] At least one table in `tables` array
- [ ] Each table has `database`, `schema`, `table` fields
- [ ] Each table has non-empty `columnNames` array (camelCase - required by system function)
- [ ] `metadata.warehouse` is present
- [ ] If queries provided, each has non-empty `sqlText`
- [ ] All unquoted identifiers are UPPERCASE

## Output Files

The FastGen script generates:

1. **`<name>_semantic_model.yaml`** - The generated semantic model in YAML format
2. **`<name>_metadata.json`** - Metadata including:
   - `semantic_view_name` - Name of the semantic view
   - `target_database` - Target database for deployment
   - `target_schema` - Target schema for deployment
   - `request_id` - Unique identifier for the FastGen request (query ID)
   - `warnings` - Any warnings from generation
   - `errors` - Any errors encountered
   - `suggestions_applied` - Relationship suggestions that were applied
   - `suggestions_filtered` - Relationship suggestions that were filtered out (many-to-many)
   - `tables_included` - List of tables included in the model

## Related Documentation

- [fastgen_workflow.md](fastgen_workflow.md) - Step-by-step workflow for using FastGen

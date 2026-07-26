# Tool: semantic_view_set.py

**Description**: Modifies semantic view YAML files through create, update, and delete operations. Always outputs to a new file for safety.

**Location**: `scripts/semantic_view_set.py`

## Parameters

- `--input-file`: Path to input semantic view YAML
- `--output-file`: Path to output semantic view YAML
- `--operations-json`: JSON array of operations

## Operation Structure

```json
{
  "operation": "create|update|delete",
  "component": "name|description|custom_instructions|module_custom_instructions|table|column|relationship|verified_query|verified_queries"
  // Additional fields based on operation
}
```

## Operations by Component

| Component                  | CREATE | UPDATE | DELETE |
| -------------------------- | ------ | ------ | ------ |
| name                       | ❌     | ✅     | ❌     |
| description                | ❌     | ✅     | ❌     |
| custom_instructions        | ✅     | ✅     | ❌     |
| module_custom_instructions | ✅     | ✅     | ✅     |
| table                      | ✅     | ✅     | ✅     |
| column                     | ✅     | ✅     | ✅     |
| relationship               | ✅     | ✅     | ✅     |
| verified_query             | ✅     | ✅     | ✅     |
| verified_queries           | ❌     | ❌     | ✅     |

## Quick Reference

### Model-Level

```json
// Update name/description
{"operation":"update","component":"name|description","value":"..."}

// Create/update custom instructions
{"operation":"create|update","component":"custom_instructions","value":"..."}
{"operation":"update","component":"custom_instructions","value":"...","mode":"append"}

// Create/update module custom instructions (module_name: sql_generation or question_categorization)
{"operation":"create","component":"module_custom_instructions","module_name":"sql_generation","value":"Always use LEFT JOINs"}
{"operation":"update","component":"module_custom_instructions","module_name":"sql_generation","value":"Use CURRENT_DATE()"}
{"operation":"update","component":"module_custom_instructions","module_name":"sql_generation","value":"Additional instruction","mode":"append"}

// Delete module custom instructions (specific module or all)
{"operation":"delete","component":"module_custom_instructions","module_name":"sql_generation"}
{"operation":"delete","component":"module_custom_instructions"}
```

### Tables

```json
// Create table
{"operation":"create","component":"table","data":{
  "name":"customers","description":"...","base_table":{...},"dimensions":[]
}}

// Update table property
{"operation":"update","component":"table","table_name":"orders","property":"description","value":"..."}

// Update synonyms (append mode available)
{"operation":"update","component":"table","table_name":"orders","property":"synonyms","value":[...],"mode":"append"}

// Delete table
{"operation":"delete","component":"table","table_name":"..."}
```

### Columns (Dimensions, Measures, Metrics, Filters)

```json
// Create column (kind: dimension|measure|metric|time_dimension|filter)
{"operation":"create","component":"column","table_name":"orders","data":{
  "name":"customer_id","kind":"dimension","description":"...","expr":"...","data_type":"..."
}}

// Update column property
{"operation":"update","component":"column","table_name":"orders","column_name":"amount",
 "property":"description|synonyms","value":"..."}

// Update synonyms (append mode available)
{"operation":"update","component":"column","table_name":"orders","column_name":"amount",
 "property":"synonyms","value":[...],"mode":"append"}

// Delete column
{"operation":"delete","component":"column","table_name":"orders","column_name":"..."}
```

### Relationships

```json
// Create relationship
{"operation":"create","component":"relationship","data":{
  "name":"orders_to_customers","left_table":"orders","right_table":"customers",
  "relationship_columns":[{"left_column":"customer_id","right_column":"id"}],
  "join_type":"inner"
}}

// Update relationship
{"operation":"update","component":"relationship","relationship_name":"...","property":"join_type","value":"left_outer"}

// Delete relationship
{"operation":"delete","component":"relationship","relationship_name":"..."}
```

### Verified Queries

This tool updates YAML only. It does **not** run Snowflake **`validate_verified_queries`** (Analyst compile / EXPLAIN). To check SQL before create/update, load [sva_validate_verified_queries.md](sva_validate_verified_queries.md) and run the inline mode against YAML **without** the `verified_queries` section. To convert semantic ↔ physical SQL, see [sva_expand_truncate_verified_query.md](sva_expand_truncate_verified_query.md).

```json
// Create VQR
{"operation":"create","component":"verified_query","data":{
  "name":"Total Sales","question":"...","sql":"..."
}}

// Update VQR
{"operation":"update","component":"verified_query","vqr_name":"...","property":"sql","value":"..."}

// Delete VQR (by name or ID)
{"operation":"delete","component":"verified_query","vqr_name":"..."}
{"operation":"delete","component":"verified_query","vqr_id":5}

// Delete ALL VQRs (for audit mode)
{"operation":"delete","component":"verified_queries"}
```

## Common Patterns

### Batch Operations

```bash
uv run python semantic_view_set.py \
  --input-file model.yaml \
  --output-file model_v2.yaml \
  --operations-json '[
    {"operation":"update","component":"description","value":"Optimized"},
    {"operation":"update","component":"table","table_name":"orders","property":"description","value":"..."},
    {"operation":"update","component":"column","table_name":"orders","column_name":"amount","property":"synonyms","value":["total"],"mode":"append"}
  ]'
```

**⚠️ Operations execute sequentially** in array order. Order matters!

### Change Column Type (Kind)

**Cannot UPDATE column kind directly**. Must DELETE then CREATE:

```json
[
  {
    "operation": "delete",
    "component": "column",
    "table_name": "orders",
    "column_name": "amount"
  },
  {
    "operation": "create",
    "component": "column",
    "table_name": "orders",
    "data": {
      "name": "amount",
      "kind": "dimension",
      "description": "...",
      "expr": "amount",
      "data_type": "NUMBER"
    }
  }
]
```

**Why?** Each kind is stored in a different YAML section. Must remove from old section, add to new section based on `kind`.

## Field Reference

### CREATE

- `custom_instructions`: Use `value` field
- `module_custom_instructions`: Use `module_name` and `value` fields
- All others: Use `data` field with complete component definition
- Columns: Must include `kind` (dimension, measure, metric, time_dimension, filter)

### UPDATE

- `property`: Property name to update
- `value`: New value
- `mode`: `"replace"` (default) or `"append"`
  - Synonyms: Appends to list
  - Custom instructions: Appends with newline
  - Module custom instructions: Appends with newline (requires `module_name`)

### DELETE

- No extra fields beyond identifiers

## Component Identifiers

| Component                  | Required Fields                                |
| -------------------------- | ---------------------------------------------- |
| name/description           | None                                           |
| custom_instructions        | None                                           |
| module_custom_instructions | `module_name` (for specific module operations) |
| table                      | `table_name`                                   |
| column                     | `table_name`, `column_name`                    |
| relationship               | `relationship_name`                            |
| verified_query             | `vqr_name` or `vqr_id`                         |
| verified_queries           | None                                           |

## Important Constraints

1. **Atomic**: All operations succeed or all fail (no partial updates)
2. **Safe**: Never modifies input file
3. **Sequential**: Operations execute in array order - dependencies must be ordered correctly
4. **Column Type Changes**: Cannot UPDATE `kind` - must DELETE then CREATE
5. **Append Mode**: Use `"mode":"append"` for synonyms/custom_instructions to preserve existing values
6. **Verify Before CREATE**: Check component doesn't exist (use semantic_view_get.py)

## Error Handling

Errors print to stderr, exit non-zero, and **do not write output file**.

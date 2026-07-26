---
name: semantic-view-creation
description: Create new semantic views from scratch using table metadata and optional VQRs. Generates complete semantic models with table-level metrics/filters, proper relationships with relationship_type, and unique keys for joins.
---

# Creation Mode

## When to Load

User wants to CREATE a new semantic view (not optimize an existing one).

## ⚠️ CRITICAL: Create TODOs

**MANDATORY**: Use `system_todo_write` to create TODOs for all workflow phases. All steps are MANDATORY.

## Purpose

Generate a complete, validated semantic view from:
1. SQL context (VQRs, SQL files, Python files with queries)
2. User context and business requirements
3. Table metadata (extracted from Snowflake)

## Workflow

### Phase 1: Context Gathering

#### Step 1.1: Get Semantic View Name

Ask user for semantic view name (valid identifier, lowercase with underscores).

**Example**: `cortex_analyst_usage_analytics`

#### Step 1.2: Get Additional Context

Ask user to provide (all optional):

**SQL Context** - Any of:
- VQRs (Verified Query/Result pairs) in YAML format
- SQL files (.sql) with queries
- Python files (.py) with SQL queries

**Business Context**:
- Purpose, key metrics, important filters, time dimensions

**Note**: Tables auto-extracted from SQL context.

**⚠️ MANDATORY STOPPING POINT**: Wait for user to provide context.

### Phase 2: Analyze SQL Context and Extract Tables

**Step 2.1: Parse SQL Context**

Analyze SQL files/VQRs/Python files to:
- Extract table references (database.schema.table)
- Identify columns, joins, relationships, filters
- Extract metrics and aggregations
- **Extract SQL queries as VQRs with natural language questions**
  - Python files: Infer from variable names, comments
  - SQL files: Infer from comments, query context
  - Existing VQRs: Use as-is

**Step 2.2: Infer Primary Keys**

Analyze SQL to identify candidate key columns from:
- JOIN conditions (`ON a.account_id = b.account_id`)
- GROUP BY clauses
- Columns with ID/KEY in names
- Temporal columns (ds, date, timestamp)

Run cardinality analysis with hint columns:

```bash
cd {WORKING_DIR}/creation && \
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python {SKILL_BASE_DIR}/scripts/infer_primary_keys.py \
  --table <database>.<schema>.<table> \
  --output inferred_keys.yaml \
  --hint-columns "account_id,deployment,ds" \
  --max-composite-cols 4 \
  --sample-rows 10000
```

**Output**: YAML with ranked primary key candidates and confidence scores. See Tool 1 for details.

**Step 2.3: Extract Table Metadata**

```bash
cd {WORKING_DIR}/creation && \
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python {SKILL_BASE_DIR}/scripts/extract_table_metadata.py \
  --table <database>.<schema>.<table> \
  --output table_metadata.yaml
```

**Output**: Table structure, sample values, constraints.

### Phase 3: Generate Semantic Model

## ⚠️ Common YAML Pitfalls

- **Relationship types**: Only `many_to_one` and `one_to_one` are valid (not `one_to_many` or `many_to_many`)
- **Joins require primary keys**: The "one" side table must have a `primary_key` with unique columns
- **Field name**: Use `relationship_columns` (not `join_conditions`)
- **Metrics**: No `data_type` field — only `name`, `synonyms`, `description`, `expr`, `access_modifier`
- **Filters/metrics**: Must be inside a table definition, not at YAML top level
- **Always validate**: Run `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(..., TRUE)` before presenting

---

**Step 3.1: Construct Base YAML**

Reference optimization patterns:
- `../optimization/dimension_optimization.md`
- `../optimization/metric_optimization.md`
- `../optimization/relationship_optimization.md`
- `../optimization/filter_optimization.md`

**Tables Section**:
```yaml
tables:
  - name: logical_table_name
    description: Table description
    base_table:
      database: db
      schema: schema
      table: physical_table
    primary_key:
      columns: [col1, col2]  # From Step 2.2
    dimensions:
      - name: column_name
        synonyms: [...]
        description: ...
        data_type: TEXT/NUMBER/DATE/BOOLEAN
        expr: column_name
        sample_values: [...]
    time_dimensions:
      - name: date_column
        expr: date_column
        data_type: DATE
    facts:
      - name: numeric_column
        description: ...
        data_type: NUMBER
        expr: column_name
        default_aggregation: sum
    filters:  # Table-level only
      - name: filter_name
        synonyms: [...]
        description: ...
        expr: column_name = 'value'
    metrics:  # Table-level only
      - name: metric_name
        description: ...
        expr: COUNT(DISTINCT column_name)
```

**Relationships Section**:
```yaml
relationships:
  - name: relationship_name
    left_table: table1
    right_table: table2
    join_type: inner|left_outer
    relationship_type: many_to_one  # REQUIRED
    relationship_columns:
      - left_column: col1
        right_column: col2
```

**Critical**: 
- `relationship_type` MUST be set
- Right table MUST have `primary_key` for many_to_one
- Use `relationship_columns` (not join_conditions)

**Step 3.2: Add VQRs** (if SQL context provided)

Extract questions from variable names, comments, or query analysis. Use YAML pipe syntax to avoid escaping:

```yaml
verified_queries:
- name: vqr_0
  question: What are the daily active users?
  sql: |
    SELECT
      DATE_TRUNC('day', logged_at)::date AS ds,
      COUNT(DISTINCT user_id) AS active_users
    FROM my_table
    GROUP BY ds
```

**Process**:
1. Create VQRs file with pipe syntax
2. Extract base model: `head -n <line_before_vqrs> model.yaml > base.yaml`
3. Combine: `cat base.yaml vqrs.yaml > model.yaml`

### Phase 4: Validation

#### Step 4.1: Validate

```
reflect_semantic_model(semantic_model_file="/path/to/<semantic_view_name>.yaml")
```

#### Step 4.2: Fix Errors

**Common errors**:
1. Invalid field names → Use `relationship_columns` not `join_conditions`
2. Missing `primary_key` → Add to referenced tables
3. Invalid metrics → Simplify expressions
4. Global filters → Move to table level

Re-validate until successful.

### Phase 5: Present Results

```
✅ Semantic View Created!

Name: <semantic_view_name>
Description: <description>

Tables: X | Relationships: Y | Metrics: Z | Filters: W | VQRs: V

File: /path/to/<semantic_view_name>.yaml

Next steps:
- Run AUDIT MODE for comprehensive testing
- Run DEBUG MODE for troubleshooting
- Use upload/SKILL.md to deploy to Snowflake
```

**⚠️ MANDATORY STOPPING POINT**: Present results and wait for feedback.

### Phase 6: Next Steps

- **AUDIT MODE**: Comprehensive VQR testing and optimization
- **DEBUG MODE**: Troubleshoot SQL generation issues
- **Upload**: Deploy to Snowflake (`../upload/SKILL.md`)

## Tools

### Tool 1: infer_primary_keys.py

See Step 2.2 for usage. Outputs ranked candidates via COUNT DISTINCT analysis.

**Parameters**:
- `--hint-columns`: Comma-separated columns from SQL analysis
- `--max-composite-cols`: Max composite key size (recommend 4)
- `--sample-rows`: Sample size for large tables (always use)

### Tool 2: extract_table_metadata.py

See Step 2.3 for usage. Extracts schema and constraints from Snowflake.

### Tool 3: reflect_semantic_model

Validates semantic model YAML. See Phase 4.

### Tool 4: semantic_view_set.py

Modifies YAML via operations. See `../reference/semantic_view_set.md`.

## Success Criteria

- ✅ Validates with reflect_semantic_model
- ✅ Tables have `primary_key` for relationships
- ✅ Relationships have `relationship_type`
- ✅ Filters/metrics at table level
- ✅ All SQL queries from context added as VQRs

## Stopping Points

- ✋ After Phase 1 (context gathering)
- ✋ After Phase 5 (presenting results)

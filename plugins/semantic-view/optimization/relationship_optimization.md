---
name: Relationship Optimization
description: Add or fix table relationships (joins)
parent_skill: semantic-view-patterns
priority: 3
---

# Relationship Optimization

## When to Load

- Missing JOINs in generated SQL
- Wrong join types or conditions
- Cardinality issues causing row multiplication
- Audit flagged missing relationships

## ⚠️ Prerequisites: Primary Key Required

**At least one table must have a primary key on the join columns.**

The script will:

- Use many_to_one if only one table has PK (that table becomes "right")
- Use one_to_one if both tables have PK
- **Reject** if neither table has PK (many_to_many)
- Auto-swap tables if needed based on where PK exists

### Check Primary Key Status

**Note:** All commands below assume you're in the `{WORKING_DIR}/optimization/` directory with the semantic model file.

```bash
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file <semantic_view_name>_semantic_model.yaml \
  --table TABLE_NAME \
  --component primary_key
```

### If Primary Key is Missing

**Option A: Validate with `infer_primary_keys.py`** (recommended)

```bash
cd {WORKING_DIR}/optimization && \
SNOWFLAKE_CONNECTION_NAME=<conn> uv run python {SKILL_BASE_DIR}/scripts/infer_primary_keys.py \
  --table DATABASE.SCHEMA.TABLE \
  --hint-columns COL1,COL2 \
  --output /tmp/pk.yaml
```

Check output for `uniqueness_percentage >= 95%`. If valid, apply:

```bash
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_set.py \
  --input-file <semantic_view_name>_semantic_model.yaml \
  --output-file <semantic_view_name>_semantic_model.yaml \
  --operations-json '[{"operation":"update","component":"table","table_name":"TABLE_NAME","property":"primary_key","value":{"columns":["COL1","COL2"]}}]'
```

**Option B: User provides primary key** (if known)

**⚠️ NEVER add primary keys without verification via Option A or user confirmation.**

---

## Creating Relationships (After PK Verified)

**Step 1: Validate with `relationship_creation.py`**

```bash
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/relationship_creation.py \
  --semantic-model <semantic_view_name>_semantic_model.yaml \
  --left-table ORDERS \
  --right-table CUSTOMERS \
  --left-columns CUSTOMER_ID \
  --right-columns CUSTOMER_ID \
  --output /tmp/rel.yaml
```

**Exit codes:** 0 = success, 2 = rejected (many_to_many), 1 = error

**Step 2: Apply with `semantic_view_set.py`** (only if step 1 exits 0)

Read `/tmp/rel.yaml` and use its contents as the `data` value:

```bash
cd {WORKING_DIR}/optimization && \
uv run python {SKILL_BASE_DIR}/scripts/semantic_view_set.py \
  --input-file <semantic_view_name>_semantic_model.yaml \
  --output-file <semantic_view_name>_semantic_model.yaml \
  --operations-json '[{"operation":"create","component":"relationship","data":{"name":"...","left_table":"...","right_table":"...","relationship_columns":[...],"relationship_type":"...","join_type":"..."}}]'
```

## Core Principles

### Relationship Type (Cardinality)

- **one_to_one**: Each left row matches exactly one right row
- **many_to_one**: Multiple left rows can match same right row
- ❌ Deprecated: one_to_many, many_to_many

**How to choose**: Analyze data relationship. Most common: many_to_one (e.g., many sales → one customer).

### Join Type

- **inner**: Only rows with matches in both tables
- **left_outer**: All left rows, NULL for non-matches
- ❌ Deprecated: full_outer, cross, right_outer

**How to choose**: Use left_outer unless reference data must exist.

## Relationship Structure

```yaml
relationships:
  - name: { DESCRIPTIVE_NAME }
    left_table: { LEFT_TABLE }
    right_table: { RIGHT_TABLE }
    relationship_columns:
      - left_column: { COLUMN }
        right_column: { COLUMN }
    relationship_type: { one_to_one | many_to_one }
    join_type: { inner | left_outer }
```

**Proto** (lines 362-377): name, left_table, right_table, relationship_columns, relationship_type, join_type

## Multi-Column Joins

For composite keys, add multiple relationship_columns:

```yaml
relationship_columns:
  - left_column: ACCOUNT_ID
    right_column: ACCOUNT_ID
  - left_column: DEPLOYMENT
    right_column: DEPLOYMENT
  - left_column: DS
    right_column: DS
```

## Common Issues

| Symptom              | Likely Cause             | Fix                         |
| -------------------- | ------------------------ | --------------------------- |
| Missing JOIN         | No relationship defined  | Add relationship            |
| Data loss            | inner → left_outer       | Change join type            |
| Duplicate rows       | one_to_one → many_to_one | Fix cardinality             |
| Wrong join condition | Wrong columns            | Update relationship_columns |

## Validation

1. Validate syntax
2. Test with question requiring join
3. Check correct join in SQL
4. Verify no row multiplication

## ⚠️ Validation Often Fails

Relationships frequently fail `reflect_semantic_model` validation. If validation fails, remove the relationship and use custom instructions instead.

See [semantic_view_set.md](../reference/semantic_view_set.md) for complete syntax.

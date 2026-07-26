---
name: semantic-view-filters-and-metrics-suggestions
description: >
  Suggest filters, metrics, and facts for a semantic view by analyzing query history.
  Use this skill whenever the user wants to enrich a semantic view with metrics/measures,
  named filters, or computed facts. This includes requests like 'suggest metrics',
  'suggest filters', 'add metrics to my view', 'what metrics should I add',
  'enrich my semantic view', 'recommend filters', 'suggest facts',
  'what measures should I define', or any mention of auto-generating, recommending,
  or populating metrics and filters.
parent_skill: semantic-view
---

# Filters & Metrics Suggestions

A semantic view starts with raw columns, but users quickly need aggregations ("total revenue"), reusable filters ("only VIP customers"), and derived facts ("is SLA compliant?"). Defining these by hand means guessing what matters. The `filters_and_metrics_suggestions` tool (via `SYSTEM$CORTEX_ANALYST_SVA_TOOL`) solves this by mining actual Snowflake query history to surface the metrics, filters, and facts people already use in practice — so the view reflects real needs, not guesswork.

## When to Load

Load this skill when the user wants to generate, suggest, or recommend metrics, filters, or facts for a semantic view. Common triggers:

- "suggest metrics for my view"
- "what filters should I add?"
- "recommend metrics", "enrich my semantic view"
- "suggest facts", "auto-generate metrics"

## Prerequisites

- A semantic view already created (fully qualified name: `DB.SCHEMA.VIEW_NAME`)
- SKILL_BASE_DIR and WORKING_DIR set (from setup/SKILL.md)
- A warehouse available for the function to use

## Workflow

### Phase 1: Gather Context

Collect from user:

| Field | Required | Notes |
|-------|----------|-------|
| **Semantic view** | Yes | Fully qualified name (`DB.SCHEMA.VIEW`) |
| **Warehouse** | No | Check with `SELECT CURRENT_WAREHOUSE()` if not provided |

**✋ STOP** if the semantic view identity is unclear — ask before proceeding.

### Phase 2: Execute the Function

Run the following SQL via `snowflake_sql_execute`. The CTE + `LATERAL FLATTEN` pattern is required — the raw function returns a large JSON string that gets truncated when displayed directly.

> **IMPORTANT — Always use `PARSE_JSON` + `LATERAL FLATTEN`.** Do NOT run the bare `SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL(...)` — the result will be unreadable. Also do NOT use `CREATE TABLE ... AS SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL(...)` — it fails because the function has side effects.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "filters_and_metrics_suggestions",
        "parameters": {
            "semantic_view": "DB.SCHEMA.VIEW_NAME",
            "warehouse": "WAREHOUSE_NAME"
        }
    }$$)):result) AS result
)
SELECT
    f.index + 1 AS suggestion_num,
    f.value AS suggestion
FROM raw, LATERAL FLATTEN(input => raw.result:suggestions) f
ORDER BY f.index;
```

For a stage-based model file, use `"semantic_model_file": "@DB.SCHEMA.STAGE/model.yaml"` instead of `"semantic_view"`.

> **Note:** If the `LATERAL FLATTEN` returns 0 rows, the function returned no suggestions. This usually means insufficient query history — suggest adding more tables or running some queries first.

> **Note:** This function does NOT support a `limit` parameter. All available suggestions are returned.

### Phase 3: Present Results

The query returns one row per suggestion. Each row's `suggestion` column is a JSON object. Expected structure:

```json
{
    "changes": [
        {
            "operation": "SEMANTIC_MODEL_CHANGE_OPERATION_APPEND",
            "path": "tables/name:ticket_sales/metrics",
            "value": {
                "metric": {
                    "name": "total_revenue",
                    "description": "Calculates total revenue by summing all prices.",
                    "expr": "SUM(price)"
                }
            }
        }
    ],
    "metadata": {
        "frequency": 38,
        "justification": "This metric was used by you 38 times recently",
        "source": "verified queries"
    },
    "version": 2
}
```

**Suggestion types — identify by the key inside `value`:**

| Value key | Type | Path pattern | Fields |
|-----------|------|-------------|--------|
| `metric` | Metric/Measure | `tables/name:<table>/metrics` | `name`, `description`, `expr` |
| `named_filter` | Named Filter | `tables/name:<table>/filters` | `name`, `description`, `expr` |
| `fact` | Computed Fact | `tables/name:<table>/facts` | `name`, `data_type`, `description`, `expr` |
| `primary_key` | Primary Key | `tables.<table>.primary_key` | `columns` (array) |

**Key fields to surface:**
- `changes[].path` — encodes the type and target table (e.g. `tables/name:ticket_sales/metrics`)
- `changes[].value` — contains the suggested metric/filter/fact with `name`, `expr`, `description`
- `metadata.frequency` — how many queries/VQRs use this pattern (higher = more common)
- `metadata.source` — origin of the suggestion (e.g. `"verified queries"`, `"query history"`)

**Present results grouped by type, sorted by frequency descending:**

- Mark recommended suggestions with ⭐ based on these heuristics:
  - Common aggregations everyone needs (COUNT DISTINCT, SUM, AVG)
  - Broadly applicable filters (region, date range, status, category)
  - Derived facts that answer frequent business questions
- For non-starred suggestions, briefly note why they're lower priority

If `warnings` is non-empty, display them to the user.

### Phase 4: Offer Next Steps

**✋ STOP** — ask the user what they'd like to do:

1. **Add suggestions to the semantic view** — use `semantic_view_set.py` (load [semantic_view_set.md](../reference/semantic_view_set.md)) to apply them. Each suggestion's `changes` array contains the exact `operation`/`path`/`value` triples needed for the edit.
2. **Get more suggestions** — try again after adding more tables or running queries
3. **See full details** of specific suggestions

## Error Handling

| Error | Fix |
|-------|-----|
| Semantic view not found | Verify FQN with `SHOW SEMANTIC VIEWS IN <database>.<schema>` |
| Permission denied | Check role: `SELECT CURRENT_ROLE()` |
| No suggestions / "No expressions extracted" | The model may lack sufficient query history — suggest adding more tables or running some queries first |
| Warehouse not specified | Provide `"warehouse"` or set one: `USE WAREHOUSE <name>` |

## Success Criteria

- ✅ Semantic view identified
- ✅ Function executed successfully
- ✅ Suggestions parsed and presented clearly, grouped by type (metrics, filters, facts)
- ✅ Next steps offered to user

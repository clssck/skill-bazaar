# SVA: `validate_verified_queries` (compile / EXPLAIN validation)

Use Snowflake **`SYSTEM$CORTEX_ANALYST_SVA_TOOL`** with tool **`validate_verified_queries`** to check verified-query SQL against a semantic model (expand + compile). This is **not** the same as:

- **Audit → VQR Testing** (`audit/vqr_testing/`) — behavioral check: does Cortex Analyst reproduce the VQR without hints?
- **`validation/SKILL.md`** — `reflect_semantic_model` and exact SQL **result** comparison

Run the SQL below via your Snowflake execution path (e.g. Snowflake CLI, worksheet, or agent `snowflake_sql_execute`).

## Prerequisites

- Role with permission to call `SYSTEM$CORTEX_ANALYST_SVA_TOOL` and run the underlying `EXPLAIN`
- **Warehouse** for compilation (use an active warehouse or pass `warehouse` in parameters)

## How to read results

> **IMPORTANT — Always use `PARSE_JSON` + `LATERAL FLATTEN`** for `validate_verified_queries` when you need one row per query. Do **not** rely on displaying the raw function return value only — it is a large JSON string. Do **not** use `CREATE TABLE ... AS SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL(...)` if your environment rejects side-effecting functions in CTAS.

---

## Mode A — Bulk: all VQRs on a deployed semantic view

Use when the user wants to validate **stored** verified queries on an existing semantic view **by FQN**.

**Only use this mode when the user asked to validate VQRs / verified queries** (or equivalent). Do not run bulk VQR validation automatically after unrelated YAML checks.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "validate_verified_queries",
        "parameters": {
            "semantic_view": "DATABASE.SCHEMA.VIEW_NAME",
            "warehouse": "WAREHOUSE_NAME"
        }
    }$$)):result) AS result
)
SELECT
    f.index + 1 AS query_num,
    f.value:question::STRING AS question,
    f.value:valid::BOOLEAN AS is_valid,
    f.value:error::STRING AS error_detail,
    f.value:sql::STRING AS semantic_sql
FROM raw, LATERAL FLATTEN(input => raw.result:results) f
ORDER BY f.index;
```

**Alternative — model file on a stage:**

```json
"semantic_model_file": "@DATABASE.SCHEMA.STAGE/path/model.yaml"
```

(use instead of `"semantic_view"` in `parameters`).

---

## Mode B — Inline: arbitrary SQL strings against a YAML model

Use when:

- Validating SQL **before** writing it into YAML with `semantic_view_set.py`, or
- Spot-checking one or more strings without a convenient FQN.

**Requirements:**

- Pass the semantic model as a **`semantic_model` string** (full YAML text).
- **Omit the `verified_queries` section** from that YAML (or strip it) so validation targets only the supplied `sqls`.
- Set **`"is_semantic_view": true`** for semantic-view YAML.
- Include **`warehouse`**.

```sql
WITH raw AS (
    SELECT PARSE_JSON(PARSE_JSON(SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
        "tool": "validate_verified_queries",
        "parameters": {
            "semantic_model": "<paste YAML here without verified_queries section>",
            "sqls": [
                "SELECT col1, SUM(metric) FROM LOGICAL_TABLE GROUP BY 1"
            ],
            "warehouse": "WAREHOUSE_NAME",
            "is_semantic_view": true
        }
    }$$)):result) AS result
)
SELECT
    f.index + 1 AS query_num,
    f.value:question::STRING AS question,
    f.value:valid::BOOLEAN AS is_valid,
    f.value:error::STRING AS error_detail,
    f.value:sql::STRING AS semantic_sql
FROM raw, LATERAL FLATTEN(input => raw.result:results) f
ORDER BY f.index;
```

`question` may be null when only raw `sqls` were supplied.

**Getting YAML from this skill:** after optimization setup, use `semantic_view_get.py` on the downloaded `*_semantic_model.yaml`, then remove the `verified_queries:` block (and its list items) before embedding the remainder in JSON. For large models, a small local edit or script is acceptable as long as the payload sent to Snowflake has no `verified_queries` section for this mode.

---

## After validation

- To **persist** new or updated VQRs, use **`semantic_view_set.py`** — see [semantic_view_set.md](semantic_view_set.md).
- To **deploy** to Snowflake, use [upload/SKILL.md](../upload/SKILL.md) / `upload_semantic_view_yaml.py` when the user requests upload.

## Privilege notes

If the role lacks `SELECT` on underlying tables, some paths treat the VQR as valid (fail-open) for `EXPLAIN`; interpret messages accordingly.

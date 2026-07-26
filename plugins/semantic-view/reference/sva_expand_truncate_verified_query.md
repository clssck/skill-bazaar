# SVA: `expand_verified_query` and `truncate_verified_query`

Use **`SYSTEM$CORTEX_ANALYST_SVA_TOOL`** to convert between **logical (semantic) SQL** and **physical SQL** (with `__` table CTEs) for verified queries. Typical flow: transform in Snowflake → copy result → update YAML with **`semantic_view_set.py`** (`verified_query` update/create).

Run via your Snowflake execution path (worksheet, CLI, or agent SQL tool).

## Prerequisites

- Same SVA access as other Analyst tools
- Correct **`semantic_model` YAML shape** for each tool (see below)

## Parse the return value

The function returns a JSON wrapper. The inner payload is usually in a `result` field (often a JSON string). Use `PARSE_JSON` on the outer and inner layers as needed, similar to [import_tableau/SKILL.md](../import_tableau/SKILL.md) and [filters_and_metrics_suggestions/SKILL.md](../filters_and_metrics_suggestions/SKILL.md).

---

## `expand_verified_query` — semantic SQL → physical SQL

**Use when:** you want worksheet-style physical SQL (e.g. to test in Snowflake) from logical VQR SQL.

**YAML rule:** pass **`semantic_model` without the `verified_queries` section** (same as inline validation). Set **`"is_semantic_view": true`**.

```sql
SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
    "tool": "expand_verified_query",
    "parameters": {
        "sqls": ["SELECT SUM(amount) FROM orders"],
        "semantic_model": "<yaml without verified_queries section>",
        "is_semantic_view": true
    }
}$$);
```

Replace `semantic_model` with escaped YAML text or build the JSON in your client. For local files, read the downloaded `*_semantic_model.yaml`, strip `verified_queries`, and embed.

---

## `truncate_verified_query` — physical SQL → semantic SQL

**Use when:** you have physical SQL (e.g. from a worksheet) and need logical SQL to store in a VQR.

**YAML rule:** pass the **full** semantic model YAML (truncate uses the full model to resolve logical tables / CTEs). Set **`"is_semantic_view": true`**.

```sql
SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
    "tool": "truncate_verified_query",
    "parameters": {
        "sqls": ["WITH __ORDERS AS (SELECT * FROM db.schema.orders) SELECT SUM(amount) FROM __ORDERS"],
        "semantic_model": "<full yaml including verified_queries if present>",
        "is_semantic_view": true
    }
}$$);
```

---

## Persist changes

After you obtain the SQL string you want:

1. Update or create the VQR with **`semantic_view_set.py`** — [semantic_view_set.md](semantic_view_set.md).
2. Upload only if the user asks — [upload/SKILL.md](../upload/SKILL.md).

## Related

- Compile-check SQL before saving: [sva_validate_verified_queries.md](sva_validate_verified_queries.md)

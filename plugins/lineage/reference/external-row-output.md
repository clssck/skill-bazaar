# External Lineage Rows in `GET_LINEAGE` Output

> **Applies when:** the account has **Horizon + Select Star Private Preview** enabled. Without it, `GET_LINEAGE` never returns rows representing external systems, and nothing in this file applies.

When Horizon + Select Star is enabled, `SNOWFLAKE.CORE.GET_LINEAGE()` traverses lineage edges that cross from Snowflake objects to external systems (Power BI, Tableau, Sigma, Looker, dbt, Databricks, …). Those edges show up as rows in the same result set as native Snowflake rows. This file describes how to recognize them and how to present them.

## Recognizing an external row

A row represents an external entity when **either** side of the edge has:

| Column | Native row | External row |
|---|---|---|
| `SOURCE_OBJECT_DATABASE` / `TARGET_OBJECT_DATABASE` | populated (e.g. `'ANALYTICS_DB'`) | **`NULL`** |
| `SOURCE_OBJECT_SCHEMA` / `TARGET_OBJECT_SCHEMA` | populated | **`NULL`** |
| `SOURCE_OBJECT_DOMAIN` / `TARGET_OBJECT_DOMAIN` | `'TABLE'`, `'VIEW'`, `'COLUMN'`, etc. | **`'EXTERNAL'`** |
| `SOURCE_NAMESPACE` / `TARGET_NAMESPACE` | `'snowflake://...'` (default) | external namespace, e.g. `'power_bi://CONNECTORS.METADATA."Sales Connector"'` |
| `SOURCE_DATASET_TYPE` / `TARGET_DATASET_TYPE` | `'TABLE'`, `'VIEW'`, `'COLUMN'`, etc. | external entity kind, e.g. `'Power BI Report'`, `'Tableau Dashboard'` |
| `SOURCE_EXTERNAL_ID` / `TARGET_EXTERNAL_ID` | `NULL` | provider-assigned ID, e.g. `'pbi-uuid-abc-def'` |

> **Note on column-level external rows:** v7 emits **only** `'EXTERNAL'` for the object domain (matching `snowflake-apis.md`). A distinct `'EXTERNAL_COLUMN'` domain is **not** currently produced — column-level external lineage rows surface with `*_OBJECT_DOMAIN = 'EXTERNAL'` and a populated `*_COLUMN_NAME`, due to a known GS resolver gap (`ExternalColumnResolver`). Treat `'EXTERNAL'` as the sole external-domain value; distinguish object- vs column-level externals by the presence of `*_COLUMN_NAME`.

**Rule of thumb:** any row whose object-side has `*_OBJECT_DATABASE IS NULL` is an external row. Use `*_NAMESPACE` and `*_DATASET_TYPE` to identify the system and entity kind.

## Presenting external rows to the user

When formatting results, render external entities differently from native ones:

- **Identifier:** use the `*_DATASET_TYPE` and `*_OBJECT_NAME`, qualified by the readable part of the namespace. Do **not** try to construct a `db.schema.table` form — they don't have one.
  - Native: `ANALYTICS_DB.REPORTING.REVENUE_SUMMARY` (Table)
  - External (object-level): `Sales Overview` (Power BI Report) — *Connector: Sales Connector*
  - External (column-level, `*_COLUMN_NAME` populated): append the column name — `Sales Overview.revenue` (Power BI Report) — *Connector: Sales Connector*. Present it the same way as object-level but with `.column_name` appended; do not try to resolve a database path.
- **Group external entities under a separate header** when both native and external rows are present. Don't intermingle — they're meaningfully different to the user.
- **Don't apply Snowflake-style risk/trust scoring** to external rows. Schema-pattern rules from `config/schema-patterns.yaml` don't apply (no schema). Note them as "external dependency, scoring not applicable" or omit risk tier.
- **For affected-users questions:** `ACCESS_HISTORY` does not record activity on external entities. Do not claim to know how many users use a Power BI dashboard — that data lives in the external system, not Snowflake.

### Example: impact analysis with external dependents

```
Impact Analysis: ANALYTICS_DB.REPORTING.REVENUE_SUMMARY

═══════════════════════════════════════════════════════════════
SNOWFLAKE DEPENDENCIES (3 objects)
═══════════════════════════════════════════════════════════════
... existing native-row presentation ...

═══════════════════════════════════════════════════════════════
EXTERNAL DEPENDENCIES (2 entities)
═══════════════════════════════════════════════════════════════
1. Q3 Revenue Dashboard  (Power BI Report)
   Connector: corp-powerbi  |  External ID: pbi-uuid-abc-def
   → Snowflake usage stats not available for external entities.

2. Sales Performance Workbook  (Tableau Dashboard)
   Connector: analytics-tableau  |  External ID: tab-uuid-xyz-789

Summary: 3 Snowflake dependencies + 2 external entities downstream
```

## Direction conventions for external rows

External lineage edges follow the same `DIRECTION` semantics as native lineage:

- **Downstream from a Snowflake object:** target side may be external (a dashboard built from this table).
- **Upstream from a Snowflake object:** source side may be external (rare — most external systems are *downstream* consumers, not upstream producers, in the Horizon + Select Star catalog).

If the user asks to anchor a query directly on the external entity (e.g. *"what feeds this Power BI dashboard?"*) — that's not a supported customer path through `GET_LINEAGE` today. Tell them to anchor on a Snowflake table or view they know is connected; the external entity will surface in the result.

## What this does **not** include

- This file is about external entities appearing as **edge endpoints** in lineage results from Snowflake-native-anchored queries. Anchoring directly on an external entity is not currently supported.
- External entities have no lineage *within* the external system reachable from `GET_LINEAGE`. A Power BI dashboard's upstream within Power BI (e.g. its dataset) is not visible here. `GET_LINEAGE` traces edges that touch Snowflake.
- `EXTERNAL_COLUMN` rows are not produced correctly today — column-level external lineage is not yet usable through `GET_LINEAGE`.

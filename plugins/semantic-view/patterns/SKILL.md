---
name: semantic-view-modeling-patterns
description: "Catalog of 14 advanced Semantic View modeling patterns. Load when the user wants to: compare a metric to the same period last year/month (YoY, MoM, SPLY); build a rolling average / YTD / lag-N comparison metric; model a slowly-changing-dimension lookup with `valid_from`/`valid_to` or attribute an event to the dim row active at event time (as-of, 'address active at order time'); track a snapshot fact that must not sum across time (balance / inventory / headcount); model an accumulating-snapshot funnel across multiple milestone dates ('loan funnel', 'applied → reviewed → decided → funded'); route a metric through a specific FK when one fact has two FKs to the same dim (multi-path metrics); reuse the same physical dim under multiple roles; add a cross-entity derived metric ('% of total', 'net = gross − returns'); split shared dims across multiple fact tables; expose a private (`access_modifier: private_access`) fact used only inside the SV to derive a tier or other dimension; join on a key that doesn't exist as a physical column (computed-fact FK); steer Cortex Analyst with verified queries and `module_custom_instructions`; or diagnose a fan trap, 'multi-path relationship not supported' error, or numbers that look inflated. Also load when an audit or debug finding maps to one of these patterns."
parent_skill: semantic-view
---

# Semantic View Modeling Patterns

## When to Load

Load this skill when the user's request, an audit finding, or a debug step maps to a known modeling pattern below. Typical triggers:

- "year-over-year", "same period last year", "rolling average", "year to date", "lag 30 days"
- "balance / inventory / headcount over time" (snapshot facts that should not sum across time)
- "join my fact to a dimension that changes over time" / "SCD2" / "valid_from / valid_to"
- "join each event to the address active at that time" (single start_date, no end_date)
- "fact has two date FKs (created vs closed; departure vs arrival; ship vs order)"
- "loan / hiring / claims funnel" / "applied → reviewed → decided → funded"
- "total = store + web + catalog" / "% of total" / "net = gross - returns"
- "customer LTV → tier", "age from birth_year", "private fact"
- "computed join key (CONCAT YEAR + QUARTER)" / "no FK column on the source"
- "the SV deployed but my query errors" / "numbers look inflated" / "fan trap"
- "custom instructions", "verified queries", "pre-approved SQL"

If the request matches a row in the catalog below, open the corresponding `snippets/<pattern>.md` first — do not author from memory.

## Catalog

| Pattern | Use when | Trigger phrases | Equivalent in other tools | Key SV constructs | vs sibling pattern |
|---|---|---|---|---|---|
| [time_intelligence](snippets/time_intelligence.md) | Compare current period to same period last year/month (SPLY, YoY %) without window functions | "YoY", "MoM", "SPLY", "same period last year", "vs prior year" | Power BI `SAMEPERIODLASTYEAR()`; LookML period-over-period derived measures; SQL self-join with date-shift | Role-playing alias of fact + computed fact (`DATEADD`) used as the join key | For YTD/QTD running totals use `window_metrics`; for funnels see `accumulating_snapshot` |
| [asof_join](snippets/asof_join.md) | Attribute each fact row to the dimension record active at event time when the dimension has only a `start_date` (no end_date) | "the address active at order time", "as-of", "latest record on or before" | dbt snapshot + manual range; LookML role-playing date dim; SQL `JOIN ... ORDER BY ... LIMIT 1` | `unique_keys` on `(key, start_date)` + `type: asof` on the date column | Use `range_join` if dim has explicit `valid_from` + `valid_to` |
| [range_join](snippets/range_join.md) | Attribute each fact row to the SCD2 dim version active during a closed `[valid_from, valid_to)` period | "SCD2", "valid_from / valid_to", "tier at time of purchase" | dbt snapshot + `BETWEEN` join; Power BI USERELATIONSHIP; SQL `BETWEEN valid_from AND valid_to` | `constraints[].distinct_range` + relationship column with `type: range` + `right_range` | Use `asof_join` when only `start_date` exists |
| [semi_additive_metric](snippets/semi_additive_metric.md) | Snapshot facts (balance, inventory, headcount, open pipeline) that must not sum across time | "current balance", "headcount over time", "inventory snapshot" | LookML `type: number` with manual filter; Power BI `LASTNONBLANK`; Tableau LOD `{ FIXED [Date]: ... }` | `non_additive_dimensions` on the metric + paired `AVG()` metric for trends | Distinct from `window_metrics` — this is about *aggregation correctness*, not period-over-period |
| [window_metrics](snippets/window_metrics.md) | Rolling averages, prior-period LAG, YTD/QTD/MTD running totals | "7-day rolling avg", "year to date", "lag 30 days", "compare to 30 days ago" | SQL window functions; LookML `running_total`; Tableau `WINDOW_AVG` / `RUNNING_SUM` | `OVER (PARTITION BY ... ORDER BY ... RANGE/ROWS BETWEEN ...)` + `LAG(metric, n)` | For SPLY/YoY shifts use `time_intelligence` |
| [multi_path_metrics](snippets/multi_path_metrics.md) | Fact has two FKs to the same dim (departure + arrival, ship-to + bill-to) and you need one metric per path | "weather at departure vs arrival", "ship-to vs bill-to", multi-path error | Power BI USERELATIONSHIP per measure; LookML view extends; SQL multiple aliased JOINs | One relationship per role + `using_relationships: [<name>]` per metric | Use `role_playing_dimensions` when each role needs its own dim names; use `accumulating_snapshot` for funnels |
| [accumulating_snapshot](snippets/accumulating_snapshot.md) | One row per entity, multiple milestone date columns (loan funnel, hiring stages, claims) | "loan funnel", "applied → reviewed → decided → funded", "stage-based pipeline" | Kimball accumulating snapshot; Power BI inactive relationships + USERELATIONSHIP per measure; dbt staged models | One date alias + one relationship per milestone + `using_relationships` per stage metric | Use `multi_path_metrics` for the general pattern; use `role_playing_dimensions` for independent date attributes |
| [role_playing_dimensions](snippets/role_playing_dimensions.md) | Two FKs to the same dim that should produce *independently named* dimensions usable together (cross-tab) | "order date vs ship date in the same report", "fulfillment lag" | LookML `view: x { from: dim_date }`; Power BI duplicate date table; Tableau duplicated source | Same physical table aliased twice in `tables:` with uniquely named dim columns per alias | Use `multi_path_metrics` (`using_relationships`) when dim columns are shared and disambiguation is at metric level |
| [derived_metrics](snippets/derived_metrics.md) | Cross-entity totals and ratios (`total = a + b + c`, `share = a / total`) | "total across channels", "% of total", "net = gross - returns" | LookML `type: number` measure; Power BI DAX `[a] + [b]`; SQL CTE | Top-level `metrics:` block (not nested under any table); right side uses entity-prefixed metrics | Combine with `multi_fact_table` when constituents live on different facts |
| [entity_facts](snippets/entity_facts.md) | Entity-level aggregations (LTV per customer) used to derive a tier dimension; calculated dimensions from physical columns (age) | "value tier from total spend", "age from birth_year", "private fact" | Tableau `{ FIXED [Customer ID]: SUM(...) }`; LookML derived table; Power BI CALCULATE+ALLEXCEPT | `access_modifier: private_access` fact (`SUM(other_table.col)`) + CASE-derived dim referencing it | If you also need YoY on the LTV, layer `time_intelligence` |
| [multi_fact_table](snippets/multi_fact_table.md) | Multiple independent fact tables sharing common dimensions (store + web + returns on product/date) | "three fact tables, one product dim", "net revenue across channels" | Power BI star schema; LookML multiple explores | Each fact joins to shared dims; cross-fact derived metrics in top-level `metrics:` | Pair with `derived_metrics` for the cross-fact totals |
| [fact_as_relationship_key](snippets/fact_as_relationship_key.md) | Need to join on a key that doesn't exist as a physical column (CONCAT/derived) | "join sales to fiscal_quarters by computed key", "no FK column on source" | dbt staging model adds derived column; LookML dimension + join; SQL `JOIN ... ON CONCAT(...)` | Computed fact (scalar expression) referenced as `left_column` inside `relationships:` | Same mechanism powers `time_intelligence`'s shifted joins |
| [ai_metadata](snippets/ai_metadata.md) | Steer Cortex Analyst: SQL generation style, topic scoping, pre-approved verified queries | "always round to 2 decimals", "decline PII questions", "verified query", "pre-approved SQL" | LookML model parameters; dbt metric `meta`; bespoke prompt prefixes | `module_custom_instructions.sql_generation` + `.question_categorization` + `verified_queries:` | n/a |
| [sv_diagnostics](snippets/sv_diagnostics.md) | An SV deployed but queries error or numbers look wrong; map error / symptom → root cause + fix | "multi-path relationship not supported", "must be related to and have an equal or lower level of granularity", "invalid identifier", "numbers look inflated" | n/a — diagnostic catalog | Six failure modes with broken/fixed YAML pairs and a cheat sheet | Use when an SV deployed but queries return errors or wrong numbers |

## Apply Steps

Use these steps once you've identified the matching pattern from the catalog.

### A1. Identify and open the pattern

Open `snippets/<pattern>.md`. Read the *How it works* + *Snippet* + *Gotchas* sections in full before editing. Do not author from memory.

### A2. Locate the target SV

If you do not yet have the SV YAML locally, retrieve it:

```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/semantic_view_get.py \
  --file {WORKING_DIR}/<sv>.yaml \
  --component all
```

### A3. Adapt the snippet

Replace the snippet's placeholder identifiers (table names, column names, join keys) with the real ones from the target SV. Keep the pattern's structural constructs verbatim — these are the delta the pattern adds (`non_additive_dimensions`, `type: asof`, `type: range` + `right_range`, `using_relationships`, `access_modifier: private_access`, computed-fact join keys, `verified_queries`, `module_custom_instructions`, etc.).

### A4. Validate before deploy

Dry-run validate the YAML against Snowflake:

```sql
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  '<TARGET_DB>.<TARGET_SCHEMA>',
  $$ <yaml content> $$,
  TRUE  -- TRUE = validate only, do not create
);
```

### A5. Deploy and verify

After deploy, run a smoke query that exercises the new construct (the *How it works* section names exactly which behavior to verify — e.g. for `time_intelligence`, group by month and confirm `revenue_ly` is non-NULL after the first year).

For audit findings, re-run the failing audit query to confirm the fix.

### A6. Persist

Update the local YAML with `semantic_view_set.py` and stage the change for the user's review before recommending production deployment.

## Hints

- **Multiple patterns can apply to one SV.** A typical "advanced" SV combines `time_intelligence` (SPLY) + `derived_metrics` (cross-channel totals) + `multi_path_metrics` (`using_relationships`) + `ai_metadata` (verified queries). Apply them one at a time.
- **All gotchas in the per-pattern `.md` files are binding constraints**, not theoretical caveats.
- **Diagnostic-first** — when in doubt, open `snippets/sv_diagnostics.md` before opening any modeling pattern. Many "I need a new pattern" requests are actually a structural failure (#5b wrong cardinality is the usual culprit).

## Related

- [../optimization/SKILL.md](../optimization/SKILL.md) — for routine metadata enhancements (descriptions, synonyms, named filters) that are not modeling-pattern fixes.
- [../validation/SKILL.md](../validation/SKILL.md) — to validate the YAML before applying.
- [../upload/SKILL.md](../upload/SKILL.md) — to deploy after pattern application.

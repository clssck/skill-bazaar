---
name: import_powerbi
description: "Import Power BI files (.pbit/.pbix) into Snowflake Semantic Views. Triggers: powerbi import, power bi import, convert powerbi, .pbit, .pbix, migrate dashboard, dax, m query. Always use this skill when the user mentions Power BI files even if they don't explicitly say 'import'."
---

# Power BI Import Skill

Import Power BI templates (.pbit) and desktop files (.pbix) into Snowflake Semantic Views.

## Reference

**Before your first export**, read [reference/pbi_tool_reference.md](../reference/pbi_tool_reference.md) to understand the full parameter set, filter ordering, and warning types.

## Prerequisites

- Snowflake connection configured
- Power BI file uploaded to a Snowflake stage (`@DB.SCHEMA.STAGE/file.pbit` or `…/file.pbix`)
- Both file types are accepted; the parser auto-detects by ZIP contents. `.pbix` is slower (XPress9 decompression) — allow longer timeouts.

## Workflow

### Step 1: Verify File Access

```sql
LIST @DB.SCHEMA.STAGE PATTERN='.*\\.pbi[tx]';
```

If not found: check path format (`@DATABASE.SCHEMA.STAGE/filename`), verify access (`SHOW STAGES IN SCHEMA`).

### Step 2: Analyze the File

```sql
SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
    "tool": "pbi_analyze",
    "parameters": {
        "file_path": "@DB.SCHEMA.STAGE/file.pbit",
        "large_threshold": 100
    }
}$$);
```

The response is a JSON wrapper — parse the `result` string to get the actual data. Key fields: `file_type` (`pbit` or `pbix`), `total_tables`, `total_physical_columns`, `total_calculated_columns`, `total_measures`, `total_relationships`, `is_large_file`, `tables` (each with `name`, `database`, `db_schema`, `snowflake_table_name`, `physical_columns`, `calculated_columns`, `measure_count`), `relationships`, `measures`, `m_query_warnings`, `validation` (only when `validate_in_snowflake=true`), `warnings`. See reference for the full schema.

**Optional Snowflake validation** — pass `"validate_in_snowflake": true` to confirm tables exist before exporting. Off by default to keep analyze cheap.

**Present findings to the user:**

1. **Summary table**: file type, total tables, physical + calculated columns, total measures, total relationships, `is_large_file`.
2. **Table list**: show each table's `name`, resolved Snowflake `database.db_schema.snowflake_table_name`, count of `physical_columns` / `calculated_columns`, and `measure_count` — helps users decide which to include via `include_tables`.
3. **Measure list** (if non-empty): show measure `name` values for `include_measures`.
4. **Warning summary** — group by category:
   - *M-query unresolved tables* (`m_query_warnings`) — parameterized-null source or non-Snowflake source; excluded from export.
   - *Validation warnings* (only with `validate_in_snowflake=true`) — tables that won't pass `validate_tables`.
5. **Filtering options** (if `is_large_file` is true or user wants to narrow scope):
   - *Filter by tables*: show table names from `tables[*].name`.
   - *Filter by columns*: show `physical_columns` and `calculated_columns` — both are filterable (unlike Tableau).
   - *Filter by measures*: show measure names.

**Wait for user approval before proceeding.**

### Step 3: Export Semantic Model

```bash
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python semantic-view/scripts/pbi_export_yaml.py \
    "@DB.SCHEMA.STAGE/file.pbit" \
    my_model \
    ./my_model.yaml
```

Required arguments: `file_path`, `semantic_model_name` (alphanumeric / `_` / `-` only), `output_file`.

Common options (see reference for full parameter list):
- `--target-database` / `--target-schema` — remap where data lives (e.g., PROD → DEV)
- `--include-tables "Sales" "Customer"` — keep only these tables (case-sensitive exact names from analyze)
- `--include-columns "ORDER_ID" "AMOUNT"` — keep only these columns (physical AND calculated)
- `--include-measures "Total Revenue" "Margin"` — keep only these DAX measures
- `--no-calculations` — drop all calculated columns (`include_calculations=false`)
- `--no-measures` — drop ALL DAX measures (`include_measures_all=false`)
- `--skip-table-validation` — skip the Snowflake `validate_tables` call (use with `--target-database`/`--target-schema` when source tables don't exist locally)
- `--generate-descriptions` — LLM-enrich metric descriptions (failures are non-fatal)
- `--model-name` — LLM model for descriptions (default `ANTHROPIC_CLAUDE_SONNET_4`)

⚠️ **`--no-measures` vs `--include-measures` are different controls.** `--include-measures` filters which measures survive; `--no-measures` is a kill-switch that drops every measure.

The script prints a summary (tables, columns, relationships, metrics, unsupported-measure count, warnings) and saves only:
- `<output_file>` — the YAML content

(Power BI v1 does NOT auto-create custom views for un-transpilable DAX — unlike the Tableau import, no `.custom_views.sql` sidecar is produced.)

**After the script completes:**

1. Don't display the full YAML — show only the printed summary.

2. **Unsupported measures** (if `unsupported_measure_count > 0`): explain that some DAX measures couldn't be transpiled and were dropped. Recreate as SQL metrics in the YAML if needed.

3. **Warnings/errors** — categorize and present:
   - *M-query unresolved tables* — tables dropped at parse time; not in YAML.
   - *Validation warnings* — tables/columns rejected by `validate_tables`; empty when `--skip-table-validation` is used.
   - *Builder warnings* — anything else flagged during proto build.
   - *Filter banner* — informational summary of filters applied.

### Step 4: Verify Table References

Parse the saved YAML for `base_table` references, then verify each exists:

```sql
SHOW TABLES LIKE '{table_name}' IN SCHEMA {database}.{schema};
```

**If tables are missing** (expected when importing from a different environment): re-export with `--target-database` / `--target-schema` (and consider `--skip-table-validation` to bypass the pre-build validation while remapping). Help discover where data lives:

```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
```

After the YAML is saved and table references are verified, the import is complete.

### Step 5: Deploy (optional)

If the user wants to deploy the semantic view to Snowflake, load **[upload/SKILL.md](../upload/SKILL.md)** and follow its process.

Only deploy when the user explicitly requests it.

## Power BI Specifics

A few things differ from the Tableau flow:

- **No published-datasource concept.** No `additional_files` or `published_datasource_stub_name` — Power BI files are self-contained.
- **Both `.pbit` and `.pbix` accepted.** `.pbix` requires VertiPaq decompression; expect longer runtimes.
- **Snowflake validation on analyze is opt-in** (`validate_in_snowflake: true`). Off by default.
- **Empty filter result is a hard error.** If `--include-tables` matches no real table, the tool returns `BAD_REQUEST: "All tables filtered out"` rather than producing an empty YAML.
- **Un-transpilable DAX is silently dropped** (counted in `unsupported_measure_count`); no view-creation analog in v1.
- **Filtering happens before validation.** `validate_tables` only sees what survives the filter.

## Stopping Points

- After Step 2: Present analysis, wait for user approval
- After Step 3: Decide whether to recreate any unsupported measures
- After Step 4: If table references need remapping

## Error Handling

- **File not found** → Check stage path format and permissions (`LIST @STAGE`)
- **Unsupported file type** → Only `.pbit` and `.pbix` are accepted
- **`large_threshold must be positive`** → Use any integer ≥ 1
- **Local/relative path rejected** → `Only Snowflake stage paths are supported`. Use `@DB.SCHEMA.STAGE/...`
- **`semantic_model_name is invalid`** → Must match `^[A-Za-z0-9_-]+$` (no spaces, dots, slashes)
- **All tables filtered out** → `--include-tables` names didn't match. Names are case-sensitive — re-check against analyze output
- **Validation warnings dropping tables** → Tables don't exist at the M-resolved location. Re-export with `--target-database`/`--target-schema`, or pass `--skip-table-validation`
- **Parameter not taking effect** → `--no-measures` (kill-switch) is NOT the same as `--include-measures` (filter list)

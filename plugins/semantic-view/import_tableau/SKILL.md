---
name: import_tableau
description: "Import Tableau workbooks (.twb/.twbx) and datasources (.tds/.tdsx) into Snowflake Semantic Views. Triggers: tableau import, convert tableau, .twb, .twbx, .tds, .tdsx, migrate workbook, published datasource. Always use this skill when the user mentions Tableau files even if they don't explicitly say 'import'."
---

# Tableau Import Skill

Import Tableau workbooks (.twb, .twbx) and datasources (.tds, .tdsx) into Snowflake Semantic Views.

## Reference

**Before your first export**, read [reference/tableau_tool_reference.md](../reference/tableau_tool_reference.md) to understand the full parameter set and warning types.

## Prerequisites

- Snowflake connection configured
- Tableau file uploaded to a Snowflake stage (`@DB.SCHEMA.STAGE/file.twbx`)
- If the workbook uses published datasources, the underlying `.tds`/`.tdsx` file must also be on stage

## Workflow

### Step 1: Verify File Access

```sql
LIST @DB.SCHEMA.STAGE PATTERN='.*\\.tw.*';
```

If not found: check path format (`@DATABASE.SCHEMA.STAGE/filename`), verify access (`SHOW STAGES IN SCHEMA`).

### Step 2: Analyze the File

```sql
SELECT SYSTEM$CORTEX_ANALYST_SVA_TOOL($${
    "tool": "tableau_analyze",
    "parameters": {
        "file_path": "@DB.SCHEMA.STAGE/workbook.twbx",
        "large_threshold": 100
    }
}$$);
```

The response is a JSON wrapper — parse the `result` string to get the actual data. Key fields: `file_type`, `datasources`, `worksheets` (objects with `name`, `datasource`, `column_count`, `has_filters`), `column_summary`, `total_columns`, `total_calculations`, `is_large_file`, `has_custom_sql`, `warnings`. See reference for the full schema.

**Present findings to the user:**

1. **Summary table**: file type, total columns (physical + calculated), datasource count, custom SQL present.
2. **Custom SQL notice** (if `has_custom_sql` is true): explain the two handling options in Step 3 (`use_custom_sql_in_definition` true vs false).
3. **Worksheet list**: show each worksheet's `name` and `column_count` — helps users decide which to include via `include_worksheets`.
4. **Warning summary** — group by category:
   - *Unsupported helper columns* — will be excluded from export.
   - *Unable to resolve metadata* — may need manual review after export.
   - *Multi-table fact expressions* — cannot be auto-converted; recreate manually.
   - *Many-to-many relationships* — not supported in semantic views.
5. **Filtering options** (if `is_large_file` is true or user wants to narrow scope):
   - *Filter by worksheets*: show the worksheet names.
   - *Filter by columns*: show `physical_columns` from `column_summary.by_datasource`. Only physical columns can be used with `include_columns` — calculated columns have opaque Tableau IDs.
   - *Filter by datasource*: if multiple datasources exist, let them choose.

**Wait for user approval before proceeding.**

#### Published Datasource Handling

If the export fails with `MultiplePublishedDatasourcesError` or a `BAD_REQUEST` message mentioning published datasource stubs, the workbook depends on a published datasource whose column metadata can't be resolved from the `.twb`/`.twbx` alone.

Resolution:
1. Ask the user to download the published datasource as a `.tds` or `.tdsx` file from Tableau Server/Cloud.
2. Upload it to the same Snowflake stage.
3. Re-run the export with `--additional-files` and (if needed) `--published-datasource-stub-name`:

```bash
# Run from the skills root directory (parent of semantic-view/)
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python semantic-view/scripts/tableau_export_yaml.py \
    "@DB.SCHEMA.STAGE/workbook.twbx" \
    my_model \
    ./my_model.yaml \
    --additional-files "@DB.SCHEMA.STAGE/published_source.tdsx" \
    --published-datasource-stub-name "Sales Data (Published)"
```

`--additional-files` accepts a list of stage paths but only the first file is used currently. `--published-datasource-stub-name` is only needed when the workbook has multiple published datasource stubs and the tool can't auto-detect which one to merge.

### Step 3: Export Semantic Model

```bash
# Run from the skills root directory (parent of semantic-view/)
SNOWFLAKE_CONNECTION_NAME=<connection> uv run python semantic-view/scripts/tableau_export_yaml.py \
    "@DB.SCHEMA.STAGE/workbook.twbx" \
    my_model \
    ./my_model.yaml
```

Required arguments: `file_path`, `semantic_model_name`, `output_file`.

Common options (see reference for full parameter list):
- `--target-database` / `--target-schema` — remap where data lives (e.g., PROD → DEV)
- `--datasource-name` — export only one datasource
- `--include-worksheets "Sheet1" "Sheet2"` — only columns used in these worksheets
- `--include-columns "col1" "col2"` — only these specific columns (physical columns only)
- `--no-calculations` — exclude Tableau calculated fields
- `--use-custom-sql-in-definition` — embed custom SQL directly in YAML instead of placeholder views
- `--extract-usage-context` — extract worksheet/dashboard context (dimensions, measures, filters, tooltips)

The script prints a summary (tables, columns, relationships, warnings) and saves:
- `<output_file>` — the YAML content
- `<output_file>.custom_views.sql` — custom view DDL (if applicable)
- `<output_file>.usage_context.txt` — usage context (if `--extract-usage-context`)

**After the script completes:**

1. Don't display the full YAML — show only the printed summary.

2. **Custom views** (if the script reports custom views required): present the DDL file and ask if the user wants to execute them now. If yes, run each statement from the `.custom_views.sql` file via SQL.

3. **Warnings/errors** — categorize and present:
   - *Unresolved columns* ("Referenced column could not be resolved") — excluded; may need manual recreation.
   - *Unsupported calculations* (LOD, table calculations, unsupported functions) — skipped; recreate in SQL if needed.
   - *Multi-table aggregations / fact expressions* — complex cross-table calculations excluded.
   - *Filter issues* (unresolvable filter columns, unsupported filter types) — excluded; add manually if needed.

### Step 4: Verify Table References

Parse the saved YAML to extract table references, then verify each exists:

```sql
SHOW TABLES LIKE '{table_name}' IN SCHEMA {database}.{schema};
```

**If tables are missing** (expected when importing from a different environment): offer to re-export with `target_database` / `target_schema`. Help discover where data lives:

```sql
SHOW DATABASES;
SHOW SCHEMAS IN DATABASE <database>;
SHOW TABLES IN SCHEMA <database>.<schema>;
```

After the YAML is saved and table references are verified, the import is complete.

### Step 5: Deploy (optional)

If the user wants to deploy the semantic view to Snowflake, load **[upload/SKILL.md](../upload/SKILL.md)** and follow its process.

Only deploy when the user explicitly requests it.

## Stopping Points

- After Step 2: Present analysis, wait for user approval
- After Step 3: If custom views needed, ask before creating them
- After Step 4: If table references need remapping

## Error Handling

- **File not found** → Check stage path format and permissions (`LIST @STAGE`)
- **Empty YAML (0 columns)** → Filters too restrictive; verify names are case-sensitive exact matches
- **Custom SQL views needed** → Run `custom_view_ddl` statements, or re-export with `use_custom_sql_in_definition: true`
- **Missing relationships** → Include PK/FK columns in filters
- **Table not found** → Re-export with `target_database`/`target_schema` remapping
- **Published datasource error** → User needs to provide the `.tds`/`.tdsx` file; see "Published Datasource Handling" above
- **Parameter not taking effect** → Check plural forms: `include_worksheets` (not `include_worksheet`), `include_columns` (not `include_column`)

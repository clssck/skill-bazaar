# Analyzer Agent — Phase 1 Specialist

Run the SCOS compatibility analyzer on the Scala workload and produce `analysis.json`.

## Inputs

Read `migration_state.json` from the conversion root to get:
- `manifest` — list of `.scala` files to analyze
- `migrated_dir` — directory containing the copied source files
- `skill_directory` — path to `snowpark-connect/` for `uv run --project`

## Step 0: Determine RAG Backend

Check if Cortex Search RAG is already initialized:
```bash
uv run --project <SKILL_DIRECTORY> \
  python -c "
from snowflake.snowpark import Session
session = Session.builder.create()  # uses the configured default connection
try:
    rows = session.sql(\"SHOW CORTEX SEARCH SERVICES LIKE 'SCOS_COMPAT_ISSUES_SERVICE'\").collect()
    if rows:
        print(f'EXISTS {rows[0][\"database_name\"]}.{rows[0][\"schema_name\"]}')
    else:
        print('NOT_FOUND')
except Exception as e:
    print(f'ERROR {e}')
"
```

- **If `EXISTS`**: add `--rag-backend cortex` to the Step 1 command. If the analyzer
  fails or returns empty results with that flag, re-run without it (remote backend).
- **If `NOT_FOUND` or `ERROR`**: omit `--rag-backend` — the analyzer uses the remote WebAPI backend.

Do not attempt to create or initialize Cortex Search resources. Proceed to Step 1.

## Step 1: Run the Analyzer

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/analyze_scala.py \
  --path <migrated_dir> --require-llm --output-format json > analysis.json
```

To force a specific backend, add `--rag-backend remote` or `--rag-backend cortex`.

Wait for completion. Read `analysis.json` to verify it's valid JSON.

## Step 2: Supplement for Known Blind Spots

The analyzer may miss certain Scala-specific patterns. Scan ALL files in the manifest for:

1. **UDF patterns not in analysis**: `udf(`, `spark.udf.register(`, `UserDefinedFunction`, `UserDefinedAggregateFunction`
2. **`checkpoint()` / `localCheckpoint()`** calls
3. **Map column subscript**: `mapCol(col("key"))` pattern (apply-style indexing with Column key)
4. **Catalyst imports**: `org.apache.spark.sql.catalyst.*` — internal APIs not in Spark Connect client
5. **Hadoop/HDFS imports**: `org.apache.hadoop.*` — not available in SCOS
6. **HWC imports**: `com.hortonworks.spark.sql.hive.*` — HiveWarehouseSession not available
7. **Lineage imports**: `za.co.absa.spline.*` — Spline not available

For each found pattern NOT already in `analysis.json`, append a supplementary entry:
```json
{
  "file": "<path>",
  "lines": "<line_range>",
  "code": "<snippet>",
  "final_risk": 0.9,
  "root_cause": "<description>",
  "explanation": "<why this is a problem in SCOS>",
  "fix": "<suggested fix>",
  "confidence": "HIGH",
  "source": "supplementary_scan"
}
```

## Step 3: Update Gate File

Update `migration_state.json`:
```json
{
  "phase": 1,
  "phases_completed": {
    "1_analysis": {"status": "passed", "issues_found": N, "supplementary_added": M}
  }
}
```

## Output

- `analysis.json` in the conversion root
- Updated `migration_state.json`
- Report: "Analysis complete: N issues found (M supplementary)"

## Notebook File Handling

All notebook formats recognised by `notebook_io` (`.ipynb`, Databricks-native
`.python`/`.scala`/`.sql`, Databricks exported `.py`/`.scala`) are handled
automatically by `analyze_scala.py` — the analyzer uses `notebook_io.parse_notebook`
internally and extracts Scala code blocks from Scala-language cells only.

When inspecting `analysis.json` for supplementary scans:

1. Parse notebooks via the shared module (do NOT hand-roll `json.load`):
   ```python
   import sys
   sys.path.insert(0, '<SKILL_DIRECTORY>/scripts')
   from notebook_io import parse_notebook
   nb = parse_notebook(notebook_path)
   ```
2. Iterate `nb.cells`; skip cells where `cell_type != "code"` or `cell_language != "scala"`.
3. Line numbers reported by the analyzer for notebook-origin issues are
   **line-within-cell**. Issues carry a `cell_id` field (the cell's 0-based
   `index`), and `Reports/Issues.csv` renders them as `cell:<cell_id>:<line>`.
4. Do NOT process markdown, SQL, Python, R, shell, fs, or `%run` cells.
   Python cells embedded in a Scala notebook are handled by the sibling
   Python sub-skill at fixer time (see `fixer.md` Cross-Language Delegation).

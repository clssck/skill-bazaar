# Analyzer Agent — Phase 1 Specialist

> **Execution model:** Phase 1 is run **inline by the coordinator** on
> single-file / small workloads (`coordinator_mode == false`) — it reads this
> file and follows the steps directly rather than spawning a `task()` sub-agent,
> since the work is one deterministic script plus a bounded supplementary scan.
> On multi-file workloads (`coordinator_mode == true`) it **is** spawned as a
> `task()` sub-agent so its many source reads and the growing `analysis.json`
> stay out of the coordinator's context window. The procedure below is identical
> either way; "agent" names the role, whoever performs it.

Run the SCOS compatibility analyzer on the workload and produce `analysis.json`.

## Inputs

Read `migration_state.json` from the conversion root to get:
- `manifest` — list of `.py` files to analyze
- `migrated_dir` — directory containing the copied source files
- `skill_directory` — path to `snowpark-connect/` for `uv run --project`

## Step 0: Determine RAG Backend

Check if Cortex Search RAG is already initialized:
```bash
uv run --project <SKILL_DIRECTORY> \
  python -c "
from snowflake.snowpark import Session
session = Session.builder.create()  # uses the configured default connection
rows = session.sql('SHOW CORTEX SEARCH SERVICES').collect()
found = [r for r in rows if r['name'] == 'SCOS_COMPAT_ISSUES_SERVICE']
if found:
    print(f'EXISTS {found[0][\"database_name\"]}.{found[0][\"schema_name\"]}')
else:
    print('NOT_FOUND')
"
```

- **Preferred (offline, deterministic): `--rag-backend trigger`.** This uses the
  curated trigger knowledge base (`scripts/data/kb_rules.json`) — no network, no
  embeddings, no throttling. A rule only fires when its literal anchor (an API,
  method, or SQL construct) actually appears in the customer code, and risk comes
  from curated severity (P0/P1/P2) rather than cosine similarity. Use this by
  default for large workloads and parallel runs.
- **If `EXISTS`** (and you specifically want fuzzy semantic recall): add
  `--rag-backend cortex`. If the analyzer fails or returns empty results with that
  flag, re-run without it (remote backend).
- **If `NOT_FOUND`**: omit `--rag-backend` — the analyzer uses the remote WebAPI backend.

Do not attempt to create or initialize Cortex Search resources. Proceed to Step 1.

## Step 1: Run the Analyzer

Pass `--recipe-edits <CONVERSION>/migration_state.json` so the Phase 0.5
`recipe_edits` block is injected as per-block grounding into every Cortex
prompt.  When recipes have already fired on a line, the LLM is instructed
to either skip it (`kind=recipe_validated`) or propose a workload-specific
rewrite on top of an `_annotate` recipe (`kind=recipe_incomplete`).  Issues
in `analysis.json` carry the resulting `kind`, `recipe_id`, and
`suggested_fixer_action` fields when applicable.

`--recipe-edits` accepts either the conversion's `migration_state.json`
(the `recipe_edits` key is extracted automatically) or a standalone JSON
of the shape `{"<rel/path.py>": [ {recipe_id, src_line, ...}, ... ]}` when
the upstream pipeline emits recipe edits separately.

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/analyze_pyspark.py \
  --path <migrated_dir> \
  --require-llm \
  --recipe-edits <CONVERSION>/migration_state.json \
  --output <CONVERSION>/analysis.json
```

The analyzer writes `analysis.json` itself to the `--output` path; stdout
only carries a `Analysis complete: N issue(s) written to ...` confirmation.
Do NOT redirect stdout to a file and do NOT reconstruct `analysis.json` from
console output — the file on disk is the source of truth.

To force a specific backend, add `--rag-backend trigger` (offline, recommended),
`--rag-backend remote`, or `--rag-backend cortex`.

Wait for completion. Read `<CONVERSION>/analysis.json` to verify it's valid JSON.

## Step 2: Supplement for Known Blind Spots

The analyzer may miss certain patterns. Scan ALL files in the manifest for:

1. **UDF patterns not in analysis**: `@udf`, `@pandas_udf`, `applyInPandas`, `mapInPandas`, bare `udf()` calls
2. **`checkpoint()` / `localCheckpoint()`** calls
3. **Map column subscript**: `map_col[col("key")]` pattern (bracket indexing with Column key)

**Recipe-aware filtering is now done by the analyzer script itself**:
because Step 1 passes `--recipe-edits`, every Cortex call already saw the
relevant `recipe_edits` entries and the resulting issues in `analysis.json`
are tiered by `kind` (`recipe_validated` | `recipe_incomplete` |
`recipe_adjacent` | `llm_only`).  Treat the script's output as the source of
truth.  As a belt-and-suspenders check, if you DO find a supplementary
issue, consult `migration_state.json:recipe_edits` and the inline `# SCOS:`,
`# SCOS-WARN:`, `# SCOS-TODO:` markers in the source.  If a line is already
recorded under a `_rewrite` recipe id (e.g.
`dataframe_checkpoint_to_cache_rewrite`,
`map_column_subscript_colkey_to_element_at_rewrite`,
`sparkcontext_property_fallback_rewrite`,
`tempview_multiuse_cache_rewrite`,
`udtf_enable_compatibility_mode_rewrite`),
**do NOT emit a supplementary issue for that line** — the fix is already
applied.  For `_annotate` / `_comment` recipes, emit a supplementary entry
only if you can provide strictly more information than the recipe's comment
text and the analyzer did not already emit it with
`kind="recipe_incomplete"`.

For each found pattern NOT already in `analysis.json` AND not handled by
a Phase 0.5 recipe, append a supplementary entry:
```json
{
  "file": "<path>",
  "lines": "<line_range>",
  "code": "<snippet>",
  "final_risk": 0.8,
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

## Notebook File Handling

All notebook formats recognised by `notebook_io` (`.ipynb`, Databricks-native
`.python`/`.scala`/`.sql`, Databricks exported `.py`/`.scala`) are handled
automatically by `analyze_pyspark.py` — the analyzer uses `notebook_io.parse_notebook`
internally and extracts Python code blocks from Python-language cells only.

When inspecting `analysis.json` for supplementary scans:

1. Parse notebooks via the shared module (do NOT hand-roll `json.load`):
   ```python
   import sys
   sys.path.insert(0, '<SKILL_DIRECTORY>/scripts')
   from notebook_io import parse_notebook
   nb = parse_notebook(notebook_path)
   ```
2. Iterate `nb.cells`; skip cells where `cell_type != "code"` or `cell_language != "python"`.
3. Line numbers reported by the analyzer for notebook-origin issues are
   **line-within-cell**. Issues carry a `cell_id` field (the cell's 0-based
   `index`), and `Reports/Issues.csv` renders them as `cell:<cell_id>:<line>`.
4. Do NOT process markdown, SQL, R, shell, fs, or `%run` cells. Scala cells
   embedded in a Python notebook are handled by the sibling Scala sub-skill
   at fixer time (see `fixer.md` Cross-Language Delegation).

## Output

- `analysis.json` in the conversion root
- Updated `migration_state.json`
- Report: "Analysis complete: N issues found (M supplementary)"

---
name: migrate-pyspark-to-snowpark-connect
description: |
  Migrate PySpark and Databricks workloads to Snowflake SCOS (Snowpark Connect for Spark).
  Use when: converting Spark code to run on Snowflake, analyzing PySpark compatibility,
  updating imports to Spark Connect equivalents, or migrating from Databricks.
  Generates SCOS-compatible reports (Issues.csv, InputFilesInventory.csv, ArtifactDependencyInventory.csv)
  for the dvp-scos-dashboard-generator using official SCOS EWI codes (SPRKCNTPY*).
  Triggers: migrate pyspark, convert spark, scos migration,
  spark connect, pyspark compatibility, snowpark connect.
parent_skill: snowpark-connect
allowed-tools: Read, Write, Bash, Task
---

# Migrate PySpark to SCOS — Coordinator

Orchestrate a multi-phase migration of PySpark workloads to Snowflake SCOS (Snowpark Connect for Spark). This coordinator delegates **code-fixing (Phase 2)** to a parallel pool of specialist sub-agents; runs the mechanical phases as scripts directly; and runs analysis + report-rendering (Phases 1, 1a, 4) **inline for single-file workloads or as sub-agents for multi-file workloads** (sized by `coordinator_mode`). Every phase is validated with deterministic quality gates (`scripts/scos_gates.py`) before advancing.

## When to Load

[snowpark-connect] Intent Detection: After user indicates migration intent (convert, migrate, update imports, rewrite for SCOS).

## Arguments

- `$ARGUMENTS` — Path to the PySpark file or directory to migrate

### Optional Metadata (from orchestrator)

| Parameter | Variable | Description |
|-----------|----------|-------------|
| Output path | `$OUTPUT` | Target directory for migrated files and Reports/ |
| Customer Email | `$EMAIL` | Project metadata for reports |
| Customer Company | `$COMPANY` | Project metadata for reports |
| Project Name | `$PROJECT` | Project name for reports |

If not provided, use `${ARGUMENTS}_scos` as output and prompt for metadata in Phase 4.

## Prerequisites

### Skill Directory

`<SKILL_DIRECTORY>` is the **parent** `snowpark-connect/` directory containing `pyproject.toml` and `scripts/`. All tool invocations use `uv run --project <SKILL_DIRECTORY>`.

### uv Package Manager

Install `uv` if it is not already available. Show both OS variants — the skill
must work on macOS / Linux *and* Windows:

```bash
# macOS / Linux
uv --version || curl -LsSf https://astral.sh/uv/install.sh | sh
```

```powershell
# Windows (PowerShell)
uv --version; if ($LASTEXITCODE -ne 0) { irm https://astral.sh/uv/install.ps1 | iex }
```

### Cortex LLM Access Preflight (REQUIRED)

Run this check before creating the conversion folder, copying source files,
initializing git, or running any recipe/preprocess step:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/check_cortex_llm_access.py \
  --connection default
```

Hard gate:

1. Command exits 0.
2. Output contains `CORTEX_LLM_PREFLIGHT=PASS`.

If this fails, STOP immediately and escalate to the user. Do not run Phase 0.
The analyzer runs in required-LLM mode, so this preflight prevents the expensive
retry/backoff loop caused by missing `SNOWFLAKE.CORTEX.COMPLETE` access.

Once this preflight passes, **export `SCOS_LLM_PREFLIGHT_VERIFIED=1` in the
shell that will run the rest of the migration**:

```bash
export SCOS_LLM_PREFLIGHT_VERIFIED=1
```

`analyze_pyspark.py` and `analyze_scala.py` see this env var and skip their own
internal `CORTEX.COMPLETE` probe — there is no value in re-asserting access
that was just verified seconds earlier. Direct analyzer invocations that did
not go through this preflight (no env var) still run the original fail-fast
probe, so this is a no-op for non-skill callers.

## Workflow

You are a coordinator. You **NEVER** hand-edit code fixes yourself, and the migrated reports are always produced by their generator scripts (never hand-written). **Code fixing (Phase 2) is always delegated to specialist sub-agents** via the `task()` tool — it fans out across files in a parallel worker pool and is by far the largest consumer of context, so isolating each fixer in its own sub-agent keeps the coordinator's window lean and lets waves run concurrently.

The **analysis (Phase 1)** and **report-rendering (Phases 1a and 4)** phases are run **one of two ways depending on workload size**, controlled by `coordinator_mode` (set in Phase 0: `false` when `manifest` holds a single file, `true` for multi-file workloads):

- **`coordinator_mode == false` (single-file / small) → run them inline yourself, no sub-agent.** Each is a deterministic script wrapped in at most light bounded judgment (a blind-spot supplementary scan for Phase 1, four advisory narrative sentences for Phase 1a, nothing for Phase 4), and on a one-file workload the inlined reads are tiny — a sub-agent would buy only cold-start latency and context churn. For the Phase 1 supplementary scan, prefer `grep`/`Bash` over `Read` so the source stays out of your window.
- **`coordinator_mode == true` (multi-file) → spawn a `task()` sub-agent for each**, exactly as for the fixer. Here the supplementary scan reads many source files and `analysis.json` / `AssessmentIR.json` grow with the workload; doing that inline would accumulate in the coordinator's single session and push toward `context_budget_tokens`. The throwaway sub-agent absorbs those reads and returns only a compact summary, preserving context isolation.

In both cases `agents/analyzer.md` and `agents/reporter.md` are the canonical step-by-step procedures — read and follow them (inline, or as the sub-agent's prompt context); the procedure is identical, only *who* runs it changes. The mechanical phases (pre-processing, SQL rewrite, import/header updates, coverage, verification, validation) are always deterministic scripts you invoke directly. Every phase is validated with a deterministic quality gate (`scripts/scos_gates.py` or a phase-specific validator); the gates are the real enforcement and run identically regardless of who performed the phase. State is tracked in `migration_state.json`.

### Phase 0: Collect Info and Create Conversion Folder

1. **Collect project info** from the user if not already provided: input path, output path, email, company, project name.

2. **Create timestamped conversion folder and copy source** — portable
   across macOS / Linux / Windows (no `date`, `mkdir -p`, or `cp -r`
   needed):

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/prepare_conversion_dirs.py \
  --output-root "<$OUTPUT or ${ARGUMENTS}_scos>" \
  --source "$ARGUMENTS"
```

The helper creates `<OUTPUT_ROOT>/Conversion-SCOS-<TIMESTAMP>/{Output,Reports,Logs}`,
copies `$ARGUMENTS` (file or directory) into `Output/` via `shutil.copytree`,
and prints the resolved paths as `KEY=value` lines (`CONVERSION`, `OUTPUT_DIR`,
`REPORTS_DIR`, `LOGS_DIR`, `TIMESTAMP`). Use those for the subsequent
placeholders.

> Prefer the helper over raw `date` / `mkdir -p` / `cp -r`. Those commands
> are not available in native Windows `cmd.exe` / PowerShell and would break
> the skill on Windows hosts.

3. **(Optional) reach for the legacy shell form only inside the CoCo bash
   sandbox** — if you are running *inside* the agent sandbox and not on the
   user's host, this Unix-only shortcut still works and the helper above
   produces the same layout:

   ```bash
   # Runs in the CoCo bash sandbox (Linux). Safe on any host OS.
   OUTPUT_ROOT="<$OUTPUT or ${ARGUMENTS}_scos>"
   TIMESTAMP=$(date +"%m-%d-%YT%H-%M-%S")
   CONVERSION="${OUTPUT_ROOT}/Conversion-SCOS-${TIMESTAMP}"
   mkdir -p "${CONVERSION}/Output" "${CONVERSION}/Reports" "${CONVERSION}/Logs"
   cp -r "$ARGUMENTS"/* "${CONVERSION}/Output/"
   ```

4. **Build the file manifest + notebook_index in one pass** — Python sources plus every notebook format (`.ipynb`, Databricks-native `.python`/`.scala`/`.sql`, Databricks exported `.py`/`.scala`). <!-- SNOW-3383535: Sort by relative path for deterministic chunk boundaries -->

Call `orchestrate_phases.py --build-notebook-index` to walk the tree once and produce both the notebook metadata and the per-cell language histogram in a single pass. It uses `notebook_io.scan_and_parse_notebooks` internally, so every notebook is detected and parsed exactly once — no redundant tree walks, no double-parsing. The Python-source (`.py`) list is built with a plain `os.walk` alongside. `notebook_io` has **zero third-party dependencies** (stdlib only), so invoke it directly with `python3` — do NOT wrap in `uv run --project`.

```bash
# First, write migration_state.json skeleton to <CONVERSION>/ (see step 7).
# Then build the combined manifest + notebook_index:
python3 <SKILL_DIRECTORY>/scripts/orchestrate_phases.py \
  --state <CONVERSION>/migration_state.json \
  --build-notebook-index <CONVERSION>/Output

# Plain-Python sources (skipping Databricks exported-text .py, which the
# notebook_index already covers):
python3 -c "
import json, os, sys
sys.path.insert(0, '<SKILL_DIRECTORY>/scripts')
import notebook_io as ni

root = '<CONVERSION>/Output'
py_files = []
for dp, _, files in os.walk(root):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(dp, f)
            if not ni.is_notebook(p):
                py_files.append(os.path.relpath(p, root))
print(json.dumps(sorted(py_files), indent=2))
"
```

The manifest for `migration_state.json` combines the `.py` list and every absolute path in the persisted `notebook_index`. The index carries `format`, `language`, `rel_path`, and `code_cells_by_language` (per-language cell counts) for every notebook, so Phase 2 orchestration can size chunks without re-parsing.

4a. **Unpack .dbc archives** (if present) — portable via the same helper.
    Use the `--unpack-dbc` flag against an existing `<CONVERSION>` folder:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/prepare_conversion_dirs.py \
  --output-root <OUTPUT_ROOT> --timestamp <TIMESTAMP> --unpack-dbc
```

The helper walks `<CONVERSION>/Output/` with `pathlib.rglob("*.dbc")` and
extracts each archive into a sibling `<name>_unpacked/` using the standard
`zipfile` module. No `find`, no POSIX `for` loop, works on Windows.
After unpacking, re-run `orchestrate_phases.py --build-notebook-index` so the index picks up the new notebooks.

5. **Determine dispatch mode**: Phase 2 fixing runs through a **fixer worker pool** (parallel sub-agents), sized by `max_parallel_fixers` (default: 4).
   - If `len(manifest) == 1`: set `coordinator_mode = false` — process the single file inline; a pool buys nothing.
   - If `len(manifest) >= 2`: set `coordinator_mode = true` — `orchestrate_phases.py` splits the manifest into balanced chunks and the coordinator dispatches up to `max_parallel_fixers` fixer sub-agents **concurrently per wave** (see Phase 2). `DISPATCH_THRESHOLD` (default 100) no longer gates parallelism; it only marks workloads large enough to expect multiple re-chunking waves.

6. **Initialize git** and tag the original source so Phase 1a can render the report from the customer's UNMODIFIED code:
```bash
cd <CONVERSION> && git init && git add . && git commit -m "Initial commit: source copied for SCOS migration" && git branch -M main && git tag phase-0-source
```

7. **Write `migration_state.json`** to `<CONVERSION>/`:
```json
{
  "phase": 0,
  "manifest": ["<relative paths for Python sources AND notebooks, sorted alphabetically>"],
  "file_order": ["<relative paths sorted alphabetically — mirrors manifest order for auditability>"],
  "notebook_files": {
    "ipynb":            ["<.ipynb files>"],
    "native_python":    ["<.python Databricks JSON files>"],
    "native_scala":     ["<.scala Databricks JSON files>"],
    "native_sql":       ["<.sql Databricks JSON files>"],
    "exported_python":  ["<.py files with '# Databricks notebook source' header>"],
    "exported_scala":   ["<.scala files with '// Databricks notebook source' header>"]
  },
  "dbc_archives": ["<list of .dbc files>"],
  "conversion_root": "<CONVERSION>",
  "migrated_dir": "<CONVERSION>/Output/",
  "skill_directory": "<SKILL_DIRECTORY>",
  "coordinator_mode": true,
  "dispatch_threshold": 100,
  "max_parallel_fixers": 4,
  "context_budget_tokens": 160000,
  "chunk_size": 20,
  "chunks": [],
  "processed_files": [],
  "pending_files": [],
  "phases_completed": {},
  "metadata": {"email": "...", "company": "...", "project": "..."}
}
```

### Phase 0.5: Deterministic Pre-Processing (MUST RUN)

**This phase MUST run as the first deterministic step of every migration**,
after Phase 0 has populated `<MIGRATED>` with the source copy and before
the LLM analyzer in Phase 1 sees the code. It applies every registered
LibCST recipe under `<SKILL_DIRECTORY>/scripts/recipes/` to every Python
file in the manifest.

**Why this exists:** the LLM fixer in Phase 2 is good at judgment-heavy
rewrites (UDFs, custom logic, ambiguous SQL) but historically dropped
mechanical details — the canonical example is silently losing
`SparkSession.builder.config("spark.sql.session.timeZone", "UTC")` when
collapsing the builder chain, which shifts every timestamp in the
migrated workload by 8h on US laptops. Recipes solve those mechanical
patterns byte-for-byte once, so the LLM can spend its tokens on the
genuinely hard stuff.

The driver script is pure Python + LibCST (already in `pyproject.toml`),
so invoke it via `uv run`:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/preprocess_recipes.py \
  --state <CONVERSION>/migration_state.json
echo "preprocess_exit=$?"
```

**Built-in pre-flight (runs automatically first):** before applying any
recipe, `preprocess_recipes.py` runs `scripts/precompile_check.py`, which
`compile()`s every Python unit (whole `.py` file, or each python code cell of
a notebook). This exists because LibCST recipes call `cst.parse_module` and
**silently skip un-parseable input** — so a *pre-existing* syntax error in the
customer's source (the canonical case: an entire notebook cell stray-indented
at module level → `IndentationError: unexpected indent`) would otherwise
survive untouched into Phase 2, where the fixer's compile guard reverts the
whole file on every pass without ever fixing anything. The pre-flight:

- attempts **guarded, whitespace-only** auto-fixes (uniform dedent;
  module-scope logical-line dedent) — a transform is accepted only if the unit
  then compiles, so it can never change semantics beyond indentation; and
- records every unit that started broken in
  `migration_state.json["preexisting_syntax"]` as
  `{file, cell_id, error, auto_fixed}`.

Residual entries with `auto_fixed: false` are genuine source bugs the
pre-flight could not safely repair. Downstream phases consume this record: the
fixer (Phase 2) does **not** revert a whole file for a pre-existing broken cell
it did not touch, and the fixer gate (`scos_gates.py`) downgrades such a
compile failure from a blocking `CRITICAL` to an advisory `preexisting_syntax`
WARN. You can run the pre-flight standalone (`precompile_check.py --state ...`,
`--dry-run` supported), but you normally do not need to — Phase 0.5 runs it.

**Hard gate (all must be true):**

1. The script exits 0.
2. The printed `PHASE 0.5 SUMMARY` block reports `Files processed` >= 1, **or** the manifest contains no `.py` files (notebook-only workload) — in that case `Files processed: 0` is expected and the phase is still `passed`.
3. `migration_state.json["phases_completed"]["0_5_preprocess"]["status"] == "passed"`.

If exit code is non-zero, do NOT advance to Phase 1. Re-read the error,
fix the underlying issue (most likely: an un-parseable Python file in
`<MIGRATED>/`), and re-run the driver. The driver is idempotent — running
it again on already-rewritten files is a safe no-op.

**Write contract** (the driver records this for you; do not touch it
manually unless overriding):

```json
"phases_completed": {
  "0_5_preprocess": {
    "status": "passed",
    "ran_at": "<ISO-8601 UTC>",
    "files_processed": <int>,
    "files_modified": <int>,
    "total_edits": <int>,
    "recipes_run": ["<recipe_id>", ...]
  }
}
```

Plus a top-level `recipe_edits` block keyed by relative path:

```json
"recipe_edits": {
  "<rel_path>.py": [
    {
      "recipe_id": "<id>",
      "src_line": <int>,
      "output_line_anchor": "<id>:<src_line>:<8-hex>"
    }
  ]
}
```

The analyzer (Phase 1) and fixer (Phase 2) MAY read `recipe_edits` to
recognise recipe-managed regions and avoid re-flagging or undoing them.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 0.5: deterministic pre-processing"`

### Phase 0.6: Standalone SQL Rewrite (MUST RUN)

Runs immediately after Phase 0.5 and before Phase 1, so the analyzer and fixer
see already-rewritten SQL. Standalone `.sql` workloads are otherwise only
*analyzed* (no phase rewrites them); embedded `spark.sql("...")` SQL is handled
by the Phase 0.5 `spark_sql_mechanical_rewrite` recipe. This step is the
standalone-`.sql` counterpart: it deterministically rewrites the SCOS SQL gaps
that have a safe, semantics-preserving syntactic fix (EXPLAIN drops, GROUPING
SETS folding, CACHE/UNCACHE removal, …) via sqlglot and annotates the residual
judgment-heavy gaps — including window-missing-ORDER-BY and multi-column NOT IN,
which are detected but NOT auto-rewritten — with `-- SCOS: TODO -` for the fixer.

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/rewrite_sql_files.py \
  --state <CONVERSION>/migration_state.json
echo "sql_rewrite_exit=$?"
```

The script discovers `.sql` files under `migrated_dir` (excluding Databricks
native-JSON `.sql` notebooks), rewrites in place, prepends a `-- SCOS:` audit
block per file, and records `sql_rewrite_edits` + `phases_completed["0_6_sql_rewrite"]`.
It is idempotent (a file carrying the sentinel is skipped) and leaves
unparseable SQL byte-identical.

**Hard gate (all must be true):**

1. The script exits 0.
2. `migration_state.json["phases_completed"]["0_6_sql_rewrite"]["status"] == "passed"`.

A workload with no `.sql` files still records the phase with `files_processed: 0`
— that is a valid pass, not a skip. Phase 0.6 is **optional only for SQL-free
workloads**: when standalone `.sql` files are present, `validate_migration_state.py`
(Phase 4a) marks a missing/failed `0_6_sql_rewrite` as a hard failure. As a
reliability backstop, `orchestrate_phases.py --phase 2` also runs the standalone
SQL rewrite itself if this phase was not recorded — so even if the coordinator
skips this step, standalone `.sql` files are still rewritten before fixer
dispatch.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 0.6: standalone SQL rewrite"`

### Phase 1: Analysis

**Run mode (size-aware)**: if `coordinator_mode == false` (single-file / small), run this phase **inline** by reading `agents/analyzer.md` and following its steps yourself; if `coordinator_mode == true` (multi-file), **spawn a `task()` sub-agent** with the content of `agents/analyzer.md` as prompt context (pass the `migration_state.json` path), so its many source reads and the growing `analysis.json` stay out of your window. The procedure is identical either way: run `analyze_pyspark.py` with `--recipe-edits <CONVERSION>/migration_state.json` so **the Phase 0.5 `recipe_edits` block is injected as per-block grounding into every Cortex call** (issues become tiered by `kind`: `recipe_validated` | `recipe_incomplete` | `recipe_adjacent` | `llm_only`), then perform the supplementary blind-spot scan from `agents/analyzer.md` Step 2 (UDF / `pandas_udf` / `applyInPandas` / `checkpoint` / map-subscript patterns the script may miss) and append any genuinely-missing entries. When running inline, prefer `grep`/`Bash` over `Read` for that scan. Produces `analysis.json`.

**Cross-language notebooks**: inspect `migration_state.json :: notebook_index`. Any entry whose `code_cells_by_language` has more than one of `{python, scala}` is cross-language. For those workloads, ALSO run `analyze_scala.py` on the same inputs (with the same `--notebook-index` flag) and merge its output into the same `analysis.json` — each row carries a `language` field so the fixer and CELL_MODE pre-filter can distinguish Python-cell issues from Scala-cell issues. If no notebook is cross-language, skip the Scala analyzer.

**Quality gate**: run the analyzer gate (a deterministic script):

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/scos_gates.py analyzer \
  --state <CONVERSION>/migration_state.json --json
```

The gate reports its outcome on stdout (`verdict` + `exit_code` in `--json`, or a `PASS`/`FAIL` line in human mode); read that directly rather than relying on a shell `$?` capture, which is not portable to Windows `cmd.exe` / PowerShell.

> Invoke through `uv run` (not a bare `python3`/`python`) so the gate runs on a guaranteed interpreter on macOS / Linux / Windows. `scos_gates.py` itself is stdlib-only, so it adds no dependencies.

The gate validates `analysis.json` (valid JSON array + risk-distribution sanity) and scans every manifest `.py` file for the analyzer's known blind spots (UDF / pandas_udf / udtf decorators, `applyInPandas`, `checkpoint`, JVM `._jdf`/`._jvm` access, `sparkContext`, map-subscript, Hadoop/HDFS, Delta, ML pipelines), flagging any match not covered by an `analysis.json` entry. Comment-only and already-`# SCOS:`-annotated lines are skipped.

**Gate**:
- Exit `0` (`PASS` or `PASS_WITH_GAPS`) → advance. `PASS_WITH_GAPS` carries advisory `WARN` findings only; record them but do not block.
- Exit `2` (`FAIL`) → re-run the analyzer step the same way you ran it (inline, or by re-dispatching the `agents/analyzer.md` sub-agent in multi-file mode) using the gate's `gaps` array as targeted feedback (it names each uncovered `file:line` + blind-spot code) — usually this just means appending the missing supplementary entries to `analysis.json` — then re-run the gate. Retry at most **2 times**; if it still fails, escalate to the user.
- Exit `3` (IO / usage error) → the gate could not read `migration_state.json` or `analysis.json`. Re-running the analyzer will NOT fix this. STOP and escalate to the user immediately; do not retry.

Record the result and set `migration_state.json` phase to 1:
```json
"phases_completed": {"1_analysis": {"status": "passed", "gate": "scos_gates.analyzer", "verdict": "<PASS|PASS_WITH_GAPS>", "attempts": <n>}}
```

### Phase 1a: Render Assessment Report

**Run mode (size-aware)**: if `coordinator_mode == false`, run this **inline** by reading `agents/reporter.md` and following **Section A (Assessment Report) only** yourself; if `coordinator_mode == true`, **spawn a `task()` sub-agent** with `agents/reporter.md` to run Section A, so the `AssessmentIR.json` read stays out of your window. Either way it renders `Reports/MigrationReadinessReport.html` + `Reports/AssessmentIR.json` from the Phase 1 `analysis.json` and a deterministic scan of the **pre-Phase-0.5** source (materialized from the `phase-0-source` git tag), producing a pre-migration readiness view for stakeholders. The reporter passes `--migration-state-json <CONVERSION>/migration_state.json` so the renderer materializes the original source itself and populates the standalone "Phase 0.5 auto-resolved" panel from `migration_state.json[recipe_edits]` — analyzer findings retain their post-Phase-0.5 risk math but their line numbers and code snippets are rebased back onto the original source.

**Talking about results in chat:** describe migration effort with the code-churn **categories** — Ready / Light Refactor / Active Refactor — and the per-bucket file counts. **Never quote a numeric "readiness score" or percentage**; the assessment is deliberately category-based (the old 0-100 score was nondeterministic analyzer confidence and is gone).

**Quality gate**: run the assessment-report gate (a deterministic script):

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/scos_gates.py reports --section assessment \
  --state <CONVERSION>/migration_state.json --json
```

The gate confirms `Reports/MigrationReadinessReport.html` and `Reports/AssessmentIR.json` exist and that the HTML has no unsubstituted Jinja placeholders (`{{` / `{%`). Read the verdict from stdout (do not rely on a non-portable `$?` capture).

**Gate (bounded retry, then hard fail)**:
- Exit `0` → advance and record:
  ```json
  "phases_completed": {"1a_assessment_report": {"status": "passed", "gate": "scos_gates.reports:assessment", "attempts": <n>}}
  ```
- Exit `2` (`FAIL`) → re-run Section A the same way you ran it (inline, or by re-dispatching the `agents/reporter.md` Section A sub-agent in multi-file mode) with the gate's `gaps` array as feedback, then re-run the gate. Retry at most **3 times total**. If it still fails, **STOP and escalate to the user** — do NOT advance to Phase 2 with a missing or broken report. Record:
  ```json
  "phases_completed": {"1a_assessment_report": {"status": "skipped", "attempts": 3, "skip_reason": "<one-line reason>"}}
  ```
- Exit `3` (IO / usage error) → the gate could not read `migration_state.json` or the `Reports/` paths; re-running the reporter will NOT fix this. STOP and escalate immediately.

**Phase 1b: Data-edge enrichment (LLM fallback) — explicit user decision.** Run this step **inline yourself (the main loop), never in a sub-agent** — it requires user interaction, and a spawned `task()` sub-agent cannot prompt. This runs regardless of `coordinator_mode`. It is **optional** (the user may decline) and so is not part of the required-phase set the final verification gate checks.

**Re-run guard (check first).** If `migration_state.json :: phases_completed.1b_data_edge_resolution` already exists with a terminal status (`passed`, `warned`, `not_needed`, or `skipped`), the decision was already made for this conversion — **do not re-prompt or re-run** (a fresh resolution pass is expensive and the IR already carries the prior result). Skip straight to the Git checkpoint. Only re-run if the user *explicitly* asks to redo enrichment.

The seed report's data dependency graph is only as complete as the static AST scanner could make it. Read the two incompleteness counts from `Reports/AssessmentIR.json` **without pulling the whole IR into context** — extract just the lengths:

```bash
python3 -c "import json,sys; d=json.load(open('<CONVERSION>/Reports/AssessmentIR.json')); print(len(d.get('unresolved_data_edges') or []), len(d.get('unresolved_dynamic_imports') or []))"
```

The two numbers are `N` (unresolved read/write call sites the scanner could not statically resolve) and `M` (dynamic import / dispatch sites it could not resolve).

- **If `N + M == 0`**: the static DAG has no unresolved gaps. Tell the user in one line that LLM enrichment is still available (it can also surface I/O the scanner never recognises — boto3, SQL template files, `dbutils.taskValues` handoffs) but is optional, then proceed **without stopping**. Record `"1b_data_edge_resolution": {"status": "not_needed"}`.
- **If `N + M > 0`**: **STOP and present this to the user** (fill in the counts), then wait for a Y/n answer before doing anything else:

  > ⚠️ **The data dependency graph is incomplete.** Static analysis left **{N} unresolved read/write edge(s)** and **{M} unresolved dynamic import(s)** — the DAG and data-lineage in the report may have blind spots at those sites.
  >
  > I can run an **LLM data-edge enrichment** pass that reads every `.py` / `.sql` / `.ipynb` file in the workload, traces the dynamic paths the scanner couldn't, resolves the dynamic imports, and discovers out-of-scope I/O (boto3, SQL template files, task-value handoffs). It needs **no Snowflake connection** and its results are cached in `AssessmentIR.json`, so the re-render is free.
  >
  > ⏱️ It reads the entire workload, so it typically takes **5+ minutes and scales with workload size** — larger workloads take longer.
  >
  > **Run LLM data-edge enrichment now? (Y/n)** — if you skip, the report ships with the static-only DAG (clearly labeled as such), and you can run enrichment later with `render_assessment.py --llm-resolved-edges --dump-ir <CONVERSION>/Reports/AssessmentIR.json` (the `--dump-ir` path is required — without it the flag loads nothing and silently produces a static-only report).

  - **Yes** → follow `agents/reporter.md` Section A **Step 1b** (the resolver loop → gate → final `--llm-resolved-edges` render). The whole-workload file reading may be dispatched to a `task()` sub-agent on multi-file workloads, but the decision prompt above stays with you.
  - **No** → keep the static report; record `"1b_data_edge_resolution": {"status": "skipped"}` and proceed.

**After enrichment runs, report the outcome to the user (Yes path only).** Summarize the result (keeps the full IR out of context):

```bash
python3 <SKILL_DIRECTORY>/scripts/assessment/summarize_llm_resolution.py <CONVERSION>/Reports/AssessmentIR.json
```

The resolver stamped each confirmed-unresolvable site with a `severity`; the summary groups by it. Relay:

- **`clean: true`** (no `critical`) → one line: enrichment resolved all `baseline_unresolved_edges` read/write edge(s) and `baseline_unresolved_imports` import(s) the static scanner left open (add `newly_discovered` if > 0). If `informational` is non-empty, add one line noting those are runtime-only endpoints (config-driven paths etc.) that migrate fine but can't be drawn as exact lineage.
- **`clean: false`** → lead with ⚠️: for each `critical` item name the `file` and its `why` — a **missing input** (a file/module/caller/table absent from the export) that may block migration; these are also in the report's data-lineage section. Then note `informational` blind spots and the `benign_count` dead ends in one line each. Advisory only; never block — the report always ships with whatever was resolved.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 1: analysis complete + assessment report rendered" && git tag phase-1-complete`

### Phase 2: Apply Fixes

<!-- SNOW-3385158: Orchestration moved to external script for deterministic dispatch -->
<!-- SNOW-3383531: Budget reduced to 80k tokens/chunk (aggressive mode) for guaranteed completion -->
**Pre-dispatch: Run External Orchestrator** — Compute budget-aware chunks and write the dispatch plan to `migration_state.json`:

```bash
python3 <SKILL_DIRECTORY>/scripts/orchestrate_phases.py \
  --state <CONVERSION>/migration_state.json \
  --phase 2 \
  --budget 80000 \
  --max-parallel 6 \
  --language python
```

The script splits the manifest into **token-balanced chunks sized for the worker pool** — at least `min(max_parallel, n_files)` chunks so even a small workload fans out — and prints a **wave-based dispatch plan**. It groups chunks into waves of `MAX_PARALLEL`, and for each chunk outputs `CHUNK_MODE`, `CHUNK_ID`, and `CHUNK_FILES`. It also initialises `chunks[]`/`pending_files`/`processed_files` and prints a final coverage report (every manifest file must be present in `Output/`). Read the output and act on it. (No `fallback_transform.py` runs here — the mechanical floor is owned by Phase 3.)

Token formula: `file_tokens = file_chars // 4 + 2000` (characters ÷ 4 plus 2000 overhead per file). `--budget` is a hard per-chunk cap; a single file that exceeds it gets a dedicated chunk so it is never silently skipped. `--max-parallel` (default 4, or `max_parallel_fixers` from state) sets the worker-pool width.

**Spawn specialists IN PARALLEL (worker pool)**: process the plan **wave by wave**. For each wave, spawn **all of that wave's chunks' `agents/fixer.md` sub-agents concurrently** — issue the `task()` calls in a **single turn** (do NOT await one before starting the next). Pass `CHUNK_MODE=chunked`, `PARALLEL_MODE=true`, `CHUNK_ID=<n>`, and `CHUNK_FILES=<files>` to each. Every fixer processes **only** the files in its `CHUNK_FILES`.

> **State-write ownership (critical):** parallel fixers **MUST NOT** write `migration_state.json` — concurrent read-modify-write on one file loses updates. Each fixer instead returns a single line:
> `CHUNK_RESULT id=<CHUNK_ID> processed=<f1,f2,...> skipped=<f,...> issues_fixed=<int> todos=<int>`
> **You (the coordinator) are the single writer.** After the whole wave's sub-agents return, update `migration_state.json` **once**: append each `processed` file to `processed_files[]`, remove it from `pending_files[]`, append `skipped` files to `2_fixes_skipped[]`, and set `chunks[i].status = "done"` for every chunk in the wave.

After each wave's state update, git checkpoint:
```bash
cd <CONVERSION> && git add -A && git commit -m "Phase 2: wave <w>/<total> complete (<k> chunks)"
```

**Checkpoint detection**: After a wave's state update, if `pending_files` is non-empty (e.g. a worker crashed), re-run `orchestrate_phases.py` — it recomputes balanced chunks from the remaining files — and dispatch the next plan. Repeat until `pending_files` is empty and every `chunks[i].status == "done"`.

**Quality gate**: after all chunks complete, run the fixer gate on the full `Output/` directory (a deterministic script):

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/scos_gates.py fixer \
  --state <CONVERSION>/migration_state.json --json
```

The gate compiles every manifest `.py` with `py_compile`, validates each `.ipynb` as well-formed notebook JSON, confirms no migrated file is empty or missing from `Output/`, and checks that every high-risk `analysis.json` issue (`final_risk >= 0.7`) has a fix or `# SCOS:` marker near its line. Read the verdict from stdout.

**Orchestration enforcement (`phase2_not_orchestrated`)**: for any workload with **≥ 2** code files, the gate FAILS if `migration_state.json` has no orchestrator plan (`max_parallel_fixers` + `phase2_chunks`). This is the deterministic guard against the coordinator *improvising* an inline single-agent fix and silently bypassing the parallel fixer pool. If you see this finding, you skipped `orchestrate_phases.py` — run it, dispatch the printed waves, then re-run the gate.

**Gate**:
- Exit `0` (`PASS` / `PASS_WITH_GAPS`) → advance and update `migration_state.json` phase to 2. `PASS_WITH_GAPS` carries advisory `WARN` findings only (e.g. no-op over-annotation); record them but do not block.
- Exit `2` (`FAIL`) → re-dispatch `agents/fixer.md` on the files named in the gate's `gaps` array only, then re-run the gate. Retry at most **2 times**; if it still fails, escalate to the user.
- Exit `3` (IO / usage error) → STOP and escalate; re-running the fixer will not fix a missing state/path.

Files the LLM fixer skipped are still handled downstream: Phase 2c (`verify_migration.py`) classifies them as `partial` from on-disk evidence, and Phase 3 (`scripts/update_imports.py`) applies the mechanical floor (imports, session-init replacement, migration header) to *every* manifest file regardless.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 2: all chunks complete, fixes applied"`

### Phase 2a: Coverage Verification Gate (MUST RUN)

<!-- SNOW-3375304: Ensure 100% file coverage -->

Every run of `orchestrate_phases.py` prints a `COVERAGE VERIFICATION` report and sets `migration_state.json` field `orchestrator_coverage_verified` (recorded under the `2a_coverage` phase). Before advancing, read the report from the final orchestrator run:

- `Coverage: 100%` (every manifest file is present in `Output/`, copied in Phase 0) → advance to the compilation gate.
- `MISSING` files listed → escalate to the user; a manifest file is absent from `Output/`. Do not advance.

### Phase 2b: Compilation Verification Gate (MUST RUN)

<!-- SNOW-3379886: Hard gate ensuring 100% compilation after code fixes -->

**This phase MUST run after Phase 2, on every workload, with no exceptions.**
Skipping it lets broken syntax ship to the customer's `Output/` directory. Even
single-file workloads must run the gate.

This is the **same fixer gate** from Phase 2, re-run with `--revert-failing` —
its final safety-net mode. During Phase 2 the gate runs read-only and drives the
re-fix loop; here it gets one authority to *repair*. Any `.py` that **still**
does not compile is reverted to its pre-Phase-2 baseline (`phase-1-complete`) — a
working original beats broken half-migrated syntax — and reported as an advisory
`fix_reverted`. Files that cannot be reverted (missing baseline, empty, or still
broken after revert) remain blocking `CRITICAL` findings. (There is no separate
`revert_failing_files.py` step anymore; that logic is folded into the gate, so
there is a single post-loop compilation gate.)

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/scos_gates.py fixer \
  --state <CONVERSION>/migration_state.json \
  --revert-failing --phase-tag phase-1-complete --json
```

The JSON payload reports `verdict`, `exit_code`, `gaps`, `reverted`, and
`reverted_count`. Use `reverted_count` for the bookkeeping below.

**Checklist** (do every step in order; do not skip steps):

- [ ] Run the gate above. If `exit_code == 2` (`FAIL`), some files could neither
      be compiled **nor** reverted — re-dispatch `agents/fixer.md` on the `gaps`
      files only, then re-run. Repeat until `exit_code == 0` or you have iterated
      3 times.
- [ ] Write to `migration_state.json`:
  ```json
  "phases_completed": {
    "2b_compilation": {
      "status": "passed",
      "reverted_count": <N>,
      "iterations": <K>
    }
  }
  ```
  AND write the legacy top-level field for backward compat:
  ```json
  "compilation_reverted_count": <N>
  ```
- [ ] If you cannot run this phase for any reason (e.g. `<MIGRATED>` is empty,
      `phase-1-complete` tag missing), set:
  ```json
  "phases_completed": {
    "2b_compilation": {
      "status": "skipped",
      "skip_reason": "<one-line reason>"
    }
  }
  ```
  and **STOP** — do not advance to Phase 3. Escalate to the user.

**Hard gate (all of the following MUST be true to advance to Phase 3):**

1. Final `exit_code == 0` (verdict `PASS` / `PASS_WITH_GAPS`) — no remaining `CRITICAL` syntax/compile findings.
2. `migration_state.json["phases_completed"]["2b_compilation"]["status"] == "passed"`.
3. The legacy field `migration_state.json["compilation_reverted_count"]` is set to `<N>`.

If any of these is false, do NOT advance. Either re-iterate or mark `skipped`
with a reason and escalate.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 2b: compilation gate passed (reverted_count=<N>)"`

### Phase 2c: Evidence-Based Verification Gate (MUST RUN)

<!-- SNOW-3383532: single, evidence-based writer of Partial Migration findings -->
**This phase MUST run exactly ONCE, after Phase 2b and after all fixer
re-dispatching is complete.** Do NOT run it inside the per-chunk dispatch loop
— doing so persists partial labels into `analysis.json` before the async fixer
has finished, producing stale/false partials.

The self-reported completion in `migration_state.json` (`processed_files` /
`files_done`) is not proof a file was migrated — only that the agent attempted
it. This gate cross-checks the state against on-disk evidence and reconciles
both artifacts to the truth. It is the **sole writer** of Partial Migration
findings. A file is marked done only by the genuine fixer, so its recorded
completion state is itself trustworthy evidence.

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/orchestrate_phases.py \
  --state <CONVERSION>/migration_state.json \
  --run-verification --language <python|scala>
```

This runs `verify_migration.py --write`, which:
- Classifies every file from evidence: `migrated` (a real `# SCOS:` fixer marker is present, OR the file is recorded done with Spark surface), `partial` (has Spark surface / real findings but no genuine fixer edit and not recorded done), `trivial` (no Spark surface), `not_attempted` (file missing from `Output/` and therefore not produced by the migration flow).
- Writes ONE verified `SPRKCNTPY0099`/`SPRKCNTSCL0099` finding per genuinely-partial file into `analysis.json` and records it in `needs_human_action`; clears any stale Partial-Migration noise and falsely-flagged migrations.
- Re-verifies and prints `disagreements = 0` on success.

If any file appears as `not_attempted`, Phase 2's coverage gate should already
have caught it. Treat that as a hard failure and escalate to the user — do NOT
advance to Phase 3 or Phase 4.

After the gate passes, record the Phase 2c milestone in `migration_state.json`
so downstream validation can detect if this phase was silently skipped:

```json
"phases_completed": {
  "2c_verification": {
    "status": "passed",
    "disagreements": 0,
    "not_attempted": 0,
    "needs_human_action": ["<relative path>", "..."],
    "verified_human_action_count": <N>,
    "recorded_migrated_count": <M>
  }
}
```

**Gate**: the command must print `Re-verify after reconcile: disagreements = 0`
and must NOT print a `Not attempted` section. The files listed in
`needs_human_action` are the genuine human-action items for the report.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 2c: evidence-based verification reconciled"`

### Phase 3: Imports and Headers

<!-- Deterministic: replaces the former agents/import-updater.md LLM specialist,
     mirroring how scos_gates.py replaced the LLM critic agents. Updating imports
     and stamping a header is a mechanical (replace/prepend) step, so it runs as a
     reproducible script the coordinator invokes directly — no sub-agent dispatch. -->
**Run the deterministic import updater** — it processes **every** manifest file
(`.py` and notebooks): replaces `SparkSession.builder...getOrCreate()` (and the
`DatabricksSession` variant) with `snowpark_connect.init_spark_session()` and
inserts `from snowflake import snowpark_connect`, comments out unsupported
`databricks` / `delta` imports (standard `pyspark` imports are kept), prepends a
SCOS migration-header docstring, and records `phases_completed["3_imports"]`.
`.config(...)` calls in builder chains are preserved via the shared LibCST recipe
(no timezone-drop). The transform is idempotent — re-running it is a safe no-op.

**This script is the sole author of the rich migration header.** It builds the
header's `Changes Overview` / `Known Limitations` from the `# SCOS:` annotations
in each file, so it MUST run on every workload. Do not hand-write headers and do
not let the report generator's placeholder stand in for it. If a file already
carries the *placeholder* stub (`Deterministic header added by report generator`,
stamped by `generate_scos_reports.py` only when this phase was skipped),
`update_imports.py` strips and replaces it with the real header.

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/update_imports.py \
  --state <CONVERSION>/migration_state.json
echo "update_imports_exit=$?"
```

**Quality gate**: run the imports gate (a deterministic script):

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/scos_gates.py imports \
  --state <CONVERSION>/migration_state.json --json
```

The gate verifies every manifest `.py` has a migration header in its first 15 lines, has no `SparkSession.builder` left in live (non-comment, non-docstring) code, has no unsupported imports (`databricks`, `delta.tables`), and that at least one file references `snowpark_connect`. It also FAILs (`stub_header`) if a file carries the report-generator placeholder header instead of a real one — proof this phase was skipped. Read the verdict from stdout.

**Gate**:
- Exit `0` → advance and update `migration_state.json` phase to 3.
- Exit `2` (`FAIL`) → the deterministic updater should already satisfy every
  check. A `stub_header` finding means `update_imports.py` never ran for that
  file — **run it now** (it strips the placeholder and writes the real header),
  then re-run the gate. Any other `FAIL` means an unusual input the transform
  could not normalise (e.g. a builder expression it could not parse, or an exotic
  multi-line import). Inspect the gate's `gaps` array, hand-correct the named
  `file:line`(s), then re-run the imports gate. If it still fails after one
  correction pass, escalate to the user.
- Exit `3` (IO / usage error) → STOP and escalate.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 3: imports and headers updated"`

### Phase 4: Generate Reports

**Run mode (size-aware)**: if `coordinator_mode == false`, run this **inline** by reading `agents/reporter.md` and following **Section B (Dashboard CSVs) only** yourself — it is purely a deterministic script invocation plus existence checks, with no judgment; if `coordinator_mode == true`, **spawn a `task()` sub-agent** with `agents/reporter.md` to run Section B (consistent with the other phases' multi-file handling, keeping the generator output and any `Issues.csv` inspection out of your window). Run `generate_scos_reports.py`, which (a) ensures each `# SCOS:` comment carries its EWI code inline (`# SCOS: [SPRKCNT...] <message>`) — reusing the code the fixer embedded, injecting a generic one only when absent, and removing legacy `#EWI:` lines that sit directly above a `# SCOS:` comment — then (b) produces `Reports/Issues.csv`, `Reports/InputFilesInventory.csv`, `Reports/ArtifactDependencyInventory.csv` from the final files. `Issues.csv` reads the same inline codes — and also surfaces the recipe-emitted `# SCOS-WARN:` / `# SCOS-TODO:` markers — so the report and the in-file comments agree on count, code, and line. (`MigrationReadinessReport.html` + `AssessmentIR.json` are **not** rendered here — they were already produced in Phase 1a.)

**Quality gate**: run the dashboard-CSV gate (a deterministic script):

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/scos_gates.py reports --section csvs \
  --state <CONVERSION>/migration_state.json --json
```

The gate confirms `Reports/Issues.csv`, `Reports/InputFilesInventory.csv`, and `Reports/ArtifactDependencyInventory.csv` exist, that `Issues.csv` has data rows carrying `SPRKCNTPY` codes, and that `InputFilesInventory.csv` is non-empty. Read the verdict from stdout.

**Gate (bounded retry, then hard fail)**:
- Exit `0` → update `migration_state.json` phase to 4 and record:
  ```json
  "phases_completed": {"4_reports": {"status": "passed", "gate": "scos_gates.reports:csvs", "attempts": <n>}}
  ```
- Exit `2` (`FAIL`) → re-run Section B the same way you ran it (inline, or by re-dispatching the `agents/reporter.md` Section B sub-agent in multi-file mode) with the gate's `gaps` as feedback, then re-run the gate. Retry at most **3 times total**. If it still fails, **STOP and escalate to the user**. Record:
  ```json
  "phases_completed": {"4_reports": {"status": "skipped", "attempts": 3, "skip_reason": "<one-line reason>"}}
  ```
- Exit `3` (IO / usage error) → STOP and escalate.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 4: reports generated"`

### Phase 4a: Post-Run State Validation (MUST RUN)

**This phase MUST run as the last deterministic step of every migration.** It
asserts that every required phase (1, 1a, 2, 2a, 2b, 2c, 3, 4) recorded evidence in
`migration_state.json` — either via the canonical `phases_completed[<key>]`
block or via the documented legacy top-level field. Silent skips become loud
failures here, before the user is offered validation.

The validator script is pure stdlib (no third-party deps), so invoke it
directly with `python3` — no `uv run` needed:

```bash
python3 <SKILL_DIRECTORY>/scripts/validate_migration_state.py \
  --strict \
  --state <CONVERSION>/migration_state.json
echo "validator_exit=$?"
```

**Hard gate (all must be true):**

1. The script exits 0 (no required phase missing or skipped without reason).
2. The printed report shows `PASS: all required phases present.`.

If the script exits non-zero, do NOT advance to Phase 5. Read the listed
missing phase(s), re-run the corresponding phase, and re-invoke the validator
until it passes. If a phase genuinely cannot run, edit `migration_state.json`
to set:

```json
"phases_completed": {
  "<phase_key>": {
    "status": "skipped",
    "skip_reason": "<one-line reason>"
  }
}
```

and re-run the validator. Skipped-with-reason is the only acceptable form of
non-completion. Skipping without a `skip_reason` always fails the gate.

**Then record the self-attestation** — after the validator exits 0, append a
`phases_completed["4a_validation"]` entry to `migration_state.json` so future
readers can tell from the state file alone that Phase 4a ran:

```json
"phases_completed": {
  "4a_validation": {
    "status": "passed",
    "validator_exit_code": 0,
    "validator_run_at": "<ISO-8601 UTC timestamp>"
  }
}
```

This entry is **optional** to the validator (it does not fail strict mode if
absent), but **required** by this SKILL — without it, downstream tooling
cannot confirm Phase 4a actually executed without parsing the transcript. (The
validator still accepts the older `4b_validation` key for back-compat.)

For machine-readable output (e.g. when wrapping in CI), pass `--json` instead
of the default human report.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 4a: validation passed"`

### Phase 4b: Generate Migration Feedback File (Non-Fatal)

Run the migration feedback generator to produce the file the FDE attaches to a
Jira ticket for Casper to triage:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/generate_migrate_feedback.py \
  --conv-root <CONVERSION>
```

Output: `<CONVERSION>/Feedback/migrate_gaps.md`

**Non-fatal**: if the script fails or `Reports/Issues.csv` is absent, log a
warning and continue.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 4b: migration feedback file generated"`

### Phase 5: Offer Validation (Optional)

Ask the user:
```
Migration complete! Would you like to validate the migrated workload
by running it end-to-end with synthetic data?
```

If yes, load `validate-pyspark-to-snowpark-connect/SKILL.md` with `<MIGRATED>` as `$ARGUMENTS`.

If the user accepted validation and it completed successfully, run the validation feedback generator (non-fatal). Skip this step entirely if the user declined validation or if validation did not complete:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/generate_validate_feedback.py \
  --conv-root <CONVERSION>
```

Output: `<CONVERSION>/Feedback/validate_feedback.md`

### Phase 6: Offer Notebook Conversion (Standalone Only)

<!-- Added for native notebook processing — only runs in standalone invocation. -->
Skip this phase entirely when the parent orchestrator (`snowflake-migration`) invoked Snowpark Connect. The orchestrator runs notebook conversion as its own later step and passes an explicit flag in the invocation context:

```
snowpark_connect_invoker: orchestrator
```

1. **Log the detected invoker** as the FIRST action of this phase. Parse the invocation context for `snowpark_connect_invoker`. Treat any value except `orchestrator` (including `standalone` and the missing case) as standalone. Print one line:
   ```
   Phase 6 invoker: <orchestrator|standalone>
   ```
2. **Orchestrator-mode gate**. Skip Phase 6 and proceed to Resumption if either:
   - `snowpark_connect_invoker == "orchestrator"`, OR
   - (legacy) the literal string `snowflake-migration` appears as the invoker — preserved only for callers that predate the invoker flag. New callers MUST set `snowpark_connect_invoker` explicitly.
   When skipping, print `Phase 6 skipped: orchestrator mode` and exit.

3. **Check whether `snowflake-notebook-migration` is installed** — use the same lookup pattern as `snowflake-migration/SKILL.md` Step 7 (search available/installed skills for `snowflake-notebook-migration`).

4. **If the skill is NOT installed**, print the informational note and exit Phase 6:
   ```
   Notebook Conversion (optional follow-up):
   To convert the migrated notebooks under <MIGRATED> to Snowflake Workspace
   `.ipynb` format, install the `snowflake-notebook-migration` skill and run
   it against the Output/ directory.
   ```

5. **If the skill IS installed**, ask the user:
   ```
   I can also convert the migrated Databricks notebooks to Snowflake
   Workspace format using the `snowflake-notebook-migration` skill.
   Would you like me to run that now on <MIGRATED>? (y/n)
   ```

6. **If the user answers yes**, load the bundled `snowflake-notebook-migration` sub-skill **in the foreground** and follow it inline. Resolve its path relative to the `spark-migration` root (`<spark_migration_root>` = this skill's grandparent = `snowpark-connect/..`):
   ```bash
   NB_MIGRATION_SKILL="<spark_migration_root>/snowflake-notebook-migration/SKILL.md"
   ```
   Read that file with the Read tool, then follow its instructions with `<MIGRATED>` as the argument. Never spawn it as a background agent. Do NOT use `skill("snowflake-notebook-migration")` — it is a bundled sub-skill at the `spark-migration` root, not a registered top-level skill in this nested context.

7. **If the user answers no**, print the informational note above and exit Phase 6.

### Resumption

If context is lost mid-migration, read `migration_state.json` to determine the last completed phase and resume from the next one. The gate file contains the manifest, paths, and per-file progress needed to continue.

## Stopping Points

- Phase 0: After collecting project info — confirm settings before starting
- Phase 2: If the fixer gate fails after 2 retries — escalate to user with specific errors
- Phase 5: After migration completes — ask user about validation

## Success Criteria

- `scripts/validate_migration_state.py --strict` exits 0 (this is the
  canonical, machine-checkable success criterion — see Phase 4a)
- `migration_state.json` shows all phases 1-4 completed with gate approval
- `Reports/Issues.csv` exists with data rows
- `Reports/InputFilesInventory.csv` row count matches manifest
- `Reports/MigrationReadinessReport.html` and `Reports/AssessmentIR.json` exist
- All `.py` files pass `py_compile` syntax check
- Every `.py` file has a migration header docstring
- File count matches between original and migrated directories

## Output

```
<output_root>/
  Conversion-SCOS-<timestamp>/                       ← <CONVERSION>
    Output/                                          ← <MIGRATED> — converted files
    Reports/
      Issues.csv                                     ← EWI issues (SPRKCNTPY*)
      InputFilesInventory.csv                        ← Source file inventory
      ArtifactDependencyInventory.csv                ← Import dependencies
      MigrationReadinessReport.html                  ← Stakeholder-facing readiness report
      AssessmentIR.json                              ← Structured IR (stable contract)
    Logs/                                            ← Migration log
    migration_state.json                             ← Phase gate tracking
    analysis.json                                    ← Compatibility analysis
```

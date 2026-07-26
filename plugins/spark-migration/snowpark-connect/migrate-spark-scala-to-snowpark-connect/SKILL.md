---
name: migrate-spark-scala-to-snowpark-connect
description: |
  Migrate Spark Scala workloads to Snowflake SCOS (Snowpark Connect for Spark).
  Use when: converting Scala Spark code to run on Snowflake, analyzing Scala Spark compatibility,
  updating imports to Spark Connect equivalents, or migrating from standalone Spark Scala.
  Generates SMA-compatible reports (Issues.csv, InputFilesInventory.csv, ArtifactDependencyInventory.csv)
  for the dvp-sma-dashboard-generator using official SMA EWI codes (SPRKCNTSCL*).
  Triggers: migrate scala spark, convert scala, scos scala migration,
  spark connect scala, scala compatibility, snowpark connect scala.
parent_skill: snowpark-connect
allowed-tools: Read, Write, Bash, Task
---

# Migrate Spark Scala to SCOS — Coordinator

Orchestrate a multi-phase migration of Spark Scala workloads to Snowflake SCOS (Snowpark Connect for Spark). This coordinator delegates work to specialist sub-agents and validates each phase with the deterministic `verify_phase.py` script before advancing.

## When to Load

[snowpark-connect] Intent Detection: After user indicates migration intent for Scala code (convert, migrate, update imports, rewrite for SCOS).

## Arguments

- `$ARGUMENTS` — Path to the Spark Scala file or directory to migrate

### Optional Metadata (from orchestrator)

| Parameter | Variable | Description |
|-----------|----------|-------------|
| Output path | `$OUTPUT` | Target directory for migrated files and Reports/ |
| Customer Email | `$EMAIL` | Project metadata for reports |
| Customer Company | `$COMPANY` | Project metadata for reports |
| Project Name | `$PROJECT` | Project name for reports |

If not provided, use `${ARGUMENTS}_scos` as output and prompt for metadata before the first consumer (the `project` name is needed by the Phase 1a assessment report; `email`/`company` by the Phase 4 CSVs).

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

## Workflow

You are a coordinator. You **NEVER** hand-write code fixes yourself — the judgment-heavy Phase 2 fixer is delegated to a specialist sub-agent via the `task()` tool. The deterministic phases (Phase 1 analysis, Phase 1a assessment render, Phase 3 imports/session/build/headers via `update_imports_scala.py`, Phase 4 reports) and **all** phase verification run as scripts you invoke directly — no sub-agent, no tokens. (`verify_phase.py` replaced the former LLM critic agents; `update_imports_scala.py` replaced the former import-updater specialist; Phases 1, 1a, and 4 call their generators directly because those generators are deterministic.) State is tracked in `migration_state.json`.

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

3. **(Optional) Unix-only shortcut inside the CoCo bash sandbox:**

   ```bash
   # Runs in the CoCo bash sandbox (Linux). Safe on any host OS.
   OUTPUT_ROOT="<$OUTPUT or ${ARGUMENTS}_scos>"
   TIMESTAMP=$(date +"%m-%d-%YT%H-%M-%S")
   CONVERSION="${OUTPUT_ROOT}/Conversion-SCOS-${TIMESTAMP}"
   mkdir -p "${CONVERSION}/Output" "${CONVERSION}/Reports" "${CONVERSION}/Logs"
   cp -r "$ARGUMENTS"/* "${CONVERSION}/Output/"
   ```

4. **Build the file manifest + notebook_index in one pass** — enumerate `.scala` source files, build files, AND every notebook format (`.ipynb`, Databricks-native `.python`/`.scala`/`.sql`, Databricks exported `.py`/`.scala`). <!-- SNOW-3383535: Sort by relative path for deterministic chunk boundaries -->

Call `orchestrate_phases.py --build-notebook-index` to walk the tree once and produce both the notebook metadata and the per-cell language histogram in a single pass. It uses `notebook_io.scan_and_parse_notebooks` internally, so every notebook is detected and parsed exactly once — no redundant tree walks, no double-parsing. The Scala source and build-file lists are gathered with a plain `os.walk` alongside. `notebook_io` has **zero third-party dependencies** (stdlib only), so invoke it directly with `python3` — do NOT wrap in `uv run --project`.

```bash
# First, write migration_state.json skeleton to <CONVERSION>/ (see step 7).
# Then build the combined manifest + notebook_index:
python3 <SKILL_DIRECTORY>/scripts/orchestrate_phases.py \
  --state <CONVERSION>/migration_state.json \
  --build-notebook-index <CONVERSION>/Output

# Plain-Scala sources (skipping native-JSON/exported-text .scala, which the
# notebook_index already covers) and build files:
python3 -c "
import json, os, sys
sys.path.insert(0, '<SKILL_DIRECTORY>/scripts')
import notebook_io as ni

root = '<CONVERSION>/Output'
# Prune VCS/IDE/build-output dirs at every depth (defense-in-depth; the copy
# step already excludes these, but a stray copy must never pollute the manifest).
EXCLUDE = {'.git', '.hg', '.svn', '.idea', '.vscode', '.metals', '.bloop',
           '.bsp', 'target', 'build', 'out', '.gradle', '__pycache__', 'node_modules'}

def walk(root):
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in EXCLUDE]  # prune in place
        yield dp, files

scala_files = []
for dp, files in walk(root):
    for f in files:
        if f.endswith('.scala'):
            p = os.path.join(dp, f)
            if not ni.is_notebook(p):
                scala_files.append(os.path.relpath(p, root))

# Collect ONLY real build files. Do NOT glob every .xml — that pulls in IDE
# library descriptors (.idea/libraries/*.xml), data/resource XML, and target
# artifacts. Maven build files are exactly pom.xml; sbt is any *.sbt; Gradle is
# the named build/settings scripts.
BUILD_NAMES = {'pom.xml', 'build.gradle', 'build.gradle.kts',
               'settings.gradle', 'settings.gradle.kts'}
build_files = []
for dp, files in walk(root):
    for f in files:
        if f.endswith('.sbt') or f in BUILD_NAMES:
            build_files.append(os.path.relpath(os.path.join(dp, f), root))

print(json.dumps({
    'scala_files': sorted(scala_files),
    'build_files': sorted(build_files),
}, indent=2))
"
```

The manifest for `migration_state.json` combines `scala_files` and every absolute path in the persisted `notebook_index`, sorted alphabetically. The index carries `format`, `language`, `rel_path`, and `code_cells_by_language` (per-language cell counts) for every notebook, so Phase 2 orchestration can size chunks without re-parsing.

4a. **Unpack .dbc archives** (if present): same unpack step as the Python sub-skill. After unpacking, re-run `orchestrate_phases.py --build-notebook-index` so the index picks up the new notebooks.

5. <!-- SNOW-3383536: Dispatch mode threshold -->
   **Determine dispatch mode**: Check manifest length against `DISPATCH_THRESHOLD` (default: 100).
   - If `len(manifest) <= 100`: set `coordinator_mode = false` — process all phases in the current agent context without sub-agent dispatch. This avoids coordinator overhead for small workloads.
   - If `len(manifest) > 100`: set `coordinator_mode = true` — use chunked sub-agent dispatch for Phase 2 (code fixes). Each chunk is sized by context budget estimation.

6. **Initialize git**:
```bash
cd <CONVERSION> && git init && git add . && git commit -m "Initial commit: source copied for SCOS migration" && git branch -M main
```

7. **Write `migration_state.json`** to `<CONVERSION>/`:
```json
{
  "phase": 0,
  "manifest": ["<relative paths for Scala sources AND notebooks, sorted alphabetically>"],
  "file_order": ["<relative paths sorted alphabetically — mirrors manifest order for auditability>"],
  "build_files": ["<list of build files>"],
  "notebook_files": {
    "ipynb":           ["<.ipynb files>"],
    "native_python":   ["<.python Databricks JSON files>"],
    "native_scala":    ["<.scala Databricks JSON files>"],
    "native_sql":      ["<.sql Databricks JSON files>"],
    "exported_python": ["<.py files with '# Databricks notebook source' header>"],
    "exported_scala":  ["<.scala files with '// Databricks notebook source' header>"]
  },
  "conversion_root": "<CONVERSION>",
  "migrated_dir": "<CONVERSION>/Output/",
  "skill_directory": "<SKILL_DIRECTORY>",
  "coordinator_mode": true,
  "dispatch_threshold": 100,
  "context_budget_tokens": 160000,
  "phases_completed": {},
  "recipe_edits": {},
  "metadata": {"email": "...", "company": "...", "project": "..."}
}
```

> **Note**: As phases complete, each entry under `phases_completed` will contain `processed_files` (done), `pending_files` (remaining), and `checkpoint_timestamp`. Non-empty `pending_files` after a specialist exits means it was interrupted — the coordinator must spawn a resume agent.

### Phase 0.5: Deterministic AST Pre-Processing (MUST RUN)

**This phase MUST run as the first deterministic step of every migration**,
after Phase 0 has populated `<MIGRATED>` with the source copy and before
the LLM analyzer in Phase 1 sees the code. It runs the AST-grade Scalafix
rules (`scripts/scalafix_rules/`, Scalameta `SyntacticRule`s) on every
`.scala` file in the manifest. This is the **sole** deterministic
pre-processing tier — the analogue of libcst for PySpark — and the regex
recipe tier (`recipes_scala/`) has been removed entirely.

**Databricks Scala notebooks.** Databricks `.scala` notebooks in the manifest
(both native JSON format and exported-text format with `// Databricks notebook source`)
are also processed. Each Scala code cell is extracted, wrapped in a minimal synthetic
`object` body so Scalafix can parse it as a valid compilation unit, processed by the
same rules (see `references/scala/recipes.md` for the full list), and the transformed content is written back into the notebook. The wrapper
is stripped from the output; only the cell content changes. Cell-level Scalafix failures
are non-fatal — that cell is left unchanged and the notebook's other cells continue.
This ensures all rules apply to notebook cells identically to plain source files.

**Why this exists:** the LLM fixer in Phase 2 is good at judgment-heavy
rewrites (UDFs, custom logic, ambiguous SQL) but historically dropped
mechanical details — the canonical example is silently losing
`SparkSession.builder().config("spark.sql.session.timeZone", "UTC")` when
collapsing the builder chain, which shifts every timestamp in the
migrated workload on machines with non-UTC JVM defaults. The Scalafix
rules solve those mechanical patterns byte-for-byte once, so the LLM can
spend its tokens on the genuinely hard stuff. Because they are
Scalameta-AST-aware they handle multi-line chains, string interpolation,
computed expressions, and chained-receiver forms that a regex pass cannot
match — with no comment/string false positives.

**Session-init rewriting (Phase 0.5, non-test files).** The `ScosSparkSessionBuilderRewrite` rule performs the full builder rename at the AST level: `SparkSession.builder` → `SnowparkConnectSession.builder()`, dropping `.master(...)`, `.enableHiveSupport()`, and `.remote(...)` from the chain. It also emits `SCOS-RECIPE-PRESERVED-CONFIG: k=v` markers for every `.config(k, v)` call so Phase 3 can re-materialize them after the Phase 2 LLM fixer has run. Test files (names ending in `Test/Spec/Suite.scala`) are left on `SparkSession` so local harnesses keep `master("local[*]")`.

**I/O detection (Phase 0.5).** `ScosSparkIoDetectAnnotate` annotates all Spark I/O call chains that require attention in SCOS: JDBC (`.format("jdbc")`/`.jdbc(...)`) → `[SPRKCNTSCL6000-Error]`; Iceberg (`.format("iceberg").load/save`) → `[SPRKCNTSCL3200-IO]`; table reads/writes (`.read.table(name)`/`.insertInto(name)`) → `[SPRKCNTSCL3200-IO]`. These are annotation-only (never rewrites) — the LLM fixer in Phase 2 resolves the concrete target. Cloud URI reads (`s3://`, `gs://`, …) and wildcard paths are handled by their own dedicated rules (`ScosExternalCloudReadAnnotate`, `ScosWildcardReadAnnotate`). The full rule set is documented in `references/scala/recipes.md`.

**Hard prerequisite (SBT + JVM):** Scala migrations are SBT/JVM projects,
so the AST runner is **mandatory, not best-effort**. You need `uv` (always)
plus **one of**: `sbt` + a JVM (preferred — every Scala project has this),
`scalafix-cli` on PATH, or Coursier (auto-bootstrapped). The runner is
resolved in that order. Pinned, verified versions: scala 2.12.20,
scalafix-cli 0.14.3. The first sbt resolve (or first `cs launch`) downloads
the Scala toolchain + scalafix once; subsequent runs are cached.

The driver is Python (already in `pyproject.toml`), so invoke it via `uv run`:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/preprocess_scalafix.py \
  --state <CONVERSION>/migration_state.json
echo "preprocess_exit=$?"
```

**Hard gate (all must be true):**

1. The script exits 0.
2. `migration_state.json["phases_completed"]["0_5b_scalafix"]["status"] == "passed"`.
3. A runner was resolved. **If no runner is available (no `sbt`+JVM, no
   `scalafix-cli`, no Coursier), the script exits 1 and records
   `status: "failed"` — this is a HARD failure, not a skip.** Do NOT advance
   to Phase 1: install `sbt` + a JVM and re-run.

If exit code is non-zero, do NOT advance to Phase 1. Re-read the error,
fix the underlying issue (a missing JVM/sbt runner, or an un-parseable
Scala file in `<MIGRATED>/`), and re-run the driver. The driver is
idempotent — running it again on already-rewritten files is a safe no-op.
If scalafix runs but fails on an individual plain file or notebook cell,
that item is logged in `failures` and processing continues — one bad file
does not abort the run, but a missing runner does.

Opt-outs (tune the runner; they do NOT make the phase optional):
- `--no-sbt` / `SCOS_SCALAFIX_USE_SBT=0` — disable the sbt runner.
- `--no-bootstrap-coursier` / `SCOS_BOOTSTRAP_COURSIER=0` — disable Coursier bootstrap.
- `--no-auto-launch` / `SCOS_SCALAFIX_AUTO_LAUNCH=0` — disable Coursier launch entirely.

**Write contract** (the driver records this for you; do not touch it
manually unless overriding):

```json
"phases_completed": {
  "0_5b_scalafix": {
    "status": "passed",
    "ran_at": "<ISO-8601 UTC>",
    "files_processed": <int>,        // plain .scala + notebooks with Scala cells
    "files_modified": <int>,
    "total_edits": <int>,
    "rules_run": ["ScosSparkSessionBuilderRewrite", "ScosCheckpointToCache", "..."],
    "notebooks_processed": <int>,    // present only when notebooks were in manifest
    "notebooks_modified": <int>
  }
}
```

Plus a top-level `recipe_edits` block keyed by relative path. For notebooks,
the `output_line_anchor` includes a `cell<N>` segment to identify the cell:

```json
"recipe_edits": {
  "<rel_path>.scala": [
    {
      "recipe_id": "scalafix:ScosSparkSessionBuilderRewrite",
      "src_line": <int>,
      "output_line_anchor": "scalafix:<RuleName>:<src_line>:<8-hex>"
    }
  ],
  "<notebook_path>.scala": [
    {
      "recipe_id": "scalafix:ScosCheckpointToCache",
      "src_line": <int>,
      "output_line_anchor": "scalafix:ScosCheckpointToCache:cell<N>:<src_line>:<8-hex>"
    }
  ]
}
```

The analyzer (Phase 1) and fixer (Phase 2) **MUST** read `recipe_edits` to
recognise AST-managed regions. These regions are already handled
deterministically: the analyzer MUST NOT re-flag them and the fixer MUST NOT
re-rewrite, collapse, or undo them (binding — see `agents/fixer.md`). The Phase 2
verifier enforces this by asserting every `SCOS-RECIPE-PRESERVED-CONFIG` pair is
still materialized.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 0.5: deterministic AST pre-processing (scalafix)"`

### Phase 1: Analysis

**Run the analyzer directly (no specialist agent)** — the coordinator runs `analyze_scala.py` itself instead of spawning a separate LLM analyzer sub-agent. Note the analyzer is **not** LLM-free: pattern *detection* is deterministic (AST facts when available, else regex + RAG retrieval), but compatibility *prediction* still issues batched Cortex `COMPLETE` calls (see `predict_compatibility_batch`). To keep that cost down the analyzer bypasses the LLM at both ends of the spectrum: blocks whose findings are **structurally-decidable failures** (exact unsupported import/format/module/Dataset API, or the `.rdd` gateway) are emitted deterministically (`source="trigger_decidable"`), and blocks that are **fully result-identical** (every method call on the shared `data/safe_apis.json` allowlist, no deterministic issue) are dropped without any RAG/LLM round-trip — only genuinely ambiguous blocks reach Cortex. The configured connection must therefore have `SNOWFLAKE.CORTEX.COMPLETE` access — if it is missing, Phase 1 fails with repeated retry/backoff, so confirm Cortex access before starting. "Deterministic orchestration" here means no second agent context and a fixed phase sequence — it does **not** mean reproducible output across model versions. (The 7 patterns the old analyzer agent re-scanned for in its "supplementation" step are now all detected natively by `analyze_scala.py` — including `za.co.absa.spline` — and the map-subscript form is handled by the Phase 0.5 scalafix rule, so no LLM supplementation pass is needed.)

**AST-facts detection (precision layer).** When a JVM/sbt toolchain is available, `analyze_scala.py` first extracts line-tagged Scalameta facts **once** over the whole workload via `scala_ast_facts.py` (which compiles and runs the `ScosMigrateFacts` extractor through the same pinned `scalafix_sbt` wrapper used by Phase 0.5). All detection categories — structural (unsupported imports/formats/Dataset APIs/no-op/UDF/RDD), behavioral differences, and Hive DDL — then run on those facts instead of regex-scanning raw block text, eliminating comment/string false-positives and handling multi-line constructs (the same precision PySpark gets from libcst). This is a *detection* pass only; it does not rewrite code. When no toolchain is present — or detection is disabled with `SCOS_NO_AST_FACTS=1` — the analyzer falls back to its regex detectors verbatim, so Phase 1 never hard-requires a JVM and the emitted issue rows are identical either way. In CI/production, add `--require-ast-facts` to fail (exit 3) if the extractor cannot compile or run — mirroring `--require-type-check` in Phase 2b. Omit it for best-effort local runs.

1. **Run the analyzer** using the offline trigger knowledgebase (`--rag-backend trigger`). This uses the curated `data/kb_rules.json` exact-match KB — no Cortex Search service or network endpoint needed, and risk scores are driven by curated severity rather than cosine similarity:
   ```bash
   uv run --project <SKILL_DIRECTORY> \
     python <SKILL_DIRECTORY>/scripts/analyze_scala.py \
     --path <MIGRATED> \
     --notebook-index <CONVERSION>/migration_state.json \
     --rag-backend trigger \
     --connection <SNOWFLAKE_CONNECTION> \
     --output <CONVERSION>/analysis.json
   ```
   `--notebook-index` skips per-candidate notebook-detection I/O for large workloads.
   Use `--output <file>` (not a `> analysis.json` shell redirect): the Snowflake
   connector may print auth/SSO banners to stdout that would corrupt a redirected
   JSON file. `--output` writes the JSON directly and implies JSON format.

2. **Cross-language notebooks:** inspect `migration_state.json :: notebook_index`. If any entry's `code_cells_by_language` has more than one of `{python, scala}`, ALSO run `analyze_pyspark.py` on the same inputs (same `--notebook-index` flag) and merge its output into the same `analysis.json` — each row carries a `language` field so the fixer and CELL_MODE pre-filter can distinguish Python-cell from Scala-cell issues. If no notebook is cross-language, skip the Python analyzer.

3. **Record the phase** in `migration_state.json`:
   ```json
   "phases_completed": { "1_analysis": {"status": "passed", "issues_found": <N>} }
   ```

> `agents/analyzer.md` is retained as human-readable reference for the analyzer flow; the coordinator now runs `analyze_scala.py` directly.

**Verify (deterministic)**: run `verify_phase.py --phase 1` — covers valid JSON, file coverage, blind-spot scan for UDFs/checkpoint/Catalyst/Hadoop/HWC/Spline, and risk-distribution sanity:

```bash
python3 <SKILL_DIRECTORY>/scripts/verify_phase.py \
  --phase 1 --language scala --strict \
  --state <CONVERSION>/migration_state.json
echo "verify_phase1_exit=$?"
```

**Gate**: exit 0 ⇒ `PASS` or `PASS_WITH_GAPS` (advisory gaps are printed but do not block). On exit 1 (`FAIL`), read the listed failing checks, re-run the analyzer with that feedback (max 2 retries), and re-run the verifier. Update `migration_state.json` phase to 1.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 1: analysis complete" && git tag -f phase-1-complete`

> The `phase-1-complete` tag is **required**: the Phase 2b compile gate reverts any file that fails to compile back to this tag. If the tag is missing, `revert_failing_scala_files.py` fails fast before doing any work.

### Phase 1a: Render Assessment Report

**Render directly (no specialist agent)** — `render_assessment.py` is deterministic, so the coordinator runs it itself. This produces a **pre-migration** readiness view for stakeholders from the Phase 1 `analysis.json` and the **original source** passed via `--workload-dir` (the user's untouched Spark code — not `<MIGRATED>`, which Phase 0.5 has already rewritten). "Before any fixes" means before the LLM fixer in Phase 2 (the same generator Phase 4 used to call, now rendered early to match the PySpark flow).

1. **Metadata:** `project` was collected in Phase 0 (`migration_state.json :: metadata`). Prompt the user only if it is missing.

2. **Readiness HTML + IR** (from the existing `analysis.json`; `--language scala`):
   ```bash
   uv run --project <SKILL_DIRECTORY> \
     python <SKILL_DIRECTORY>/scripts/assessment/render_assessment.py \
     --language scala --project "<project>" \
     --analysis-json <CONVERSION>/analysis.json \
     --workload-dir <original_source_path> \
     --output-html <CONVERSION>/Reports/MigrationReadinessReport.html \
     --dump-ir <CONVERSION>/Reports/AssessmentIR.json
   ```
   If `<original_source_path>` is unavailable, fall back to `--workload-dir <MIGRATED>`.

**Quality gate**: run the assessment-report gate (a deterministic, language-agnostic script):

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
- Exit `2` (`FAIL`) → re-run `render_assessment.py` with the gate's `gaps` array as feedback, then re-run the gate. Retry at most **3 times total**. If it still fails, **STOP and escalate to the user** — do NOT advance to Phase 2 with a missing or broken report. Record:
  ```json
  "phases_completed": {"1a_assessment_report": {"status": "skipped", "attempts": 3, "skip_reason": "<one-line reason>"}}
  ```
- Exit `3` (IO / usage error) → the gate could not read `migration_state.json` or the `Reports/` paths; re-rendering will NOT fix this. STOP and escalate immediately.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 1a: assessment report rendered"`

### Phase 2: Apply Fixes

<!-- SNOW-3385158: Orchestration moved to external script for deterministic dispatch -->
<!-- SNOW-3383536: Budget reduced to 80k tokens/chunk (aggressive mode) for guaranteed completion -->
**Pre-dispatch: Run External Orchestrator (PLAN ONLY)** — Compute budget-aware chunks and write the dispatch plan to `migration_state.json`. This step is **side-effect-free**: it does NOT modify any source files. (The deterministic fallback runs later, in Phase 2a, only after the fixers complete — running it now would generically transform the whole manifest before the fixer ever sees it.)

```bash
python3 <SKILL_DIRECTORY>/scripts/orchestrate_phases.py \
  --state <CONVERSION>/migration_state.json \
  --phase 2 \
  --budget 80000 \
  --max-parallel 6 \
  --language scala
```

`--max-parallel` is the fixer worker-pool width (default 6). The orchestrator
splits the manifest into at least `min(max_parallel, n_files)` budget-aware
chunks and groups them into **waves** of `max_parallel`. Lower it (e.g. `1`)
for fully sequential dispatch; raise it for more concurrency.

The script prints a structured **PHASE 2 DISPATCH PLAN**: a `MAX_PARALLEL=<n>` line, a `Waves` count, and for each wave a `========== WAVE k/N (dispatch these C chunk(s) IN PARALLEL) ==========` header followed by its chunks (`CHUNK_MODE`, `CHUNK_ID`, `CHUNK_FILES`). It ends with `PLANNING ONLY — no files were modified.` Read the plan and act on it wave-by-wave. Fallback is **not** run here.

Token formula: `file_tokens = file_chars // 4 + 2000` (characters ÷ 4 plus 2000 overhead per file). A single file that exceeds the budget on its own gets a dedicated chunk so it is never silently skipped.

**Dispatch fixers wave-by-wave (parallel worker pool)**: process waves in order. For **each wave**, spawn ALL of that wave's chunks' `agents/fixer.md` sub-agents **concurrently** — issue the `task()` calls in a **single turn** (one message with multiple tool calls), passing `CHUNK_MODE=chunked`, `CHUNK_ID=<n>`, `CHUNK_FILES=<files>`, and `PARALLEL_MODE=true` to each. The fixer reads `analysis.json`, loads `references/fix-rules.md` for the detailed Scala-specific rules, and applies fixes to its assigned file list.

> **You (the coordinator) are the single writer of `migration_state.json`.** In `PARALLEL_MODE=true`, workers must NOT write state (they would race) — each returns a `CHUNK_RESULT` line listing the files it completed. When the **whole wave** returns, update `migration_state.json` ONCE: append each reported file to `phases_completed["2_fixes"].files_done`, remove it from `pending_files`, and mark `chunks[i].status="done"`. Then git-checkpoint that wave before starting the next.

**Checkpoint detection**: after the last wave, read `migration_state.json`. If `phases_completed["2_fixes"]["pending_files"]` is non-empty, re-run `orchestrate_phases.py` — it recomputes chunks (and re-waves them) from the remaining files. Dispatch the new waves the same way. Repeat until `pending_files` is empty.

**Verify (deterministic)**: run `verify_phase.py --phase 2` — covers phase-2 orchestration (a multi-file workload must carry the orchestrator plan `max_parallel_fixers`/`phase2_chunks` in state, else the coordinator fixed inline and bypassed the worker pool), syntax artifacts, high-risk coverage, no-op over-annotation, stale cross-file refs, file count, no empty files, **preserved-config survival** (fixer must not undo any Phase 0.5 `SCOS-RECIPE-PRESERVED-CONFIG`), and **notebook coverage** (Scala notebooks get the same validity + artifact + high-risk-marker checks as `.scala` files). Compilation is **not** re-checked here — Phase 2b owns the authoritative compile gate:

```bash
python3 <SKILL_DIRECTORY>/scripts/verify_phase.py \
  --phase 2 --language scala --strict \
  --state <CONVERSION>/migration_state.json
echo "verify_phase2_exit=$?"
```

**Gate**: exit 0 ⇒ `PASS` or `PASS_WITH_GAPS`. On exit 1 (`FAIL`), re-run the fixer on the listed files with that feedback, then re-run the verifier. Update `migration_state.json` phase to 2. (Compilation correctness is enforced separately by the Phase 2b hard gate below.)

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 2: fixes applied"`

### Phase 2a: Coverage Verification and Deterministic Fallback

<!-- SNOW-3375304: Ensure 100% file coverage after Phase 2 -->
<!-- SNOW-3383533: Scala deterministic fallback — header + import annotations + session init + EWI -->
<!-- fallback runs HERE (post-fixer), not during planning -->
**Run the fallback hard gate — only now that the fixers have completed.** This is the deterministic safety net for any file the fixer sub-agents missed:

```bash
python3 <SKILL_DIRECTORY>/scripts/orchestrate_phases.py \
  --state <CONVERSION>/migration_state.json \
  --phase 2 --run-fallback \
  --language scala
```

Read the printed coverage report:

- If it reports `Coverage: 100%` — proceed to the compilation gate below.
- If it lists `MISSING` files — escalate to the user; files are absent even after fallback.

The fallback script applies deterministic transformations only to files the fixer did **not** record as done (`phases_completed["2_fixes"].files_done` / `pending_files`):
- Copies the original source to `Output/` if not already present
- Injects a SCOS migration header block comment (Scala `/* ... */` style)
- Annotates `org.apache.spark`, `com.databricks`, and `io.delta` imports with `// SCOS: [SPRKCNTSCL0099]` comments
- Replaces `SparkSession.builder()...getOrCreate()` with `SnowparkConnectSession.builder().getOrCreate()` in entry-point files and injects `import com.snowflake.snowpark_connect.client.SnowparkConnectSession` — the canonical SCOS Scala session form expected by the Phase 3 import-updater and the `verify_phase.py --phase 3` gate (it deliberately does **not** emit vanilla `SparkSession...remote()`, which that gate rejects)
- Appends a `SPRKCNTSCL0099` EWI entry to `analysis.json` for each fallback file

> If many files land in fallback, that signals a fixer/dispatch problem — investigate rather than treating the fallback output as a clean migration.

**Gate**: All manifest files must exist in `<MIGRATED>`. `migration_state.json` field `orchestrator_coverage_verified` is set to `true` by the orchestrator when coverage is 100%.

### Phase 2b: Compilation Verification Gate (MUST RUN)

<!-- SNOW-3379886: Hard gate ensuring 100% compilation after code fixes -->

**This phase MUST run after Phase 2a, on every workload, with no exceptions.**
Skipping it lets broken syntax ship to the customer's `Output/` directory. Even
single-file workloads must run the gate.

**Checklist** (do every step in order; do not skip steps):

- [ ] Run the compilation script below. Capture the final `fail_count` value
      **and the reported `compile_mode`**.
- [ ] For each `COMPILE_FAIL` line, the script reverts the file to its
      `phase-1-complete` tag state via `git show`.
- [ ] If `fail_count > 0`, re-dispatch `agents/fixer.md` on **only** the reverted
      files, then re-run the script. Repeat until `fail_count == 0` or you have
      iterated 3 times.
- [ ] Write to `migration_state.json`:
  ```json
  "phases_completed": {
    "2b_compilation": {
      "status": "passed",
      "fail_count_initial": <M>,
      "reverted_count": <N>,
      "iterations": <K>,
      "compile_mode": "<type_check | parse_only | tokenizer>",
      "classpath_used": "<jar path or null>"
    }
  }
  ```
  AND write the legacy top-level field for backward compat:
  ```json
  "compilation_reverted_count": <N>
  ```
- [ ] If you cannot run this phase for any reason (e.g. `<MIGRATED>` is empty,
      git checkpoint missing), set:
  ```json
  "phases_completed": {
    "2b_compilation": {
      "status": "skipped",
      "skip_reason": "<one-line reason>"
    }
  }
  ```
  and **STOP** — do not advance to Phase 3. Escalate to the user.

**Compilation script (portable across macOS / Linux / Windows):**

The `revert_failing_scala_files.py` helper checks every `*.scala` under
`<MIGRATED>` (`pathlib.rglob`, whitespace-safe) in one of three modes, best
first:

1. **`type_check`** — `scalac -classpath <snowpark-connect-java-client.jar> -Ystop-after:typer`.
   Catches the highest-value Scala error class: type mismatches and unresolved
   symbols introduced by Spark→SCOS API changes. Runs only when a working Scala
   compiler is available (on `PATH`, or resolved via Coursier with
   `--bootstrap-coursier`) **and** the client JAR is resolvable. The resolved
   compiler **and** the JAR are each smoke-tested on a trivial snippet before
   use, so a broken compiler or an incompatible JAR safely degrades the mode
   rather than mass-reverting good files against a bad toolchain.
2. **`parse_only`** — `scalac -Ystop-after:parser`. Catches syntax errors only;
   **type errors pass through silently.** Used when `scalac` is present but no
   JAR was found.
3. **tokenizer fallback** — brace/paren/string balance check, when no working
   `scalac` could be resolved.

When a check fails the file is reverted to `phase-1-complete` via `git show`.

**Enable `type_check` mode (do this — do not let it silently degrade):**
`type_check` needs two things — a working `scalac` and the full SCOS
**classpath** — and the script resolves both best-effort:

- **Compiler.** A `scalac` already on `PATH` is used as-is. Otherwise, pass
  `--bootstrap-coursier` (or set `SCOS_BOOTSTRAP_COURSIER=1`) to let the script
  launch `scalac` via Coursier — the same bootstrap path used by Phase 0.5. The
  first launch downloads a JVM + scala once (cached). Coursier use is **opt-in**:
  without the flag, behavior is unchanged on machines that lack `scalac`.
- **Classpath.** Real type-checking needs the SCOS client JAR **plus**
  `spark-connect-client-jvm` and its transitive deps (~38 JARs — that is what
  provides `org.apache.spark.sql.*`, the API the migrated code compiles against).
  A single client JAR alone only resolves `SnowparkConnectSession`, so it usually
  degrades to `parse_only`. With `--bootstrap-coursier`, the script
  **auto-resolves the whole classpath** (`cs fetch --classpath
  spark-connect-client-jvm_2.12:<spark> …` plus a direct download of the client
  JAR). Tune versions with `--spark-version` / `--scos-version`. You can also
  supply a classpath yourself via `--classpath`: a single JAR path, a full
  `os.pathsep`-joined classpath string, or `@FILE` to read one from a file.

> NOTE: the published `snowpark-connect-java-client` POM leaves
> `${scala.binary.version}` unsubstituted in its artifact filename, so a plain
> `cs fetch <coordinate>` of the client JAR fails. The script (and the recipe
> below) work around it by downloading the correctly named JAR directly from
> Maven Central.

Run the sweep — `--bootstrap-coursier` self-provisions both `scalac` and the
full classpath:

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/revert_failing_scala_files.py \
  --migrated <MIGRATED> \
  --phase-tag phase-1-complete \
  --bootstrap-coursier \
  --json
```

**Bounded compiler-feedback repair (do this before accepting any revert).** A
straight revert throws away a whole file for a trivial slip (a dropped bracket,
a missing `.asJava`) the LLM itself introduced. So give the fixer **one** shot at
its own compiler errors before reverting:

1. **Diagnose first** — run the gate with `--no-revert`. It compiles every file and
   emits `failures` plus a `diagnostics` map (`{file: scalac error text}`)
   **without** reverting anything:
   ```bash
   uv run --project <SKILL_DIRECTORY> \
     python <SKILL_DIRECTORY>/scripts/revert_failing_scala_files.py \
     --migrated <MIGRATED> --bootstrap-coursier --no-revert --json
   ```
   **Before doing anything else**, inspect the `diagnostics` values. If every
   error is a missing project-internal class or third-party library that was
   absent from the classpath *before* Phase 2 (e.g. `object utils is not a
   member of package`, `object udojava is not a member of package com`) —
   not a type error on a line the fixer touched — then all failures are
   pre-existing. Mark Phase 2b as `skipped` with the reason and advance to
   Phase 3. **Do not run the revert-enabled gate in this case.**
2. **Repair once** — for each file in `diagnostics` that has a genuine fixer
   regression (a type error on a line the fixer changed), re-invoke the Phase 2
   fixer on that file with its compiler error appended as feedback
   ("You broke this file. Here is the scalac error: …. Fix it."). This is a
   **single** bounded pass — do not loop.
   Note: files in `quarantined_manual` are unsupported-RDD (Bucket A) — do **not**
   try to repair them; they stay annotated for manual refactor.
3. **Gate + revert** — run the gate normally (no `--no-revert`). Anything that
   *still* fails to compile is now genuinely broken and is reverted to
   `phase-1-complete`.

The gate itself stays fully deterministic (no LLM inside it); the repair is the
orchestrator's job, exactly like the Phase 2 verifier re-run loop.

If you prefer to resolve the classpath once and reuse it (e.g. offline CI), build
a classpath file and pass it with `@`:

```bash
# Runs in the CoCo bash sandbox (Linux/macOS) — not portable to Windows cmd.exe/PowerShell.
CS=~/.cache/scos/coursier/cs   # or any cs/coursier on PATH
JAR=~/.cache/scos/jars/snowpark-connect-java-client_2.12-1.0.0.jar
mkdir -p "$(dirname "$JAR")"
curl -sSf -o "$JAR" \
  https://repo1.maven.org/maven2/com/snowflake/snowpark-connect-java-client_2.12/1.0.0/snowpark-connect-java-client_2.12-1.0.0.jar
DEPS=$("$CS" fetch --classpath org.apache.spark:spark-connect-client-jvm_2.12:3.5.6 org.slf4j:slf4j-api:2.0.16)
echo "$JAR:$DEPS" > ~/.cache/scos/scos_typecheck_classpath.txt
# then: ... revert_failing_scala_files.py --classpath @$HOME/.cache/scos/scos_typecheck_classpath.txt --bootstrap-coursier --json
```

**Production / CI — enforce the strongest gate:** add `--require-type-check` to
make the script **exit 3** if it cannot run in `type_check` mode (missing
compiler or classpath). This turns silent degradation into a loud failure so the
compile gate — not the LLM fixer — is the authoritative backstop. Use it once
you have confirmed the toolchain resolves; omit it for best-effort local runs.

Exit code is the final `fail_count` (capped at 255; `3` is reserved for the
`--require-type-check` enforcement failure above). The JSON payload reports
`fail_count`, `failures`, `reverted`, `quarantined_manual`, `scalac_available`,
`compile_mode` (`type_check` | `parse_only` | `tokenizer`), `compile_strategy`,
`classpath_used`, and `target_dirs_removed`. Read `compile_mode` — if it is
`parse_only` or `tokenizer`, type errors were **not** caught; record that in the
state block and warn the user that runtime validation (Phase 5) is the only
remaining type-correctness backstop.

`quarantined_manual` lists files that failed to compile **only** because they
carry a Bucket-A unsupported-RDD marker (`// SCOS: [SPRKCNTSCL1500] … manual
refactor required`). These are **not** reverted and **not** counted in
`fail_count` — RDD APIs have no SCOS equivalent (no client-side RDD), so the
original code is equally broken and a revert would just erase the annotation.
Surface them to the user as **manual-intervention** items (see
`../../references/scala/rdd-conversion.md`), not as migration failures.

**Hard gate (all of the following MUST be true to advance to Phase 3):**

1. Final `fail_count == 0` after the last iteration.
2. `migration_state.json["phases_completed"]["2b_compilation"]["status"] == "passed"`.
3. The legacy field `migration_state.json["compilation_reverted_count"]` is also set.

If any of these is false, do NOT advance. Either re-iterate or mark `skipped`
with a reason and escalate.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 2b: compilation gate passed (reverted_count=<N>)"`

### Phase 3: Imports, Session, Build, and Headers

**Run the import-updater directly (no specialist agent)** — every action of this phase is mechanical (rename the session builder, drop unsupported imports, materialize preserved config, transform build files, stamp a header), so the coordinator runs the deterministic `update_imports_scala.py` itself instead of spawning an LLM specialist. This replaces the former `agents/import-updater.md` LLM specialist, mirroring how `verify_phase.py` replaced the LLM critic agents. This is the Scala counterpart of PySpark's `update_imports.py` (which likewise replaced PySpark's former `agents/import-updater.md`).

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/update_imports_scala.py \
  --state <CONVERSION>/migration_state.json
echo "update_imports_scala_exit=$?"
```

What it does for every manifest file (and Scala cells in notebooks): injects the `SnowparkConnectSession` import, materializes `// SCOS-RECIPE-PRESERVED-CONFIG: k=v` markers (emitted by Phase 0.5) into `.config("k","v")` on the builder, removes unsupported import lines, transforms `build.sbt`/`pom.xml`/`build.gradle`/`build.gradle.kts` (snowpark-connect-java-client + `--add-opens` flags, removing `spark-connect-client-jvm`/`spark-hive`), and prepends an idempotent SCOS migration header. The `SparkSession` → `SnowparkConnectSession` rename and the `.master()`/`.enableHiveSupport()`/`.remote()` drops were already done by the Phase 0.5 `ScosSparkSessionBuilderRewrite` Scalafix rule; Phase 3 repeats those steps only as a fallback when Phase 0.5 did not run (no JVM/sbt toolchain). Test files (`*Spec/Test/Suite`) keep `master("local[*]")` and are left on `SparkSession` with a TODO.

> **Maven version pinning**: Maven has no safe dynamic-version keyword, so when the concrete `snowpark-connect-java-client` version is unknown the script emits a `PIN_CONCRETE_VERSION` placeholder + a `SCOS: TODO`. The Phase-3 gate then FAILs on that placeholder by design — a human must pin the version. sbt/Gradle use the valid `latest.release` and pass automatically.

**Verify (deterministic)**: run `verify_phase.py --phase 3` — covers migration header, session init replacement, `SnowparkConnectSession` present, no unsupported imports, build files transformed, syntax artifacts, file count, and recipe-preserved-config materialization:

```bash
python3 <SKILL_DIRECTORY>/scripts/verify_phase.py \
  --phase 3 --language scala --strict \
  --state <CONVERSION>/migration_state.json
echo "verify_phase3_exit=$?"
```

**Gate**: exit 0 ⇒ `PASS` or `PASS_WITH_GAPS`. On exit 1 (`FAIL`), address the listed failures (e.g. pin a Maven version) and re-run the verifier. Update `migration_state.json` phase to 3.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 3: imports, session, build, and headers updated"`

### Phase 4: Generate Reports

**Generate the dashboard CSVs directly (no specialist agent)** — the CSV generator is deterministic and always emitted, so the coordinator runs it itself. The readiness HTML + IR were already rendered pre-fix in **Phase 1a** and are **not** regenerated here.

1. **Metadata:** `project`/`email`/`company` were collected in Phase 0 and live in `migration_state.json :: metadata`. Only if they are missing, prompt the user for them now (the coordinator is the right place for user interaction).

2. **CSV reports:**
   ```bash
   uv run --project <SKILL_DIRECTORY> \
     python <SKILL_DIRECTORY>/scripts/generate_scos_reports.py \
     --output-dir <CONVERSION> --analysis <CONVERSION>/analysis.json \
     --source-dir <original_source_path> --migrated-dir <MIGRATED> \
     --project-name "<project>" --email "<email>" --company "<company>" \
     --language scala
   ```
   Produces `Reports/{Issues,InputFilesInventory,ArtifactDependencyInventory}.csv`.
   Also annotates migrated source files inline: every `// SCOS:` comment gets its
   EWI code embedded (`// SCOS: [SPRKCNTSCL…] …`) via `annotate_scos_markers` —
   no separate bridge step is required.
   In `InputFilesInventory.csv`, only source code and build files are conversion
   units (`Ignored == "False"`); data/resource files (CSV, JSON, Parquet, txt, …)
   are inventoried but marked `Ignored == "True"` so they are not counted as
   migration work (code-vs-data split).

3. **Record the phase:** `"phases_completed": { "4_reports": {"status": "passed"} }`.

> `agents/reporter.md` is retained as human-readable reference for the report flow; the coordinator now runs the generator directly. The `MigrationReadinessReport.html` + `AssessmentIR.json` are produced in **Phase 1a**, not here.

**Verify (deterministic)**: run `verify_phase.py --phase 4` — covers all three CSVs present, InputFilesInventory row count, Issues.csv columns, and `SPRKCNTSCL` prefix:

```bash
python3 <SKILL_DIRECTORY>/scripts/verify_phase.py \
  --phase 4 --language scala --strict \
  --state <CONVERSION>/migration_state.json
echo "verify_phase4_exit=$?"
```

**Gate**: exit 0 ⇒ `PASS` or `PASS_WITH_GAPS`. On exit 1 (`FAIL`), re-run the reporter, then re-run the verifier. Update `migration_state.json` phase to 4.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 4: reports generated"`

### Phase 4a: Post-Run State Validation (MUST RUN)

**This phase MUST run as the last deterministic step of every migration.** It
asserts that every required phase (0.5, 1, 2, 2a, 2b, 3, 4) recorded evidence in
`migration_state.json` — either via the canonical `phases_completed[<key>]`
block or via the documented legacy top-level field. Silent skips become loud
failures here, before the user is offered validation.

The validator script is pure stdlib (no third-party deps), so invoke it
directly with `python3` — no `uv run` needed:

```bash
python3 <SKILL_DIRECTORY>/scripts/validate_migration_state.py \
  --strict \
  --language scala \
  --state <CONVERSION>/migration_state.json
echo "validator_exit=$?"
```

**Hard gate (all must be true):**

1. The script exits 0 (no required phase missing or skipped without reason).
2. The printed report shows `PASS: all required phases present.`.

The required phase set for Scala is:
`{0_5b_scalafix, 1_analysis, 1a_assessment_report, 2_fixes, 2a_fallback, 2b_compilation, 3_imports, 4_reports}`.

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
cannot confirm Phase 4a actually executed without parsing the transcript.

For machine-readable output (e.g. when wrapping in CI), pass `--json` instead
of the default human report.

**Git checkpoint**: `cd <CONVERSION> && git add -A && git commit -m "Phase 4a: validation passed"`

### Phase 5: Offer Validation (Optional)

Ask the user:
```
Migration complete! Would you like to validate the migrated workload
by running it end-to-end with synthetic data?
```

If yes, load `validate-spark-scala-to-snowpark-connect/SKILL.md` with `<MIGRATED>` as `$ARGUMENTS`.

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
- Phase 2: If `verify_phase.py --phase 2` fails after 2 retries — escalate to user with specific errors
- Phase 5: After migration completes — ask user about validation

## Success Criteria

- `scripts/validate_migration_state.py --strict --language scala` exits 0 (this is the
  canonical, machine-checkable success criterion — see Phase 4a)
- `migration_state.json` shows all phases 1-4 completed and verified
- `Reports/Issues.csv` exists with data rows
- `Reports/InputFilesInventory.csv` code-row count (conversion units, `Ignored == "False"`) matches the manifest
- `Reports/MigrationReadinessReport.html` and `Reports/AssessmentIR.json` exist
- All `.scala` files pass the Phase 2b compile gate — `scalac -Ystop-after:typer` (when the SCOS client JAR is resolvable), else `-Ystop-after:parser`, else tokenizer fallback; the mode used is recorded in `phases_completed.2b_compilation.compile_mode`
- Every `.scala` file has a migration header block comment
- Build files actively transformed (Scala 2.12+, Spark 3.5+, `com.snowflake:snowpark-connect-java-client` added)
- File count matches between original and migrated directories

## Output

```
<output_root>/
  Conversion-SCOS-<timestamp>/                       ← <CONVERSION>
    Output/                                          ← <MIGRATED> — converted files
    Reports/
      Issues.csv                                     ← EWI issues (SPRKCNTSCL*)
      InputFilesInventory.csv                        ← Source file inventory
      ArtifactDependencyInventory.csv                ← Import dependencies
      MigrationReadinessReport.html                  ← Stakeholder-facing readiness report
      AssessmentIR.json                              ← Structured IR (stable contract)
    Logs/                                            ← Migration log
    migration_state.json                             ← Phase gate tracking
    analysis.json                                    ← Compatibility analysis
```

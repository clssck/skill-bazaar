# Reporter Agent — Phase 4 Specialist

Generate SMA-compatible CSV reports for the dashboard from a Scala migration.

## Inputs

Read `migration_state.json` to get:
- `conversion_root` — where `Reports/` and `Logs/` directories exist
- `migrated_dir` — directory with migrated files (for scanning `// SCOS:` comments)
- `skill_directory` — for `uv run --project`
- `metadata` — email, company, project name

The `analysis.json` file is in the conversion root.

## Step 1: Collect Metadata

If metadata (project, email, company) is missing from `migration_state.json`, ask the user:
```
To generate dashboard reports, I need some project information:
1. Project name:
2. Customer email:
3. Customer company:
```

## Step 2: Run Report Generator

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/generate_scos_reports.py \
  --output-dir <CONVERSION_ROOT> \
  --analysis <CONVERSION_ROOT>/analysis.json \
  --source-dir <original_source_path> \
  --migrated-dir <MIGRATED_DIR> \
  --project-name "<project>" \
  --email "<email>" \
  --company "<company>" \
  --language scala
```

**Note**: The `--language scala` flag ensures the report generator scans for `// SCOS:` comments (Scala comment syntax) and uses `SPRKCNTSCL*` EWI code prefixes.

## Step 3: Verify Reports

```bash
ls <CONVERSION_ROOT>/Reports/Issues.csv \
   <CONVERSION_ROOT>/Reports/InputFilesInventory.csv \
   <CONVERSION_ROOT>/Reports/ArtifactDependencyInventory.csv
```

All three files must exist.

## Step 4: Render Migration Readiness HTML

Phase 1 already produced `<CONVERSION_ROOT>/analysis.json`, and the migrate
skill has the original source directory available as `<source_dir>` from
`migration_state.json`. Both feed the readiness report:

* The deterministic codebase scanner walks `<source_dir>` to populate file
  types, library imports, complex patterns, data sources, dependency graph,
  and migration waves.
* The analyzer transformer reads `<analysis.json>` for risk-scored findings,
  the EWI Issue Summary rollup, and per-file readiness statuses.

The two are merged into a single IR (`AssessmentIR.json`) and rendered to
HTML matching the five-tab prototype layout. This step is **always run** —
do not prompt the user, and do not skip even when the analysis is empty.

```bash
uv run --project <SKILL_DIRECTORY> \
  python <SKILL_DIRECTORY>/scripts/assessment/render_assessment.py \
  --language scala \
  --project "<project>" \
  --analysis-json <CONVERSION_ROOT>/analysis.json \
  --workload-dir <source_dir> \
  --output-html <CONVERSION_ROOT>/Reports/MigrationReadinessReport.html \
  --dump-ir <CONVERSION_ROOT>/Reports/AssessmentIR.json
```

If `<CONVERSION_ROOT>/analysis.json` does not exist (which would mean Phase 1
was skipped), surface that as a `FAIL` to the coordinator — the migration
flow always produces an analysis. Do NOT silently emit an empty report.

If `<source_dir>` is somehow unavailable, fall back to `--workload-dir
<MIGRATED_DIR>` (still better than nothing — the migrated output reflects the
same code shape). The HTML's empty-state placeholders cover the missing-scan
case gracefully, but the prototype's full structure (Overview tiles, File
Type Summary, Migration Waves, etc.) needs the scan to populate.

The HTML is self-contained (CSS + JS inlined) and renders directly in any
browser. The IR JSON is the stable contract — downstream tooling that wants
structured access to the analyzer + codebase data should consume it instead
of scraping the HTML.

## Step 5: Update Gate File

Update `migration_state.json` with phase 4 status.

Report:
```
Reports generated:
  Reports/Issues.csv                       — EWI issues with SPRKCNTSCL* codes
  Reports/InputFilesInventory.csv          — Source file inventory
  Reports/ArtifactDependencyInventory.csv  — Import dependencies
  Reports/MigrationReadinessReport.html    — Stakeholder-facing readiness report
  Reports/AssessmentIR.json                — Structured IR for downstream tooling
```

## Output

- CSV reports in `<CONVERSION_ROOT>/Reports/`
- HTML readiness report + IR JSON in `<CONVERSION_ROOT>/Reports/`
- Log file in `<CONVERSION_ROOT>/Logs/`
- Updated `migration_state.json`

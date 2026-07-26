---
name: snowpark-connect
description: |
  Snowpark Connect (SCOS) skills for migrating and validating PySpark and Spark Scala workloads on Snowflake.
  Generates SMA-compatible reports (Issues.csv, InputFilesInventory.csv, ArtifactDependencyInventory.csv)
  using EWI codes (SPRKCNTPY* for Python, SPRKCNTSCL* for Scala) for use with dvp-sma-dashboard-generator.
  Use when: migrating PySpark or Spark Scala to Snowpark Connect, validating SCOS migrations,
  analyzing Spark compatibility, or working with Snowpark Connect for Spark.
  Triggers: snowpark connect, scos, pyspark migration, spark connect, scala spark migration,
  validate migration, pyspark compatibility, scala compatibility.
---

# Snowpark Connect

> **Bundled sub-skill of `spark-migration`.** This SKILL.md is loaded
> on-demand by the parent `spark-migration` skill via the Read tool
> (see its "Sub-skill Loading Convention" section) — it is **not**
> registered as a standalone top-level skill in the Cortex Code skill
> registry, by design, to avoid trigger collisions with its parent.
> Do not call `skill("snowpark-connect")`; if you reached this file
> outside of a `spark-migration` flow, start at `spark-migration` instead.

Skills for working with Snowpark Connect for Spark (SCOS) on Snowflake — supports Python and Scala workloads.

## When to Use

- User wants to migrate PySpark, Databricks, or Spark Scala code to Snowflake
- User asks about SCOS or Snowpark Connect compatibility
- User wants to validate a completed SCOS migration
- User mentions "spark connect", "scos", or "snowpark connect"

## Intent Detection

Determine the **language** and **action** from the user request, then route to the correct sub-skill:

```
Start
  ↓
Analyze User Request
  ↓
Detect Language
  ├─→ Python (.py, PySpark, Databricks, pyspark)
  │     ├─→ Migration intent → Load migrate-pyspark-to-snowpark-connect/SKILL.md
  │     └─→ Validation intent → Load validate-pyspark-to-snowpark-connect/SKILL.md
  │
  ├─→ Scala (.scala, Spark Scala, build.sbt)
  │     ├─→ Migration intent → Load migrate-spark-scala-to-snowpark-connect/SKILL.md
  │     └─→ Validation intent → Load validate-spark-scala-to-snowpark-connect/SKILL.md
  │
  └─→ Ambiguous → Ask the user which language the workload uses
```

### Step 1: Detect Language

Determine the source language from:
- **Explicit mention**: "PySpark", "Python Spark", "Scala Spark"
- **File extensions**: `.py` → Python; `.scala` → Scala
- **Import patterns**: `from pyspark` / `import pyspark` → Python; `import org.apache.spark` with `.scala` → Scala
- **Build files**: `requirements.txt` / `pyproject.toml` → Python; `build.sbt` → Scala
- **Notebook primary language + cell distribution** (for notebook workloads):
  - For every notebook found by `notebook_io.scan_notebooks`, combine the
    notebook's primary `language` with a per-cell language count obtained from
    `notebook_io.parse_notebook`.
  - The **dominant language across all code cells** in the workload picks the
    migration sub-skill. Cells in the minority language are handled via
    per-cell delegation at fixer time (see below).

If the language cannot be determined, ask the user:
```
I detected Spark code in your workload. Which language is it written in?
- Python (PySpark / Databricks)
- Scala (Spark Scala)
```

## Supported Notebook Formats

Both migration sub-skills process the following notebook formats natively via
the shared `scripts/notebook_io.py` module — no `jupyter nbconvert` required:

| Extension | Format                       | Notes                                         |
|-----------|------------------------------|-----------------------------------------------|
| `.ipynb`  | Standard Jupyter JSON        | Typically pretty-printed; kernel language in metadata |
| `.python` | Databricks native JSON       | Python-primary; `commands[]` array            |
| `.scala`  | Databricks native JSON       | Scala-primary; first byte `{`                 |
| `.scala`  | Databricks exported text     | First line `// Databricks notebook source`    |
| `.sql`    | Databricks native JSON       | SQL-primary; routed to whichever language has more code cells |
| `.py`     | Databricks exported text     | First line `# Databricks notebook source`     |

`.dbc` archives are automatically unpacked in Phase 0 and their contents flow
through the same scanner.

## Cross-Language Delegation

Databricks notebooks routinely mix languages via `%python`, `%scala`, `%sql`
magic lines. When the fixer in one sub-skill encounters a cell whose
`cell_language` differs from the sub-skill's primary language, it delegates
the single cell to the sibling sub-skill's fixer via `task()` in
`CELL_MODE=true` — the delegated agent returns the transformed cell source as
text, and the caller splices it back into the notebook. Markdown, SQL, R,
shell, FS, and `%run` cells are left untouched.

See `migrate-*/agents/fixer.md` — "Cross-Language Delegation" and
"CELL_MODE" sections — for protocol details.

## Phase 6 Handoff (Standalone Mode Only)

After a successful migration in **standalone** invocation (not via the
`snowflake-migration` orchestrator), each sub-skill offers an optional
handoff to `snowflake-notebook-migration` to convert the migrated notebooks
to Snowflake Workspace `.ipynb` format. The offer is skipped entirely when:

- the invocation context carries `snowpark_connect_invoker: orchestrator`, or
- the `snowflake-notebook-migration` skill is not installed (in which case an
  informational note is printed and the sub-skill exits cleanly).

### Step 2: Route by Intent

**Migration intent** — keywords: migrate, convert, rewrite, update imports, move to SCOS
**Validation intent** — keywords: validate, verify, check, test, review migration

### Route: Migrate PySpark to Snowpark Connect

**If user wants to migrate Python Spark code:**
- **Load** `migrate-pyspark-to-snowpark-connect/SKILL.md`
- Follow the migration workflow
- Uses EWI codes: `SPRKCNTPY*`
- References: `references/python/`

### Route: Migrate Spark Scala to Snowpark Connect

**If user wants to migrate Scala Spark code:**
- **Load** `migrate-spark-scala-to-snowpark-connect/SKILL.md`
- Follow the migration workflow
- Uses EWI codes: `SPRKCNTSCL*`
- References: `references/scala/`

### Route: Validate a PySpark Migration

**If user wants to validate a completed Python migration:**
- **Load** `validate-pyspark-to-snowpark-connect/SKILL.md`
- Follow the validation workflow

### Route: Validate a Spark Scala Migration

**If user wants to validate a completed Scala migration:**
- **Load** `validate-spark-scala-to-snowpark-connect/SKILL.md`
- Follow the validation workflow

## Cross-Platform Compatibility

Every command this skill surfaces to the user runs on **macOS, Linux, and
Windows**. Follow the authoring rules in
[`skill_development/references/cross-platform.md`](../../../skill_development/references/cross-platform.md)
— specifically:

- **Primary entry point for every script: `uv run --project <SKILL_DIRECTORY> python <SKILL_DIRECTORY>/scripts/<name>.py`.**
  No `chmod`, no `source`, no activation — `uv` handles the venv on every OS.
- **Dual-install snippets for `uv` bootstrap** (see each `migrate-*`
  sub-skill's *uv Package Manager* section): show both the macOS/Linux
  `curl -LsSf … | sh` and the Windows PowerShell `irm … | iex` forms.
- **No user-facing Unix-only constructs**: `date +…`, `mkdir -p`,
  `cp -r`, `find -print0`, `xargs`, `$(…)` command substitution, raw
  `/tmp/` or `~/` paths. Use the portable Python helpers under `scripts/`
  instead:
  - `scripts/prepare_conversion_dirs.py` — timestamped folder + source copy + `.dbc` unpack
  - `scripts/revert_failing_files.py` — Phase-2 compile gate + git-revert + `__pycache__` cleanup
  - `scripts/run_scos_migration.py` — portable wrapper that ensures
    `generate_scos_reports.py` runs even when the migration agent is
    interrupted mid-workflow (replaces the deprecated `.sh`
    equivalent).
- **Sandbox-only bash is explicitly marked** with a comment
  `# Runs in the CoCo bash sandbox (Linux) — not portable` so readers
  know not to copy it into Windows `cmd.exe` or PowerShell.

When authoring new scripts or phases in this skill, pick the Python
helper-script pattern first. Fall back to the in-sandbox bash form only
when the work is genuinely bound to the CoCo Linux sandbox and rewriting
in Python would add disproportionate complexity — and even then, mark
the block with the sandbox comment above.

## Stopping Points

None — this skill routes to sub-skills. Stopping points are defined within each sub-skill.

## Output

Output is determined by the loaded sub-skill:
- **Python Migration**: Migrated `_scos` files with compatibility fixes, migration headers, and SCOS-compatible dashboard reports (`Reports/Issues.csv`, `Reports/InputFilesInventory.csv`, `Reports/ArtifactDependencyInventory.csv`) using `SPRKCNTPY*` codes
- **Scala Migration**: Migrated `_scos` files with compatibility fixes, migration headers, and SCOS-compatible dashboard reports using `SPRKCNTSCL*` codes
- **Validation**: Validation report with pass/fail status for each check

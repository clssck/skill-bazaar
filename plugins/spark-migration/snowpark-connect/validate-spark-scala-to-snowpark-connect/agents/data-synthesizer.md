# Data Synthesizer

Loaded by `SKILL.md`. This agent has two paths:

1. full flow: no user-approved `entrypoints[]` exist yet — survey the
   workload, ask the user to choose entrypoints, record the selection,
   then continue straight into deep analysis in the same dispatch
2. deep-analysis refresh: `entrypoints[]` already exists in `analysis.json`

Keep the output simple and scoped to the validation workflow.

## Inputs

- `CONVERSION_ROOT`
- `SKILL_DIRECTORY`

Derived paths:

- `VALIDATION_ROOT = <CONVERSION_ROOT>/Validation`
- `SOURCE_ROOT     = Validation/source`
- `MIGRATED_ROOT   = <CONVERSION_ROOT>/Output`
- `SHARED_DIR      = Validation/shared`
- `MOCK_DATA_DIR   = Validation/shared/mock_data`
- `AUXILIARY_DIR   = Validation/shared/auxiliary`

## Survey Mode

Run this path when `analysis.json` does not yet have a selected
`entrypoints[]` list.

### Goals

1. Build `entrypoint_candidates[]`.
2. Discover `source_roots[]`.
3. Detect the build tool used by the workload.
4. Copy unresolved migrate-skill issues into `migration_issues[]`.
5. Ask the user to choose entrypoints.
6. Record the selection and continue directly into deep analysis.

### Entrypoint candidates

Treat a `.scala` file or directory as a candidate when it looks like a
workload entrypoint:

- `object X { def main(args: Array[String]): Unit = ... }` — standard
  Scala main object
- `object X extends App { ... }` — App trait entrypoint
- `object X extends DelayedInit` — scopt-style CLI driver
- Databricks `.scala` notebook markers (`// Databricks notebook source`,
  `// COMMAND ---------`)
- Databricks exported Python/Scala `.ipynb` notebooks with `"language":"scala"`
- Files containing `SparkSession.builder` or
  `SnowparkConnectSession.builder` at top level
- Job/pipeline-named paths: `*Pipeline.scala`, `*Job.scala`, `*Driver.scala`

> **Use the deterministic `analyze` command first.** Instead of eyeballing
> source for entrypoints/reads/writes, run the control-plane parser and reason
> over its facts:
>
> ```bash
> java -jar "$SKILL_DIRECTORY/harness-scala/control/target/scos-analyze.jar" \
>   analyze --source "$SOURCE_ROOT" --output "$SHARED_DIR/ast_facts.json"
> ```
>
> Immediately materialize the survey skeleton from those facts (do not hand-build
> `entrypoint_candidates[]` from scratch):
>
> ```bash
> uv run --project $SKILL_DIRECTORY/.. python \
>   $SKILL_DIRECTORY/scripts/ast_to_analysis.py --conv-root $CONVERSION_ROOT --mode survey
> ```
>
> (`analyze` is the only command still on the JVM — it needs a real Scala parser
> (Scalameta); there is no equivalent in Python. All state, Snowflake, and
> compare commands reuse the canonical PySpark validator scripts at
> `$VALIDATOR_SCRIPTS` (`scos_state.py`, `scos_state.py provision`/`cleanup.py`,
> `harness/comparator.py compare` looped per table).)
>
> `ast_facts.json` lists, per file: `objects`/`classes`, `entrypoints`
> (objects/classes with a `main`/`run` method), `imports`,
> `spark_session_created`, `reads` (`parquet`/`csv`/`json`/`load`/`table`/...),
> `writes` (`save`/`saveAsTable`/`insertInto`/format terminals), `table_refs`,
> and `column_refs` (`col("x")` / `$"x"`, plus the string args of
> `select`/`groupBy`/`orderBy`/`sort`/`sortBy`/`drop`/`dropDuplicates`), and
> `write_helpers` (functions whose body writes a DataFrame, **including
> transitively** — a function that delegates to a writer, e.g.
> `writeToSchema → fullLoad → .write.saveAsTable`). Use
> these as ground truth for
> candidate discovery, external sources, and sink targets; reserve LLM
> judgement for *semantics* (which source matters, schema inference, mock data)
> rather than re-parsing Scala by hand. **A call to any `write_helpers` name from
> an entrypoint is a sink** — declare it in `sinks[]` even though the actual
> `.write` is several calls away (delegating data-mart entrypoints otherwise look
> like they have no write targets). `parse_ok=false` entries flag files the
> parser could not read (e.g. raw Databricks notebooks before flattening).

For each candidate, emit:

```json
{
  "id": "relative_path_slug",
  "path": "relative/path.scala",
  "kind": "scala_object | extends_app | notebook | sbt_project",
  "entry_kind": "entrypoint_main | entrypoint_utility | library | passthrough",
  "call": "com.example.MyObject::main",
  "rationale": "why this looks like an entrypoint"
}
```

Do not emit extra viability scoring or auto-selection metadata.

### Source roots and build tool

Detect the build tool by presence of:
- `build.sbt` → `sbt`
- `pom.xml` → `maven`
- `build.gradle` / `build.gradle.kts` → `gradle`
- None of the above → `unknown`

Discover the minimal source roots needed for the harness to compile the
workload JAR. Standard layouts:

- sbt: `src/main/scala`, `src/main/java`
- Maven: `src/main/scala`, `src/main/java`
- Gradle: `src/main/scala`, `src/main/java`
- Flat: `.` (single-file workloads)

Record `build_tool` and `source_roots[]` in `analysis.json`.

### Migration issues

If `<CONVERSION_ROOT>/analysis.json` exists, copy unresolved migration
issues into `migration_issues[]` in the validation analysis.

### Survey output

Write `Validation/shared/analysis.json` with:

```json
{
  "entrypoint_candidates": [...],
  "source_roots": [...],
  "build_tool": "sbt | maven | gradle | unknown",
  "migration_issues": [...]
}
```

Then record:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  record-milestone --conv-root $CONVERSION_ROOT --milestone synth_survey
```

### Ask the user to choose entrypoints

Present the candidate list and ask the user which entrypoints to validate.
Default guidance:

- recommend a batch of up to 10,
- prefer business-critical or representative entrypoints first,
- split very large workloads into multiple validation runs.

After the user responds, record the selection:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  select-entrypoints --conv-root $CONVERSION_ROOT --ids <comma-separated-ids>
```

Then build the deep-analysis skeleton deterministically before LLM judgement:

```bash
uv run --project $SKILL_DIRECTORY/.. python \
  $SKILL_DIRECTORY/scripts/ast_to_analysis.py --conv-root $CONVERSION_ROOT --mode deep
```

Resolve only the `llm_todo` items the skeleton flagged (type confirmation,
`natural_keys`, ambiguous column attribution, non-relational document schemas).
Then continue straight into deep analysis in the same dispatch.

## Deep Analysis Mode

Run this mode after `analysis.json["entrypoints"]` is populated.

Scope everything to the selected entrypoints and their reachable files.

### For each selected entrypoint

Produce:

- `external_sources[]`
- `sinks[]`
- `intermediate_tables[]` when selected entrypoints share table-shaped handoffs
- `schemas`
- `mock_data_dir`
- `dependencies`
- patch-author hints
- shim hints
- notes for the runners

### External sources

Capture the sources needed to execute the entrypoint. Scan all `.scala`
files reachable from the entrypoint:

- table reads: `spark.table("name")`, `spark.read.table("name")`,
  SQL `FROM` references in `spark.sql("SELECT ... FROM ...")`,
  `spark.read.format("snowflake").load(...)`
- file reads: `.read.csv(...)`, `.read.parquet(...)`, `.read.json(...)`,
  `.read.text(...)`, `.read.format(...).load(...)`
- connector reads that need mocked tabular inputs

Do NOT include `.sql` script files in `external_sources[]` — declare
those in `auxiliary_files[]` only.

Each source record:

```json
{
  "id": "orders_source",
  "name": "orders_source",
  "category": "table | file | jdbc | snowflake",
  "original_path": "literal from source when available",
  "reader_method": "table | csv | parquet | json | ...",
  "reader_options": {},
  "mock_file": "orders.csv",
  "subpath": "optional/stage/layout/override",
  "schema": [...]
}
```

`mock_file` path resolution: always relative to
`Validation/shared/mock_data/<ep_id>/`. Never use paths like
`../shared/x.csv`.

> **FIELD NAME IS `mock_file`, NOT `mock_path`.**  The Scala harness case
> class maps `mock_file` → `ExternalSource.mockFile`.  Writing `mock_path`
> instead silently produces `None` → `SCOS_INPUT_*` is never set → workload
> reads the live cloud path at runtime → Phase A/B both fail with "Loaded data
> was empty". Always use `"mock_file": "filename.parquet"` (filename only,
> relative to the ep mock dir). Never write `"mock_path"`.

### Column reference extraction (Scala patterns)

When inferring schemas from workload code, extract column references
using these Scala Spark patterns:

- `col("colName")` and `functions.col("colName")`
- `$"colName"` (implicit encoder syntax)
- `.select("col1", "col2")` and `.select(col(...), col(...))`
- `.filter($"col" === value)`, `.where($"col" > 0)`
- `.groupBy("col1", "col2")`, `.groupBy($"col")`
- `.agg(sum("col"), avg("col"), count("col"))`
- `.withColumn("newCol", expr)` — `newCol` is output, not input
- `.join(other, "joinKey")`, `.join(other, Seq("k1", "k2"))`
- `.orderBy("col")`, `.sortBy("col")`
- `StructField("colName", DataType, ...)` — use declared type directly

**Confirm types — don't trust an all-`string` guess.** Column *names* mined from
`col(...)`/`$"..."`/`.select(...)` come with no type, so they default to
`string`. When a source's columns came from these patterns (not an explicit
`StructType`/`StructField` or a `.cast(...)`) and **every** type is `string`,
that is a guess, not a fact: infer the real types from how the columns are used
(arithmetic/`sum`/`avg` → numeric; date filters/`datediff` → date/timestamp;
`===`/`>`/`<` against typed literals → that literal's type) rather than leaving
the all-string default, which silently produces wrong mock data.

**Connector/JDBC reads need the underlying source columns, not just aliases.** A
`spark.read.format("snowflake").option("query"/"dbtable", …)` or `spark.table`
read often projects output aliases, but the workload also filters/joins on
columns that never appear in the projection. Declare the physical WHERE/JOIN
source columns in the source `schema` too — otherwise Phase B fails
`COLUMN_NOT_FOUND` on a column the mock never created.

**Runtime-substituted read names.** When a read's table or file path is built
at runtime, the analyzer records it with an unresolved `name` (e.g. `null` or a
partial literal) and an `llm_todo` hint. Common Scala shapes:
- String interpolation with a runtime segment: `spark.table(s"$schema.tbl")`,
  `spark.read.parquet(s"$basePath/run_$date")`
- Concatenation: `spark.table(schema + ".my_table")`
- `String.format("db.tbl_%s", suffix)` / `.formatted(...)`

The analyzer resolves a trailing literal dotted segment from `+` concat
(`schema + ".my_table"` → `my_table`) and constant-folded interpolations, but
NOT runtime-computed slots. For those: open `defined_at`, substitute the same
values the workload uses at run time, and update the entry's `name` and
`original_path` to the fully-substituted name so the mock matches what the code
reads.

### Sinks

Capture the outputs that should be snapshotted and compared:

```json
{
  "id": "orders_output",
  "name": "orders_output",
  "kind": "table | file | non_spark",
  "method": "saveAsTable | parquet | insertInto | ...",
  "original_target": "literal target when available",
  "schema": [...],
  "natural_keys": ["order_id"]
}
```

`natural_keys` is **required for meaningful A/B comparison**: the scos-runner passes
it to the comparator as `--key-columns`, enabling stable keyed row-matching. Without
it the comparator falls back to full-row lexicographic sort — one divergent cell
cascades into many false mismatches. Use the primary key(s) of the output table, or
the business-key columns that uniquely identify a row (e.g. `["route_id", "read_ts"]`).
If no natural key exists (e.g. order-dependent aggregation output), declare
`"natural_keys": []` explicitly to suppress the analyzer warning.

### Intermediate tables

When one selected entrypoint writes a table that another reads:

```json
{
  "name": "db.schema.table_name",
  "writer_entrypoint_id": "upstream_entrypoint",
  "reader_entrypoint_ids": ["downstream_entrypoint"],
  "schema": [...],
  "seed_strategy": "empty | from_source_join",
  "seed_sql": ""
}
```

### Schemas and mock data

Every source should get mock data under `Validation/shared/mock_data/<ep_id>/`.

**Generate relational mocks deterministically** — do NOT hand-author tabular
data. Once `external_sources[]` have `schema` + `mock_file`, run the typed
generator (same engine as the PySpark validator). It
writes type-correct, edge-case-covering data, and columns sharing a name across
an entrypoint's sources draw from a shared pool so joins actually match:

```bash
# Convert analysis.json -> schemas/ folder (same layout as PySpark validator)
uv run --project $SKILL_DIRECTORY/.. python \
  $SKILL_DIRECTORY/scripts/schema_mine.py --conv-root $CONVERSION_ROOT
# Generate typed mocks from schemas/
uv run --project $SKILL_DIRECTORY/.. python \
  $VALIDATOR_SCRIPTS/datagen.py \
  $CONVERSION_ROOT/Validation/shared/schemas \
  $CONVERSION_ROOT/Validation/shared/mock_data
# then confirm coverage:
uv run --project $SKILL_DIRECTORY/.. python \
  $VALIDATOR_SCRIPTS/datagen.py \
  $CONVERSION_ROOT/Validation/shared/schemas \
  $CONVERSION_ROOT/Validation/shared/mock_data \
  --verify
```

Use the LLM only for **judgement** the generator can't do: inferring the schema
itself, and authoring **non-tabular** inputs (config/JSON document blobs — a
source whose `schema` is not a column list). Hand-author or fix a specific mock
only when `--verify` flags a gap or a workload needs particular values.

**Work one repair unit at a time — do not batch unrelated fixes.** `datagen.py
--verify` is your prioritized to-do list. Take the **first** problem it reports,
map it to the smallest edit that clears it (one `external_sources[]` entry, one
`sinks[]` entry, or one `joins`/`values` edit in `analysis.json`), make that edit,
then re-run `schema_mine.py` → `datagen.py` → `--verify`. Stay on that unit until
its problems disappear, then restart from the new first problem. Do not read every
source file up front or plan the whole batch before the first datagen run.

**Datagen is hash-driven and incremental** — it regenerates only tables whose
schema hash changed (or whose mock is missing) and leaves the rest untouched, so
cheap re-runs after each edit are safe. **Do not wipe `mock_data` just because
`--verify` failed** — that defeats the hash mechanism. Force a full regenerate
(`--all`, or `rm -rf $MOCK_DATA_DIR`) **only** when an edit renamed or removed a
source/sink (datagen does not prune orphaned mock files from a rename/drop).

Requirements (the generator satisfies these for relational sources; verify them
for any hand-authored mock):

- every mock file exists,
- CSV-style mocks MUST have a real delimited header row as row 1,
- at least one data row exists,
- schema is good enough to exercise the workload,
- generated values should not all be identical.

### Auxiliary files

If the workload reads config or SQL files, materialize simple test-safe
versions under `Validation/shared/auxiliary/` and record them in
`auxiliary_files[]`.

Record widget/config values expected from the environment as plain notes
under the entrypoint (env var name `SCOS_WIDGET_<NAME>`).

### Verify the analysis (deterministic gates)

Before recording `synth_deep`, run the deterministic exit gates. There is no
separate critic agent — use the tools below instead of a manual body-scan.

**Gate 1 — mock files exist:**

```bash
uv run --project $SKILL_DIRECTORY/.. python \
  $SKILL_DIRECTORY/scripts/schema_mine.py --conv-root $CONVERSION_ROOT
uv run --project $SKILL_DIRECTORY/.. python \
  $VALIDATOR_SCRIPTS/datagen.py \
  $CONVERSION_ROOT/Validation/shared/schemas \
  $CONVERSION_ROOT/Validation/shared/mock_data \
  --verify
```

**Gate 2 — column coverage + write_helper sinks (replaces manual body-scan):**

```bash
uv run --project $SKILL_DIRECTORY/.. python \
  $SKILL_DIRECTORY/scripts/column_check.py --conv-root $CONVERSION_ROOT
```

Both gates must exit `0`. Gate 1 prints `"ok": true` in JSON; gate 2 prints
`[column_check] verify OK`. If gate 2 lists missing columns, edit
`analysis.json` and re-run `schema_mine.py` + `datagen.py` until clean.

When gate 2 flags gaps the AST extractor cannot attribute (helper-method
column gaps, `.agg(sum("col"))`, `StructField` declarations), supplement
`ast_facts.json` with targeted source reads — do not re-parse the whole workload
by hand.

Re-derive obviously-wrong types instead of leaving an all-`string` mined
schema: numeric for `sum`/arithmetic, date/timestamp for date filters /
`datediff`. For a `format("snowflake")` / `spark.table` connector read, ensure
the schema includes the WHERE/JOIN columns the workload uses, not just the
projected output aliases.

- **`array<struct<...>>` mistyped as `string`.** A source column feeding
  `explode`/`flatten`, or produced by `collect_list`/`collect_set` of a struct,
  is `array<struct<...>>`, not `string` (the AST extractor defaults to `string`
  for unresolved complex types). Fix the type from the call site if you can spot
  it; otherwise the Phase B inline-repair loop will surface it.

**Sink declarations.** For every sink confirm `kind`/`method` are present,
table/file sinks have a non-empty schema, and the target identifier is not
blank. Gate 2 (`column_check.py`) also flags `write_helpers` without matching `sinks[]`.

If either gate adds columns or sinks, re-run `schema_mine.py` then
`datagen.py schemas/ mock_data --verify` and `column_check.py --conv-root ...`;
confirm both exit `0` before recording the milestone.

### Warning handling

`datagen.py --verify` emits `warnings` separately from `problems`. Warnings are
not part of `ok`, but you must resolve or explicitly dismiss them before finishing
— an unhandled join warning silently produces empty joins at runtime. Handle them
only once `problems` is empty, one edit at a time:

- **Join-overlap warnings** (a column appears in ≥2 sources but datagen won't pool
  it — no `joins` edge, no shared `values`): if it is a real join key, add a
  `joins` edge (or a shared `values` domain) in `analysis.json`, then re-run
  `schema_mine.py` + `datagen.py` so the linked columns draw from one pool. A
  star-pattern key shared across many sources is **one** edit — add all its edges
  at once, then regenerate once (not one edge at a time).
- **Confirmed non-keys**: set `"join_key": false` on the column to dismiss the
  warning. This only silences the *warning*; it does **not** dismiss a real
  `join overlap empty` *problem* once a column is already in an established pool.
- Pure `join_key: false` dismissals need only a re-run of `--verify` (no datagen
  regenerate).

### Review generated mocks with `--peek`

Once `problems` is empty and warnings are handled, spot-check the mocks against the
workload source (the `python_repl` kernel has no pandas/pyarrow, so use `--peek`):

```bash
uv run --project $SKILL_DIRECTORY/.. python \
  $VALIDATOR_SCRIPTS/datagen.py \
  $CONVERSION_ROOT/Validation/shared/mock_data/<ep_id>/<mock_file> --peek
```

It prints per-column dtype, null count, distinct count, and sample values. Confirm:

- declared **types** match the workload's real expectations (an amount cast to
  decimal isn't left `string`; a date column isn't an int);
- **literal filter domains** are represented — when the source filters on a small
  fixed set (`col.isin(...)`, SQL `IN (...)`, `=== "610A"`), the mock must contain
  those values or the filter yields **zero rows** with random mocks. Add them as
  `"values"` on the column;
- **join keys** that must match across sources actually overlap;
- sample values are plausible for the domain (a `latitude` in `[-90, 90]`);
- nullable columns still contain nulls and NOT NULL keys do not.

Prefer a systematic schema fix + re-run `schema_mine.py` + `datagen.py` over
hand-editing a mock (a later datagen regenerate overwrites hand edits). If you edit
a mock or schema here, run one final `--verify` before recording the milestone.

### Deep-analysis output

Update `analysis.json` in place, then record:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  record-milestone --conv-root $CONVERSION_ROOT --milestone synth_deep
```

## Self-check

Before finishing, verify:

1. `entrypoint_candidates[]` exists after survey mode.
2. `entrypoints[]` exists after deep-analysis mode.
3. Every selected entrypoint has `mock_data`, `external_sources`, and
   `sinks` recorded.
4. `build_tool` and `source_roots[]` are populated.
5. No auto-selection logic was introduced.
6. **Hard gate:** `datagen.py schemas/ mock_data --verify` exits `0` AND
   `column_check.py --conv-root` exits `0`. Do not record `synth_deep` while
   either gate reports problems; fix and re-run.
7. No `warnings` from the final `--verify` remain unresolved or undismissed.
8. Every `llm_todo` on selected entrypoints and their `external_sources`/`sinks`
   is resolved (or explicitly documented as a known gap with a fix plan).

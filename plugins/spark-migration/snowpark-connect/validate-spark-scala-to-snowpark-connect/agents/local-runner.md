# Local Runner

Owns Phase A: copy the test kit, render ScalaTest specs from the
template, run the selected entrypoints locally on Spark + Delta, and
persist source baselines when possible.

## Inputs

- `CONVERSION_ROOT`
- `SKILL_DIRECTORY`

Derived paths:

- `VALIDATION_ROOT = <CONVERSION_ROOT>/Validation`
- `TESTS_DIR       = Validation/tests`
- `RESULTS_DIR     = Validation/results/phase_a`
- `ANALYSIS_JSON   = Validation/shared/analysis.json`
- `STATE_JSON      = Validation/state.json`

## Ground Rules

1. Copy the shared kit from `$SKILL_DIRECTORY/harness-scala/kit/` instead
   of re-authoring `ScosTrialFixture` or `Helpers` from memory (output
   comparison is done by `$VALIDATOR_SCRIPTS/harness/comparator.py compare`, looped per captured table).
2. Render one `Test<EpId>Spec.scala` per selected entrypoint from
   `TestTemplate.scala.tmpl`.
3. If you find a reusable harness gap during this run, fix the copied
   kit under `Validation/tests/` instead of piling fixes into individual
   test specs.
4. Widget inputs belong in rendered test specs via `WIDGET_ENV_VARS`,
   not in a separate widget manifest file.

## Setting up the test project

Copy the full kit as an sbt project. Use `rsync` so the build output
(`target/`, `project/target/`) is NOT dragged into the trial dir — copying
it forces a full zinc recompile and pulls in the resolved Spark JARs:

```bash
rsync -a --exclude 'target/' --exclude 'project/target/' \
  $SKILL_DIRECTORY/harness-scala/kit/ $TESTS_DIR/
# Fallback if rsync is unavailable:
#   cp -R $SKILL_DIRECTORY/harness-scala/kit/. $TESTS_DIR/ && \
#   rm -rf $TESTS_DIR/target $TESTS_DIR/project/target
```

This gives you:
- `build.sbt` — kit build file (spark, delta, JDBC dependencies)
- `project/` — sbt meta-project
- `src/main/scala/ScosTrialFixture.scala` — base fixture
- `src/main/scala/Helpers.scala` — seedEntrypoint, captureResults,
  cloneGoldenSchemaForTrial, declaredSinkTables
- `src/main/scala/ReflectionEntrypoint.scala` — JVM reflection
  loader for compiled workload JARs
- `templates/TestTemplate.scala.tmpl` — fill-in template for per-entrypoint specs
- `.gitignore.template`

Copy the `.gitignore.template`:

```bash
cp $SKILL_DIRECTORY/harness-scala/kit/.gitignore.template $TESTS_DIR/.gitignore
```

**Critical Rule**: Do NOT redefine path-rewriting, connector-read
intercept, or schema-clone logic in individual `Test*Spec.scala` files.
Always use `Helpers` methods. Workload-specific extensions belong in
dedicated `tests/src/test/scala/<Workload>Extensions.scala` files that
import `Helpers` and add new wrappers.

## Rendering test specs

Render one `Test<EpId>Spec.scala` per selected entrypoint from
`TestTemplate.scala.tmpl`, filling in the fields recorded by the patch author:

- `EP_ID` — entrypoint ID, matches analysis.json `"id"`
- `CLASS_NAME` — ScalaTest class name, e.g. `"TestMyEntrypointSpec"`
- `ENTRY_CLASS_NAME` — fully qualified JVM class name
- `ENTRY_METHOD_NAME` — method name (usually `"main"`)
- `ENTRYPOINT_ARGS` — `Array[String]` literal, e.g. `Array("--env", "dev")` or `Array.empty[String]`
- `JAR_PATH` — absolute path to compiled workload JAR
- `TRIAL_DIR` — absolute path to `results/phase_a/<ep_id>/`
- `PHASE_A_DIR` — absolute path to `results/phase_a/<ep_id>/` (Phase B comparison baseline)
- `WIDGET_ENV_VARS` — Map entries, e.g. `"SCOS_WIDGET_ENV" -> "dev",` or empty
- `ANALYSIS_JSON_PATH` — absolute path to `Validation/shared/analysis.json` — required so `AnalysisJson.load()` / `StateJson.load()` resolve before `beforeAll()` runs in the forked JVM
- `STATE_JSON_PATH` — absolute path to `Validation/state.json` — same reason

Place the rendered spec at:
`Validation/tests/src/test/scala/Test<EpId>Spec.scala`

Create the package directory first (it is not in the kit source):
```bash
mkdir -p "$TESTS_DIR/src/test/scala/com/snowflake/scos/kit/generated"
```

Keep these rendered specs minimal.

## Prerequisites (Phase A)

Phase A runs the **original** workload (`Validation/source/`, plain `SparkSession`) on
local Spark+Delta against the seeded mock data — it produces the baseline that Phase B
is compared against. It does **not** run the migrated `Output/` (that uses
`SnowparkConnectSession` and is Phase B's job).

The deterministic runner `scos_state.py run-phase-a` handles this end to end: it builds
the original source jar (`sbt assembly` / `mvn package` / `./gradlew shadowJar` in
`Validation/source/`, with a `package` fallback), resolves the migrated `Output` jar,
renders one spec per entrypoint with **both** jars baked in (the spec picks one at
runtime via `SCOS_FLAVOR`), and runs `sbt test`. Prefer it over driving the steps by hand:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  run-phase-a --conv-root $CONVERSION_ROOT
```

> **Do NOT pre-skip Phase A by grepping `Output/` for `SnowparkConnectSession`.** The
> migrated `Output/` always contains it — that is expected and is exactly what Phase B
> runs. Skipping Phase A on that basis destroys the baseline and makes the whole
> validation a no-op (`passed_no_baseline` for everything). Phase A must run the
> *original* source. Only mark a trial `phase_a_skipped` when the **original source**
> genuinely cannot run on local OSS Spark (real dialect/Databricks reasons below), not
> because the migrated output uses SCOS.

If you are running the steps manually instead of via `run-phase-a`, build the source jar
first and verify it exists:

```bash
test -f "$SOURCE_JAR" || echo "PREREQ_FAIL: source JAR not built — run sbt assembly (or mvn package / ./gradlew shadowJar) in Validation/source/ first"
```

## Iteration loop

Run **all** selected specs in one batched pass — this is the default. One
forked JVM per entrypoint spec, run in bounded parallel, in a single agent
loop with one result-processing pass (do NOT dispatch one `testOnly` per
trial — that pays N JVM cold-starts and N read→compare→record loops):

```bash
# Runs in CoCo bash sandbox (Linux) - safe on any host OS
SCOS_FLAVOR=source \
SCOS_TEST_PARALLELISM=4 \
SCOS_RESULTS_DIR=$RESULTS_DIR \
SCOS_CONV_ROOT=$CONVERSION_ROOT \
SCOS_ANALYSIS_JSON=$CONVERSION_ROOT/Validation/shared/analysis.json \
SCOS_STATE_JSON=$CONVERSION_ROOT/Validation/state.json \
SCOS_MOCK_DATA_DIR=$CONVERSION_ROOT/Validation/shared/mock_data \
sbt test 2>&1 | tee $RESULTS_DIR/sbt_source.log
```

Only when you need to isolate a single failing spec for debugging, narrow
to one with `testOnly`:

```bash
# Runs in CoCo bash sandbox (Linux) - safe on any host OS
SCOS_FLAVOR=source \
SCOS_RESULTS_DIR=$RESULTS_DIR \
SCOS_CONV_ROOT=$CONVERSION_ROOT \
SCOS_ANALYSIS_JSON=$CONVERSION_ROOT/Validation/shared/analysis.json \
SCOS_STATE_JSON=$CONVERSION_ROOT/Validation/state.json \
SCOS_MOCK_DATA_DIR=$CONVERSION_ROOT/Validation/shared/mock_data \
sbt "testOnly *Test<EpId>Spec" 2>&1 | tee $RESULTS_DIR/sbt_source.log
```

Phase A specs run in **bounded parallel** — one forked JVM per entrypoint spec
(per-suite fork keeps EnvUtil system-property overrides isolated), each with its
own warehouse/checkpoint dir. Concurrency is capped by `SCOS_TEST_PARALLELISM`
(default 4); lower it to `1` for fully serial if the machine is memory-constrained
(each fork starts a local Spark + Delta session).

Classify failures into:

- **harness issue** — problem in `ScosTrialFixture`, `Helpers`, or the
  kit build configuration
- **mock-data issue** — schema mismatch, missing column, bad CSV
- **compilation/reflection issue** — workload JAR not found,
  `ClassNotFoundException`, `NoSuchMethodException`
- **workload issue** — runtime exception in the workload body that
  prevents a trustworthy local baseline

Route each failure to the matching action:

| Failure | Action |
|---|---|
| `AnalysisException` / `TABLE_OR_VIEW_NOT_FOUND` on a table | Add the missing table to `external_sources[]` in `analysis.json` with `"access": "read"` (or `"readwrite"`); re-run `schema_mine.py` + datagen (see **Inline schema repair** below) |
| `COLUMN_NOT_FOUND` / Spark analysis error on a column | Add the missing column to the source's `schema` array in `analysis.json`; re-run `schema_mine.py` + datagen |
| `AnalysisException` on a 3-part `CATALOG.SCHEMA.TABLE` name | **Namespace-rebind patch** via `patch-add` (`SCOS_DATABASE_NAME`/`SCOS_OUTPUT_SCHEMA`) — this is plumbing, NOT a skip |
| Parquet type mismatch (`Expected: decimal(10,2), Found: DOUBLE`; `Expected: date, Found: INT64`) | Fix the column's `type` in `external_sources[].schema` in `analysis.json`; re-run `schema_mine.py` + datagen |
| Clean run but output empty/all-null (filter keeps no rows, join key doesn't overlap), or a harness failure saying a declared sink produced/captured 0 rows | Add the filter literals as `"values"`, or a `joins` edge in `analysis.json`; re-run datagen. Set `allowEmpty` on the sink in `analysis.json` only for a rare sink that is genuinely intentionally empty. |
| Unpatched I/O — cloud read/write, `dbutils`, secrets | **`patch-add`** so the workload reads `SCOS_INPUT_*` / `SCOS_SINK_*`; see `patch-author.md` |
| Connector read — `spark.read.format("snowflake")…load()` | **`patch-add` per-side**: `source` → `spark.table(...)` rewrite; see `patch-author.md`; never skip |
| Harness/kit bug (`ScosTrialFixture`, `Helpers`, `build.sbt`) | Edit the copied kit under `Validation/tests/`; escalate if a deeper kit defect |

JVM-specific failure modes to watch for in Phase A:

- `ClassNotFoundException` — compiled JAR is missing or the
  `entrypoint_class` is wrong; re-run `sbt assembly` in `Output/`
- `NoSuchMethodException` — `entrypoint_method` does not match the
  actual method signature; verify with `javap -p ClassName`
- **`NoSuchMethodError` containing `remote` or `SparkConnect`** — Phase A loaded the
  *migrated* jar (which calls `SparkSession.builder().remote()`) instead of the original
  source jar. This means the wrong jar was selected: confirm `SCOS_FLAVOR=source` and that
  `run-phase-a` built the source jar from `Validation/source/` (`JAR_PATH_SOURCE` in the
  rendered spec must be non-empty). It is **not** a reason to skip Phase A.
- `KryoException` / `NotSerializableException` — Spark serialization
  issue in the workload; note for human review, do not attempt to fix
- `DeltaAnalysisException` — Delta table path conflict; use a fresh
  `spark.warehouse.dir` per trial (the fixture handles this)
- Scala version mismatch — workload compiled with Scala 2.13 but kit is
  2.12 (or vice versa); check `build.sbt` `scalaVersion`
- **Connector read breaks Phase A** — a source-side
  `spark.read.format("snowflake")…load()` (no local connector; its options map is
  often a stripped `%run`-config global) or a `spark.sql`/`spark.table` read with
  a hardcoded prod 3-part name. This is **not** a harness or workload defect: the
  `source` side needs a `spark.table(...)` mock rewrite / literal-prefix rebind
  via `patch-add` (see `patch-author.md` "Connector reads are a per-side patch"). An
  `.option("sfDatabase"/"sfSchema", …)` rebind only fixes the migrated side and
  silently no-ops on `spark.sql`/`spark.table`.

### Inline schema repair (Phase A — do not exit)

**Mock data is owned by `analysis.json` — never hand-edit mock files.** When a
Phase A run hits a mock-data failure (missing table/column, type mismatch, empty
output), the repair loop is:

1. Edit `analysis.json` — add or fix the relevant `external_sources[].schema`
   columns or table entry.
2. Re-run `schema_mine.py` to regenerate `schemas/` from the updated `analysis.json`:
   ```bash
   uv run --project $SKILL_DIRECTORY/.. python \
     $SKILL_DIRECTORY/scripts/schema_mine.py --conv-root $CONVERSION_ROOT
   ```
3. Regenerate typed mocks and verify:
   ```bash
   uv run --project $SKILL_DIRECTORY/.. python \
     $VALIDATOR_SCRIPTS/datagen.py \
     $CONVERSION_ROOT/Validation/shared/schemas \
     $CONVERSION_ROOT/Validation/shared/mock_data
   uv run --project $SKILL_DIRECTORY/.. python \
     $VALIDATOR_SCRIPTS/datagen.py \
     $CONVERSION_ROOT/Validation/shared/schemas \
     $CONVERSION_ROOT/Validation/shared/mock_data \
     --verify
   ```
   `--verify` must print `[datagen] verify OK` (exit 0) before re-running sbt.
4. Re-run the spec(s) and record the iter with `--fix-category analysis_repair`.

`datagen.py` derives the physical Parquet type from the declared `type` in
`analysis.json`: `decimal(p,s)` → `decimal128(p,s)`, `timestamp*` →
`timestamp[us]`, `date` → `date32`, `short`/`smallint` → `int16`,
`byte`/`tinyint` → `int8`, `real` → `double`. A correctly declared `type` always
produces a seedable mock.

Only escalate past this loop for harness kit bugs or genuine Phase A skip
conditions — not for fixable schema gaps.

## No shims — patch the I/O instead

There are no JVM shims or mock filesystems in the kit. All non-Spark I/O
(cloud reads/writes, `dbutils`, JDBC, HTTP, secrets, widgets) is rewritten by
the patch-author's `patch-add` blueprint into native Spark + env-var
indirection (`System.getProperty`), or deleted — exactly like the PySpark
validator.

If a Phase A run hits a missing class or an unsupported non-Spark call
(`ClassNotFoundException`, `NoSuchMethodException`, `ClassCastException`), the
cause is an **un-patched I/O dependency**, not a missing stub. Add a
`scos_state.py patch-add` patch that rewrites the offending call to native
Spark / env reads (see `patch-author.md`), then re-run. If the problem is at
the reusable execution seam (session wiring, snapshot capture), fix the copied
kit under `Validation/tests/` instead.

## When to stop Phase A

For each entrypoint: if local execution succeeds and the snapshot looks
trustworthy, record the baseline; otherwise classify the failure and fix it.

**Schema/mock gaps are always repairable — never skip for them.**
`TABLE_OR_VIEW_NOT_FOUND`, `COLUMN_NOT_FOUND`, missing `mock_file`,
`columns: []`, empty/all-null output, and declared-sink-empty failures are
always fixable by inline schema repair (see *Inline schema repair* below),
no matter how many tables are missing — unless the sink is genuinely
intentionally empty, in which case set `allowEmpty` on the sink entry in
`analysis.json`. `phase_a_skipped` is the Phase A analogue of `hard_stuck` — rare, and
never the right response to a schema gap. The 3-iteration cap below is a guard
against genuine thrash, not an escape hatch for fixable schema issues — add the
missing table to `external_sources[]` and repair the schema instead.

**Hard iteration cap (enforce, not advisory):** Phase A gets at most **3**
iterations per entrypoint. At the START of every Phase A attempt, check the
recorded `phase_a_iters` for the trial; if it is already `>= 3`, do NOT start
another iteration — immediately mark the trial `phase_a_skipped` and proceed
to Phase B:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  record-trial-status --conv-root $CONVERSION_ROOT \
  --trial-id <id> --status phase_a_skipped \
  --reason "phase A iteration cap (3) reached"
```

A missing Phase A baseline is not a failure — Phase B still runs and a clean
SCOS run becomes `passed_no_baseline`. Burning >3 local iterations on one
entrypoint is pure wasted wall time.

Do not block the entire workflow on one missing baseline. Phase B still
runs.

## Environment differences and Phase A skip

Phase A runs the source-flavor Scala workload against local Spark +
Delta. Some constructs cannot be executed in this environment:

- `QUALIFY` clauses and Snowflake-specific SQL extensions
- `MERGE INTO` / `LATERAL VIEW` Databricks-dialect variants
- Operations that require a real Snowflake connection at the Spark level

**Never a skip:**
- **Missing / unmocked source tables** (`TABLE_OR_VIEW_NOT_FOUND`,
  `COLUMN_NOT_FOUND`) — inline schema repair, regardless of table count (see
  *When to stop Phase A* above).

When Phase A fails on such an environment difference (NOT a workload
bug), the local-runner MUST:

1. Mark the trial with status `phase_a_skipped`:
   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
     record-trial-status --conv-root $CONVERSION_ROOT \
     --trial-id <id> --status phase_a_skipped \
     --reason "<short reason>"
   ```
2. Proceed to Phase B without a Phase A baseline.
3. Phase B will produce `passed_no_baseline` on success.

Do NOT attempt to rewrite Snowflake-only SQL into local-Spark
equivalents. The honest path is `phase_a_skipped` → `passed_no_baseline`.

## Record keeping

Call `record-iter` after each meaningful iteration:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  record-iter --conv-root $CONVERSION_ROOT --trial-id <id> \
  --phase phase_a --iter <N> --fix-category <category> \
  --notes "<short>"
```

After applying any patch to `tests/`, `Output/`, or `shared/`, record:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  record-patch --conv-root $CONVERSION_ROOT --trial-id <id> \
  --phase phase_a --file <path-relative-to-conv-root> \
  --reason "<short>" --iter <N>
```

If baselines were authored at all, record:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/scos_state.py \
  record-milestone --conv-root $CONVERSION_ROOT --milestone tests_authored
```

## Report back

Summarize:

- which entrypoints produced baselines
- which did not, and why
- what harness changes were made
- what JVM-specific issues should be carried into Phase B for human review

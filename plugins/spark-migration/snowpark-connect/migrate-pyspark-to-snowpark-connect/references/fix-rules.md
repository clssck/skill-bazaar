# SCOS Fix Rules Reference

Rules for fixing SCOS compatibility issues found during analysis. The fixer agent reads this document when applying fixes to migrated files.

**Related references:**
- `../../references/python/rdd-conversion.md` — RDD-to-DataFrame conversion rules and examples (required for Rule 2)
- `../../references/python/udf-dependencies.md` — UDF serialization tiered fix approach (required for Rules 10 and 11)
- `../../references/python/spark-config.md` — which `spark.conf.set` / `.config` keys SCOS honors vs silently ignores, default deviations, and SCOS-specific knobs (required for Rule 5)
- `../../references/python/ewi-codes.md` — Official SCOS EWI code scheme (required for `# SCOS:` comment tagging)
- `../../references/python/troubleshooting.md` — runtime / SQL / connection error playbook (e.g. "Insert value list does not match column list", mixed-case "Object does not exist", `RESOURCE_EXHAUSTED` → `ChannelBuilder.MAX_MESSAGE_LENGTH`, `safe_count`/`safe_checkpoint`, QUALIFY pass-through, connection env vars) — consult when a fix needs to resolve a specific runtime error

---

## Phase 0.5 Recipe Coverage

Several rules below are now fully or partially handled by deterministic
LibCST recipes that run in Phase 0.5 before the LLM analyzer ever sees the
file. The recipes emit `# SCOS:`, `# SCOS-WARN:`, or `# SCOS-TODO:` comments
naming themselves; the fixer's job for those lines is to (a) NOT undo the
recipe edit and (b) optionally apply a deeper, context-aware fix on top.

| Rule(s) | Recipe id | Status |
|---|---|---|
| `checkpoint()` / `localCheckpoint()` (workflow §3) | `dataframe_checkpoint_to_cache_rewrite` | **rewrite — done** |
| Wildcard / glob reads (Rule 9) | `wildcard_file_read_todo_annotate` | annotate — fixer may rewrite to enumerated paths |
| Map column subscript (Rule 13, workflow §3) | `map_column_subscript_colkey_to_element_at_rewrite` | **rewrite — done** |
| SparkContext properties (Rule 14) | `sparkcontext_property_fallback_rewrite` | **rewrite — done** (skips f-strings) |
| `unionByName(..., allowMissingColumns=True)` | `unionbyname_allowmissing_schema_align_warn_annotate` | annotate — fixer should pre-align schemas |
| External-cloud reads (`s3://`, `gs://`, `abfss://`, ...) | `external_cloud_read_stage_perf_comment` | annotate — fixer may rewrite to `@stage/...` |
| Self-join `df.join(df, ...)` (no alias) | `self_join_unaliased_warn_annotate` | annotate — fixer should add `.alias()` |
| Driver materialization in loops (`.collect()` / `.toPandas()` / `.first()` / `.take()` / `.head()` inside `for`/`while`) | `driver_materialization_hotpath_warn_annotate` | annotate — fixer should lift out of loop |
| Temp-view multi-use cache (Rule 21) | `tempview_multiuse_cache_rewrite` | **rewrite — done** |
| `@udtf` compatibility flag (Rule 19) | `udtf_enable_compatibility_mode_rewrite` | **rewrite — done** |
| `SparkSession.builder...master()/config().getOrCreate()` | `spark_builder_drop_master_init_session_rewrite` | **rewrite — done** (preserves configs) |
| `SparkContext.getOrCreate()` / `SparkContext(...)` / `SparkSession(sc)` (legacy two-line bootstrap) | `sparkcontext_getorcreate_init_session_rewrite` | **rewrite — done** (both names rebind to `init_spark_session()`; warns on dropped `SparkConf`) |
| No-op cluster/runtime configs (Rule 5) — `spark.executor.*`, `spark.driver.memory|cores`, `spark.dynamicAllocation.*`, `spark.shuffle.*`, ... | `spark_config_noop_annotate` | annotate — flags `# SCOS-WARN: [SPRKCNTPY1000]`; fixer leaves the line (safe to delete) |
| UDF-backed builtins (`crc32`, `format_number`, `format_string`/`printf`, `from_csv`, `map_concat`, `map_from_arrays`) | `udf_backed_builtin_perf_annotate` | annotate — perf hint (server-side Python UDF, slower than native); fixer may swap for a native alternative on hot paths. Conditional cases (`bit_count`/`encode`/`transform`) are left to the analyzer — see `../../references/python/udf-dependencies.md` |

When the fixer encounters a line already marked by one of the recipes, it
MUST consult `migration_state.json:recipe_edits` to confirm the
recipe-managed state and proceed with the workflow above.

---

## Pre-Fix: Read EWI Codes

Before applying fixes, read `references/python/ewi-codes.md` to understand the official SCOS EWI code scheme. When adding `# SCOS:` comments, include the relevant EWI code where possible. For example:
- `# SCOS: [SPRKCNTPY1500] RDD operation converted to DataFrame`
- `# SCOS: TODO - [SPRKCNTPY2500] ML element requires manual migration`

This tagging enables the report generator to map comments to official codes accurately.

---

## Per-Issue Processing

For EACH issue in `analysis.json`, perform the following:

0. **Branch on `kind` FIRST** (recipe-aware shortcut, added with the
   recipe-aware analyzer).  Each issue carries a `kind` field set by
   `analyze_pyspark.py`.  Use it to route the issue before applying any of
   the per-rule logic below:

   | `kind` | What it means | Required fixer action |
   |---|---|---|
   | `recipe_validated` | A `*_rewrite` recipe already fixed this site bytewise in Phase 0.5. `final_risk` is forced to 0.0 and `recipe_id` names the recipe. | **Skip** — emit no edit. Verify the inline `# SCOS:` comment naming `recipe_id` is still present in the source; if missing, re-add `# SCOS: validated by <recipe_id>` (recipe audit trail). Move to the next issue. |
   | `recipe_incomplete` | A `*_annotate` / `*_comment` recipe flagged this site but could not auto-rewrite. `recipe_id` names the recipe; `suggested_fixer_action` MAY contain a concrete LLM-proposed rewrite. | **Prefer `suggested_fixer_action` over `fix`** if it is non-null and concrete code (not prose).  Apply it verbatim, then append `# SCOS: fixed by fixer on top of <recipe_id>` (do NOT remove the recipe's original `# SCOS-WARN:` / `# SCOS-TODO:` comment). If `suggested_fixer_action` is null/empty, fall through to the normal rules below using `fix` and `root_cause`. |
   | `recipe_adjacent` | No recipe fired here, but the analyzer thinks the pattern matches a recipe (`suggested_recipe_id`). | Apply normal rules below using `fix` / `root_cause`. ADDITIONALLY append `# SCOS: recipe-coverage gap - pattern matches <suggested_recipe_id>` so we can mine these for future Phase 0.5 recipe additions. |
   | `llm_only` (default) | No recipe relationship. | Apply normal rules below.  This is the historical behavior. |

   For backward compatibility: if `kind` is missing from the issue object
   (older `analysis.json` files predating recipe-awareness), treat the
   issue as `kind="llm_only"`.

1. **Locate the issue**: Find the code at `file` and `lines` in the copied directory.
2. **Assess the risk**: Check the `final_risk` value.
3. **Apply the appropriate action** based on the rules below.
4. **Record the action.** Every issue you process MUST end with a recorded
   verdict, but *where* you record it depends on the outcome:

   - **Action taken or follow-up needed → inline `# SCOS:` comment.** When you
     applied a fix, rewrote the logic, left a manual `TODO`, or have a
     performance tip, add a code comment next to the processed chunk explaining
     the root cause and your decision. Use one of these prefixes so the
     validation skill can parse them:
     - `# SCOS: <explanation>` — fix applied
     - `# SCOS: TODO - <explanation>` — requires manual review; could not be auto-fixed (see requirements below)
     - `# SCOS: Performance tip - <explanation>` — optimization recommendation

   **`# SCOS: TODO` requirements — every TODO MUST contain all three of:**
   1. The specific unsupported API or element (e.g. `spark.read.format("com.databricks.spark.redshift")`, `dbutils.secrets.get`).
   2. WHY it is unsupported in SCOS (the concrete root cause).
   3. The suggested Snowflake-native alternative.

   Generic placeholder text such as "high-risk pattern requires manual review" or "requires manual review" with no specifics is **FORBIDDEN**.

   BAD: `# SCOS: TODO - high-risk pattern requires manual review`
   GOOD: `# SCOS: TODO - spark.read.format("com.databricks.spark.redshift") with forward_spark_s3_credentials + s3a tempdir is unsupported in SCOS; load the Redshift data via a Snowflake external/JDBC source or stage instead`

   - **Safe / no action needed → `analysis.json`, NOT an inline comment.** When
     you reviewed the issue and concluded the code is already correct on
     Snowpark Connect (a false positive, or a KB rule that does not apply given
     the surrounding context), do **not** clutter the source with a
     `# SCOS: ...safe` comment. Instead set `resolution` and
     `resolution_reason` on that issue object in `analysis.json` (see
     [Recording resolutions in `analysis.json`](#recording-resolutions-in-analysisjson)).

   **Exceptions (no record of any kind):** accepted no-op operations (Rule 4),
   which are left as-is without comment or resolution. No-op *configs* (Rule 5)
   are not re-recorded by the fixer either, but they already carry the
   `spark_config_noop_annotate` recipe's `# SCOS-WARN` marker — leave it intact.

---

## Rules for Fixing based on Risk Score

1. **Must Fix (`final_risk` >= 0.7)**: These are critical compatibility issues. You **MUST** apply a fix or rewrite the logic. If no direct fix is available, you must rewrite the code to avoid the unsupported feature. If a rewrite is not feasible, add `# SCOS: TODO - <explanation>` so the validation skill flags it. Only record `resolution: "safe"` for a high-risk issue when you can give a concrete, code-grounded justification in `resolution_reason` (e.g. "window has an explicit `orderBy` → deterministic"); a bare "looks fine" is not acceptable and the gate will reject a `safe` verdict with no reason.
2. **Should Fix (0.3 <= `final_risk` < 0.7)**: These are likely issues. You **SHOULD** apply a fix if one is suggested. If a concrete fix exists, apply it rather than deferring to a `TODO`. If it genuinely needs human judgment, add `# SCOS: TODO - <explanation>`. If review shows the code is already safe, record `resolution: "safe"` in `analysis.json` (no inline comment).
3. **Fix if possible (`final_risk` < 0.3)**: These are minor risks or potential false positives. You **MUST still review them** and apply a fix if possible. If the code is safe, record `resolution: "safe"` (with a brief reason) in `analysis.json` — do **not** add a `# SCOS: ...safe` comment.

---

## Recording resolutions in `analysis.json`

After you process an issue, write your verdict back onto that issue object in
`analysis.json` by adding two fields. This is the structured, machine-readable
record the gates and the validation skill rely on — it replaces the old habit
of leaving a `# SCOS: ...reviewed, safe` comment in the source for every
finding.

| Field | Values | Meaning |
|---|---|---|
| `resolution` | `"fixed"` | You applied a fix or rewrite (also leave the inline `# SCOS:` comment). |
| | `"todo"` | Needs manual follow-up (also leave the inline `# SCOS: TODO` comment). |
| | `"safe"` | Reviewed; no action needed. **No inline comment.** Requires `resolution_reason`. |
| | `"perf"` | Performance tip only (also leave the inline `# SCOS: Performance tip` comment). |
| `resolution_reason` | free text | Why. **Mandatory for `"safe"`**; recommended for the rest. |

Example — a window-function finding the KB flags as non-deterministic, but the
code has an explicit `orderBy`, so it is actually deterministic:

```json
{
  "file": "jobs/sales.py",
  "lines": "42-42",
  "final_risk": 0.8,
  "resolution": "safe",
  "resolution_reason": "row_number() over a window with explicit orderBy('id') -> ordering is deterministic; KB rule is context-free and does not apply here"
}
```

Rules for `resolution`:

- **`"safe"` requires a concrete, code-grounded `resolution_reason`.** The fixer
  gate emits a CRITICAL `safe_without_reason` finding for any high-risk
  (`final_risk` >= 0.7) issue marked `safe` with an empty reason, which
  re-triggers the fixer. Do not use `"safe"` as a shortcut to silence a finding
  you have not actually reasoned through.
- **Never upgrade an "unverified" verdict into a confident `"safe"`.** If
  `analysis.json` (or the KB) says to *verify* something and you have no
  grounding to confirm it, keep it as `# SCOS: TODO - verify ...` with
  `resolution: "todo"`. Do **not** assert "auto-translated by SCOS / supported /
  safe" based on a function name alone.
- A recorded `resolution` satisfies the high-risk coverage gate **without** an
  inline marker, so a legitimately-safe finding no longer forces a noisy comment
  or a spurious fixer re-dispatch.

---

## General Rules

1. **Use the Tool's Fix** (recipe-aware priority order):
   1. If `suggested_fixer_action` is non-null AND looks like concrete code
      (not prose), use it verbatim. This is the recipe-aware LLM rewrite
      and is strictly more grounded than the generic `fix` because it was
      produced with the recipe context in mind.  Issue this for
      `kind="recipe_incomplete"` issues.
   2. Else if `fix` is non-null, use it.  This is the generic LLM
      workaround.
   3. Else fall back to `root_cause` + the rule below that matches the
      issue type.

2. **Handle RDDs**: RDD operations (`final_risk` near 1.0) drop out of the DataFrame API. Each RDD issue carries an `rdd_class` field, and the `fix` names the detected op(s) and points to `references/python/rdd-conversion.md`:
   - `rdd_class == "convertible"` — **look up each named op in `rdd-conversion.md` and apply its DataFrame rewrite.** Do NOT defer a convertible op to a `# SCOS: TODO`.
   - `rdd_class == "mixed"` — rewrite the convertible ops from the reference; add a `# SCOS: TODO` only for the named no-equivalent op(s).
   - `rdd_class == "no_equivalent"` — no rewrite exists (no `suggested_fixer_action`); add a `# SCOS: TODO` naming the op, why it is unsupported, and the Snowflake-native alternative.

   **Read** `references/python/rdd-conversion.md` for the full conversion mapping, notes, and worked examples — it is the source of truth for the per-op rewrites.

3. **Unsupported Formats**: Change file formats if required (e.g., ORC/Avro -> Parquet).

4. **Accepted APIs (hint / repartition / coalesce)**: `hint()`, `repartition()`, and `coalesce()` are **accepted** by SCOS but are **not pure no-ops**:
    - `hint("DIRECTED")` actively controls join direction.
    - `hint("broadcast")` and other optimizer hints are accepted.
    - `repartition(n)` and `coalesce(n)` preserve the partition count as a hint. When `snowflake.repartition.for.writes` is enabled, the hint controls how many files `COPY INTO` writes. `coalesce(1)` before a write produces a single output file.

   Leave this code as-is without adding any comment — the semantics are close enough to native Spark that no annotation is needed. Do NOT describe these as "no-op" in comments or reports.

5. **No-Op Configs**: Cluster/runtime-resource Spark configs that SCOS does not read (category: "No-Op Config") are silently ignored — they have no effect but do not cause errors (Snowflake's warehouse manages compute). The Phase 0.5 recipe `spark_config_noop_annotate` already flags these with `# SCOS-WARN: [SPRKCNTPY1000] ... no-op on SCOS`; **do not undo that annotation and do not re-annotate** — the line is safe to leave as-is (or delete). Examples: `spark.executor.memory`, `spark.driver.memory`, `spark.dynamicAllocation.enabled`, `spark.shuffle.service.enabled`. **Caution:** not every config is a no-op — `spark.sql.*` semantic knobs (`spark.sql.ansi.enabled`, `spark.sql.session.timeZone`, `spark.sql.storeAssignmentPolicy`, ...), all `snowpark.connect.*`/`snowflake.*` knobs, `spark.app.name`, `spark.jars`, and `spark.hadoop.fs.s3a.*` credentials **are honored** and must be preserved. See `../../references/python/spark-config.md` for the full honored-vs-ignored classification, the SCOS default deviations from Spark, and SCOS-specific knobs worth adding for parity.

6. **Missing Fixes**: If `fix` is null, use the `root_cause` to determine the best workaround. If unsure, add a TODO comment: `# SCOS: TODO - <explanation>`.

7. **File Reads**: For file read operations (`.read.csv`, `.read.json`, `.read.parquet`, `.load`), check the path being read:
    - **Already using Snowflake stage** (`@STAGE_NAME/...` or `@~/...`): No comment needed, this is optimal.
    - **External cloud storage** (paths starting with `s3://`, `s3a://`, `gs://`, `abfs://`, `wasb://`, `adl://`): Add performance comment recommending Snowflake stage upload.
    - **Local paths or variables**: If the path is a variable, trace it to determine if it's external cloud storage. Add performance comment recommending Snowflake stage upload for both.

    ```python
    # SCOS: Performance tip - Consider uploading this file to a Snowflake stage
    # for faster processing. Use: session.file.put("local_path", "@STAGE_NAME/path")
    df = spark.read.csv("s3://bucket/path/file.csv", header=True)
    ```

8. **Snowflake Connector I/O (`.format("snowflake")`) — do NOT hand-migrate**: connector reads/writes are converted deterministically by the Phase 0.5 recipe `snowflake_connector_io_to_snowflake_session_rewrite`, so you normally will not see raw connector code. Your rules:
    - **NEVER** rewrite a connector read to a **bare `spark.sql(...)`** — it is parsed as Spark SQL and breaks on Snowflake-specific syntax. Native Snowflake SQL must go through `SnowflakeSession(<session>).sql(...)`.
    - If a line already carries a `snowflake_connector_io_to_snowflake_session_rewrite` marker, it is done — leave it alone.
    - Your ONLY action here: finish a `# SCOS: TODO - [SPRKCNTPY5400-IO]` the recipe left behind (options it could not statically read, e.g. `.options(**cfg)`), using the target form and mapping below.

    **Target form (for finishing a TODO):**
    ```python
    from snowflake.snowpark_connect.snowflake_session import SnowflakeSession
    sf = SnowflakeSession(spark)
    sf.use_database("BRAND_PLK"); sf.use_schema("STORES"); sf.use_warehouse("ANALYSIS_PLK")
    rest_data_info = sf.sql("""
        select store_id as rest_no, full_address as rest_address
        from STORES where status = 'OPEN'
    """)
    ```

    **Mapping:**
    - `.option("query", <q>)` → `SnowflakeSession(<session>).sql(<q>)`
    - `.option("dbtable", T)` → `SnowflakeSession(<session>).sql("SELECT * FROM T")`
    - write `.option("dbtable", T)[.mode(M)].save()` → `df.write[.mode(M)].saveAsTable(T)`
    - `sfDatabase`/`sfSchema`/`sfWarehouse`/`sfRole` → `use_database`/`use_schema`/`use_warehouse`/`use_role`
    - the `SnowflakeSession` import appears once per file

9. **Wildcard/Glob Patterns in File Reads**: Wildcard patterns (e.g., `*.json`, `*.csv`, `*.parquet`, `**/*.json`) in `spark.read.json()`, `spark.read.csv()`, `spark.read.parquet()`, or `.load()` are **not supported** in SCOS. They will fail at runtime with `SparkConnectGrpcException: AssertionError (ERROR CODE: 5001)`.

    **Detection**: Look for file read calls where the path argument contains `*`, `?`, `[`, or other glob characters:
    ```python
    # These patterns WILL FAIL in SCOS:
    df = spark.read.json("@MY_STAGE/*.json")
    df = spark.read.csv("s3://bucket/data/*.csv")
    df = spark.read.parquet("/path/to/**/*.parquet")
    df = spark.read.json("data/prefix_*.json")
    ```

    **Fix**: Replace wildcard reads with explicit file lists. Enumerate the individual files that the glob would match and pass them as a list:
    ```python
    # BEFORE (not supported in SCOS):
    df = spark.read.json("@MY_STAGE/*.json")

    # AFTER (supported):
    df = spark.read.json([
        "@MY_STAGE/file1.json",
        "@MY_STAGE/file2.json",
        "@MY_STAGE/file3.json"
    ])
    ```

    If the exact file list is not known at migration time (e.g., the wildcard was reading dynamically generated files), add a TODO with the fix pattern:
    ```python
    # SCOS: TODO - [SPRKCNTPY1000] Wildcard glob "*.json" is not supported in SCOS.
    # Replace with explicit file list: spark.read.json(["@STAGE/f1.json", "@STAGE/f2.json"])
    df = spark.read.json("@MY_STAGE/*.json")
    ```

10. **UDF Serialization (ALL UDF patterns: `udf()`, `@udf`, `@pandas_udf`, `applyInPandas`, `mapInPandas`, factory-style `udf()` calls)**: When the workload uses UDFs that call helper functions, reference module-level variables, or import external modules, these will fail on Snowflake's server-side worker because cloudpickle serializes function references that point to the workload module (which doesn't exist on the server). **Read** `../../references/python/udf-dependencies.md` (Part 2) for the tiered fix approach:
    - **Tier 1 (Preferred)**: Use `snowpark.connect.udf.packages` for Anaconda packages and `snowpark.connect.udf.python.imports` for custom modules uploaded to a stage. Import inside the UDF body.
    - **Tier 2**: For UDFs with simple logic (including factory-style `udf()` calls that return `udf(fn, type)`), keep all logic self-contained (inline) inside the closure body. Move all imports (`import datetime`, `import ast`, etc.), constants, and helper functions inside the UDF function body so cloudpickle captures them by value. Do NOT replace working UDFs with built-in SQL functions — apply the minimal fix to make the closure self-contained.
    - **Tier 3**: For complex UDFs that call many tightly-coupled helper functions in the same file, use the factory function pattern (to capture data in closures) and `__module__ = "__main__"` patching (to force serialization by value) on the UDF and **all** helper functions in its call chain.

    ```python
    # Example: Tier 3 — factory + __module__ patching
    def make_process_udf(config_dict):
        """Factory captures config in closure."""
        def process_udf(pdf):
            result = helper_a(pdf, config_dict)
            return helper_b(result)
        return process_udf

    process_udf = make_process_udf(my_config)
    for _fn in [process_udf, helper_a, helper_b]:
        _fn.__module__ = "__main__"

    result = df.groupby("key").applyInPandas(process_udf, schema=output_schema)
    ```

11. **Server-Side Package Availability**: When UDFs import third-party packages, verify they are available in Snowflake's Anaconda channel or use PyPI via artifact repository. **Read** `../../references/python/udf-dependencies.md` (Part 1) for details. If a package is missing from Anaconda:
    - Use PyPI via artifact repository (recommended): `spark.conf.set("snowpark.connect.artifact_repository", "snowflake.snowpark.pypi_shared_repository")`
    - Or replace with a stdlib/numpy-only implementation.
    - Or upload a pure-Python package via `snowpark.connect.udf.python.imports`.

    To check Anaconda availability:
    ```sql
    SELECT * FROM INFORMATION_SCHEMA.PACKAGES
    WHERE LANGUAGE = 'python' AND PACKAGE_NAME ILIKE '%<package>%';
    ```

    To use PyPI:
    ```python
    spark.conf.set("snowpark.connect.artifact_repository", "snowflake.snowpark.pypi_shared_repository")
    spark.conf.set("snowpark.connect.udf.packages", "[package1, package2]")
    ```

12. **`checkpoint()` Not Supported**: `DataFrame.checkpoint()` is not supported in SCOS and will fail at runtime. Replace it with `cache()`, which provides equivalent in-memory persistence behavior.

    ```python
    # BEFORE (not supported in SCOS):
    df = spark.createDataFrame(data, schema)
    df.checkpoint(False)

    # AFTER (supported):
    df = spark.createDataFrame(data, schema)
    # SCOS: [SPRKCNTPY1000] checkpoint() not supported — replaced with cache()
    df.cache()
    ```

    This also applies to `localCheckpoint()` and any variant of `checkpoint(eager)`. In all cases, replace with `cache()`.

13. **Map Column Subscript with Column Key**: Using bracket indexing on a map column with another column as the key (e.g., `map_col[col("key")]`) is **not supported** in Spark Connect. The `Column.__getitem__` method only accepts literal values, not other `Column` objects. It fails at runtime with `PySparkTypeError: [UNSUPPORTED_DATA_TYPE] Unsupported DataType 'Column'`.

    **Detection**: Look for bracket indexing on a map-typed column where the index is a `col()` or `Column` expression:
    ```python
    # These patterns WILL FAIL in SCOS:
    result = df.withColumn("val", category_map[col("category_code")])
    result = df.select(my_map_col[col("lookup_key")])
    result = df.withColumn("v", create_map(lit("a"), lit(1), lit("b"), lit(2))[col("key")])
    ```

    **Fix**: Replace bracket indexing with `element_at()` from `pyspark.sql.functions`, which accepts `Column` arguments and works in both classic and Connect modes:
    ```python
    from pyspark.sql.functions import element_at

    # BEFORE (not supported in SCOS):
    result = df.withColumn("val", category_map[col("category_code")])

    # AFTER (supported):
    # SCOS: [SPRKCNTPY1000] Map column subscript with Column key replaced
    # with element_at() for Spark Connect compatibility
    result = df.withColumn("val", element_at(category_map, col("category_code")))
    ```

    **Note**: Bracket indexing with **literal** keys (e.g., `map_col["some_string"]`) still works. Only `Column`-typed keys trigger this error.

14. **SparkContext Property Access**: Direct access to `SparkContext` properties (e.g., `spark.sparkContext.appName`, `spark.sparkContext.master`, `spark.sparkContext.getConf()`) is not supported in Snowpark Connect. These properties either have static fallback values or should be replaced with configuration lookups.

    ```python
    # BEFORE (not supported in SCOS):
    app_name = spark.sparkContext.appName
    master = spark.sparkContext.master

    # AFTER (supported):
    # SCOS: [SPRKCNTPY1000] SparkContext property replaced with static fallback
    app_name = spark.conf.get("spark.app.name", "scos-app")
    master = "snowflake"  # SCOS runs on Snowflake, no master URL
    ```

14a. **Legacy SQL/Hive entry points (`sqlContext` / `SQLContext` / `HiveContext`)**: These were deprecated in Spark 2.0 and are **removed in Spark Connect / SCOS** — their methods now live on the SparkSession `spark`. Rewrite every reference; tag with `SPRKCNTPY3500`.

    ```python
    # BEFORE (not available in SCOS):
    # from pyspark.sql import SQLContext, HiveContext
    # sqlContext = SQLContext(sc)
    # df = sqlContext.sql("SELECT * FROM t")
    # rows = sqlContext.read.parquet("@stage/data")

    # AFTER — use the active `spark` session directly:
    # SCOS: [SPRKCNTPY3500] sqlContext/HiveContext removed in Spark Connect; use spark
    df = spark.sql("SELECT * FROM t")
    rows = spark.read.parquet("@stage/data")
    ```

    Mapping: `sqlContext.sql` → `spark.sql`, `sqlContext.read` → `spark.read`,
    `sqlContext.table` → `spark.table`, `sqlContext.createDataFrame` →
    `spark.createDataFrame`. `HiveContext` Hive-catalog access maps to Snowflake's
    native catalog (fully-qualified `db.schema.table`).

15. **Hadoop Filesystem Access**: Hadoop filesystem patterns (`spark.sparkContext._jvm.org.apache.hadoop`, `FileSystem.get()`, `hdfs://` paths) are not available in Snowpark Connect. Replace with Snowflake stage operations or cloud-native SDK calls.

    ```python
    # BEFORE (not supported in SCOS):
    fs = spark.sparkContext._jvm.org.apache.hadoop.fs.FileSystem.get(spark.sparkContext._jsc.hadoopConfiguration())

    # AFTER:
    # SCOS: TODO - [SPRKCNTPY1000] Hadoop filesystem access not available in SCOS.
    # Replace with Snowflake stage operations (session.file.put/get) or cloud SDK (boto3/azure-storage).
    ```

16. **JVM-Only Library Imports (Deequ, pydeequ)**: Libraries that depend on the JVM (Deequ, pydeequ, Hive LLAP connectors) are not available in Snowpark Connect. Replace with native DataFrame validation or Snowflake data quality features.

    ```python
    # BEFORE (not supported in SCOS):
    from pydeequ.checks import Check
    check = Check(spark, "data quality")

    # AFTER:
    # SCOS: TODO - [SPRKCNTPY2500] pydeequ/Deequ requires JVM. Replace with native
    # DataFrame checks: df.filter(col("x").isNull()).count() == 0
    ```

17. **ML Pipeline Patterns**: PySpark ML pipeline components (`VectorAssembler`, `Pipeline`, `CrossValidator`, etc.) are not supported in Snowpark Connect. Flag for manual migration to Snowpark ML or scikit-learn.

    ```python
    # SCOS: TODO - [SPRKCNTPY2500] ML pipeline requires manual migration.
    # Consider Snowpark ML (snowflake.ml) or scikit-learn as alternatives.
    ```

18. **`@udtf` — Natively Supported (enable compatibility mode)**: PySpark's `@udtf` decorator is **natively supported** in SCOS. No structural rewrite is needed — the SCOS runtime auto-translates the Spark-style `eval()` method to Snowpark's UDTF handler contract when compatibility mode is enabled.

    **Fix**: enable compatibility mode once per session. Keep the class and `eval()` as written.

    ```python
    # Keep the PySpark-style @udtf class AS-IS. Only add the config once per session:
    spark.conf.set("snowpark.connect.udtf.compatibility_mode", "true")
    # Optional, for vectorized UDTFs:
    # spark.conf.set("spark.sql.execution.pythonUDTF.arrow.enabled", "true")

    @udtf(returnType="id: int, doubled: int")
    class DoubleUDTF:
        def eval(self, id, val):
            yield id, val * 2

    spark.udtf.register("double_udtf", DoubleUDTF)
    ```

    **UDAF / `PandasUDFType.GROUPED_AGG`** still requires structural conversion (there is no server-side UDAF mapping at the time of writing). Convert those to Snowpark UDAF: handler class with `accumulate()` / `merge()` / `finish()` methods, registered via `session.udaf.register()`.

19. **Delta Lake Patterns**: Delta Lake operations (`DeltaTable.forPath()`, `MERGE INTO`, `.format("delta")`) are not available in Snowpark Connect. Replace with Snowflake table operations.

    ```python
    # BEFORE (not supported in SCOS):
    from delta.tables import DeltaTable
    dt = DeltaTable.forPath(spark, "/path/to/delta")

    # AFTER:
    # SCOS: TODO - [SPRKCNTPY1000] Delta Lake not available. Use Snowflake tables:
    # df = spark.sql("SELECT * FROM my_table")
    ```

20. **Lazy View Re-Evaluation**: When a `createOrReplaceTempView()` is defined once but referenced multiple times in downstream operations, Snowpark Connect may re-evaluate the underlying query each time. Insert `.cache()` after view creation to materialize and prevent redundant computation.

    ```python
    # BEFORE (potential performance issue):
    df.createOrReplaceTempView("my_view")
    result1 = spark.sql("SELECT * FROM my_view WHERE x > 1")
    result2 = spark.sql("SELECT COUNT(*) FROM my_view")

    # AFTER:
    # SCOS: Performance tip - cached view to prevent re-evaluation
    df.cache()
    df.createOrReplaceTempView("my_view")
    result1 = spark.sql("SELECT * FROM my_view WHERE x > 1")
    result2 = spark.sql("SELECT COUNT(*) FROM my_view")
    ```

21. **Memory Anti-Patterns & Known Issues**: Patterns like `.toPandas()` on large DataFrames, `.collect()` in loops, or broadcasting large objects can cause memory issues in Snowpark Connect. The analyzer flags these with specific `how_to_fix` guidance — follow the provided fix. Common patterns:
    - `.toPandas()` on large DataFrames → add `.limit(N)` or use `to_pandas_batches()`
    - `.collect()` in tight loops → refactor to use DataFrame operations
    - `broadcast()` with large tables → let Snowflake's optimizer handle join strategies

22. **`withColumnRenamed` to an already-existing column name**: `df.withColumnRenamed("a", "b")` when `b` already exists raises `[COLUMN_ALREADY_EXISTS] The column 'b' already exists` on SCOS. Open-source Spark and Databricks instead keep both columns (producing two `b`s), so Databricks-origin code that does this runs there but fails on SCOS. `.drop("b")` the pre-existing column **before** the rename, or rename to a unique name.

23. **`TIMESTAMP_LTZ`/`TIMESTAMP_TZ` cannot be unloaded to Parquet**: Writing a DataFrame that contains a `TIMESTAMP_LTZ`/`TIMESTAMP_TZ` column (e.g. from `F.current_timestamp()`) to **Parquet** fails with `100171 (22000): Error encountered when unloading to PARQUET: TIMESTAMP_TZ and LTZ types are not supported for unloading to Parquet`. Writing the same frame to a **table** (`saveAsTable`/`insertInto`) succeeds — this is only a Parquet-*unload* limitation, not a general write failure (verified on SCOS: `saveAsTable` of `current_timestamp()` is OK). If a Parquet write is required, convert the column to a non-LTZ type first: `F.date_format(ts, "yyyy-MM-dd HH:mm:ss.SSSSSS")` (string) or `ts.cast("timestamp_ntz")`.

24. **`ABS`/numeric function applied to a `DATE` column**: `F.abs(date_col)` fails with `001044 (42P13): SQL compilation error: Invalid argument types for function 'ABS': (DATE)`. Direct date arithmetic is fine: `datediff(a, b)` returns an **int**, `a - b` (date subtraction) returns an **interval**, and `abs(...)` over either works on SCOS (verified). A **bare `DATE` passed to `abs`** directly is an SMA mistranslation or latent bug — fix the upstream expression so `abs` wraps a numeric magnitude (e.g. `abs(datediff(a, b))`), not a date.

    **There is also a codegen path that injects `ABS(DATE)` with no `abs` in the source: a two-argument `TO_CHAR`/`TO_VARCHAR` applied to a `DATE`.** `F.expr("TO_CHAR(d, 'YYYYMMDD')")`, `TO_VARCHAR(d, fmt)`, and `TO_CHAR(TO_DATE(s,'YYYY-MM-DD'), 'YYYYMMDD')` all fail with the same `Invalid argument types for function 'ABS': (DATE)` — for a date column, `TO_DATE(...)`, or `current_date()`, with **any** format string. (`TO_CHAR` on a **number** is fine; the DATE overload is the problem.) **Fix: format dates with PySpark `F.date_format(col, '<java pattern>')`** (`'yyyyMMdd'`, `'yyyy-MM-dd'`, ...) — works in every case — or `CAST(col AS STRING)` when the default ISO output is acceptable. Do **not** rewrite `F.date_format` into `TO_CHAR` to "reformat a date"; that is backwards and triggers this failure. *(verified on SCOS 1.32.0.)*

25. **Pandas List Column → `StringType()` in `createDataFrame` (SNOW-3590200)**: When `spark.createDataFrame(pandas_df, schema)` ingests a pandas column that holds **Python lists/arrays** (object dtype) and the schema maps it to `StringType()`, OSS Spark (Classic) silently coerces each list to a string via `str()`, but **SCOS raises** an error. SCOS is built on Spark Connect, which uses the Arrow serialization path by default (`spark.sql.execution.arrow.pyspark.enabled`); PyArrow infers the column as `pa.list_(...)` and there is no `list → StringType()` coercion. This is a fundamental Spark-Connect-vs-Classic difference and is **not fixable inside SCOS** — the migration agent flags it so the workaround can be applied. **Fix:** pre-cast the list column to string **before** building the DataFrame, then annotate. Only applies to list/array-valued columns mapped to `StringType()`; scalar columns are unaffected.

    **BEFORE (works in Spark Classic, fails in SCOS):**
    ```python
    pandas_df = pd.DataFrame({"id": [1, 2], "value": [[1, 2, 3], [4, 5]]})
    schema = StructType([
        StructField("id", StringType(), True),
        StructField("value", StringType(), True),
    ])
    df = spark.createDataFrame(pandas_df, schema=schema)
    ```

    **AFTER:**
    ```python
    pandas_df = pd.DataFrame({"id": [1, 2], "value": [[1, 2, 3], [4, 5]]})
    # SCOS: pandas-list-to-stringtype - the Arrow createDataFrame path has no
    # list->StringType coercion (SNOW-3590200); cast the list column to str first.
    pandas_df["value"] = pandas_df["value"].astype(str)
    schema = StructType([
        StructField("id", StringType(), True),
        StructField("value", StringType(), True),
    ])
    df = spark.createDataFrame(pandas_df, schema=schema)
    ```

26. **Null `array`/`struct` read as VARIANT null → `isNotNull()` filter leaks a row**: SCOS reads a parquet/source NULL `array<...>`/`struct<...>` value as a **VARIANT null** (JSON `null`), not a SQL `NULL`. So `F.col("X").isNotNull()` returns **True** for a null array/struct on SCOS (it is False on Spark) — a row that Spark filters out leaks through on SCOS, producing an extra output row (a real, off-by-one value divergence vs the Phase A baseline, **not** cosmetic). When a filter/dedup guards an `array<struct<...>>` (or `struct`) column with `isNotNull()`, guard with **both** `isNotNull()` AND `F.size(F.col("X")) > 0` — `size()` returns 0/negative for a VARIANT null and correctly excludes the row.

    **BEFORE (extra row leaks on SCOS):**
    ```python
    df = df.filter(F.col("items").isNotNull())
    ```

    **AFTER:**
    ```python
    # SCOS: null array reads as VARIANT null, so isNotNull() is True for it;
    # add size()>0 so empty/null arrays are excluded as they are on Spark.
    df = df.filter(F.col("items").isNotNull() & (F.size(F.col("items")) > 0))
    ```

27. **Column names round-trip UPPERCASE → exact-case `df.columns` membership breaks**: after a DataFrame is written and re-read through Snowflake (`saveAsTable` then `spark.table`, or any Snowflake-backed source), its column identifiers come back **upper-cased** (Snowflake folds unquoted identifiers), whereas Spark Classic preserves the original (usually lowercase) case. `F.col("x")`, `df.filter("x = …")`, and `df.select("x")` stay **case-insensitive** on SCOS and keep working — no rewrite needed. What breaks is code that inspects `df.columns` / `df.schema.names` and does an **exact-case** comparison: `if "my_col" in df.columns:`, `[c for c in df.columns if c == "my_col"]`. On SCOS `df.columns` is `["MY_COL"]`, so the lowercase check is silently False and a branch or column is dropped — a real value divergence, not cosmetic. **Fix: lower-case BOTH sides** — `if "my_col".lower() in [c.lower() for c in df.columns]:` (lower-casing the search key too, so a mixed-case literal like `"My_Col"` also matches). Only exact-case `.columns`/`.schema.names` string matching needs this; `col()`/`select()`/`filter()` do not.

    **BEFORE (silently False on SCOS — `df.columns` is `["MY_COL"]`):**
    ```python
    if "my_col" in df.columns:
        df = df.withColumn("flag", F.lit(1))
    ```

    **AFTER:**
    ```python
    # SCOS: Snowflake round-trip upper-cases column identifiers; compare case-insensitively.
    if "my_col".lower() in [c.lower() for c in df.columns]:
        df = df.withColumn("flag", F.lit(1))
    ```

## Issue Processing Checklist

After processing all issues from `analysis.json`, verify completeness:

- [ ] Every issue in `analysis.json` has been reviewed and carries a verdict
  (an inline `# SCOS:` comment **or** a `resolution` field)
- [ ] All high-risk issues (`final_risk` >= 0.7) have fixes applied, a `TODO`, or a `resolution: "safe"` **with** a `resolution_reason`
- [ ] All medium-risk issues (`final_risk` >= 0.3) have fixes, TODO comments, or a `resolution`
- [ ] All low-risk issues (`final_risk` < 0.3) have fixes or a `resolution`
- [ ] No issue marked `resolution: "safe"` has an empty `resolution_reason`
- [ ] **Recipe-aware checks** (when `kind` field is present on issues):
  - [ ] No `kind="recipe_validated"` issue was re-edited (the recipe's
    output must round-trip unchanged)
  - [ ] Every `kind="recipe_incomplete"` issue with a non-null
    `suggested_fixer_action` had that action applied verbatim (or was
    explicitly downgraded to a TODO with reason)
  - [ ] Every `kind="recipe_adjacent"` issue has a `# SCOS: recipe-coverage
    gap` annotation naming `suggested_recipe_id`

### Files with No Issues

For files in the manifest that had **no issues** reported by the analysis tool: no changes are needed in this step. These files will still be processed for import updates and migration headers in Phase 3 — **do not** add a migration header yourself here. Confirm you have accounted for them:

```
Step 3 Summary:
  Files with fixes applied: N
  Files with no issues:     M
  Total in manifest:        N + M  ← must match manifest count
```

**Do NOT proceed to import updates until ALL issues have been addressed and the file count is confirmed.**

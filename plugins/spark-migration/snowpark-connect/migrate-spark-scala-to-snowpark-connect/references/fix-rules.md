# SCOS Fix Rules Reference — Scala

Rules for fixing SCOS compatibility issues found during analysis of Scala workloads. The fixer agent reads this document when applying fixes to migrated files.

**Related references:**
- `../../references/scala/rdd-conversion.md` — RDD-to-DataFrame conversion rules and examples (required for Rule 2)
- `../../references/scala/udf-dependencies.md` — UDF serialization fix approach for Scala (required for Rule 10)
- `../../references/scala/ewi-codes.md` — Official SMA EWI code scheme for Scala (required for `// SCOS:` comment tagging)

---

## Pre-Fix: Read EWI Codes

Before applying fixes, read `../../references/scala/ewi-codes.md` to understand the official SMA EWI code scheme for Scala. When adding `// SCOS:` comments, include the relevant EWI code where possible. For example:
- `// SCOS: [SPRKCNTSCL1500] RDD operation converted to DataFrame`
- `// SCOS: TODO - [SPRKCNTSCL2500] ML element requires manual migration`

---

## Per-Issue Processing

For EACH issue in `analysis.json`:

1. **Locate the issue**: Find the code at `file` and `lines` in the copied directory.
2. **Assess the risk**: Check the `final_risk` value.
3. **Apply the appropriate action** based on the rules below.
4. **Document the action**: Add a `// SCOS:` comment **or** record a `resolution` verdict on the issue in `analysis.json` (see "Recording resolutions in `analysis.json`") — **except** for no-op operations and configs (Rules 4 and 5), which need neither.

---

## Rules for Fixing based on Risk Score

1. **Must Fix (`final_risk` >= 0.7)**: Apply a fix or rewrite. If impossible, add `// SCOS: TODO - <explanation>`. If you review it and it genuinely needs no action, record `resolution: "safe"` **with** a concrete `resolution_reason` in `analysis.json` (see below).
2. **Should Fix (0.3 <= `final_risk` < 0.7)**: Apply fix if suggested, else `// SCOS: TODO`. If genuinely safe, record `resolution: "safe"` in `analysis.json`.
3. **Fix if possible (`final_risk` < 0.3)**: Fix if possible, else record `resolution: "safe"` in `analysis.json` (no inline comment needed) or leave a brief `// SCOS: <explanation>`.

---

## Recording resolutions in `analysis.json`

After you process an issue, write your verdict back onto that issue object in
`analysis.json` by adding two fields. This is the structured, machine-readable
record the gates (`verify_phase.py --phase 2`) and the validation skill rely on —
it is the alternative to leaving a `// SCOS: ...reviewed, safe` comment in the
source for every finding. This mirrors the PySpark path 1:1.

| Field | Values | Meaning |
|---|---|---|
| `resolution` | `"fixed"` | You applied a fix or rewrite (also leave the inline `// SCOS:` comment). |
| | `"todo"` | Needs manual follow-up (also leave the inline `// SCOS: TODO` comment). |
| | `"safe"` | Reviewed; no action needed. **No inline comment.** Requires `resolution_reason`. |
| | `"perf"` | Performance tip only (also leave the inline `// SCOS: Performance tip` comment). |
| `resolution_reason` | free text | Why. **Mandatory for `"safe"`**; recommended for the rest. |

Example — an `.isEmpty` finding the analyzer flags as a possible `DataFrame.isEmpty`,
but the receiver is a Scala collection, so it is actually fine:

```json
{
  "file": "src/main/scala/com/flashfood/petl/util/Image.scala",
  "lines": "40-40",
  "final_risk": 0.8,
  "resolution": "safe",
  "resolution_reason": "receiver is a scala.collection Map (bound via `val m: Map[..]`), not a Spark DataFrame; Scala collection .isEmpty is fully supported"
}
```

Rules for `resolution`:

- **`"safe"` requires a concrete, code-grounded `resolution_reason`.** The Phase-2
  gate emits a `safe_without_reason` failure for any high-risk
  (`final_risk` >= 0.7) issue marked `safe` with an empty reason, which
  re-triggers the fixer. Do not use `"safe"` as a shortcut to silence a finding
  you have not actually reasoned through.
- **Never upgrade an "unverified" verdict into a confident `"safe"`.** If
  `analysis.json` says to *verify* something and you have no grounding to confirm
  it, keep it as `// SCOS: TODO - verify ...` with `resolution: "todo"`. Do **not**
  assert "supported / safe" based on a method name alone.
- A recorded `resolution` (`fixed`/`safe`/`todo`/`perf`) satisfies the high-risk
  coverage gate **without** an inline marker within ±3 lines of the issue, so a
  legitimately-safe finding no longer forces a noisy comment or a spurious fixer
  re-dispatch.

---

## General Rules

### Rule 1: Use the Tool's Fix
If the issue provides a `fix` value, use it.

### Rule 2: Handle RDDs
RDD usage (`category: "RDD"`, `final_risk` near 1.0) splits into three buckets — **the analyzer issue carries `"unsupported": true|false` to tell you which.** **Read** `../../references/scala/rdd-conversion.md` for the full rules and verified examples.

- **Unsupported (`"unsupported": true`)** — `.rdd` with a closure or partition-level op, `mapPartitions`/`foreachPartition`, `SparkContext` file/accumulator APIs: no DataFrame equivalent. Do **NOT** rewrite or invent a workaround. Preserve the original line and prepend a `// SCOS:` marker (keep the literal `manual refactor` phrase so the Phase 2b gate quarantines the file):
  ```scala
  // SCOS: [SPRKCNTSCL1500] RDD API '.rdd.getNumPartitions' is not supported in Snowpark Connect; manual refactor required.
  println(df.rdd.getNumPartitions)
  ```
  (The Phase 2b gate quarantines these and reports them as manual items, not failures.)
- **Drop-the-hop (`"unsupported": false`, issue `fix` mentions "drop the .rdd accessor")** — the `.rdd` accessor leads to a method that exists directly on DataFrame. Drop the `.rdd` hop and call the same method on the DataFrame:
  - `df.rdd.count()` → `df.count()`; `df.rdd.isEmpty()` → `df.isEmpty()`; `df.rdd.collect()` → `df.collect()`; `df.rdd.first()` → `df.first()`; `df.rdd.take(n)` → `df.take(n)`; `df.rdd.toLocalIterator()` → `df.toLocalIterator()`
  - `df.rdd.cache()` / `persist()` → `df.cache()`; `df.rdd.unpersist()` → `df.unpersist()`
  - `df1.rdd.union(df2.rdd)` → `df1.union(df2)`; `df.rdd.distinct()` → `df.distinct()`; `df1.rdd.intersection(df2.rdd)` → `df1.intersect(df2)`; `df1.rdd.subtract(df2.rdd)` → `df1.exceptAll(df2)`
  - `df.rdd.sample(wr,f)` → `df.sample(wr,f)`; `df.rdd.repartition(n)` → `df.repartition(n)`;  `df.rdd.coalesce(n)` → `df.coalesce(n)`
- **Convertible (`"unsupported": false`, other patterns)** — rewrite to the DataFrame API using the recipe in the issue's `"fix"` field (the analyzer now emits a specific recipe per pattern). Key conversions:
  - `sc.parallelize(Seq[tuple])` → `spark.createDataFrame(seq).toDF(names…)` (**never** `Tuple1.apply` on tuples).
  - `sc.parallelize(Seq[primitive])` → `spark.createDataFrame(seq.map(Tuple1.apply)).toDF("value")`.
  - `createDataFrame(sc.parallelize(Seq[Row]), schema)` / `emptyRDD[Row]` → `spark.createDataFrame(seq.asJava, schema)` (+ `import scala.collection.JavaConverters._`). **Never** nest `createDataFrame`.
  - `reduceByKey(_ + _)` / `groupByKey` / `countByKey` → `groupBy(key).agg(...)`.
  - `sortByKey()` → `df.orderBy(col("key"))`; `sortByKey(ascending=false)` → `df.orderBy(col("key").desc)`.
  - `sampleByKey(wr, fractions)` → `df.sampleBy("key", fractions, seed)`.
  - `mapValues(f)` → `df.withColumn("value", <col-expr from f>)` (translate the closure to a column expression).
  - `flatMapValues(f)` → `df.withColumn("value", <col-expr>).select(explode(col("value")))`.
  - `rdd1.join(rdd2)` → `df1.join(df2, Seq("key"))`; `leftOuterJoin` → `"left"`; `rightOuterJoin` → `"right"`; `fullOuterJoin` → `"outer"`; `cartesian` → `df1.crossJoin(df2)`; `subtractByKey` → `"left_anti"`.
  - `keys()` → `df.select(col("key"))`; `values()` → `df.select(col("value"))`.
  - `takeOrdered(n)` → `df.orderBy(col.asc).limit(n).collect()`; `top(n)` → `df.orderBy(col.desc).limit(n).collect()`.
  - `zipWithIndex()` → `row_number().over(Window.orderBy(<col>)) - 1`; `zipWithUniqueId()` → `monotonically_increasing_id()`.
  - `countByValue()` → `df.groupBy(df.columns.map(col): _*).count().collect()`.
  - `saveAsTextFile(path)` → `df.write.mode("overwrite").text(path)`.
  - `randomSplit(weights)` — **`df.randomSplit()` is itself unsupported in SCOS**; use `df.sample(fraction, seed)` with complementary fractions instead.
  - `sc.broadcast(v)` scalar → use `v` directly; `sc.broadcast(df)` join hint → `df.hint("broadcast")`.

**CRITICAL:** never fabricate an RDD shim to force compilation — no `.rdd` re-introduction, no nested `createDataFrame`, no `Tuple1` wrapping of tuples. A correct EWI is better than type-incorrect or semantically-wrong code.

### Rule 3: Unsupported Formats
Change file formats if required (ORC/Avro → Parquet). Add a downstream impact warning:
```scala
// SCOS: [SPRKCNTSCL1000] ORC format replaced with Parquet — ORC not supported in SCOS
// SCOS: TODO - Verify downstream consumers can accept Parquet instead of ORC
df.write.mode("overwrite").parquet(path)
```

### Rule 4: No-Op Operations
`hint()`, `repartition()`, `coalesce()` are silently ignored in SCOS. Leave as-is, **no comment**.

### Rule 5: No-Op Configs
Unsupported Spark configs (`spark.sql.shuffle.partitions`, `spark.executor.memory`, etc.) are silently ignored. Leave as-is, **no comment**.

### Rule 6: Missing Fixes
If `fix` is null, use `root_cause` for a workaround. If unsure: `// SCOS: TODO - <explanation>`.

### Rule 7: File Reads
Check the path in `.read.csv`, `.read.json`, `.read.parquet`, `.load`:
- **Snowflake stage** (`@STAGE_NAME/...`): No comment needed.
- **Cloud storage** (`s3://`, `gs://`, `abfs://`): Add performance tip recommending stage upload.
- **Local/variable paths**: Add performance tip.

```scala
// SCOS: Performance tip - Consider uploading to a Snowflake stage
val df = spark.read.option("header", "true").csv("s3://bucket/path/file.csv")
```

### Rule 7b: Delta Format Reads/Writes (Must Fix — `final_risk >= 0.9`)

`.format("delta")` is **not supported** in Snowpark Connect. Every Delta read and write must be
rewritten to the Snowflake-native equivalent. This is a **must-fix** — do not leave a TODO.

**Delta reads → `spark.read.table()`:**

```scala
// BEFORE:
val legs = spark.read.format("delta").load(stage + "fare_legs/")

// AFTER:
// SCOS: [SPRKCNTSCL1000] Delta format replaced with Snowflake table read — Delta not supported in SCOS
val legs = spark.read.table("fare_legs")
```

Table name inference: use the last meaningful path segment (strip trailing `/`, date partitions, `_delta_log`). If ambiguous, emit `// SCOS: TODO - [SPRKCNTSCL1000] confirm table name`.

**Delta writes → `saveAsTable()`:**

```scala
// BEFORE:
df.write.format("delta").mode("overwrite").save(stage + "settled_legs/")

// AFTER:
// SCOS: [SPRKCNTSCL1000] Delta write replaced with saveAsTable — Delta not supported in SCOS
df.write.mode("overwrite").saveAsTable("settled_legs")
```

**Path-based Parquet writes → `saveAsTable()` (also applies to `.write.save(path)`):**

Snowpark Connect cannot write Parquet to a local or cloud path. Rewrite all path-based writes:

```scala
// BEFORE:
df.write.mode("overwrite").parquet(outputPath)
df.write.save(outputPath)

// AFTER:
// SCOS: [SPRKCNTSCL1000] Path-based Parquet write replaced with saveAsTable — .write.parquet(path) not supported in SCOS
df.write.mode("overwrite").saveAsTable("output_table_name")
```

> **Note:** `sys.env.getOrElse(...)` paths feeding Delta/Parquet reads are also handled
> deterministically in Phase 3 (`update_imports_scala.py`). If you see
> `System.getProperty(...)` wrapping a Delta path after Phase 3, the Delta→table rewrite
> is still required here.

### Rule 8: Snowflake Connector I/O → SnowflakeSession / saveAsTable

**Phase 0.5 deterministic rule `ScosSnowflakeConnectorIO` handles the common literal-option cases automatically.** The LLM fixer is responsible for the remaining cases flagged with `SCOS: TODO`.

The Spark Snowflake connector (`.format("snowflake")` / `.format("net.snowflake.spark.snowflake")`) is unnecessary under SCOS — the workload already runs inside Snowflake. Replace with:

- **Reads** → `new SnowflakeSession(spark).sql(query)`. Never use bare `spark.sql(...)` for Snowflake-specific SQL: `spark.sql` is parsed as Spark SQL and breaks on Snowflake-specific syntax. `SnowflakeSession.sql()` wraps the statement with the `PRIVATE-SNOWFLAKE-SQL` pass-through marker.
- **Writes** → `df.write[.mode(m)].saveAsTable(tableName)`.

```scala
// BEFORE (Snowflake connector read):
val df = spark.read
  .format("snowflake")
  .option("query", "SELECT * FROM DB.SC.T WHERE id > 0")
  .load()

// AFTER:
// SCOS-RECIPE-INSERT-IMPORT: com.snowflake.snowpark_connect.client.SnowflakeSession
val df = new SnowflakeSession(spark).sql("SELECT * FROM DB.SC.T WHERE id > 0")

// BEFORE (Snowflake connector write):
df.write.format("snowflake").option("dbtable", "DB.SC.OUT").mode("overwrite").save()

// AFTER:
df.write.mode("overwrite").saveAsTable("DB.SC.OUT")
```

For session context (database/schema/role/warehouse) previously passed as `.option("sfDatabase", ...)`, use `SnowflakeSession` context methods — see Rule 24.

**Column-ambiguity (SCOS error 5004):** if connector I/O rewrites cause `AMBIGUOUS_REFERENCE` in Phase A/B validation, this is usually a **mock-schema problem** (a join seeds the column onto both legs), not a code defect. Fix in the data (schema repair via the data-synthesizer) before dispatching the migration-fixer. See the SCOS-runner agent for the full routing rule.

### Rule 9: Wildcard/Glob File Reads
Wildcard patterns (`*.json`, `*.csv`) in file reads are **not supported**. Replace with explicit file lists:
```scala
// BEFORE (fails in SCOS):
val df = spark.read.json("@MY_STAGE/*.json")

// AFTER:
val df = spark.read.json("@MY_STAGE/file1.json", "@MY_STAGE/file2.json")
```
If exact files unknown: `// SCOS: TODO - [SPRKCNTSCL1000] Wildcard glob not supported`.

### Rule 10: UDF Serialization (Scala)
UDFs referencing custom classes or non-serializable closures may fail. **Read**
`../../references/scala/udf-dependencies.md` for the full fix approach
(`addArtifact`, staged JARs, inline closures).

- **Option 1 (Dev)**: `REPLClassDirMonitor` for compiled class files
- **Option 2 (Prod)**: `spark.addArtifact(jarPath)` for JAR uploads
- **Option 3**: Staged JARs via `snowpark.connect.udf.java.imports`
- **Inline**: Keep simple UDF logic self-contained in anonymous functions with no
  enclosing-object references

### Rule 11: StructType in UDFs
In SCOS, `StructType` is converted to `Map` in UDFs instead of `Row`/`tuple`. Rewrite field access from numeric index (`e(0)`) to named access (`e("col1")`).

### Rule 12: checkpoint() Not Supported
Replace `checkpoint()` and `localCheckpoint()` with `cache()`:
```scala
// BEFORE:
df.checkpoint(false)

// AFTER:
// SCOS: [SPRKCNTSCL1000] checkpoint() not supported — replaced with cache()
df.cache()
```

> **Usually already done by Phase 0.5.** The deterministic pre-pass ships two
> context-aware checkpoint recipes, so the fixer normally only needs to handle
> what they miss:
> - `checkpoint_to_cache_rewrite` — default, non-iterative contexts → `cache()`
>   (this rule).
> - `dataframe_checkpoint_to_persist_rewrite` — checkpoints inside a `for`/`while`
>   loop → `persist(StorageLevel.MEMORY_AND_DISK)`, because `cache()`
>   (MEMORY_AND_DISK by default for DataFrames) can silently recompute on
>   executor eviction in iterative workloads. This intentionally diverges from
>   the single PySpark `dataframe_checkpoint_to_cache_rewrite` recipe.
>
> If you see `recipe_edits` entries for either recipe on a line, do **not**
> re-rewrite it — just verify the annotation is present.

### Rule 13: Scala Version Compatibility
If the workload uses Scala 2.13, add: `spark.conf.set("snowpark.connect.scala.version", "2.13")`. SCOS defaults to 2.12.

### Rule 14: Unsupported Save Modes
`Append` and `Ignore` save modes are not supported for CSV, JSON, Parquet, Text, XML. Replace with `Overwrite` or `ErrorIfExists`:
```scala
// SCOS: [SPRKCNTSCL1000] Append save mode not supported — replaced with overwrite
df.write.mode("overwrite").csv("@STAGE/output")
```

### Rule 15: Spark Catalyst / Internal APIs
Imports from `org.apache.spark.sql.catalyst.*` are not in the Spark Connect client JAR. Create local drop-in case classes:
```scala
// SCOS: [SPRKCNTSCL1000] Catalyst QualifiedTableName replaced with local case class
package com.myproject.model
case class QualifiedTableName(database: String, name: String) {
  override def toString: String = s"$database.$name"
}
```
**⚠️ CRITICAL**: Replace the import in ALL files that reference the type.

### Rule 16: Hadoop / HDFS APIs
`org.apache.hadoop.*` imports are not available. Remove and replace:

| HDFS Operation | SCOS Replacement |
|----------------|-----------------|
| `df.write.parquet(hdfsPath)` | `df.write.saveAsTable("db.table")` or `df.write.parquet("@stage/path")` |
| `spark.read.parquet(hdfsPath)` | `spark.read.table("db.table")` or `spark.read.parquet("@stage/path")` |
| `FileSystem.get(conf).exists(path)` | Remove — Snowflake manages table existence |
| `FileSystem.get(conf).delete(path)` | `spark.sql("DROP TABLE IF EXISTS db.table")` |

Remove `implicit hdfs: FileSystem` from method signatures. **Trace all callers** (Rule 20).

### Rule 16b: Data Lineage Libraries
Remove Spline (`za.co.absa.spline.*`), DataHub, OpenLineage agents. Remove `.enableLineageTracking()`. Snowflake provides native lineage.

### Rule 16c: Databricks-Specific Imports (`com.databricks.*`, `dbutils`) — MUST ANNOTATE

`com.databricks.*` imports and `dbutils` usage have no SCOS equivalent. **Do NOT silently drop them.** For every `import com.databricks.*` line that cannot be replaced, prepend an annotation comment:

```scala
// SCOS: [SPRKCNTSCL1100] Databricks-only import — no SCOS equivalent; remove or replace with Snowflake Session API
import com.databricks.dbutils_v1.{DBUtilsHolder, DBUtilsV1}
```

For `dbutils.*` call sites that survive (cannot be rewritten):

```scala
// SCOS: [SPRKCNTSCL1100] dbutils.fs / dbutils.widgets / dbutils.notebook have no SCOS equivalent — replace with Snowflake stage ops / session params / stored-proc calls
val path = dbutils.fs.ls("/mnt/data")
```

**Replacement guidance:**

| `dbutils` call | SCOS replacement |
|----------------|-----------------|
| `dbutils.fs.ls(path)` | Remove or use `@stage` path with `spark.read` |
| `dbutils.fs.rm(path)` | `spark.sql("REMOVE @stage/path")` |
| `dbutils.widgets.get("key")` | `sys.env.getOrElse("KEY", "default")` or session parameter |
| `dbutils.secrets.get(scope, key)` | Snowflake secret / external token |
| `dbutils.notebook.run(path, timeout)` | Stored procedure or task DAG |
| `dbutils.notebook.exit(value)` | `return` or exception |

If the entire `dbutils` block can be deleted (e.g. a mount operation that SCOS handles implicitly), delete it and note: `// SCOS: [SPRKCNTSCL1100] Removed Databricks mount — SCOS reads stages directly`.

**⚠️ MANDATORY scan after all edits:** Run:
```bash
# Runs in CoCo bash sandbox (Linux) - safe on any host OS
grep -rn "com\.databricks\|dbutils\." <MIGRATED>/ --include="*.scala" | grep -v "// SCOS\|// EWI"
```
Any match is an **unannotated survivor** — add the annotation before finishing.

### Rule 17: Hive Integration
Remove `enableHiveSupport()`, `HiveContext`, and HWC (`com.hortonworks.spark.sql.hive.*`).

**HWC API → SCOS mapping** (apply to ALL files including tests):

| HWC Call | SCOS Replacement |
|----------|-----------------|
| `hive.sql(query)` | `spark.sql(query)` |
| `hive.executeQuery(query)` | `spark.sql(query)` |
| `hive.table(name)` | `spark.read.table(name)` |
| `hive.session()` | `spark` |
| `hive.setDatabase(db)` | `spark.sql(s"USE $db")` |

**⚠️ CRITICAL**: After removing `implicit val hive: HiveWarehouseSession`, search ALL files for `hive.` references and replace with `spark.sql(...)`.

### Rule 18: Hive DDL Statements
Comment out `MSCK REPAIR TABLE`, `ALTER TABLE RECOVER PARTITIONS`, `CREATE EXTERNAL TABLE`:
```scala
// SCOS: TODO - [SPRKCNTSCL1000] MSCK REPAIR TABLE is Hive-specific.
// Snowflake manages partitions automatically.
// spark.sql("MSCK REPAIR TABLE schema.table")
```

### Rule 19: External Library Parameter Mismatch
After removing parameters (e.g., `hdfs: FileSystem`), check if external library calls still expect them. Add TODO if so.

### Rule 20: ⚠️ Cross-File Consistency (MANDATORY)
When you modify a method signature, remove a method/parameter/variable, or change a type:
1. Grep the **entire codebase** (including tests) for references
2. Update **every caller** to match the new signature
3. Update every subclass/implementation
4. Verify the call chain (callers of callers)
5. Check variable references (`hive.` → `spark.sql(...)`), implicit parameters, companion objects

```bash
# After removing hdfs parameter:
grep -rn "Job\.run" <MIGRATED>/ --include="*.scala"
# After removing HWC variable:
grep -rn "hive\." <MIGRATED>/ --include="*.scala"
# After replacing a Catalyst type:
grep -rn "QualifiedTableName" <MIGRATED>/ --include="*.scala"
# After changing session type:
grep -rn "SparkSession\|sqlContext" <MIGRATED>/ --include="*.scala"
# After removing HDFS FileSystem:
grep -rn "FileSystem\|hadoopConf\|hdfsPath" <MIGRATED>/ --include="*.scala"
```

**Failure to do this is the #1 cause of compilation errors.**

### Rule 21: ⚠️ Import Replacement Emission (MANDATORY)
Only emit syntactically valid Scala import lines. **NEVER** append text, em-dashes, or descriptions after the import path:

**Correct:**
```scala
// SCOS: [SPRKCNTSCL1000] Removed: import org.apache.hadoop.fs.FileSystem
import com.myproject.model.QualifiedTableName
```

**INVALID (causes compilation error):**
```scala
import com.myproject.model.QualifiedTableName — replaced with local model class
```

This applies to ALL import lines — imports must be syntactically pure. Put migration notes in `// SCOS:` comment lines above or below, never inline on the import statement itself.

### Rule 22: ⚠️ Syntax Artifact Cleanup (MANDATORY)
After ALL edits, scan for malformed lines:
```bash
grep -rn '^import .*[—–]' <MIGRATED>/ --include="*.scala"
grep -rn '^—\|^[[:space:]]*—[[:space:]]*$' <MIGRATED>/ --include="*.scala"
grep -rn '^import .* removed' <MIGRATED>/ --include="*.scala"
grep -rn '^import .* //.*→' <MIGRATED>/ --include="*.scala"
```
Fix: move trailing text to comment lines, delete bare em-dash lines. Every import line must compile as Scala.

---

### Rule 23: Map Column Subscript with Column Key
`mapCol(col("key"))` is not supported. Replace with `element_at()`:
```scala
// BEFORE:
val result = df.withColumn("val", categoryMap(col("category_code")))

// AFTER:
// SCOS: [SPRKCNTSCL1000] Map column subscript replaced with element_at()
import org.apache.spark.sql.functions.element_at
val result = df.withColumn("val", element_at(categoryMap, col("category_code")))
```
Literal keys (`mapCol("literal_string")`) still work.

---

### Rule 24: Snowflake-SQL Pass-Through (USE DATABASE / SCHEMA / ROLE / WAREHOUSE)

`spark.sql("USE DATABASE …")` statements do not reliably update the SCOS session context for subsequent DataFrame operations. Lift all USE statements to `SnowflakeSession` calls:

```scala
// BEFORE:
spark.sql("USE DATABASE mydb")
spark.sql("USE SCHEMA myschema")
spark.sql("USE ROLE analyst")
spark.sql("USE WAREHOUSE compute_wh")

// AFTER:
// SCOS: [SPRKCNTSCL3500] USE statements lifted to SnowflakeSession
import com.snowflake.snowpark_connect.client.SnowflakeSession
val sf = new SnowflakeSession(spark)
sf.useDatabase("mydb")
sf.useSchema("myschema")
sf.useRole("analyst")
sf.useWarehouse("compute_wh")
```

`SnowflakeSession.sql(...)` is also available for arbitrary Snowflake SQL that is not a USE statement. Create `sf` once per session — it is lightweight and shares the underlying `SparkSession`.

---

### Rule 25: Snowpark Connect Server URL Resolution

Do NOT hardcode `sc://localhost:15002` in migrated entry points. The server URL is resolved automatically in priority order:

1. `SPARK_REMOTE` environment variable — highest priority. Set to your Snowflake account endpoint.
2. `SNOWPARK_SUBMIT_JOB=true` — sidecar mode, automatically connects to `sc://localhost:15002`.
3. Auto Python venv launch (local dev) — uses `SNOWPARK_CONNECT_PYTHON_VENV`.

```scala
// WRONG — hardcodes a local URL that only works in sidecar mode:
val spark = SparkSession.builder().remote("sc://localhost:15002").getOrCreate()

// CORRECT — resolution is automatic:
import com.snowflake.snowpark_connect.client.SnowparkConnectSession
val spark = SnowparkConnectSession.builder().appName("MyApp").getOrCreate()
```

If you see `sys.env.getOrElse("SPARK_REMOTE", "sc://localhost:15002")` patterns, remove the whole block and replace with `SnowparkConnectSession.builder()`.

---

### Rule 26: Cross-Build-Tool Consistency — Scala Version Suffix

When `scalaVersion` is changed in the build file (e.g. from `2.11` to `2.12`), all cross-compiled artifact coordinates with hardcoded `_2.11` suffixes must be updated:

```scala
// WRONG — version suffix unchanged:
libraryDependencies += "com.example" % "my-lib_2.11" % "1.2.3"

// CORRECT — update to match new scalaVersion:
libraryDependencies += "com.example" % "my-lib_2.12" % "1.2.3"
// Or use %% to let sbt derive the suffix:
libraryDependencies += "com.example" %% "my-lib" % "1.2.3"
```

For Maven: change `_2.11` suffixes to `_${scala.short}` in all `<artifactId>` elements.
For Gradle: change hardcoded `_2.11` strings to `_${scalaShort}` (Groovy) or `_$scalaShort` (Kotlin DSL).

Also check transitive ecosystem libraries: Kafka connectors, Avro, Delta, JSON4S, Shapeless, etc. all publish per-Scala-version artifacts.

---

## Unsupported Dataset/DataFrame APIs

The following DataFrame/Dataset APIs are documented as unsupported in Snowpark Connect. Each must be flagged with a `// SCOS: TODO` or replaced per the guidance below.

| API | Category | EWI Code | Replacement / Guidance |
|-----|----------|----------|------------------------|
| `df.checkpoint()` | No-Op API | SPRKCNTSCL1000 | Replace with `df.cache()`. See Rule 12. |
| `df.localCheckpoint()` | No-Op API | SPRKCNTSCL1000 | Replace with `df.cache()`. See Rule 12. |
| `df.randomSplit(weights)` | No-Op API | SPRKCNTSCL1000 | Use `df.sample(withReplacement=false, fraction=w)` or filter on a random column expression. |
| `df.rdd` | RDD | SPRKCNTSCL1500 | Rewrite to DataFrame API. See `../../references/scala/rdd-conversion.md`. |
| `df.javaRDD` | RDD | SPRKCNTSCL1500 | Rewrite to DataFrame API. |
| `df.toJavaRDD` | RDD | SPRKCNTSCL1500 | Rewrite to DataFrame API. |
| `df.toJSON` | No-Op API | SPRKCNTSCL1000 | Use `df.select(to_json(struct(col("*"))))` and write to a JSON stage file. |
| `df.withWatermark(...)` | No-Op API | SPRKCNTSCL2000 | Streaming API — remove watermark; SCOS is batch only. |
| `df.writeStream` | No-Op API | SPRKCNTSCL2000 | Streaming API — replace with `df.write.mode(...).format(...)`. |
| `df.dropDuplicatesWithinWatermark(...)` | No-Op API | SPRKCNTSCL2000 | Streaming API — use `df.dropDuplicates(cols)` for batch dedup. |
| `df.reduce(func)` | No-Op API | SPRKCNTSCL1000 | Use `df.agg(...)` or `df.groupBy().agg(...)` aggregation. |
| `df.sortWithinPartitions(...)` | No-Op API | SPRKCNTSCL1000 | Use `df.orderBy(...)` at DataFrame level; partitioning managed by Snowflake. |
| `df.queryExecution` | No-Op API | SPRKCNTSCL1000 | Internal Catalyst API; not available via Spark Connect. Remove usage. |
| `df.sqlContext` | No-Op API | SPRKCNTSCL3500 | Deprecated alias for SparkSession; use `spark` directly. |
| `df.isEmpty` | No-Op API | SPRKCNTSCL1000 | Use `df.count() == 0` or `df.limit(1).collect().isEmpty`. |
| `df.toLocalIterator()` | No-Op API | SPRKCNTSCL1000 | Use `df.collect().iterator` for small datasets or process server-side. |

Apply `final_risk >= 0.7` to all entries in this table when found in production code. Add `// SCOS: [SPRKCNTSCL<code>] <api> not supported — <replacement>` on the line before usage.

---

## Behavioral Differences (BD) — Detection and Fix Reference

These are not compilation errors but silent data-correctness issues. Flag each with `// SCOS: TODO - BD-N` when detected.

| BD | EWI | API Pattern | Risk | Spark Behavior | Snowflake Behavior | Fix |
|----|-----|-------------|------|---------------|-------------------|-----|
| BD-1 | SPRKCNTSCL5000 | `a / b` literal `0` divisor | High | Returns NULL | Throws error | `when(col("b") =!= 0, col("a") / col("b")).otherwise(null)` |
| BD-3 | SPRKCNTSCL5002 | `datediff(` | High | `datediff(end, start)` | Requires part + reversed | `expr("DATEDIFF('day', start, end)")` |
| BD-4 | SPRKCNTSCL5003 | `.union(` | High | Position-based | Same — silent corruption risk | Replace with `.unionByName()` |
| BD-8 | SPRKCNTSCL5007 | `isnan(` | High | Returns true for NaN | NaN not supported; returns NULL | Replace `isnan(c)` with `c.isNull` |
| BD-9 | SPRKCNTSCL5008 | `regexp_replace(` | High | Java regex | POSIX regex | Convert `\d`→`[0-9]`, `\w`→`[a-zA-Z0-9_]`; remove lookaheads |
| BD-12 | SPRKCNTSCL5011 | `regexp_extract(` | High | Returns `""` on no-match | Returns NULL | Wrap with `coalesce(regexp_extract(...), lit(""))` |
| BD-13 | SPRKCNTSCL5012 | `first(` / `last(` | High | Order-dependent | Non-deterministic without ORDER BY | Use with explicit window ordering |
| BD-14 | SPRKCNTSCL5013 | `round(` | Medium | Half-up rounding | Banker's rounding | Use `when(x % 1 === 0.5, ceil(x)).otherwise(round(x))` for half-up |
| BD-20 | SPRKCNTSCL5019 | `split(` | Medium | Java regex delimiter | Literal string delimiter | Remove regex escaping: `"\\."` → `"."` |
| BD-27 | SPRKCNTSCL5026 | `date_format(` | Medium | Java tokens (yyyy, HH, mm) | SQL tokens (YYYY, HH24, MI) | Translate: `yyyy`→`YYYY`, `HH`→`HH24`, `mm`→`MI`, `ss`→`SS`, `SSS`→`FF3` |
| BD-28 | SPRKCNTSCL5027 | `collect_list(` / `collect_set(` | Medium | Preserves order, includes nulls | Non-deterministic, excludes nulls | Add explicit ordering; filter nulls before collecting |

For a complete list of behavioral differences see `../../references/scala/behavioral-differences.md`.

---

## UDF Dependency Strategies (Reference)

For UDFs that reference custom classes or third-party JARs, three strategies are available. See `../../references/scala/udf-dependencies.md` for full details:

| Strategy | When to Use | Key Method |
|----------|-------------|------------|
| `REPLClassDirMonitor` | Development — auto-monitors compiled classes dir | `spark.registerClassFinder(new REPLClassDirMonitor(path))` |
| `spark.addArtifact(jar)` | Production — upload packaged JAR before UDF calls | `spark.addArtifact("/path/to/app.jar")` |
| `snowpark.connect.udf.java.imports` | Staged JARs already in Snowflake stage | `spark.conf.set("snowpark.connect.udf.java.imports", "[@stage/dep.jar]")` |

**Rule 27:** After migrating a UDF, verify no `broadcast` variable usage remains (see BD-29); capture lookup data directly in the closure instead.

---

### Rule 28: Null `array`/`struct` Read as VARIANT Null — `isNotNull` Filter Leaks a Row

SCOS reads a parquet/source NULL `array<...>`/`struct<...>` value as a **VARIANT null** (JSON `null`), not a SQL `NULL`. So `col("X").isNotNull` returns **true** for a null array/struct on SCOS (it is `false` on Spark) — a row that Spark filters out leaks through on SCOS, producing an extra output row (a real, off-by-one value divergence vs the Phase A baseline, **not** cosmetic).

When a filter/dedup guards an `array<struct<...>>` (or `struct`) column with `isNotNull`, guard with **both** `isNotNull` AND `size(col("X")) > 0` — `size()` returns 0/negative for a VARIANT null and correctly excludes the row.

**BEFORE (extra row leaks on SCOS):**

```scala
df.filter(col("items").isNotNull)
```

**AFTER:**

```scala
// SCOS: null array reads as VARIANT null, so isNotNull is true for it;
// add size()>0 so empty/null arrays are excluded as they are on Spark.
df.filter(col("items").isNotNull && size(col("items")) > 0)
```

Applies to any `isNotNull`-only guard on an `array<...>` or `struct<...>` column.

---

### Rule 29: Column Names Round-Trip UPPERCASE — Exact-Case `df.columns` Membership Breaks

After a DataFrame is written to and re-read through Snowflake (`saveAsTable` then `spark.table`, or any Snowflake-backed source), its column identifiers come back **upper-cased** (Snowflake folds unquoted identifiers), whereas Spark Classic preserves the original (usually lowercase) case. `col("x")`, `filter($"x" === ...)`, and `select("x")` stay **case-insensitive** on SCOS and keep working — no rewrite needed. What breaks is code that inspects `df.columns` or `df.schema.names` and does an **exact-case** membership check:

```scala
// BEFORE (silently false on SCOS — df.columns contains "MY_COL", not "my_col"):
if (df.columns.contains("my_col")) {
  df = df.withColumn("flag", lit(1))
}
```

On SCOS `df.columns` returns `Array("MY_COL")`, so `contains("my_col")` is `false` and a branch or column is silently dropped — a real value divergence, not cosmetic.

**Fix: lower-case both sides.**

```scala
// AFTER:
// SCOS: Snowflake round-trip upper-cases column identifiers; compare case-insensitively.
if (df.columns.map(_.toLowerCase).contains("my_col".toLowerCase)) {
  df = df.withColumn("flag", lit(1))
}
```

Only exact-case `df.columns`/`df.schema.names` string matching needs this rewrite. `col()`/`select()`/`filter()`/`$"..."` are case-insensitive and do not need to change.

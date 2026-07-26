# RDD to DataFrame Conversion Reference — Python

RDD operations are **not supported** in SCOS (Snowpark Connect on Snowflake).
Spark Connect has no RDD surface: `SparkContext` is unavailable and
`SparkSession.sparkContext` raises `PySparkNotImplementedError` at the
`.sparkContext` access itself. Any RDD hop is a hard runtime failure, so every
RDD operation **must** be rewritten as DataFrame / Snowpark Connect logic.

**Conversion policy (in priority order):**

1. **Native DataFrame functions** (`pyspark.sql.functions`) — always prefer these.
2. **Window functions / SQL expressions** — for ordering, indexing, ranking.
3. **UDF** — only when the user's per-row logic has no native equivalent.
4. **`# SCOS-TODO [SPRKCNTPY1500]`** — when there is no SCOS equivalent at all
   (see [§11](#11-no-equivalent--emit-a-todo)). Never silently drop the operation.

Tag every rewrite with the EWI code: `# SCOS: [SPRKCNTPY1500] <what changed>`.
SparkContext-specific entry points (`broadcast`, `accumulator`, `setLogLevel`, …)
use `SPRKCNTPY4000` / `SPRKCNTPY4002` instead.

Assume these imports are available in examples:

```python
from pyspark.sql import functions as F, Window
```

---

## Quick reference table

### Creation / entry points

| RDD op | DataFrame equivalent | Notes |
|---|---|---|
| `sc.parallelize(data)` | `spark.createDataFrame(data, schema)` | supply an explicit schema (rewritten by `sc_parallelize_to_createdataframe_rewrite`; schema still must be added) |
| `sc.range(n)` | `spark.range(n)` | returns `DataFrame[id: bigint]` |
| `sc.emptyRDD()` | `spark.createDataFrame([], schema)` | schema required |
| `sc.textFile(path)` | `spark.read.text(path)` | 1-col `DataFrame[value: string]` |
| `sc.wholeTextFiles(path)` | `spark.read.text(path, wholetext=True)` (one row per **file**, not per line) + `F.input_file_name()` for the path | rewritten by `sc_wholetextfiles_to_read_text_rewrite`; verify `input_file_name` in SCOS |
| `sc.binaryFiles(path)` | — | **no SCOS equivalent → TODO**: SCOS registers no `binaryFile` reader (`map_read` accepts only csv/json/parquet/text/xml) and its file I/O is UTF-8 only. Left unrewritten; `sparkcontext_property_fallback_rewrite` annotates it |
| `sc.binaryRecords(path, len)` | — | **no SCOS equivalent → TODO** (binary read unsupported) |
| `sc.sequenceFile / objectFile / pickleFile` | — | **no equivalent → TODO** |
| `sc.hadoopFile / hadoopRDD / newAPIHadoopFile / newAPIHadoopRDD` | — | **no equivalent → TODO** |
| `sc.broadcast(v)` | use the value directly; `F.broadcast(df)` for join hints | `SPRKCNTPY4000` |
| `sc.accumulator(...)` | — | **no equivalent → TODO** (`SPRKCNTPY4000`) |
| `SparkContext.getOrCreate()` / `SparkContext(conf=…)` / `from pyspark import SparkContext` | drop — use the existing `spark` (SparkSession); there is no SparkContext under Connect | `SPRKCNTPY4001` |
| `sc.getConf().get(k)` / `sc.getConf()` | `spark.conf.get(k)` / `spark.conf` | `SPRKCNTPY4000` |
| `sc.hadoopConfiguration.set(k, v)` | drop — Snowflake manages storage auth via a storage integration / stage; cloud creds do not flow through Hadoop conf | `SPRKCNTPY3202` |
| `sc.setLogLevel(level)` | drop — no client-settable cluster log level under Spark Connect | `SPRKCNTPY4000` |
| `from pyspark import RDD` / `from pyspark.rdd import …` | remove the import; rewrite the RDD usage it enables | `SPRKCNTPY1500` (flagged by `pyspark_rdd_import_todo_annotate`) |
| `df.rdd` | remove — use the DataFrame directly | |

> **Deterministic detection note.** RDD usage is detected even when the RDD is
> bound to a variable and operated on in a later statement (e.g.
> `rdd = sc.parallelize(...)` then `out = rdd.reduceByKey(add)`). Method names
> that exist **only** on RDD — `reduceByKey`, `reduceByKeyLocally`, `groupByKey`,
> `aggregateByKey`, `foldByKey`, `combineByKey`, `sampleByKey`, `countByKey`,
> `countByValue`, `mapValues`, `flatMapValues`, `keyBy`, `zipWithIndex`,
> `zipWithUniqueId`, `sortByKey`, `mapPartitions`, `mapPartitionsWithIndex`,
> `takeOrdered`, `takeSample`, `saveAsTextFile` — are unambiguous, so the
> `rdd_exclusive_method_todo_annotate` recipe annotates any call to them
> regardless of receiver, and the analyzer flags them without requiring a
> co-located `.rdd`/`sc.` token. Ambiguous names that also exist on DataFrame
> (`map`, `filter`, `collect`, `count`, `distinct`, `union`, `join`, …) still
> require an RDD context token to avoid false positives. RDD imports and `: RDD`
> / `-> RDD` type annotations are also detected at file scope.

### Transformations

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.map(f)` | `df.select(...)` / `df.withColumn(...)` |
| `rdd.flatMap(f)` | `df.select(F.explode(...))` |
| `rdd.filter(f)` | `df.filter(cond)` / `df.where(cond)` |
| `rdd.mapValues(f)` | `df.withColumn("value", expr)` |
| `rdd.flatMapValues(f)` | `df.withColumn("value", expr)` then `F.explode` |
| `rdd.keyBy(f)` | `df.withColumn("key", expr)` |
| `rdd.mapPartitions(f)` / `mapPartitionsWithIndex(f)` | `df.mapInPandas(...)` or a UDF |
| `rdd.pipe(cmd)` | **no equivalent → TODO** |
| `rdd.glom()` | **no equivalent → TODO** (exposes partition layout) |

### Pair / key-value

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.reduceByKey(f)` | `df.groupBy("key").agg(...)` |
| `rdd.reduceByKeyLocally(f)` | `df.groupBy("key").agg(...).collect()` |
| `rdd.groupByKey()` | `df.groupBy("key").agg(F.collect_list("value"))` |
| `rdd.aggregateByKey(z)(seq, comb)` | `df.groupBy("key").agg(...)` |
| `rdd.combineByKey(...)` | `df.groupBy("key").agg(...)` |
| `rdd.foldByKey(z)(f)` | `df.groupBy("key").agg(...)` |
| `rdd.sampleByKey(...)` | `df.sampleBy("key", fractions)` |
| `rdd.keys()` | `df.select("key")` |
| `rdd.values()` | `df.select("value")` |
| `rdd.lookup(k)` | `df.filter(F.col("key") == k).select("value").collect()` |
| `rdd.cogroup(other)` / `groupWith` | full-outer `join` + `F.collect_list` per side |
| `rdd.subtractByKey(other)` | left-anti join on key: `df1.join(df2, "key", "left_anti")` (not detected today; included for completeness) |

### Joins

| RDD op | DataFrame equivalent |
|---|---|
| `rdd1.join(rdd2)` | `df1.join(df2, "key")` |
| `rdd1.leftOuterJoin(rdd2)` | `df1.join(df2, "key", "left")` |
| `rdd1.rightOuterJoin(rdd2)` | `df1.join(df2, "key", "right")` |
| `rdd1.fullOuterJoin(rdd2)` | `df1.join(df2, "key", "outer")` |
| `rdd1.cartesian(rdd2)` | `df1.crossJoin(df2)` |

### Sorting

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.sortByKey()` | `df.orderBy("key")` |
| `rdd.sortBy(f)` | `df.orderBy(expr)` |

### Set operations

| RDD op | DataFrame equivalent |
|---|---|
| `rdd1.union(rdd2)` | `df1.union(df2)` (or `df1.unionByName(df2)`) |
| `rdd1.intersection(rdd2)` | `df1.intersect(df2)` |
| `rdd1.subtract(rdd2)` | **set** semantics (dedups): `df1.subtract(df2)` (SQL `EXCEPT`). **Multiset** (keeps duplicates): `df1.exceptAll(df2)`. RDD `subtract` keeps unmatched duplicates from the left, so `exceptAll` is usually closer — pick by whether dedup is intended. |
| `rdd.distinct()` | `df.distinct()` |

### Aggregation actions

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.reduce(f)` | `df.agg(...)` |
| `rdd.fold(z)(f)` | `df.agg(...)` |
| `rdd.aggregate(z)(seq, comb)` | `df.agg(...)` |
| `rdd.count()` | `df.count()` |
| `rdd.countByKey()` | `df.groupBy("key").count().collect()` |
| `rdd.countByValue()` | `df.groupBy(df.columns).count().collect()` |
| `rdd.sum() / max() / min() / mean()` | `df.agg(F.sum / F.max / F.min / F.avg(col))` |
| `rdd.variance() / stdev()` | `df.agg(F.var_pop / F.stddev_pop(col))` |
| `rdd.sampleVariance() / sampleStdev()` | `df.agg(F.var_samp / F.stddev_samp(col))` |
| `rdd.stats()` | `df.select(F.count, F.mean, F.stddev, F.min, F.max ...)` or `df.summary()` / `df.describe()` (not detected today; included for completeness) |
| `rdd.histogram(buckets)` | `F.width_bucket(...)` + `groupBy().count()` (verify `width_bucket` in SCOS; else **TODO**) |

### Driver / collection actions

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.collect()` | `df.collect()` |
| `rdd.first()` | `df.first()` |
| `rdd.take(n)` | `df.take(n)` (= `df.limit(n).collect()`) |
| `rdd.takeOrdered(n)` | `df.orderBy(col).limit(n).collect()` |
| `rdd.takeSample(...)` | `df.sample(frac).limit(n).collect()` |
| `rdd.top(n)` | `df.orderBy(F.col(c).desc()).limit(n).collect()` |
| `rdd.toLocalIterator()` | `df.toLocalIterator()` |
| `rdd.foreach(f)` | collect + Python loop, or a side-effecting UDF |
| `rdd.foreachPartition(f)` | `df.mapInPandas(...)` (or **TODO**) |
| `rdd.isEmpty()` | `df.isEmpty()` |
| `rdd.zip(other)` | join on a generated row index (see [§8](#8-zip--indexing)) |
| `rdd.zipWithIndex()` | `row_number()` window (0-based; see [§8](#8-zip--indexing)) |
| `rdd.zipWithUniqueId()` | `F.monotonically_increasing_id()` (unique but **not** contiguous and not stable across recompute/repartition — differs from RDD's partition-derived numbering) |

### Sampling / splitting

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.sample(withReplacement, frac)` | `df.sample(withReplacement, frac, seed)` — keep the `withReplacement` flag (verify with-replacement support in SCOS); do not silently drop it |
| `rdd.randomSplit(weights)` | `df.randomSplit(weights)` |

### Saving

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.saveAsTextFile(path)` | `df.write.text(path)` / `df.write.csv(path)` |
| `rdd.saveAsSequenceFile / saveAsObjectFile` | **no equivalent → TODO** |

### Partitioning / caching

| RDD op | DataFrame equivalent |
|---|---|
| `rdd.cache()` | `df.cache()` |
| `rdd.persist(level)` | `df.cache()` (storage level dropped) |
| `rdd.unpersist()` | `df.unpersist()` |
| `rdd.checkpoint() / localCheckpoint()` | `df.cache()` |
| `rdd.repartition(n) / coalesce(n)` | drop the `.rdd` hop; the DataFrame `repartition`/`coalesce` is **accepted** (not a no-op — controls write file count). Leave it; **do not** call it a no-op. |
| `rdd.getNumPartitions()` | no meaningful value under Spark Connect — remove / **TODO** |
| `rdd.isCheckpointed() / getCheckpointFile()` | **no equivalent → TODO** |

> ⚠️ `repartition` / `coalesce`: do **not** annotate the surviving DataFrame call
> as a "no-op". Per the fixer's Rule 4 they are accepted and `repartition(n)` /
> `coalesce(n)` hint the `COPY INTO` output-file count. (Rule 4 covers
> `hint`/`repartition`/`coalesce` only — `partitionBy` is **not** in scope and is
> not flagged by the detector today.)

> **Recipe note — the `.rdd` hop.** When an identical-signature method is reached
> through the unsupported `.rdd` hop, `df_rdd_passthrough_rewrite` drops the hop
> deterministically (`df.rdd.<m>(...)` → `df.<m>(...)`) for
> `isEmpty`, `toLocalIterator`, `collect`, `count`, `first`, `take`, `distinct`,
> `cache`, `unpersist`, `repartition`, `coalesce`. Two `.rdd` methods are handled
> by sibling recipes instead: `df.rdd.persist(level)` →
> `rdd_persist_to_cache_rewrite` (drops the storage level), and
> `df.rdd.getNumPartitions()` → `rdd_no_equivalent_todo_annotate`. Everything else
> on `df.rdd` (`map`, `flatMap`, `keyBy`, `zipWithIndex`, …) is left for the LLM
> fixer.

---

## Worked examples

### 1. Word count (flatMap + map + reduceByKey)

```python
# BEFORE:
# sc.textFile("data.txt").flatMap(lambda x: x.split(" ")) \
#   .map(lambda w: (w, 1)).reduceByKey(lambda a, b: a + b)
# AFTER:
(
    spark.read.text("data.txt")
    .select(F.explode(F.split(F.col("value"), " ")).alias("word"))
    .groupBy("word")
    .agg(F.count("*").alias("count"))
)
```

### 2. map / withColumn

```python
# BEFORE: rdd.map(lambda x: x * 2)
# AFTER:
df.select((F.col("value") * 2).alias("value"))

# BEFORE: rdd.map(lambda r: (r.id, r.amount * 1.1))
# AFTER:
df.select(F.col("id"), (F.col("amount") * 1.1).alias("amount"))
```

### 3. filter

```python
# BEFORE: rdd.filter(lambda x: x > 10)
# AFTER:
df.filter(F.col("value") > 10)
```

### 4. groupByKey / reduceByKey / aggregateByKey

```python
# BEFORE: rdd.groupByKey()
# AFTER:
df.groupBy("key").agg(F.collect_list("value").alias("values"))

# BEFORE: rdd.reduceByKey(lambda a, b: a + b)
# AFTER:
df.groupBy("key").agg(F.sum("value").alias("value"))

# BEFORE: rdd.aggregateByKey(0)(lambda acc, v: acc + v, lambda a, b: a + b)
# AFTER (a + b is just a sum):
df.groupBy("key").agg(F.sum("value").alias("value"))
```

### 5. Joins (all variants)

```python
# BEFORE: rdd1.join(rdd2)            AFTER: df1.join(df2, "key")
# BEFORE: rdd1.leftOuterJoin(rdd2)   AFTER: df1.join(df2, "key", "left")
# BEFORE: rdd1.rightOuterJoin(rdd2)  AFTER: df1.join(df2, "key", "right")
# BEFORE: rdd1.fullOuterJoin(rdd2)   AFTER: df1.join(df2, "key", "outer")
# BEFORE: rdd1.cartesian(rdd2)       AFTER: df1.crossJoin(df2)
```

### 6. Sorting

```python
# BEFORE: rdd.sortByKey()            AFTER: df.orderBy("key")
# BEFORE: rdd.sortBy(lambda r: r[1]) AFTER: df.orderBy(F.col("_2"))
# descending:                        AFTER: df.orderBy(F.col("key").desc())
```

### 7. Aggregation actions (reduce / mean / countByValue)

```python
# BEFORE: rdd.map(lambda r: r.amount).reduce(lambda a, b: a + b)
# AFTER:
df.agg(F.sum("amount").alias("total")).collect()[0]["total"]

# BEFORE: rdd.map(lambda r: r.amount).mean()
# AFTER:
df.agg(F.avg("amount")).collect()[0][0]

# BEFORE: rdd.countByValue()
# AFTER:
df.groupBy(df.columns).count().collect()
```

### 8. zip / indexing

`zipWithIndex` is deterministic and 0-based in Spark. The closest SCOS-safe form
uses a window; it requires an explicit ordering to be deterministic.

```python
# BEFORE: rdd.zipWithIndex()
# AFTER (0-based, deterministic given an order column):
w = Window.orderBy("some_order_col")
df.withColumn("index", F.row_number().over(w) - 1)

# BEFORE: rdd.zipWithUniqueId()   (unique but not contiguous)
# AFTER:
df.withColumn("uid", F.monotonically_increasing_id())
```

> ⚠️ `row_number().over(Window.orderBy(...))` over an unpartitioned window
> serializes all rows through one partition. Acceptable for indexing semantics but
> note the cost. If the original code only needed *a* unique id (not 0..N-1),
> prefer `monotonically_increasing_id()`.

### 9. mapPartitions → mapInPandas / UDF

```python
# BEFORE: rdd.mapPartitions(lambda it: (heavy(x) for x in it))
# AFTER (native if expressible):
df.withColumn("out", heavy_expr(F.col("in")))

# AFTER (when per-row Python logic is unavoidable):
from pyspark.sql.types import StringType

@F.udf(StringType())
def heavy(value):
    return _do_work(value)

df.select(heavy(F.col("in")).alias("out"))
```

### 10. UDF fallback (only when native functions won't work)

```python
from pyspark.sql.types import StringType

@F.udf(StringType())
def complex_transform(val):
    return val.upper() + "_processed"

df.select(complex_transform(F.col("name")).alias("result"))
```

> Prefer native functions. A UDF runs row-by-row on the Snowflake Python worker
> and forfeits vectorized pushdown — use it only when the logic genuinely has no
> column-expression equivalent.

---

## 11. No equivalent → emit a TODO

Some RDD operations have **no** SCOS/Snowflake equivalent. Do not improvise a
rewrite and do not silently drop them — emit a TODO so a human migrates them:

```python
# SCOS-TODO: [SPRKCNTPY1500] sc.sequenceFile has no SCOS equivalent
# (Hadoop/Java-serialized I/O). Re-express the data as a supported Snowflake
# source (stage file / table) before migrating.
```

Ops in this bucket:

- **I/O with no analogue:** `sequenceFile`, `objectFile`, `pickleFile`,
  `hadoopFile`, `hadoopRDD`, `newAPIHadoopFile`, `newAPIHadoopRDD`,
  `saveAsSequenceFile`, `saveAsObjectFile`, `binaryFiles`, `binaryRecords`
  (SCOS has no `binaryFile` reader and its file I/O is UTF-8 only).
- **Execution primitives with no analogue:** `pipe` (forks an external process),
  `glom` (exposes partition layout), `getNumPartitions`, `isCheckpointed`,
  `getCheckpointFile`.
- **SparkContext primitives** (use `SPRKCNTPY4000`): `accumulator`
  (no driver-side accumulators). `broadcast(v)` can usually be replaced by using
  the value directly, or `F.broadcast(df)` for a join hint.

---

## Spark Connect / SCOS specifics

- There is **no `SparkContext`**. Replace `sc.<x>` with the equivalent on
  `spark` (the `SparkSession`) or a DataFrame; an unported `sc.<x>` will raise
  `PySparkNotImplementedError` at runtime.
- `df.rdd` is unavailable — never route through it. Operations like
  `df.rdd.isEmpty()` / `df.rdd.toLocalIterator()` have direct DataFrame methods
  (`df.isEmpty()`, `df.toLocalIterator()`).
- `repartition` / `coalesce` are **accepted** on DataFrames and are **not** pure
  no-ops; do not remove them or label them "no-op".
- `checkpoint()` / `localCheckpoint()` are not supported by the Connect client —
  use `df.cache()`.
- Prefer `spark.createDataFrame(data, schema)` with an **explicit schema** when
  replacing `parallelize` / `emptyRDD`; schema inference over Python literals is
  fragile and sometimes unsupported.

### SparkContext entry points & config (`getOrCreate` / `getConf` / `hadoopConfiguration`)

```python
# BEFORE: explicit SparkContext bootstrap (RuntimeError on SCOS)
# from pyspark import SparkContext
# sc = SparkContext.getOrCreate()
# data = sc.parallelize([1, 2, 3])
# AFTER: there is no SparkContext — use the existing SparkSession `spark`:
data = spark.createDataFrame([(i,) for i in [1, 2, 3]], ["value"])

# BEFORE: reading a conf via SparkContext
# n = sc.getConf().get("spark.sql.shuffle.partitions")
# AFTER:
n = spark.conf.get("spark.sql.shuffle.partitions")

# BEFORE: storage auth via Hadoop conf
# sc.hadoopConfiguration.set("fs.s3a.access.key", "AKIA...")
# AFTER: drop it — Snowflake authenticates cloud storage via a storage
# integration / external stage, not Hadoop conf. (SPRKCNTPY3202)
```

> `getConf()` / `setLogLevel()` map to (or drop against) the `spark`
> session — they do not need a `SparkContext`. `hadoopConfiguration` cloud
> credentials have no SCOS analogue: re-point the read at a Snowflake stage.

### SparkContext EWI codes: `4000` vs `4002`

`SPRKCNTPY4000` = an unsupported SparkContext **element/method call** that must be
migrated (`sc.parallelize`, `sc.broadcast`, `sc.accumulator`, `sc.setLogLevel`, …).
`SPRKCNTPY4002` = a SparkContext **property read** that was replaced with a static
fallback so diagnostic code keeps running (handled deterministically by the
`sparkcontext_property_fallback_rewrite` recipe). Example:

```python
# BEFORE: app_id = spark.sparkContext.applicationId
# AFTER  (property read → getattr fallback; .sparkContext hop dropped):
# SCOS: [SPRKCNTPY4002] sparkContext property read replaced with a getattr fallback
app_id = getattr(spark, "applicationId", "scos-unsupported")
```

A SparkContext **method call** cannot use the getattr fallback (it would
`TypeError` when invoked) — those stay `SPRKCNTPY4000` and are migrated to the
SparkSession/Snowpark Connect surface (e.g. `parallelize` → `createDataFrame`).

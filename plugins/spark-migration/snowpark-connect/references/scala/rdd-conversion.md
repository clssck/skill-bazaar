# RDD → DataFrame Conversion Rules (Scala / Snowpark Connect)

Referenced by the `migrate-spark-scala-to-snowpark-connect` skill
(`references/fix-rules.md` Rule 2 and `agents/fixer.md`).

## Quick Reference

| RDD pattern | Bucket | DataFrame equivalent |
| --- | --- | --- |
| `.rdd.map(f)` / `.flatMap(f)` / `.filter(f)` / `.foreach(f)` (closure) | **A** | annotate `[SPRKCNTSCL1500]` + preserve |
| `.rdd.mapPartitions(f)` / `foreachPartition` / `glom` / `pipe` | **A** | annotate `[SPRKCNTSCL1500]` + preserve |
| `.rdd.getNumPartitions` / `.rdd.partitions` | **A** | annotate `[SPRKCNTSCL1500]` + preserve |
| `sc.textFile` / `hadoopFile` / `sequenceFile` / `new SparkContext` | **A** | annotate `[SPRKCNTSCL1500]` + preserve |
| `sc.accumulator(...)` | **A** | annotate `[SPRKCNTSCL1500]` + preserve |
| `df.rdd.count()` / `collect()` / `first()` / `take(n)` / `isEmpty()` | **B** | `df.count()` etc. — drop `.rdd` |
| `df.rdd.cache()` / `persist()` / `unpersist()` | **B** | `df.cache()` etc. — drop `.rdd` |
| `df1.rdd.union(df2.rdd)` / `distinct()` / `intersection` / `subtract` | **B** | `df1.union(df2)` etc. — drop `.rdd` |
| `df.rdd.repartition(n)` / `coalesce(n)` | **B** | `df.repartition(n)` / `df.coalesce(n)` — drop `.rdd` |
| `sc.parallelize(Seq[tuple/case class])` | **C** | `spark.createDataFrame(seq).toDF(names…)` |
| `sc.parallelize(Seq[primitive])` | **C** | `spark.createDataFrame(seq.map(Tuple1.apply)).toDF("value")` |
| `sc.parallelize(Seq[Row], schema)` / `emptyRDD[Row]` | **C** | `spark.createDataFrame(seq.asJava, schema)` |
| `reduceByKey` / `reduceByKeyLocally` / `groupByKey` / `countByKey` / `aggregateByKey` / `foldByKey` / `combineByKey` | **C** | `groupBy(key).agg(...)` |
| `rdd.sortByKey()` | **C** | `df.orderBy(col("key"))` |
| `rdd1.join(rdd2)` / `leftOuterJoin` / `rightOuterJoin` / `fullOuterJoin` | **C** | `df1.join(df2, Seq("key"), "inner/left/right/outer")` |
| `rdd1.subtractByKey(rdd2)` | **C** | `df1.join(df2, Seq("key"), "left_anti")` |
| `rdd.mapValues(f)` / `flatMapValues(f)` | **C** | `df.withColumn(...)` / `df.withColumn(...).select(explode(...))` |
| `rdd.saveAsTextFile(path)` | **C** | `df.write.mode("overwrite").text(path)` |
| `sc.broadcast(v)` scalar | **C** | use `v` directly |
| `sc.broadcast(df)` join hint | **C** | `df.hint("broadcast")` |

---

## Why RDD is unsupported

Snowpark Connect (Spark Connect) is a thin **declarative client**: it builds an
unresolved logical plan and ships it to the server for execution. There is **no
`SparkContext`, no executors, and no RDD layer on the client**, and the backend
does not run arbitrary JVM closures. The Connect `Dataset`/`DataFrame` class
literally has **no `.rdd` member** (`scalac` reports `value rdd is not a member of
org.apache.spark.sql.DataFrame`).

So every RDD usage falls into one of three buckets:

- **Bucket A — unsupported.** No DataFrame equivalent → annotate and refactor
  manually. **Never fabricate a shim.**
- **Bucket B — drop-the-hop.** `df.rdd.METHOD()` where the same METHOD exists on
  DataFrame directly (no closure needed) → drop the `.rdd` accessor and call the
  method on the DataFrame.
- **Bucket C — convertible.** Has a supported DataFrame form that requires a
  rewrite (e.g. `sc.parallelize` → `createDataFrame`, pair ops → `groupBy.agg`).

---

## Bucket A — UNSUPPORTED (annotate `// SCOS: [SPRKCNTSCL1500]`, preserve, manual)

Triggers (no DataFrame equivalent):

- `.rdd.map(f)`, `.rdd.flatMap(f)`, `.rdd.filter(f)` and any closure-bearing RDD transform — JVM closures are opaque; rewrite manually
- `.rdd.mapValues(f)`, `.rdd.flatMapValues(f)` — closure on pair RDD
- `.rdd.foreach(f)`, `.rdd.foreachPartition(f)` — side-effecting closure
- `.rdd.mapPartitions(f)`, `mapPartitionsWithIndex(f)` — partition-level execution
- `.rdd.getNumPartitions`, `.rdd.partitions` / `.partitions.length` — meaningless under SC
- `.rdd.glom()`, `.rdd.pipe(cmd)` — no equivalent
- `.javaRDD`, `.toJavaRDD` — no equivalent
- `SparkContext` ingestion: `sc.textFile`, `sc.wholeTextFiles`, `sc.hadoopFile`, `sc.hadoopRDD`, `sc.sequenceFile`, `sc.objectFile`, `new SparkContext`
- `rdd.saveAsSequenceFile(path)`, `rdd.saveAsObjectFile(path)` — Hadoop-serialised formats, no SCOS equivalent
- `import org.apache.spark.rdd._`
- `sc.accumulator(...)` — no driver-side accumulator in the Connect model

**Action:** leave the original expression in place and prepend a `// SCOS:`
marker that embeds the EWI code `[SPRKCNTSCL1500]` (single marker vocabulary —
parity with PySpark's `# SCOS: [SPRKCNTPY####]`; do **not** use a bare `// EWI:`
prefix). Keep the literal phrase `manual refactor` so the Phase 2b gate
quarantines the file. Do **NOT** delete the logic, and do **NOT** invent a
replacement (no `.rdd` re-introduction, no nested `createDataFrame`, no `Tuple1`
wrapping).

```scala
// SCOS: [SPRKCNTSCL1500] RDD API '.rdd.getNumPartitions' is not supported in
// Snowpark Connect; manual refactor required (no RDD layer on the client).
println(df.rdd.getNumPartitions)
```

The Phase 2b type-check gate **quarantines** files whose only failures are these
annotated RDD lines (it keys on the `SPRKCNTSCL1500` … `manual refactor` text, not
the comment prefix, so it will not revert them); they are reported as
manual-intervention items, not migration failures.

---

## Bucket B — DROP-THE-HOP: `df.rdd.*` shortcuts

These patterns use `.rdd` only as a gateway to a method that exists **identically**
on DataFrame. Drop the `.rdd` accessor and call the same method directly — no
closure or RDD knowledge required.

### Terminal actions

| RDD form | DataFrame equivalent |
| --- | --- |
| `df.rdd.count()` | `df.count()` |
| `df.rdd.isEmpty()` | `df.isEmpty()` |
| `df.rdd.collect()` | `df.collect()` |
| `df.rdd.first()` | `df.first()` |
| `df.rdd.take(n)` | `df.take(n)` |
| `df.rdd.toLocalIterator()` | `df.toLocalIterator()` |

### Caching / persistence

| RDD form | DataFrame equivalent |
| --- | --- |
| `df.rdd.cache()` / `df.rdd.persist()` | `df.cache()` |
| `df.rdd.unpersist()` | `df.unpersist()` |

### Set operations (both arguments are DataFrames)

| RDD form | DataFrame equivalent | Notes |
| --- | --- | --- |
| `df1.rdd.union(df2.rdd)` | `df1.union(df2)` / `df1.unionByName(df2)` | use `unionByName` when column order differs |
| `df.rdd.distinct()` | `df.distinct()` | |
| `df1.rdd.intersection(df2.rdd)` | `df1.intersect(df2)` | deduplicated |
| `df1.rdd.subtract(df2.rdd)` | `df1.except(df2)` (dedup) or `df1.exceptAll(df2)` (multiset) | RDD `subtract` preserves left duplicates → prefer `exceptAll` |

### Sampling / splitting

| RDD form | DataFrame equivalent |
| --- | --- |
| `df.rdd.sample(withReplacement, frac)` | `df.sample(withReplacement, frac)` |

> `df.rdd.randomSplit(weights)` is **not** a valid drop-the-hop — `df.randomSplit()`
> is itself unsupported in SCOS. This is a Bucket C case; see "CONVERTIBLE: saving
> and splitting" below.

### Repartitioning

| RDD form | DataFrame equivalent |
| --- | --- |
| `df.rdd.repartition(n)` | `df.repartition(n)` |
| `df.rdd.coalesce(n)` | `df.coalesce(n)` |

```scala
// BEFORE:
val n    = df.rdd.count()
val rows = df.rdd.collect()
val uniq = df.rdd.distinct()
val both = df1.rdd.union(df2.rdd)

// AFTER:
val n    = df.count()
val rows = df.collect()
val uniq = df.distinct()
val both = df1.union(df2)
```

> **Note:** these are only safe to convert when the source of `.rdd` is a
> DataFrame (not an independently-constructed `RDD[Row]` or `RDD[(K,V)]`). When
> in doubt, trace the origin of the value before `.rdd`.

---

## Bucket C — CONVERTIBLE: `createDataFrame` (`sc.parallelize` / `sc.emptyRDD`)

`createDataFrame` **is** the correct SCOS target. Pick the overload by element type
(verified against `spark-connect-client-jvm` 3.5.x):

### C1. `Seq` of tuples / case classes (a `Product`)

```scala
// before: val rdd = sc.parallelize(Seq(("a", 1), ("b", 2)))   // used as a DataFrame
val df = spark.createDataFrame(Seq(("a", 1), ("b", 2))).toDF("key", "value")
```

**NEVER** `Seq(...).map(Tuple1.apply)` here — it compiles but **collapses the
tuple into a single struct column `_1`** (wrong schema).

### C2. `Seq` of primitives (NOT a `Product`) — Tuple1 wrap is required

```scala
val df = spark.createDataFrame(Seq(1, 2, 3).map(Tuple1.apply)).toDF("value")
```

`createDataFrame[A <: Product]` rejects a bare `Seq[Int]` (`inferred type
arguments [Int] do not conform to ... bounds [A <: Product]`), so primitives
**must** be wrapped.

### C3. `createDataFrame(sc.parallelize(rows), schema)` / `createDataFrame(sc.emptyRDD[Row], schema)`

Here `rows: Seq[Row]`. Drop the RDD and pass a `java.util.List[Row]` — the client
has `createDataFrame(rows: java.util.List[Row], schema: StructType)` but **no**
`Seq[Row]` overload:

```scala
import scala.collection.JavaConverters._   // Scala 2.12 (use scala.jdk.CollectionConverters for 2.13)

val df    = spark.createDataFrame(rows.asJava, schema)
val empty = spark.createDataFrame(Seq.empty[Row].asJava, schema)
```

**NEVER** nest: `createDataFrame(createDataFrame(rows.map(Tuple1.apply)).toDF("_1"), schema)`
does **not** type-check — there is no `createDataFrame(DataFrame, StructType)`
overload.

---

## Bucket C — CONVERTIBLE: key-based pair operations → `groupBy().agg(...)`

Once the source is a DataFrame, RDD pair ops become relational aggregations:

| RDD pair op                 | DataFrame equivalent                         |
| --------------------------- | -------------------------------------------- |
| `reduceByKey(_ + _)`        | `groupBy(key).agg(sum(value))`               |
| `reduceByKey(_ max _)`      | `groupBy(key).agg(max(value))`               |
| `reduceByKeyLocally(f)`     | `groupBy(key).agg(...).collect().toMap`      |
| `groupByKey()`              | `groupBy(key)`                               |
| `countByKey()`              | `groupBy(key).count()`                       |
| `aggregateByKey(z)(sf, cf)` | `groupBy(key).agg(...)`                      |
| `foldByKey(z)(f)`           | `groupBy(key).agg(...)`                      |
| `combineByKey(c, m, r)`     | `groupBy(key).agg(...)`                      |

```scala
import org.apache.spark.sql.functions.{explode, split, col, sum, count}

// Word count (flatMap + reduceByKey):
// BEFORE: sc.textFile("data.txt").flatMap(_.split(" ")).map(w => (w, 1)).reduceByKey(_ + _)
// AFTER:
spark.read.text("data.txt")
  .select(explode(split(col("value"), " ")).alias("word"))
  .groupBy("word")
  .agg(count("*").alias("count"))

// reduceByKey sum:
// BEFORE: sc.parallelize(Seq(("a", 1), ("a", 2))).reduceByKey(_ + _)
val df     = spark.createDataFrame(Seq(("a", 1), ("a", 2))).toDF("word", "count")
val result = df.groupBy("word").agg(sum("count").as("count"))
```

Note the ordering: convert the `parallelize`/`createDataFrame` source **first** so
the key/value column names exist, **then** rewrite the pair op against those
columns. If the reducer is an arbitrary non-associative lambda that has no `agg`
form, treat it as Bucket A (`// SCOS: [SPRKCNTSCL1500]` + manual).

---

## Bucket C — CONVERTIBLE: sorting and ordering

| RDD form | DataFrame equivalent | Notes |
| --- | --- | --- |
| `rdd.sortByKey()` | `df.orderBy(col("key"))` | replace `"key"` with the actual key column |
| `rdd.sortByKey(ascending = false)` | `df.orderBy(col("key").desc)` | |
| `rdd.takeOrdered(n)` | `df.orderBy(col("key").asc).limit(n).collect()` | for custom `Ordering`, match the ordering expression |
| `rdd.top(n)` | `df.orderBy(col("key").desc).limit(n).collect()` | |

---

## Bucket C — CONVERTIBLE: pair joins

All four RDD pair-join variants + `cogroup` and `subtractByKey` map to DataFrame joins:

| RDD form | DataFrame equivalent |
| --- | --- |
| `rdd1.join(rdd2)` | `df1.join(df2, Seq("key"))` |
| `rdd1.leftOuterJoin(rdd2)` | `df1.join(df2, Seq("key"), "left")` |
| `rdd1.rightOuterJoin(rdd2)` | `df1.join(df2, Seq("key"), "right")` |
| `rdd1.fullOuterJoin(rdd2)` | `df1.join(df2, Seq("key"), "outer")` |
| `rdd1.cartesian(rdd2)` | `df1.crossJoin(df2)` |
| `rdd1.cogroup(rdd2)` | `df1.join(df2, Seq("key"), "outer")` + `collect_list` per side |
| `rdd1.subtractByKey(rdd2)` | `df1.join(df2, Seq("key"), "left_anti")` |

```scala
// BEFORE: rdd1.join(rdd2)  →  AFTER:
val result = df1.join(df2, Seq("key"))

// BEFORE: rdd1.subtractByKey(rdd2)  →  AFTER (left-anti join):
val result = df1.join(df2, Seq("key"), "left_anti")
```

---

## Bucket C — CONVERTIBLE: pair accessors and sampling

| RDD form | DataFrame equivalent |
| --- | --- |
| `rdd.keys()` | `df.select(col("key"))` (use the actual key column name) |
| `rdd.values()` | `df.select(col("value"))` (use the actual value column name) |
| `rdd.sampleByKey(withReplacement, fractions)` | `df.sampleBy("key", fractions, seed)` |
| `rdd.countByValue()` | `df.groupBy(df.columns.map(col): _*).count().collect()` |

---

## Bucket C — CONVERTIBLE: mapValues / flatMapValues

These require translating the closure to a column expression (inspect the closure body):

| RDD form | DataFrame equivalent |
| --- | --- |
| `rdd.mapValues(f)` | `df.withColumn("value", <col-expr from f>)` |
| `rdd.flatMapValues(f)` | `df.withColumn("value", <col-expr from f>).select(explode(col("value")))` |

```scala
// BEFORE: rdd.mapValues(_ * 2)
// AFTER  (first convert parallelize source to df with named columns):
df.withColumn("value", col("value") * 2)

// BEFORE: rdd.flatMapValues(_.split(","))
// AFTER:
df.withColumn("value", split(col("value"), ",")).select(explode(col("value")))
```

---

## Bucket C — CONVERTIBLE: indexing

| RDD form | DataFrame equivalent | Notes |
| --- | --- | --- |
| `rdd.zipWithIndex()` | `df.withColumn("index", row_number().over(Window.orderBy(<col>)) - 1)` | requires an explicit ordering column; result is 0-based |
| `rdd.zipWithUniqueId()` | `df.withColumn("uid", monotonically_increasing_id())` | unique but NOT contiguous; not stable across repartition |

```scala
import org.apache.spark.sql.expressions.Window
import org.apache.spark.sql.functions.{row_number, monotonically_increasing_id}

// zipWithIndex (0-based, deterministic given an order column):
val w = Window.orderBy("order_col")
df.withColumn("index", row_number().over(w) - 1)

// zipWithUniqueId (unique, not contiguous):
df.withColumn("uid", monotonically_increasing_id())
```

> ⚠️ `row_number()` over an unpartitioned window serialises all rows through one
> executor. If only a unique id is needed (not 0..N-1), prefer
> `monotonically_increasing_id()`.

---

## Bucket C — CONVERTIBLE: saving and splitting

| RDD form | DataFrame equivalent | Notes |
| --- | --- | --- |
| `rdd.saveAsTextFile(path)` | `df.write.mode("overwrite").text(path)` | one line per row in the `value` column |
| `rdd.randomSplit(weights)` | ⚠ **`df.randomSplit()` is itself unsupported in SCOS** | use `df.sample(fraction, seed)` with complementary fractions, or add `df.withColumn("split", rand() < fraction)` |

---

## Bucket C — CONVERTIBLE: `sc.broadcast`

`sc.broadcast(v)` has no equivalent, but its intent is almost always achievable
without it:

- **Scalar / lookup value** — use `v` directly. Snowpark Connect broadcasts small
  values to the server automatically; no explicit `Broadcast` wrapper is needed.
- **DataFrame join hint** — replace `F.broadcast(df)` hint with
  `df.hint("broadcast")` or use `broadcast(df)` from
  `org.apache.spark.sql.functions`.

```scala
// BEFORE: val lookup = sc.broadcast(Map("a" -> 1, "b" -> 2))
// AFTER (scalar lookup used directly):
val lookup = Map("a" -> 1, "b" -> 2)

// BEFORE: df1.join(F.broadcast(df2), "key")
// AFTER:
df1.join(df2.hint("broadcast"), Seq("key"))
// or: import org.apache.spark.sql.functions.broadcast
df1.join(broadcast(df2), Seq("key"))
```

---

## Decision summary

| Pattern | Bucket | Action |
| --- | --- | --- |
| `.rdd.map(f)` / `.flatMap(f)` / `.filter(f)` / `.foreach(f)` (closure) | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `.rdd.mapValues(f)` / `.flatMapValues(f)` (closure, `.rdd`-sourced) | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `.rdd.mapPartitions` / `foreachPartition` / `glom` / `pipe` | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `.rdd.getNumPartitions` / `.rdd.partitions` | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `sc.textFile`/`hadoopFile`/`sequenceFile`/`objectFile`, `new SparkContext` | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `rdd.saveAsSequenceFile(path)` / `rdd.saveAsObjectFile(path)` | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `sc.accumulator(...)` | A | `// SCOS: [SPRKCNTSCL1500]` + preserve + manual |
| `df.rdd.count()` / `isEmpty()` / `collect()` / `first()` / `take(n)` / `toLocalIterator()` | B | drop `.rdd` → `df.count()` etc. |
| `df.rdd.cache()` / `persist()` / `unpersist()` | B | drop `.rdd` → `df.cache()` etc. |
| `df1.rdd.union(df2.rdd)` / `distinct()` / `intersection` / `subtract` | B | drop both `.rdd` hops → `df1.union(df2)` etc. |
| `df.rdd.sample(wr,f)` / `repartition(n)` / `coalesce(n)` | B | drop `.rdd` → same method on DataFrame |
| `sc.parallelize(Seq[Product])` | C1 | `createDataFrame(seq).toDF(names…)` |
| `sc.parallelize(Seq[primitive])` | C2 | `createDataFrame(seq.map(Tuple1.apply)).toDF("value")` |
| `createDataFrame(sc.parallelize(Seq[Row]), schema)` / `emptyRDD[Row]` | C3 | `createDataFrame(seq.asJava, schema)` + `JavaConverters` |
| `reduceByKey`/`reduceByKeyLocally`/`groupByKey`/`countByKey`/`aggregateByKey`/`foldByKey`/`combineByKey` | C | `groupBy(key).agg(...)` |
| `rdd.sortByKey()` | C | `df.orderBy(col("key"))` / `.orderBy(col("key").desc)` |
| `rdd.takeOrdered(n)` / `rdd.top(n)` | C | `df.orderBy(col.asc/desc).limit(n).collect()` |
| `rdd1.join(rdd2)` / `leftOuterJoin` / `rightOuterJoin` / `fullOuterJoin` | C | `df1.join(df2, Seq("key"), "inner/left/right/outer")` |
| `rdd1.cartesian(rdd2)` | C | `df1.crossJoin(df2)` |
| `rdd1.cogroup(rdd2)` | C | `df1.join(df2, Seq("key"), "outer")` + `collect_list` |
| `rdd1.subtractByKey(rdd2)` | C | `df1.join(df2, Seq("key"), "left_anti")` |
| `rdd.keys()` / `rdd.values()` | C | `df.select(col("key"))` / `df.select(col("value"))` |
| `rdd.sampleByKey(wr, fractions)` | C | `df.sampleBy("key", fractions, seed)` |
| `rdd.mapValues(f)` (after `sc.parallelize`) | C | `df.withColumn("value", <col-expr from f>)` |
| `rdd.flatMapValues(f)` (after `sc.parallelize`) | C | `df.withColumn("value", <expr>).select(explode(...))` |
| `rdd.zipWithIndex()` | C | `row_number().over(Window.orderBy(<col>)) - 1` |
| `rdd.zipWithUniqueId()` | C | `df.withColumn("uid", monotonically_increasing_id())` |
| `rdd.countByValue()` | C | `df.groupBy(df.columns.map(col): _*).count().collect()` |
| `rdd.saveAsTextFile(path)` | C | `df.write.mode("overwrite").text(path)` |
| `rdd.randomSplit(weights)` | C | ⚠ `df.randomSplit()` is unsupported in SCOS — use `df.sample()` |
| `sc.broadcast(v)` scalar | C | use `v` directly |
| `sc.broadcast(df)` join hint | C | `df.hint("broadcast")` or `broadcast(df)` |

---

## Scala-Specific Considerations

- Use `spark.implicits._` for implicit conversions from Scala collections to DataFrames
- Prefer `col("columnName")` or `$"columnName"` (requires `spark.implicits._`) for column references
- When converting `sc.parallelize`, `Seq(...).toDF(...)` works for tuples/case classes via implicits; for `Seq[Row]` use `createDataFrame(seq.asJava, schema)`
- For typed transformations, prefer the `Dataset[T]` API with case classes over RDD `.map()` — it preserves compile-time type safety while being fully supported in SCOS

# EWI Code Reference for SCOS Migration — Scala

Official Snowpark Migration Accelerator (SMA) issue codes used when generating dashboard-compatible reports for Scala workloads. Consult this reference when classifying issues during Step 3 (Apply Fixes) and when generating Reports/ CSV files.

## Code Prefixes

| Prefix | Language | Source |
|--------|----------|--------|
| `SPRKCNTSCL` | Scala | Snowpark Connect for Scala |
| `SPRKSCL` | Scala | Snowpark API (general Scala) |
| `SSC-EWI` | SQL | SnowConvert SQL |

## Snowpark Connect Scala Codes (SPRKCNTSCL)

| Code | Message | Category | Doc URL |
|------|---------|----------|---------| 
| `SPRKCNTSCL0099` | The file `<element>` was not fully processed by the LLM migration agent — a deterministic fallback transformation was applied. Manual review required. | Warning | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl0099) |
| `SPRKCNTSCL1000` | The element `<element>` is not supported for Snowpark Connect | Conversion Error | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl1000) |
| `SPRKCNTSCL1500` | The element `<element>` of the library RDD is not supported for Snowpark Connect | Conversion Error | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl1500) |
| `SPRKCNTSCL2000` | The element `<element>` of the library Streaming is not supported for Snowpark Connect | Conversion Error | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl2000) |
| `SPRKCNTSCL2500` | The element `<element>` of the library ML is not supported for Snowpark Connect | Conversion Error | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl2500) |
| `SPRKCNTSCL3000` | The element `<element>` of the library MLLIB is not supported for Snowpark Connect | Conversion Error | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl3000) |
| `SPRKCNTSCL3500` | The element `<element>` of the library Spark Session is not supported for Snowpark Connect | Conversion Error | [Link](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala#sprkcntscl3500) |

## SCOS Category to EWI Code Mapping

Use this table to determine the correct EWI code when generating `Issues.csv` from SCOS analysis findings.

### By SCOS Analysis Category

| SCOS Category | Scala Code | SMA Category |
|---------------|------------|--------------|
| RDD operation (`has_rdd_usage`) | `SPRKCNTSCL1500` | Conversion Error |
| Unsupported Module: `org.apache.spark.ml` | `SPRKCNTSCL2500` | Conversion Error |
| Unsupported Module: `org.apache.spark.streaming` | `SPRKCNTSCL2000` | Conversion Error |
| Unsupported Module: `org.apache.spark.mllib` | `SPRKCNTSCL3000` | Conversion Error |
| Unsupported Module: `org.apache.spark.graphx` | `SPRKCNTSCL1000` | Conversion Error |
| SparkSession creation / replacement | `SPRKCNTSCL3500` | Conversion Error |
| SparkContext element | `SPRKCNTSCL1500` | Conversion Error |
| Unsupported Format (avro, orc, delta, binary) | `SPRKCNTSCL1000` | Conversion Error |
| Wildcard/Glob File Read (`*.json`, `*.csv`, etc.) | `SPRKCNTSCL1000` | Conversion Error |
| Unsupported Save Mode | `SPRKCNTSCL1000` | Conversion Error |
| Unsupported Option | `SPRKCNTSCL1000` | Warning |
| No-Op API (hint, repartition, coalesce) | `SPRKCNTSCL1000` | Warning |
| No-Op Config | `SPRKCNTSCL1000` | Warning |
| UDF Serialization | `SPRKCNTSCL1000` | Warning |
| Performance Optimization | `SPRKCNTSCL1000` | Information |
| Recommended Improvement (SF Connector pushdown) | `SPRKCNTSCL1000` | Information |
| Map Column Subscript with Column Key | `SPRKCNTSCL1000` | Conversion Error |
| Generic / unclassified | `SPRKCNTSCL1000` | Conversion Error |

### By SCOS Comment Prefix

| Comment Pattern | Scala Code | SMA Category |
|-----------------|------------|--------------|
| `// SCOS: TODO -` | `SPRKCNTSCL1000` | Conversion Error |
| `// SCOS: Performance tip -` | `SPRKCNTSCL1000` | Information |
| `// SCOS:` (fix applied/reviewed) | `SPRKCNTSCL1000` | Warning |

### Keyword-Based Code Refinement

When the generic `*1000` code would be assigned, refine it by checking the `root_cause` field from `analysis.json`:

| Keyword in root_cause | Scala Code |
|-----------------------|------------|
| `rdd`, `parallelize`, `sparkContext`, `SparkContext` | `SPRKCNTSCL1500` |
| `org.apache.spark.ml`, `spark.ml` | `SPRKCNTSCL2500` |
| `streaming`, `DStream`, `StreamingContext` | `SPRKCNTSCL2000` |
| `org.apache.spark.mllib`, `spark.mllib` | `SPRKCNTSCL3000` |
| `SparkSession`, `getOrCreate`, `builder` | `SPRKCNTSCL3500` |
| `wildcard`, `glob`, `*.json`, `*.csv`, `*.parquet` | `SPRKCNTSCL1000` |
| `create_map`, `map`, `apply`, `element_at`, `Column subscript`, `UNSUPPORTED_DATA_TYPE` | `SPRKCNTSCL1000` |
| `checkpoint`, `localCheckpoint`, `randomSplit`, `sortWithinPartitions`, `isEmpty`, `toLocalIterator` | `SPRKCNTSCL1000` |
| `withWatermark`, `writeStream`, `dropDuplicatesWithinWatermark` | `SPRKCNTSCL2000` |
| `javaRDD`, `toJavaRDD`, `toJSON`, `reduce`, `queryExecution`, `sqlContext` | `SPRKCNTSCL1000` |
| `fallback`, `partial migration`, `not fully processed` | `SPRKCNTSCL0099` |

## External Documentation

- [Issue Codes by Source (index)](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/README)
- [Snowpark Connect Scala Codes](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/snowpark-connect-codes-scala)
- [Spark-Scala Issue Codes (SPRKSCL)](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/spark-scala/README)
- [SQL Issue Codes (SSC-EWI)](https://docs.snowflake.com/en/migrations/sma-docs/issue-analysis/issue-codes-by-source/sql/README)

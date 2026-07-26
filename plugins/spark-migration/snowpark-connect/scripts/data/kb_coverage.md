# Unified Trigger-KB — Coverage

Raw rules ingested: **1374**
Unique anchors after merge: **427**
Auto-firing rules (reliable literal trigger): **307**
Reference-only rules (manual, no auto-trigger): **120**
Anchors backed by >1 source: **145**

## Raw rules by source

| Source | Rules |
|---|---|
| gaps-report | 113 |
| behavioral | 169 |
| csv | 1092 |

## Merged rules by severity

| Severity | Rules |
|---|---|
| high | 30 |
| medium | 234 |
| low | 163 |

## Merged rules by disposition

| Disposition | Rules |
|---|---|
| annotate | 371 |
| awareness | 37 |
| rewrite | 19 |

## Merged rules by trigger kind

| Kind | Rules |
|---|---|
| python_or_sql | 186 |
| manual | 120 |
| python_method | 105 |
| sql_construct | 16 |

## Sample high-severity rules

- **collect_list** [P0/annotate] — Snowflake's `ARRAY_AGG` in window context does not respect the `ORDER BY` direction for element accumulation order — it always ret
- **com.hortonworks.spark.sql.hive.llap.HiveWarehouseSession.session** [trigger/annotate] — HiveWarehouseSession (the Hortonworks/Cloudera connector for Hive LLAP from Spark) is not supported in Snowpark Connect; replace w
- **CrossValidator** [trigger/annotate] — PySpark ML CrossValidator with ParamGridBuilder (hyperparameter tuning) is not available in Snowpark Connect; replace with Snowfla
- **dbutils.fs.cp** [trigger/annotate] — dbutils.fs.cp/mv/rm perform DBFS file operations not available in Snowpark Connect; use Snowflake stage operations instead (COPY I
- **dbutils.fs.ls** [trigger/annotate] — dbutils.fs (ls/head/mkdirs) is a DBFS/cloud-storage filesystem abstraction not available in Snowpark Connect; use Snowflake stages
- **dbutils.fs.mount** [trigger/annotate] — dbutils.fs.mount/unmount attach cloud storage as DBFS mount points and are not available in Snowpark Connect; use Snowflake extern
- **dbutils.notebook.exit** [trigger/annotate] — dbutils.notebook.exit() returns a value to a parent Databricks notebook and has no Snowpark Connect equivalent; use stored-procedu
- **dbutils.notebook.run** [trigger/annotate] — dbutils.notebook.run() runs another Databricks notebook as a child job and is not available in Snowpark Connect (no notebook-orche
- **dbutils.secrets.get** [trigger/annotate] — dbutils.secrets (get/list/listScopes) is Databricks secret management and is not available in Snowpark Connect; use Snowflake Secr
- **dbutils.widgets.text** [trigger/annotate] — dbutils.widgets (text/get/dropdown) create interactive notebook parameters in Databricks and are not available in Snowpark Connect
- **df.sampleBy** [trigger/annotate] — DataFrame.sampleBy / stat.sampleBy is non-deterministic in SCOS: it maps to Snowflake sampling and ignores the seed, so the sample
- **explode_outer** [trigger/annotate] — explode_outer filters out NULL elements from an array before exploding in SCOS, so NULL array elements are dropped from the output

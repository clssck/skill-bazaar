// Ported from: validate-pyspark-to-snowpark-connect/scripts/harness/helpers.py
// and conftest.py (connection / JDBC helpers).
//
// Provides seedEntrypoint, captureResults, cloneGoldenSchemaForTrial,
// declaredSinkTables, interceptConnectorReads, buildLocalSession, and
// JSON model case classes (AnalysisJson / StateJson).
//
// JVM NOTE: Python's mock.patch-based DataFrameReader interception is NOT
// available on the JVM. interceptConnectorReads instead registers catalog
// views in the trial schema so spark.table() and spark.sql() calls resolve
// to the seeded/cloned tables. Workloads that still use
//   spark.read.format("snowflake").option("dbtable","foo").load()
// must have the patch-author step rewrite them to spark.table("foo") first.

package com.snowflake.scos.kit

import com.fasterxml.jackson.annotation.JsonCreator
import com.fasterxml.jackson.databind.{DeserializationFeature, ObjectMapper, PropertyNamingStrategies}
import com.fasterxml.jackson.module.scala.DefaultScalaModule
import org.apache.spark.sql.{DataFrame, SparkSession}
import org.apache.spark.sql.types._

import java.io.{File, PrintWriter}
import java.nio.file.{Files, Paths}
import java.sql.DriverManager
import java.util.Properties
import java.time.{ZoneOffset, ZonedDateTime}
import java.time.format.DateTimeFormatter
import java.util.UUID
import scala.collection.mutable
import scala.util.Try

// ---------------------------------------------------------------------------
// JSON model case classes (analysis.json / state.json)
// ---------------------------------------------------------------------------

/** Minimal representation of analysis.json["entrypoints"][i]. */
case class EntrypointConfig(
    id: String                                        = "",
    entrypointCallable: Option[String]                = None,
    externalSources: List[ExternalSource]             = Nil,
    sinks: List[SinkConfig]                           = Nil,
    pathRedirects: Map[String, AnyRef]                = Map.empty,
    readerOptions: Map[String, String]                = Map.empty,
    schemas: Map[String, AnyRef]                      = Map.empty,
    importRoots: List[String]                         = Nil,
)

case class ExternalSource(
    id: Option[String]           = None,
    name: Option[String]         = None,
    originalPath: Option[String] = None,
    mockFile: Option[String]     = None,
    category: Option[String]     = None,
    schema: List[ColumnDef]      = Nil,
    readerOptions: Map[String, String] = Map.empty,
)

/** Allow the analyzer to write external_sources as plain strings (e.g. "src_raw_taps")
  * as well as proper objects.  Jackson calls this when the JSON token is a String. */
object ExternalSource {
  @JsonCreator
  def fromString(s: String): ExternalSource =
    ExternalSource(id = Some(s), name = Some(s), category = Some("table"))
}

case class SinkConfig(
    id: Option[String]             = None,
    name: Option[String]           = None,
    originalTarget: Option[String] = None,
    kind: Option[String]           = None,
    allowEmpty: Option[String]     = None,
    schema: List[ColumnDef]        = Nil,
)

/** Allow the analyzer to write sinks as plain strings (e.g. "sink_taps_norm")
  * as well as proper objects. */
object SinkConfig {
  @JsonCreator
  def fromString(s: String): SinkConfig =
    SinkConfig(id = Some(s), name = Some(s), kind = Some("table"))
}

case class ColumnDef(
    name: String                = "",
    `type`: Option[String]      = None,
    dtype: Option[String]       = None,
    nullable: Option[Boolean]   = None,
)

/** Top-level analysis.json model. */
case class AnalysisJson(
    entrypoints: List[EntrypointConfig]  = Nil,
    importRoots: List[String]            = Nil,
    externalSources: List[ExternalSource] = Nil,
    sinks: List[SinkConfig]              = Nil,
)

object AnalysisJson {
  private val _mapper = JsonUtil.newMapper()

  def load(path: String = EnvUtil.get("SCOS_ANALYSIS_JSON")): AnalysisJson = {
    if (path == null || path.isEmpty || !new File(path).isFile)
      throw new RuntimeException(s"SCOS_ANALYSIS_JSON not set or not found: $path")
    val raw = _mapper.readValue(new File(path), classOf[AnalysisJson])
    // Entrypoint external_sources are stored as string IDs in analysis.json.
    // ExternalSource.fromString defaults category to "table", losing the real
    // category/mock_file/schema. Resolve each string-ID source against the
    // global externalSources list so seedEntrypoint and injectIoEnvVars see
    // the full object (including category="file" and mock_file).
    val sourceById = raw.externalSources
      .flatMap(s => s.id.map(_ -> s))
      .toMap
    val resolved = raw.entrypoints.map { ep =>
      ep.copy(externalSources = ep.externalSources.map { src =>
        src.id.flatMap(sourceById.get).getOrElse(src)
      })
    }
    // Entrypoint sinks are also stored as string IDs (e.g. "scan_events_clean_sink").
    // SinkConfig.fromString sets name=id, losing the real table name stored in the global
    // sinks list (where id="scan_events_clean_sink" but name="scan_events_clean").
    // Resolve each sink string-ID against the global sinks so declaredSinkTables and
    // captureResults see the actual Snowflake write-target name, not the ID.
    val sinkById = raw.sinks.flatMap(s => s.id.map(_ -> s)).toMap
    val resolved2 = resolved.map { ep =>
      ep.copy(sinks = ep.sinks.map { sink =>
        sink.id.flatMap(sinkById.get).getOrElse(sink)
      })
    }
    raw.copy(entrypoints = resolved2)
  }
}

/** Snowflake section of state.json. */
case class SnowflakeState(
    database: String                          = "",
    goldenSchemas: Map[String, GoldenSchema]  = Map.empty,
    /** Pre-cloned trial schemas: ep_id → already-cloned schema name.
      * When set, cloneGoldenSchemaForTrial skips JDBC and returns this directly.
      * Useful when JDBC-based cloning is unavailable in the environment (driver/network
      * restricted) or schemas are pre-provisioned out of band. */
    preClonedSchemas: Map[String, String]     = Map.empty,
)

case class GoldenSchema(
    schema: String       = "",
    stage: String        = "",
    stagePrefix: String  = "",
)

case class ScosConfig(
    connectionName: String = "",
)

/** Top-level state.json model. */
case class StateJson(
    snowflake: SnowflakeState = SnowflakeState(),
    config: ScosConfig        = ScosConfig(),
)

object StateJson {
  private val _mapper = JsonUtil.newMapper()   // same SNAKE_CASE mapper as analysis.json

  def load(path: String = EnvUtil.get("SCOS_STATE_JSON")): StateJson = {
    if (path == null || path.isEmpty || !new File(path).isFile)
      throw new RuntimeException(s"SCOS_STATE_JSON not set or not found: $path")
    _mapper.readValue(new File(path), classOf[StateJson])
  }
}

// ---------------------------------------------------------------------------
// Jackson helpers
// ---------------------------------------------------------------------------

private[kit] object JsonUtil {
  /** Both analysis.json and state.json use snake_case keys (external_sources, mock_file,
    * golden_schemas, stage_prefix, connection_name, …). Case-class fields keep idiomatic
    * camelCase (externalSources, stagePrefix, connectionName) and the SNAKE_CASE strategy
    * maps them automatically — the same pattern Jackson uses for the analysis case classes. */
  def newMapper(): ObjectMapper = {
    val m = new ObjectMapper()
    m.registerModule(DefaultScalaModule)
    m.configure(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES, false)
    m.setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
    m
  }
}

// ---------------------------------------------------------------------------
// EnvUtil — env-var simulation via System properties (forked JVM safe)
// ---------------------------------------------------------------------------

/**
 * Environment variable accessor that reads from a process-level override map
 * (populated by setEnv) first, then System.getenv, then System.getProperty.
 *
 * Because Test/fork=true isolates each test JVM, setEnv/unsetEnv are safe to
 * use inside beforeAll/afterAll without cross-test contamination.
 *
 * JVM NOTE: Python's os.environ mutation works in-process because cpython is
 * single-interpreter.  On the JVM, System.setenv is not public, so we use a
 * companion-object map that the shims and harness always consult first.
 */
object EnvUtil {
  private[kit] val overrides = new java.util.concurrent.ConcurrentHashMap[String, String]()

  def setEnv(key: String, value: String): Unit = {
    val v = normalizeStagePath(key, value)
    overrides.put(key, v)
    // Also set as system property so code that calls System.getProperty works.
    System.setProperty(key, v)
  }

  /**
   * Normalize Snowflake stage-PATH values to end with `/` at the single
   * injection chokepoint, so a workload's `s"$STAGE_PATH/file"` or a directory
   * read resolves regardless of whether the provisioner/patch-author supplied the
   * trailing slash. Targets only stage *directory* paths:
   *   - the env key is named like a stage path (`*_STAGE_PATH` / `*STAGE_PATH`),
   *     or the value is a Snowflake stage ref (`@db.schema.stage/prefix`), AND
   *   - the last `/`-segment has no file extension (so a value pointing at a
   *     single file like `.../data.parquet` is never mangled).
   */
  private[kit] def normalizeStagePath(key: String, value: String): String = {
    if (value == null || value.isEmpty || value.endsWith("/")) return value
    val isStage  = key.toUpperCase.endsWith("STAGE_PATH") || value.startsWith("@")
    val lastSeg  = value.split("/").lastOption.getOrElse("")
    val looksFile = lastSeg.contains(".")
    if (isStage && !looksFile) value + "/" else value
  }

  def unsetEnv(key: String): Unit = {
    overrides.remove(key)
    System.clearProperty(key)
  }

  /** Read key from override map → System.getenv → System.getProperty → default. */
  def get(key: String, default: String = ""): String = {
    val ov = overrides.get(key)
    if (ov != null) return ov
    val env = System.getenv(key)
    if (env != null) return env
    Option(System.getProperty(key)).getOrElse(default)
  }

  def saveAndSet(keys: Map[String, String]): Map[String, Option[String]] = {
    val saved = keys.map { case (k, _) => k -> Option(overrides.get(k)) }
    keys.foreach { case (k, v) => setEnv(k, v) }
    saved
  }

  def restore(saved: Map[String, Option[String]]): Unit = {
    saved.foreach {
      case (k, Some(v)) => setEnv(k, v)
      case (k, None)    => unsetEnv(k)
    }
  }

  /** SCOS Phase-B reflection class names, overridable via env/system property.
   *  Centralised here so ScosTrialFixture and tests share one resolution path. */
  def scosClientClass: String =
    get("SCOS_CLIENT_CLASS", "com.snowflake.snowpark_connect.client.SnowparkConnectSession")
  def scosSessionClass: String =
    get("SCOS_SESSION_CLASS", "com.snowflake.snowpark_connect.client.SnowflakeSession")
}

// ---------------------------------------------------------------------------
// Helpers object
// ---------------------------------------------------------------------------

object Helpers {

  // -------------------------------------------------------------------------
  // Path helpers
  // -------------------------------------------------------------------------

  /** mock_data root for a given entrypoint id. */
  def mockDataDirForEp(epId: String): String = {
    val root = EnvUtil.get("SCOS_MOCK_DATA_DIR", "/tmp/scos_mock_data")
    Paths.get(root, epId).toString
  }

  /**
   * Inject SCOS_INPUT_*, SCOS_TEST_AUX_*, and SCOS_SINK_* env vars for
   * file-category sources and sinks declared in the entrypoint config.
   *
   * Ports: conftest.py::io_env_for_trial() from validate-pyspark-to-snowpark-connect.
   *
   * File-category sources are mock files on disk (set as SCOS_INPUT_<ID>).
   * File-category sinks are per-trial capture directories (set as SCOS_SINK_<ID>).
   * Both must be exposed via System.getProperty (EnvUtil.setEnv writes there)
   * so workloads patched to System.getProperty("SCOS_INPUT_FOO") see the value.
   */
  def injectIoEnvVars(
      epConfig: EntrypointConfig,
      mockDataDir: String,
      trialDir: String,
  ): Unit = {
    // File-category sources → SCOS_INPUT_<ID> and SCOS_TEST_AUX_<NAME>
    // Table/connector-category sources → SCOS_INPUT_<ID> pointing to mock parquet file.
    // Mirrors PySpark file_io_env: patched workloads call
    //   spark.read.parquet(System.getProperty("SCOS_INPUT_<id>"))
    // for both file and table/connector sources.
    epConfig.externalSources.foreach { src =>
      val rawId    = src.id.orElse(src.name).getOrElse("")
      val id       = rawId.toUpperCase.replaceAll("[^A-Z0-9]", "_")
      val mockFile = src.mockFile.getOrElse("")
      if (id.nonEmpty && mockFile.nonEmpty) {
        val path = Paths.get(mockDataDir, mockFile).toString
        if (src.category.contains("file")) {
          EnvUtil.setEnv(s"SCOS_INPUT_$id", path)
          if (rawId != id) EnvUtil.setEnv(s"SCOS_INPUT_$rawId", path)
          // Expose as SCOS_TEST_AUX_<NAME> (mirrors Python io_env_for_trial)
          src.name.foreach { n =>
            val auxKey = n.toUpperCase.replaceAll("[^A-Z0-9]", "_")
            if (auxKey != id) EnvUtil.setEnv(s"SCOS_TEST_AUX_$auxKey", path)
          }
        } else {
          // table / snowflake / jdbc: inject SCOS_INPUT_* pointing at the mock parquet.
          // The patched workload uses spark.read.parquet(getProperty("SCOS_INPUT_<id>")).
          EnvUtil.setEnv(s"SCOS_INPUT_$id", path)
          if (rawId != id) EnvUtil.setEnv(s"SCOS_INPUT_$rawId", path)
        }
      }
    }

    // Sinks → SCOS_SINK_<ID>  (per-trial capture dir)
    // Inject for ALL sinks regardless of kind: patched workloads that write via
    // System.getProperty("SCOS_SINK_<id>") need the path set even when the sink
    // kind is recorded as "table" in analysis.json (the string-deserialised default).
    val sinkCaptureRoot = new java.io.File(trialDir, "sink_captures")
    epConfig.sinks.foreach { sink =>
      val rawId = sink.id.orElse(sink.name).getOrElse("")
      val id    = rawId.toUpperCase.replaceAll("[^A-Z0-9]", "_")
      if (id.nonEmpty) {
        val captureDir = new java.io.File(sinkCaptureRoot, rawId.toLowerCase)
        captureDir.mkdirs()
        EnvUtil.setEnv(s"SCOS_SINK_$id", captureDir.getAbsolutePath + "/")
        // Also set with original-case ID for workloads that use lowercase property names.
        if (rawId != id) EnvUtil.setEnv(s"SCOS_SINK_$rawId", captureDir.getAbsolutePath + "/")
      }
    }
  }

  /** Bare (unqualified) table name from a FQN or path expression.
   *  Returns "" for DBFS interpolation paths (e.g. dbfs:${getBronzeLocation(banners)})
   *  whose last segment still contains unsafe SQL identifier characters like { } $ ( ) [ ].
   */
  def bareTableName(raw: String): String = {
    if (raw == null || raw.isEmpty) return ""
    val clean = raw.replace("`", "").replace("\"", "").trim
    // last segment of dot-separated FQN, last segment of a path
    val dotPart = clean.split("\\.", -1).last
    val slashPart = dotPart.split("/", -1).last
    // strip extension
    val withoutExt = slashPart.split("\\.", -1) match {
      case parts if parts.length > 1 => parts.dropRight(1).mkString(".")
      case parts                     => parts(0)
    }
    val result = withoutExt.toLowerCase.trim
    // Reject DBFS interpolation expressions (e.g. ${getbronzelocation(banners)}) that
    // produce unsafe SQL identifiers.  safeIdent would throw on these; return "" so
    // callers skip the sink/source silently instead of aborting the test suite.
    if (result.exists(c => "{}$()[]".indexOf(c) >= 0)) "" else result
  }

  // -------------------------------------------------------------------------
  // Phase A — local SparkSession with Delta
  // -------------------------------------------------------------------------

  /**
   * Build a local SparkSession backed by Delta Lake.
   * Ported from conftest.py::_build_local_session.
   */
  def buildLocalSession(warehouseDir: String): SparkSession = {
    // Phase A uses plain Hive catalog (not DeltaCatalog) so seedEntrypoint's saveAsTable
    // does NOT trigger DatabricksLogging.recordOperation, which creates too-many-args lambdas
    // in Scala 2.12 + Java 17 (DELTA-3744 / LambdaMetafactory.altMetafactory limit).
    // Workloads can still write delta format via df.write.format("delta").save(path) which
    // bypasses the catalog entirely.
    SparkSession.builder()
      .master("local[1]")
      .config("spark.sql.shuffle.partitions", "1")
      .config("spark.sql.warehouse.dir", warehouseDir)
      .config("spark.driver.extraJavaOptions", s"-Dderby.system.home=$warehouseDir/derby")
      .config("spark.driver.host", "127.0.0.1")
      .config("spark.driver.bindAddress", "127.0.0.1")
      .config("spark.databricks.delta.schema.autoMerge.enabled", "true")
      .config("spark.databricks.delta.commitInfo.enabled", "false")
      .getOrCreate()
  }

  /**
   * Install Delta idempotency patches (Phase A only).
   * Ported from helpers.py::install_delta_patches.
   *
   * JVM NOTE: Unlike Python, we cannot monkey-patch DataFrame.write.saveAsTable.
   * Instead, install_delta_patches configures Spark SQL to tolerate missing
   * tables for DELETE/INSERT operations via the custom SQL listener below.
   * Patch-author edits should be reviewed if they rely on Mode.Overwrite+saveAsTable
   * for idempotency; the Scala Delta DSL handles this natively.
   */
  def installDeltaPatches(spark: SparkSession): Unit = {
    // Register a no-op listener; actual idempotency comes from Delta's own
    // CREATE OR REPLACE / MERGE semantics when Mode.Overwrite is used.
    // This is a no-op stub — workloads that need richer idempotency should
    // use df.write.mode(SaveMode.Overwrite).format("delta").saveAsTable(name).
    ()
  }

  // -------------------------------------------------------------------------
  // Type resolution
  // -------------------------------------------------------------------------

  private val sparkTypeMap: Map[String, DataType] = Map(
    "string"         -> StringType,
    "varchar"        -> StringType,
    "text"           -> StringType,
    "char"           -> StringType,
    "int"            -> IntegerType,
    "integer"        -> IntegerType,
    "long"           -> LongType,
    "bigint"         -> LongType,
    "short"          -> ShortType,
    "smallint"       -> ShortType,
    "byte"           -> ByteType,
    "tinyint"        -> ByteType,
    "float"          -> FloatType,
    "double"         -> DoubleType,
    "real"           -> DoubleType,
    "boolean"        -> BooleanType,
    "bool"           -> BooleanType,
    "date"           -> DateType,
    "timestamp"      -> TimestampType,
    "timestamp_ltz"  -> TimestampType,
    "binary"         -> BinaryType,
  )

  def resolveSparkType(typeStr: String): DataType = {
    if (typeStr == null || typeStr.isEmpty) return StringType
    val base = typeStr.toLowerCase.split("\\(")(0).trim
    // Accept "LongType"-style class names from the analyzer
    val key = if (base.endsWith("type")) base.stripSuffix("type") else base
    // decimal/numeric carry precision+scale that must be preserved — otherwise a
    // decimal(18,4) source column would be seeded as the default (or worse, String),
    // diverging from the DECIMAL(18,4) golden Snowflake table. Mirrors Python
    // helpers._resolve_spark_type (default DECIMAL(38,18) when unparametrized).
    if (key == "decimal" || key == "numeric") {
      val m = """\(\s*(\d+)\s*,\s*(\d+)\s*\)""".r.findFirstMatchIn(typeStr)
      return m.map(g => DecimalType(g.group(1).toInt, g.group(2).toInt)).getOrElse(DecimalType(38, 18))
    }
    // timestamp_ntz only exists as a static type from Spark 3.4+. Resolve it at runtime
    // via DDL so the kit still compiles against older Spark (3.3) when aligned to the
    // workload in Phase A; on 3.3 the unknown type falls back to TimestampType.
    if (key == "timestamp_ntz") {
      return try { DataType.fromDDL("timestamp_ntz") }
             catch { case _: Throwable => TimestampType }
    }
    sparkTypeMap.getOrElse(key, sparkTypeMap.getOrElse(base, StringType))
  }

  def buildSparkSchema(fields: List[ColumnDef]): StructType = {
    StructType(fields.map { f =>
      val typeStr = f.dtype.orElse(f.`type`).getOrElse("string")
      StructField(f.name, resolveSparkType(typeStr), f.nullable.getOrElse(true))
    })
  }

  // -------------------------------------------------------------------------
  // seed_entrypoint — Ported from helpers.py::seed_entrypoint
  // -------------------------------------------------------------------------

  /**
   * Seed external source tables and pre-create empty sink tables into outputSchema.
   * Reads mock CSV/JSON/Parquet files from mockDataDir via spark.read.
   * Writes via DataFrame.write.mode(Overwrite).saveAsTable.
   * Works for both Phase A (Delta-backed local Spark) and Phase B (SCOS Spark).
   *
   * Returns the list of fully-qualified table names created by the harness.
   */
  def seedEntrypoint(
      spark: SparkSession,
      epConfig: EntrypointConfig,
      mockDataDir: String,
      outputSchema: String,
  ): List[String] = {
    val seeded   = mutable.ListBuffer[String]()
    val seededSet = mutable.Set[String]()

    // --- external sources (category: table / snowflake / jdbc) ---
    val tableCategories = Set("table", "snowflake", "jdbc")
    for (src <- epConfig.externalSources if tableCategories.contains(src.category.getOrElse(""))) {
      val bare = bareTableName(src.originalPath.orElse(src.name).getOrElse(""))
      if (bare.isEmpty) ()
      else {
        val target   = s"$outputSchema.$bare"
        val mockFile = src.mockFile.getOrElse("")
        if (mockFile.nonEmpty) {
          val csvPath = Paths.get(mockDataDir, mockFile).toString
          if (new File(csvPath).isFile) {
            Try {
              val df = readMockFile(spark, csvPath, src.schema, src.readerOptions)
              df.write.mode("overwrite").saveAsTable(target)
              seeded += target.toLowerCase
              seededSet += target.toLowerCase
            }.failed.foreach { e =>
              System.err.println(s"warn: seed_entrypoint: failed to seed $target: $e")
            }
          }
        }
      }
    }

    // --- pre-create empty sink tables ---
    for (sink <- epConfig.sinks if sink.kind.contains("table")) {
      val bare = bareTableName(sink.originalTarget.orElse(sink.name).getOrElse(""))
      if (bare.isEmpty || sink.schema.isEmpty) ()
      else {
        val target = s"$outputSchema.$bare"
        if (!seededSet.contains(target.toLowerCase)) {
          Try {
            // spark.sparkContext is NOT available on Spark Connect (SCOS) sessions.
            // Use an empty java.util.List<Row> instead — compatible with both local Spark and SCOS.
            val emptyDf = spark.createDataFrame(
              java.util.Collections.emptyList[org.apache.spark.sql.Row](),
              buildSparkSchema(sink.schema),
            )
            emptyDf.write.mode("overwrite").saveAsTable(target)
            seeded += target.toLowerCase
            seededSet += target.toLowerCase
          }.failed.foreach { e =>
            System.err.println(s"warn: seed_entrypoint: failed to pre-create sink $target: $e")
          }
        }
      }
    }

    seeded.toList
  }

  /** Read a single mock file (CSV / JSON / Parquet) with optional schema. */
  private def readMockFile(
      spark: SparkSession,
      path: String,
      schema: List[ColumnDef],
      readerOptions: Map[String, String],
  ): DataFrame = {
    val ext = path.toLowerCase.split("\\.").lastOption.getOrElse("csv")
    var reader = spark.read
    readerOptions.foreach { case (k, v) => reader = reader.option(k, v) }

    if (schema.nonEmpty) {
      val st = buildSparkSchema(schema)
      ext match {
        // Parquet files carry an embedded schema. Forcing the analysis.json schema
        // via reader.schema(st) fails when the prewarm encodes string-ID columns as
        // INT64 — the vectorized reader cannot convert INT64 to BINARY(UTF8) and the
        // write task aborts. Instead, read with the parquet's own types and then cast
        // each declared column to the target type so downstream workloads see the
        // correct types (e.g. LongType IDs cast to StringType).
        case "parquet" =>
          val rawDf = reader.parquet(path)
          schema.foldLeft(rawDf) { (df, colDef) =>
            if (df.schema.fieldNames.exists(_.equalsIgnoreCase(colDef.name))) {
              val typeStr    = colDef.dtype.orElse(colDef.`type`).getOrElse("string")
              val targetType = resolveSparkType(typeStr)
              df.withColumn(colDef.name, df(colDef.name).cast(targetType))
            } else df
          }
        case "json" | "jsonl" | "ndjson" => reader.schema(st).json(path)
        case "tsv"                       =>
          reader.option("header", "true").option("sep", "\t")
            .option("nullValue", "").schema(st).csv(path)
        case _                           =>
          reader.option("header", "true").option("nullValue", "").schema(st).csv(path)
      }
    } else {
      ext match {
        case "parquet"                   => reader.parquet(path)
        case "json" | "jsonl" | "ndjson" => reader.json(path)
        case "tsv"                       =>
          reader.option("header", "true").option("sep", "\t")
            .option("inferSchema", "true").option("nullValue", "").csv(path)
        case _                           =>
          reader.option("header", "true").option("inferSchema", "true")
            .option("nullValue", "").csv(path)
      }
    }
  }

  // -------------------------------------------------------------------------
  // captureResults — Ported from helpers.py::capture_results
  //
  // Output layout (must match ScosComparator / Track A expectations):
  //   <outputDir>/tables/<name>.parquet
  //   <outputDir>/_index.json
  //
  // _index.json schema:
  //   { trial_id, phase, output_schema, captured_at,
  //     tables: [{name, path, schema_json, row_count, absolute_path}],
  //     artifacts: [], failures: [] }
  // -------------------------------------------------------------------------

  /**
   * Snapshot all tables in outputSchema to Parquet + write _index.json manifest.
   *
   * @param spark        active SparkSession
   * @param outputSchema schema whose tables to capture
   * @param outputDir    trial result directory (e.g. results/phase_a/<ep_id>)
   * @param exclude      table names to skip (the seeded inputs)
   * @param excludeIfEmpty  declared sinks: skip if empty and not written by workload
   * @return the manifest as a Map (mirrors Python dict return)
   */
  def captureResults(
      spark: SparkSession,
      outputSchema: String,
      outputDir: String,
      exclude: Seq[String]        = Nil,
      excludeIfEmpty: Seq[String] = Nil,
  ): Map[String, Any] = {

    val mapper    = JsonUtil.newMapper()
    val tablesDir = new File(outputDir, "tables")
    tablesDir.mkdirs()

    val excluded           = (exclude ++ exclude.map(_.split("\\.").last)).map(_.toLowerCase).toSet
    val excludeIfEmptySet  = (excludeIfEmpty ++ excludeIfEmpty.map(_.split("\\.").last)).map(_.toLowerCase).toSet

    val capturedTables = mutable.ListBuffer[Map[String, Any]]()
    val failures       = mutable.ListBuffer[Map[String, String]]()

    // List tables in the output schema
    val schemaId = safeIdent(outputSchema)
    val rows = Try(spark.sql(s"SHOW TABLES IN $schemaId").collect()).getOrElse(Array.empty)

    // Fallback: if the catalog is empty (e.g. the workload called spark.stop() and we
    // rebuilt the session), scan the warehouse filesystem for Delta/Parquet directories
    // written by saveAsTable and register them so SHOW TABLES works.
    if (rows.isEmpty) {
      val warehousePath = Try(spark.conf.get("spark.sql.warehouse.dir")).getOrElse("")
      if (warehousePath.nonEmpty) {
        val warehouseRoot = warehouseDirFile(warehousePath)
        val schemaDb = new java.io.File(warehouseRoot, s"${schemaId}.db")
        if (!schemaDb.isDirectory) {
          // Also try without .db suffix (some Hive configurations omit it)
          Try {
            val alt = new java.io.File(warehouseRoot, schemaId)
            if (alt.isDirectory) {
              spark.sql(s"CREATE DATABASE IF NOT EXISTS $schemaId")
              Option(alt.listFiles(f => f.isDirectory && !f.getName.startsWith("_"))).getOrElse(Array.empty)
                .foreach { td =>
                  Try { spark.sql(s"CREATE TABLE IF NOT EXISTS $schemaId.${td.getName} USING DELTA LOCATION '${td.getAbsolutePath}'") }
                }
            }
          }
        } else {
          Try { spark.sql(s"CREATE DATABASE IF NOT EXISTS $schemaId") }
          Option(schemaDb.listFiles(f => f.isDirectory && !f.getName.startsWith("_"))).getOrElse(Array.empty)
            .foreach { td =>
              Try { spark.sql(s"CREATE TABLE IF NOT EXISTS $schemaId.${td.getName} USING DELTA LOCATION '${td.getAbsolutePath}'") }
                .failed.foreach(e => System.err.println(s"warn: warehouse fallback: failed to register ${td.getName}: $e"))
            }
        }
      }
    }

    val rowsFinal = if (rows.nonEmpty) rows
                   else Try(spark.sql(s"SHOW TABLES IN $schemaId").collect()).getOrElse(Array.empty)

    for (row <- rowsFinal) {
      // SHOW TABLES columns: (namespace, tableName, isTemporary). Prefer the named
      // column; fall back to index 1 (tableName) — NOT index 0 (namespace).
      val tableName = Try(row.getAs[String]("tableName"))
        .recoverWith { case _ => Try(row.getString(1)) }
        .getOrElse("").toLowerCase
      if (tableName.isEmpty
          || tableName.startsWith("snowpark_temp_")
          || excluded.contains(tableName)
          || excluded.contains(s"$outputSchema.$tableName")) {
      } else {
        val outPath = new File(tablesDir, s"$tableName.parquet")
        Try {
          val df       = spark.table(s"$schemaId.${safeIdent(tableName)}").cache()
          try {
            val countResult = Try(df.count())
            countResult match {
              // SCOS tolerance: a 0-row saveAsTable writes no Parquet files; the subsequent
              // read fails with Snowflake error 253006 "file does not exist".  Treat this as
              // an empty capture (0 rows, schema preserved) so the manifest is not lost and
              // the comparator can still compare structure against the Phase-A baseline.
              case scala.util.Failure(ex)
                  if { val m = Option(ex.getMessage).getOrElse("").toLowerCase
                       m.contains("does not exist") || m.contains("no files") ||
                       m.contains("253006") } =>
                 Try {
                  // Use Java empty list instead of sparkContext.emptyRDD — sparkContext is not
                  // available on the SCOS SparkSession (spark-connect client) in Phase B.
                  val emptyDf = spark.createDataFrame(
                    java.util.Collections.emptyList[org.apache.spark.sql.Row](), df.schema)
                  emptyDf.write.mode("overwrite").parquet(outPath.getAbsolutePath)
                  val schemaJson = mapper.writeValueAsString(
                    df.schema.fields.map(f => Map("name" -> f.name, "type" -> f.dataType.typeName))
                  )
                  capturedTables += Map(
                    "name"          -> tableName,
                    "path"          -> s"tables/$tableName.parquet",
                    "schema_json"   -> schemaJson,
                    "row_count"     -> 0L,
                    "absolute_path" -> outPath.getAbsolutePath,
                  )
                }.failed.foreach { writeEx =>
                  failures += Map("source" -> "catalog", "name" -> tableName,
                    "reason" -> s"empty-table write failed: ${writeEx.getMessage.take(200)}")
                }

              case scala.util.Failure(ex) =>
                throw ex  // genuine failure — re-throw for outer Try.failed.foreach

              case scala.util.Success(rowCount) =>
                if (rowCount == 0 && (excludeIfEmptySet.contains(tableName)
                    || excludeIfEmptySet.contains(s"$outputSchema.$tableName"))) {
                  System.err.println(s"warn: captureResults: skipped allow_empty sink $tableName in $outputSchema")
                } else {
                  // SCOS error 5001: TIMESTAMP_LTZ columns cannot be unloaded to Parquet
                  // (the stage unload path fails with "TIMESTAMP_LTZ Parquet/stage unload failure").
                  // Cast all TimestampType columns to StringType before writing so the comparator
                  // can still do structural comparison on the captured data.
                  import org.apache.spark.sql.types.TimestampType
                  import org.apache.spark.sql.functions.date_format
                  val dfSafe = df.schema.fields.foldLeft(df) { (acc, field) =>
                    field.dataType match {
                      case TimestampType =>
                        acc.withColumn(field.name,
                          date_format(acc(field.name), "yyyy-MM-dd HH:mm:ss.SSSSSS"))
                      case _ => acc
                    }
                  }
                  // No coalesce(1): forcing a single partition OOMs on large tables and the
                  // comparator reads multi-part Parquet directories natively. df is cached so
                  // count() + write() do not double-scan the (possibly remote) source.
                  dfSafe.write.mode("overwrite").parquet(outPath.getAbsolutePath)
                  val schemaJson = mapper.writeValueAsString(
                    df.schema.fields.map(f => Map("name" -> f.name, "type" -> f.dataType.typeName))
                  )
                  capturedTables += Map(
                    "name"          -> tableName,
                    "path"          -> s"tables/$tableName.parquet",
                    "schema_json"   -> schemaJson,
                    "row_count"     -> rowCount,
                    "absolute_path" -> outPath.getAbsolutePath,
                  )
                }
            }
          } finally df.unpersist()
        }.failed.foreach { e =>
          failures += Map("source" -> "catalog", "name" -> tableName, "reason" -> e.getMessage.take(200))
        }
      }
    }

    // Also capture any file-form sinks written to SCOS_SINK_* paths.
    captureSinkDirs(spark, outputDir, capturedTables, failures, mapper)

    writeIndex(outputDir, outputSchema, capturedTables.toList, failures.toList, mapper)
  }

  /**
   * Capture Parquet outputs from SCOS_SINK_* directories (file-form sinks).
   * Called automatically by captureResults if any SCOS_SINK_* keys are present.
   * Mirrors Python helpers.py capture_results() file-sink branch.
   */
  private def captureSinkDirs(
      spark: SparkSession,
      outputDir: String,
      capturedTables: mutable.ListBuffer[Map[String, Any]],
      failures: mutable.ListBuffer[Map[String, String]],
      mapper: com.fasterxml.jackson.databind.ObjectMapper,
  ): Unit = {
    import scala.collection.JavaConverters._
    val tablesDir = new File(outputDir, "tables")
    tablesDir.mkdirs()
    val sinkKeys = EnvUtil.overrides.keys().asScala
      .filter(_.startsWith("SCOS_SINK_")).toList.sorted
    for (sinkKey <- sinkKeys) {
      val sinkDir     = EnvUtil.get(sinkKey)
      val sinkDirFile = new File(sinkDir)
      if (sinkDirFile.isDirectory && Option(sinkDirFile.listFiles()).exists(_.nonEmpty)) {
        val sinkName = sinkKey.stripPrefix("SCOS_SINK_").toLowerCase
        val outPath  = new File(tablesDir, s"$sinkName.parquet")
        Try {
          val df       = spark.read.parquet(sinkDir)
          val rowCount = df.count()
          if (rowCount > 0) {
            df.write.mode("overwrite").parquet(outPath.getAbsolutePath)
            val schemaJson = mapper.writeValueAsString(
              df.schema.fields.map(f => Map("name" -> f.name, "type" -> f.dataType.typeName)))
            capturedTables += Map(
              "name"          -> sinkName,
              "path"          -> s"tables/$sinkName.parquet",
              "schema_json"   -> schemaJson,
              "row_count"     -> rowCount,
              "absolute_path" -> outPath.getAbsolutePath,
              "source"        -> "file_sink",
            )
          }
        }.failed.foreach { e =>
          failures += Map("source" -> "file_sink", "name" -> sinkName, "reason" -> e.getMessage.take(200))
        }
      }
    }
  }

  private def writeIndex(
      outputDir: String,
      outputSchema: String,
      tables: List[Map[String, Any]],
      failures: List[Map[String, String]],
      mapper: ObjectMapper,
  ): Map[String, Any] = {
    val trialId      = new File(outputDir).getName
    val phaseDir     = Option(new File(outputDir).getParentFile).map(_.getName).getOrElse("unknown")
    val phase        = if (phaseDir == "phase_a" || phaseDir == "phase_b") phaseDir else "unknown"
    val capturedAt   = ZonedDateTime.now(ZoneOffset.UTC)
      .format(DateTimeFormatter.ofPattern("yyyy-MM-dd'T'HH:mm:ss.SSS'Z'"))

    val manifest: Map[String, Any] = Map(
      "trial_id"      -> trialId,
      "phase"         -> phase,
      "output_schema" -> outputSchema,
      "captured_at"   -> capturedAt,
      "tables"        -> tables,
      "artifacts"     -> List.empty[Map[String, Any]],
      "failures"      -> failures,
    )

    val indexPath = new File(outputDir, "_index.json")
    val tmpPath   = new File(outputDir, "_index.json.tmp")
    Try {
      val pw = new PrintWriter(tmpPath, "UTF-8")
      try { pw.print(mapper.writerWithDefaultPrettyPrinter().writeValueAsString(manifest)) }
      finally { pw.close() }
      tmpPath.renameTo(indexPath)
    }.failed.foreach { e =>
      System.err.println(s"warn: captureResults: failed to write _index.json: $e")
      tmpPath.delete()
    }

    manifest
  }

  // -------------------------------------------------------------------------
  // declaredSinkTables — Ported from helpers.py::declared_sink_tables
  // -------------------------------------------------------------------------

  def declaredSinkTables(epConfig: EntrypointConfig, outputSchema: String): List[String] = {
    val seen  = mutable.Set[String]()
    val sinks = mutable.ListBuffer[String]()
    for (sink <- epConfig.sinks if sink.kind.contains("table")) {
      val bare = bareTableName(sink.originalTarget.orElse(sink.name).getOrElse(""))
      if (bare.nonEmpty) {
        val target = s"$outputSchema.$bare".toLowerCase
        if (seen.add(target)) sinks += target
      }
    }
    sinks.toList
  }

  // -------------------------------------------------------------------------
  // allow_empty sink helpers — Ported from helpers.py (PR #3621)
  // -------------------------------------------------------------------------

  private def sinkCaptureKey(sink: SinkConfig): String = {
    val kind = sink.kind.getOrElse("table")
    if (kind == "table") {
      bareTableName(sink.originalTarget.orElse(sink.name).orElse(sink.id).getOrElse(""))
    } else {
      val rawId = sink.id.orElse(sink.name).getOrElse("")
      rawId.toLowerCase.replaceAll("[^a-z0-9]+", "_").stripPrefix("_").stripSuffix("_")
    }
  }

  /** Sinks explicitly allowed to be empty (have a non-blank allowEmpty reason).
   *  Table sinks → fully-qualified "schema.table"; file sinks → normalized io_id.
   *  Passed as excludeIfEmpty to captureResults so empty pre-seeded sink tables
   *  are skipped only when intentional, not silently for every declared sink. */
  def declaredAllowEmptySinkTables(epConfig: EntrypointConfig, outputSchema: String): List[String] = {
    val seen   = mutable.Set[String]()
    val result = mutable.ListBuffer[String]()
    for (sink <- epConfig.sinks if sink.allowEmpty.exists(_.trim.nonEmpty)) {
      val key    = sinkCaptureKey(sink)
      if (key.isEmpty) ()
      else {
        val target = if (sink.kind.getOrElse("table") == "table") s"$outputSchema.$key".toLowerCase
                     else key
        if (seen.add(target)) result += target
      }
    }
    result.toList
  }

  /** Normalized capture expectations for every declared sink.
   *  Returns a map from capture_name → spec map (mirrors declared_sink_capture_specs). */
  private[kit] def declaredSinkCaptureSpecs(epConfig: EntrypointConfig): Map[String, Map[String, String]] = {
    val result = mutable.LinkedHashMap[String, Map[String, String]]()
    for (sink <- epConfig.sinks) {
      val captureName = sinkCaptureKey(sink)
      if (captureName.nonEmpty && !result.contains(captureName)) {
        result(captureName) = Map(
          "captureName"  -> captureName,
          "declaredName" -> sink.name.orElse(sink.id).getOrElse(captureName),
          "kind"         -> sink.kind.getOrElse("table"),
          "allowEmpty"   -> sink.allowEmpty.map(_.trim).getOrElse(""),
        )
      }
    }
    result.toMap
  }

  /** True when the entrypoint declares at least one sink that must capture rows
   *  (i.e. at least one sink without an allowEmpty reason). */
  def requiresNonemptySinkCapture(epConfig: EntrypointConfig): Boolean =
    declaredSinkCaptureSpecs(epConfig).values.exists(_.getOrElse("allowEmpty", "").isEmpty)

  private def matchesDeclaredSink(item: Map[String, Any], captureName: String): Boolean = {
    val name = item.getOrElse("name", "").toString.trim.toLowerCase
    name == captureName || name.startsWith(s"${captureName}__")
  }

  /** Validate captured tables against declared sinks.
   *  Returns a list of failure maps with "critical" -> true for each non-allow_empty
   *  sink that produced no rows (mirrors validate_declared_sink_outputs in helpers.py). */
  def validateDeclaredSinkOutputs(
      epConfig: EntrypointConfig,
      manifest: Map[String, Any],
  ): List[Map[String, Any]] = {
    val specs = declaredSinkCaptureSpecs(epConfig)
    if (specs.isEmpty) return Nil

    val captured = manifest.getOrElse("tables", Nil).asInstanceOf[List[Map[String, Any]]]
    val guidance = "Fix the mock/schema data so the sink becomes non-empty, or set " +
      "allowEmpty to a short reason string if empty output is intentional."

    specs.values.toList.sortBy(_.getOrElse("captureName", "")).flatMap { spec =>
      val captureName = spec("captureName")
      val allowEmpty  = spec("allowEmpty")
      val matches     = captured.filter(item => matchesDeclaredSink(item, captureName))
      if (matches.isEmpty) {
        if (allowEmpty.nonEmpty) Nil
        else List(Map[String, Any](
          "source"   -> "declared_sink",
          "name"     -> captureName,
          "reason"   -> "empty_declared_sink",
          "message"  -> s"Declared sink '$captureName' produced no captured rows. $guidance",
          "critical" -> true,
        ))
      } else if (allowEmpty.nonEmpty) Nil
      else {
        val totalRows = matches.map(m => Try(m.getOrElse("row_count", 0L).toString.toLong).getOrElse(0L)).sum
        if (totalRows == 0)
          List(Map[String, Any](
            "source"   -> "declared_sink",
            "name"     -> captureName,
            "reason"   -> "empty_declared_sink",
            "message"  -> s"Declared sink '$captureName' captured 0 rows. $guidance",
            "critical" -> true,
          ))
        else Nil
      }
    }
  }

  // -------------------------------------------------------------------------
  // interceptConnectorReads — JVM equivalent of Python's mock.patch approach
  //
  // Python patches DataFrameReader.format/option/load at runtime.
  // JVM CANNOT do this (no monkey-patching).  Instead, register catalog views
  // in the trial schema so spark.table("foo") and spark.sql("...FROM foo...")
  // resolve to the seeded / cloned table.  Workloads using
  //   spark.read.format("snowflake").option("dbtable","foo").load()
  // must have been adapted (Rule 8 / patch-author step) to use spark.table().
  // -------------------------------------------------------------------------

  def interceptConnectorReads(
      spark: SparkSession,
      epConfig: EntrypointConfig,
      outputSchema: String,
  ): Unit = {
    val connectorCategories = Set("snowflake", "jdbc", "table")
    for (src <- epConfig.externalSources if connectorCategories.contains(src.category.getOrElse(""))) {
      val raw  = src.originalPath.orElse(src.name).getOrElse("")
      val bare = bareTableName(raw)
      if (bare.nonEmpty) {
        val schemaId = safeIdent(outputSchema)
        val bareId   = safeIdent(bare)
        // The fully-qualified seeded table already exists in $outputSchema; expose the
        // bare table name to workloads that reference it unqualified, via a session
        // temp view and a global temp view. (The previous code created a self-referential
        // view `$fq AS SELECT * FROM $fq`, which is circular and silently failed.)
        val fqTable = s"$schemaId.$bareId"
        Try { spark.sql(s"CREATE OR REPLACE TEMP VIEW $bareId AS SELECT * FROM $fqTable") }
        Try { spark.sql(s"CREATE OR REPLACE GLOBAL TEMP VIEW $bareId AS SELECT * FROM $fqTable") }

        // Multi-namespace sources (e.g. `ops.job_audit`, `ref.route_catalog`)
        // are referenced by the workload with their ORIGINAL namespace in Phase A.
        // Expose a qualified alias backed by the seeded table so reads resolve.
        //
        // Phase B (SCOS/Snowflake): qualified reads must NOT exist in migrated code.
        // Rule 8 of fix-rules.md requires migrated workloads to use bare table names;
        // the clone schema is the active Snowflake schema so unqualified reads resolve
        // automatically. column_check.py enforces this as an exit gate before Phase B
        // is run. We therefore do nothing here for Phase B — attempting to create
        // qualified Spark temp views is invalid syntax (Spark does not support
        // namespace-qualified TEMP VIEWs) and would silently fail anyway.
        val isScosMode = System.getProperty("SPARK_CONNECT_MODE_ENABLED") != null
        if (!isScosMode) {
          val parts = raw.replace("`", "").replace("\"", "").trim
            .split("/").last       // drop any path prefix
            .split("\\.", -1).filter(_.nonEmpty)
          if (parts.length >= 2) {
            val nsRaw = parts(parts.length - 2).toLowerCase
            if (nsRaw != schemaId) {
              // Phase A: prefer a real Hive database when the namespace is a safe ident.
              trySafeIdent(nsRaw) match {
                case Some(nsId) =>
                  Try { spark.sql(s"CREATE DATABASE IF NOT EXISTS $nsId") }
                  Try {
                    spark.table(fqTable)
                      .write.mode("overwrite")
                      .saveAsTable(s"$nsId.$bareId")
                  }.failed.foreach(e =>
                    System.err.println(s"warn: interceptConnectorReads: saveAsTable $nsId.$bareId: $e"))
                case None =>
                  // Hyphenated / unsafe namespace token — fall back to a temp view using
                  // the quoted dotted name (Hive CREATE VIEW, not TEMP VIEW, so the
                  // database must exist; we create it first).
                  val quotedNs = sqlQuotedIdent(nsRaw)
                  Try { spark.sql(s"CREATE DATABASE IF NOT EXISTS $quotedNs") }
                  Try {
                    spark.table(fqTable)
                      .write.mode("overwrite")
                      .saveAsTable(s"$quotedNs.$bareId")
                  }.failed.foreach(e =>
                    System.err.println(s"warn: interceptConnectorReads: saveAsTable $quotedNs.$bareId: $e"))
              }
            }
          }
        }
      }
    }
  }

  // -------------------------------------------------------------------------
  // Snowflake JDBC helpers (Phase B)
  // -------------------------------------------------------------------------

  /**
   * Clone the golden schema for an entrypoint trial and return the clone name.
   * Ported from helpers.py::clone_golden_schema_for_trial.
   *
   * The clone is named <GOLDEN>_T<8-hex> and lives in the same DB.
   * Callers are responsible for calling dropTrialCloneSchema on teardown.
   *
   * Connection params are resolved in priority order:
   *   1. Env vars: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_PASSWORD, ...
   *   2. ~/.snowflake/connections.toml entry named by state_json.config.connectionName
   */
  /**
   * Validate a SQL identifier sourced from LLM-authored analysis.json / state.json
   * before interpolating it into Spark SQL or JDBC. Returns it unchanged when safe;
   * throws otherwise. Blocks injection via quotes/semicolons/whitespace/dashes.
   */
  def safeIdent(name: String): String = {
    if (name == null || !name.matches("[A-Za-z0-9_$]+"))
      throw new IllegalArgumentException(s"refusing to interpolate unsafe SQL identifier: '${Option(name).getOrElse("<null>")}'")
    name
  }

  /** Like safeIdent but returns None for names that cannot be used bare (e.g. hyphens). */
  def trySafeIdent(name: String): Option[String] =
    Option(name).filter(_.matches("[A-Za-z0-9_$]+"))

  /** Quote a SQL identifier when it is not safe bare (Spark/Snowflake double-quote style). */
  def sqlQuotedIdent(name: String): String = {
    if (name == null || name.isEmpty) return "\"\""
    if (name.matches("[A-Za-z0-9_$]+")) name
    else "\"" + name.replace("\"", "\"\"") + "\""
  }

  /** Resolve spark.sql.warehouse.dir to a local filesystem directory. */
  def warehouseDirFile(warehousePath: String): java.io.File = {
    if (warehousePath == null || warehousePath.isEmpty) return new java.io.File("")
    val trimmed = warehousePath.trim
    val pathStr =
      if (trimmed.startsWith("file:")) {
        Try(new java.net.URI(trimmed).getPath).filter(_.nonEmpty).getOrElse {
          trimmed.stripPrefix("file:").replaceFirst("^//+", "")
        }
      } else trimmed
    new java.io.File(pathStr)
  }

  def cloneGoldenSchemaForTrial(stateJson: StateJson, epId: String): String = {
    val database  = stateJson.snowflake.database
    val connName  = stateJson.config.connectionName
    if (database.isEmpty)
      throw new RuntimeException("state.json missing snowflake.database")

    // Fast path: pre-cloned schema already exists — skip JDBC entirely.
    // Used when JDBC-based cloning is unavailable (driver/network restricted) or
    // schemas are pre-provisioned out of band.
    val preCloned = stateJson.snowflake.preClonedSchemas.get(epId)
    if (preCloned.isDefined && preCloned.get.nonEmpty) {
      println(s"[ScosTrialFixture] Using pre-cloned schema for $epId: ${preCloned.get}")
      return preCloned.get
    }

    val goldenSchemas = stateJson.snowflake.goldenSchemas
    val epInfo = goldenSchemas.getOrElse(epId,
      throw new RuntimeException(s"No golden schema for ep_id=$epId in state.snowflake.goldenSchemas"))
    val golden = epInfo.schema
    if (golden.isEmpty)
      throw new RuntimeException(s"Golden schema for ep_id=$epId has empty schema name")

    val clone = s"${golden}_T${UUID.randomUUID().toString.replace("-", "").take(8).toUpperCase}"

    val conn = openJdbcConnection(connName, database)
    try {
      val db = safeIdent(database); val cl = safeIdent(clone); val gold = safeIdent(golden)
      val stmt = conn.createStatement()
      try {
        stmt.execute(s"""USE DATABASE "$db"""")
        stmt.execute(s"""CREATE OR REPLACE SCHEMA "$db"."$cl" CLONE "$db"."$gold"""")
      } finally stmt.close()
    } finally {
      conn.close()
    }
    clone
  }

  def dropTrialCloneSchema(stateJson: StateJson, cloneSchema: String): Unit = {
    val database = stateJson.snowflake.database
    if (database.isEmpty || cloneSchema.isEmpty) return
    // Skip teardown for pre-cloned schemas — they're managed externally.
    if (stateJson.snowflake.preClonedSchemas.values.toSet.contains(cloneSchema)) {
      println(s"[Helpers] Skipping DROP for pre-cloned schema $cloneSchema (managed externally)")
      return
    }
    val conn = Try(openJdbcConnection(stateJson.config.connectionName, database)).getOrElse(return)
    try {
      val db = safeIdent(database); val cs = safeIdent(cloneSchema)
      val stmt = conn.createStatement()
      try stmt.execute(s"""DROP SCHEMA IF EXISTS "$db"."$cs" CASCADE""")
      finally stmt.close()
    } finally {
      conn.close()
    }
  }

  /** List the tables in the clone schema via JDBC (mirrors conftest._list_seed_tables).
    * Falls back gracefully if JDBC is unavailable — returns an empty list, and
    * the interceptConnectorReads path will still create views for table-category sources. */
  def listSeedTablesViaJdbc(stateJson: StateJson, cloneSchema: String): List[String] = {
    val database = stateJson.snowflake.database
    // If this is a pre-cloned schema, JDBC may not be available — return empty list.
    // The SCOS session (Spark SQL) will still find the tables via SHOW TABLES.
    if (stateJson.snowflake.preClonedSchemas.values.toSet.contains(cloneSchema)) {
      println(s"[Helpers] listSeedTablesViaJdbc: pre-cloned schema $cloneSchema — skipping JDBC, tables will be resolved via Spark SQL SHOW TABLES")
      return Nil
    }
    val conn     = Try(openJdbcConnection(stateJson.config.connectionName, database)).getOrElse(return Nil)
    try {
      val db = safeIdent(database); val cs = safeIdent(cloneSchema)
      val stmt = conn.prepareStatement(s"""SHOW TABLES IN SCHEMA "$db"."$cs"""")
      try {
        val rs  = stmt.executeQuery()
        val buf = mutable.ListBuffer[String]()
        try {
          while (rs.next()) {
            val tableName = rs.getString(2) // column index 2 = table name in SHOW TABLES
            buf += s"$cloneSchema.$tableName".toLowerCase
          }
        } finally rs.close()
        buf.toList
      } finally stmt.close()
    } finally {
      conn.close()
    }
  }

  /**
   * Open a Snowflake JDBC connection.
   * Auth precedence:
   *   1. OAuth token  — SNOWFLAKE_OAUTH_TOKEN env (or `token` in connections.toml)
   *      → authenticator=oauth. Removes the JIT auth patching that otherwise
   *      costs Phase A/B iterations in token-based (e.g. SPCS / Snowsight) envs.
   *   2. Key-pair      — SNOWFLAKE_PRIVATE_KEY_FILE env, or `private_key_file` /
   *      `private_key_path` in connections.toml (parity with the Python connector,
   *      so a user's existing key-pair connection works with no extra env vars).
   *   3. Password      — SNOWFLAKE_PASSWORD / connections.toml `password`.
   * Reads params from env vars (SNOWFLAKE_*) first; falls back to
   * ~/.snowflake/connections.toml for the named connection.
   */
  private[kit] def openJdbcConnection(
      connectionName: String,
      database: String,
  ): java.sql.Connection = {
    // Load the Snowflake JDBC driver
    Class.forName("net.snowflake.client.jdbc.SnowflakeDriver")

    // Try env vars first
    val acctEnv = EnvUtil.get("SNOWFLAKE_ACCOUNT", "")
    val pkFileEnv = EnvUtil.get("SNOWFLAKE_PRIVATE_KEY_FILE", "")
    val pkPassEnv = EnvUtil.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE", "")
    val (account, user, password, warehouse, role, oauthToken, authenticator, pkFile, pkPass) =
      if (acctEnv.nonEmpty) {
        (
          acctEnv,
          EnvUtil.get("SNOWFLAKE_USER", ""),
          EnvUtil.get("SNOWFLAKE_PASSWORD", ""),
          EnvUtil.get("SNOWFLAKE_WAREHOUSE", ""),
          EnvUtil.get("SNOWFLAKE_ROLE", ""),
          EnvUtil.get("SNOWFLAKE_OAUTH_TOKEN", ""),
          EnvUtil.get("SNOWFLAKE_AUTHENTICATOR", ""),
          pkFileEnv,
          pkPassEnv,
        )
      } else {
        // Parse ~/.snowflake/connections.toml for the named connection.
        // Key-pair: env var wins (explicit override), else the toml key — parity
        // with the Python connector, which reads private_key_file/private_key_path
        // straight from connections.toml.
        val params = parseConnectionsToml(connectionName)
        val tomlPk = params.get("private_key_file").orElse(params.get("private_key_path"))
          .map(_.trim).filter(_.nonEmpty).getOrElse("")
        val tomlPkPass = params.get("private_key_file_pwd").orElse(params.get("private_key_passphrase"))
          .map(_.trim).filter(_.nonEmpty).getOrElse("")
        (
          params.getOrElse("account", ""),
          params.getOrElse("user", ""),
          params.getOrElse("password", ""),
          params.getOrElse("warehouse", ""),
          params.getOrElse("role", ""),
          params.getOrElse("token", ""),
          params.getOrElse("authenticator", ""),
          if (pkFileEnv.nonEmpty) pkFileEnv else tomlPk,
          if (pkPassEnv.nonEmpty) pkPassEnv else tomlPkPass,
        )
      }

    // OAuth is active when a token is supplied, or the authenticator is
    // explicitly set to oauth.
    // Programmatic Access Token (PAT): uses authenticator=programmatic_access_token.
    val isPat    = authenticator.equalsIgnoreCase("programmatic_access_token")
    val useOauth = !isPat && (oauthToken.nonEmpty || authenticator.equalsIgnoreCase("oauth"))

    // user is not required for OAuth/PAT (the token carries identity); account always is.
    if (account.isEmpty || (user.isEmpty && !useOauth && !isPat))
      throw new RuntimeException(
        s"Snowflake JDBC: missing account/user. Set SNOWFLAKE_ACCOUNT + SNOWFLAKE_USER " +
          s"(or SNOWFLAKE_OAUTH_TOKEN) env vars, or configure " +
          s"~/.snowflake/connections.toml entry '$connectionName'."
      )

    val jdbcUrl = s"jdbc:snowflake://$account.snowflakecomputing.com/"
    val props   = new Properties()
    if (user.nonEmpty) props.setProperty("user", user)
    props.setProperty("db", database)
    if (warehouse.nonEmpty) props.setProperty("warehouse", warehouse)
    if (role.nonEmpty) props.setProperty("role", role)

    if (isPat) {
      // Programmatic Access Token — Snowflake JDBC driver native support
      props.setProperty("authenticator", "programmatic_access_token")
      if (oauthToken.nonEmpty) props.setProperty("token", oauthToken)
    } else if (useOauth) {
      // OAuth: authenticator=oauth + token. No password / key-pair.
      props.setProperty("authenticator", "oauth")
      if (oauthToken.nonEmpty) props.setProperty("token", oauthToken)
    } else {
      if (authenticator.nonEmpty) props.setProperty("authenticator", authenticator)
      if (password.nonEmpty) props.setProperty("password", password)
      // Key-pair auth — pkFile/pkPass resolved above from SNOWFLAKE_PRIVATE_KEY_FILE
      // env or the connections.toml private_key_file/private_key_path key.
      if (pkFile.nonEmpty) {
        // Expand a leading ~ like the Python connector does (JDBC won't).
        val resolvedPk =
          if (pkFile == "~" || pkFile.startsWith("~/"))
            System.getProperty("user.home") + pkFile.substring(1)
          else pkFile
        props.setProperty("private_key_file", resolvedPk)
        if (pkPass.nonEmpty) props.setProperty("private_key_file_pwd", pkPass)
      }
    }

    DriverManager.getConnection(jdbcUrl, props)
  }

  /**
   * Minimal parser for ~/.snowflake/connections.toml.
   * Handles flat [connection_name] sections with key = "value" entries.
   */
  private[kit] def parseConnectionsToml(connectionName: String): Map[String, String] = {
    val tomlPath = Paths.get(System.getProperty("user.home"), ".snowflake", "connections.toml")
    if (!tomlPath.toFile.isFile) return Map.empty
    val lines  = Files.readAllLines(tomlPath).toArray.map(_.toString)
    val params = mutable.Map[String, String]()
    var inSection = false
    val sectionHeader = s"[$connectionName]"
    for (line <- lines) {
      val trimmed = line.trim
      if (trimmed.startsWith("[")) {
        inSection = trimmed == sectionHeader
      } else if (inSection && trimmed.contains("=")) {
        val Array(k, rest @ _*) = trimmed.split("=", 2)
        val v = rest.mkString("=").trim.stripPrefix("\"").stripSuffix("\"")
        params(k.trim.toLowerCase) = v
      }
    }
    params.toMap
  }

  def deleteRecursive(file: File): Unit = {
    if (file.isDirectory) file.listFiles().foreach(deleteRecursive)
    file.delete()
  }
}

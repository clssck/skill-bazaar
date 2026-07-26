// Kit-level tests for the SCOS Scala validation harness.
//
// Covers the runtime behaviour the control-plane tests cannot reach:
//   - EnvUtil override/restore semantics (and its documented JVM limitation)
//   - SCOS Phase-B reflection class-name overrides (SCOS_CLIENT_CLASS / SCOS_SESSION_CLASS)
//   - captureResults: excludes seeded inputs + skips allow_empty sinks
//   - declaredAllowEmptySinkTables / requiresNonemptySinkCapture / validateDeclaredSinkOutputs
//
// Runs in the forked test JVM configured in build.sbt (local[1] Spark + Delta + add-opens).

package com.snowflake.scos.kit

import org.scalatest.BeforeAndAfterAll
import org.scalatest.funsuite.AnyFunSuite
import org.scalatest.matchers.should.Matchers

import java.io.File
import java.nio.file.Files

class KitSpec extends AnyFunSuite with Matchers with BeforeAndAfterAll {

  // ── EnvUtil ────────────────────────────────────────────────────────────────

  test("EnvUtil.get resolves override map first, then default") {
    EnvUtil.unsetEnv("SCOS_TEST_KEY")
    EnvUtil.get("SCOS_TEST_KEY", "fallback") shouldBe "fallback"
    EnvUtil.setEnv("SCOS_TEST_KEY", "from-override")
    EnvUtil.get("SCOS_TEST_KEY", "fallback") shouldBe "from-override"
    // setEnv mirrors into system properties (the documented in-process channel)
    System.getProperty("SCOS_TEST_KEY") shouldBe "from-override"
    EnvUtil.unsetEnv("SCOS_TEST_KEY")
    EnvUtil.get("SCOS_TEST_KEY", "fallback") shouldBe "fallback"
    System.getProperty("SCOS_TEST_KEY") shouldBe null
  }

  test("EnvUtil.saveAndSet / restore round-trips prior state") {
    EnvUtil.unsetEnv("SCOS_RT_A")
    EnvUtil.setEnv("SCOS_RT_B", "orig-b")
    val saved = EnvUtil.saveAndSet(Map("SCOS_RT_A" -> "new-a", "SCOS_RT_B" -> "new-b"))
    EnvUtil.get("SCOS_RT_A") shouldBe "new-a"
    EnvUtil.get("SCOS_RT_B") shouldBe "new-b"
    EnvUtil.restore(saved)
    // A had no prior value → cleared; B restored to its original value
    EnvUtil.get("SCOS_RT_A", "absent") shouldBe "absent"
    EnvUtil.get("SCOS_RT_B") shouldBe "orig-b"
    EnvUtil.unsetEnv("SCOS_RT_B")
  }

  // ── SCOS class overrides ─────────────────────────────────────────────────────

  test("EnvUtil normalizes stage-path env values to a trailing slash (C11)") {
    // Key named like a stage path → always trailing-slashed.
    EnvUtil.setEnv("FARECARD_STAGE_PATH", "@DB.SCH.STG/run123")
    EnvUtil.get("FARECARD_STAGE_PATH") shouldBe "@DB.SCH.STG/run123/"
    // Already-slashed value is left untouched (idempotent).
    EnvUtil.setEnv("FARECARD_STAGE_PATH", "@DB.SCH.STG/run123/")
    EnvUtil.get("FARECARD_STAGE_PATH") shouldBe "@DB.SCH.STG/run123/"
    // A stage value pointing at a single file is NOT slashed.
    EnvUtil.setEnv("SOME_STAGE_PATH", "@DB.SCH.STG/run/data.parquet")
    EnvUtil.get("SOME_STAGE_PATH") shouldBe "@DB.SCH.STG/run/data.parquet"
    // A non-stage value with an ordinary key is untouched.
    EnvUtil.setEnv("SCOS_OUTPUT_SCHEMA", "scos_abc_1234")
    EnvUtil.get("SCOS_OUTPUT_SCHEMA") shouldBe "scos_abc_1234"
    Seq("FARECARD_STAGE_PATH", "SOME_STAGE_PATH", "SCOS_OUTPUT_SCHEMA").foreach(EnvUtil.unsetEnv)
  }

  test("SCOS reflection class names honor SCOS_CLIENT_CLASS / SCOS_SESSION_CLASS overrides") {
    EnvUtil.unsetEnv("SCOS_CLIENT_CLASS")
    EnvUtil.unsetEnv("SCOS_SESSION_CLASS")
    EnvUtil.scosClientClass  shouldBe "com.snowflake.snowpark_connect.client.SnowparkConnectSession"
    EnvUtil.scosSessionClass shouldBe "com.snowflake.snowpark_connect.client.SnowflakeSession"

    EnvUtil.setEnv("SCOS_CLIENT_CLASS", "com.example.RenamedClient")
    EnvUtil.setEnv("SCOS_SESSION_CLASS", "com.example.RenamedSession")
    EnvUtil.scosClientClass  shouldBe "com.example.RenamedClient"
    EnvUtil.scosSessionClass shouldBe "com.example.RenamedSession"

    EnvUtil.unsetEnv("SCOS_CLIENT_CLASS")
    EnvUtil.unsetEnv("SCOS_SESSION_CLASS")
  }

  // ── bareTableName ─────────────────────────────────────────────────────────────

  test("bareTableName strips paths/qualifiers down to the table name") {
    Helpers.bareTableName("db.schema.orders")   shouldBe "orders"
    Helpers.bareTableName("s3://bucket/orders")  shouldBe "orders"
    Helpers.bareTableName("orders")              shouldBe "orders"
  }

  test("trySafeIdent and sqlQuotedIdent handle hyphenated namespace tokens") {
    Helpers.trySafeIdent("ops")           shouldBe Some("ops")
    Helpers.trySafeIdent("my-schema")     shouldBe None
    Helpers.sqlQuotedIdent("ops")         shouldBe "ops"
    Helpers.sqlQuotedIdent("my-schema")   shouldBe "\"my-schema\""
  }

  test("warehouseDirFile normalizes file:// warehouse URIs") {
    val f = Helpers.warehouseDirFile("file:///tmp/warehouse")
    f.getAbsolutePath should endWith("/tmp/warehouse")
  }

  // ── captureResults (local Spark) ──────────────────────────────────────────────

  private var spark: org.apache.spark.sql.SparkSession = _
  private var warehouse: File = _

  override def beforeAll(): Unit = {
    warehouse = Files.createTempDirectory("scos-kit-test-").toFile
    spark = Helpers.buildLocalSession(new File(warehouse, "warehouse").getAbsolutePath)
    Helpers.installDeltaPatches(spark)
  }

  override def afterAll(): Unit = {
    if (spark != null) spark.stop()
  }

  test("captureResults excludes seeded inputs and skips empty declared sinks") {
    import org.apache.spark.sql.Row
    import org.apache.spark.sql.types._
    val idName = StructType(Seq(StructField("id", IntegerType), StructField("name", StringType)))
    val schema = "captest"
    spark.sql(s"CREATE DATABASE IF NOT EXISTS $schema")

    // Use createDataFrame (not Seq.toDF) to avoid Scala 2.12 encoder lambdas that fail
    // in Java 17 with too-many-arguments in LambdaMetafactory.altMetafactory.
    spark.createDataFrame(java.util.Arrays.asList(Row(1, "a"), Row(2, "b")), idName)
      .write.mode("overwrite").saveAsTable(s"$schema.seed_in")
    spark.createDataFrame(java.util.Arrays.asList[Row](), idName)
      .write.mode("overwrite").saveAsTable(s"$schema.empty_sink")
    spark.createDataFrame(java.util.Arrays.asList(Row(10, "x")), idName)
      .write.mode("overwrite").saveAsTable(s"$schema.out_real")

    val outDir = new File(warehouse, "results/phase_a/ep1")
    outDir.mkdirs()

    val manifest = Helpers.captureResults(
      spark          = spark,
      outputSchema   = schema,
      outputDir      = outDir.getAbsolutePath,
      exclude        = Seq("seed_in"),
      excludeIfEmpty = Seq("empty_sink"),
    )

    val captured = manifest.get("tables").collect { case ts: List[_] => ts }.getOrElse(Nil)
    val names = captured.collect { case m: Map[_, _] => m.asInstanceOf[Map[String, Any]]("name").toString }.toSet

    names shouldBe Set("out_real")
    names should not contain "seed_in"
    names should not contain "empty_sink"

    // _index.json manifest must be written next to the captured tables.
    new File(outDir, "_index.json").isFile shouldBe true
  }

  // ── allow_empty sink helpers ─────────────────────────────────────────────────

  test("declaredAllowEmptySinkTables returns only sinks with allowEmpty set") {
    val ep = EntrypointConfig(
      id = "ep1",
      sinks = List(
        SinkConfig(id = Some("orders"), name = Some("orders"),
          kind = Some("table"), allowEmpty = None),
        SinkConfig(id = Some("audit"), name = Some("audit"),
          kind = Some("table"), allowEmpty = Some("incremental no-op is valid")),
      ),
    )
    Helpers.declaredAllowEmptySinkTables(ep, "OUT") shouldBe List("out.audit")
  }

  test("requiresNonemptySinkCapture is true when any non-allow_empty sink exists") {
    val epMixed = EntrypointConfig(
      id = "ep2",
      sinks = List(
        SinkConfig(id = Some("t1"), name = Some("t1"), kind = Some("table")),
        SinkConfig(id = Some("t2"), name = Some("t2"), kind = Some("table"), allowEmpty = Some("empty ok")),
      ),
    )
    Helpers.requiresNonemptySinkCapture(epMixed) shouldBe true

    val epAllEmpty = EntrypointConfig(
      id = "ep3",
      sinks = List(
        SinkConfig(id = Some("t3"), name = Some("t3"), kind = Some("table"), allowEmpty = Some("intentional")),
      ),
    )
    Helpers.requiresNonemptySinkCapture(epAllEmpty) shouldBe false

    val epNoSinks = EntrypointConfig(id = "ep4")
    Helpers.requiresNonemptySinkCapture(epNoSinks) shouldBe false
  }

  test("validateDeclaredSinkOutputs fails when a non-allow_empty sink has 0 rows") {
    val ep = EntrypointConfig(
      id = "ep5",
      sinks = List(
        SinkConfig(id = Some("out_tbl"), name = Some("out_tbl"), kind = Some("table")),
      ),
    )
    val manifest: Map[String, Any] = Map(
      "tables" -> List(Map[String, Any]("name" -> "out_tbl", "row_count" -> 0L)),
    )
    val failures = Helpers.validateDeclaredSinkOutputs(ep, manifest)
    failures should have size 1
    failures.head.get("critical") shouldBe Some(true)
    failures.head.get("reason") shouldBe Some("empty_declared_sink")
  }

  test("validateDeclaredSinkOutputs passes when allow_empty sink has 0 rows") {
    val ep = EntrypointConfig(
      id = "ep6",
      sinks = List(
        SinkConfig(id = Some("summary"), name = Some("summary"),
          kind = Some("table"), allowEmpty = Some("empty when no data")),
      ),
    )
    val manifest: Map[String, Any] = Map(
      "tables" -> List(Map[String, Any]("name" -> "summary", "row_count" -> 0L)),
    )
    Helpers.validateDeclaredSinkOutputs(ep, manifest) shouldBe empty
  }

  test("validateDeclaredSinkOutputs fails when declared sink is absent from manifest") {
    val ep = EntrypointConfig(
      id = "ep7",
      sinks = List(
        SinkConfig(id = Some("missing_sink"), name = Some("missing_sink"), kind = Some("table")),
      ),
    )
    val manifest: Map[String, Any] = Map("tables" -> List.empty[Map[String, Any]])
    val failures = Helpers.validateDeclaredSinkOutputs(ep, manifest)
    failures should have size 1
    failures.head.get("critical") shouldBe Some(true)
  }

  test("validateDeclaredSinkOutputs passes when sink has rows") {
    val ep = EntrypointConfig(
      id = "ep8",
      sinks = List(
        SinkConfig(id = Some("result"), name = Some("result"), kind = Some("table")),
      ),
    )
    val manifest: Map[String, Any] = Map(
      "tables" -> List(Map[String, Any]("name" -> "result", "row_count" -> 42L)),
    )
    Helpers.validateDeclaredSinkOutputs(ep, manifest) shouldBe empty
  }

  // ── resolveSparkType: decimal fidelity ───────────────────────────────────────

  test("resolveSparkType preserves decimal/numeric precision and scale") {
    import org.apache.spark.sql.types._
    Helpers.resolveSparkType("decimal(18,4)")  shouldBe DecimalType(18, 4)
    Helpers.resolveSparkType("DECIMAL(10, 2)") shouldBe DecimalType(10, 2)
    Helpers.resolveSparkType("numeric(38,0)")  shouldBe DecimalType(38, 0)
    Helpers.resolveSparkType("decimal")        shouldBe DecimalType(38, 18) // unparametrized default
    Helpers.resolveSparkType("DecimalType(9,3)") shouldBe DecimalType(9, 3) // class-name form
    // sanity: non-decimal types still resolve
    Helpers.resolveSparkType("long")           shouldBe LongType
    Helpers.resolveSparkType("string")         shouldBe StringType
  }

}

// Ported from: validate-pyspark-to-snowpark-connect/scripts/harness/conftest.py (trial fixture)
//
// ScalaTest BeforeAndAfterAll trait that provides the A/B trial environment:
//
//   Phase A (SCOS_FLAVOR=source or unset):
//     - local SparkSession + Delta Lake, fresh per-test schema
//     - seeds mock data into Delta tables
//     - installs date pinning via Spark conf
//
//   Phase B (SCOS_FLAVOR=migrated):
//     - clones golden Snowflake schema for the trial via JDBC
//     - initialises SnowparkConnectSession via JVM reflection
//       (SCOS client does not need to be on the COMPILE classpath; only the
//        runtime classpath when running Phase B)
//     - seeds/bridges local reads; intercepts connector reads via catalog views
//
// JVM differences from Python:
//   - No monkey-patching: interceptConnectorReads creates catalog views instead.
//   - No sitecustomize/loader/fallback: JVM classloader isolation handles this.
//   - EnvUtil.setEnv uses System.setProperty (per-JVM-fork safe).
//   - SnowparkConnectSession is accessed via reflection to avoid compile dep.

package com.snowflake.scos.kit

import org.apache.spark.sql.SparkSession
import org.scalatest.{Assertions, BeforeAndAfterAll, Suite}

import java.io.File
import java.nio.file.{Files, Paths}
import java.util.UUID
import scala.util.{Failure, Success, Try}

/**
 * Mix into a ScalaTest Suite (e.g. AnyFunSuite) to get the full A/B trial environment.
 *
 * {{{
 *   class MyEntrypointSpec extends AnyFunSuite with ScosTrialFixture {
 *     override val epId = "my_ep_id"
 *     test("workload produces expected tables") {
 *       val ep = analysis.entrypoints.find(_.id == epId).get
 *       // call the workload, then captureResults(spark, outputSchema, trialDir)
 *     }
 *   }
 * }}}
 */
trait ScosTrialFixture extends BeforeAndAfterAll with Assertions { self: Suite =>

  /** Entrypoint ID — must match an entry in analysis.json["entrypoints"][i]["id"]. */
  val epId: String

  /** epId sanitized to a SQL/filesystem-safe token (epId itself may contain '-' etc.). */
  private def safeEpId: String = epId.replaceAll("[^A-Za-z0-9_]", "_")

  // Populated by beforeAll(); available to all tests.
  protected var spark:        SparkSession         = _
  protected var seedTables:   List[String]         = Nil
  protected var sinkTables:   List[String]         = Nil
  protected var outputSchema: String               = ""
  protected var mockDataDir:  String               = ""
  protected var analysis:     AnalysisJson         = _
  protected var stateJson:    StateJson            = _
  protected var trialDir:     String               = ""
  protected var epConfig:     EntrypointConfig     = _

  private val flavor = sys.env.getOrElse("SCOS_FLAVOR", "source")

  private var _cloneSchema:   Option[String]       = None
  private var _tmpDir:        Option[java.io.File] = None
  private var _warehouseDir:  Option[java.io.File] = None
  private var _savedEnv:      Map[String, Option[String]] = Map.empty

  // -------------------------------------------------------------------------
  // Lifecycle
  // -------------------------------------------------------------------------

  override def beforeAll(): Unit = {
    super.beforeAll()
    analysis    = AnalysisJson.load()
    stateJson   = StateJson.load()
    mockDataDir = Helpers.mockDataDirForEp(epId)
    trialDir    = buildTrialDir()
    _setup()
  }

  override def afterAll(): Unit = {
    try { _teardown() }
    finally { super.afterAll() }
  }

  // -------------------------------------------------------------------------
  // Setup
  // -------------------------------------------------------------------------

  private def _setup(): Unit = {
    epConfig = analysis.entrypoints.find(_.id == epId)
      .getOrElse(sys.error(s"ScosTrialFixture: no entrypoint '$epId' found in analysis.json"))

    // Save + set per-trial env vars (mirrors conftest.py trial fixture env setup)
    val envOverrides = Map(
      "SCOS_TRIAL_START_TS"    -> (System.currentTimeMillis() / 1000L).toString,
      "SCOS_RUN_ID"            -> UUID.randomUUID().toString.replace("-", "").take(8),
    )
    _savedEnv = EnvUtil.saveAndSet(envOverrides)

    if (flavor == "migrated") {
      _setupPhaseB(epConfig)
    } else {
      _setupPhaseA(epConfig)
    }

    // Install date pinning (both phases)
    DatePin.install(spark)
  }

  private def _setupPhaseA(epConfig: EntrypointConfig): Unit = {
    val tmpDir = Files.createTempDirectory("scos-trial-").toFile
    _tmpDir = Some(tmpDir)
    val warehouseDir = new java.io.File(tmpDir, "warehouse")
    warehouseDir.mkdirs()
    _warehouseDir = Some(warehouseDir)

    spark = Helpers.buildLocalSession(warehouseDir.getAbsolutePath)
    Helpers.installDeltaPatches(spark)

    val localSchema = s"scos_${safeEpId.take(24)}_${UUID.randomUUID().toString.replace("-", "").take(8)}".toLowerCase
    outputSchema = localSchema
    EnvUtil.setEnv("SCOS_OUTPUT_SCHEMA", localSchema)
    // mirrors conftest.py: Phase A always uses "spark_catalog" as the database name
    // for 3-part FQN namespace rebinds against the local Spark catalog.
    EnvUtil.setEnv("SCOS_DATABASE_NAME", "spark_catalog")
    EnvUtil.setEnv("SCOS_MOCK_DATA_DIR", mockDataDir)

    spark.sql(s"CREATE DATABASE IF NOT EXISTS $localSchema")
    spark.sql(s"USE $localSchema")

    sinkTables = Helpers.declaredSinkTables(epConfig, localSchema)
    seedTables = Helpers.seedEntrypoint(spark, epConfig, mockDataDir, localSchema)
    Helpers.interceptConnectorReads(spark, epConfig, localSchema)
    Helpers.injectIoEnvVars(epConfig, mockDataDir, trialDir)
  }

  private def _setupPhaseB(epConfig: EntrypointConfig): Unit = {
    val cloneSchema = Helpers.cloneGoldenSchemaForTrial(stateJson, epId)
    _cloneSchema = Some(cloneSchema)
    outputSchema = cloneSchema
    EnvUtil.setEnv("SCOS_TRIAL_CLONE_SCHEMA", cloneSchema)
    EnvUtil.setEnv("SCOS_OUTPUT_SCHEMA", cloneSchema)     // mirrors Phase A; workload reads this for namespace-qualified table refs
    // mirrors conftest.py Phase B: signal that we're running in SCOS mode
    EnvUtil.setEnv("SPARK_CONNECT_MODE_ENABLED", "1")
    EnvUtil.setEnv("SCOS_MOCK_DATA_DIR", mockDataDir)

    sinkTables = Helpers.declaredSinkTables(epConfig, cloneSchema)

    // Connection model: SnowparkConnectSession.builder().getOrCreate() launches a local
    // Python SCOS server from SNOWPARK_CONNECT_PYTHON_VENV; that server resolves the
    // Snowflake connection from SNOWFLAKE_DEFAULT_CONNECTION_NAME. Both MUST be real OS
    // environment variables on this JVM process (set by `scos_state.py run-phase-b` in the
    // sbt env and inherited here) — the Python server is a child process and reads the OS
    // env, NOT JVM system properties, so EnvUtil.setEnv cannot supply them. We deliberately
    // do NOT set SPARK_REMOTE: doing so forces remote mode and bypasses the local server.
    // The JVM client does not read connections.toml itself. (Forked JVMs cannot use browser
    // OAuth/SSO — the configured connection must be non-interactive: PAT, key-pair,
    // password, or a cached OAuth token.)
    if (System.getenv("SNOWFLAKE_DEFAULT_CONNECTION_NAME") == null)
      System.err.println(
        "[ScosTrialFixture] WARN: SNOWFLAKE_DEFAULT_CONNECTION_NAME is not set in the OS " +
        "environment. The local SCOS Python server will use the default connection; if Phase B " +
        "fails to authenticate, run via `scos_state.py run-phase-b` (which sets it) or export it.")

    // Initialise SnowparkConnectSession via JVM reflection.
    // The SCOS client JAR must be on the runtime classpath (lib/ or provided).
    // See fix-rules.md Rule 25 for the builder API.
    spark = initScosSession(s"scos-trial-$epId")

    val scosDb = stateJson.snowflake.database
    if (scosDb.nonEmpty) EnvUtil.setEnv("SCOS_DATABASE_NAME", scosDb)

    // Point SCOS session at the trial clone schema via SnowflakeSession.
    // Ditto PySpark scos_runtime.run_trial: USE DATABASE / USE SCHEMA only — no
    // explicit warehouse. The warehouse comes from the configured connection: the
    // local SCOS Python server resolves it from connections.toml, exactly like
    // PySpark's init_spark_session. The connection MUST define a warehouse.
    // This MUST succeed: if it silently failed, Phase B would run against the wrong
    // schema and the A/B comparison would "pass" on bogus data.
    try {
      val sfSession = newSnowflakeSession(spark)
      useScosNamespace(spark, sfSession, scosDb, cloneSchema)
    } catch {
      case e: Throwable =>
        throw new RuntimeException(
          s"ScosTrialFixture: failed to switch SCOS session to $scosDb.$cloneSchema — refusing to " +
          s"run Phase B against an unknown schema: ${e.getMessage}", e)
    }

    // Add import roots so UDF workers can resolve workload modules (mirrors conftest.py).
    val outputRoot = EnvUtil.get("SCOS_OUTPUT_ROOT", "")
    if (outputRoot.nonEmpty) {
      analysis.importRoots.foreach { root =>
        val abs = Paths.get(outputRoot, root).toFile
        if (abs.isDirectory) {
          Try(invokeMethod(spark, "addArtifact", abs.getAbsolutePath))
            .failed.foreach(_ => ()) // best-effort
        }
      }
    }

    seedTables  = Helpers.listSeedTablesViaJdbc(stateJson, cloneSchema)
    Helpers.interceptConnectorReads(spark, epConfig, cloneSchema)
    Helpers.injectIoEnvVars(epConfig, mockDataDir, trialDir)
  }

  // -------------------------------------------------------------------------
  // Teardown
  // -------------------------------------------------------------------------

  private def _teardown(): Unit = {
    _cloneSchema.foreach { schema =>
      Try(Helpers.dropTrialCloneSchema(stateJson, schema))
        .failed.foreach(e => System.err.println(s"warn: teardown: DROP SCHEMA failed: $e"))
    }
    Try { if (spark != null) spark.stop() }
      .failed.foreach(e => System.err.println(s"warn: teardown: spark.stop() failed: $e"))
    _tmpDir.foreach { dir =>
      Try(Helpers.deleteRecursive(dir))
        .failed.foreach(_ => ())
    }
    EnvUtil.restore(_savedEnv)
  }

  // -------------------------------------------------------------------------
  // SCOS session init via reflection
  // -------------------------------------------------------------------------

  /**
   * Initialise a SnowparkConnectSession without a compile-time dependency on
   * the SCOS client JAR.  Equivalent to:
   *   SnowparkConnectSession.builder().appName(appName).getOrCreate()
   */
  private def initScosSession(appName: String): SparkSession = {
    val scosClass   = Class.forName(EnvUtil.scosClientClass)
    val builderMeth = scosClass.getMethod("builder")
    val builder     = builderMeth.invoke(null)
    val withName    = builder.getClass.getMethod("appName", classOf[String]).invoke(builder, appName)
    withName.getClass.getMethod("getOrCreate").invoke(withName).asInstanceOf[SparkSession]
  }

  /**
   * Construct a SnowflakeSession wrapping the SCOS SparkSession.
   * Equivalent to: new SnowflakeSession(spark)
   */
  private def newSnowflakeSession(spark: SparkSession): AnyRef = {
    val sfClass = Class.forName(EnvUtil.scosSessionClass)
    sfClass.getConstructor(classOf[SparkSession]).newInstance(spark).asInstanceOf[AnyRef]
  }

  /** Invoke a single-String-arg method on an object via reflection. */
  private def invokeMethod(obj: AnyRef, method: String, arg: String): Unit = {
    obj.getClass.getMethod(method, classOf[String]).invoke(obj, arg)
    ()
  }

  /**
   * Point the SCOS session at the trial database/schema.
   *
   * Primary path: SnowflakeSession.useDatabase / useSchema via reflection.
   * Fallback: spark.sql USE DATABASE/SCHEMA — used when the SCOS client JAR version
   *   omits useSchema (NoSuchMethodException on older/newer API versions).
   *
   * After the schema switch, verifies via SELECT CURRENT_SCHEMA() that the SCOS
   * session is actually pointing at the expected schema. Throws if verification
   * fails — Phase B must never run against the wrong schema (bogus "passed" risk).
   */
  private def useScosNamespace(
      spark: SparkSession,
      sfSession: AnyRef,
      database: String,
      schema: String,
  ): Unit = {
    if (database.nonEmpty) {
      Try(invokeMethod(sfSession, "useDatabase", database)).recoverWith { case _ =>
        Try(spark.sql(s"USE DATABASE ${Helpers.sqlQuotedIdent(database)}"))
      }.get
    }
    Try(invokeMethod(sfSession, "useSchema", schema)).recoverWith { case _ =>
      Try(spark.sql(s"USE SCHEMA ${Helpers.sqlQuotedIdent(schema)}"))
    }.get

    // Verify the switch actually took effect.  SELECT CURRENT_SCHEMA() routes
    // through the SCOS server to Snowflake and returns the active schema name.
    val current = Try {
      spark.sql("SELECT CURRENT_SCHEMA()").collect().headOption
        .flatMap(r => Option(r.getString(0)))
        .getOrElse("")
    }.getOrElse("")

    if (current.nonEmpty && !current.equalsIgnoreCase(schema))
      throw new RuntimeException(
        s"useScosNamespace: schema switch verification failed — " +
        s"CURRENT_SCHEMA() returned '$current', expected '$schema'. " +
        s"Check that the SCOS client JAR exposes useSchema/useDatabase and that " +
        s"the connection has USE SCHEMA privilege on $schema.")
  }

  // -------------------------------------------------------------------------
  // Helpers for sub-classes
  // -------------------------------------------------------------------------

  private def buildTrialDir(): String = {
    val resultsDir = EnvUtil.get("SCOS_RESULTS_DIR",
      sys.env.getOrElse("SCOS_RESULTS_DIR", s"/tmp/scos_results/$flavor"))
    val dir = new java.io.File(resultsDir, safeEpId)
    dir.mkdirs()
    dir.getAbsolutePath
  }

  // -------------------------------------------------------------------------
  // Runtime execution — mirrors PySpark ValidationRuntime.run_trial
  // -------------------------------------------------------------------------

  /**
   * Workload-agnostic trial body: invoke the workload, capture results, and
   * (Phase B) compare against the Phase A baseline.
   *
   * Mirrors PySpark's runtimes.driver.run_validation_trial / ScosRuntime.run_trial.
   * By delegating here the generated test template is thin — it only declares WHAT to
   * run (constants) and calls runTrial with them, exactly like test_template.py calls
   * run_validation_trial(request, runtime).
   */
  def runTrial(
      jarPath:       String,
      entryClass:    String,
      entryMethod:   String,
      entryArgs:     Array[String],
      trialDir:      String,
      phaseADir:     String,
      widgetEnvVars: Map[String, String] = Map.empty,
  ): Unit = {
    // seedTables may be fully qualified (schema.table) from listSeedTablesViaJdbc;
    // sinkTables are short names from declaredSinkTables. Normalize both to short names
    // before filtering so that output sinks are not accidentally excluded from capture.
    val sinkShortNames = sinkTables.map(_.split("\\.").last.toLowerCase).toSet
    val excludedTables = seedTables.filterNot(t => sinkShortNames.contains(t.split("\\.").last.toLowerCase))

    val ep = ReflectionEntrypoint.load(
      jarPath    = jarPath,
      className  = entryClass,
      methodName = entryMethod,
    )

    // Register the workload JAR with SparkContext so the executor can resolve
    // workload lambda classes during task deserialization (fixes SerializedLambda
    // ClassCastException when the workload uses rdd.map / other RDD closures).
    if (flavor != "migrated") {
      // Access via reflection: SCOS SparkSession (spark-connect) does not expose sparkContext
      // as a typed member, so direct access fails to compile even though this branch is
      // dead in Phase B (flavor == "migrated"). Reflection keeps the Phase A behaviour intact.
      Try {
        val sc = spark.getClass.getMethod("sparkContext").invoke(spark)
        sc.getClass.getMethod("addJar", classOf[String]).invoke(sc, jarPath)
      }.failed.foreach(e => System.err.println(s"warn: addJar($jarPath): $e"))
    }

    val savedWidgets = EnvUtil.saveAndSet(widgetEnvVars)
    var workloadError: Option[Throwable] = None
    try {
      if (entryMethod == "main") {
        ep.invokeMain(entryArgs)
      } else {
        // Introspect the method's first parameter type to decide how to invoke:
        //   Array[String] first param → pass entryArgs (Job.run(args: Array[String]))
        //   SparkSession  first param → pass spark     (DataTransform.run(spark, args))
        //   No params                → call with no args
        val paramTypes = ep.method.getParameterTypes
        if (paramTypes.isEmpty) {
          ep.invoke()
        } else if (paramTypes(0).isAssignableFrom(classOf[Array[String]])) {
          ep.invoke(entryArgs.asInstanceOf[AnyRef])
        } else if (paramTypes(0).getName.contains("SparkSession")) {
          ep.invoke(spark)
        } else {
          // Fallback: try with args, then spark, then no args
          try { ep.invoke(entryArgs.asInstanceOf[AnyRef]) }
          catch { case _: IllegalArgumentException =>
            try { ep.invoke(spark) }
            catch { case _: IllegalArgumentException => ep.invoke() }
          }
        }
      }
    } catch {
      case e: Throwable => workloadError = Some(e)
    } finally {
      EnvUtil.restore(savedWidgets)
      Try(ep.close())
    }

    // Workloads that call spark.stop() in their finally block shut down the
    // shared SparkSession that captureResults needs. Rebuild from the same
    // warehouse dir so the persisted Hive metastore tables are still visible.
    if (flavor != "migrated" && Try {
      // Reflective sparkContext.isStopped — SCOS SparkSession has no typed sparkContext member
      val sc = spark.getClass.getMethod("sparkContext").invoke(spark)
      sc.getClass.getMethod("isStopped").invoke(sc).asInstanceOf[Boolean]
    }.getOrElse(false)) {
      _warehouseDir.foreach { warehouseDir =>
        println(s"[ScosTrialFixture] workload stopped SparkSession; rebuilding for captureResults")
        spark = Helpers.buildLocalSession(warehouseDir.getAbsolutePath)
        Helpers.installDeltaPatches(spark)
      }
    }

    new File(trialDir).mkdirs()

    val manifest = Try {
      Helpers.captureResults(
        spark          = spark,
        outputSchema   = outputSchema,
        outputDir      = trialDir,
        exclude        = excludedTables,
        excludeIfEmpty = Helpers.declaredAllowEmptySinkTables(epConfig, outputSchema),
      )
    } match {
      case Success(m) => Some(m)
      case Failure(e) =>
        System.err.println(s"warn: captureResults failed: $e")
        Try(Files.write(new File(trialDir, "capture_error.txt").toPath, e.toString.getBytes("UTF-8")))
        None
    }

    workloadError.foreach { e =>
      Try(Files.write(new File(trialDir, "workload_error.txt").toPath, e.toString.getBytes("UTF-8")))
      throw e
    }

    // Validate that every non-allow_empty declared sink actually captured rows.
    // Mirrors PySpark _executor.py validate_declared_sink_outputs injection.
    val sinkFailures = manifest.map(m => Helpers.validateDeclaredSinkOutputs(epConfig, m)).getOrElse(Nil)
    val criticalMsgs = sinkFailures.collect {
      case f: Map[_, _]
          if f.asInstanceOf[Map[String, Any]].get("critical").contains(true) =>
        Seq(
          f.asInstanceOf[Map[String, Any]].get("message"),
          f.asInstanceOf[Map[String, Any]].get("reason"),
        ).flatten.map(_.toString.trim).find(_.nonEmpty).getOrElse("")
    }.filter(_.nonEmpty)
    if (criticalMsgs.nonEmpty)
      fail(criticalMsgs.mkString("\n"))

    val tables = manifest.flatMap(_.get("tables")).collect { case ts: List[_] => ts }.getOrElse(Nil)
    val manifestFailures = manifest.flatMap(_.get("failures")).getOrElse(Nil)
    if (Helpers.requiresNonemptySinkCapture(epConfig))
      assert(tables.nonEmpty,
        s"No outputs produced for trial $epId (manifest failures: $manifestFailures)")
    val failures = manifest.flatMap(_.get("failures")).collect { case fs: List[_] => fs }.getOrElse(Nil)
    assert(failures.isEmpty, s"Snapshot capture failed for trial $epId: $failures")

    if (flavor == "migrated") {
      if (!new File(phaseADir, "tables").isDirectory)
        _writeManualReview(trialDir, phaseADir, tables)
      else
        _comparePhases(phaseADir, trialDir)
    }
  }

  private def _writeManualReview(trialDir: String, phaseADir: String, tables: List[_]): Unit = {
    import com.fasterxml.jackson.databind.ObjectMapper
    import com.fasterxml.jackson.module.scala.DefaultScalaModule
    val mapper = new ObjectMapper(); mapper.registerModule(DefaultScalaModule)
    val marker = Map(
      "trial_id"        -> epId,
      "reason"          -> "no_phase_a_baseline",
      "phase_a_dir"     -> phaseADir,
      "phase_b_dir"     -> trialDir,
      "captured_tables" -> tables.map {
        case m: Map[_, _] => m.asInstanceOf[Map[String, Any]].getOrElse("name", "").toString
        case other        => other.toString
      },
    )
    Files.write(
      new File(trialDir, "_manual_review.json").toPath,
      mapper.writerWithDefaultPrettyPrinter().writeValueAsBytes(marker),
    )
  }

  private def _comparePhases(phaseADir: String, phaseBDir: String): Unit = {
    import com.fasterxml.jackson.databind.ObjectMapper
    import com.fasterxml.jackson.module.scala.DefaultScalaModule
    val mapper = new ObjectMapper(); mapper.registerModule(DefaultScalaModule)

    val aTablesDir = new File(phaseADir, "tables")
    val bTablesDir = new File(phaseBDir, "tables")
    if (!aTablesDir.isDirectory) return
    if (!bTablesDir.isDirectory) fail(s"Phase B tables dir missing: $bTablesDir")

    def tableNamesForPhase(phaseDir: String, tablesDir: File): Set[String] = {
      val indexPath = new File(phaseDir, "_index.json")
      if (indexPath.isFile) {
        Try {
          val idx = mapper.readValue(indexPath, classOf[Map[String, Any]])
          idx.getOrElse("tables", Nil).asInstanceOf[List[Map[String, Any]]]
            .flatMap(m => m.get("name").map(_.toString))
            .toSet[String]
        }.getOrElse(Set.empty[String])
      } else {
        Option(tablesDir.listFiles(_.getName.endsWith(".parquet")))
          .map(_.map(_.getName.stripSuffix(".parquet")).toSet)
          .getOrElse(Set.empty[String])
      }
    }

    val aNames = tableNamesForPhase(phaseADir, aTablesDir)
    val bNames = tableNamesForPhase(phaseBDir, bTablesDir)
    val mismatches = scala.collection.mutable.ListBuffer[String]()

    for (name <- (aNames ++ bNames).toSeq.sorted) {
      (aNames.contains(name), bNames.contains(name)) match {
        case (true, false) => mismatches += s"$name: present in Phase A but missing in Phase B"
        case (false, true) => mismatches += s"$name: present in Phase B but missing in Phase A"
        case _             => ()
      }
    }

    if (mismatches.nonEmpty)
      fail(s"Baseline structural mismatch — ${mismatches.size} table(s) diverge " +
           s"(row-level diff deferred to comparator.py):\n" +
           mismatches.map(m => s"  - $m").mkString("\n"))
  }
}

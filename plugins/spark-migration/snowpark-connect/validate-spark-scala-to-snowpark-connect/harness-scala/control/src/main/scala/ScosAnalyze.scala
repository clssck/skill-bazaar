// com.snowflake.scos.validate.ScosAnalyze
//
// Deterministic Scala source analysis for the validator's data-synthesizer agent.
//
// The data-synthesizer agent reasons about *semantics* (which sources matter, what the
// schemas are). This command gives it deterministic *facts* extracted from the
// AST via Scalameta, so the agent does not have to act as a Scala parser:
//   - entrypoints   (objects/classes that declare a `main`/`run` method)
//   - imports
//   - reads         (spark.read....{parquet,csv,json,orc,text,load,table,jdbc};
//                    SparkContext RDD reads sc.{textFile,wholeTextFiles,binaryFiles,
//                    binaryRecords,sequenceFile,objectFile};
//                    DeltaTable.forPath/forName; spark.catalog reads)
//   - writes        (....write....{parquet,csv,...,save}, saveAsTable, insertInto;
//                    spark.catalog.createTable/createExternalTable)
//   - table_refs    (spark.table / saveAsTable / insertInto targets)
//   - column_refs   (col("x") / column("x") / $"x", plus string args of
//                    select / groupBy / orderBy / sort / sortBy / drop /
//                    dropDuplicates)
//   - unresolved_reads / unresolved_writes — call sites whose path/table arg
//                    could not be statically resolved (dynamic paths are
//                    recorded rather than dropped, so the data-synthesizer can
//                    still declare a source with an llm_todo).
//
// Argument resolution (parity with PySpark assessment data_edge_ast.py):
//   B1  Lit.String literal             → verbatim
//   B2  s"..." interpolation           → resolve each ${} arg; join
//   B3  .format(arg)                   → substitute %s / {} in receiver
//   B4  .replace(old,new)              → perform replacement
//   B5  Seq(...).mkString(sep)         → join resolved parts
//   B6  "a" + "b" binary concat        → concatenate resolved sides
//   B7  Map("k"->"v")("k")             → resolve value for literal key
//   B8  Map(...)( varKey )             → trace varKey → literal then B7
//   B9  Term.Name → val/var binding    → recurse on RHS
//   B10 for-loop target enumeration    → first element of literal iterable
//   B11 if (c) a else b ternary        → enumerate BOTH branches
//   B12 .trim/.toLowerCase/etc.        → recurse receiver (trivial pass)
//   B13 sys.env.getOrElse("V","d")     → use default arg
//   B14 Paths.get("a"[,"b"])           → join args
//   B16 f() single-return def inline   → recurse body
//
// Usage:
//   java -jar scos-analyze.jar analyze --source <file-or-dir> [--output <path>]
//                                       [--config-pool-file <flat-json-map>]
//
// --config-pool-file  Optional flat JSON ``{"VAR_NAME": "value", …}`` produced
//                     by the Python-side ``_load_config_pool`` in
//                     scan_codebase.py. Variable names unresolvable via Scala
//                     val/def bindings are looked up here as a final fallback
//                     (PR #3548 parity with PySpark config-pool threading).
//
// Output: JSON to stdout (or --output file). Exit 0 always; per-file `parse_ok`
// flags surface parse failures without aborting the whole run.

package com.snowflake.scos.validate

import io.circe.Json            // type alias (term `Json` is the local helper object)
import io.circe.{Json => CJson} // circe builder object, used for CJson.obj(...)
import io.circe.parser.{parse => circeParseJson}
import io.circe.syntax._

import java.nio.file.{Files, Path, Paths}
import scala.meta._
import scala.meta.parsers.Parsed

object ScosAnalyze {

  // ── read/write terminal method-name sets ────────────────────────────────────

  private val readTerminals  = Set("parquet", "csv", "json", "orc", "text", "textFile", "load", "table", "jdbc")
  private val fmtTerminals   = Set("parquet", "csv", "json", "orc", "text")
  // SparkContext RDD read methods. Parity with PySpark data_edge_ast._SC_READ_METHODS.
  private val scReadMethods  = Set(
    "textFile", "wholeTextFiles", "binaryFiles", "binaryRecords", "sequenceFile", "objectFile")

  // ── resolver constants ───────────────────────────────────────────────────────

  private val DEPTH_CAP = 6   // max recursion depth in resolveSignatures

  // B12: trivial string-method passthrough (resolver recurses the receiver)
  private val TRIVIAL_PASS = Set(
    "trim", "strip", "stripLeading", "stripTrailing",
    "toLowerCase", "toUpperCase",
    "stripPrefix", "stripSuffix", "stripMargin",
    "intern"
  )

  // ── per-file resolver context builders ──────────────────────────────────────

  /** B9: val/var name → RHS term (first binding wins). */
  private def buildValBindings(tree: Tree): Map[String, Term] = {
    val m = scala.collection.mutable.Map[String, Term]()
    tree.traverse {
      case d: Defn.Val if d.pats.size == 1 =>
        d.pats.head match {
          case Pat.Var(n) => m.getOrElseUpdate(n.value, d.rhs)
          case _          => ()
        }
      case d: Defn.Var if d.pats.size == 1 =>
        d.pats.head match {
          case Pat.Var(n) => d.rhs.foreach(rhs => m.getOrElseUpdate(n.value, rhs))
          case _          => ()
        }
    }
    m.toMap
  }

  /** B16: function name → single-expression return body. */
  private def buildDefReturns(tree: Tree): Map[String, Term] = {
    val m = scala.collection.mutable.Map[String, Term]()
    tree.traverse {
      case d: Defn.Def =>
        val bodyOpt: Option[Term] = d.body match {
          case Term.Block(List(s: Term)) => Some(s)  // { expr }
          case _: Term.Block             => None      // multi-statement block
          case t                         => Some(t)   // direct expression body
        }
        bodyOpt.foreach(t => m.getOrElseUpdate(d.name.value, t))
    }
    m.toMap
  }

  /** B10: for-loop enumerator → list of iterable elements. */
  private def buildForTargets(tree: Tree): Map[String, List[Term]] = {
    val m = scala.collection.mutable.Map[String, List[Term]]()
    def registerEnum(enums: List[Enumerator]): Unit =
      enums.foreach {
        case Enumerator.Generator(Pat.Var(n), rhs) =>
          val elems = rhs match {
            case Term.Apply(Term.Name("List" | "Seq" | "Vector" | "Set"), args) => args
            case _ => Nil
          }
          if (elems.nonEmpty) m.getOrElseUpdate(n.value, elems)
        case _ => ()
      }
    tree.traverse {
      case Term.For(enums, _)      => registerEnum(enums)
      case Term.ForYield(enums, _) => registerEnum(enums)
    }
    m.toMap
  }

  /**
   * PR #3548 parity — call-site argument expansion.
   *
   * Maps each def's parameter names to the literal (Lit.String) argument
   * values seen at call sites in the same file.  Merged into ``vals`` so
   * that a parameter like ``tableName`` resolves when the def body uses it
   * as a data-edge path argument.
   *
   * Covers the most common 1-hop pattern:
   *   {{{
   *     def load(tableName: String) = spark.read.table(tableName)
   *     load("DB.SCH.ORDERS")   // tableName → "DB.SCH.ORDERS"
   *   }}}
   */
  private def buildParamBindings(tree: Tree): Map[String, Term] = {
    // Step 1: map funcName → ordered list of param names
    val funcParams = scala.collection.mutable.Map[String, List[String]]()
    tree.traverse {
      case d: Defn.Def if d.paramss.nonEmpty =>
        val params = d.paramss.flatten.map(_.name.value)
        if (params.nonEmpty) funcParams(d.name.value) = params
    }
    if (funcParams.isEmpty) return Map.empty

    // Step 2: at every call site Term.Apply(Term.Name(fn), args), bind
    // params to call-site literal args (first literal seen wins).
    val bindings = scala.collection.mutable.Map[String, Term]()
    tree.traverse {
      case ta: Term.Apply =>
        val (fn, callArgs) = ta.fun match {
          case Term.ApplyType(Term.Name(n), _) => (Some(n), ta.argClause.values)
          case Term.Name(n)                    => (Some(n), ta.argClause.values)
          case _                               => (None, Nil)
        }
        fn.foreach { name =>
          funcParams.get(name).foreach { params =>
            params.zip(callArgs).foreach { case (paramName, argNode) =>
              // Only bind if we don't already have a binding for this param
              if (!bindings.contains(paramName)) {
                argNode match {
                  case _: Lit.String => bindings(paramName) = argNode
                  case _             => () // non-literal; leave for resolver
                }
              }
            }
          }
        }
    }
    bindings.toMap
  }

  // ── argument resolver (B1–B16 + config pool) ─────────────────────────────

  /**
   * Recursively resolve a Term to a list of concrete string signatures.
   * Empty list → could not resolve (caller emits an UnresolvedEdge).
   * Multiple elements → enumerated branches (ternary / for-loop).
   */
  private def resolveSignatures(
    node: Term,
    depth: Int,
    vals: Map[String, Term],
    defs: Map[String, Term],
    fors: Map[String, List[Term]],
    configPool: Map[String, String] = Map.empty
  ): List[String] = {
    if (depth >= DEPTH_CAP) return Nil
    val d1 = depth + 1

    node match {

      // B1: string literal
      case Lit.String(s) => List(s)

      // B6: binary + concatenation
      case Term.ApplyInfix(l, Term.Name("+"), _, List(r)) =>
        val ls = resolveSignatures(l, d1, vals, defs, fors)
        val rs = resolveSignatures(r, d1, vals, defs, fors)
        if (ls.isEmpty || rs.isEmpty) Nil
        else for (lv <- ls; rv <- rs) yield lv + rv

      // B11: ternary if/else — enumerate BOTH branches
      case ti: Term.If =>
        resolveSignatures(ti.thenp, d1, vals, defs, fors) ++
        resolveSignatures(ti.elsep, d1, vals, defs, fors)

      // B2: string interpolation s"..." — use instance guard to match regardless
      // of whether prefix is Term.Name or Name.Indeterminate in this Scalameta build.
      case ti: Term.Interpolate if ti.prefix.value == "s" =>
        val iparts = ti.parts
        val iargs  = ti.args
        // parts.length == iargs.length + 1; interleave
        val resolvedArgs: List[Option[String]] = iargs.map { a =>
          resolveSignatures(a, d1, vals, defs, fors) match {
            case h :: _ => Some(h) // take first if multiple branches
            case Nil    => None
          }
        }
        if (resolvedArgs.exists(_.isEmpty)) Nil
        else {
          val sb = new StringBuilder
          iparts.zipWithIndex.foreach { case (Lit.String(p), i) =>
            sb.append(p)
            if (i < iargs.size) sb.append(resolvedArgs(i).getOrElse(""))
            case _ => ()
          }
          List(sb.toString)
        }

      // B12: trivial string-method passthrough — bare accessor form (no parens)
      // e.g. "str".trim, myStr.toLowerCase  → recurse receiver
      case Term.Select(recv, Term.Name(m)) if TRIVIAL_PASS(m) =>
        resolveSignatures(recv, d1, vals, defs, fors)

      // B9/B16: name → val binding OR single-return def inlining
      // Config-pool fallback (PR #3548 parity): if the name is unresolvable
      // via val/def/for bindings, check the config pool — useful for env-style
      // variables like DATABASE_NAME or TABLE_PREFIX that are set in
      // application.json/yaml rather than as Scala literals.
      case Term.Name(x) =>
        fors.get(x) match {
          case Some(elems) =>
            // B10: loop target → first element
            elems.headOption.fold(Nil: List[String])(
              e => resolveSignatures(e, d1, vals, defs, fors, configPool))
          case None =>
            val fromBindings: List[String] =
              vals.get(x).fold(
                // B16: no-paren def reference (def f = expr, called as f not f())
                defs.get(x).fold(Nil: List[String])(
                  body => resolveSignatures(body, d1, vals, defs, fors, configPool))
              )(rhs => resolveSignatures(rhs, d1, vals, defs, fors, configPool))
            if (fromBindings.nonEmpty) fromBindings
            else {
              // Config-pool fallback: resolve bare variable names whose values
              // come from JSON/YAML config files in the workload directory.
              configPool.get(x).fold(Nil: List[String])(v => List(v))
            }
        }

      case ta: Term.Apply =>
        // Unwrap type application (e.g. f[T](arg))
        val (func, applyArgs) = ta.fun match {
          case Term.ApplyType(inner, _) => (inner, ta.argClause.values)
          case other                    => (other, ta.argClause.values)
        }
        func match {

          // B12: trivial passthrough methods (.trim, .toLowerCase, etc.)
          case Term.Select(recv, Term.Name(m)) if TRIVIAL_PASS(m) && applyArgs.isEmpty =>
            resolveSignatures(recv, d1, vals, defs, fors)

          // B4: .replace(old, new)
          case Term.Select(recv, Term.Name("replace")) if applyArgs.size == 2 =>
            val rs = resolveSignatures(recv, d1, vals, defs, fors)
            val os = resolveSignatures(applyArgs(0), d1, vals, defs, fors)
            val ns = resolveSignatures(applyArgs(1), d1, vals, defs, fors)
            if (rs.isEmpty || os.isEmpty || ns.isEmpty) Nil
            else rs.flatMap(r => os.flatMap(o => ns.map(n => r.replace(o, n))))

          // B3: .format(arg) — substitute first %s/{} in receiver
          case Term.Select(recv, Term.Name("format")) if applyArgs.nonEmpty =>
            val rs = resolveSignatures(recv, d1, vals, defs, fors)
            val as = resolveSignatures(applyArgs.head, d1, vals, defs, fors)
            if (rs.isEmpty || as.isEmpty) Nil
            else rs.flatMap(r => as.map(a => r.replace("%s", a).replace("{}", a)))

          // B5: Seq/List(...).mkString(sep)
          case Term.Select(
                Term.Apply(Term.Name("List" | "Seq" | "Vector"), elems),
                Term.Name("mkString")
              ) if applyArgs.size == 1 =>
            val seps = resolveSignatures(applyArgs.head, d1, vals, defs, fors)
            if (seps.isEmpty) Nil
            else {
              val elemStrs = elems.map(e => resolveSignatures(e, d1, vals, defs, fors))
              if (elemStrs.exists(_.isEmpty)) Nil
              else List(elemStrs.map(_.head).mkString(seps.head))
            }

          // B13: sys.env.getOrElse("V", default) — use default
          case Term.Select(
                Term.Select(Term.Name("sys"), Term.Name("env")),
                Term.Name("getOrElse")
              ) if applyArgs.size >= 2 =>
            resolveSignatures(applyArgs(1), d1, vals, defs, fors)

          // B13: sys.env.get("V").getOrElse(default)
          case Term.Select(_, Term.Name("getOrElse")) if applyArgs.size >= 2 =>
            resolveSignatures(applyArgs(1), d1, vals, defs, fors)

          // B13: System.getProperty("k", "default") — use default (2nd arg)
          case Term.Select(Term.Name("System"), Term.Name("getProperty"))
              if applyArgs.size >= 2 =>
            resolveSignatures(applyArgs(1), d1, vals, defs, fors)

          // B14: Paths.get("a"[,"b",...]) — join all args
          case Term.Select(Term.Name("Paths"), Term.Name("get")) if applyArgs.nonEmpty =>
            val parts = applyArgs.map(a => resolveSignatures(a, d1, vals, defs, fors))
            if (parts.exists(_.isEmpty)) Nil
            else List(parts.map(_.head).mkString("/"))

          // B14: new File("a") or new File(parent, child)
          case Term.Name("File") | Term.Select(_, Term.Name("File"))
              if applyArgs.nonEmpty =>
            val parts = applyArgs.map(a => resolveSignatures(a, d1, vals, defs, fors))
            if (parts.exists(_.isEmpty)) Nil
            else List(parts.map(_.head).mkString("/"))

          // B7/B8 Map lookup + B16 function inlining — function-call forms
          case Term.Name(fn) if applyArgs.size == 1 =>
            // B7/B8: check if fn binds to a Map literal
            val keyRes = resolveSignatures(applyArgs.head, d1, vals, defs, fors)
            val mapResult: List[String] = if (keyRes.nonEmpty) {
              vals.get(fn).toList.flatMap {
                case Term.Apply(Term.Name("Map"), entries) =>
                  val mapM: Map[String, Term] = entries.collect {
                    case Term.ApplyInfix(Lit.String(k), Term.Name("->"), _, List(v)) => k -> v
                  }.toMap
                  keyRes.flatMap(k => mapM.get(k).toList.flatMap(v =>
                    resolveSignatures(v, d1, vals, defs, fors)))
                case _ => Nil
              }
            } else Nil
            if (mapResult.nonEmpty) mapResult
            else {
              // B16: single-return function inlining
              defs.get(fn).fold(Nil: List[String])(body =>
                resolveSignatures(body, d1, vals, defs, fors))
            }

          // B16: zero-arg function inlining  f()
          case Term.Name(fn) if applyArgs.isEmpty =>
            defs.get(fn).fold(Nil: List[String])(body =>
              resolveSignatures(body, d1, vals, defs, fors))

          case _ => Nil
        }

      case _ => Nil
    }
  }

  /** Short description of a Term node for UnresolvedEdge diagnostics. */
  private def describeNode(t: Term): String = t match {
    case Term.Name(n)                                => s"variable '${n}'"
    case Term.Select(_, Term.Name(n))                => s"attribute '.${n}'"
    case Term.Apply(Term.Name(fn), _)                => s"call '${fn}(...)'"
    case Term.Apply(Term.Select(_, Term.Name(m)), _) => s"method '.${m}(...)'"
    case _: Term.If                                  => "conditional (if/else)"
    case _: Term.Interpolate                         => "string interpolation"
    case Term.ApplyInfix(_, Term.Name(op), _, _)     => s"operator '${op}'"
    case _                                           => t.productPrefix
  }

  // ── JSON helpers ─────────────────────────────────────────────────────────────

  private def callJson(call: String, args: List[String], line: Int): Json =
    CJson.obj("call" -> call.asJson, "args" -> args.asJson, "line" -> line.asJson)

  private def unresolvedJson(kind: String, call: String, argExpr: String, line: Int): Json =
    CJson.obj(
      "kind"     -> kind.asJson,
      "call"     -> call.asJson,
      "arg_expr" -> argExpr.asJson,
      "line"     -> line.asJson,
    )

  // ── config pool loader (PR #3548 parity) ─────────────────────────────────

  /**
   * Load a flat JSON map from a file for config-pool resolution.
   *
   * The file must be a JSON object ``{"VAR_NAME": "value", …}`` produced by
   * the Python-side ``_load_config_pool`` in scan_codebase.py. Pass the path
   * via the ``--config-pool-file`` CLI flag; if the flag is absent or the
   * file is unreadable/unparseable, resolution degrades gracefully to the
   * existing val/def/for bindings.
   */
  private def loadConfigPool(path: String): Map[String, String] = {
    val text = try {
      new String(Files.readAllBytes(Paths.get(path)), "UTF-8")
    } catch {
      case _: Exception =>
        System.err.println(s"[scos-analyze] WARNING: could not read config pool file: $path")
        return Map.empty
    }
    circeParseJson(text) match {
      case Right(json) =>
        json.asObject.fold(Map.empty[String, String]) { obj =>
          obj.toMap.collect {
            case (k, v) if v.isString => k -> v.asString.getOrElse("")
          }
        }
      case Left(err) =>
        System.err.println(s"[scos-analyze] WARNING: could not parse config pool JSON: $err")
        Map.empty
    }
  }

  // ── entry point ──────────────────────────────────────────────────────────────

  def main(args: Array[String]): Unit = {
    var source         = ""
    var output         = ""
    var configPoolFile = ""
    args.sliding(2, 2).foreach {
      case Array("--source",          v) => source         = v
      case Array("--output",          v) => output         = v
      case Array("--config-pool-file",v) => configPoolFile = v
      case _                             => ()
    }
    if (source.isEmpty) Json.die(2, "analyze: --source <file-or-dir> is required")

    val configPool = if (configPoolFile.nonEmpty) loadConfigPool(configPoolFile)
                     else Map.empty[String, String]

    val root  = Paths.get(source).toAbsolutePath.normalize()
    val files = collectScalaFiles(root)
    val fileResults = files.map(analyzeFile(_, configPool))

    val out = CJson.obj(
      "source"     -> source.asJson,
      "file_count" -> files.size.asJson,
      "parse_errors" -> fileResults.count(j => !j.hcursor.get[Boolean]("parse_ok").getOrElse(true)).asJson,
      "files"      -> fileResults.asJson,
    )

    val rendered = out.spaces2
    if (output.nonEmpty) {
      val outPath = Paths.get(output).toAbsolutePath
      Option(outPath.getParent).foreach(Files.createDirectories(_))
      Files.write(outPath, (rendered + "\n").getBytes("UTF-8"))
      System.err.println(s"[scos-analyze] wrote $outPath (${files.size} file(s))")
    } else {
      println(rendered)
    }
  }

  private def collectScalaFiles(root: Path): List[Path] = {
    if (Files.isRegularFile(root)) {
      if (root.toString.endsWith(".scala")) List(root) else Nil
    } else if (Files.isDirectory(root)) {
      import scala.collection.JavaConverters._
      val stream = Files.walk(root)
      try {
        stream.iterator().asScala
          .filter(p => Files.isRegularFile(p) && p.toString.endsWith(".scala"))
          .toList.sortBy(_.toString)
      } finally stream.close()
    } else Nil
  }

  // ── per-file analysis ────────────────────────────────────────────────────────

  private def analyzeFile(p: Path, configPool: Map[String, String] = Map.empty): Json = {
    val code = try {
      new String(Files.readAllBytes(p), "UTF-8")
    } catch {
      case e: java.io.IOException =>
        return CJson.obj(
          "path"     -> p.toString.asJson,
          "parse_ok" -> false.asJson,
          "error"    -> s"read error: ${e.getMessage}".asJson,
        )
    }
    val input = Input.VirtualFile(p.toString, code)
    implicit val dialect: Dialect = dialects.Scala213

    input.parse[Source] match {
      case Parsed.Error(pos, msg, _) =>
        CJson.obj(
          "path"     -> p.toString.asJson,
          "parse_ok" -> false.asJson,
          "error"    -> s"$msg (line ${pos.startLine + 1})".asJson,
        )

      case Parsed.Success(tree) =>
        // ── resolver context (single pass each) ──────────────────────────────
        val baseVals    = buildValBindings(tree)
        val paramBinds  = buildParamBindings(tree)  // PR #3548: call-site arg expansion
        // Local vals take precedence over call-site parameter bindings
        val vals = baseVals ++ paramBinds.filter { case (k, _) => !baseVals.contains(k) }
        val defs = buildDefReturns(tree)
        val fors = buildForTargets(tree)

        // ── structural facts ──────────────────────────────────────────────────
        val imports = tree.collect { case i: Importer => i.syntax }.distinct.sorted
        val objects = tree.collect { case o: Defn.Object => o.name.value }.distinct.sorted
        val classes = tree.collect { case c: Defn.Class => c.name.value }.distinct.sorted
        val entrypoints = tree.collect {
          case o: Defn.Object => entrypointMethods(o.name.value, o.templ)
          case c: Defn.Class  => entrypointMethods(c.name.value, c.templ)
        }.flatten

        // ── mutable accumulators ──────────────────────────────────────────────
        val reads          = scala.collection.mutable.ListBuffer[Json]()
        val writes         = scala.collection.mutable.ListBuffer[Json]()
        val unresolvedRds  = scala.collection.mutable.ListBuffer[Json]()
        val unresolvedWrs  = scala.collection.mutable.ListBuffer[Json]()
        val tableRefs      = scala.collection.mutable.LinkedHashSet[String]()
        val colRefs        = scala.collection.mutable.LinkedHashSet[String]()
        var sparkSessionCreated = false

        // ── emit helpers (resolve → edge, or unresolved edge) ────────────────
        // All helpers pass configPool to resolveSignatures so config-file
        // variable names can be resolved as a final fallback (PR #3548 parity).
        def emitRead(call: String, argTerm: Term, line: Int): Unit = {
          val resolved = resolveSignatures(argTerm, 0, vals, defs, fors, configPool)
          if (resolved.nonEmpty)
            reads += callJson(call, resolved, line)
          else
            unresolvedRds += unresolvedJson("read", call,
              argTerm.syntax.take(200), line)
        }

        def emitWrite(call: String, argTerm: Term, line: Int): Unit = {
          val resolved = resolveSignatures(argTerm, 0, vals, defs, fors, configPool)
          if (resolved.nonEmpty)
            writes += callJson(call, resolved, line)
          else
            unresolvedWrs += unresolvedJson("write", call,
              argTerm.syntax.take(200), line)
        }

        def emitTableRead(call: String, argTerm: Term, line: Int): Unit = {
          val resolved = resolveSignatures(argTerm, 0, vals, defs, fors, configPool)
          if (resolved.nonEmpty) {
            reads += callJson(call, resolved, line)
            tableRefs ++= resolved
          } else {
            unresolvedRds += unresolvedJson("read", call,
              argTerm.syntax.take(200), line)
          }
        }

        def emitTableWrite(call: String, argTerm: Term, line: Int): Unit = {
          val resolved = resolveSignatures(argTerm, 0, vals, defs, fors, configPool)
          if (resolved.nonEmpty) {
            writes += callJson(call, resolved, line)
            tableRefs ++= resolved
          } else {
            unresolvedWrs += unresolvedJson("write", call,
              argTerm.syntax.take(200), line)
          }
        }

        // Column-ref methods (string args are column names, not paths)
        val colMethods = Set(
          "select", "groupBy", "orderBy", "sort", "sortBy", "drop", "dropDuplicates",
        )

        // ── main traversal ────────────────────────────────────────────────────
        tree.traverse {
          case ta: Term.Apply =>
            val allArgs = ta.argClause.values
            val strArgs = allArgs.collect { case Lit.String(s) => s }
            val line    = ta.pos.startLine + 1

            // Unwrap type-parameterized calls: sc.objectFile[T](path)
            val fun = ta.fun match {
              case Term.ApplyType(inner, _) => inner
              case other                    => other
            }
            fun match {
              case Term.Select(qual, Term.Name(m)) =>
                val recv = qual.collect { case Term.Name(n) => n }.toSet

                if (m == "getOrCreate" && recv.contains("SparkSession"))
                  sparkSessionCreated = true

                // ── writes ───────────────────────────────────────────────────
                if (m == "saveAsTable" || m == "insertInto") {
                  if (allArgs.nonEmpty) emitTableWrite(m, allArgs.head, line)
                } else if (m == "save" || (recv.contains("write") && fmtTerminals.contains(m))) {
                  if (allArgs.nonEmpty) emitWrite(m, allArgs.head, line)
                  else writes += callJson(m, Nil, line) // bare .save() with no path

                // A1.6: spark.catalog.createTable / createExternalTable
                } else if ((m == "createTable" || m == "createExternalTable") &&
                           recv.contains("catalog")) {
                  if (allArgs.nonEmpty) emitTableWrite(m, allArgs.head, line)

                // ── reads ────────────────────────────────────────────────────
                } else if (m == "table") {
                  // spark.table("name") — table is always a direct read + tableRef
                  if (allArgs.nonEmpty) emitTableRead(m, allArgs.head, line)

                // A1.3: DeltaTable.forPath(spark, path) / forName(spark, name)
                //        SECOND arg is the path/name
                } else if ((m == "forPath" || m == "forName") &&
                           recv.contains("DeltaTable")) {
                  if (allArgs.size >= 2) emitRead(s"DeltaTable.$m", allArgs(1), line)
                  else if (allArgs.size == 1) emitRead(s"DeltaTable.$m", allArgs.head, line)

                // A1.5: spark.read.jdbc(url, table, ...) — SECOND arg is table
                } else if (m == "jdbc" && recv.contains("read")) {
                  if (allArgs.size >= 2)      emitRead("jdbc", allArgs(1), line)
                  else if (allArgs.size == 1) emitRead("jdbc", allArgs.head, line)

                // spark.read.{parquet,csv,...}(path)
                } else if (recv.contains("read") && readTerminals.contains(m)) {
                  if (allArgs.nonEmpty) emitRead(m, allArgs.head, line)

                // A1.2: sc.textFile / wholeTextFiles / binaryFiles / etc.
                } else if (scReadMethods.contains(m) &&
                           (recv.contains("sc") || recv.contains("sparkContext"))) {
                  if (allArgs.nonEmpty) emitRead(m, allArgs.head, line)

                // column refs
                } else if (colMethods.contains(m)) {
                  colRefs ++= strArgs
                }

              case Term.Name(fn) if fn == "col" || fn == "column" =>
                colRefs ++= strArgs

              case _ => ()
            }

          case ti: Term.Interpolate if ti.prefix.value == "$" =>
            colRefs ++= ti.parts.collect { case Lit.String(s) => s }
        }

        // ── write-helper function detection (transitive) ─────────────────────
        def bodyWrites(body: Tree): Boolean = body.collect {
          case Term.Apply(Term.Select(qual, Term.Name(m)), _) =>
            val recv = qual.collect { case Term.Name(n) => n }.toSet
            m == "saveAsTable" || m == "insertInto" || m == "save" ||
              (recv.contains("write") && fmtTerminals.contains(m))
        }.exists(identity)

        def calledNames(body: Tree): Set[String] = body.collect {
          case Term.Apply(Term.Name(fn), _)               => fn
          case Term.Apply(Term.Select(_, Term.Name(fn)), _) => fn
        }.toSet

        val treeDefs   = tree.collect { case d: Defn.Def => d }
        val directWrts = treeDefs.collect { case d if bodyWrites(d.body) => d.name.value }.toSet
        val writeHelps = scala.collection.mutable.LinkedHashSet[String]() ++ directWrts
        treeDefs.foreach { d =>
          val nm = d.name.value
          if (!writeHelps.contains(nm) && (calledNames(d.body) & directWrts).nonEmpty)
            writeHelps += nm
        }

        // ── output ────────────────────────────────────────────────────────────
        CJson.obj(
          "path"                  -> p.toString.asJson,
          "parse_ok"              -> true.asJson,
          "objects"               -> objects.asJson,
          "classes"               -> classes.asJson,
          "entrypoints"           -> entrypoints.asJson,
          "imports"               -> imports.asJson,
          "spark_session_created" -> sparkSessionCreated.asJson,
          "reads"                 -> reads.toList.asJson,
          "writes"                -> writes.toList.asJson,
          "unresolved_reads"      -> unresolvedRds.toList.asJson,
          "unresolved_writes"     -> unresolvedWrs.toList.asJson,
          "write_helpers"         -> writeHelps.toList.asJson,
          "table_refs"            -> tableRefs.toList.asJson,
          "column_refs"           -> colRefs.toList.asJson,
        )
    }
  }

  private def entrypointMethods(owner: String, templ: Template): List[Json] =
    templ.stats.collect {
      case d: Defn.Def if d.name.value == "main" || d.name.value == "run" =>
        CJson.obj("owner" -> owner.asJson, "method" -> d.name.value.asJson)
    }
}

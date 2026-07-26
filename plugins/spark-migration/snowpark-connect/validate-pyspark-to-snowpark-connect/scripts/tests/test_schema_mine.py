"""Regression tests for schema_mine.py column/source/sink attribution.

Run: uv run --project <skill>/.. python -m pytest scripts/tests/ -q
(or: pytest from the scripts dir with schema_mine importable).

Each test writes a tiny PySpark snippet to a temp file and runs ``mine()`` on it,
asserting the mined sources/sinks. Tests named ``test_bug_*`` pin behaviors that
were wrong in the pre-bench data-synthesizer and must stay fixed.
"""
import json
import os
import re
import sys
import textwrap

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import schema_mine  # noqa: E402


def _mine(tmp_path, code: str) -> dict:
    p = tmp_path / "wl.py"
    p.write_text(textwrap.dedent(code))
    return schema_mine.mine(str(p))


def _cols(contract, source_name) -> set:
    s = contract["_sources"].get(source_name, {})
    return {c["name"] for c in s.get("columns", [])}


def _sink_cols(contract, sink_name) -> set:
    s = contract["_sinks"].get(sink_name, {})
    return {c["name"] for c in s.get("columns", [])}


def _col(contract, source_name, col_name) -> dict:
    s = contract["_sources"].get(source_name, {})
    for c in s.get("columns", []):
        if c["name"] == col_name:
            return c
    return {}


# --- characterization: behaviors that must keep working ---------------------

def test_basic_read_select(tmp_path):
    c = _mine(tmp_path, """
        df = spark.read.parquet("/data/customers")
        out = df.select("customer_id", "status", "amount")
        out.write.parquet("/out/result")
    """)
    cols = _cols(c, "customers")
    assert {"customer_id", "status", "amount"} <= cols, c["_sources"]


def test_saveastable_sink_detected(tmp_path):
    c = _mine(tmp_path, """
        df = spark.read.table("raw.events")
        df.select("event_id", "ts").write.saveAsTable("out.events_clean")
    """)
    # sink keyed by its (possibly qualified) target name at the mine() layer
    match = [k for k in c["_sinks"] if k.split(".")[-1] == "events_clean"]
    assert match, c["_sinks"]
    sk = c["_sinks"][match[0]]
    assert sk["kind"] == "table"
    # inline select().write must capture the written columns (not empty)
    assert {"event_id", "ts"} <= {col["name"] for col in sk["columns"]}, sk


def test_fstring_const_table_path_resolved(tmp_path):
    # module-level constants folded into an f-string table path -> real name
    c = _mine(tmp_path, """
        CATALOG = "glue_catalog"
        SCHEMA = "prod"
        df = spark.read.format("iceberg").load(f"{CATALOG}.{SCHEMA}.orders_master")
        df.select("order_no").write.parquet("/o")
    """)
    assert "orders_master" in c["_sources"], list(c["_sources"])


# --- bug repros: must be FIXED (assert the correct behavior) -----------------

def test_bug_join_type_literal_not_a_column(tmp_path):
    # df.join(other, [...], "inner") must NOT mine "inner"/"left"/etc as a column
    c = _mine(tmp_path, """
        a = spark.read.parquet("/data/a_tbl")
        b = spark.read.parquet("/data/b_tbl")
        j = a.join(b, ["k"], "inner")
        j.write.parquet("/o")
    """)
    JOIN_WORDS = {"inner", "outer", "left", "right", "full", "cross",
                  "semi", "anti", "leftsemi", "leftanti", "left_outer",
                  "right_outer", "full_outer", "left_semi", "left_anti"}
    for src in c["_sources"]:
        assert not (JOIN_WORDS & _cols(c, src)), (src, _cols(c, src))


def test_bug_join_on_key_attributed_to_both_sides(tmp_path):
    # a join key in on=[...] belongs to BOTH joined frames
    c = _mine(tmp_path, """
        base = spark.read.parquet("/data/base_tbl")
        rel = spark.read.parquet("/data/rel_tbl")
        j = rel.join(base, on=["res_ent_id"])
        j.write.parquet("/o")
    """)
    assert "res_ent_id" in _cols(c, "base_tbl"), _cols(c, "base_tbl")
    assert "res_ent_id" in _cols(c, "rel_tbl"), _cols(c, "rel_tbl")


def test_bug_post_join_column_not_over_attributed_to_source(tmp_path):
    # Root cause of mock-schema column over-inclusion (and the resulting SCOS 5004
    # ambiguity): a column that arrives via a join (from the RIGHT leg) must NOT be
    # attributed to the LEFT leg's source table. Mirrors the RBI rev_drilldown case
    # where country_cd/fz_code (from rest_data_info) were wrongly seeded onto the
    # rev_data_score mock, creating a duplicate column after the join.
    c = _mine(tmp_path, """
        score_raw = spark.read.parquet("/data/rev_score")
        score = score_raw.select("rest_no", "year_month", "score_val")
        info = spark.read.parquet("/data/rest_info")
        joined = score.join(
            info.select("rest_no", "year_month", "country_cd", "fz_code"),
            ["rest_no", "year_month"], "inner")
        out = joined.select("rest_no", "year_month", "score_val", "country_cd", "fz_code")
        out.write.parquet("/o")
    """)
    score_cols = _cols(c, "rev_score")
    info_cols = _cols(c, "rest_info")
    # country_cd / fz_code arrive from `info` via the join -> must NOT land on the LEFT table
    assert "country_cd" not in score_cols, ("over-inclusion", c["_sources"])
    assert "fz_code" not in score_cols, ("over-inclusion", c["_sources"])
    # `info` genuinely provides them (referenced pre-join in its own .select)
    assert {"country_cd", "fz_code"} <= info_cols, c["_sources"]
    # the LEFT table's genuine pre-join columns + join keys are still attributed
    assert {"rest_no", "year_month", "score_val"} <= score_cols, c["_sources"]


def test_bug_second_join_key_not_attributed_via_joined_leg(tmp_path):
    # RBI rev_drilldown 2-join case: country_cd/time_period arrive via the FIRST
    # join (from `info`) and are then used only as KEYS of a SECOND join whose
    # legs are both join results. They must NOT be attributed back to the base
    # score/point sources via var_src — doing so re-creates the phantom duplicate
    # the first join would raise on (this is what left country_cd/time_period on
    # the RBI score/point mocks even after the projection-leak fix).
    c = _mine(tmp_path, """
        score = spark.read.parquet("/data/rev_score")
        point = spark.read.parquet("/data/rev_point")
        info = spark.read.parquet("/data/rest_info")
        score_j = score.join(info.select("rest_no", "year_month", "country_cd", "time_period"),
                             ["rest_no", "year_month"], "inner")
        point_j = point.join(info.select("rest_no", "year_month", "country_cd", "time_period"),
                             ["rest_no", "year_month"], "inner")
        out = point_j.join(
            score_j.select("rest_no", "time_period", "country_cd", "impactedperc").distinct(),
            ["rest_no", "time_period", "country_cd"], "inner")
        out.write.parquet("/o")
    """)
    score_cols = _cols(c, "rev_score")
    point_cols = _cols(c, "rev_point")
    info_cols = _cols(c, "rest_info")
    # country_cd / time_period come from `info` and are only 2nd-join keys on
    # already-joined legs -> must NOT land on the base score/point sources
    assert "country_cd" not in score_cols, ("2nd-join-key over-inclusion", c["_sources"])
    assert "time_period" not in score_cols, c["_sources"]
    assert "country_cd" not in point_cols, c["_sources"]
    assert "time_period" not in point_cols, c["_sources"]
    # `info` genuinely provides them
    assert {"country_cd", "time_period"} <= info_cols, c["_sources"]
    # first-join keys (native to the base sources) are still attributed
    assert {"rest_no", "year_month"} <= score_cols, c["_sources"]
    assert {"rest_no", "year_month"} <= point_cols, c["_sources"]



def test_bug_groupby_agg_sink_columns(tmp_path):
    # the sink of a groupBy().agg() is the agg OUTPUT columns, not the input cols
    c = _mine(tmp_path, """
        from pyspark.sql import functions as F
        df = spark.read.parquet("/data/facts")
        res = df.groupBy("group_id").agg(
            F.count("input_id").alias("row_count"),
            F.sum("amt").alias("total_amt"),
        )
        res.write.parquet("/out/step_one")
    """)
    sink = _sink_cols(c, "step_one")
    # the agg output keys/aliases must be present
    assert {"group_id", "row_count", "total_amt"} <= sink, sink
    # the raw input-only measure must NOT leak into the sink
    assert "amt" not in sink and "input_id" not in sink, sink


def test_bug_structtype_schema_binding(tmp_path):
    # a StructType literal used as applyInPandas(schema=...) defines the output cols
    c = _mine(tmp_path, """
        from pyspark.sql.types import StructType, StructField, StringType, DoubleType
        out_schema = StructType([
            StructField("id", StringType()),
            StructField("score", DoubleType()),
            StructField("flag", StringType()),
        ])
        df = spark.read.parquet("/data/src")
        res = df.groupBy("id").applyInPandas(my_udf, schema=out_schema)
        res.write.parquet("/out/scored")
    """)
    sink = _sink_cols(c, "scored")
    assert {"id", "score", "flag"} <= sink, sink
    # the StructType field TYPES must carry through, not default to string
    types = {col["name"]: col["type"] for col in c["_sinks"]["scored"]["columns"]}
    assert types.get("score") == "double", types


def test_bug_isin_values_not_columns(tmp_path):
    # .isin([...]) / lit() / when() args are VALUES, never source columns
    c = _mine(tmp_path, """
        from pyspark.sql import functions as F
        df = spark.read.parquet("/data/svc")
        out = df.filter(F.col("svc_cd").isin(["B2B", "B2C", "WH_RENT"])) \
                .withColumn("flag", F.lit("FULFILMENT")) \
                .select("svc_cd", "amount")
        out.write.parquet("/o")
    """)
    cols = _cols(c, "svc")
    # the real columns are present
    assert {"svc_cd", "amount"} <= cols, cols
    # the enum VALUES must NOT appear as columns
    assert not ({"B2B", "B2C", "WH_RENT", "FULFILMENT"} & cols), cols


def test_bug_bare_comparison_value_not_column(tmp_path):
    # F.col('x') == 'VALUE' (no lit wrapper) -> 'VALUE' is not a column
    c = _mine(tmp_path, """
        from pyspark.sql import functions as F
        df = spark.read.parquet("/data/t")
        out = df.filter((F.col("rmk3") == "DLV") & (F.col("rmk2") == "B2C")).select("rmk2", "rmk3")
        out.write.parquet("/o")
    """)
    cols = _cols(c, "t")
    assert {"rmk2", "rmk3"} <= cols, cols
    assert not ({"DLV", "B2C"} & cols), cols


# --- filter/join domain extraction (empty-output prevention) ----------------
# Models a common pattern: a column is filtered against a fixed literal set, and
# a non-id-like key joins two tables. Without seeding the filter literals +
# pooling the join key, the mock filter returns 0 rows and every downstream
# join/output silently collapses to empty.

def test_isin_filter_literals_become_column_values(tmp_path):
    # firc_rld_contrat.filter(code_cat_det IN ('610A','610B','610C')) must seed
    # those literals as the column's `values` domain so the filter keeps rows.
    c = _mine(tmp_path, """
        from pyspark.sql import functions as F
        contrat = spark.table("firc_rld_contrat")
        liste = contrat.filter(F.col("code_cat_det").isin("610A", "610B", "610C")).select("contrat")
        liste.write.saveAsTable("out")
    """)
    col = _col(c, "firc_rld_contrat", "code_cat_det")
    assert set(col.get("values", [])) == {"610A", "610B", "610C"}, col


def test_isin_list_and_starred_var_resolved(tmp_path):
    # isin([...]) literal list AND isin(*var) where var is a list literal
    c = _mine(tmp_path, """
        from pyspark.sql.functions import col
        codes = ["A1", "A2"]
        df = spark.read.parquet("/data/t")
        a = df.filter(col("seg").isin(["S1", "S2"]))
        b = df.filter(col("seg2").isin(*codes))
        a.write.parquet("/o1")
        b.write.parquet("/o2")
    """)
    assert set(_col(c, "t", "seg").get("values", [])) == {"S1", "S2"}, _col(c, "t", "seg")
    assert set(_col(c, "t", "seg2").get("values", [])) == {"A1", "A2"}, _col(c, "t", "seg2")


def test_bare_eq_filter_literal_becomes_value(tmp_path):
    c = _mine(tmp_path, """
        from pyspark.sql.functions import col
        df = spark.read.parquet("/data/t")
        out = df.filter(col("statut") == "ACTIF").select("statut", "x")
        out.write.parquet("/o")
    """)
    assert "ACTIF" in _col(c, "t", "statut").get("values", []), _col(c, "t", "statut")


def test_negated_isin_does_not_seed_values(tmp_path):
    # ~col(x).isin(...) EXCLUDES those values; seeding them would empty the mock.
    c = _mine(tmp_path, """
        from pyspark.sql.functions import col
        df = spark.read.parquet("/data/t")
        out = df.filter(~col("kind").isin("DROP1", "DROP2")).select("kind")
        out.write.parquet("/o")
    """)
    assert not _col(c, "t", "kind").get("values"), _col(c, "t", "kind")


def test_join_on_key_emits_same_named_edge(tmp_path):
    # a join on a (non-id-like) key emits a `joins` edge linking both frames so
    # datagen pools the column and the two mocks overlap.
    c = _mine(tmp_path, """
        base = spark.read.parquet("/data/contrat_detail")
        contrat = spark.read.parquet("/data/firc_rld_contrat")
        j = base.join(contrat, on="contrat", how="inner")
        j.write.parquet("/o")
    """)
    edges = {tuple(sorted((e["left"], e["right"]))) for e in c["_joins"]}
    assert ("contrat_detail.contrat", "firc_rld_contrat.contrat") in edges, c["_joins"]


def test_join_cross_named_equality_edge(tmp_path):
    # T1.a == T2.b links the two DIFFERENTLY-named columns (name-based pooling
    # can never do this).
    c = _mine(tmp_path, """
        a = spark.read.parquet("/data/T1")
        b = spark.read.parquet("/data/T2")
        j = a.join(b, a.k1 == b.k2)
        j.write.parquet("/o")
    """)
    edges = {tuple(sorted((e["left"], e["right"]))) for e in c["_joins"]}
    assert ("T1.k1", "T2.k2") in edges, c["_joins"]


def test_join_multi_key_emits_one_edge_per_key(tmp_path):
    c = _mine(tmp_path, """
        a = spark.read.parquet("/data/T1")
        b = spark.read.parquet("/data/T2")
        j = a.join(b, on=["k1", "k2"])
        j.write.parquet("/o")
    """)
    edges = {tuple(sorted((e["left"], e["right"]))) for e in c["_joins"]}
    assert ("T1.k1", "T2.k1") in edges, c["_joins"]
    assert ("T1.k2", "T2.k2") in edges, c["_joins"]


def test_join_no_longer_sets_per_column_join_key(tmp_path):
    # the per-column `join_key` flag is replaced by the `joins` edge list.
    c = _mine(tmp_path, """
        a = spark.read.parquet("/data/T1")
        b = spark.read.parquet("/data/T2")
        a.join(b, on="k").write.parquet("/o")
    """)
    for src in c["_sources"].values():
        for col in src.get("columns", []):
            assert "join_key" not in col, col


def test_sql_in_predicate_seeds_values(tmp_path):
    # WHERE col IN (...) inside an embedded spark.sql() body -> column values
    c = _mine(tmp_path, """
        df = spark.sql("SELECT contrat, code_cat_det FROM firc_rld_contrat "
                       "WHERE code_cat_det IN ('610A', '610B', '610C')")
        df.write.saveAsTable("out")
    """)
    col = _col(c, "firc_rld_contrat", "code_cat_det")
    assert {"610A", "610B", "610C"} <= set(col.get("values", [])), col


def test_bug_agg_output_types(tmp_path):
    # count(..).alias(..) -> long; sum(..).alias(..) -> double (not string)
    c = _mine(tmp_path, """
        from pyspark.sql import functions as F
        df = spark.read.parquet("/data/facts")
        res = df.groupBy("k").agg(
            F.count("a").alias("n_rows"),
            F.sum("amt").alias("amt_total"),
        )
        res.write.parquet("/out/rollup")
    """)
    sink = c["_sinks"]["rollup"]["columns"]
    types = {col["name"]: col["type"] for col in sink}
    assert types.get("n_rows") == "long", types
    assert types.get("amt_total") == "double", types


def test_loop_read_is_one_dynamic_source_with_fanout(tmp_path):
    # a loop over a dict literal that reads N tables -> ONE source flagged
    # dynamic_read with the resolved fan-out value-set (NOT N materialized tables,
    # NOT a garbage merged column set).
    c = _mine(tmp_path, """
        tables = {'CVT130':'policy-phone', 'CVT125':'policy-master', 'CVT137':'subject-master'}
        for name, table in tables.items():
            path = f"{s3_path}{table}/year={y}/*/"
            df = spark.read.parquet(path)
            tables[name] = df
    """)
    dyn = [(n, s) for n, s in c["_sources"].items() if s.get("dynamic_read")]
    assert len(dyn) == 1, list(c["_sources"])
    _, s = dyn[0]
    assert s["fanout"]["count"] == 3, s["fanout"]
    assert set(s["fanout"]["values"]) == {"policy-phone", "policy-master", "subject-master"}, s["fanout"]
    assert s["column_completeness"] == "open"


def test_loop_read_over_list_literal_fanout(tmp_path):
    # control-flow-agnostic: a list literal works the same as a dict
    c = _mine(tmp_path, """
        SHARDS = ["shard_a", "shard_b", "shard_c", "shard_d"]
        for s in SHARDS:
            df = spark.read.parquet(f"{base}/{s}/")
            df.write.parquet("/o")
    """)
    dyn = [s for s in c["_sources"].values() if s.get("dynamic_read")]
    assert len(dyn) == 1 and dyn[0]["fanout"]["count"] == 4, [s.get("fanout") for s in c["_sources"].values()]


def test_dynamic_read_unresolvable_fanout_count_none(tmp_path):
    # path built from a runtime var with no static value-set -> dynamic, count None
    c = _mine(tmp_path, """
        tbl = some_runtime_lookup()
        df = spark.read.parquet(f"{base}/{tbl}/")
        df.write.parquet("/o")
    """)
    dyn = [s for s in c["_sources"].values() if s.get("dynamic_read")]
    assert dyn and dyn[0]["fanout"]["count"] is None, [s.get("fanout") for s in c["_sources"].values()]


def test_constant_read_not_flagged_dynamic(tmp_path):
    c = _mine(tmp_path, """
        df = spark.read.parquet("/data/static_table")
        df.select("a").write.parquet("/o")
    """)
    assert not any(s.get("dynamic_read") for s in c["_sources"].values()), c["_sources"]


def test_partitioned_single_table_not_dynamic(tmp_path):
    # fixed table with only a runtime partition/date is NOT a fan-out
    c = _mine(tmp_path, """
        df = spark.read.parquet(f"{base}/loan_master/dt={run_date}/")
        df.select("loan_id").write.parquet("/o")
    """)
    assert not any(s.get("dynamic_read") for s in c["_sources"].values()), \
        {n: s.get("fanout") for n, s in c["_sources"].items()}
    # and the table is still correctly named
    assert any(n.split(".")[-1] == "loan_master" for n in c["_sources"]), list(c["_sources"])


def test_qualified_ref_attributes_to_owning_source(tmp_path):
    # `b.col` qualified refs place columns on the right source even when a bare
    # post-join `.select("col")` is ambiguous (the EQS Step 1 bug).
    c = _mine(tmp_path, """
        a = spark.read.parquet("/a")
        b = spark.read.parquet("/b")
        j1 = a.join(b, a.res_ent_id == b.src, "inner").select("src","dst")
        j2 = a.join(b, a.res_ent_id == b.dst, "inner").select("src","dst")
        out = j1.union(j2)
        out.write.parquet("/o")
    """)
    cols = {n: sorted(col["name"] for col in s.get("columns", [])) for n, s in c["_sources"].items()}
    a = next(s for n, s in cols.items() if n.endswith("a"))
    b = next(s for n, s in cols.items() if n.endswith("b"))
    assert "src" in b and "dst" in b, cols          # src/dst belong to b
    assert "src" not in a and "dst" not in a, cols   # and must NOT leak onto a
    assert "res_ent_id" in a, cols                   # a owns the join key it references


def test_join_key_survives_rename_to_same_name(tmp_path):
    # a column that is also a withColumnRenamed TARGET elsewhere must not be deleted
    # from a source that genuinely joins on it.
    c = _mine(tmp_path, """
        base = spark.read.parquet("/base")
        recs = spark.read.parquet("/recs")
        renamed = recs.withColumnRenamed("src", "res_ent_id")
        out = base.join(renamed, on=["res_ent_id"], how="inner")
        out.write.parquet("/o")
    """)
    base = next(s for n, s in c["_sources"].items() if n.endswith("base"))
    names = [col["name"] for col in base.get("columns", [])]
    assert "res_ent_id" in names, names


def test_helper_referenced_columns_attributed_to_source(tmp_path):
    # columns referenced only inside a helper fn (behind a df param) are attributed
    # to the source the helper is called on (5.3). The withColumn OUTPUT name is
    # excluded; the coalesce/concat_ws INPUT names are kept.
    c = _mine(tmp_path, """
        import pyspark.sql.functions as f
        def address_cleaning(df):
            df = df.withColumn("address_line1",
                               f.coalesce("address_line1",
                                          f.concat_ws(" ", "street_number", "street_name", "apartment_number")))
            return df
        users = spark.read.parquet("/users")
        users = address_cleaning(users)
        users.write.parquet("/o")
    """)
    src = next(s for s in c["_sources"].values())
    names = {col["name"] for col in src.get("columns", [])}
    assert {"street_number", "street_name", "apartment_number"} <= names, names


def test_dynamic_columns_helper_not_a_column_helper(tmp_path):
    # a helper that only does `for col in df.columns` (fully dynamic) references no
    # specific column literals, so it must NOT inject phantom columns.
    c = _mine(tmp_path, """
        import pyspark.sql.functions as f
        def basic_clean(df):
            for col in df.columns:
                df = df.withColumn(col, f.trim(f.col(col)))
            return df
        t = spark.read.parquet("/t")
        t = basic_clean(t)
        t.write.parquet("/o")
    """)
    src = next(s for s in c["_sources"].values())
    names = {col["name"] for col in src.get("columns", [])}
    assert "col" not in names and "columns" not in names, names


def test_write_to_unresolved_path_still_emits_sink(tmp_path):
    # a genuine write whose target path is an unresolvable variable must still
    # surface a sink (placeholder name from the written df + llm_todo), never drop it.
    c = _mine(tmp_path, """
        df = spark.read.parquet("/in")
        events_df = df.select("road_id", "score")
        events_df.write.mode("overwrite").parquet(out_path)
    """)
    assert c["_sinks"], "write to a variable path dropped the sink"
    nm, sk = next(iter(c["_sinks"].items()))
    assert sk.get("llm_todo"), sk           # flagged for target confirmation
    assert "road_id" in [col["name"] for col in sk.get("columns", [])], sk


def test_helper_built_path_var_names_sink(tmp_path):
    # `target_path = stagingPathFor(cat, sch, "grp", "tbl")` then `.save(target_path)`
    # -> the helper's id-like string arg names the sink (not dropped).
    c = _mine(tmp_path, """
        df = spark.read.json("/in")
        out = df.select("a")
        target_path = stagingPathFor(cat, sch, "vehicle_events", "trip_start")
        out.write.format("json").save(target_path)
    """)
    assert any("vehicle_events" in n or "trip_start" in n for n in c["_sinks"]), list(c["_sinks"])


def test_class_based_main_is_entrypoint_helper_is_not(tmp_path):
    # a __main__ script that builds a SparkSession inside a class/method (reached via
    # importlib dynamic dispatch) IS an entrypoint; a common/ helper that merely
    # DEFINES a session-builder is NOT.
    import schema_mine
    (tmp_path / "common").mkdir()
    (tmp_path / "common" / "__init__.py").write_text("")
    (tmp_path / "common" / "session.py").write_text(
        "from pyspark.sql import SparkSession\n"
        "def get_spark():\n"
        "    return SparkSession.builder.getOrCreate()\n")
    (tmp_path / "main.py").write_text(
        "import importlib\n"
        "from pyspark.sql import SparkSession\n"
        "class App:\n"
        "    def run(self):\n"
        "        self.spark = SparkSession.builder.getOrCreate()\n"
        "        mod = importlib.import_module('common.session')\n"
        "if __name__ == '__main__':\n"
        "    App().run()\n")
    eps, _ = schema_mine.detect_entrypoints(str(tmp_path))
    paths = {e["path"] for e in eps}
    assert "main.py" in paths, paths
    assert not any("session.py" in p for p in paths), paths


# --- .ipynb (Jupyter notebook) entrypoint support --------------------------

def _write_ipynb(path, *code_cells):
    import json
    nb = {"cells": [{"cell_type": "code", "metadata": {}, "outputs": [],
                     "execution_count": None,
                     "source": (c if c.endswith("\n") else c + "\n").splitlines(keepends=True)}
                    for c in code_cells],
          "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    path.write_text(json.dumps(nb))
    return path


def test_read_source_ipynb_concats_cells_and_neutralizes_magics():
    import tempfile, pathlib, ast
    d = pathlib.Path(tempfile.mkdtemp())
    p = _write_ipynb(d / "nb.ipynb",
                     "%pip install foo\nimport os",
                     "!ls -la",
                     "df = spark.read.parquet('/data/orders')\nx = 1")
    src = schema_mine._read_source(str(p))
    ast.parse(src)                       # must parse despite the magics
    assert "spark.read.parquet('/data/orders')" in src
    assert "%pip" not in src and "!ls" not in src
    assert "notebook-magic" in src       # magics were neutralized, not dropped


def test_mine_runs_on_ipynb(tmp_path):
    p = _write_ipynb(tmp_path / "job.ipynb",
                     "orders = spark.read.parquet('/data/orders')",
                     "out = orders.select('order_id', 'amount')",
                     "out.write.parquet('/out/orders_clean')")
    c = schema_mine.mine(str(p))
    src = next(iter(c["_sources"].values()))
    assert {"order_id", "amount"} <= {col["name"] for col in src["columns"]}
    assert c["_sinks"], "ipynb write sink not detected"


def test_detect_entrypoints_picks_up_ipynb(tmp_path):
    _write_ipynb(tmp_path / "pipeline.ipynb",
                 "from pyspark.sql import SparkSession\nspark = SparkSession.builder.getOrCreate()",
                 "df = spark.read.parquet('/data/events')",
                 "df.write.parquet('/out/events')")
    # a non-spark notebook must NOT become an entrypoint
    _write_ipynb(tmp_path / "scratch.ipynb", "x = 1 + 1\nprint(x)")
    eps, facts = schema_mine.detect_entrypoints(str(tmp_path))
    paths = {e["path"] for e in eps}
    assert "pipeline.ipynb" in paths, paths
    assert "scratch.ipynb" not in paths, paths
    ep = next(e for e in eps if e["path"] == "pipeline.ipynb")
    assert "ipynb" in ep["reasons"]


# --- dotted catalog.schema.table f-strings (no '/' path) --------------------

def test_dotted_fstring_table_is_static_not_dynamic_read(tmp_path):
    # spark.table(f"{DB}.{SCHEMA}.BROKERS") -> the trailing literal segment is the
    # static table identity; must NOT be flagged a dynamic/parameterized read.
    c = _mine(tmp_path, """
        df = spark.table(f"{DATABASE_NAME}.{SCHEMA_STAGING}.BROKERS")
        df.select("a").write.parquet("/o")
    """)
    assert "BROKERS" in c["_sources"], list(c["_sources"])
    assert not c["_sources"]["BROKERS"].get("dynamic_read"), c["_sources"]["BROKERS"]


def test_dotted_fstring_sink_resolves_table_name(tmp_path):
    # saveAsTable on a dotted f-string target must be keyed by the table name
    # (BROKERS), not the written DataFrame variable.
    c = _mine(tmp_path, """
        df = spark.read.csv("s3://bucket/brokers.csv")
        df.select("a", "b").write.saveAsTable(f"{DATABASE_NAME}.{SCHEMA_STAGING}.BROKERS")
    """)
    assert "BROKERS" in c["_sinks"], list(c["_sinks"])


def test_fully_dynamic_dotted_table_still_unresolved(tmp_path):
    # f"{schema}.{tbl}" where the table segment itself is a runtime variable must
    # NOT be coerced to a bogus static name.
    c = _mine(tmp_path, """
        df = spark.table(f"{schema}.{tbl}")
        df.select("a").write.parquet("/o")
    """)
    assert "BROKERS" not in c["_sources"]
    # nothing resolved to a certain literal table name here
    assert not any(s.get("name_origin") == "literal_name"
                   for s in c["_sources"].values()), c["_sources"]


# --- sibling .sql template enrichment ---------------------------------------

def test_sql_files_catalog_mines_all_project_sql(tmp_path):
    (tmp_path / "orders.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.table(f"{DB}.{SCH}.ORDERS")
        df.write.saveAsTable(f"{DB}.{SCH}.ORDERS")
    """))
    (tmp_path / "orders.sql").write_text(
        "INSERT INTO ${DB}.${SCH}.ORDERS\n"
        "SELECT o.ORDER_ID, o.LOCATION_ID, o.AMOUNT\n"
        "FROM ${DB}.${SCH}.ORDERS o WHERE o.STATUS = 'X';")
    out = schema_mine.synthesize(str(tmp_path))
    ep = next(e for e in out["entrypoints"] if e["path"] == "orders.py")
    assert "sql_templates" not in ep
    assert "sql_column_refs" not in ep
    sql_files = out.get("sql_files") or []
    assert len(sql_files) == 1
    sf = sql_files[0]
    assert sf["path"] == "orders.sql"
    assert sf.get("llm_todo")
    assert "delete this todo" in sf["llm_todo"]
    orders = sf["tables"]["orders"]
    assert orders["name"] == "ORDERS"
    assert {"ORDER_ID", "LOCATION_ID", "AMOUNT", "STATUS"} <= set(orders["columns"])
    assert "write" in orders["roles"]
    assert out["complete"] is False


def test_sql_files_catalog_excludes_cte_aliases_case_insensitive(tmp_path):
    # Spark SQL often declares CTEs in uppercase (CTE_COMP) but references them
    # lowercase (cte_comp); those aliases must not become catalog tables.
    (tmp_path / "run.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        spark.sql("SELECT 1")
    """))
    (tmp_path / "compdata.sql").write_text(textwrap.dedent("""
        INSERT INTO ${DB}.${SCH}.COMP_VS_RDS
        WITH CTE_COMP AS (
          SELECT a.EFFECTIVE_DATE
          FROM ${DB}.${SCH}.HXPRICECOMP a
        ),
        CTE1 AS (
          SELECT c.EFFECTIVE_DATE FROM cte_comp c
        )
        SELECT c.EFFECTIVE_DATE FROM cte1 c;
    """))
    out = schema_mine.synthesize(str(tmp_path))
    sf = next(sf for sf in out["sql_files"] if sf["path"] == "compdata.sql")
    assert "cte_comp" not in sf["tables"], sf["tables"]
    assert "cte1" not in sf["tables"], sf["tables"]
    assert "hxpricecomp" in sf["tables"]
    assert "comp_vs_rds" in sf["tables"]


def test_sql_files_catalog_dedupes_mixed_case_columns(tmp_path):
    (tmp_path / "run.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        spark.sql("SELECT 1")
    """))
    (tmp_path / "orders.sql").write_text(textwrap.dedent("""
        INSERT INTO ${DB}.${SCH}.ORDERS
        SELECT o.ITEM, o.item, o.CHANNEL, c.channel
        FROM ${DB}.${SCH}.ORDERS o
        JOIN ${DB}.${SCH}.CHANNELS c ON o.ITEM = c.ITEM;
    """))
    out = schema_mine.synthesize(str(tmp_path))
    sf = next(sf for sf in out["sql_files"] if sf["path"] == "orders.sql")
    orders = sf["tables"]["orders"]
    assert orders["columns"] == ["CHANNEL", "ITEM"]
    channels = sf["tables"]["channels"]
    assert set(channels["columns"]) == {"CHANNEL", "ITEM"}


def test_sql_files_catalog_keeps_duplicate_stems_separate(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "a" / "pricecost.sql").write_text(
        "SELECT p.COST FROM ${DB}.${SCH}.PRICE p;")
    (tmp_path / "b" / "pricecost.sql").write_text(
        "SELECT c.MARGIN FROM ${DB}.${SCH}.COST c;")
    (tmp_path / "run.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        spark.sql("SELECT 1")
    """))
    out = schema_mine.synthesize(str(tmp_path))
    paths = {sf["path"] for sf in out.get("sql_files", [])}
    assert paths == {"a/pricecost.sql", "b/pricecost.sql"}


def test_write_schemas_dir_split_layout(tmp_path):
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        spark.table("T").write.parquet("/o")
    """))
    out_dir = tmp_path / "schemas"
    result = schema_mine.synthesize(str(tmp_path))
    import datagen
    datagen.write_schemas_dir(out_dir, result)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert len(manifest["entrypoints"]) == len(result["entrypoints"])
    for ref in manifest["entrypoints"]:
        assert "dir" in ref
        assert "file" not in ref
        ep_dir = out_dir / ref["dir"]
        meta_path = ep_dir / "_meta.json"
        assert meta_path.is_file()
        ep = json.loads(meta_path.read_text())
        assert ep["id"] == ref["id"]
        # tables/ dir should exist and contain the table files
        tables_dir = ep_dir / "tables"
        assert tables_dir.is_dir()


def test_sql_file_does_not_invent_unrelated_sources(tmp_path):
    # .sql catalog is separate from entrypoint mining; staging tables in .sql must
    # not appear on the entrypoint until the LLM links and merges them.
    (tmp_path / "orders.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.table(f"{DB}.{SCH}.ORDERS")
        df.write.parquet("/o")
    """))
    (tmp_path / "orders.sql").write_text(
        "INSERT INTO ${DB}.${SCH}.ORDERS_STAGING\n"
        "SELECT s.ORDER_ID FROM ${DB}.${SCH}.ORDERS s;")
    out = schema_mine.synthesize(str(tmp_path))
    ep = next(e for e in out["entrypoints"] if e["path"] == "orders.py")
    assert "ORDERS_STAGING" not in ep["tables"], ep["tables"]
    sf = next(sf for sf in out["sql_files"] if sf["path"] == "orders.sql")
    assert "orders_staging" in sf["tables"]


# --- source naming + provenance --------------------------------------------

def test_generic_schema_var_name_not_used_as_source_name(tmp_path):
    # a `.schema(df_schema)` binding strips to the generic token "df" -- that is
    # NOT a table identity (and collides across entrypoints), so the source falls
    # back to a per-entrypoint `srcN` placeholder instead.
    c = _mine(tmp_path, """
        df = spark.read.schema(df_schema).csv(input_path)
        df.select("a").write.parquet("/o")
    """)
    assert "df" not in c["_sources"], list(c["_sources"])
    assert any(re.match(r"^src\d+$", n) for n in c["_sources"]), list(c["_sources"])


def test_sources_and_sinks_carry_defined_at_provenance(tmp_path):
    # every mined source/sink records `file:line` so the LLM can pin which read /
    # write a (possibly placeholder) name refers to.
    c = _mine(tmp_path, """
        df = spark.read.parquet("/data/customers")
        df.select("a").write.saveAsTable("out.events")
    """)
    src = next(iter(c["_sources"].values()))
    assert src.get("defined_at", "").endswith("wl.py:2"), src.get("defined_at")
    sink = next(iter(c["_sinks"].values()))
    assert sink.get("defined_at", "").endswith("wl.py:3"), sink.get("defined_at")


def test_fstring_path_extension_not_mistaken_for_table_name(tmp_path):
    # a filesystem path f-string ending in a literal extension (data_{d}.csv) must
    # NOT be named after the extension ("csv") -- the dot-segment table logic only
    # applies to slash-free dotted table refs.
    c = _mine(tmp_path, """
        df = spark.read.csv(f"s3://bucket/daily/data_{run_date}.csv")
        df.select("a").write.parquet("/o")
    """)
    assert "csv" not in c["_sources"], list(c["_sources"])


def test_reader_options_mined_from_read_chain(tmp_path):
    # delimiter/header/encoding given via .option(...) on a CSV read are mined into
    # reader_options so datagen + COPY INTO match the workload's reader.
    c = _mine(tmp_path, """
        df = (spark.read
              .option("delimiter", "|")
              .option("header", "false")
              .option("encoding", "ISO-8859-1")
              .csv("/data/customers.csv"))
        df.select("a").write.parquet("/o")
    """)
    src = next(iter(c["_sources"].values()))
    opts = src.get("reader_options") or {}
    assert opts.get("delimiter") == "|", opts
    assert opts.get("header") is False, opts            # 'false' string -> bool
    assert opts.get("encoding") == "ISO-8859-1", opts


def test_reader_options_mined_from_options_kwargs(tmp_path):
    # the .options(sep=..., header=...) keyword form is mined the same way.
    c = _mine(tmp_path, """
        df = spark.read.options(sep=";", header=True).csv("/data/t.csv")
        df.select("a").write.parquet("/o")
    """)
    src = next(iter(c["_sources"].values()))
    opts = src.get("reader_options") or {}
    assert opts.get("sep") == ";", opts
    assert opts.get("header") is True, opts


def test_read_parquet_is_not_sink(tmp_path):
    # spark.read.parquet shares the 'parquet' method name with df.write.parquet —
    # a read must never be mined as a sink.
    c = _mine(tmp_path, """
        df = spark.read.parquet("/data/customers")
        df.select("a").write.parquet("/out")
    """)
    assert len(c["_sources"]) == 1, c
    assert len(c["_sinks"]) == 1, c
    sink = next(iter(c["_sinks"].values()))
    assert sink.get("kind") == "file", sink


def test_format_snowflake_read_is_connector(tmp_path):
    c = _mine(tmp_path, """
        df = (spark.read.format("snowflake")
              .option("dbtable", "MY_TBL")
              .option("sfurl", "acct.snowflakecomputing.com")
              .load())
        df.select("a").write.parquet("/o")
    """)
    src = next(iter(c["_sources"].values()))
    assert src.get("format") == "snowflake", src
    assert src.get("reader_method") == "load", src


def test_synthesize_preserves_defined_at_and_reader_options(tmp_path):
    # fields set in mine() must survive synthesize()'s lean contract rebuild.
    p = tmp_path / "wl.py"
    p.write_text(textwrap.dedent("""
        df = (spark.read.option("delimiter", "|").csv("/data/t.csv"))
        df.select("a").write.saveAsTable("out.t")
    """))
    out = schema_mine.synthesize(str(tmp_path))
    ep = out["entrypoints"][0]
    # In tables dict, read tables have access=read, write tables have access=write
    read_tables = {n: t for n, t in ep["tables"].items() if t.get("access") in ("read", "readwrite")}
    write_tables = {n: t for n, t in ep["tables"].items() if t.get("access") in ("write", "readwrite")}
    src = next(iter(read_tables.values()))
    assert src.get("defined_at", "").endswith("wl.py:2"), src
    assert src.get("reader_options", {}).get("delimiter") == "|"
    sink = next(iter(write_tables.values()))
    assert sink.get("defined_at", "").endswith("wl.py:3"), sink
    assert sink.get("category") == "table"


def test_qualified_column_named_like_api_method(tmp_path):
    # call-site detection: df.select as a column (not df.select(...)) is harvested.
    c = _mine(tmp_path, """
        t = spark.read.parquet("/t")
        t = t.withColumn("out", t.select + 1)
        t.write.parquet("/o")
    """)
    src = next(iter(c["_sources"].values()))
    names = {col["name"] for col in src.get("columns", [])}
    assert "select" in names, names


def test_imported_capability_io_not_attributed_to_entrypoint(tmp_path):
    # I/O buried inside a def of an IMPORTED module is a reusable capability, not
    # confirmed entrypoint I/O -> it must NOT be attributed. The entrypoint's OWN
    # reads/writes (even inside its own functions) ARE kept.
    (tmp_path / "util_io.py").write_text(textwrap.dedent("""
        def write_out(df):
            df.write.saveAsTable("warehouse.capability_table")
    """))
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        from util_io import write_out
        spark = SparkSession.builder.getOrCreate()
        def run():
            df = spark.read.parquet("/data/orders")
            write_out(df)
        run()
    """))
    out = schema_mine.synthesize(str(tmp_path))
    ep = next(e for e in out["entrypoints"] if e["path"] == "job.py")
    # the imported util's in-def write is NOT a sink of this entrypoint
    assert "capability_table" not in ep["tables"], ep["tables"]
    # the entrypoint's OWN read (inside its own def) is still attributed
    assert "orders" in ep["tables"], ep["tables"]


def test_module_level_io_in_imported_file_is_kept(tmp_path):
    # a read at MODULE level in an imported file runs on import -> it IS real I/O
    # for any entrypoint that imports it (only in-def capabilities are dropped).
    (tmp_path / "bootstrap.py").write_text(textwrap.dedent("""
        config_df = spark.read.parquet("/data/bootstrap_config")
    """))
    (tmp_path / "job2.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        import bootstrap
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.parquet("/data/main")
        df.write.parquet("/o")
    """))
    out = schema_mine.synthesize(str(tmp_path))
    ep = next(e for e in out["entrypoints"] if e["path"] == "job2.py")
    assert "bootstrap_config" in ep["tables"], ep["tables"]
    assert "main" in ep["tables"], ep["tables"]


def test_synthesize_records_import_closure(tmp_path):
    # The entrypoint's persisted closure must list the entrypoint AND every file
    # it statically imports, so downstream patch/scan tooling inspects helpers too.
    # Put both in a SUBDIR importing a bare sibling — the file's own dir is on
    # sys.path[0], so this must resolve even though it isn't the workload root
    # (regression guard for own-dir import resolution).
    sub = tmp_path / "jobs"
    sub.mkdir()
    (sub / "io_helpers.py").write_text(textwrap.dedent("""
        def load(spark):
            return spark.read.parquet("/data/helper_src")
    """))
    (sub / "job3.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        import io_helpers
        spark = SparkSession.builder.getOrCreate()
        df = io_helpers.load(spark)
        df.write.parquet("/o")
    """))
    out = schema_mine.synthesize(str(tmp_path))
    ep = next(e for e in out["entrypoints"] if e["path"] == "jobs/job3.py")
    assert "closure" in ep, ep
    assert "jobs/job3.py" in ep["closure"]
    assert "jobs/io_helpers.py" in ep["closure"], ep["closure"]


# ---------------------------------------------------------------------------
# Display detection + sink synthesis
# ---------------------------------------------------------------------------


def test_display_only_notebook_synthesis(tmp_path):
    """A notebook with reads + display(df) but no write → display_only + display_0 sink."""
    code = """\
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.parquet("/data/input")
        display(df)
    """
    contract = _mine(tmp_path, code)
    assert contract.get("display_only") is True
    assert "display_0" in contract["_sinks"]
    sink = contract["_sinks"]["display_0"]
    assert sink["kind"] == "file"
    ds = contract.get("display_sinks", [])
    assert len(ds) == 1
    assert ds[0]["id"] == "display_0"
    assert "df" in ds[0]["arg_src"]


def test_display_with_real_write_no_synthesis(tmp_path):
    """A notebook with a real saveAsTable write + display(df) → NOT display_only."""
    code = """\
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.parquet("/data/input")
        df.write.saveAsTable("output_table")
        display(df)
    """
    contract = _mine(tmp_path, code)
    assert contract.get("display_only") is not True
    assert "display_0" not in contract["_sinks"]
    assert contract.get("display_sinks") is None



# --- llm_todo flagging of guessed (all-'string') column types ---

def _synthesize_tables(tmp_path, code: str) -> dict:
    """Run synthesize() on a one-file workload; return {table_name: entry}."""
    (tmp_path / "wl.py").write_text(textwrap.dedent(code))
    res = schema_mine.synthesize(str(tmp_path))
    out = {}
    for ep in res["entrypoints"]:
        out.update(ep.get("tables", {}))
    return res, out


def test_all_string_read_source_flags_types_and_connector_columns(tmp_path):
    res, tables = _synthesize_tables(tmp_path, """
        df = spark.read.table("SRC")
        df = df.filter(df.status == "OPEN")
        df.select("store_id", "status").write.saveAsTable("OUT")
    """)
    todo = tables["SRC"].get("llm_todo", "")
    assert "types default to string" in todo
    # P5: connector/JDBC alias reads must add WHERE/JOIN source columns
    assert "source columns" in todo and "aliases" in todo
    assert res["complete"] is False


def test_all_string_sink_gets_confirm_types_todo(tmp_path):
    _res, tables = _synthesize_tables(tmp_path, """
        df = spark.read.table("SRC")
        df.select("store_id", "status").write.saveAsTable("OUT")
    """)
    todo = tables["OUT"].get("llm_todo", "")
    assert "every TYPE defaulted to 'string'" in todo


def test_typed_columns_do_not_get_string_default_todo(tmp_path):
    # a column with an explicit int cast must NOT trip the all-string todo
    _res, tables = _synthesize_tables(tmp_path, """
        from pyspark.sql import functions as F
        df = spark.read.table("SRC")
        df = df.withColumn("n", F.col("n").cast("int"))
        df.select("n").write.saveAsTable("OUT")
    """)
    out_todo = tables.get("OUT", {}).get("llm_todo", "")
    assert "every TYPE defaulted to 'string'" not in out_todo


def test_ep_weight_in_synthesize_and_manifest(tmp_path):
    # Two reads, one write -> weight = 1 + 2*2 + 1 = 6
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        a = spark.read.table("src_a")
        b = spark.read.table("src_b")
        a.join(b, "id").write.saveAsTable("out_table")
    """))

    result = schema_mine.synthesize(str(tmp_path))

    # weights key must exist
    assert "weights" in result, result.keys()
    assert len(result["weights"]) == len(result["entrypoints"])

    # verify formula for each EP
    for ep in result["entrypoints"]:
        ep_id = ep["id"]
        assert ep_id in result["weights"], ep_id
        tables = ep.get("tables") or {}
        expected_n_read = sum(
            1 for t in tables.values()
            if t.get("access", "read") in ("read", "readwrite")
        )
        expected_n_write = sum(
            1 for t in tables.values()
            if t.get("access") in ("write", "readwrite")
        )
        expected_weight = 1 + 2 * expected_n_read + expected_n_write
        w = result["weights"][ep_id]
        assert w["weight"] == expected_weight, (ep_id, w, tables)
        assert w["weight_breakdown"]["n_read_tables"] == expected_n_read
        assert w["weight_breakdown"]["n_write_tables"] == expected_n_write

    # check manifest.json entries
    out_dir = tmp_path / "schemas"
    import datagen
    datagen.write_schemas_dir(out_dir, result)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    for ref in manifest["entrypoints"]:
        assert isinstance(ref["weight"], int), ref
        assert isinstance(ref["weight_breakdown"], dict), ref
        assert "n_read_tables" in ref["weight_breakdown"]
        assert "n_write_tables" in ref["weight_breakdown"]
        # source_runtime is surfaced in the manifest so the orchestrator can
        # detect Databricks-native entrypoints without reading per-EP files.
        assert "source_runtime" in ref, ref
        assert ref["source_runtime"] in ("databricks", "spark", None)

    # _meta.json must NOT contain weight
    for ref in manifest["entrypoints"]:
        meta = json.loads((out_dir / ref["dir"] / "_meta.json").read_text())
        assert "weight" not in meta, meta.keys()


def test_summary_n_databricks_entrypoints(tmp_path):
    # One Databricks-native entrypoint (uses dbutils) + one plain Spark entrypoint.
    (tmp_path / "dbx_job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src")
        dbutils.fs.ls("/mnt/data")
        df.write.saveAsTable("out")
    """))
    (tmp_path / "spark_job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src2")
        df.write.saveAsTable("out2")
    """))

    result = schema_mine.synthesize(str(tmp_path))

    # In-memory result first
    assert result["summary"]["n_databricks_entrypoints"] == 1
    assert result["summary"]["n_entrypoints"] == 2

    # Manifest on disk must carry the same values
    out_dir = tmp_path / "schemas"
    import datagen
    datagen.write_schemas_dir(out_dir, result)
    manifest = json.loads((out_dir / "manifest.json").read_text())
    assert manifest["summary"]["n_databricks_entrypoints"] == 1
    assert manifest["summary"]["n_entrypoints"] == 2


# ---------------------------------------------------------------------------
# Fix 1: case-insensitive table name deduplication
# ---------------------------------------------------------------------------

def test_case_insensitive_dedupe(tmp_path):
    """Two reads of the same table with different casing → single merged entry."""
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        a = spark.read.table("MY_TABLE")
        b = spark.read.table("my_table")
        a.join(b, "id").write.saveAsTable("out")
    """))
    result = schema_mine.synthesize(str(tmp_path))
    tables = result["entrypoints"][0]["tables"]
    variants = [k for k in tables if k.lower() == "my_table"]
    assert len(variants) == 1, \
        "Expected case-insensitive dedup but got: %s" % list(tables.keys())


# ---------------------------------------------------------------------------
# Fix 2: alias join edge warning
# ---------------------------------------------------------------------------

def test_alias_join_edge_warning(tmp_path, capsys):
    """selectExpr alias used as join key → warning emitted to stderr."""
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        a = spark.read.table("src_a")
        b = spark.read.table("src_b")
        a2 = a.selectExpr("id AS aliased_id")
        a2.join(b, on="aliased_id").write.saveAsTable("out")
    """))
    schema_mine.synthesize(str(tmp_path))
    captured = capsys.readouterr()
    assert "[schema_mine] WARN" in captured.err, \
        "Expected alias warning, stderr was: %r" % captured.err
    assert "aliased_id" in captured.err


# ---------------------------------------------------------------------------
# Fix 3: Python-variable false-positive filter for write targets
# ---------------------------------------------------------------------------

def test_saveAsTable_string_var_positive(tmp_path):
    """Variable holding a valid dotted table ref used in saveAsTable → write entry."""
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src")
        TABLE_NAME = "db.my_output"
        df.write.saveAsTable(TABLE_NAME)
    """))
    result = schema_mine.synthesize(str(tmp_path))
    tables = result["entrypoints"][0]["tables"]
    write_entries = {k: v for k, v in tables.items()
                     if v.get("access") in ("write", "readwrite")}
    assert any("my_output" in k.lower() for k in write_entries), \
        "Expected write entry for my_output, got: %s" % list(write_entries.keys())


def test_saveAsTable_string_var_not_used_is_not_write_target(tmp_path):
    """String variable never used as saveAsTable arg → does NOT produce write entry."""
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src")
        unused_var = "not_a_write_target"
        df.write.saveAsTable("actual_output")
    """))
    result = schema_mine.synthesize(str(tmp_path))
    tables = result["entrypoints"][0]["tables"]
    assert "not_a_write_target" not in tables, \
        "Unexpected write entry for unused string var: %s" % list(tables.keys())


# ---------------------------------------------------------------------------
# Fix 4: spark.read.csv produces category:"file", relational:true
# ---------------------------------------------------------------------------

def test_csv_read_relational_and_category(tmp_path):
    """spark.read.csv() produces relational:True, category:'file' entry."""
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.csv("/data/input.csv")
        df.write.saveAsTable("output")
    """))
    result = schema_mine.synthesize(str(tmp_path))
    tables = result["entrypoints"][0]["tables"]
    # Find the read source with category "file" (the csv input)
    file_reads = {k: v for k, v in tables.items()
                  if v.get("category") == "file" and v.get("access") in ("read", "readwrite")}
    assert file_reads, \
        "Expected a category:'file' read entry for csv source, got: %s" % tables
    csv_entry = next(iter(file_reads.values()))
    assert csv_entry.get("relational") is True, csv_entry
    assert csv_entry.get("category") == "file", csv_entry


def test_csv_format_load_relational_and_category(tmp_path):
    """spark.read.format('csv').load() also produces relational:True, category:'file'."""
    (tmp_path / "job.py").write_text(textwrap.dedent("""
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.format("csv").load("/data/records.csv")
        df.write.saveAsTable("output")
    """))
    result = schema_mine.synthesize(str(tmp_path))
    tables = result["entrypoints"][0]["tables"]
    file_reads = {k: v for k, v in tables.items()
                  if v.get("category") == "file" and v.get("access") in ("read", "readwrite")}
    assert file_reads, \
        "Expected category:'file' entry for .format('csv').load(), got: %s" % tables
    entry = next(iter(file_reads.values()))
    assert entry.get("relational") is True, entry


# ---------------------------------------------------------------------------
# Feature C: isin() filter literal domain → column `values`
# ---------------------------------------------------------------------------

def _col_values(tmp_path, src, col_name, table_name="src_table"):
    """Helper: mine src snippet and return the `values` list for col_name."""
    (tmp_path / "job.py").write_text(textwrap.dedent(src))
    result = schema_mine.synthesize(str(tmp_path))
    tables = result["entrypoints"][0]["tables"]
    tbl = tables.get(table_name, {})
    for c in tbl.get("columns", []):
        if c["name"] == col_name:
            return c.get("values")
    return None


def test_isin_literal_values(tmp_path):
    """Positional and list-arg isin() populate column values; dynamic args stay empty."""
    for src, expected in (
        ("""
        from pyspark.sql import SparkSession
        from pyspark.sql.functions import col
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src_table")
        df2 = df.filter(col('code_cat_det').isin('610A', '610B', '610C'))
        df2.write.saveAsTable("out")
    """, ['610A', '610B', '610C']),
        ("""
        from pyspark.sql import SparkSession
        from pyspark.sql.functions import col
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src_table")
        df2 = df.filter(col('code_cat_det').isin(['610A', '610B', '610C']))
        df2.write.saveAsTable("out")
    """, ['610A', '610B', '610C']),
    ):
        vals = _col_values(tmp_path, src, "code_cat_det")
        assert vals == expected, vals

    dynamic_vals = _col_values(tmp_path, """
        from pyspark.sql import SparkSession
        from pyspark.sql.functions import col
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src_table")
        df2 = df.filter(col('code_cat_det').isin(get_dynamic_values()))
        df2.write.saveAsTable("out")
    """, "code_cat_det")
    assert not dynamic_vals, dynamic_vals


def test_isin_subscript_receiver_values(tmp_path):
    """df['col'].isin('a','b') (subscript receiver) populates column values list."""
    vals = _col_values(tmp_path, """
        from pyspark.sql import SparkSession
        spark = SparkSession.builder.getOrCreate()
        df = spark.read.table("src_table")
        df2 = df.filter(df['code_cat_det'].isin('610A', '610B', '610C'))
        df2.write.saveAsTable("out")
    """, "code_cat_det")
    assert vals == ['610A', '610B', '610C'], \
        "Expected ['610A','610B','610C'] but got: %r" % vals


def test_is_garbled_table_key():
    g = schema_mine._is_garbled_table_key
    # garbled: leading underscore, SQL fragments, whitespace, empty
    assert g("_select___from_dm_ops")
    assert g("select * from ods_ops")
    assert g("\nselect * from dm_ops")
    assert g("_raw")
    assert g("")
    assert g("   ")
    # clean identifiers are fine
    assert not g("dm_ops")
    assert not g("fz_dashboard_grading_t")
    assert not g("customer_from_region")   # 'from' substring but a valid name
    assert not g("select_options")         # 'select' substring but a valid name
    assert not g("select_from_options")    # both words as substrings — NOT garbled


def test_post_join_only_single_leg_column_attributed_to_neither(tmp_path):
    # Documented tradeoff of the post-join over-attribution fix: a genuine single-leg
    # column referenced ONLY after the join (never pre-join, not a join key) is
    # attributed to NEITHER source. The mock then lacks it and the workload hits a
    # recoverable COLUMN_NOT_FOUND (fix via schema repair, per the runner-doc routing)
    # rather than the 5004 ambiguity that over-attribution used to cause. This locks in
    # the tradeoff direction so it is an intentional, reviewed behavior.
    c = _mine(tmp_path, """
        left = spark.read.parquet("/data/left_tbl")
        right = spark.read.parquet("/data/right_tbl")
        joined = left.join(right, ["k"], "inner")
        out = joined.select("k", "left_only_col")
        out.write.parquet("/o")
    """)
    left_cols = _cols(c, "left_tbl")
    right_cols = _cols(c, "right_tbl")
    # left_only_col is native to `left` but referenced only post-join -> neither source
    assert "left_only_col" not in left_cols, c["_sources"]
    assert "left_only_col" not in right_cols, c["_sources"]
    # the join key is still attributed to both legs
    assert "k" in left_cols and "k" in right_cols, c["_sources"]


# --- read-detection coverage: patterns the miner used to miss entirely --------
# These pin the fixes for the Pilote_Flottes friction run, where reads assigned to
# subscript targets, built from `PREFIX + '.table'` concatenation, buried in inline
# join chains, or done via pandas were never mined and surfaced as runtime
# TABLE_OR_VIEW_NOT_FOUND / FileNotFound during Phase A/B.

def test_binop_concat_table_name(tmp_path):
    # spark.table(SCHEMA + '.my_table') -> the trailing literal segment is the table
    c = _mine(tmp_path, """
        df = spark.table(SCHEMA + ".my_table")
        df.write.saveAsTable("out.t")
    """)
    assert "my_table" in c["_sources"], c["_sources"]


def test_binop_concat_table_name_is_certain(tmp_path):
    # a spark.table BinOp name is an exact identity, not a path guess
    c = _mine(tmp_path, """
        df = spark.table(DB + ".SCHEMA." + "brokers")
        df.write.saveAsTable("out.t")
    """)
    # last operand is the literal '.brokers'/'brokers' -> name resolved
    assert "brokers" in c["_sources"], c["_sources"]
    assert c["_sources"]["brokers"].get("name_confidence") == "certain", \
        c["_sources"]["brokers"]


def test_subscript_target_read_detected(tmp_path):
    # dfMap['k'] = spark.table(...) — a read assigned to a subscript target was
    # skipped by visit_Assign (Name-target only); the visit_Call catch-all fixes it.
    c = _mine(tmp_path, """
        dfMap = {}
        dfMap["histo"] = spark.table("cat.b_i_histo_org")
        dfMap["histo"].write.saveAsTable("out.t")
    """)
    assert "b_i_histo_org" in c["_sources"], c["_sources"]


def test_subscript_target_with_binop_and_transform(tmp_path):
    # the exact Pilote gam_risk shape: dict target + PREFIX+'.tbl' + wrapping call/filter
    c = _mine(tmp_path, """
        dfGAM = {}
        dfGAM["histo_org"] = drop_null_columns(
            spark.table(_SCHEMA + ".b_i_entga_i_firc_rld_histo_org")
            .filter(col("num_contrat").isin(liste))
        )
        dfGAM["histo_org"].write.saveAsTable("out.t")
    """)
    assert "b_i_entga_i_firc_rld_histo_org" in c["_sources"], c["_sources"]


def test_inline_join_chain_all_legs_detected(tmp_path):
    # a.join(spark.table('b')).join(spark.table('c')): _detect_read returns only the
    # first read; the catch-all registers every additional inline read leg.
    c = _mine(tmp_path, """
        x = (spark.table("cat.aa")
             .join(spark.table("cat.bb"), "k")
             .join(spark.table("cat.cc"), "k"))
        x.write.saveAsTable("out.t")
    """)
    for name in ("aa", "bb", "cc"):
        assert name in c["_sources"], (name, sorted(c["_sources"]))


def test_pandas_read_csv_file_source(tmp_path):
    # pd.read_csv never touches spark.read; register it as a file source
    c = _mine(tmp_path, """
        import pandas as pd
        lk = pd.read_csv(path + "lookup_table.csv", sep=";")
    """)
    assert "lookup_table" in c["_sources"], c["_sources"]
    s = c["_sources"]["lookup_table"]
    assert s.get("reader_method") == "read_csv" and s.get("format") == "csv", s


def test_pandas_read_inside_createdataframe(tmp_path):
    # spark.createDataFrame(pd.read_csv(...)) — the nested pandas read is still mined
    c = _mine(tmp_path, """
        import pandas as pd
        df = spark.createDataFrame(pd.read_csv("dir/ref_data.csv"))
        df.write.saveAsTable("out.t")
    """)
    assert "ref_data" in c["_sources"], c["_sources"]


def test_read_not_double_registered(tmp_path):
    # a plain Name-target read must still produce exactly one source (visit_Assign
    # consumes it; the catch-all must skip it) — no duplicate / column loss.
    c = _mine(tmp_path, """
        df = spark.read.parquet("/data/customers")
        out = df.select("customer_id", "amount")
        out.write.parquet("/out/r")
    """)
    assert "customer_id" in _cols(c, "customers"), c["_sources"]
    assert {"customer_id", "amount"} <= _cols(c, "customers"), c["_sources"]


# --- review follow-ups: guard the widened read detection --------------------

def test_bare_table_on_non_spark_receiver_not_mined(tmp_path):
    # a non-Spark `.table(...)` (e.g. matplotlib Axes.table) must NOT register a
    # source now that the visit_Call catch-all runs on every `.table` call.
    c = _mine(tmp_path, """
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots()
        ax.table(cellText=[["a", "b"]], colLabels=["x", "y"])
        real = spark.table("cat.real_tbl")
        real.write.saveAsTable("out.t")
    """)
    assert "real_tbl" in c["_sources"], c["_sources"]
    # no spurious source from ax.table(...)
    assert "table" not in c["_sources"], c["_sources"]
    assert all("cellText" not in k for k in c["_sources"]), c["_sources"]


def test_session_like_receiver_table_still_mined(tmp_path):
    # a `.table` on a session-like receiver that is not literally `spark`
    # (sqlContext / a *session* var / a *spark-suffixed alias) is still a real read;
    # a loose substring like `sparkles` is NOT (guards against false positives).
    c = _mine(tmp_path, """
        df1 = sqlContext.table("cat.aa")
        df2 = my_session.table("cat.bb")
        df3 = myspark.table("cat.cc")
        sparkles.table("cat.zz")
        df1.write.saveAsTable("out.t")
        df2.write.saveAsTable("out.u")
        df3.write.saveAsTable("out.v")
    """)
    assert {"aa", "bb", "cc"} <= set(c["_sources"]), c["_sources"]
    assert "zz" not in c["_sources"], c["_sources"]


def test_binop_concat_prefers_last_var_operand(tmp_path):
    # spark.table(SCHEMA + '.' + tbl): the table identity is the LAST operand,
    # not the leading schema-prefix var.
    c = _mine(tmp_path, """
        SCHEMA = "prod_db"
        tbl = "my_table"
        df = spark.table(SCHEMA + "." + tbl)
        df.write.saveAsTable("out.t")
    """)
    assert "my_table" in c["_sources"], c["_sources"]
    assert "prod_db" not in c["_sources"], c["_sources"]


def test_pandas_read_table_and_excel_not_mined(tmp_path):
    # read_table (TAB-delimited) and read_excel (binary) are intentionally NOT
    # surfaced as mockable file sources — their downstream handling is unsafe.
    c = _mine(tmp_path, """
        import pandas as pd
        a = pd.read_table("dir/tab_data.tsv")
        b = pd.read_excel("dir/book.xlsx")
    """)
    assert "tab_data" not in c["_sources"], c["_sources"]
    assert "book" not in c["_sources"], c["_sources"]


def test_ipynb_sql_magic_tables_appear_in_lineage(tmp_path):
    """A %sql SELECT FROM some_tbl results in some_tbl appearing in mined sources."""
    _write_ipynb(tmp_path / "sql_nb.ipynb",
                 "%%sql\nSELECT order_id, amount FROM orders;\nINSERT INTO summary SELECT count(*) as cnt FROM orders;",
                 "df = spark.read.parquet('/data/extra')",
                 "df.write.parquet('/out/result')")
    c = schema_mine.mine(str(tmp_path / "sql_nb.ipynb"))
    # The %%sql cell translates to spark.sql("SELECT order_id, amount FROM orders")
    # etc.; the lineage layer should now see "orders" as a source table.
    source_names = set(c.get("_sources", {}).keys())
    assert any("order" in n.lower() for n in source_names), (
        f"Expected 'orders' in mined sources, got: {source_names}"
    )


def test_read_source_ipynb_fallback_neutralizes_cell_magic_body(monkeypatch, tmp_path):
    """When notebook_source can't be imported, the .ipynb fallback must still
    neutralize a %%sql cell's SQL body (not leak it as bare, unparseable text)."""
    import ast
    # Force the delegate to return "" so _read_source uses the inline fallback.
    monkeypatch.setattr(schema_mine, "_notebook_source_to_python", lambda p: "")
    nb = {"cells": [
        {"cell_type": "code", "source": ["%%sql\n", "SELECT a FROM t;\n", "SELECT b FROM u\n"]},
        {"cell_type": "code", "source": ["x = 1\n"]},
    ], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    p = tmp_path / "nb.ipynb"
    p.write_text(json.dumps(nb), encoding="utf-8")
    out = schema_mine._read_source(str(p))
    ast.parse(out)  # must be valid Python — the SQL body must not leak
    assert "SELECT a FROM t" not in out
    assert "x = 1" in out

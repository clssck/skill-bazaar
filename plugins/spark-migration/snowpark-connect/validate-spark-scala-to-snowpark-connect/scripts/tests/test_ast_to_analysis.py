"""Tests for ast_to_analysis.py."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SCRIPTS))

import ast_to_analysis as ata  # noqa: E402


def _write_ast(tmp_path: Path, files: list[dict]) -> None:
    shared = tmp_path / "Validation" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "ast_facts.json").write_text(json.dumps({
        "source": str(tmp_path / "Validation" / "source"),
        "file_count": len(files),
        "parse_errors": 0,
        "files": files,
    }), encoding="utf-8")


def _write_source(tmp_path: Path, rel: str, body: str = "") -> Path:
    src = tmp_path / "Validation" / "source" / rel
    src.parent.mkdir(parents=True, exist_ok=True)
    src.write_text(body or "object Main { def main(args: Array[String]): Unit = () }", encoding="utf-8")
    return src


def test_survey_builds_candidates(tmp_path):
    rel = "src/main/scala/Jobs.scala"
    src = _write_source(tmp_path, rel)
    _write_ast(tmp_path, [{
        "path": str(src),
        "parse_ok": True,
        "objects": ["Main"],
        "entrypoints": [{"owner": "Main", "method": "main"}],
        "reads": [{"call": "table", "args": ["ORDERS"]}],
        "writes": [],
        "table_refs": ["ORDERS"],
        "column_refs": ["order_id"],
        "write_helpers": [],
        "spark_session_created": True,
    }])
    result = ata.run(tmp_path, mode="survey")
    assert len(result["entrypoint_candidates"]) == 1
    assert result["entrypoint_candidates"][0]["id"] == "jobs"
    assert result["build_tool"] in {"sbt", "unknown"}


def test_deep_builds_sources_sinks_with_llm_todo(tmp_path):
    rel = "src/main/scala/Jobs.scala"
    src = _write_source(tmp_path, rel)
    shared = tmp_path / "Validation" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "analysis.json").write_text(json.dumps({
        "entrypoints": [{"id": "jobs", "path": rel}],
        "source_roots": ["src/main/scala"],
        "build_tool": "sbt",
    }), encoding="utf-8")
    _write_ast(tmp_path, [{
        "path": str(src),
        "parse_ok": True,
        "objects": ["Main"],
        "entrypoints": [{"owner": "Main", "method": "main"}],
        "reads": [{"call": "table", "args": ["DB.SCH.ORDERS"]}],
        "writes": [{"call": "saveAsTable", "args": ["DB.SCH.OUT"]}],
        "table_refs": ["DB.SCH.ORDERS", "DB.SCH.OUT"],
        "column_refs": ["order_id", "amount"],
        "write_helpers": ["writeOut"],
        "spark_session_created": True,
    }])
    result = ata.run(tmp_path, mode="deep")
    ep = result["entrypoints"][0]
    assert ep["external_sources"]
    assert ep["sinks"]
    assert result["external_sources"][0]["schema"]
    assert result["external_sources"][0].get("llm_todo")
    assert result["sinks"][0].get("natural_keys") == []
    assert result["complete"] is False
    assert result["llm_todos"]


# ── unresolved edge consumption (ScosAnalyze data-edge parity) ─────────────


def _write_ast_unresolved(tmp_path: Path, unresolved_reads, unresolved_writes) -> None:
    rel = "src/main/scala/Job.scala"
    src = _write_source(tmp_path, rel)
    shared = tmp_path / "Validation" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "analysis.json").write_text(json.dumps({
        "entrypoints": [{"id": "job", "path": rel}],
        "source_roots": ["src/main/scala"],
        "build_tool": "sbt",
    }), encoding="utf-8")
    _write_ast(tmp_path, [{
        "path": str(src),
        "parse_ok": True,
        "objects": ["Job"],
        "entrypoints": [{"owner": "Job", "method": "main"}],
        "reads": [],
        "writes": [],
        "unresolved_reads": unresolved_reads,
        "unresolved_writes": unresolved_writes,
        "table_refs": [],
        "column_refs": ["id"],
        "write_helpers": [],
        "spark_session_created": True,
    }])


def test_unresolved_read_creates_source_with_llm_todo(tmp_path):
    """An unresolved read (dynamic path) must create a source with a dynamic-path llm_todo."""
    _write_ast_unresolved(tmp_path, unresolved_reads=[
        {"call": "parquet", "arg_expr": "configPath", "line": 10},
    ], unresolved_writes=[])
    result = ata.run(tmp_path, mode="deep")
    sources = result.get("external_sources") or []
    assert sources, "expected at least one source from unresolved read"
    src = sources[0]
    assert "dynamic" in src["llm_todo"].lower() or "path" in src["llm_todo"].lower()
    assert "configPath" in src["llm_todo"] or "configPath" in src.get("original_path", "")
    assert src.get("reader_method") == "parquet"


def test_unresolved_write_creates_sink_with_llm_todo(tmp_path):
    """An unresolved write (dynamic target) must create a sink with an llm_todo."""
    _write_ast_unresolved(tmp_path, unresolved_reads=[], unresolved_writes=[
        {"call": "saveAsTable", "arg_expr": "outputTable", "line": 15},
    ])
    result = ata.run(tmp_path, mode="deep")
    sinks = result.get("sinks") or []
    assert sinks, "expected at least one sink from unresolved write"
    sink = sinks[0]
    assert sink.get("llm_todo") or sink.get("method") == "saveastable"


def test_resolved_and_unresolved_reads_together(tmp_path):
    """Mix of resolved + unresolved reads: all become sources, unresolved flagged."""
    rel = "src/main/scala/MixedJob.scala"
    src = _write_source(tmp_path, rel)
    shared = tmp_path / "Validation" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "analysis.json").write_text(json.dumps({
        "entrypoints": [{"id": "mixedjob", "path": rel}],
        "source_roots": ["src/main/scala"],
        "build_tool": "sbt",
    }), encoding="utf-8")
    _write_ast(tmp_path, [{
        "path": str(src),
        "parse_ok": True,
        "objects": ["MixedJob"],
        "entrypoints": [{"owner": "MixedJob", "method": "main"}],
        "reads": [{"call": "parquet", "args": ["s3://bucket/static.parquet"], "line": 5}],
        "writes": [{"call": "saveAsTable", "args": ["out_table"], "line": 20}],
        "unresolved_reads": [
            {"call": "csv", "arg_expr": "dynamicCsvPath", "line": 8},
        ],
        "unresolved_writes": [],
        "table_refs": [],
        "column_refs": ["id", "value"],
        "write_helpers": [],
        "spark_session_created": True,
    }])
    result = ata.run(tmp_path, mode="deep")
    sources = result.get("external_sources") or []
    # Should have both the static read AND the unresolved one
    assert len(sources) == 2, f"expected 2 sources (static + unresolved), got {len(sources)}"
    methods = {s["reader_method"] for s in sources}
    assert "parquet" in methods
    assert "csv" in methods
    # The unresolved one must have a dynamic-path llm_todo
    unresolved_src = next(s for s in sources if s["reader_method"] == "csv")
    assert "dynamic" in unresolved_src.get("llm_todo", "").lower() or \
           "path" in unresolved_src.get("llm_todo", "").lower()


def test_unresolved_edges_deduplication(tmp_path):
    """Duplicate unresolved reads (same call+arg_expr) must be deduplicated."""
    _write_ast_unresolved(tmp_path, unresolved_reads=[
        {"call": "parquet", "arg_expr": "samePath", "line": 5},
        {"call": "parquet", "arg_expr": "samePath", "line": 5},  # duplicate
    ], unresolved_writes=[])
    result = ata.run(tmp_path, mode="deep")
    sources = result.get("external_sources") or []
    assert len(sources) == 1, "duplicate unresolved reads must be deduplicated"


def test_line_field_on_resolved_read(tmp_path):
    """Reads now carry a line field; ast_to_analysis must not break when it's present."""
    rel = "src/main/scala/LineJob.scala"
    src = _write_source(tmp_path, rel)
    shared = tmp_path / "Validation" / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    (shared / "analysis.json").write_text(json.dumps({
        "entrypoints": [{"id": "linejob", "path": rel}],
        "source_roots": ["src/main/scala"],
        "build_tool": "sbt",
    }), encoding="utf-8")
    _write_ast(tmp_path, [{
        "path": str(src),
        "parse_ok": True,
        "objects": ["LineJob"],
        "entrypoints": [{"owner": "LineJob", "method": "main"}],
        "reads": [{"call": "parquet", "args": ["s3://b/f.parquet"], "line": 42}],
        "writes": [],
        "unresolved_reads": [],
        "unresolved_writes": [],
        "table_refs": [],
        "column_refs": ["id"],
        "write_helpers": [],
        "spark_session_created": True,
    }])
    result = ata.run(tmp_path, mode="deep")
    sources = result.get("external_sources") or []
    assert sources, "source should be created for read with line field"
    assert sources[0]["reader_method"] == "parquet"

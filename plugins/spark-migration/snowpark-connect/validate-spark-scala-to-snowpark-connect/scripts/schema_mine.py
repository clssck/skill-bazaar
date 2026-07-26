#!/usr/bin/env python3
"""Scala schema-mining: analysis.json -> the PySpark ``schemas/`` layout.

This is the Scala validator's analog of the PySpark validator's ``schema_mine.py``.
Where the PySpark miner reads Python source and emits ``schemas/``, this reads the
Scalameta analyzer's ``analysis.json`` (entrypoints + external_sources + sinks +
intermediate_tables, with ``$ref`` into ``schemas.json``) and emits the SAME
``Validation/shared/schemas/`` layout (``manifest.json`` + ``entrypoints/<id>.json``
with a ``tables{}`` map).

Downstream, the *unchanged* canonical PySpark scripts consume ``schemas/``:
  - ``datagen.py schemas/ mock_data``           -> typed mocks
  - ``scos_state.py provision --conv-root ...`` -> golden Snowflake schemas

Mapping:
  external_sources -> read tables (mock_file + COPY; non-tabular -> staged file)
  sinks            -> empty write tables (DML lands here)
  intermediate_tables -> empty write tables in each reader/writer entrypoint

Type inference (Fix #3):
  When a column has type ``string`` (the default produced by the LLM analyzer),
  ``schema_mine.py`` consults two sources of evidence:
  1. ``Validation/shared/ast_facts.json`` (from ``scos-analyze.jar``): column names
     referenced across all Scala source files.  Not expression-aware, but good for
     name-based heuristics.
  2. Column name suffix/pattern rules (see ``_infer_type_from_name``).

  Only ``string`` columns are upgraded — columns already typed by the LLM
  (``integer``, ``double``, ``date``, etc.) are never downgraded.

NOTE: ``seed_strategy=from_source_join`` ``seed_sql`` is NOT applied here (the
default provisioner has no server-side seed step); such intermediates are created
empty. The Phase A vs Phase B comparison stays valid, just less data-exercising
for that table.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_TABLE_UNSAFE_RE = re.compile(r'[/\\:*?"<>|\s]')

# ---------------------------------------------------------------------------
# Dynamic class-load site detection (opt-in: detect_dynamic_imports=True)
# Scala parity for PySpark schema_mine._find_dynamic_import_sites.
# Detects Class.forName / classLoader.loadClass patterns where the class name
# traces back to a config subscript, surfacing config-driven pipeline dispatch.
# Uses a lightweight regex scan of .scala source files (no Python ast access to
# JVM code; Scalameta ast_facts does not include general method calls).
# ---------------------------------------------------------------------------
_FORNAME_RE = re.compile(
    r'(?:Class\.forName|classLoader\.loadClass|loadClass)\s*\(\s*'
    r'(?P<expr>[^)]{1,120})\)',
)
_CONFIG_KEY_RE = re.compile(r'(?:\.get)?\("([^"]{1,60})"\)')


def _find_dynamic_class_loads(source_root: Path) -> list[dict]:
    """Scan *.scala / *.sc files for Class.forName(config(\"KEY\")) patterns.

    Returns list of {file, line, kind, config_key, raw_expr}.
    """
    sites: list[dict] = []
    for p in sorted(source_root.rglob("*.scala")) + sorted(source_root.rglob("*.sc")):
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = _FORNAME_RE.search(line)
            if not m:
                continue
            expr = m.group("expr").strip()
            key_m = _CONFIG_KEY_RE.search(expr)
            sites.append({
                "file": str(p.relative_to(source_root)),
                "line": i,
                "kind": "class_forname",
                "config_key": key_m.group(1) if key_m else None,
                "raw_expr": expr,
            })
    return sites

# ---------------------------------------------------------------------------
# Type inference from column name (Fix #3)
# Applied only when the column type is "string" (LLM default / unknown).
# Rules are ordered: first match wins.  Patterns are case-insensitive suffix/
# full-name checks so they're cheap and safe for goldset workloads.
# ---------------------------------------------------------------------------

_TYPE_SUFFIX_RULES: list = [
    # Timestamps / dates
    (re.compile(r"_ts$|_timestamp$|_at$|_time$", re.I), "timestamp"),
    (re.compile(r"_date$|_dt$|_day$", re.I), "date"),
    # Numeric IDs that are commonly longs in JVM-land
    (re.compile(r"_id$", re.I), "long"),
    # Rank / row-number window columns
    (re.compile(r"^rn$|^rank$|^row_num(ber)?$|^seq$|^sequence$", re.I), "long"),
    # Counts
    (re.compile(r"^count$|_count$|_cnt$|^num_|_num$", re.I), "long"),
    # Monetary / scored quantities
    (re.compile(r"_amount$|_amt$|_price$|_cost$|_revenue$|_total$|_value$", re.I), "double"),
    # Scores / ratios / rates
    (re.compile(r"_score$|_rate$|_ratio$|_pct$|_percent$|_fraction$", re.I), "double"),
    # Physical measurements (temperature in Celsius, distances, weights)
    (re.compile(r"_c$|_f$|_k$|_celsius$|_fahrenheit$", re.I), "double"),
    (re.compile(r"_deg$|_degrees$|_km$|_miles$|_meters?$|_kg$|_lbs?$", re.I), "double"),
    # Duration / intervals
    (re.compile(r"_minutes?$|_seconds?$|_hours?$|_days?$|_duration$|_elapsed$", re.I), "double"),
    # Penalties / corrections (often float arithmetic)
    (re.compile(r"_penalty$|_adjustment$|_correction$|_delta$|_diff$", re.I), "double"),
    # Latitude / longitude
    (re.compile(r"_lat$|_lon$|_lng$|latitude$|longitude$", re.I), "double"),
    # Flags / indicators (boolean)
    (re.compile(r"^is_|^has_|^flag_|_flag$|_indicator$|_enabled$|_active$", re.I), "boolean"),
    # Zones / numbers that are clearly integer (zone_num, zone_span)
    (re.compile(r"_num$|_number$|_zone$|_level$|_tier$", re.I), "long"),
]

_STRING_TYPES = {"string", "varchar", "text", "str"}


def _infer_type_from_name(col_name: str) -> str | None:
    """Return a Spark type hint for *col_name* based on suffix/pattern rules.

    Returns ``None`` when no pattern matches (caller keeps the existing type).
    Only applied when the existing column type is in ``_STRING_TYPES``.
    """
    for pattern, inferred_type in _TYPE_SUFFIX_RULES:
        if pattern.search(col_name):
            return inferred_type
    return None


def _upgrade_columns(columns: list, ast_col_names: set) -> list:
    """Apply type inference to a column list.

    ``ast_col_names`` is the union of all column_refs across ast_facts.json —
    used only to confirm the column appears in actual source code (avoids
    upgrading phantom columns that were hallucinated by the LLM analyzer).
    When ast_facts is absent, ``ast_col_names`` is empty and the check is skipped.
    """
    out = []
    for col in columns:
        if not isinstance(col, dict):
            out.append(col)
            continue
        col_type = (col.get("type") or "string").lower()
        if col_type in _STRING_TYPES:
            name = col.get("name") or col.get("column") or ""
            # Only upgrade if the column appears in AST facts (or facts absent)
            if not ast_col_names or name.lower() in ast_col_names:
                inferred = _infer_type_from_name(name)
                if inferred:
                    col = {**col, "type": inferred}
        out.append(col)
    return out


def _load_ast_col_names(conv_root: Path) -> set:
    """Return a lowercased set of all column_refs from ast_facts.json, or empty set."""
    ast_path = conv_root / "Validation" / "shared" / "ast_facts.json"
    if not ast_path.is_file():
        return set()
    try:
        facts = json.loads(ast_path.read_text(encoding="utf-8"))
        names: set = set()
        for f in facts.get("files") or []:
            for col in f.get("column_refs") or []:
                if isinstance(col, str):
                    names.add(col.lower())
        return names
    except (ValueError, OSError):
        return set()


def _table_filename(key: str, used: set) -> str:
    """Return a filesystem-safe filename stem for a table key, unique within *used*."""
    safe = _TABLE_UNSAFE_RE.sub("_", key)
    if not safe:
        safe = "_table"
    candidate = safe
    suffix = 2
    while candidate in used:
        candidate = f"{safe}_{suffix}"
        suffix += 1
    used.add(candidate)
    return candidate


def _die(code: int, msg: str) -> None:
    print(f"[schema_mine.py] error: {msg}", file=sys.stderr)
    sys.exit(code)


def _bare_table_name(raw: str) -> str:
    """Last dotted segment, sans quotes (mirrors provision._bare_table_name)."""
    if not raw:
        return ""
    name = str(raw).strip().strip('"').strip("`")
    if "." in name:
        name = name.split(".")[-1]
    return name.strip().strip('"').strip("`")


def _resolve_schema(schema_field, schemas_cache: dict):
    """Resolve an analysis schema field to a column list.

    Handles inline ``[{name,type,...}]``; ``{"$ref": "schemas.json#/external_sources/<k>"}``;
    and bare string keys into schemas.json's ``external_sources``.
    """
    if isinstance(schema_field, list):
        return schema_field
    if isinstance(schema_field, dict) and "$ref" in schema_field:
        ref = schema_field["$ref"]
        if isinstance(ref, str) and ref.startswith("schemas.json#/"):
            node: object = schemas_cache
            for seg in ref[len("schemas.json#/"):].split("/"):
                if isinstance(node, dict):
                    node = node.get(seg)
            if isinstance(node, list):
                return node
    if isinstance(schema_field, str):
        node = (schemas_cache.get("external_sources") or {}).get(schema_field)
        if isinstance(node, list):
            return node
    return []


def _resolve_catalog(items, catalog: dict):
    """Expand string-id references against a top-level catalog; pass dicts through."""
    out = []
    for it in items or []:
        if isinstance(it, str):
            if it in catalog:
                out.append(catalog[it])
        elif isinstance(it, dict):
            out.append(it)
    return out


def _table_entry(obj, access, columns):
    raw = next((obj.get(k) for k in ("original_path", "original_target", "name", "id")
                if obj.get(k)), "")
    key = _bare_table_name(raw) or str(obj.get("id") or obj.get("name") or "tbl")
    entry: dict = {
        "access": access,
        "category": obj.get("category", "table"),
        "relational": True,
        "columns": columns,
        "reader_options": obj.get("reader_options") or {},
        "original_path": raw or str(obj.get("id") or obj.get("name") or key),
    }
    # For relational read tables: always set the canonical datagen mock_file name so
    # provision (which reads schemas/ from disk via load_entrypoint) finds the file that
    # datagen actually generates.  datagen's _materialize_fmt + _ext_for logic:
    #   - category "file": ext follows source_format (csv→csv, json→json, text→txt, else parquet)
    #   - category "table"/"connector": always parquet (regardless of format field)
    # datagen's _canon: bare lowercased table name — must match key.lower().
    if access == "read":
        _category = obj.get("category", "table")
        _fmt = (obj.get("format") or "").lower()
        if _category == "file":
            if _fmt in ("csv", "tsv"):
                _ext = "csv"
            elif _fmt in ("json", "jsonl", "ndjson"):
                _ext = "json"
            elif _fmt == "text":
                _ext = "txt"
            elif _fmt == "avro":
                _ext = "avro"
            else:
                _ext = "parquet"
        else:
            _ext = "parquet"
        entry["mock_file"] = f"{key.lower()}.{_ext}"
    return key, entry


def analysis_to_schemas(conv_root: Path, detect_dynamic_imports: bool = False) -> dict:
    """Convert analysis.json -> Validation/shared/schemas/. Returns a small summary."""
    shared = conv_root / "Validation" / "shared"
    analysis_path = shared / "analysis.json"
    if not analysis_path.is_file():
        _die(2, f"analysis.json not found: {analysis_path}")
    analysis = json.loads(analysis_path.read_text(encoding="utf-8"))

    schemas_json = shared / "schemas.json"
    schemas_cache: dict = {}
    if schemas_json.is_file():
        try:
            schemas_cache = json.loads(schemas_json.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            schemas_cache = {}

    # Load AST column names for type-inference cross-check (Fix #3).
    # If ast_facts.json is absent the set is empty and _upgrade_columns applies
    # name-based rules unconditionally (still safe — only upgrades "string").
    ast_col_names = _load_ast_col_names(conv_root)

    def _resolve_typed(schema_field) -> list:
        """Resolve schema field and upgrade string-typed columns from name heuristics."""
        return _upgrade_columns(_resolve_schema(schema_field, schemas_cache), ast_col_names)

    src_catalog = {s["id"]: s for s in (analysis.get("external_sources") or [])
                   if isinstance(s, dict) and s.get("id")}
    sink_catalog = {s["id"]: s for s in (analysis.get("sinks") or [])
                    if isinstance(s, dict) and s.get("id")}

    entrypoints = analysis.get("entrypoints", []) or []
    ep_ids = [ep.get("id") for ep in entrypoints if ep.get("id")]
    ep_out: list = []

    for ep in entrypoints:
        ep_id = ep.get("id")
        if not ep_id:
            continue
        tables: dict = {}
        for src in _resolve_catalog(ep.get("external_sources"), src_catalog):
            cols = _resolve_typed(src.get("schema"))
            if cols:
                k, v = _table_entry(src, "read", cols)
                tables[k] = v
            elif src.get("mock_file"):  # non-tabular document/file -> stage only
                raw = src.get("original_path") or src.get("name") or src.get("id") or "doc"
                tables[str(src.get("id") or src.get("name") or raw)] = {
                    "access": "read", "category": src.get("category", "file"),
                    "relational": False, "mock_file": src.get("mock_file"),
                    "columns": [], "reader_options": src.get("reader_options") or {},
                    "original_path": raw,
                }
        for sink in _resolve_catalog(ep.get("sinks"), sink_catalog):
            if sink.get("kind") not in (None, "table"):
                continue
            cols = _resolve_typed(sink.get("schema"))
            if cols:
                k, v = _table_entry(sink, "write", cols)
                tables[k] = v
        ep_entry: dict = {
            "id": ep_id,
            "path": ep.get("path", ep_id),
            "run_mode": ep.get("run_mode", "script"),
            "import_roots": ep.get("import_roots", ["src/main/scala"]),
            "entrypoint_kwargs": ep.get("entrypoint_kwargs", {}),
            "tables": tables,
        }
        # pass through optional harness fields when present
        for _opt in ("entrypoint_callable", "cli_args", "source_runtime"):
            if ep.get(_opt) is not None:
                ep_entry[_opt] = ep[_opt]
        ep_out.append(ep_entry)

    # intermediate_tables -> empty write tables in each reader/writer entrypoint
    for entry in (analysis.get("intermediate_tables") or []):
        cols = _resolve_typed(entry.get("schema"))
        name = entry.get("name", "")
        if not cols or not name:
            continue
        tname = _bare_table_name(name) or name.lower().replace(".", "_")
        targets = [e for e in ((entry.get("reader_entrypoint_ids") or [])
                               + (entry.get("consumer_entrypoint_ids") or [])
                               + [entry.get("writer_entrypoint_id")]) if e in ep_ids]
        if not targets:
            targets = ep_ids
        for epd in ep_out:
            if epd["id"] in targets:
                epd["tables"].setdefault(tname, {
                    "access": "write", "category": "table", "relational": True,
                    "columns": cols, "reader_options": {},
                    "original_path": name,
                })

    schemas_dir = shared / "schemas"
    schemas_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "root": analysis.get("root"),
        "complete": True,
        "summary": {},
        "expected_divergences": analysis.get("expected_divergences") or {},
        "entrypoints": [{"id": e["id"], "path": e["path"],
                         "dir": f"entrypoints/{e['id']}"} for e in ep_out],
    }
    (schemas_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    total_tables = 0
    for e in ep_out:
        ep_dir = schemas_dir / "entrypoints" / e["id"]
        (ep_dir / "tables").mkdir(parents=True, exist_ok=True)
        tables = e.pop("tables")
        total_tables += len(tables)
        used: set = set()
        for k, v in tables.items():
            entry = dict(v)
            entry["_table_key"] = k
            (ep_dir / "tables" / f"{_table_filename(k, used)}.json").write_text(
                json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")
        (ep_dir / "_meta.json").write_text(
            json.dumps(e, indent=2, default=str) + "\n", encoding="utf-8")
    ast_hint = f" (ast_facts: {len(ast_col_names)} col names)" if ast_col_names else ""

    dynamic_loads: list[dict] = []
    if detect_dynamic_imports:
        source_root = conv_root / "Validation" / "source"
        if source_root.is_dir():
            dynamic_loads = _find_dynamic_class_loads(source_root)
        if dynamic_loads:
            (schemas_dir / "dynamic_class_loads.json").write_text(
                json.dumps(dynamic_loads, indent=2) + "\n", encoding="utf-8")

    return {"entrypoints": len(ep_out),
            "tables": total_tables,
            "schemas_dir": str(schemas_dir),
            "ast_hint": ast_hint,
            "dynamic_class_loads": len(dynamic_loads)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="schema_mine.py",
        description="Scala: convert analysis.json into the PySpark schemas/ layout.")
    ap.add_argument("--conv-root", required=True,
                    help="Conversion root containing Validation/")
    args = ap.parse_args(argv)
    res = analysis_to_schemas(Path(args.conv_root).expanduser().resolve())
    print(f"[schema_mine.py] wrote schemas/ for {res['entrypoints']} entrypoint(s), "
          f"{res['tables']} table(s) -> {res['schemas_dir']}{res.get('ast_hint', '')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

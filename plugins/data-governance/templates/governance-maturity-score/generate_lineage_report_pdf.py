"""Governance maturity score lineage report (PDF).

Builds a *direct-only* lineage graph for:
- data-governance skill router -> governance-maturity-score workflow
- workflow -> referenced templates/scripts
- templates/scripts -> referenced Snowflake objects/functions

Outputs:
- A PDF with a swimlane, top-to-bottom DAG + inventory tables.

This script is intentionally self-contained so it can be run via `uvx` without
adding dependencies to the repo Python environment.

Example:
  uvx --with reportlab python generate_lineage_report_pdf.py \
    --repo-root /abs/path/to/cortex-code-skills \
    --out ~/governance_maturity_score_lineage.pdf
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import argparse
import json
import os
import re
from typing import Iterable

from reportlab.lib.pagesizes import letter
from reportlab.lib.colors import HexColor, white
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    HRFlowable,
    Flowable,
    PageBreak,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT


# ----------------------------
# Model
# ----------------------------


@dataclass(frozen=True)
class Evidence:
    file: str  # repo-relative
    line: int
    snippet: str


@dataclass(frozen=True)
class Node:
    node_id: str
    label: str
    kind: str  # SKILL | WORKFLOW | TEMPLATE | SCRIPT | VIEW | FUNCTION | SHOW_TARGET | IMPLIED_VIEW | SUBSKILL
    lane: str  # Skills | Workflow | Repo assets | Snowflake
    evidence: Evidence | None = None


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str  # routes_to | references | queries | calls | shows | implies
    evidence: Evidence


# ----------------------------
# Parsing helpers
# ----------------------------


_SNOWFLAKE_FQN_RE = re.compile(r"\bSNOWFLAKE\.[A-Z0-9_]+\.[A-Z0-9_]+\b")
_SYSTEM_FN_RE = re.compile(r"\bSYSTEM\$[A-Z0-9_]+\b")
_GENERIC_FN_RE = re.compile(r"\bIS_ROLE_IN_SESSION\b")


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def _find_first_match_line(lines: list[str], pattern: re.Pattern[str]) -> int | None:
    for i, line in enumerate(lines, start=1):
        if pattern.search(line):
            return i
    return None


def _all_matches_with_lines(lines: list[str], pattern: re.Pattern[str]) -> list[tuple[str, int, str]]:
    out: list[tuple[str, int, str]] = []
    for i, line in enumerate(lines, start=1):
        for m in pattern.finditer(line.upper()):
            out.append((m.group(0), i, line.strip()))
    return out


def _rel(repo_root: Path, p: Path) -> str:
    return str(p.resolve().relative_to(repo_root.resolve()))


def _mk_node_id(prefix: str, value: str) -> str:
    safe = re.sub(r"[^a-zA-Z0-9_\-]+", "_", value)
    return f"{prefix}:{safe}"


# ----------------------------
# Graph extraction (direct-only)
# ----------------------------


@dataclass
class Graph:
    nodes: dict[str, Node]
    edges: list[Edge]

    def add_node(self, node: Node) -> None:
        self.nodes.setdefault(node.node_id, node)

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)


def build_graph(repo_root: Path) -> Graph:
    g = Graph(nodes={}, edges=[])

    skill_file = repo_root / "data-governance" / "data-governance" / "SKILL.md"
    workflow_file = (
        repo_root
        / "data-governance"
        / "data-governance"
        / "workflows"
        / "governance-maturity-score.md"
    )

    tpl_dir = (
        repo_root
        / "data-governance"
        / "data-governance"
        / "templates"
        / "governance-maturity-score"
    )

    template_files = [
        tpl_dir / "check-popular-databases.sql",
        tpl_dir / "check-classification-status.sql",
        tpl_dir / "check-masking-policies.sql",
        tpl_dir / "check-access-history-usage.sql",
    ]
    pdf_script = tpl_dir / "generate_report_pdf.py"

    # --- Nodes: skill + workflow ---
    skill_lines = _read_lines(skill_file)
    wf_lines = _read_lines(workflow_file)

    skill_node = Node(
        node_id=_mk_node_id("skill", "data-governance"),
        label="data-governance (skill)",
        kind="SKILL",
        lane="Skills",
        evidence=Evidence(_rel(repo_root, skill_file), 2, skill_lines[1].strip()),
    )
    g.add_node(skill_node)

    wf_node = Node(
        node_id=_mk_node_id("workflow", "governance-maturity-score"),
        label="governance-maturity-score.md (workflow)",
        kind="WORKFLOW",
        lane="Workflow",
        evidence=Evidence(_rel(repo_root, workflow_file), 2, wf_lines[1].strip()),
    )
    g.add_node(wf_node)

    # Edge: router -> workflow (evidence where the router references it)
    route_line = _find_first_match_line(
        skill_lines, re.compile(r"workflows/governance-maturity-score\.md", re.IGNORECASE)
    )
    if route_line is None:
        route_line = 1
    g.add_edge(
        Edge(
            src=skill_node.node_id,
            dst=wf_node.node_id,
            kind="routes_to",
            evidence=Evidence(
                _rel(repo_root, skill_file),
                route_line,
                skill_lines[route_line - 1].strip() if route_line - 1 < len(skill_lines) else "",
            ),
        )
    )

    # --- Nodes: templates + script ---
    for tf in template_files:
        lines = _read_lines(tf)
        g.add_node(
            Node(
                node_id=_mk_node_id("template", tf.name),
                label=tf.name,
                kind="TEMPLATE",
                lane="Repo assets",
                evidence=Evidence(_rel(repo_root, tf), 1, (lines[0].strip() if lines else "")),
            )
        )

        # Edge: workflow -> template (evidence is link in workflow markdown)
        link_re = re.compile(re.escape(tf.name), re.IGNORECASE)
        link_line = _find_first_match_line(wf_lines, link_re) or 1
        g.add_edge(
            Edge(
                src=wf_node.node_id,
                dst=_mk_node_id("template", tf.name),
                kind="references",
                evidence=Evidence(
                    _rel(repo_root, workflow_file),
                    link_line,
                    wf_lines[link_line - 1].strip() if link_line - 1 < len(wf_lines) else "",
                ),
            )
        )

    # PDF generator script is also referenced in the workflow
    pdf_lines = _read_lines(pdf_script)
    pdf_node = Node(
        node_id=_mk_node_id("script", pdf_script.name),
        label=pdf_script.name,
        kind="SCRIPT",
        lane="Repo assets",
        evidence=Evidence(_rel(repo_root, pdf_script), 1, (pdf_lines[0].strip() if pdf_lines else "")),
    )
    g.add_node(pdf_node)

    pdf_link_line = _find_first_match_line(wf_lines, re.compile(re.escape(pdf_script.name), re.IGNORECASE)) or 1
    g.add_edge(
        Edge(
            src=wf_node.node_id,
            dst=pdf_node.node_id,
            kind="references",
            evidence=Evidence(
                _rel(repo_root, workflow_file),
                pdf_link_line,
                wf_lines[pdf_link_line - 1].strip() if pdf_link_line - 1 < len(wf_lines) else "",
            ),
        )
    )

    # --- Nodes: mentioned sub-skills (direct-only, no expansion) ---
    for name, needle in [
        ("data-policy", "workflows/data-policy.md"),
        ("sensitive-data-classification", "workflows/sensitive-data-classification.md"),
        ("horizon-catalog", "workflows/horizon-catalog.md"),
    ]:
        ln = _find_first_match_line(wf_lines, re.compile(re.escape(needle), re.IGNORECASE))
        if ln:
            sub_id = _mk_node_id("subskill", name)
            g.add_node(
                Node(
                    node_id=sub_id,
                    label=f"{name} (sub-skill, not expanded)",
                    kind="SUBSKILL",
                    lane="Skills",
                    evidence=Evidence(_rel(repo_root, workflow_file), ln, wf_lines[ln - 1].strip()),
                )
            )
            g.add_edge(
                Edge(
                    src=wf_node.node_id,
                    dst=sub_id,
                    kind="references",
                    evidence=Evidence(_rel(repo_root, workflow_file), ln, wf_lines[ln - 1].strip()),
                )
            )

    # --- Snowflake dependencies from templates ---
    def add_sf_node(kind: str, label: str, evidence: Evidence) -> str:
        node_id = _mk_node_id("sf", label)
        g.add_node(
            Node(
                node_id=node_id,
                label=label,
                kind=kind,
                lane="Snowflake",
                evidence=evidence,
            )
        )
        return node_id

    for tf in template_files:
        lines = _read_lines(tf)
        relf = _rel(repo_root, tf)

        for obj, ln, snippet in _all_matches_with_lines(lines, _SNOWFLAKE_FQN_RE):
            sf_kind = "VIEW"  # conservative default for ACCOUNT_USAGE references
            sf_id = add_sf_node(sf_kind, obj, Evidence(relf, ln, snippet))
            g.add_edge(
                Edge(
                    src=_mk_node_id("template", tf.name),
                    dst=sf_id,
                    kind="queries",
                    evidence=Evidence(relf, ln, snippet),
                )
            )

        for fn, ln, snippet in _all_matches_with_lines(lines, _SYSTEM_FN_RE):
            sf_id = add_sf_node("FUNCTION", fn, Evidence(relf, ln, snippet))
            g.add_edge(
                Edge(
                    src=_mk_node_id("template", tf.name),
                    dst=sf_id,
                    kind="calls",
                    evidence=Evidence(relf, ln, snippet),
                )
            )

        # Special-case: SHOW targets (present in classification-status.sql)
        show_ln = _find_first_match_line(lines, re.compile(r"SHOW\s+SNOWFLAKE\.DATA_PRIVACY\.CLASSIFICATION_PROFILE", re.IGNORECASE))
        if show_ln:
            show_label = "SNOWFLAKE.DATA_PRIVACY.CLASSIFICATION_PROFILE"
            sf_id = add_sf_node("SHOW_TARGET", show_label, Evidence(relf, show_ln, lines[show_ln - 1].strip()))
            g.add_edge(
                Edge(
                    src=_mk_node_id("template", tf.name),
                    dst=sf_id,
                    kind="shows",
                    evidence=Evidence(relf, show_ln, lines[show_ln - 1].strip()),
                )
            )

        # Special-case: implied ACCESS_HISTORY (access-history-usage.sql searches for it)
        if tf.name == "check-access-history-usage.sql":
            implied_ln = _find_first_match_line(lines, re.compile(r"ACCESS_HISTORY", re.IGNORECASE))
            if implied_ln:
                implied = "SNOWFLAKE.ACCOUNT_USAGE.ACCESS_HISTORY"
                sf_id = add_sf_node("IMPLIED_VIEW", implied, Evidence(relf, implied_ln, lines[implied_ln - 1].strip()))
                g.add_edge(
                    Edge(
                        src=_mk_node_id("template", tf.name),
                        dst=sf_id,
                        kind="implies",
                        evidence=Evidence(relf, implied_ln, lines[implied_ln - 1].strip()),
                    )
                )

    # --- Snowflake function dependency from workflow markdown (IS_ROLE_IN_SESSION) ---
    fn_ln = _find_first_match_line(wf_lines, _GENERIC_FN_RE)
    if fn_ln:
        sf_id = add_sf_node(
            "FUNCTION",
            "IS_ROLE_IN_SESSION",
            Evidence(_rel(repo_root, workflow_file), fn_ln, wf_lines[fn_ln - 1].strip()),
        )
        g.add_edge(
            Edge(
                src=wf_node.node_id,
                dst=sf_id,
                kind="calls",
                evidence=Evidence(_rel(repo_root, workflow_file), fn_ln, wf_lines[fn_ln - 1].strip()),
            )
        )

    return g


# ----------------------------
# PDF rendering
# ----------------------------


class SwimlaneDag(Flowable):
    def __init__(self, graph: Graph, width: float, height: float):
        super().__init__()
        self.graph = graph
        self.width = width
        self.height = height

    def draw(self):
        c = self.canv
        x0, y0 = 0, 0
        w, h = self.width, self.height

        lane_names = ["Skills", "Workflow", "Repo assets", "Snowflake"]
        lane_w = w / len(lane_names)

        # Colors
        lane_bg = HexColor("#F7FAFC")
        lane_border = HexColor("#D0D7DE")
        title_bg = HexColor("#1A3A5C")
        title_fg = white
        box_border = HexColor("#11567F")
        box_fill = HexColor("#E3F2FD")
        box_fill_alt = HexColor("#FFF8E1")
        implied_border = HexColor("#E65100")

        # Lane backgrounds + headers
        header_h = 20
        for idx, lane in enumerate(lane_names):
            lx = x0 + idx * lane_w
            c.setFillColor(lane_bg)
            c.setStrokeColor(lane_border)
            c.rect(lx, y0, lane_w, h, fill=1, stroke=1)
            c.setFillColor(title_bg)
            c.rect(lx, y0 + h - header_h, lane_w, header_h, fill=1, stroke=0)
            c.setFillColor(title_fg)
            c.setFont("Helvetica-Bold", 9)
            c.drawCentredString(lx + lane_w / 2, y0 + h - header_h + 6, lane)

        # Group nodes by lane
        by_lane: dict[str, list[Node]] = {k: [] for k in lane_names}
        for n in self.graph.nodes.values():
            if n.lane in by_lane:
                by_lane[n.lane].append(n)

        # Stable ordering within each lane
        def sort_key(n: Node) -> tuple[int, str]:
            pri = {
                "SKILL": 0,
                "SUBSKILL": 1,
                "WORKFLOW": 0,
                "TEMPLATE": 0,
                "SCRIPT": 1,
                "SHOW_TARGET": 0,
                "VIEW": 1,
                "IMPLIED_VIEW": 2,
                "FUNCTION": 3,
            }.get(n.kind, 9)
            return (pri, n.label)

        for lane in lane_names:
            by_lane[lane].sort(key=sort_key)

        # Node layout
        box_h = 34
        v_gap = 12
        box_w = lane_w - 18
        node_pos: dict[str, tuple[float, float, float, float]] = {}

        for idx, lane in enumerate(lane_names):
            lx = x0 + idx * lane_w
            top_y = y0 + h - header_h - 10
            cur_y = top_y
            for n in by_lane[lane]:
                cur_y -= box_h
                bx = lx + 9
                by = cur_y

                # style
                if n.kind in ("SCRIPT", "FUNCTION"):
                    fill = box_fill_alt
                else:
                    fill = box_fill

                c.setFillColor(fill)
                c.setStrokeColor(implied_border if n.kind == "IMPLIED_VIEW" else box_border)
                if n.kind == "IMPLIED_VIEW":
                    c.setDash(3, 2)
                else:
                    c.setDash()
                c.roundRect(bx, by, box_w, box_h, 6, fill=1, stroke=1)

                c.setFillColor(HexColor("#0B1F33"))
                c.setFont("Helvetica", 7)
                # naive wrap: two lines max
                label = n.label
                max_chars = 34
                line1 = label[:max_chars]
                line2 = label[max_chars:max_chars * 2] if len(label) > max_chars else ""
                c.drawString(bx + 8, by + 21, line1)
                if line2:
                    c.drawString(bx + 8, by + 10, line2)

                node_pos[n.node_id] = (bx, by, box_w, box_h)
                cur_y -= v_gap

        # Draw edges (straight lines with small arrowheads)
        c.setStrokeColor(HexColor("#374151"))
        c.setLineWidth(1)
        c.setDash()

        def center_right(box):
            bx, by, bw, bh = box
            return (bx + bw, by + bh / 2)

        def center_left(box):
            bx, by, bw, bh = box
            return (bx, by + bh / 2)

        def arrow(x1, y1, x2, y2):
            c.line(x1, y1, x2, y2)
            # arrow head
            ah = 4
            c.line(x2, y2, x2 - ah, y2 + ah / 2)
            c.line(x2, y2, x2 - ah, y2 - ah / 2)

        for e in self.graph.edges:
            if e.src not in node_pos or e.dst not in node_pos:
                continue
            src_box = node_pos[e.src]
            dst_box = node_pos[e.dst]
            x1, y1 = center_right(src_box)
            x2, y2 = center_left(dst_box)
            # small horizontal padding
            arrow(x1 + 2, y1, x2 - 2, y2)


def _build_styles():
    styles = getSampleStyleSheet()

    # NOTE: reportlab sample stylesheet already defines "Title".
    styles.add(
        ParagraphStyle(
            "ReportTitle",
            parent=styles["Title"],
            fontSize=18,
            alignment=TA_CENTER,
            textColor=HexColor("#11567F"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            "H2",
            parent=styles["Heading2"],
            fontSize=12,
            textColor=HexColor("#11567F"),
            spaceBefore=14,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=10,
            leading=14,
        )
    )
    styles.add(
        ParagraphStyle(
            "Small",
            parent=styles["Normal"],
            fontSize=8,
            leading=11,
            textColor=HexColor("#444444"),
        )
    )
    return styles


def _table(data: list[list[object]], col_widths: list[float]) -> Table:
    t = Table(data, colWidths=col_widths)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HexColor("#1A3A5C")),
                ("TEXTCOLOR", (0, 0), (-1, 0), white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.5, HexColor("#D0D7DE")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def render_pdf(graph: Graph, out_path: Path) -> None:
    styles = _build_styles()

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=letter,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
    )

    available_width = letter[0] - (0.75 + 0.75) * inch

    elements: list[object] = []
    elements.append(Paragraph("Governance Maturity Score — Lineage Report", styles["ReportTitle"]))
    elements.append(
        Paragraph(
            f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} — scope: <b>direct only</b>",
            styles["Small"],
        )
    )
    elements.append(HRFlowable(width="100%", thickness=1.5, color=HexColor("#29B5E8"), spaceAfter=10))

    elements.append(Paragraph("High-level lineage DAG (swimlanes)", styles["H2"]))
    elements.append(
        Paragraph(
            "Lanes show: skill routing → workflow → repo templates/scripts → Snowflake objects/functions.",
            styles["Body"],
        )
    )
    elements.append(Spacer(1, 8))
    elements.append(SwimlaneDag(graph, width=available_width, height=520))

    elements.append(PageBreak())

    # Nodes table
    elements.append(Paragraph("Node inventory", styles["H2"]))
    node_rows: list[list[object]] = [["Type", "Label", "Lane", "Evidence"]]
    for n in sorted(graph.nodes.values(), key=lambda x: (x.lane, x.kind, x.label)):
        ev = (
            f"{n.evidence.file}:{n.evidence.line}" if n.evidence else ""
        )
        node_rows.append([n.kind, n.label, n.lane, ev])
    elements.append(_table(node_rows, [1.0 * inch, 3.6 * inch, 1.1 * inch, 1.4 * inch]))

    elements.append(Spacer(1, 12))

    # Edges table
    elements.append(Paragraph("Edge inventory", styles["H2"]))
    edge_rows: list[list[object]] = [["From", "To", "Kind", "Evidence"]]
    for e in graph.edges:
        src = graph.nodes.get(e.src)
        dst = graph.nodes.get(e.dst)
        src_label = src.label if src else e.src
        dst_label = dst.label if dst else e.dst
        edge_rows.append([src_label, dst_label, e.kind, f"{e.evidence.file}:{e.evidence.line}"])
    elements.append(_table(edge_rows, [2.7 * inch, 2.7 * inch, 0.8 * inch, 0.9 * inch]))

    doc.build(elements)


def _graph_to_json(graph: Graph) -> dict:
    return {
        "nodes": [
            {
                "id": n.node_id,
                "label": n.label,
                "kind": n.kind,
                "lane": n.lane,
                "evidence": (
                    {
                        "file": n.evidence.file,
                        "line": n.evidence.line,
                        "snippet": n.evidence.snippet,
                    }
                    if n.evidence
                    else None
                ),
            }
            for n in graph.nodes.values()
        ],
        "edges": [
            {
                "src": e.src,
                "dst": e.dst,
                "kind": e.kind,
                "evidence": {
                    "file": e.evidence.file,
                    "line": e.evidence.line,
                    "snippet": e.evidence.snippet,
                },
            }
            for e in graph.edges
        ],
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--repo-root", required=True, help="Repo root (cortex-code-skills)")
    p.add_argument("--out", required=True, help="Output PDF path")
    p.add_argument("--emit-json", action="store_true", help="Print graph JSON to stdout")
    args = p.parse_args()

    repo_root = Path(args.repo_root).resolve()
    out_path = Path(os.path.expanduser(args.out)).resolve()

    graph = build_graph(repo_root)

    if args.emit_json:
        print(json.dumps(_graph_to_json(graph), indent=2))

    render_pdf(graph, out_path)
    print(f"PDF saved to: {out_path}")


if __name__ == "__main__":
    from datetime import datetime

    main()

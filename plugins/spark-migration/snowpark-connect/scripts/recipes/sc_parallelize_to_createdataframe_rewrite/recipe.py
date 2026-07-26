"""Rewrite ``sc.parallelize(data)`` / ``<x>.sparkContext.parallelize(data)`` to
``spark.createDataFrame(data)``.

What it does
------------

``SparkContext.parallelize`` is unavailable in Spark Connect / SCOS. The closest
DataFrame equivalent is ``spark.createDataFrame(data, schema)``::

    rdd = sc.parallelize([(1, "a"), (2, "b")])
    ->
    rdd = spark.createDataFrame([(1, "a"), (2, "b")])

When the receiver is ``<x>.sparkContext`` the session ``<x>`` is reused; a bare
``sc`` (the de-facto convention) becomes ``spark``. The single data argument is
preserved.

Why no schema is added
----------------------

``createDataFrame`` strongly prefers an **explicit schema** (per the RDD
reference -- inference over Python literals is fragile and sometimes
unsupported on SCOS), but the recipe cannot synthesise a correct schema
deterministically. So it rewrites the call shape and attaches a ``# SCOS``
comment telling the reader to supply an explicit schema and verify inference.
This is still a strict improvement over the annotate-only ``# SCOS-TODO`` the
``sparkcontext_property_fallback_rewrite`` method-call path would otherwise
leave.

Composition note
----------------

Sorts BEFORE ``sparkcontext_property_fallback_rewrite``
(``"sc_" < "sp"``), so it rewrites ``sc.parallelize`` first and leaves nothing
for that recipe's method-call annotation path to flag. Idempotent.

Negative cases (must NOT trigger)
---------------------------------

* ``obj.parallelize(...)`` where the receiver is not ``sc`` / ``.sparkContext``.
* ``sc.parallelize(data, numSlices)`` -- more than one positional arg; skipped
  (``createDataFrame`` has no ``numSlices``/partition-count parameter), left for
  the LLM fixer.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import _common  # noqa: E402
import libcst as cst  # noqa: E402

RECIPE_ID = "sc_parallelize_to_createdataframe_rewrite"
MIN_SCOS_VERSION = "0.4.0"

_COMMENT_TEXT = (
    f"# SCOS: [SPRKCNTPY1500] {RECIPE_ID}: sc.parallelize -> "
    f"spark.createDataFrame (supply an explicit schema; verify inference)"
)


def _is_sc_receiver(expr: cst.BaseExpression) -> bool:
    """True iff ``expr`` is bare ``sc`` or terminates in ``.sparkContext``."""
    if isinstance(expr, cst.Name) and expr.value == "sc":
        return True
    return (
        isinstance(expr, cst.Attribute)
        and isinstance(expr.attr, cst.Name)
        and expr.attr.value == "sparkContext"
    )


def _session_of(receiver: cst.BaseExpression) -> cst.BaseExpression:
    """``<x>.sparkContext`` -> ``<x>``; bare ``sc`` -> ``spark`` (convention)."""
    if isinstance(receiver, cst.Attribute) and isinstance(receiver.attr, cst.Name) \
            and receiver.attr.value == "sparkContext":
        return receiver.value
    return cst.Name("spark")


def _is_target_call(node: cst.CSTNode) -> bool:
    """True iff ``node`` is ``<sc>.parallelize(<single_positional_arg>)``."""
    if not (
        isinstance(node, cst.Call)
        and isinstance(node.func, cst.Attribute)
        and isinstance(node.func.attr, cst.Name)
        and node.func.attr.value == "parallelize"
        and _is_sc_receiver(node.func.value)
    ):
        return False
    # Single positional data arg only (skip parallelize(data, numSlices)).
    return len(node.args) == 1 and node.args[0].keyword is None


def _rewrite(call: cst.Call) -> cst.Call:
    """``<sc>.parallelize(data)`` -> ``<session>.createDataFrame(data)``."""
    assert isinstance(call.func, cst.Attribute)
    session = _session_of(call.func.value)
    return cst.Call(
        func=cst.Attribute(value=session, attr=cst.Name("createDataFrame")),
        args=[call.args[0].with_changes(comma=cst.MaybeSentinel.DEFAULT)],
    )


class _CallRewriter(cst.CSTTransformer):
    def __init__(self) -> None:
        super().__init__()
        self.rewrites = 0

    def leave_Call(  # type: ignore[override]
        self, original_node: cst.Call, updated_node: cst.Call
    ) -> cst.BaseExpression:
        if _is_target_call(updated_node):
            self.rewrites += 1
            return _rewrite(updated_node)
        return updated_node


def _already_annotated(stmt: cst.SimpleStatementLine) -> bool:
    for line in stmt.leading_lines:
        if line.comment is not None and RECIPE_ID in line.comment.value:
            return True
    return False


def _with_leading_comment(
    stmt: cst.SimpleStatementLine,
) -> cst.SimpleStatementLine:
    new_leading = list(stmt.leading_lines) + [
        cst.EmptyLine(comment=cst.Comment(_COMMENT_TEXT))
    ]
    return stmt.with_changes(leading_lines=tuple(new_leading))


class _Recipe(_common.BaseRecipe):
    RECIPE_ID = RECIPE_ID

    def leave_SimpleStatementLine(  # type: ignore[override]
        self,
        original_node: cst.SimpleStatementLine,
        updated_node: cst.SimpleStatementLine,
    ):
        if _already_annotated(updated_node):
            return updated_node
        sub = _CallRewriter()
        new_stmt = updated_node.visit(sub)
        if sub.rewrites == 0:
            return updated_node
        assert isinstance(new_stmt, cst.SimpleStatementLine)
        new_stmt = _with_leading_comment(new_stmt)
        self._record(
            self._line_of(original_node),
            f"sc.parallelize -> spark.createDataFrame ({sub.rewrites} call(s))",
        )
        return new_stmt


def apply(
    source: str, *, file: str = "<input.py>", facts_db: Optional[str] = None
) -> _common.RecipeResult:
    return _common.run_recipe(_Recipe, source, file=file, facts_db=facts_db)

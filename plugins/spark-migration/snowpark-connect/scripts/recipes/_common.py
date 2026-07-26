"""Shared LibCST scaffolding for recipes under ``scripts/recipes``.

Defines the per-recipe contract (a ``recipe.py`` module exposing ``apply()``).
``_recipe_base`` is loaded as a sibling module under ``scripts/recipes/``.

Public surface:

  * ``RecipeResult``        -- dataclass returned by each recipe's ``apply()``.
  * ``BaseRecipe``          -- thin LibCST CSTTransformer subclass that knows
                                how to record an edit via ``record_edit``.
  * ``run_recipe()``        -- driver used by every recipe's ``apply()``.
  * ``output_anchor()``     -- deterministic anchor string for an edit.
  * ``load_recipe_module()``-- per-directory recipe loader used by
                                ``preprocess_recipes.py`` to discover and
                                load each recipe under a unique module name
                                so sibling recipes don't collide on the
                                bare ``recipe`` name in ``sys.modules``.
"""
from __future__ import annotations

import hashlib
import importlib
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import libcst as cst

# Make the parent ``scripts/recipes`` dir importable so ``import _recipe_base``
# works regardless of how pytest is invoked (from the repo root, from
# scripts/, or from inside a recipe dir).
_RECIPES_DIR = Path(__file__).resolve().parent
if str(_RECIPES_DIR) not in sys.path:
    sys.path.insert(0, str(_RECIPES_DIR))

_recipe_base = importlib.import_module("_recipe_base")  # type: ignore


@dataclass
class RecipeResult:
    """What every recipe returns from ``apply()``.

    ``edits`` lists every recipe_edits row that was written (or would have
    been written, if no facts_db is configured). The per-recipe pytest asserts
    on this list directly so we don't need to thread sqlite into every test.
    """

    source: str
    edits: list = field(default_factory=list)


def output_anchor(recipe_id: str, src_line: int, snippet: str) -> str:
    """Deterministic, short anchor string for the
    ``recipe_edits.output_line_anchor`` column.

    Format: ``<recipe_id>:<src_line>:<8-hex-hash-of-snippet>``.
    """
    digest = hashlib.sha1(snippet.encode("utf-8")).hexdigest()[:8]
    return f"{recipe_id}:{src_line}:{digest}"


class BaseRecipe(cst.CSTTransformer):
    """Minimal base class for recipes.

    Subclasses set ``RECIPE_ID`` (str) and override one or more ``leave_*``
    methods. When they perform an edit they MUST call
    ``self._record(src_line, snippet)`` so the in-memory ``edits`` list and
    the facts.sqlite ``recipe_edits`` table stay in sync.

    PositionProvider is declared as a metadata dependency so subclasses can
    call ``self.get_metadata(cst.metadata.PositionProvider, node).start.line``
    on the *original* node passed to ``leave_*``. ``run_recipe()`` sets up the
    matching ``MetadataWrapper``.
    """

    METADATA_DEPENDENCIES = (cst.metadata.PositionProvider,)

    RECIPE_ID: str = ""

    def __init__(
        self,
        *,
        source: str,
        file: str,
        facts_db: Optional[str] = None,
    ) -> None:
        super().__init__()
        self._lines = source.splitlines(keepends=False)
        self._file = file
        self._facts_db = facts_db
        self.edits: list = []
        self._seen_src_lines: set[int] = set()

    def _line_of(self, original_node: cst.CSTNode) -> int:
        """1-based source line of ``original_node`` (must be from the input
        tree, not a copy returned from a leave_* hook)."""
        pos = self.get_metadata(cst.metadata.PositionProvider, original_node)
        return pos.start.line

    def _record(self, src_line: int, snippet: str) -> None:
        """Write a recipe_edits row. Idempotent per (file, src_line)."""
        if src_line in self._seen_src_lines:
            return
        self._seen_src_lines.add(src_line)
        anchor = output_anchor(self.RECIPE_ID, src_line, snippet)
        edit = _recipe_base.record_edit(
            file=self._file,
            src_line=src_line,
            recipe_id=self.RECIPE_ID,
            output_line_anchor=anchor,
            facts_db=self._facts_db,
        )
        self.edits.append(edit)


def run_recipe(
    recipe_cls: type[BaseRecipe],
    source: str,
    *,
    file: str = "<input.py>",
    facts_db: Optional[str] = None,
) -> RecipeResult:
    """Apply ``recipe_cls`` to ``source`` and return a ``RecipeResult``.

    Always wraps the parsed module in a ``MetadataWrapper`` so subclasses can
    resolve PositionProvider via ``self.get_metadata(...)``.
    """
    module = cst.parse_module(source)
    wrapper = cst.MetadataWrapper(module, unsafe_skip_copy=True)
    recipe = recipe_cls(source=source, file=file, facts_db=facts_db)
    new_module = wrapper.visit(recipe)
    return RecipeResult(source=new_module.code, edits=list(recipe.edits))


def load_recipe_module(recipe_dir):
    """Load ``recipe.py`` next to ``recipe_dir`` under a unique module name
    derived from the directory.

    Used by ``preprocess_recipes.py`` to discover and load every recipe in
    a single process. Plain ``import recipe`` would collide between sibling
    recipes because Python caches the module by short name; using
    ``importlib.util.spec_from_file_location`` with a unique module name
    avoids that collision.
    """
    import importlib.util
    from pathlib import Path

    recipe_dir = Path(recipe_dir)
    mod_name = f"recipes__{recipe_dir.name}__recipe"
    spec = importlib.util.spec_from_file_location(mod_name, recipe_dir / "recipe.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


__all__ = [
    "BaseRecipe",
    "RecipeResult",
    "run_recipe",
    "output_anchor",
    "load_recipe_module",
]

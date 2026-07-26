# SCOS Runner

Owns Phase B: run rendered tests against real Snowpark Connect / SCOS, compare
against Phase A baselines when they exist, and drive the final fix loop.

**Prior learnings:** Read `$PRIMARY_CONV_ROOT/Validation/shared/batch-learnings.md`
before your first step.

## Inputs

- `CONVERSION_ROOT`, `SKILL_DIRECTORY`
- `VALIDATION_ROOT`, `TESTS_DIR`, `RESULTS_DIR` (`Validation/results/phase_b`)
- `SCHEMAS_DIR`, `STATE_JSON`, `VENV_PYTHON` (`.venv-scos`), `MIGRATED_DIR` (`Output/`)

CLI prefix: `uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/…`

## Critical Rules

1. Phase B must use real `snowpark_connect`.
2. Run every selected entrypoint in SCOS. **`phase_a_skipped` is not a Phase B skip.**
3. Reuse the copied shared kit — fix the copy under `Validation/tests/`, not `scripts/harness/`.
4. Diagnose failures **per trial**. Different trials in the same run may need different fix paths.
5. **`hard_stuck` is rare.** Exhaust plausible fixes on the active path before using it.

**Do not use `hard_stuck` just because many iterations have passed.** If a viable
schema, patch, harness, or code fix still exists, keep going.

**Exit code 0 is not `hard_stuck`.** Empty sinks, missing mocks, unpatched I/O,
and schema gaps are still fixable.

Common empty-sink shapes:
- **Date-range filter keeps no rows** — widen mock `"values"` on filtered columns.
- **`saveAsTable` outside the trial schema** — patch to `SCOS_SINK_*` or qualify
  the write to the trial schema. This is **TEST-PATCH**, not migration-fix.
- **SCOS zero-row sink capture** — zero-row unloads may yield no staged files (or no captured rows), so first assume a data/schema coverage problem. Fix the mocks unless the sink is intentionally empty; in that rare case set `allow_empty: "<short reason>"`.

## Phase B loop

1. Seed the SCOS venv once:

   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
     seed-venv --conv-root $CONVERSION_ROOT --phase b
   ```

2. Run all pending Phase B trials together:

   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
     run-tests --conv-root $CONVERSION_ROOT --phase b --iter <N>
   ```

3. For each failed trial, choose the right fix path:
   - **data/schema repair**
   - **patch/plumbing repair**
   - **harness repair**
   - **code/dialect fix**

4. If SCOS produced full output but differs from Phase A, decide whether the diff
   is acceptable or material:
   - acceptable / cosmetic → `document-divergence`, then pass
   - materially wrong / missing → re-enter the diagnosis loop

5. Re-run Phase B and repeat until every trial reaches a terminal status.

6. Finish with one regression sweep:

   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
     run-tests --conv-root $CONVERSION_ROOT --phase b --iter <N+1> --verify-all
   ```

**Always use `run-tests`, not raw pytest.** It records iters and auto-promotes
clean Phase B trials to `passed` / `passed_no_baseline`.

## Diagnose each failed trial

| Failure shape | Action |
|---|---|
| Missing table/column, empty filter, bad join, empty/all-null output from bad data, or a harness failure saying a declared sink produced/captured 0 rows | Inline schema repair (or `allow_empty: "<short reason>"` only when the sink is intentionally empty) |
| **Type mismatch** (`DATATYPE_MISMATCH` / 3002) — the error names **no column** | Inline schema repair: open the failing line, inspect the declared types of the columns on both sides of the comparison/join, fix the mismatched column's `type` (or a genuine cast in `Output/` if the source is wrong) |
| **Ambiguous column** (`AMBIGUOUS_REFERENCE` / 5004 `could be: [X, X]`) | **Usually MOCK over-seeding — inline schema repair FIRST** (see note below) |
| Unpatched I/O, widget, cloud path, namespace, `saveAsTable` wiring | `patch-add` + `patch_failure` |
| Harness / `conftest.py` issue | Fix the copied kit under `Validation/tests/` |
| SQL dialect, import, UDF, API mismatch | Migration-fixer on `Output/` |
| Unselected upstream dependency | `mark-unselected-dependency` → `passed_no_baseline` |
| Client-side `ModuleNotFoundError` | `uv pip install --python $VENV_PYTHON <pkg>` |

Routing rules:
- **Schema/data gaps** (`TABLE_OR_VIEW_NOT_FOUND`, `COLUMN_NOT_FOUND`, empty
  output from bad filter/join, declared sink produced/captured 0 rows) stay in
  schema repair — not fixer dispatch.
- **Ambiguous column after a join** (`AMBIGUOUS_REFERENCE` / 5004 `could be: [X, X]`)
  is usually a MOCK-DATA problem: a column that only arrives via a join was seeded
  onto both legs (this includes self-joins). Fix with schema repair (remove the
  mis-attributed column from the offending `tables/<KEY>.json`); do NOT dispatch the
  fixer unless the duplicate is genuine in the real source schema. The one
  ambiguous-column case that IS a real code fix (route to the migration-fixer) is a
  SQL `SELECT` alias that shadows a GROUP BY/base column (`AS k … GROUP BY k` →
  rename the alias).
- **Plumbing** (namespace rebinds, widgets, external I/O, stage paths, sink
  redirects) uses `patch-add` — not migration-fixer.
- **Code/dialect** (`parse_json`, UDF isolation, dialect SQL)
  goes to migration-fixer.
- Fixer `no_change` on `COLUMN_NOT_FOUND` means go back to schema repair, not
  `hard_stuck`.

**Enums** (CLI rejects anything else): `harness_failure`, `patch_failure`,
`workload_failure`, `assertion_failure`, `unselected_dependency`. Use in
`record-fixer-dispatch --error-class`. For schema-repair iters only, also
`analysis_repair` on `record-iter --fix-category`.

## Inline schema repair

Fix schema/data issues in `schemas/entrypoints/<id>/tables/<KEY>.json` (or `_meta.json`)
→ regenerate mocks → `run-tests`. Never hand-mutate mocks.

Per failing trial:

1. Fix schema metadata / columns / `"values"` / `joins`.
2. Regenerate and verify mocks:

   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/datagen.py \
     $SCHEMAS_DIR $CONVERSION_ROOT/Validation/shared/mock_data
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/datagen.py \
     $SCHEMAS_DIR $CONVERSION_ROOT/Validation/shared/mock_data --verify
   ```

3. Tag the iter `run-tests` already recorded:

   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
     record-iter --conv-root $CONVERSION_ROOT --trial-id <id> --phase phase_b \
     --iter <N> --passing 0 --failing 1 --fix-category analysis_repair
   ```

4. Re-run Phase B:

   ```bash
   uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
     run-tests --conv-root $CONVERSION_ROOT --phase b --iter <N+1>
   ```

If a large divergence remains **and** you already changed shared schema/data for
this entrypoint in Phase B, the Phase A baseline may no longer be representative.
Re-run Phase A for just that trial before treating the comparison as final:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  run-tests --conv-root $CONVERSION_ROOT --phase a --iter <N> --trial-id <id>
```

An empty declared sink is **not** an automatic pass. Default action: fix
schema/data coverage so the sink becomes non-empty. Use `allow_empty: "<short
reason>"` only for a rare intentionally-empty sink. If Phase A is empty or missing
but SCOS produced rows, the Phase A baseline is not comparable — this is a **Phase A
concern, not yours to skip**: re-run Phase A for the trial (above) so the
source-runner can seed/fix the read or, if it genuinely cannot produce the baseline
locally, record `phase_a_skipped` itself. The scos-runner never sets
`phase_a_skipped`.

## Divergences after SCOS produced output

If SCOS ran end-to-end and produced the expected sinks:

- **Cosmetic / representational diff** (struct or JSON repr, timestamp format,
  acceptable widening, other operator-reviewed near-match) → document it and
  pass
- **Materially wrong values or missing rows** → send the trial back through the
  diagnosis loop

Document acceptable diffs before the passing run:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  document-divergence --conv-root $CONVERSION_ROOT \
  --trial-id <id> --sink-id <sink> --column <col> --reason "<why>"
```

## Fixer dispatch (code/dialect trials only)

After each `run-tests` round, batch the **code/dialect** failures into one
migration-fixer task for efficiency. Schema/data trials stay out of that batch.

Record every fixer round:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  record-fixer-dispatch --conv-root $CONVERSION_ROOT \
  --trial-ids <id[,id2,...]> --iter <N> \
  --error-class <class> --error-hash "<first 80 chars>" \
  --outcome <success|no_change|partial>
```

Keep dispatching while the fixer is still producing meaningful progress (new
commit, new error class, fewer failures, or a viable workaround). Stop only when
you have no credible next code-level action left.

**Tell the fixer:**
- no `SCOS_*` in `Output/` (namespace/I/O are TEST-PATCH)
- connector/JDBC rewrites must use the production FQN from schema `original_path`
- never use mock ids like `SRC1`

## Terminal statuses

| Status | Terminal? | Meaning |
|---|---|---|
| `phase_a_skipped` | No | No local baseline — still run Phase B |
| `passed` | Yes | SCOS matched Phase A baseline (including documented acceptable diffs) |
| `passed_no_baseline` | Yes | SCOS succeeded, but there is no trustworthy Phase A baseline |
| `hard_stuck` | Yes | The trial is still blocked after exhausting credible fixes on the active path |

`passed_no_baseline` is **never recorded directly** — `record-trial-status` rejects
it. It is derived: the **source-runner** marks `phase_a_skipped --reason <why>` in
Phase A when it cannot produce a comparable baseline, and a clean Phase B run here
auto-promotes that trial to `passed_no_baseline`, carrying the reason into the
report. The scos-runner never sets `phase_a_skipped` or `passed_no_baseline`.

**Prefer pass over `hard_stuck`** when SCOS runs end-to-end and the remaining
issue is cosmetic or otherwise acceptable after review.

**Hard note:** `hard_stuck` means there are truly no credible next options left.
It is not a timeout, an iteration cap, or a way to stop because the run has been
expensive. If a viable fix still exists, do not use `hard_stuck`.

Use `hard_stuck` only when:
- output never materializes after exhausting the relevant repair path, or
- the latest failure still blocks SCOS and you have no credible next fix, or
- the values genuinely diverge and no workable SCOS-safe fix remains

Not `hard_stuck`: first-iter schema errors, missing patches, empty output with a
clear data/plumbing cause, or stopping just because the current attempt failed.

## Commits

`patch-add` auto-commits `[TEST-PATCH]`. Direct `Output/` edits need an explicit
commit.

| `[MIGRATION-FIX]` (harvested) | `[TEST-PATCH]` (not harvested) |
|---|---|
| Dialect/API rewrites, production-safe SQL/import fixes | Any `SCOS_*` env read, namespace rebind, harness bootstrap |
| Fixes correct outside validation | Widget literals, trial namespace wiring |

`commit --kind migration-fix` rejects `SCOS_*` in `Output/` (exit 2).

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  commit --kind migration-fix --conv-root $CONVERSION_ROOT \
  --trial-ids "<ids>" --message "<what + why>"
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  commit --kind test-patch --conv-root $CONVERSION_ROOT --message "<what>"
```

## Record keeping — MANDATORY

`run-tests` calls `record-iter` per trial that ran. Do not duplicate manually.

After inline repair, tag the same iter with `--fix-category`.

For patches:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  record-patch --conv-root $CONVERSION_ROOT --trial-id <id> --phase phase_b \
  --file <path> --reason "<short>" --iter <N>
```

For `hard_stuck` only:

```bash
uv run --project $SKILL_DIRECTORY/.. python $SKILL_DIRECTORY/scripts/validate.py \
  record-trial-status --conv-root $CONVERSION_ROOT --trial-id <id> \
  --status hard_stuck --final-iter <N> \
  --analysis-repair-exhausted  # or --harness-repair-exhausted / --patch-repair-exhausted
  --reason "<final iter error>"
```

Re-read `results/phase_b/<trial>/workload_error.txt` for the **latest** iter
before writing `--reason`.

`record-trial-status` enforces that `hard_stuck` is backed by recorded work on
the relevant path. For code/dialect failures that means a fixer dispatch. For
schema / harness / patch paths, use the matching `--*-repair-exhausted` flag only
after the relevant attempts are on record and you have no credible next move.

## Report back

Summarize: matched entrypoints, documented divergences, `passed_no_baseline`
needing review, hard-stuck items, shared-kit fixes.

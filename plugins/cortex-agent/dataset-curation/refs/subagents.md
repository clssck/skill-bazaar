# Methodology + worker-subagent playbook (reference)

Two concerns owned by this reference file:

1. **`<METHODOLOGY>`** — invoke the user's agent for ground truth, or have CoCo generate it locally.
2. **Worker-subagent invocation** — when methodology = 1, spawn up to 8 `general-purpose` subagents in parallel (one per question-chunk) using the [team-workflow worker-launch contract](../../../team-workflow/SKILL.md#required-worker-launch-contract). Same `Task` tool, same required fields.

It is **not** a skill. `dataset-curation-scratch` (and transitively `dataset-curation-expand`'s `build-only` sub-call) link here when they reach the methodology choice or the agent-invocation batch. Does NOT apply to `dataset-curation-production` (its data is observed, not invoked).

**The calling skill's Step 3.1 STOP already selects `<METHODOLOGY>`** before reaching this file. The defaults below apply only to execution-layer settings (worker count, timeouts, retry policy): ≤ 8 workers, 300 s per-question hard timeout, one consolidated retry pass, drop residual misses, print the miss-rate report.

## When to read this

| You're at… | …read |
|---|---|
| methodology reference (already selected by calling skill) | [Step 1](#step-1-methodology-decision-matrix) |
| spawning the batch | [Step 2](#step-2-parallel-invocation-via-worker-subagents) |
| post-batch verification + miss-rate report | [Step 3](#step-3-verification--miss-rate-report) |
| per-track projection / trace-window rules | [Step 4](#step-4-projection--trace-window-invariants) |

---

## Step 1: Methodology decision matrix

`<METHODOLOGY>` is already set by the calling skill's Step 3.1 STOP. This matrix documents the two values for reference and per-row fallback decisions mid-batch.

| `<METHODOLOGY>` | What it does | When to pick |
|---|---|---|
| **1 — invoke the user's agent** | Spawns Step 2 against `<ALL_QUESTIONS>`. AC-track rows capture `record_root.output`; TEA-track rows capture the full trace. Higher fidelity, some bias toward current agent behaviour. | Default. Agent is wired up and the user wants ground truth that reflects what it does today. |
| **2 — CoCo generates** | No agent invocation, no observability traffic. CoCo hand-authors `ground_truth_output` and writes SQL / search queries / `CALL`s against real data (see [`ac_details.md` § AC drafting by methodology](./ac_details.md#ac-drafting-by-methodology) and [`tea_details.md` § TEA drafting by methodology](./tea_details.md#tea-drafting-by-methodology)). | Agent not yet built, or the user wants a clean reference independent of current behaviour. |

**Per-row fallback** — under `<METHODOLOGY> = 2` you may escalate individual rows to #1 (or vice versa). Track which path produced each row so the user can audit later.

---

## Step 2: Parallel invocation via worker subagents

Mirrors the [team-workflow worker-launch contract](../../../team-workflow/SKILL.md#required-worker-launch-contract). Fixed budget: **≤ 8 `general-purpose` subagents per round**. Spawn `min(N, 8)` workers, each invoking the user's agent on `ceil(N / min(N, 8))` questions (the last chunk may be one question short). Never spawn empty-chunk workers.

**Setup** (one assistant message):

```text
cortex ctx task add "Invoke <AGENT_FQN> on <N> questions"   # → <invoke_tid>
cortex ctx team create team-scratch-invoke-<invoke_tid>
cortex ctx step add -t <invoke_tid> \
    "Invoke agent on chunk 1" "Invoke agent on chunk 2" ...  # one step per chunk
cortex ctx step start -t <invoke_tid> <chunk_sid_1> && \
cortex ctx step start -t <invoke_tid> <chunk_sid_2> && ...
```

**Spawn** (same assistant message, one `Task` call per chunk — all fire concurrently):

- `subagent_type = general-purpose`
- `run_in_background = true`
- `team_name = team-scratch-invoke-<invoke_tid>`
- `name = invoker-<chunk_sid>`
- `description` ≤ 5 words (e.g. `"Invoke agent on chunk 1"`)
- `prompt` includes: `<AGENT_FQN>`, `<CONNECTION>`, `<DATABASE>`, `<SCHEMA>`, `<batch_start>` (so the worker can scope its `record_root` span-existence check to the shared window), the chunk's `INPUT_QUERY` list verbatim, and the four worker responsibilities below.

**Each worker subagent's responsibilities:**

1. Loop through its `INPUT_QUERY` list. Invoke the user's agent on each one with a **300 s per-call hard timeout**. On timeout, append `INPUT_QUERY` to a local `timed_out` list (`reason = "timeout_300s"`) and continue — do not retry inline.
2. After every successful call, verify a `record_root` span exists for that exact `INPUT_QUERY` in the `<batch_start>` window. If absent, append to `failed` (`reason = "no_record_root_span"`).
3. Before exiting, emit one `cortex ctx discovery add --type invoker --tags chunk-result` with `{"chunk_idx": …, "succeeded": [...], "failed": [...], "timed_out": [...]}`.
4. **Do NOT** project the trace, write to `EVAL_DATASET_*`, execute trace SQL, or modify ground-truth fields — those are the main agent's job in the per-track subsections.

**Wait + single retry pass:**

- Wait for every `Step <chunk_sid> complete: …` callback. Run `cortex ctx step list -t <invoke_tid>` after each callback.
- After all chunks terminal, sweep discoveries; build `<FAILED_QUESTIONS>` = union of every chunk's `failed[*]` + `timed_out[*]`.
- If `<FAILED_QUESTIONS>` is non-empty **and** the ≤ 8 budget has a free slot (chunk worker count `< 8`), spawn **one** retry worker (`invoker-retry-<…>`) on the failed list, same 300 s cap. It counts against the budget for the current round.
- If the ≤ 8 budget is already exhausted (8 chunk workers spawned because `N ≥ 8`), **skip the retry pass** and move the entire `<FAILED_QUESTIONS>` set straight into `<MISS_LIST>` — do not violate the cap.
- Residuals after the retry (or all of `<FAILED_QUESTIONS>` when retry is skipped) → `<MISS_LIST>` (auto-dropped, no user STOP — see Step 3).

**Cleanup:**

```text
cortex ctx task done <invoke_tid>
cortex ctx team delete team-scratch-invoke-<invoke_tid>
```

If `team delete` fails: `cortex ctx message clear --team … && cortex ctx discovery clear --team …`.

**Forbidden inside the worker subagents:**

- Do NOT project per-tool traces (no `agent.tool.*` SQL) — the main agent does that in Step 4.
- Do NOT write to `EVAL_DATASET_*` / `EVAL_ANNOTATIONS_*` tables — that's Step 4 / Step 5 of the calling skill.
- Do NOT call `SYSTEM$CREATE_EVALUATION_DATASET` — the calling skill's Step 5 owns registration.
---

## Step 3: Verification + miss-rate report

Run **once** after Step 2 completes, before any per-track projection:

> Use `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('<DATABASE>', '<SCHEMA>', '<AGENT_NAME>', 'CORTEX AGENT'))` to read observability events scoped to the agent.

```sql
SELECT COUNT(DISTINCT RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING) AS distinct_questions
FROM TABLE(
  SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(
    '<DATABASE>',
    '<SCHEMA>',
    '<AGENT_NAME>',
    'CORTEX AGENT'
  )
)
WHERE TIMESTAMP >= '<batch_start>'
  AND RECORD_ATTRIBUTES:"ai.observability.span_type"::STRING = 'record_root'
  AND RECORD_ATTRIBUTES:"ai.observability.record_root.input"::STRING IN (<ALL_QUESTIONS>);
-- expected = N - len(<MISS_LIST>)
```

If `distinct_questions` is short of `N - len(<MISS_LIST>)`, append the silently-missing `INPUT_QUERY` values to `<MISS_LIST>` (`reason = "silent_missing_span"`) — do not re-invoke.

**`<MISS_LIST>`** = union of timeouts, HTTP/wrapper errors, and silent missing spans (per question, with a reason tag). Reduce `<ALL_QUESTIONS>` by `<MISS_LIST>`. For each missed `INPUT_QUERY`, look up its track label (`ac` / `tea`) from the Step 2 question design (the same label attached when the question was authored) and decrement `<AC_COUNT>` or `<TEA_COUNT>` accordingly.

> Print to user:
> ```
> Done! Captured <N - MISS_COUNT> of <N> questions:
>   - <AC_COUNT - ac_misses> for answer correctness and logical consistency
>   - <TEA_COUNT - tea_misses> for tool execution accuracy and tool selection accuracy
> [If MISS_COUNT > 0:]  Dropped <MISS_COUNT> questions (timed out or errored): <list of dropped question texts>
> ```

If `<MISS_RATE> > 25 %`, append a one-line warning but still proceed — the user can re-run dataset-curation later.

---

## Step 4: Projection + trace-window invariants

> **MANDATORY:** All ground-truth data (agent answers for AC, SQL/search/generic invocations for TEA) MUST be extracted by executing the projection SQL from `tea_details.md` / `ac_details.md` against `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS(...))` via `sql_execute`. Do NOT read or parse any local trace files, SSE payloads, `.jsonl` files, or Python script output for ground truth. The invocation script exists only to trigger runs — it produces no usable ground-truth artifacts.

After Step 3, the AC-track and TEA-track per-track subsections in the calling skill each run their own projection against the same `<batch_start>` window:

- **AC-track** — pulls `record_root.input` + `record_root.output` for the AC-track subset. SQL: [`ac_details.md` § AC drafting by methodology](./ac_details.md#ac-drafting-by-methodology).
- **TEA-track** — pulls the per-family `agent.tool.<sql_execution|cortex_search|web_search>.*` payloads (plus `agent.planning.tool_execution.*` as the fallback for custom / generic tools) for the TEA-track subset. SQL: [`tea_details.md` § TEA drafting by methodology](./tea_details.md#tea-drafting-by-methodology).

**Trace-window invariants** (must hold across the whole batch):

1. `<batch_start>` is fixed **once**, immediately before Step 2 spawns its first invoker. Never re-capture later.
2. Both per-track projections read the **same** `<batch_start>`. Mixing windows lets non-deterministic tool routing drift the two tracks apart.
3. Never invoke the agent inside a per-track subsection — the shared Step 2 batch is the only window.
4. Under `<METHODOLOGY> = 2`, there is no `<batch_start>` and no batch — `ac_details.md` / `tea_details.md` handle the local-only path.

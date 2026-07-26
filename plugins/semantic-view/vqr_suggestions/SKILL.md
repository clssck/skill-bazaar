---
name: semantic-view-vqr-suggestions
description: >
  Generate verified query (VQR) suggestions for a semantic view by analyzing Cortex Analyst
  usage and Snowflake query history. Use this skill whenever the user wants to discover what
  questions people are asking, populate verified queries from real usage patterns, bootstrap
  VQRs for a new or existing semantic view, or understand which queries would benefit from
  verification. This includes requests like 'suggest VQRs', 'what are people asking',
  'generate queries from history', 'recommend verified queries', or any mention of
  populating, seeding, or auto-generating VQRs. Even if the user just says something like
  'add some queries' after creating a view, this is the right skill.
parent_skill: semantic-view
---

# VQR Suggestions

Verified queries (VQRs) teach Cortex Analyst how to answer specific questions correctly. Manually writing them is slow — this workflow uses `get_vqr_suggestions.py` to automatically suggest VQRs by mining both Cortex Analyst request history and Snowflake query history in parallel.

## When to Load

Load this skill when the user wants to generate, suggest, seed, or populate VQRs for a semantic view. Common triggers:

- Right after creating a new semantic view ("now add some queries")
- User asks what questions people are asking a view
- User wants to bootstrap VQRs from query history
- Any mention of "VQR suggestions", "recommend queries", "auto-generate VQRs"

## Prerequisites

- A semantic view already created (fully qualified name: `DB.SCHEMA.VIEW_NAME`)
- SKILL_BASE_DIR and WORKING_DIR set (from setup/SKILL.md)

## Workflow

### Phase 1: Gather Context

Collect from user:

| Field | Required | Notes |
|-------|----------|-------|
| **Semantic view** | Yes | Fully qualified name (`DB.SCHEMA.VIEW`) |
| **Limit** | No | Number of suggestions per mode (default: 3) |
| **Speed** | No | `fast` (default) or `slow` — see below |
| **Connection** | No | Snowflake connection name (default: from env or first available) |

**✋ STOP** if the semantic view identity is unclear — ask before proceeding.

### Phase 2: Execute the Script

**Load** [get_vqr_suggestions.md](../reference/get_vqr_suggestions.md) for full tool parameters.

```bash
uv run --project {SKILL_BASE_DIR} python {SKILL_BASE_DIR}/scripts/get_vqr_suggestions.py \
  --semantic-view DB.SCHEMA.VIEW_NAME \
  --output {WORKING_DIR}/vqr_suggestions.json \
  --limit 10
```

The script runs **both** `ca_requests_based` and `query_history_based` modes in parallel and merges results automatically.

**Speed modes** control which query history sources are used:

| Mode | Sources | When to use |
|------|---------|-------------|
| `fast` (default) | Snowscope only | Always try first |
| `slow` | Snowscope + information_schema | Only when `fast` returns insufficient results. **⚠️ Warn user** — significantly slower |

To use slow mode, add `--speed slow` to the command.

### Phase 3: Present Results

The script prints results to console and saves JSON to the output file. Present the suggestions as a numbered list showing **question**, **SQL**, **source mode**, and **occurrence count** for each.

If no suggestions were returned, explain possible reasons (new view with no history, no CA traffic) and suggest trying again later or creating VQRs manually.

### Phase 4: Offer Next Steps

**✋ STOP** — ask the user what they'd like to do:

1. **Validate SQL with SVA (optional)** — before writing to YAML, compile-check candidate SQL: [sva_validate_verified_queries.md](../reference/sva_validate_verified_queries.md) (inline mode; strip `verified_queries` from model YAML in the payload).
2. **Add suggestions as VQRs** — use `semantic_view_set.py` (load [semantic_view_set.md](../reference/semantic_view_set.md))
3. **Get more suggestions** — increase the limit or try `--speed slow`
4. **Run VQR testing audit** — behavioral audit (CA without VQR hints): [audit/vqr_testing/SKILL.md](../audit/vqr_testing/SKILL.md)

## Error Handling

| Error | Fix |
|-------|-----|
| Script timeout (2 min per request) | Manually generate suggestions by analyzing the semantic model YAML |
| Connection failed | Check `SNOWFLAKE_CONNECTION_NAME` env var or provide `--connection` |
| No suggestions returned | View may lack history — try other mode or create VQRs manually |
| Permission denied | Check role: `SELECT CURRENT_ROLE()` |

## Success Criteria

- ✅ Script executed with both modes
- ✅ Suggestions presented clearly to user
- ✅ Output JSON saved to WORKING_DIR
- ✅ Next steps offered

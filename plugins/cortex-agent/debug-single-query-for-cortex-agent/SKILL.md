---
name: debug-single-query-for-cortex-agent
description: Interactively debug specific agent query failures to identify and fix routing, SQL, or response issues. Use when investigating why a specific query fails or produces incorrect results, either from live testing or production event logs.
---

# Debug Single Query For Cortex Agent

Whenever running scripts, make sure to use `uv`.

**Workflow:** Follow the interactive debugging process in this doc.

1. **Establish Context** - Identify agent name, and what issue we're trying to debug
2. **Get Query & Response** - Determine if debugging from request ID (event table) or running fresh query
3. **Run/Retrieve Query** - Fetch event trace or execute new query
4. **Test Stability** - Run query multiple times to check for non-deterministic behavior
   4.5. **Tool Type Decision Gate** ⚠️ MANDATORY CHECKPOINT - Check if Cortex Analyst tool was used; if yes, immediately load semantic-view skill
5. **Check Correctness** - Compare actual vs. expected answer, identify issue type
6. **Analyze Tool Calls and Agent Config** - Set up workspace per system of record, retrieve agent config (create clone if production), examine tool selection, VQR influence, SQL logic, and results
7. **Present Hypothesis** - Clearly articulate what went wrong with evidence
8. **Apply Fix** - Update instructions in version directory, deploy changes following system of record protocols, and verify

**⚠️ Important:** Stages 6-8 follow the **system of record protocols** (see `../agent-system-of-record/SKILL.md`). This includes workspace setup, production agent cloning, and proper versioning of all changes.

**Common Issues Debugged:**

- Wrong tool selected (VQR override or ambiguous routing)
- SQL logic errors (date/filter interpretation, pattern matching)
- Response formatting/completeness issues
- "No data available" errors (wrong tool or semantic model gaps)

**Debugging Modes:**

**A) Production Debugging (from request ID):**

**Preferred — request/record ID:** from **`cortex-agent/`**, **`fetch_events_from_event_table.py --request-id …`** only (queries **`SNOWFLAKE.LOCAL.AI_OBSERVABILITY_EVENTS`** by **`record_id`**; do not pass agent FQN args). Eval: **`uv run --project /custom-skills/cortex-agent python /custom-skills/cortex-agent/scripts/fetch_events_from_event_table.py ...`**. Raw rows—use **`RECORD_ATTRIBUTES`** for FQN hints before structured fetch.

```bash
uv run python scripts/fetch_events_from_event_table.py \
  --request-id 'REQUEST_ID' \
  --connection CONNECTION \
  --limit 50 \
  --output "$VER_DIR/evals/debug_trace.json"
```

**If the raw table is blocked:** rerun with **`--agent-name` / `--database` / `--schema`** and **`--where`** on **`ai.observability.record_id`** (script uses **`GET_AI_OBSERVABILITY_EVENTS(..., 'CORTEX AGENT')`**).

```bash
uv run python scripts/fetch_events_from_event_table.py --agent-name AGENT --database DATABASE --schema SCHEMA \
  --connection CONNECTION \
  --where "RECORD_ATTRIBUTES:\"ai.observability.record_id\" = 'REQUEST_ID'" \
  --output "$VER_DIR/evals/debug_trace.json"
```

Read **`debug_trace`** from the script output to understand the run; use agent-scoped fetch if you need traces via the UDTF.

**B) Fresh Query Testing:**

```bash
# Run query and save response
# Note: Ensure workspace is set up (see Stage 6 for workspace setup)
uv run python ../scripts/test_agent.py --agent-name AGENT --question "question" \
  --output-file "$VER_DIR/evals/debug.json" --database DATABASE --schema SCHEMA --connection CONNECTION
```

## 1. Establish Context

Check if user already has:
- Agent context (name, database, schema)
- Query text or response

If missing, ask or infer from working directory.

## 2. Get Query & Response

Determine scenario:
- User has response JSON (from evaluation or logs)
- User has query text only → need to run it
- User has request ID → fetch from event table

## 3. Run/Retrieve Query

**Option A: User has request ID** (most common for production debugging)

1. **If you only have the request/record ID** — call the script with **`--request-id`** (see **Debugging Modes → A** for full flags). That loads rows from **`AI_OBSERVABILITY_EVENTS`** without an agent FQN.
2. **After you know `DATABASE`, `SCHEMA`, and `AGENT`** — use agent-scoped fetch for **`GET_AI_OBSERVABILITY_EVENTS`**, structured questions, and trace enrichment:

```bash
# Note: Workspace should be set up in Stage 6, but if running early, create version dir:
# VERSION="v$(date +%Y%m%d-%H%M)"
# VER_DIR="${WORKSPACE_DIR:-$(pwd)}/versions/$VERSION"
# mkdir -p "$VER_DIR/evals"
uv run python ../scripts/fetch_events_from_event_table.py --agent-name AGENT --database DATABASE --schema SCHEMA \
  --connection CONNECTION \
  --where "RECORD_ATTRIBUTES:\"ai.observability.record_id\" = 'REQUEST_ID'" \
  --output "$VER_DIR/evals/debug_trace.json"
```

**Option B: User has query text only**

```bash
# Run query and capture response
# Note: Workspace should be set up in Stage 6, but if running early, create version dir:
# VERSION="v$(date +%Y%m%d-%H%M)"
# VER_DIR="${WORKSPACE_DIR:-$(pwd)}/versions/$VERSION"
# mkdir -p "$VER_DIR/evals"
uv run python ../scripts/test_agent.py --agent-name AGENT --question "question" \
  --output-file "$VER_DIR/evals/debug.json" --database DATABASE --schema SCHEMA --connection CONNECTION
```

## 4. Test Stability

**If debugging from event table:**

- Re-run the same query to check consistency:

```bash
QUESTION=$(cat "$VER_DIR/evals/debug_trace.json" | jq -r '.[0].question')
uv run python ../scripts/test_agent.py --agent-name AGENT --question "$QUESTION" \
  --output-file "$VER_DIR/evals/debug_rerun.json" --database DATABASE --schema SCHEMA --connection CONNECTION
```

**If ran fresh query:**
Run query a second time and compare answers:

```bash
uv run python ../scripts/test_agent.py --agent-name AGENT --question "question" --output-file "$VER_DIR/evals/debug2.json" --database DB --schema SCH --connection CONN
diff <(cat "$VER_DIR/evals/debug.json" | jq -r '.content[].text') \
     <(cat "$VER_DIR/evals/debug2.json" | jq -r '.content[].text')
```

Note if answers differ (may indicate VQR/LLM routing variability).

## 4.5. Tool Type Decision Gate ⚠️ MANDATORY CHECKPOINT

**STOP HERE and check tool types before proceeding to correctness analysis.**

Extract tool types from the test response:

```bash
cat "$VER_DIR/evals/debug.json" | jq -r '.content[] | select(.type == "tool_use") | .name' | sort | uniq
```

**Decision tree:**

- ✅ **If ANY tool is `cortex_analyst`** → **IMMEDIATELY STOP THIS WORKFLOW**
  - Load `semantic-view` skill
  - Follow semantic view debug workflow instead (use `debug/SKILL.md`)
  - **Reason**: SQL generation issues must be debugged at the semantic view level with specialized tools (semantic_view_get.py, semantic_view_set.py, VQR analysis)
- ✅ **If tools are `cortex_search`, `generic`, or other custom tools** → Continue to Step 5

**Why this gate exists**: Cortex Analyst SQL issues require semantic view debugging expertise. Agent instruction changes won't fix semantic view configuration problems. The semantic-view skill has specialized tools that aren't available in this workflow.

**DO NOT SKIP THIS GATE.** Agent debugging and semantic view debugging are separate workflows.

## 5. Check Correctness

If expected answer available, compare. Otherwise ask user:

- Is the answer correct?
- If no, why is it incorrect?

Capture the issue type: wrong tool, SQL error, formatting, etc.

**Check user feedback (if available):**

If debugging from event table, check if users have already provided feedback on this query:

Feedback can provide valuable clues about the issue:
- `positive: false` indicates user dissatisfaction
- `categories` may reveal issue type (e.g., "Wrong tool used", "Incorrect SQL", "Incomplete answer")
- `feedback_message` may contain specific details about what went wrong

**Note**: If you identified a Cortex Analyst tool issue in Step 4.5, you should have already loaded the semantic-view skill. Only non-Cortex Analyst issues reach this step.

## 6. Analyze Tool Calls and Agent Config

**⚠️ CRITICAL: Follow System of Record Protocols**

Before analyzing the agent config, ensure proper workspace setup:

**1. Check if workspace exists, create if needed:**

```bash
AGENT_FQN="DATABASE.SCHEMA.AGENT_NAME"
AGENT_DIR_NAME=$(echo "$AGENT_FQN" | tr '.' '_')
WORKSPACE_DIR="${WORKSPACE_DIR:-$(pwd)/$AGENT_DIR_NAME}"
mkdir -p "$WORKSPACE_DIR/versions"
```

**2. ⚠️ CRITICAL: Ask user: Is this a production agent?**

- If **YES**: Ask user for the **fully qualified clone name** (`DATABASE.SCHEMA.CLONE_AGENT_NAME`) where they want the clone created (see step 3)
- If **NO**: Proceed with direct agent access

**3. For production agents, create clone:**

⚠️ **Ask the user:** "What fully qualified name would you like for the clone? (e.g., `DATABASE.SCHEMA.CLONE_NAME`)"

```bash
VERSION="v$(date +%Y%m%d-%H%M)"
VER_DIR="$WORKSPACE_DIR/versions/$VERSION"
mkdir -p "$VER_DIR/evals"

# Get agent config and save to version directory
uv run python ../scripts/get_agent_config.py --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION_NAME --output "$VER_DIR/agent_config.json"

# Create clone using user-provided fully qualified name (CLONE_DATABASE.CLONE_SCHEMA.CLONE_AGENT_NAME)
uv run python ../scripts/create_or_alter_agent.py create --agent-name CLONE_AGENT_NAME --config-file "$VER_DIR/agent_config.json" \
  --database CLONE_DATABASE --schema CLONE_SCHEMA --role ROLE_NAME --connection CONNECTION_NAME

# Use the clone's FQN (CLONE_DATABASE.CLONE_SCHEMA.CLONE_AGENT_NAME) for all subsequent operations
AGENT_NAME="$CLONE_AGENT_NAME"
```

**4. For non-production agents, retrieve config:**

```bash
VERSION="v$(date +%Y%m%d-%H%M)"
VER_DIR="$WORKSPACE_DIR/versions/$VERSION"
mkdir -p "$VER_DIR/evals"

# Get agent config and save to version directory
uv run python ../scripts/get_agent_config.py --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION_NAME --output "$VER_DIR/agent_config.json"
```

**5. Extract instructions for analysis:**

```bash
# Extract instructions from agent config
cat "$VER_DIR/agent_config.json" | jq -r '.instructions_orchestration' > "$VER_DIR/instructions_orchestration.txt"
```

**Now proceed with analysis:**

**Note**: You should have already checked tool types in Step 4.5. If a Cortex Analyst tool was involved, you should have loaded semantic-view skill. This analysis is for non-Cortex Analyst issues only.

**From event table trace:**
Read downloaded JSON trace.

**From fresh test_agent.py response:**
Read downloaded JSON trace.

**Review agent config:**

- Read `$VER_DIR/agent_config.json` to understand tool configuration
- Read `$VER_DIR/instructions_orchestration.txt` to understand routing logic

**Identify inconsistencies:**

- Wrong tool? Check VQR confidence (>0.6 can override routing)
- Response formatting/completeness issues
- Results don't match expectations? Data issues or wrong query

## 7. Present Hypothesis & Solutions

**⚠️ Only reach this step for non-Cortex Analyst issues**
(For Cortex Analyst SQL issues, you should have loaded semantic-view skill in step 6)

**Format hypothesis clearly:**

```
Hypothesis: [What went wrong]

Evidence:
- [Key observation 1]
- [Key observation 2]
- [Root cause]

Proposed Solutions:
A) [Fix option 1]
B) [Fix option 2]
C) [Combination]
```

**After user selects solution, prepare fix in version directory:**

1. Edit `$VER_DIR/instructions_orchestration.txt` with new guidance
2. Update `optimization_log.md` in workspace root with the proposed change
3. Wait for user confirmation before deploying

## 8. Apply Fix

**⚠️ Read `../agent-system-of-record/SKILL.md` for deployment protocols**

Follow the system of record protocols for:

- Deploying instruction changes (see "When modifying agent" section)
- Creating version snapshots after deployment
- Updating `optimization_log.md` with changes and results
- Re-testing the query to verify the fix

**Quick reference:**

- Edit `$VER_DIR/instructions_orchestration.txt` with the fix
- Deploy: `uv run python ../scripts/create_or_alter_agent.py alter --agent-name AGENT_NAME --instructions "$VER_DIR/instructions_orchestration.txt" --database DATABASE --schema SCHEMA --connection CONNECTION_NAME`
- Re-test the original query and verify the fix
- Update `optimization_log.md` with results

## Common Patterns

| Issue                                    | Cause                                                                    | Fix                                                                     |
| ---------------------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------- |
| Wrong tool selected                      | VQR override, ambiguous routing                                          | Add explicit routing rules + VQR guidance                               |
| SQL logic errors                         | Ambiguous date/filter interpretation                                     | Add clear patterns to instructions                                      |
| Pattern matching too broad               | ILIKE matching unintended results                                        | Add "exact match first" guidance                                        |
| Response incomplete                      | Formatting/presentation issue                                            | Add examples (harder to fix)                                            |
| "No data available"                      | Wrong tool or semantic model gap                                         | Check routing + model coverage                                          |
| Semantic view/Cortex Analyst tool issues | SQL generation errors, missing columns, incorrect logic in semantic view | **Load** `semantic-view` skill for semantic view debugging |

## Key Commands Reference

```bash
# ===== Workspace Setup (Do this first) =====
AGENT_FQN="DATABASE.SCHEMA.AGENT_NAME"
AGENT_DIR_NAME=$(echo "$AGENT_FQN" | tr '.' '_')
WORKSPACE_DIR="${WORKSPACE_DIR:-$(pwd)/$AGENT_DIR_NAME}"
mkdir -p "$WORKSPACE_DIR/versions"

VERSION="v$(date +%Y%m%d-%H%M)"
VER_DIR="$WORKSPACE_DIR/versions/$VERSION"
mkdir -p "$VER_DIR/evals"

# ===== Fetch from Event Table (request ID only — fast path) =====
uv run python ../scripts/fetch_events_from_event_table.py \
  --request-id 'REQUEST_ID' --connection CONN --limit 50 --output "$VER_DIR/evals/debug_trace.json"

# ===== Fetch from Event Table (agent FQN known — UDTF + traces) =====
uv run python ../scripts/fetch_events_from_event_table.py --agent-name AGENT --database DB --schema SCHEMA \
  --connection CONN \
  --where "RECORD_ATTRIBUTES:\"ai.observability.record_id\" = 'REQUEST_ID'" \
  --output "$VER_DIR/evals/debug_trace_agent.json"

# ===== Fresh Query Execution =====
uv run python ../scripts/test_agent.py --agent-name AGENT --question "question" \
  --output-file "$VER_DIR/evals/debug.json" --database DATABASE --schema SCHEMA --connection CONNECTION

# ===== Get Agent Config (with workspace setup) =====
uv run python ../scripts/get_agent_config.py --agent-name AGENT_NAME --database DATABASE --schema SCHEMA \
  --connection CONNECTION_NAME --output "$VER_DIR/agent_config.json"

# ===== Deploy Fix =====
uv run python ../scripts/create_or_alter_agent.py alter --agent-name AGENT_NAME --instructions "$VER_DIR/instructions_orchestration.txt" \
  --database DATABASE --schema SCHEMA --connection CONNECTION_NAME
```

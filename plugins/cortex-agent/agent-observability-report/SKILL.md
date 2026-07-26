---
name: agent-observability-report
description: "Generate comprehensive observability reports for Cortex Agents using AI_OBSERVABILITY_EVENTS. Works in any Snowflake deployment. Use when: user wants agent analytics, usage stats, performance metrics, error analysis, feedback summary, or token economics. Triggers: agent observability, agent report, agent analytics, agent usage, agent metrics, agent performance, agent monitoring."
guardrails: references/insight-quality-guardrails.md
validation_required: true
validation_scope: "user_feedback, key_insights"
style:
  emoji: never
---

# Agent Observability Report Skill

## Overview

Universal Cortex Agent observability using `SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS_NORMALIZED` (preferred) or `SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS` UDTFs. Works in any Snowflake deployment.

**Metrics Coverage:** 110 metrics (55 raw, 55 derived) across 8 categories. See `references/metrics_catalog.md`.

## When to Use

- User asks for agent usage report or analytics
- User wants to understand agent performance
- User needs error analysis for an agent
- User wants feedback/satisfaction data
- User wants token usage or cost analysis

## Prerequisites

- Active Snowflake connection
- MONITOR or OWNERSHIP privilege on the AGENT object
- CORTEX_USER database role
- Event table configured for the agent

## Data Source

| UDTF | Location | Description |
|------|----------|-------------|
| `GET_AI_OBSERVABILITY_EVENTS_NORMALIZED` | `SNOWFLAKE.LOCAL` | Preferred. Flattens span attributes into top-level columns (DURATION_MS, SPAN_NAME, INPUT, OUTPUT, USER_NAME, etc.) |
| `GET_AI_OBSERVABILITY_EVENTS` | `SNOWFLAKE.LOCAL` | Alternative. Returns raw schema with RECORD, RECORD_ATTRIBUTES, VALUE columns |

Both UDTFs take 4 arguments: `(database_name VARCHAR, schema_name VARCHAR, agent_name VARCHAR, agent_type VARCHAR)`

Example: `TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS_NORMALIZED('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))`

### Event Types

| Event Type | Purpose |
|------------|---------|
| `CORTEX_AGENT_REQUEST` | Request/response data |
| `AgentV2RequestResponseInfo` | Detailed request metrics |
| `ReasoningAgentStepPlanning-N` | Planning steps, tokens |
| `CORTEX_AGENT_FEEDBACK` | User feedback |
| `SqlExecution_CortexAnalyst` | SQL tool execution |
| `CortexSearchService_*` | Search tool execution |

---

## Workflow

### Step 1: Validate Data Source

**Goal:** Confirm access and collect parameters.

```sql
-- List available agents in the account
SHOW AGENTS IN ACCOUNT;
```

Use `SHOW AGENTS` (or `SHOW AGENTS IN DATABASE {db}` / `SHOW AGENTS IN SCHEMA {db}.{schema}`) to discover agent names.
Then validate data access for a specific agent:

```sql
SELECT COUNT(*) AS event_count
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
  AND TIMESTAMP >= CURRENT_DATE - 30
```

**Parameters to collect:**
- Agent Name
- Database Name (from discovery query)
- Schema Name (from discovery query)
- Time Range (default: 7 days)
- Report depth (summary/detailed/full)

**CHECKPOINT:** If UDTF not accessible or returns error:
- Inform user that AI Observability UDTFs are not available
- Verify user has MONITOR/OWNERSHIP on the AGENT object and CORTEX_USER database role
- Do NOT offer to set it up; user should contact their Snowflake administrator
- **Stop workflow**

---

### Step 2: Select Metric Categories

**Goal:** Let user choose which metric categories to collect.

**USER PROMPT (REQUIRED):** Ask user to select categories:

| Option | Categories Included |
|--------|--------------------|
| All categories | All 8 categories below |
| Usage & Adoption | U1-U20 |
| Performance & Latency | P1-P16 |
| Token Economics | T1-T12 |
| Quality & Reliability | Q1-Q12 |
| User Feedback | F1-F13 |
| Tool Execution | X1-X14 |
| Conversation Behavior | C1-C11 |
| Identity & Context | I1-I12 |

**Note:** Allow multi-select. Default to "All categories" if user doesn't specify.

**⚠️ MANDATORY STOPPING POINT:** Wait for user selection before proceeding.

---

### Step 3: Collect Metrics

**Goal:** Materialize observability events once, then run analytical queries against the materialized table.

**Step 3a: Materialize Events**

Create a temporary materialized table from a single UDTF call. This avoids repeated UDTF invocations (which are slow) by scanning the data once:

```sql
CREATE OR REPLACE TEMPORARY TABLE _obs_events AS
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE TIMESTAMP >= CURRENT_DATE - {DAYS};
```

**Important:** If temp tables are not accessible across queries (session isolation), use a permanent table with a fully qualified name instead:
```sql
CREATE OR REPLACE TABLE {USER_DB}.{USER_SCHEMA}._obs_events AS
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE TIMESTAMP >= CURRENT_DATE - {DAYS};
```

**Step 3b: Run Analytical Queries**

Load queries from `references/queries.md` for selected categories only. All queries reference `_obs_events` (or the fully qualified name) instead of calling the UDTF directly.

Run queries for all selected categories **in parallel** for maximum speed.

**Step 3c: Cleanup**

After all queries complete, drop the materialized table:
```sql
DROP TABLE IF EXISTS _obs_events;
```

**CHECKPOINT:** If category fails, note in `data_limitations` and continue.

---

### Step 4: Calculate Derived Metrics

Compute from raw data per `references/metrics_catalog.md`:
- Percentiles (P50, P90, P95, P99)
- Rates (success_rate, error_rate, feedback_rate)
- Ratios (cache_hit_rate, input_output_ratio)
- Trends (daily_trend, week_over_week)

---

### Step 5: Validate Insights

Apply statistical rigor per `references/insight-quality-guardrails.md`:

| Sample Size | Action |
|-------------|--------|
| n < 10 | Suppress, note in limitations |
| n 10-29 | Add "Low confidence" warning |
| n >= 30 | Report normally |

**Language rules:** Use correlational language ("associated with"), not causal ("causes").

---

### Step 6: Compile Report

```json
{
  "_meta": {
    "skill": "agent-observability-report",
    "version": "1.0",
    "generated_at": "ISO8601",
    "data_source": "SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS_NORMALIZED"
  },
  "usage_adoption": { "raw": {}, "derived": {} },
  "performance_latency": { "raw": {}, "derived": {}, "percentiles": {} },
  "token_economics": { "raw": {}, "derived": {} },
  "quality_reliability": { "raw": {}, "derived": {} },
  "user_feedback": { "raw": {}, "derived": {}, "confidence": "low|moderate|high" },
  "tool_execution": { "raw": {}, "derived": {}, "by_tool": [] },
  "conversation_behavior": { "raw": {}, "derived": {} },
  "key_insights": [],
  "data_limitations": [],
  "recommendations": []
}
```

---

### Step 7: Select Output Format

**Goal:** Let user choose how to receive the report.

**USER PROMPT (REQUIRED):** Ask user for output format:

| Option | Description |
|--------|-------------|
| Display in chat | Show full report directly in conversation |
| Save as JSON | Save to `Reports/{YYYY-MM-DD}/{agent}_observability_{days}days.json` |

**⚠️ MANDATORY STOPPING POINT:** Wait for user selection before proceeding.

---

### Step 8: Deliver Report

**If "Display in chat":**

Present full report in conversation:
```
Agent: {AGENT_NAME}
Period: {DAYS} days

USAGE: X requests, Y users
PERFORMANCE: Avg X ms, P90 Y ms
QUALITY: X% success rate
FEEDBACK: X% satisfaction (n=Y)

[Full metrics for each selected category]
[Key insights]
[Recommendations]
```

**If "Save as JSON":**

1. Save report to: `Reports/{YYYY-MM-DD}/{agent}_observability_{days}days.json`
2. Confirm file path to user

**Follow-up:** Offer deep dive, compare periods, or switch output format

---

## Query Pattern

Preferred (normalized UDTF with top-level columns):
```sql
SELECT {metrics}
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS_NORMALIZED('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE SPAN_NAME = '{EVENT_TYPE}'
  AND TIMESTAMP >= CURRENT_DATE - {DAYS}
```

Fallback (raw UDTF):
```sql
SELECT {metrics}
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE RECORD:"name"::STRING = '{EVENT_TYPE}'
  AND TIMESTAMP >= CURRENT_DATE - {DAYS}
```

| Event Type | Filter (SPAN_NAME for normalized, RECORD:"name" for raw) |
|------------|--------|
| Requests | `CORTEX_AGENT_REQUEST` |
| Details | `AgentV2RequestResponseInfo` |
| Planning | `LIKE 'ReasoningAgentStepPlanning-%'` |
| Feedback | `CORTEX_AGENT_FEEDBACK` |

---

## Troubleshooting

| Issue | Resolution |
|-------|------------|
| UDTF not found | Verify role has MONITOR/OWNERSHIP on AGENT object and CORTEX_USER database role |
| No data | Check agent name (case-sensitive), verify activity in time range |
| Missing metrics | Some require specific event types; note in `data_limitations` |
| Slow queries | Ensure materialization pattern is used (Step 3a); narrow time range if still slow |
| Dirty data casts | Use TRY_TO_BOOLEAN/TRY_TO_NUMBER for RECORD_ATTRIBUTES fields that may contain non-matching types |
| Temp table not found | Session isolation — use permanent table with fully qualified name instead |

---

## Stopping Points

- ✋ Step 1: If event table not accessible (stop workflow)
- ✋ Step 2: Category selection (wait for user)
- ✋ Step 7: Output format selection (wait for user)

---

## References

- `references/metrics_catalog.md` - 110 metrics across 8 categories
- `references/queries.md` - SQL query templates
- `references/insight-quality-guardrails.md` - Statistical validation rules

---
parent_skill: data-quality
---

# Workflow 2: Root Cause Analysis

## Trigger Phrases
- "Why is this table failing?"
- "What's wrong with [TABLE]?"
- "Show me the failures"
- "What are the quality issues?"
- "Root cause analysis"

## When to Load
Data-quality Step 2: failure/investigation intent.

## Template to Use
**Primary:** `schema-root-cause-realtime.sql`
- Shows immediate failures with details via dynamic table discovery
- Use for troubleshooting

**Fallback (if real-time fails):** `schema-root-cause.sql`
- Also uses `SNOWFLAKE.LOCAL` but with a different query structure
- Use when the primary template has issues

## Execution Steps

### Step 0: Preflight Check
- Run `templates/preflight-check.sql` first (as specified in SKILL.md Step 0)
- If preflight fails, stop and report the issue
- If preflight passes, proceed to Step 1

### Step 1: Extract Database and Schema
- From user query: "DEMO_DQ_DB.SALES" → database='DEMO_DQ_DB', schema='SALES'
- If not already provided, ask which DATABASE.SCHEMA to investigate

### Step 2: Execute Template
- Read: `templates/schema-root-cause-realtime.sql`
- This template dynamically discovers tables via `INFORMATION_SCHEMA.TABLES` — no hardcoded table names
- Uses `SNOWFLAKE.LOCAL.DATA_QUALITY_MONITORING_RESULTS()` table function (correct column: `VALUE`, not `metric_value`)
- Column-level info is in `ARGUMENT_NAMES` array (not a `column_name` column)
- Replace: `<database>` → actual database name, `<schema>` → actual schema name
- Execute via `snowflake_sql_execute`

### Step 3: Present Results
```
Root Cause Analysis: DATABASE.SCHEMA

Top Issues Found:

1. TABLE_NAME.COLUMN_NAME - Metric: NULL_COUNT
   Status: FAILED
   Issue: Column contains 3 null values
   Recommendation: Add NOT NULL constraint or fix upstream data

2. TABLE_NAME2.COLUMN_NAME2 - Metric: UNIQUE_COUNT
   Status: FAILED
   Issue: Duplicate values detected
   Recommendation: Add UNIQUE constraint or deduplicate data
```

### Step 4: Next Steps

**Always proactively suggest lineage investigation for any failing table** — this is the most valuable follow-up when quality issues are detected. Data quality RCA tells you *what* is failing; lineage RCA tells you *why* and *where in the pipeline* the bad data originated.

After presenting the results, immediately surface the lineage next step without waiting for the user to ask:

> "I found quality issues in **[list failing tables]**. To understand *why* this is happening, I can trace the upstream data lineage to find where the bad data entered the pipeline. I'll do that now."

Then load the lineage skill and run its root cause analysis workflow:
- Load skill: `data-governance/lineage` → workflow: `root-cause-analysis`
- Pass the failing table(s) as the starting point — the user should not have to re-enter them
- Frame the transition as: "These tables have quality issues — tracing upstream to find the source of the bad data"

**Only pause and use `ask_user_question`** if:
- The user has already said they don't want lineage tracing in this session, OR
- There are more than 10 failing tables (ask which ones to prioritize)

**After lineage investigation**, offer:

| Option | Description |
|--------|-------------|
| **Fix the quality issues** | Address the DMF failures directly (add constraints, fix nulls, deduplicate). |
| **Set up alerts so I'm notified next time** | Load the `sla-alerting` workflow to create monitors for these metrics. |

## Output Format
- Table name and column name (if applicable)
- Metric type that failed
- Specific issue description
- Actionable recommendation for each failure

## What to Show
- Top 5-10 failing metrics (prioritize by severity)
- Column-level details when available
- Specific metric values (e.g., "3 nulls found")
- Clear fix recommendations

## Error Handling
- If real-time template fails → Try fallback template (`schema-root-cause.sql`)
- If both fail → Run `preflight-check.sql` to diagnose
- If no failures found → "All metrics passing! No issues detected."

## Notes
- This is a READ-ONLY workflow (no approval required)
- Digs deeper than health-scoring — shows specific violations, not just counts
- Provides actionable recommendations per failure
- Separate workflow from health scoring (do not auto-chain)

## Halting States
- **Success**: Failures listed with recommendations
- **No failures**: "All metrics passing. No issues detected."
- **No DMFs**: Inform user that monitoring needs to be set up first

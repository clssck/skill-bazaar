---
name: investigate-cortex-agent-evals
description: Use for requests that mention: debug evaluation, investigate agent evaluations, eval timed out, evaluation error, missing eval metrics, analyze low scores, evaluation traces. Provides SQL queries using GET_AI_EVALUATION_DATA, GET_AI_RECORD_TRACE, and GET_AI_OBSERVABILITY_LOGS to debug AI agent evaluation runs.
---

# Agent Evals Deep Dive

## When to Use

Use this skill when debugging or analyzing Cortex Agent evaluation runs:
- Investigating eval failures or task errors
- Analyzing low-scoring records or missing metrics
- Tracing agent execution for a specific record
- Troubleshooting AI Observability event issues

## Key Functions

All evaluation debugging uses these three Snowflake table functions. **Always use these functions** — they are the only way to access evaluation trace data:

| Function | Purpose |
|----------|---------|
| `snowflake.local.GET_AI_EVALUATION_DATA(db, schema, agent, 'CORTEX AGENT', run)` | Evaluation scores, metrics, inputs/outputs |
| `snowflake.local.GET_AI_RECORD_TRACE(db, schema, agent, 'CORTEX AGENT', record_id)` | Full execution trace for one record |
| `snowflake.local.GET_AI_OBSERVABILITY_LOGS(db, schema, agent, 'CORTEX AGENT')` | Log messages and diagnostics |

## Workflow

### Step 1: Gather Parameters

Collect from the user:

| Parameter | Description | Example |
|-----------|-------------|---------|
| **Agent Name** | Fully qualified agent name | `MY_AGENT` |
| **Run Name** | Evaluation run being debugged | `weekly_benchmark_run` |
| **Database** | Database containing the agent | `MY_DB` |
| **Schema** | Schema containing the agent | `MY_SCHEMA` |

Set session variables for reuse:

```sql
SET agent_name = '<AGENT_NAME>';
SET run_name = '<RUN_NAME>';
SET database_name = '<DATABASE>';
SET schema_name = '<SCHEMA>';

USE DATABASE IDENTIFIER($database_name);
USE SCHEMA IDENTIFIER($schema_name);
```

### Step 2: Get Evaluation Overview

Run `GET_AI_EVALUATION_DATA` to see all evaluation results:

```sql
SELECT *
FROM TABLE(snowflake.local.GET_AI_EVALUATION_DATA(
    $database_name, $schema_name, $agent_name, 'CORTEX AGENT', $run_name
))
ORDER BY TIMESTAMP DESC;
```

**What to look for:**
- Each row = one metric evaluation for one record
- `EVAL_AGG_SCORE` = the metric score (missing = computation failed)
- `INPUT` / `OUTPUT` = the evaluated data
- `METRIC_NAME` = which metric was computed

### Step 3: Investigate Based on Issue Type

#### For Low Scores

Find records scoring below threshold:

```sql
SELECT DISTINCT RECORD_ID, INPUT, METRIC_NAME, EVAL_AGG_SCORE
FROM TABLE(snowflake.local.GET_AI_EVALUATION_DATA(
    $database_name, $schema_name, $agent_name, 'CORTEX AGENT', $run_name
))
WHERE EVAL_AGG_SCORE < 0.5
ORDER BY EVAL_AGG_SCORE ASC;
```

Get evaluation criteria and explanations for why scores are low:

```sql
SELECT
    RECORD_ID, METRIC_NAME, EVAL_AGG_SCORE,
    e.VALUE:criteria::VARCHAR AS CRITERIA,
    e.VALUE:explanation::VARCHAR AS EXPLANATION
FROM TABLE(snowflake.local.GET_AI_EVALUATION_DATA(
    $database_name, $schema_name, $agent_name, 'CORTEX AGENT', $run_name
)),
LATERAL FLATTEN(input => EVAL_CALLS) e
ORDER BY EVAL_AGG_SCORE ASC;
```

#### For Missing Metrics

Count metrics per record to find incomplete evaluations:

```sql
SELECT
    RECORD_ID,
    COUNT(DISTINCT METRIC_NAME) AS metrics_computed,
    LISTAGG(DISTINCT METRIC_NAME, ', ') AS computed_metrics
FROM TABLE(snowflake.local.GET_AI_EVALUATION_DATA(
    $database_name, $schema_name, $agent_name, 'CORTEX AGENT', $run_name
))
WHERE METRIC_NAME IS NOT NULL
GROUP BY RECORD_ID
ORDER BY metrics_computed ASC;
```

#### For Task Failures

Check AI_EVALS task execution history:

```sql
SELECT NAME, STATE, ERROR_CODE, ERROR_MESSAGE, SCHEDULED_TIME, COMPLETED_TIME
FROM TABLE(snowflake.information_schema.task_history())
WHERE NAME LIKE 'AI_EVALS_%'
    AND QUERY_TEXT ILIKE '%' || $agent_name || '%'
ORDER BY SCHEDULED_TIME DESC
LIMIT 50;
```

### Step 4: Drill down to Specific Records

For each low-scoring or failed record, trace a specific record's full execution:

```sql
SELECT *
FROM TABLE(snowflake.local.GET_AI_RECORD_TRACE(
    $database_name, $schema_name, $agent_name, 'CORTEX AGENT', '<record_id>'
))
ORDER BY START_TIMESTAMP;
```

**What to look for in traces:**
- Agent execution steps and tool calls
- LLM reasoning and intermediate outputs
- Where in the execution the issue occurred

### Step 5: Check Logs

Get log messages for additional diagnostics:

```sql
SELECT *
FROM TABLE(snowflake.local.GET_AI_OBSERVABILITY_LOGS(
    $database_name, $schema_name, $agent_name, 'CORTEX AGENT'
))
ORDER BY TIMESTAMP DESC
LIMIT 100;
```

## Common Error Patterns

| Pattern | Symptom | First Query |
|---------|---------|-------------|
| **Compute Metrics Failed** | "Compute Metrics failed for run X" | `GET_AI_EVALUATION_DATA` → check which metrics exist |
| **Task Timeout** | AI_EVALS task STATE = 'FAILED' | Task history query → check error message |
| **Missing Events** | No observability data | `GET_AI_EVALUATION_DATA` → check if any records exist |
| **Low Scores** | Scores below threshold | `GET_AI_EVALUATION_DATA` with WHERE clause → criteria/explanations |

## Additional Queries

### Query History

```sql
SELECT QUERY_ID, QUERY_TEXT, EXECUTION_STATUS, ERROR_MESSAGE, START_TIME
FROM TABLE(information_schema.query_history())
WHERE QUERY_TEXT LIKE '%' || $agent_name || '%'
    OR QUERY_TEXT LIKE '%' || $run_name || '%'
ORDER BY START_TIME DESC
LIMIT 100;
```

### Procedure Execution

```sql
SELECT QUERY_ID, QUERY_TEXT, ERROR_MESSAGE, EXECUTION_STATUS, START_TIME
FROM TABLE(information_schema.query_history())
WHERE QUERY_TEXT LIKE '%SYSTEM$EXECUTE_AI_OBSERVABILITY_RUN%'
    AND QUERY_TEXT LIKE '%' || $run_name || '%'
ORDER BY START_TIME DESC
LIMIT 10;
```

## Debugging Tips

1. **Always start with `GET_AI_EVALUATION_DATA`** — it's the single source of truth for evaluation results
2. **Use session variables** — set them once to avoid typos
3. **Compare record counts** — if input records ≠ metric records, some failed
4. **Check criteria/explanations** — LATERAL FLATTEN on EVAL_CALLS reveals why scores are low
5. **Trace low-scoring records** — `GET_AI_RECORD_TRACE` shows the full execution path

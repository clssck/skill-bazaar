# Query Templates for Agent Observability Skill

All queries run against a **materialized table** `_obs_events` created from a single UDTF call (see Step 0 below). This avoids repeated slow UDTF invocations.

**Placeholders:**
- `{DATABASE}` - Agent database name
- `{SCHEMA}` - Agent schema name
- `{AGENT_NAME}` - Agent name
- `{DAYS}` - Number of days lookback
- `{OBS_TABLE}` - Materialized table name (default: `_obs_events`, or fully qualified if session isolation applies)

**Note:** Agent filtering is handled by UDTF arguments at materialization time, not in analytical queries.

---

## Step 0: Materialize Events

Run this **once** before all other queries:

```sql
CREATE OR REPLACE TEMPORARY TABLE _obs_events AS
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE TIMESTAMP >= CURRENT_DATE - {DAYS};
```

If temp tables are not accessible across queries (session isolation), use a permanent table:
```sql
CREATE OR REPLACE TABLE {USER_DB}.{USER_SCHEMA}._obs_events AS
SELECT *
FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_OBSERVABILITY_EVENTS('{DATABASE}', '{SCHEMA}', '{AGENT_NAME}', 'CORTEX AGENT'))
WHERE TIMESTAMP >= CURRENT_DATE - {DAYS};
```

After all queries complete, clean up:
```sql
DROP TABLE IF EXISTS _obs_events;
```

---

## Category 1: Usage & Adoption

### U1-U3: Core Usage Counts

```sql
SELECT 
    COUNT(*) AS total_requests,
    COUNT(DISTINCT RESOURCE_ATTRIBUTES:"snow.user.name"::STRING) AS unique_users,
    COUNT(DISTINCT RESOURCE_ATTRIBUTES:"snow.session.id"::STRING) AS unique_sessions
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
```

### U4: Requests by Agent

```sql
SELECT 
    RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING AS agent_name,
    COUNT(*) AS total_requests,
    COUNT(DISTINCT RESOURCE_ATTRIBUTES:"snow.user.name"::STRING) AS unique_users
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1
ORDER BY 2 DESC
```

### U5-U7: Conversation Starters & Research Mode

```sql
SELECT 
    COUNT(CASE WHEN TRY_TO_BOOLEAN(RECORD_ATTRIBUTES:"snow.ai.observability.agent.first_message_in_thread"::STRING) = TRUE THEN 1 END) AS first_messages,
    COUNT(CASE WHEN TRY_TO_BOOLEAN(RECORD_ATTRIBUTES:"snow.ai.observability.agent.first_message_in_thread"::STRING) = FALSE THEN 1 END) AS follow_up_messages,
    COUNT(CASE WHEN TRY_TO_BOOLEAN(RECORD_ATTRIBUTES:"snow.ai.observability.agent.research_mode"::STRING) = TRUE THEN 1 END) AS research_mode_requests
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'AgentV2RequestResponseInfo'
```

### U8: Daily Request Counts

```sql
SELECT 
    DATE(TIMESTAMP) AS ds,
    COUNT(*) AS requests,
    COUNT(DISTINCT RESOURCE_ATTRIBUTES:"snow.user.name"::STRING) AS unique_users
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1
ORDER BY 1
```

### U12: Hourly Distribution

```sql
SELECT 
    HOUR(TIMESTAMP) AS hour_of_day,
    COUNT(*) AS requests,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct_of_total
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1
ORDER BY 1
```

### U14: Week-over-Week Change

```sql
WITH weekly AS (
    SELECT 
        DATE_TRUNC('week', TIMESTAMP) AS week_start,
        COUNT(*) AS requests
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
    GROUP BY 1
)
SELECT 
    this_week.requests AS this_week_requests,
    last_week.requests AS last_week_requests,
    ROUND(100.0 * (this_week.requests - last_week.requests) / NULLIF(last_week.requests, 0), 2) AS wow_change_pct
FROM weekly this_week
JOIN weekly last_week ON this_week.week_start = last_week.week_start + INTERVAL '7 days'
WHERE this_week.week_start = DATE_TRUNC('week', CURRENT_DATE)
```

### U16: Active User Ratio

```sql
WITH user_requests AS (
    SELECT 
        RESOURCE_ATTRIBUTES:"snow.user.name"::STRING AS user_name,
        COUNT(*) AS request_count
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
    GROUP BY 1
)
SELECT 
    COUNT(*) AS total_users,
    COUNT(CASE WHEN request_count >= 2 THEN 1 END) AS active_users,
    ROUND(100.0 * COUNT(CASE WHEN request_count >= 2 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS active_user_ratio_pct
FROM user_requests
```

---

## Category 2: Performance & Latency

### P1-P2: Response Times

```sql
SELECT 
    COUNT(*) AS total_requests,
    ROUND(AVG(VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS avg_response_time_ms,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS p50_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS p90_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS p95_ms,
    ROUND(PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS p99_ms,
    ROUND(STDDEV(VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS stddev_ms,
    MIN(VALUE:"snow.ai.observability.response_time_ms"::FLOAT) AS min_ms,
    MAX(VALUE:"snow.ai.observability.response_time_ms"::FLOAT) AS max_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
  AND VALUE:"snow.ai.observability.response_time_ms" IS NOT NULL
```

### P2: Agent Duration (from AgentV2)

```sql
SELECT 
    ROUND(AVG(RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration"::FLOAT), 2) AS avg_agent_duration_ms,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration"::FLOAT), 2) AS p50_duration_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration"::FLOAT), 2) AS p90_duration_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'AgentV2RequestResponseInfo'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration" IS NOT NULL
```

### P3: Planning Duration

```sql
SELECT 
    COUNT(*) AS planning_steps,
    ROUND(AVG(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"::FLOAT), 2) AS avg_planning_duration_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"::FLOAT), 2) AS p90_planning_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration" IS NOT NULL
```

### P4: SQL Execution Duration

```sql
SELECT 
    COUNT(*) AS sql_executions,
    ROUND(AVG(RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.duration"::FLOAT), 2) AS avg_sql_duration_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.duration"::FLOAT), 2) AS p90_sql_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'SqlExecution_CortexAnalyst'
```

### P4b: Analyst SQL Generation Duration

```sql
SELECT 
    COUNT(*) AS sql_generations,
    ROUND(AVG(RECORD_ATTRIBUTES:"snow.ai.observability.analyst.sql_generation.duration"::FLOAT), 2) AS avg_sql_gen_duration_ms,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.analyst.sql_generation.duration"::FLOAT), 2) AS p50_sql_gen_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.analyst.sql_generation.duration"::FLOAT), 2) AS p90_sql_gen_ms,
    ROUND(PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.analyst.sql_generation.duration"::FLOAT), 2) AS p95_sql_gen_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'SqlExecution_CortexAnalyst'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.analyst.sql_generation.duration" IS NOT NULL
```

### P5: Search Duration

```sql
SELECT 
    COUNT(*) AS search_invocations,
    ROUND(AVG(RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.duration"::FLOAT), 2) AS avg_search_duration_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.duration"::FLOAT), 2) AS p90_search_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'CortexSearchService_%'
```

### P6: Planning Steps per Request

```sql
WITH steps_per_request AS (
    SELECT 
        TRACE:"trace_id"::STRING AS trace_id,
        MAX(REGEXP_SUBSTR(RECORD:"name"::STRING, 'ReasoningAgentStepPlanning-([0-9]+)', 1, 1, 'e')::INT) + 1 AS planning_steps
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
    GROUP BY 1
)
SELECT 
    ROUND(AVG(planning_steps), 2) AS avg_planning_steps,
    MIN(planning_steps) AS min_steps,
    MAX(planning_steps) AS max_steps,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY planning_steps) AS median_steps
FROM steps_per_request
```

### P13: Slow Request Rate

```sql
SELECT 
    COUNT(*) AS total_requests,
    COUNT(CASE WHEN VALUE:"snow.ai.observability.response_time_ms"::FLOAT > 5000 THEN 1 END) AS slow_requests,
    ROUND(100.0 * COUNT(CASE WHEN VALUE:"snow.ai.observability.response_time_ms"::FLOAT > 5000 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS slow_request_rate_pct
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
```

### Daily Performance Trend

```sql
SELECT 
    DATE(TIMESTAMP) AS ds,
    COUNT(*) AS requests,
    ROUND(AVG(VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS avg_response_time_ms,
    ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS p90_ms
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
  AND VALUE:"snow.ai.observability.response_time_ms" IS NOT NULL
GROUP BY 1
ORDER BY 1
```

---

## Category 3: Token Economics

### T1-T6: Token Counts

```sql
SELECT 
    COUNT(*) AS planning_events,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.input"::STRING)) AS total_input_tokens,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.output"::STRING)) AS total_output_tokens,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.plan"::STRING)) AS total_plan_tokens,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::STRING)) AS total_tokens,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_read_input"::STRING)) AS total_cache_read_tokens,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_write_input"::STRING)) AS total_cache_write_tokens
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
```

### T7: Model Distribution

```sql
SELECT 
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.model"::STRING AS model_used,
    COUNT(*) AS planning_steps,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::STRING)) AS total_tokens
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.model" IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
```

### T8-T12: Derived Token Metrics

```sql
WITH request_tokens AS (
    SELECT 
        TRACE:"trace_id"::STRING AS trace_id,
        SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.input"::STRING)) AS input_tokens,
        SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.output"::STRING)) AS output_tokens,
        SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::STRING)) AS total_tokens,
        SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_read_input"::STRING)) AS cache_read,
        SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_write_input"::STRING)) AS cache_write
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
    GROUP BY 1
)
SELECT 
    COUNT(*) AS total_requests,
    ROUND(AVG(total_tokens), 2) AS avg_tokens_per_request,
    ROUND(AVG(input_tokens), 2) AS avg_input_tokens,
    ROUND(AVG(output_tokens), 2) AS avg_output_tokens,
    ROUND(100.0 * SUM(cache_read) / NULLIF(SUM(cache_read) + SUM(input_tokens), 0), 2) AS cache_hit_rate_pct,
    ROUND(AVG(input_tokens) / NULLIF(AVG(output_tokens), 0), 2) AS input_output_ratio
FROM request_tokens
```

### Daily Token Trend

```sql
SELECT 
    DATE(TIMESTAMP) AS ds,
    COUNT(DISTINCT TRACE:"trace_id"::STRING) AS requests,
    SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::STRING)) AS total_tokens,
    ROUND(SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::STRING)) / 
          NULLIF(COUNT(DISTINCT TRACE:"trace_id"::STRING), 0), 2) AS avg_tokens_per_request
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
GROUP BY 1
ORDER BY 1
```

---

## Category 4: Quality & Reliability

### Q1-Q5: Status Codes

```sql
SELECT 
    VALUE:"snow.ai.observability.response_status_code"::INT AS http_status_code,
    COUNT(*) AS request_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct_of_total
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1
ORDER BY 2 DESC
```

### Q4-Q5: Slow/Tainted Flags

```sql
SELECT 
    COUNT(*) AS total_requests,
    COUNT(CASE WHEN RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.description"::STRING = 'SLOW' THEN 1 END) AS slow_count,
    COUNT(CASE WHEN RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.description"::STRING = 'TAINTED' THEN 1 END) AS tainted_count,
    ROUND(100.0 * COUNT(CASE WHEN RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.description"::STRING = 'SLOW' THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS slow_rate_pct,
    ROUND(100.0 * COUNT(CASE WHEN RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.description"::STRING = 'TAINTED' THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS tainted_rate_pct
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'AgentV2RequestResponseInfo'
```

### Q6-Q7: Success/Error Rates

```sql
SELECT 
    COUNT(*) AS total_requests,
    COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT = 200 THEN 1 END) AS success_count,
    COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT >= 400 THEN 1 END) AS error_count,
    ROUND(100.0 * COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT = 200 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS success_rate_pct,
    ROUND(100.0 * COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT >= 400 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
```

### Daily Error Trend

```sql
SELECT 
    DATE(TIMESTAMP) AS ds,
    COUNT(*) AS total_requests,
    COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT >= 400 THEN 1 END) AS errors,
    ROUND(100.0 * COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT >= 400 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1
ORDER BY 1
```

---

## Category 5: User Feedback

### F1-F6: Feedback Counts

```sql
SELECT 
    COUNT(*) AS total_feedback,
    COUNT(CASE WHEN VALUE:"positive"::BOOLEAN = TRUE THEN 1 END) AS thumbs_up,
    COUNT(CASE WHEN VALUE:"positive"::BOOLEAN = FALSE THEN 1 END) AS thumbs_down,
    ROUND(100.0 * COUNT(CASE WHEN VALUE:"positive"::BOOLEAN = TRUE THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS satisfaction_rate_pct
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_FEEDBACK'
```

### F7: Feedback Rate (Coverage)

```sql
WITH requests AS (
    SELECT COUNT(*) AS total_requests
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
),
feedback AS (
    SELECT COUNT(*) AS total_feedback
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_FEEDBACK'
)
SELECT 
    r.total_requests,
    f.total_feedback,
    ROUND(100.0 * f.total_feedback / NULLIF(r.total_requests, 0), 2) AS feedback_rate_pct
FROM requests r, feedback f
```

### F9-F13: Feedback Categories

```sql
SELECT 
    cat.value::STRING AS feedback_category,
    COUNT(*) AS count
FROM {OBS_TABLE} e,
     LATERAL FLATTEN(input => e.VALUE:"categories") cat
WHERE e.RECORD:"name"::STRING = 'CORTEX_AGENT_FEEDBACK'
  AND e.VALUE:"positive"::BOOLEAN = FALSE
GROUP BY 1
ORDER BY 2 DESC
```

### Feedback Messages (Sample)

```sql
SELECT 
    TIMESTAMP,
    VALUE:"feedback_message"::STRING AS feedback_message,
    VALUE:"categories" AS categories
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_FEEDBACK'
  AND VALUE:"positive"::BOOLEAN = FALSE
  AND VALUE:"feedback_message" IS NOT NULL
ORDER BY TIMESTAMP DESC
LIMIT 20
```

---

## Category 6: Tool Execution

### X9-X11: Tool Invocation Counts

```sql
SELECT 
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.name"::STRING AS tool_name,
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.type"::STRING AS tool_type,
    COUNT(*) AS invocations
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.name" IS NOT NULL
GROUP BY 1, 2
ORDER BY 3 DESC
```

### X10: Cortex Search Details

```sql
SELECT 
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.name"::STRING AS search_service,
    COUNT(*) AS invocations,
    ROUND(AVG(RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.duration"::FLOAT), 2) AS avg_duration_ms,
    AVG(RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.limit"::INT) AS avg_result_limit
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'CortexSearchService_%'
GROUP BY 1
ORDER BY 2 DESC
```

### X11: Cortex Analyst SQL Executions

```sql
SELECT 
    COUNT(*) AS sql_executions,
    ROUND(AVG(RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.duration"::FLOAT), 2) AS avg_duration_ms,
    COUNT(CASE WHEN RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.status"::STRING != 'success' THEN 1 END) AS errors
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'SqlExecution_CortexAnalyst'
```

### X12: Tool Error Rate

```sql
SELECT 
    RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.type"::STRING AS tool_type,
    COUNT(*) AS total_invocations,
    COUNT(CASE WHEN RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.status.code"::STRING != 'success' THEN 1 END) AS errors,
    ROUND(100.0 * COUNT(CASE WHEN RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.status.code"::STRING != 'success' THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS error_rate_pct
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.type" IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
```

---

## Category 7: Conversation Behavior

### C6: Average Conversation Depth

```sql
SELECT 
    ROUND(AVG(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)), 2) AS avg_messages_per_thread,
    MIN(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)) AS min_messages,
    MAX(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)) AS max_messages,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)) AS median_messages
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'AgentV2RequestResponseInfo'
  AND RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages" IS NOT NULL
```

### C7-C8: Multi-turn vs Single-turn

```sql
WITH thread_depths AS (
    SELECT 
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id"::STRING AS thread_id,
        MAX(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)) AS max_messages
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'AgentV2RequestResponseInfo'
    GROUP BY 1
)
SELECT 
    COUNT(*) AS total_threads,
    COUNT(CASE WHEN max_messages = 1 THEN 1 END) AS single_turn_threads,
    COUNT(CASE WHEN max_messages > 1 THEN 1 END) AS multi_turn_threads,
    ROUND(100.0 * COUNT(CASE WHEN max_messages = 1 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS single_turn_rate_pct,
    ROUND(100.0 * COUNT(CASE WHEN max_messages > 1 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS multi_turn_rate_pct
FROM thread_depths
```

### C11: Thread Duration

```sql
WITH thread_times AS (
    SELECT 
        RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id"::STRING AS thread_id,
        MIN(TIMESTAMP) AS first_message,
        MAX(TIMESTAMP) AS last_message,
        MAX(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)) AS message_count
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'AgentV2RequestResponseInfo'
    GROUP BY 1
    HAVING MAX(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"::STRING)) > 1
)
SELECT 
    COUNT(*) AS multi_turn_threads,
    ROUND(AVG(TIMESTAMPDIFF('second', first_message, last_message)), 2) AS avg_thread_duration_seconds,
    ROUND(AVG(message_count), 2) AS avg_messages_per_thread
FROM thread_times
```

---

## Category 8: Identity & Context

### Agent Discovery

```sql
SELECT 
    RECORD_ATTRIBUTES:"snow.ai.observability.object.name"::STRING AS agent_name,
    RECORD_ATTRIBUTES:"snow.ai.observability.database.name"::STRING AS database_name,
    RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"::STRING AS schema_name,
    COUNT(*) AS total_events,
    MIN(TIMESTAMP) AS first_activity,
    MAX(TIMESTAMP) AS last_activity
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1, 2, 3
ORDER BY 4 DESC
```

### User Activity

```sql
SELECT 
    RESOURCE_ATTRIBUTES:"snow.user.name"::STRING AS user_name,
    RESOURCE_ATTRIBUTES:"snow.session.role.primary.name"::STRING AS role_name,
    COUNT(*) AS request_count,
    COUNT(DISTINCT DATE(TIMESTAMP)) AS active_days
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1, 2
ORDER BY 3 DESC
LIMIT 20
```

### Role Distribution

```sql
SELECT 
    RESOURCE_ATTRIBUTES:"snow.session.role.primary.name"::STRING AS role_name,
    COUNT(*) AS request_count,
    COUNT(DISTINCT RESOURCE_ATTRIBUTES:"snow.user.name"::STRING) AS unique_users,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) AS pct_of_requests
FROM {OBS_TABLE}
WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
GROUP BY 1
ORDER BY 2 DESC
```

---

## Composite Queries

### Executive Summary (All Categories)

```sql
WITH requests AS (
    SELECT 
        COUNT(*) AS total_requests,
        COUNT(DISTINCT RESOURCE_ATTRIBUTES:"snow.user.name"::STRING) AS unique_users,
        ROUND(AVG(VALUE:"snow.ai.observability.response_time_ms"::FLOAT), 2) AS avg_response_time_ms,
        ROUND(100.0 * COUNT(CASE WHEN VALUE:"snow.ai.observability.response_status_code"::INT = 200 THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS success_rate_pct
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_REQUEST'
),
feedback AS (
    SELECT 
        COUNT(*) AS total_feedback,
        ROUND(100.0 * COUNT(CASE WHEN VALUE:"positive"::BOOLEAN = TRUE THEN 1 END) / NULLIF(COUNT(*), 0), 2) AS satisfaction_rate_pct
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING = 'CORTEX_AGENT_FEEDBACK'
),
tokens AS (
    SELECT 
        SUM(TRY_TO_NUMBER(RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"::STRING)) AS total_tokens
    FROM {OBS_TABLE}
    WHERE RECORD:"name"::STRING LIKE 'ReasoningAgentStepPlanning-%'
)
SELECT 
    r.total_requests,
    r.unique_users,
    ROUND(r.total_requests / NULLIF(r.unique_users, 0), 2) AS requests_per_user,
    r.avg_response_time_ms,
    r.success_rate_pct,
    f.total_feedback,
    f.satisfaction_rate_pct,
    t.total_tokens,
    ROUND(t.total_tokens / NULLIF(r.total_requests, 0), 2) AS tokens_per_request
FROM requests r, feedback f, tokens t
```

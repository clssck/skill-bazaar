# Metrics Catalog

110 metrics (55 raw, 55 derived) across 8 categories.

## Category 1: Usage & Adoption (20 metrics)

### Raw Metrics (8)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| U1 | total_requests | CORTEX_AGENT_REQUEST | `COUNT(*)` |
| U2 | unique_users | CORTEX_AGENT_REQUEST | `DISTINCT RESOURCE_ATTRIBUTES:"snow.user.name"` |
| U3 | unique_sessions | Any | `DISTINCT RESOURCE_ATTRIBUTES:"snow.session.id"` |
| U4 | requests_by_agent | CORTEX_AGENT_REQUEST | `GROUP BY RECORD_ATTRIBUTES:"snow.ai.observability.object.name"` |
| U5 | first_messages | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.first_message_in_thread" = true` |
| U6 | follow_up_messages | AgentV2RequestResponseInfo | `first_message_in_thread = false` |
| U7 | research_mode_requests | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.research_mode" = true` |
| U8 | daily_request_counts | CORTEX_AGENT_REQUEST | `COUNT(*) GROUP BY DATE(TIMESTAMP)` |

### Derived Metrics (12)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| U9 | requests_per_user | total_requests / unique_users | Avg engagement per user |
| U10 | requests_per_day | total_requests / days_in_period | Daily average volume |
| U11 | requests_per_hour | total_requests / hours_in_period | Hourly average volume |
| U12 | hourly_distribution | COUNT GROUP BY HOUR | Peak hour identification |
| U13 | daily_trend | Slope of daily_request_counts | Growth/decline indicator |
| U14 | week_over_week_change | (this_week - last_week) / last_week | WoW growth % |
| U15 | adoption_rate | unique_users / total_possible_users | User penetration |
| U16 | active_user_ratio | users_with_2plus_requests / unique_users | Retention indicator |
| U17 | new_vs_returning | first_time_users / returning_users | User mix |
| U18 | peak_hour | HOUR with MAX requests | Busiest hour |
| U19 | busiest_day | DAY_OF_WEEK with MAX requests | Busiest day |
| U20 | request_velocity | requests_last_hour / avg_hourly | Real-time activity |

---

## Category 2: Performance & Latency (16 metrics)

### Raw Metrics (6)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| P1 | response_time_ms | CORTEX_AGENT_REQUEST | `VALUE:"snow.ai.observability.response_time_ms"` |
| P2 | agent_duration_ms | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.duration"` |
| P3 | planning_duration_ms | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.duration"` |
| P4 | sql_execution_duration_ms | SqlExecution_CortexAnalyst | `RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.duration"` |
| P5 | search_duration_ms | CortexSearchService_* | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.duration"` |
| P6 | planning_steps_count | ReasoningAgentStepPlanning-N | `MAX(N) per TRACE:trace_id` |

### Derived Metrics (10)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| P7 | avg_response_time | AVG(response_time_ms) | Mean latency |
| P8 | p50_response_time | PERCENTILE_CONT(0.5) | Median latency |
| P9 | p90_response_time | PERCENTILE_CONT(0.9) | 90th percentile |
| P10 | p95_response_time | PERCENTILE_CONT(0.95) | 95th percentile |
| P11 | p99_response_time | PERCENTILE_CONT(0.99) | 99th percentile |
| P12 | response_time_stddev | STDDEV(response_time_ms) | Latency variance |
| P13 | slow_request_rate | COUNT(>5s) / total | % slow requests |
| P14 | planning_time_ratio | planning_duration / total_duration | Planning overhead |
| P15 | tool_time_ratio | tool_duration / total_duration | Tool execution overhead |
| P16 | time_to_first_response | First chunk timestamp - request timestamp | TTFR |

---

## Category 3: Token Economics (12 metrics)

### Raw Metrics (7)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| T1 | input_tokens | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.input"` |
| T2 | output_tokens | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.output"` |
| T3 | plan_tokens | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.plan"` |
| T4 | total_tokens | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.total"` |
| T5 | cache_read_tokens | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_read_input"` |
| T6 | cache_write_tokens | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.token_count.cache_write_input"` |
| T7 | model_used | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.model"` |

### Derived Metrics (5)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| T8 | tokens_per_request | SUM(total_tokens) / total_requests | Avg token consumption |
| T9 | cache_hit_rate | cache_read_tokens / (cache_read + input) | Cache efficiency |
| T10 | cache_efficiency_ratio | cache_read / cache_write | Read vs write balance |
| T11 | input_output_ratio | input_tokens / output_tokens | Prompt vs completion |
| T12 | avg_tokens_per_turn | total_tokens / total_turns | Per-turn consumption |

---

## Category 4: Quality & Reliability (12 metrics)

### Raw Metrics (5)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| Q1 | http_status_code | CORTEX_AGENT_REQUEST | `VALUE:"snow.ai.observability.response_status_code"` |
| Q2 | agent_status_code | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.code"` |
| Q3 | agent_status_description | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.status.description"` |
| Q4 | slow_flag | AgentV2RequestResponseInfo | `status.description = 'SLOW'` |
| Q5 | tainted_flag | AgentV2RequestResponseInfo | `status.description = 'TAINTED'` |

### Derived Metrics (7)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| Q6 | success_rate | COUNT(status=200) / total | % successful |
| Q7 | error_rate | COUNT(status>=400) / total | % failed |
| Q8 | error_count_by_type | GROUP BY status_code | Error distribution |
| Q9 | slow_response_rate | COUNT(SLOW) / total | % flagged slow |
| Q10 | tainted_response_rate | COUNT(TAINTED) / total | % tainted |
| Q11 | availability | (total - errors) / total | Uptime % |
| Q12 | mtbf | total_time / error_count | Mean time between failures |

---

## Category 5: User Feedback (13 metrics)

### Raw Metrics (4)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| F1 | feedback_positive | CORTEX_AGENT_FEEDBACK | `VALUE:"positive"` |
| F2 | feedback_message | CORTEX_AGENT_FEEDBACK | `VALUE:"feedback_message"` |
| F3 | feedback_categories | CORTEX_AGENT_FEEDBACK | `VALUE:"categories"` |
| F4 | feedback_entity_type | CORTEX_AGENT_FEEDBACK | `VALUE:"entity_type"` |

### Derived Metrics (9)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| F5 | thumbs_up_count | COUNT(positive=true) | Positive feedback |
| F6 | thumbs_down_count | COUNT(positive=false) | Negative feedback |
| F7 | feedback_rate | total_feedback / total_requests | Coverage % |
| F8 | satisfaction_rate | thumbs_up / total_feedback | Satisfaction % |
| F9 | category_incorrect_response | COUNT('Incorrect response') | Category breakdown |
| F10 | category_incorrect_source | COUNT('Incorrect data source') | Category breakdown |
| F11 | category_permission_issue | COUNT('Permission issue') | Category breakdown |
| F12 | category_out_of_date | COUNT('Data out-of-date') | Category breakdown |
| F13 | category_too_slow | COUNT('Too slow') | Category breakdown |

---

## Category 6: Tool Execution (14 metrics)

### Raw Metrics (8)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| X1 | tool_name | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.name"` |
| X2 | tool_type | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.type"` |
| X3 | tool_arguments | ReasoningAgentStepPlanning-N | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.planning.tool_selection.argument.*"` |
| X4 | search_service_name | CortexSearchService_* | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.name"` |
| X5 | search_query | CortexSearchService_* | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.query"` |
| X6 | search_limit | CortexSearchService_* | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.tool.cortex_search.limit"` |
| X7 | sql_query_text | SqlExecution_CortexAnalyst | `RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.query"` |
| X8 | sql_query_id | SqlExecution_CortexAnalyst | `RECORD_ATTRIBUTES:"ai.observability.agent.tool.sql_execution.query_id"` |

### Derived Metrics (6)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| X9 | tool_invocation_count | COUNT GROUP BY tool_name | Usage by tool |
| X10 | cortex_search_invocations | COUNT(CortexSearchService_*) | Search tool usage |
| X11 | cortex_analyst_invocations | COUNT(SqlExecution_*) | Analyst tool usage |
| X12 | tool_error_rate | tool_errors / tool_invocations | Tool reliability |
| X13 | avg_tool_duration | AVG(tool_duration_ms) | Tool latency |
| X14 | most_used_tools | TOP N by invocation_count | Tool popularity |

---

## Category 7: Conversation Behavior (11 metrics)

### Raw Metrics (5)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| C1 | thread_id | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.thread_id"` |
| C2 | message_id | CORTEX_AGENT_REQUEST | `RECORD_ATTRIBUTES:"snow.ai.observability.llm.message.id"` |
| C3 | parent_message_id | CORTEX_AGENT_REQUEST | `RECORD_ATTRIBUTES:"snow.ai.observability.llm.parent_message.id"` |
| C4 | messages_in_thread | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.messages"` |
| C5 | first_message_in_thread | AgentV2RequestResponseInfo | `RECORD_ATTRIBUTES:"snow.ai.observability.agent.first_message_in_thread"` |

### Derived Metrics (6)

| ID | Metric | Formula | Description |
|----|--------|---------|-------------|
| C6 | avg_conversation_depth | AVG(messages_in_thread) | Avg turns per conversation |
| C7 | multi_turn_rate | multi_turn_convos / total_convos | % multi-turn |
| C8 | single_turn_rate | single_turn_convos / total_convos | % single-turn |
| C9 | avg_turns_per_session | total_messages / unique_sessions | Session engagement |
| C10 | conversation_completion_rate | completed / started | Completion % |
| C11 | thread_duration | MAX(timestamp) - MIN(timestamp) per thread | Conversation length |

---

## Category 8: Identity & Context (12 metrics)

### Raw Metrics (12)

| ID | Metric | Event Type | Field Path |
|----|--------|------------|------------|
| I1 | user_id | Any | `RESOURCE_ATTRIBUTES:"snow.user.id"` |
| I2 | user_name | Any | `RESOURCE_ATTRIBUTES:"snow.user.name"` |
| I3 | session_id | Any | `RESOURCE_ATTRIBUTES:"snow.session.id"` |
| I4 | role_id | Any | `RESOURCE_ATTRIBUTES:"snow.session.role.primary.id"` |
| I5 | role_name | Any | `RESOURCE_ATTRIBUTES:"snow.session.role.primary.name"` |
| I6 | agent_name | Any | `RECORD_ATTRIBUTES:"snow.ai.observability.object.name"` |
| I7 | agent_id | Any | `RECORD_ATTRIBUTES:"snow.ai.observability.object.id"` |
| I8 | agent_type | Any | `RECORD_ATTRIBUTES:"snow.ai.observability.object.type"` |
| I9 | agent_version_id | Any | `RECORD_ATTRIBUTES:"snow.ai.observability.object.version.id"` |
| I10 | database_name | Any | `RECORD_ATTRIBUTES:"snow.ai.observability.database.name"` |
| I11 | schema_name | Any | `RECORD_ATTRIBUTES:"snow.ai.observability.schema.name"` |
| I12 | trace_id | Any | `TRACE:"trace_id"` |

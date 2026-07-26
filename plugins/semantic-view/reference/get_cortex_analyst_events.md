# Get Cortex Analyst Events Tool

## Tool Description

Fetches Cortex Analyst events from the CORTEX_ANALYST_REQUESTS table checking for feedback and grouping them by source (agent session or individual request). Automatically deduplicates questions within each source and aggregates feedback. Optionally joins with AI_OBSERVABILITY_EVENTS table to fetch agent feedback when agent information is provided.

## Tool Parameters

**Required:**
- `semantic_view_type`: Type parameter for CORTEX_ANALYST_REQUESTS (e.g., `SEMANTIC_VIEW`)
- `semantic_view_name`: Name parameter for CORTEX_ANALYST_REQUESTS (e.g., `DATABASE.SCHEMA.SEMANTIC_VIEW_NAME`)

**Optional:**
- `--agent-full-name`: Agent full name in format `DATABASE.SCHEMA.AGENT_NAME`. When provided, fetches agent feedback from observability events. Agent feedback takes priority over analyst request feedback.
- `--request-ids`: Comma-separated list of request IDs to filter. Can be either analyst request IDs or agent request IDs (e.g., `id1,id2,id3`)
- `--connection`: Snowflake connection name from `~/.snowflake/connections.toml` (default: `snowhouse`)
- `--where`: WHERE clause for filtering (default: `timestamp >= dateadd(day, -7, current_timestamp())`)
- `--order-by`: ORDER BY clause (default: `ORDER BY timestamp DESC`)
- `--limit`: Maximum number of records to fetch before grouping (default: `25`)
- `--output`: Path to save results as JSON (default: print to console)

## Tool Results

**Output format:**
```json
[
  {
    "source": "agent_request_id or analyst request_id",
    "requests": [
      {
        "request_id": "analyst request_id",
        "latest_question": "What is the total sales?",
        "generated_sql": "SELECT SUM(sales) FROM..."
      }
    ],
    "feedback": "positive"
  }
]
```

**Feedback values:**
- `"positive"`: User gave positive feedback
- `"negative"`: User gave negative feedback
- `""`: No feedback provided

**Grouping logic:**
- If request has `agent_request_id` in source field, all requests from that agent session are grouped together
- Otherwise, each request is its own group
- Questions are automatically deduplicated within each group

## Example Usage

```bash
# Get last 25 requests from last 7 days (default)
uv run python get_cortex_analyst_events.py \
  SEMANTIC_VIEW \
  'MY_DATABASE.MY_SCHEMA.MY_SEMANTIC_VIEW'

# Get requests from specific time range
uv run python get_cortex_analyst_events.py \
  SEMANTIC_VIEW \
  'MY_DATABASE.MY_SCHEMA.MY_SEMANTIC_VIEW' \
  --where "timestamp between '2025-11-05 00:00:00' and '2025-11-05 23:59:59'" \
  --order-by "ORDER BY timestamp" \
  --limit 1000

# With agent feedback lookup
uv run python get_cortex_analyst_events.py \
  SEMANTIC_VIEW \
  'MY_DATABASE.MY_SCHEMA.MY_SEMANTIC_VIEW' \
  --agent-full-name "MY_DATABASE.MY_SCHEMA.MY_AGENT" \
  --limit 100

# Save to file
uv run python get_cortex_analyst_events.py \
  SEMANTIC_VIEW \
  'MY_DATABASE.MY_SCHEMA.MY_SEMANTIC_VIEW' \
  --output ./analyst_events.json

# Filter by specific request IDs (analyst or agent)
uv run python get_cortex_analyst_events.py \
  SEMANTIC_VIEW \
  'MY_DATABASE.MY_SCHEMA.MY_SEMANTIC_VIEW' \
  --request-ids "req_123,agent_req_456,req_789"
```

# Get VQR Suggestions Tool

## Tool Description

Retrieves verified query suggestions for a given semantic model by calling the `/api/v2/cortex/analyst/verified-query-suggestions` endpoint in two modes simultaneously:

1. **ca_requests_based**: Suggestions based on Cortex Analyst request history
2. **query_history_based**: Suggestions based on query history analysis

The tool runs both modes in parallel and merges results, prioritizing query_history_based suggestions when questions overlap. This provides a comprehensive set of query suggestions that the semantic model should be optimized to answer.

## Tool Parameters

**Required:**
- `--semantic-view`: Semantic view name (e.g., `DB.SCHEMA.VIEW_NAME`)
- `--output`: Output file path to save raw API response JSON

**Optional:**
- `--limit`: Number of suggestions to return (default: 3)
- `--connection`: Snowflake connection name from `~/.snowflake/connections.toml` or `~/.snowflake/config.toml` (default: from `SNOWFLAKE_CONNECTION_NAME` env var or first available connection)
- `--speed`: `fast` (default) uses Snowscope only. `slow` also queries `information_schema` sources for `query_history_based` mode — **significantly slower but may return more results.** Only use `slow` when `fast` returns insufficient results.

## Tool Results

**Output to file (JSON):**
- Raw API responses from both modes
- Merged suggestions with source tags and deduplication
- Metadata with counts and statistics

**Output to stdout:**
Console displays parallel execution progress, merged suggestions with their source mode (ca_requests_based or query_history_based), scores, verification status, full SQL queries, and deduplication statistics.

## Example Usage

```bash
# Basic usage (fast mode — Snowscope only, default)
uv run python get_vqr_suggestions.py --semantic-view DB.SCHEMA.MY_SEMANTIC_VIEW --output response.json

# With custom limit and connection
uv run python get_vqr_suggestions.py \
  --semantic-view DB.SCHEMA.MY_SEMANTIC_VIEW \
  --output response.json \
  --limit 10

# Slow mode — also queries information_schema (more results, slower)
uv run python get_vqr_suggestions.py \
  --semantic-view DB.SCHEMA.MY_SEMANTIC_VIEW \
  --output response.json \
  --speed slow
```

## Error Handling

The tool has a 2-minute timeout per API request. If it times out, manually generate query suggestions:

1. **Analyze the semantic model YAML**: Review available tables and columns, relationships/joins between tables, defined metrics with their aggregations, and any filters or custom instructions
2. **Generate natural language questions**: Create business-relevant questions that leverage the model's metrics, explore meaningful dimension breakdowns (e.g., by region, category, time), and identify trend analysis opportunities
3. **Write corresponding SQL queries**: Construct queries using the semantic model's tables and columns, respect defined relationships as joins, apply appropriate aggregations for metrics, and follow SQL best practices

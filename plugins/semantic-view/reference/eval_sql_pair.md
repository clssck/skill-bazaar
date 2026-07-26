# Eval SQL Pair Tool

## Tool Description

Executes two SQL queries in parallel against Snowflake and outputs both results to a file for comparison. Useful for comparing generated SQL vs ground truth SQL, or evaluating different SQL implementations. Results are formatted in CSV with automatic limits to prevent overwhelming output (1000 rows or 20KB per query). Supports multi-statement SQL scripts.

## Tool Parameters

**Required:**
- `--output`: Output file path for comparison results

**SQL Input (must provide one for each SQL):**
- `--sql1` or `--sql1-file`: First SQL query as string or path to file
- `--sql2` or `--sql2-file`: Second SQL query as string or path to file
- Can mix and match: e.g., SQL1 from string and SQL2 from file

**Optional:**
- `--connection`: Snowflake connection name from `~/.snowflake/connections.toml` (default: `snowhouse`)

## Tool Results

**Output to specified file:**
- Execution results from both SQL queries in structured format
- CSV-formatted query results with headers
- Error messages if execution fails

**Output format:**
```
================================================================================
SQL 1 RESULTS
================================================================================
1 row(s) returned.

COUNT
123

================================================================================
SQL 2 RESULTS
================================================================================
1 row(s) returned.

COUNT
456
```

## Example Usage

```bash
# With SQL strings
uv run python scripts/eval_sql_pair.py \
  --sql1 "SELECT COUNT(*) FROM orders WHERE status = 'completed'" \
  --sql2 "SELECT COUNT(*) FROM orders" \
  --output results.txt \
  --connection snowhouse

# With SQL files
uv run python scripts/eval_sql_pair.py \
  --sql1-file generated_query.sql \
  --sql2-file ground_truth_query.sql \
  --output comparison_results.txt

# Mix and match: SQL1 from string, SQL2 from file
uv run python scripts/eval_sql_pair.py \
  --sql1 "SELECT * FROM orders LIMIT 10" \
  --sql2-file ground_truth_query.sql \
  --output comparison_results.txt
```

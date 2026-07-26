# Agent Task Tracking Pattern

## How to Use This Feature

When I'm working on tasks, I can now track my complete work cycles including "thinking time" by using the `track_agent_task.py` wrapper.

## Pattern for Agent Use

```bash
SESSION_ID="my_session"

# 1. Before I start analyzing something
uv run python scripts/track_agent_task.py "$SESSION_ID" start "analyze_sql_comparison" \
  "Comparing generated SQL against expected SQL to identify gaps"

# 2. I do my work (all of this time is captured):
#    - Read and understand the question
#    - Analyze the generated SQL
#    - Compare with expected SQL
#    - Identify semantic model gaps
#    - Formulate recommendations

# 3. After I complete the analysis
uv run python scripts/track_agent_task.py "$SESSION_ID" end "analyze_sql_comparison" \
  "Found 3 key differences: missing EVENT_TYPE filter, no lookback period, different column naming"
```

## What Gets Captured

The 18.03s in the demo above captures:

- ⏱️ **My reasoning time** (thinking about the problem)
- 🔧 **Tool execution time** (running commands, reading files)
- 📝 **Response formulation** (writing analysis)

This is the **total wall-clock time** from when I start a task to when I finish it.

## Example: Typical Debug Session

```
⏱️  Task Started: understand_user_question (2.3s)
    ├─ Reading user question
    ├─ Identifying key requirements
    └─ Planning approach

⏱️  Task Started: generate_baseline_sql (22.5s)
    ├─ Calling Cortex Analyst
    ├─ Analyzing generated SQL
    └─ Documenting results

⏱️  Task Started: compare_with_expected (8.7s)
    ├─ Reading expected SQL
    ├─ Identifying differences
    ├─ Categorizing issues
    └─ Formulating recommendations

⏱️  Task Started: apply_optimizations (45.2s)
    ├─ Designing fixes
    ├─ Running semantic_view_set.py
    ├─ Validating changes
    └─ Documenting applied fixes

⏱️  Task Started: validate_results (28.1s)
    ├─ Regenerating SQL
    ├─ Comparing before/after
    └─ Writing summary
```

## Benefits

1. **See where I spend time** - Identify which tasks take longest
2. **Approximate thinking time** - The difference between task time and tool time
3. **Track complete workflows** - End-to-end timing for multi-step processes
4. **Compare approaches** - See if optimizations actually save time

## Limitations

- Cannot break down "thinking" into sub-steps
- Cannot separate pure reasoning from response generation
- Wall-clock time includes network latency, API delays, etc.

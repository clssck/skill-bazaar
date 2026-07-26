---
name: semantic-view-time-tracking
description: Track and report execution time for workflow steps including setup, audit, debug, and validation. Only use when explicitly requested for performance analysis.
applies_to: [semantic-view-audit, semantic-view-debug, semantic-view-setup, semantic-view-validation, all_workflows]
---

# Time Tracking

## When to Load

Load this skill when you need to measure and report timing for:
- Individual tool calls
- Workflow steps
- Complete optimization sessions
- Performance analysis

## Prerequisites

- Python 3 with standard library
- Write access to optimization directory and `/tmp` for state files

## Important Implementation Notes

### State File Location

**CRITICAL**: The `TimeTracker` uses `/tmp` for centralized state file storage:
```python
tracker = TimeTracker(session_id="my_session")
# Creates state file: /tmp/.time_tracker_my_session.json
```

**Why `/tmp`?**
- State persists across different working directories
- Multiple processes can access the same session
- Avoids creating duplicate state files in subdirectories

**Avoid This Common Mistake**:
```python
# ❌ BAD - Creates state file in current directory
tracker = TimeTracker(session_id="my_session", state_file=".time_tracker_my_session.json")

# Different working directories create separate state files:
# /skills/.time_tracker_my_session.json
# /skills/subdir/.time_tracker_my_session.json
# Result: Lost timing data!
```

**Correct Approach**:
```python
# ✅ GOOD - Always use default (stores in /tmp)
tracker = TimeTracker(session_id="my_session")

# ✅ GOOD - Or use absolute path
tracker = TimeTracker(session_id="my_session", 
                     state_file="/tmp/.time_tracker_my_session.json")
```

## Usage

### Agent Task Tracking (Recommended)

Track complete agent tasks that include both reasoning and tool execution using `track_agent_task.py`:

```bash
# Before starting a task
uv run python scripts/track_agent_task.py SESSION_ID start "task_name" "Task description"

# ... agent does work (thinking + tool calls) ...

# After completing a task
uv run python scripts/track_agent_task.py SESSION_ID end "task_name" "Summary of results"
```

**What This Captures:**
- ⏱️ Wall-clock time from task start to completion
- 🧠 Agent reasoning/thinking time (implicit)
- 🔧 Tool execution time
- 📝 Response generation time

**Example Usage:**
```bash
SESSION_ID="my_session"

# Start tracking analysis task
uv run python scripts/track_agent_task.py "$SESSION_ID" start "analyze_sql_differences" \
  "Comparing generated SQL vs expected SQL"

# Agent analyzes, thinks, and executes tools...
# (This all happens in the time between start and end)

# End tracking
uv run python scripts/track_agent_task.py "$SESSION_ID" end "analyze_sql_differences" \
  "Identified 3 key differences"
```

**Example Output:**
```
⏱️  Task Started: analyze_sql_differences
    Comparing generated SQL vs expected SQL

... [agent work happens] ...

✅ Task Completed: analyze_sql_differences (45.2s)
    Identified 3 key differences
```

### View Progress and Generate Reports

**Console Report** (shows completed and in-progress steps):
```bash
uv run python scripts/track_agent_task.py SESSION_ID report
```

Or use Python directly:
```python
from scripts.time_tracker import TimeTracker

tracker = TimeTracker("semantic_view_20251023_202151")
tracker.print_summary()
```

**Export to File**:
```bash
# Export to CSV
uv run python -c "from scripts.time_tracker import TimeTracker; TimeTracker('SESSION_ID').export_csv('timing_report.csv')"

# Export to JSON
uv run python -c "from scripts.time_tracker import TimeTracker; TimeTracker('SESSION_ID').export_json('timing_report.json')"
```

**Cleanup** (remove state file):
```bash
uv run python -c "from scripts.time_tracker import TimeTracker; TimeTracker('SESSION_ID').cleanup()"
```

### 3. Integration Points

#### During Setup
Track semantic model download and VQR extraction:
```bash
SESSION_ID="semantic_view_20251023_224445"
cd semantic_view_TIMESTAMP

# Start setup tracking
uv run python scripts/track_agent_task.py "$SESSION_ID" start "setup" "Running semantic view setup"

# Track download step
uv run python scripts/track_agent_task.py "$SESSION_ID" start "download_semantic_model" "Downloading semantic model YAML"
SNOWFLAKE_CONNECTION_NAME=snowhouse uv run python scripts/download_semantic_view_yaml.py VIEW_NAME .
uv run python scripts/track_agent_task.py "$SESSION_ID" end "download_semantic_model" "Download complete"

# Track VQR extraction
uv run python scripts/track_agent_task.py "$SESSION_ID" start "extract_vqrs" "Extracting VQRs from semantic model"
uv run python scripts/extract_vqrs.py model.yaml vqrs.csv
uv run python scripts/track_agent_task.py "$SESSION_ID" end "extract_vqrs" "Extracted N VQRs"

# End setup tracking
uv run python scripts/track_agent_task.py "$SESSION_ID" end "setup" "Setup complete"

# View progress
uv run python -c "from scripts.time_tracker import TimeTracker; TimeTracker('$SESSION_ID').print_summary()"
```

#### During Audit
Track each VQR evaluation:
```bash
SESSION_ID="semantic_view_20251023_224445"

# Start audit
uv run python scripts/track_agent_task.py "$SESSION_ID" start "audit" "Starting VQR audit"

# Track each VQR
uv run python scripts/track_agent_task.py "$SESSION_ID" start "vqr_001" "Evaluating VQR 001"
# ... evaluation work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "vqr_001" "VQR 001 passed"

# End audit
uv run python scripts/track_agent_task.py "$SESSION_ID" end "audit" "Audit complete"
```

#### During Debug
Track diagnosis and optimization steps:
```bash
SESSION_ID="semantic_view_20251023_224445"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "debug" "Starting debug workflow"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "issue_diagnosis" "Diagnosing issue"
# ... diagnosis work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "issue_diagnosis" "Issue identified"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "root_cause_analysis" "Analyzing root cause"
# ... analysis work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "root_cause_analysis" "Root cause found"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "apply_optimization" "Applying optimization"
# ... optimization work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "apply_optimization" "Optimization applied"

uv run python scripts/track_agent_task.py "$SESSION_ID" end "debug" "Debug complete"
```

#### During Validation
Track validation phases:
```bash
SESSION_ID="semantic_view_20251023_224445"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "semantic_model_validation" "Validating semantic model"
# ... validation work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "semantic_model_validation" "Model valid"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "sql_execution" "Executing SQL queries"
# ... execution work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "sql_execution" "Queries executed"

uv run python scripts/track_agent_task.py "$SESSION_ID" start "data_comparison" "Comparing results"
# ... comparison work ...
uv run python scripts/track_agent_task.py "$SESSION_ID" end "data_comparison" "Results match"
```

## Report Format

### Console Summary
```
=== Time Tracking Summary ===
Total Duration: 125.43s

Step Breakdown:
  setup                          : 12.34s (9.8%)
  ├─ download_semantic_model     : 8.12s (6.5%)
  └─ extract_vqrs                : 4.22s (3.4%)
  
  audit                          : 98.45s (78.5%)
  ├─ vqr_001                     : 5.23s (4.2%)
  ├─ vqr_002                     : 4.89s (3.9%)
  └─ ...
  
  validation                     : 14.64s (11.7%)
  ├─ semantic_model_validation   : 1.23s (1.0%)
  ├─ sql_execution               : 11.02s (8.8%)
  └─ data_comparison             : 2.39s (1.9%)
```

### CSV Export
```csv
step_name,start_time,end_time,duration_seconds,parent_step
setup,2025-10-24T10:00:00,2025-10-24T10:00:12,12.34,
download_semantic_model,2025-10-24T10:00:00,2025-10-24T10:00:08,8.12,setup
extract_vqrs,2025-10-24T10:00:08,2025-10-24T10:00:12,4.22,setup
...
```

### JSON Export
```json
{
  "session_id": "semantic_view_20251024_100000",
  "total_duration": 125.43,
  "steps": [
    {
      "name": "setup",
      "start": "2025-10-24T10:00:00",
      "end": "2025-10-24T10:00:12",
      "duration": 12.34,
      "children": [
        {
          "name": "download_semantic_model",
          "duration": 8.12
        }
      ]
    }
  ]
}
```

## Performance Analysis

Use timing data to:
- Identify bottlenecks in workflow
- Compare optimization approaches
- Track improvements over time
- Generate performance benchmarks

## Best Practices

1. **Use `../scripts/track_agent_task.py` for All Tracking**: This captures complete task duration including thinking time
2. **Start Before Work Begins**: Call `start` right before starting the task
3. **End After Work Completes**: Call `end` immediately after finishing
4. **Hierarchical Steps**: Track parent tasks and sub-tasks for structure
5. **Consistent Naming**: Use clear, descriptive task names
6. **Export Reports**: Save timing data for historical comparison
7. **Minimal Overhead**: Time tracking has negligible performance impact (<0.1%)
8. **Default State Location**: State is stored in `/tmp/.time_tracker_SESSION_ID.json` for cross-process consistency

## Common Issues and Solutions

### Issue: Steps Not Appearing in Summary

**Symptom**: Only some steps show up in report

**Cause**: Missing `end` call for tasks

**Solution**: 
- Ensure every `start` has a matching `end`
- Check for exceptions that skip `end` calls
- Verify state file location: `ls /tmp/.time_tracker_*`

### Issue: "Task Already Started" Warning

**Symptom**: Warning message when starting a task

**Cause**: Task already in progress (not ended properly)

**Solution**:
- Ensure previous task was ended with `track_agent_task.py SESSION_ID end TASK_NAME`
- Check for exceptions that prevented the `end` call
- Manually end the stuck task if needed

## Error Handling

If timing fails (rare):
- Continues execution without throwing errors
- Logs warning
- Returns empty report

## Next Steps

After collecting timing data:
- Review performance bottlenecks
- Optimize slow steps
- Compare with baseline metrics
- Include in optimization reports

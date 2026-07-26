#!/usr/bin/env python3
"""
Enhanced time tracker that captures both tool execution AND agent processing time.
This approximates "thinking time" by tracking wall-clock duration of complete tasks.
"""

import os
import sys
import time

from time_tracker import TimeTracker


def track_agent_task(session_id: str, task_name: str, description: str = "") -> None:
    """
    Track an agent task that includes both thinking and tool execution.

    Usage in conversation:
        Before starting work: track_agent_task(session, "analyze_sql", "Analyzing SQL differences")
        After completing work: end_agent_task(session, "analyze_sql")

    This captures the total wall-clock time including:
    - Agent reasoning/thinking
    - Tool call execution
    - Response generation
    """
    tracker = TimeTracker(session_id)
    tracker.start(task_name)

    if description:
        print(f"⏱️  Task Started: {task_name}")
        print(f"    {description}")
    else:
        print(f"⏱️  Task Started: {task_name}")

    # Store start time for reference
    with open(f"/tmp/.task_{session_id}_{task_name}.start", "w") as f:
        f.write(str(time.time()))


def end_agent_task(session_id: str, task_name: str, summary: str = "") -> float:
    """
    End tracking for an agent task.
    """
    tracker = TimeTracker(session_id)
    duration = tracker.end(task_name)

    # Clean up start marker
    start_file = f"/tmp/.task_{session_id}_{task_name}.start"
    if os.path.exists(start_file):
        os.remove(start_file)

    if summary:
        print(f"✅ Task Completed: {task_name} ({tracker._format_duration(duration)})")
        print(f"    {summary}")

    return float(duration)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print(
            "Usage: track_agent_task.py <session_id> <start|end> <task_name> [description]"
        )
        sys.exit(1)

    session_id = sys.argv[1]
    action = sys.argv[2]
    task_name = sys.argv[3]
    description = sys.argv[4] if len(sys.argv) > 4 else ""

    if action == "start":
        track_agent_task(session_id, task_name, description)
    elif action == "end":
        end_agent_task(session_id, task_name, description)
    else:
        print(f"Unknown action: {action}")
        sys.exit(1)

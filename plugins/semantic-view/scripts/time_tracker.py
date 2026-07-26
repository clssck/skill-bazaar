import csv
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Generator, List, Optional


class TimeTracker:
    """
    Persistent time tracker that saves state to disk.
    Allows tracking across multiple Python processes.
    """

    def __init__(
        self, session_id: Optional[str] = None, state_file: Optional[str] = None
    ):
        self.session_id = (
            session_id or f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )

        # Use /tmp for centralized state file location
        if state_file:
            self.state_file = state_file
        else:
            self.state_file = f"/tmp/.time_tracker_{self.session_id}.json"

        self.steps: Dict[str, Dict[str, Any]] = {}
        self.step_stack: List[str] = []
        self.session_start: Optional[float] = None
        self.session_end: Optional[float] = None

        # Load existing state if available
        self._load_state()

    def _load_state(self) -> None:
        """Load tracker state from disk if it exists."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                    self.steps = state.get("steps", {})
                    self.step_stack = state.get("step_stack", [])
                    self.session_start = state.get("session_start")
                    self.session_end = state.get("session_end")
            except Exception as e:
                print(f"Warning: Could not load state from {self.state_file}: {e}")

    def _save_state(self) -> None:
        """Save tracker state to disk."""
        try:
            state = {
                "session_id": self.session_id,
                "steps": self.steps,
                "step_stack": self.step_stack,
                "session_start": self.session_start,
                "session_end": self.session_end,
            }
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save state to {self.state_file}: {e}")

    def start(self, step_name: str, silent: bool = False) -> None:
        """Start tracking a step."""
        if not self.session_start:
            self.session_start = time.time()

        if step_name in self.steps and self.steps[step_name]["end"] is None:
            if not silent:
                print(f"⚠️  Step '{step_name}' already in progress")
            return

        parent = self.step_stack[-1] if self.step_stack else None

        self.steps[step_name] = {
            "start": time.time(),
            "end": None,
            "duration": None,
            "parent": parent,
            "children": [],
        }

        if parent and step_name not in self.steps[parent]["children"]:
            self.steps[parent]["children"].append(step_name)

        if step_name not in self.step_stack:
            self.step_stack.append(step_name)

        if not silent:
            print(f"⏱️  Started: {step_name}")

        self._save_state()

    def end(self, step_name: str, silent: bool = False) -> float:
        """End tracking a step."""
        if step_name not in self.steps:
            if not silent:
                print(f"⚠️  Step '{step_name}' was never started")
            return 0.0

        if self.steps[step_name]["end"]:
            if not silent:
                print(f"⚠️  Step '{step_name}' already ended")
            return float(self.steps[step_name]["duration"] or 0.0)

        end_time = time.time()
        self.steps[step_name]["end"] = end_time
        duration = end_time - self.steps[step_name]["start"]
        self.steps[step_name]["duration"] = duration

        if self.step_stack and self.step_stack[-1] == step_name:
            self.step_stack.pop()

        if not self.step_stack and not self.session_end:
            self.session_end = end_time

        if not silent:
            print(f"✅ Completed: {step_name} ({self._format_duration(duration)})")

        self._save_state()
        return float(duration)

    @contextmanager
    def step(self, step_name: str, silent: bool = False) -> Generator[None, None, None]:
        """Context manager for tracking a step."""
        self.start(step_name, silent=silent)
        try:
            yield
        except Exception as e:
            self.end(step_name, silent=silent)
            raise e
        else:
            self.end(step_name, silent=silent)

    def track(
        self, step_name: str, silent: bool = False
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Decorator for tracking a function."""

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.step(step_name, silent=silent):
                    return func(*args, **kwargs)

            return wrapper

        return decorator

    def get_total_duration(self) -> float:
        """Get total session duration."""
        if self.session_start and self.session_end:
            return self.session_end - self.session_start
        elif self.session_start:
            return time.time() - self.session_start
        return 0.0

    def get_step_duration(self, step_name: str) -> Optional[float]:
        """Get duration of a specific step."""
        if step_name in self.steps:
            duration = self.steps[step_name]["duration"]
            return float(duration) if duration is not None else None
        return None

    def _format_duration(self, seconds: Optional[float]) -> str:
        """Format duration in human-readable format."""
        if seconds is None:
            return "N/A"
        if seconds < 1:
            return f"{seconds*1000:.0f}ms"
        elif seconds < 60:
            return f"{seconds:.2f}s"
        else:
            mins = int(seconds // 60)
            secs = seconds % 60
            return f"{mins}m {secs:.1f}s"

    def _get_percentage(self, duration: Optional[float], total: float) -> str:
        """Calculate percentage of total duration."""
        if duration is None or total == 0:
            return "N/A"
        return f"{(duration/total)*100:.1f}%"

    def print_summary(self, indent: int = 0) -> None:
        """Print summary of all tracked steps."""
        print("\n" + "=" * 60)
        print("Time Tracking Summary".center(60))
        print("=" * 60)

        total = self.get_total_duration()
        print(f"\nSession ID: {self.session_id}")
        print(f"Total Duration: {self._format_duration(total)}")

        if not self.steps:
            print("\nNo steps tracked.")
            return

        print("\n" + "-" * 60)
        print("Step Breakdown:")
        print("-" * 60)

        root_steps = [
            name for name, data in self.steps.items() if data["parent"] is None
        ]

        for step_name in root_steps:
            self._print_step_tree(step_name, total, 0)

        # Show in-progress steps
        in_progress = [name for name, data in self.steps.items() if data["end"] is None]
        if in_progress:
            print("\n" + "-" * 60)
            print("⚠️  In Progress:")
            for step_name in in_progress:
                elapsed = time.time() - self.steps[step_name]["start"]
                print(f"  - {step_name} ({self._format_duration(elapsed)} elapsed)")

    def _print_step_tree(self, step_name: str, total: float, level: int) -> None:
        """Print hierarchical step tree."""
        step = self.steps[step_name]
        duration = step["duration"]

        indent = "  " * level
        prefix = "├─ " if level > 0 else ""

        duration_str = self._format_duration(duration)
        percentage = self._get_percentage(duration, total)

        print(f"{indent}{prefix}{step_name:35} : {duration_str:>10} ({percentage})")

        for child_name in step["children"]:
            self._print_step_tree(child_name, total, level + 1)

    def export_csv(self, filepath: str) -> None:
        """Export timing data to CSV."""
        with open(filepath, "w", newline="") as csvfile:
            fieldnames = [
                "step_name",
                "start_time",
                "end_time",
                "duration_seconds",
                "parent_step",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            writer.writeheader()

            for step_name, data in self.steps.items():
                start_time = (
                    datetime.fromtimestamp(data["start"]).isoformat()
                    if data["start"]
                    else None
                )
                end_time = (
                    datetime.fromtimestamp(data["end"]).isoformat()
                    if data["end"]
                    else None
                )

                writer.writerow(
                    {
                        "step_name": step_name,
                        "start_time": start_time,
                        "end_time": end_time,
                        "duration_seconds": data["duration"],
                        "parent_step": data["parent"] or "",
                    }
                )

        print(f"\n✅ Timing data exported to: {filepath}")

    def export_json(self, filepath: str) -> None:
        """Export timing data to JSON."""

        def build_tree(step_name: str) -> Dict[str, Any]:
            step = self.steps[step_name]
            return {
                "name": step_name,
                "start": datetime.fromtimestamp(step["start"]).isoformat()
                if step["start"]
                else None,
                "end": datetime.fromtimestamp(step["end"]).isoformat()
                if step["end"]
                else None,
                "duration": step["duration"],
                "children": [build_tree(child) for child in step["children"]],
            }

        root_steps = [
            name for name, data in self.steps.items() if data["parent"] is None
        ]

        output = {
            "session_id": self.session_id,
            "total_duration": self.get_total_duration(),
            "start_time": datetime.fromtimestamp(self.session_start).isoformat()
            if self.session_start
            else None,
            "end_time": datetime.fromtimestamp(self.session_end).isoformat()
            if self.session_end
            else None,
            "steps": [build_tree(step_name) for step_name in root_steps],
        }

        with open(filepath, "w") as jsonfile:
            json.dump(output, jsonfile, indent=2)

        print(f"\n✅ Timing data exported to: {filepath}")

    def cleanup(self) -> None:
        """Remove state file from disk."""
        if os.path.exists(self.state_file):
            try:
                os.remove(self.state_file)
            except Exception as e:
                print(f"Warning: Could not remove state file {self.state_file}: {e}")

    def reset(self) -> None:
        """Reset all tracking data."""
        self.steps.clear()
        self.step_stack.clear()
        self.session_start = None
        self.session_end = None
        self.cleanup()


if __name__ == "__main__":
    # Demo
    tracker = TimeTracker("demo_session")

    tracker.start("setup")
    time.sleep(0.5)

    with tracker.step("download_model"):
        time.sleep(0.3)

    with tracker.step("extract_vqrs"):
        time.sleep(0.2)

    tracker.end("setup")

    tracker.start("audit")
    for i in range(3):
        with tracker.step(f"vqr_{i:03d}"):
            time.sleep(0.1)
    tracker.end("audit")

    tracker.print_summary()

    tracker.export_csv("demo_timing.csv")
    tracker.export_json("demo_timing.json")

    tracker.cleanup()

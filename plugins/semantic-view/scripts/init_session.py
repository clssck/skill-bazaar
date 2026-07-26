#!/usr/bin/env python3
"""
Initialize a semantic-view skill session directory and (optionally) verify host prerequisites.

Cross-platform replacement for the bash snippets that previously lived in
`semantic-view/setup/SKILL.md` (TIMESTAMP=$(date +...) ; mkdir -p ; ls ~/.snowflake/...).
Runs identically on macOS, Linux, and Windows because it relies only on
`pathlib`, `datetime`, and `shutil` from the Python standard library.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def check_prerequisites():
    """
    Verify host-side prerequisites for semantic-view skills.

    Checks performed:
    - `uv` binary is on PATH (cross-platform via shutil.which)
    - At least one Snowflake config file exists at ~/.snowflake/config.toml or
      ~/.snowflake/connections.toml (cross-platform via Path.home())

    Returns:
        dict: {
            "uv_installed": bool,
            "uv_path": str | None,
            "snowflake_config_present": bool,
            "snowflake_config_files": list[str],   # absolute paths of files found
            "all_passed": bool,
        }
    """
    uv_path = shutil.which("uv")
    home = Path.home()
    candidate_configs = [
        home / ".snowflake" / "config.toml",
        home / ".snowflake" / "connections.toml",
    ]
    found_configs = [str(p) for p in candidate_configs if p.exists()]

    result = {
        "uv_installed": uv_path is not None,
        "uv_path": uv_path,
        "snowflake_config_present": len(found_configs) > 0,
        "snowflake_config_files": found_configs,
    }
    result["all_passed"] = result["uv_installed"] and result["snowflake_config_present"]
    return result


def create_session_dir(base_working_dir, sub_dir=None):
    """
    Create a timestamped semantic-view session directory under base_working_dir.

    The directory layout matches the historical bash version:
      <base_working_dir>/semantic_view_<YYYYMMDD_HHMMSS>/[<sub_dir>/]

    Args:
        base_working_dir: Parent directory in which to create the session folder.
        sub_dir: Optional subdirectory to also create inside the session dir
                 (e.g. "optimization" or "creation").

    Returns:
        dict: {
            "timestamp": str,
            "base_working_dir": str,
            "working_dir": str,         # session dir (= base / semantic_view_<TS>)
            "sub_dir": str | None,      # absolute path of sub_dir if requested
        }
    """
    base = Path(base_working_dir).expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    working_dir = base / f"semantic_view_{timestamp}"
    working_dir.mkdir(parents=True, exist_ok=True)

    sub_dir_path = None
    if sub_dir:
        sub_dir_path = working_dir / sub_dir
        sub_dir_path.mkdir(parents=True, exist_ok=True)

    return {
        "timestamp": timestamp,
        "base_working_dir": str(base),
        "working_dir": str(working_dir),
        "sub_dir": str(sub_dir_path) if sub_dir_path else None,
    }


def _print_check_report(checks):
    """Print a human-readable summary of prerequisite check results to stdout."""
    print("Prerequisite checks:")
    print(f"  uv installed:              {'OK' if checks['uv_installed'] else 'MISSING'}"
          + (f"  ({checks['uv_path']})" if checks["uv_path"] else ""))
    print(f"  Snowflake config present:  {'OK' if checks['snowflake_config_present'] else 'MISSING'}")
    for cfg in checks["snowflake_config_files"]:
        print(f"    - {cfg}")
    print(f"  Overall:                   {'PASS' if checks['all_passed'] else 'FAIL'}")


def _build_arg_parser():
    """Build the argparse parser for the init_session CLI."""
    parser = argparse.ArgumentParser(
        description="Initialize a semantic-view session directory and/or verify host prerequisites.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser("check", help="Verify uv and Snowflake config are present on the host.")
    p_check.add_argument("--json", dest="json_output", action="store_true",
                         help="Emit a JSON report on stdout instead of human-readable text.")

    p_init = sub.add_parser("init", help="Create a timestamped session directory under --base-dir.")
    p_init.add_argument("--base-dir", required=True,
                        help="Parent directory in which to create the semantic_view_<timestamp>/ folder.")
    p_init.add_argument("--sub-dir", default=None,
                        help="Optional subdirectory to create inside the session dir (e.g. 'optimization').")
    p_init.add_argument("--json", dest="json_output", action="store_true",
                        help="Emit session paths as JSON on stdout instead of human-readable text.")

    return parser


def main(argv=None):
    """Entry point: dispatch the `check` or `init` subcommand."""
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.command == "check":
        checks = check_prerequisites()
        if args.json_output:
            print(json.dumps(checks, indent=2))
        else:
            _print_check_report(checks)
        return 0 if checks["all_passed"] else 1

    if args.command == "init":
        info = create_session_dir(args.base_dir, args.sub_dir)
        if args.json_output:
            print(json.dumps(info, indent=2))
        else:
            print(f"WORKING_DIR={info['working_dir']}")
            if info["sub_dir"]:
                print(f"SUB_DIR={info['sub_dir']}")
        return 0

    parser.error("unknown command")


if __name__ == "__main__":
    sys.exit(main())

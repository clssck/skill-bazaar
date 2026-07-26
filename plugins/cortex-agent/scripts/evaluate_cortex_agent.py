#!/usr/bin/env python3
"""
Helper script for Cortex Agent evaluations.
Handles YAML config upload to stage and evaluation execution via EXECUTE_AI_EVALUATION.
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

import snowflake.connector


def _validate_identifier(value, label):
    """Validate a Snowflake identifier (database, schema, stage, file format).

    Allows qualified names like DB.SCHEMA.OBJECT. Must start with a letter or
    underscore, then alphanumeric, underscores, and dots only.
    """
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", value):
        print(
            f"Error: Invalid {label}: {value!r}. "
            "Must start with a letter/underscore; only alphanumeric, underscores, "
            "and dots allowed.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _validate_literal(value, label):
    """Validate a value used inside SQL string literals (run name, filename).

    Only allows alphanumeric, underscores, hyphens, and dots. No quotes,
    backslashes, semicolons, or whitespace — preventing SQL injection when
    the value is interpolated inside single quotes.
    """
    if not re.match(r"^[A-Za-z0-9_.\-]+$", value):
        print(
            f"Error: Invalid {label}: {value!r}. "
            "Only alphanumeric, underscores, hyphens, and dots allowed.",
            file=sys.stderr,
        )
        sys.exit(1)
    return value


def _add_common_args(subparser):
    """Add common connection arguments to a subparser."""
    subparser.add_argument(
        "--connection",
        default=os.getenv("SNOWFLAKE_CONNECTION_NAME", "snowhouse"),
        help="Snowflake connection name (default: snowhouse)",
    )
    subparser.add_argument("--database", help="Database name")
    subparser.add_argument("--schema", help="Schema name")


def _connect(args):
    """Create a Snowflake connection and set database/schema context."""
    conn = snowflake.connector.connect(connection_name=args.connection)
    cur = conn.cursor()
    if args.database:
        _validate_identifier(args.database, "database")
        cur.execute(f"USE DATABASE {args.database}")
    if args.schema:
        _validate_identifier(args.schema, "schema")
        cur.execute(f"USE SCHEMA {args.schema}")
    return conn, cur


def upload(args):
    """Upload a YAML config file to a Snowflake stage via PUT."""
    yaml_path = Path(args.yaml_file).resolve()
    if not yaml_path.exists():
        print(f"Error: YAML file not found: {yaml_path}", file=sys.stderr)
        sys.exit(1)

    stage = _validate_identifier(args.stage, "stage")
    conn, cur = _connect(args)

    try:
        # Create file format if it doesn't exist
        ff_name = (
            f"{args.database}.{args.schema}.YAML_FILE_FORMAT"
            if args.database and args.schema
            else "YAML_FILE_FORMAT"
        )
        _validate_identifier(ff_name, "file format")
        cur.execute(f"""
            CREATE FILE FORMAT IF NOT EXISTS {ff_name}
              TYPE = 'CSV'
              FIELD_DELIMITER = NONE
              RECORD_DELIMITER = '\\n'
              SKIP_HEADER = 0
              FIELD_OPTIONALLY_ENCLOSED_BY = NONE
              ESCAPE_UNENCLOSED_FIELD = NONE
        """)
        print(f"✓ File format ready: {ff_name}", file=sys.stderr)

        # Create stage if it doesn't exist
        cur.execute(f"""
            CREATE STAGE IF NOT EXISTS {stage}
              FILE_FORMAT = {ff_name}
        """)
        print(f"✓ Stage ready: {stage}", file=sys.stderr)

        # PUT the YAML file to the stage
        put_sql = (
            f"PUT file://{yaml_path} @{stage} AUTO_COMPRESS=false OVERWRITE=TRUE"
        )
        cur.execute(put_sql)
        result = cur.fetchall()
        print(f"✓ Uploaded {yaml_path.name} to @{stage}", file=sys.stderr)
        for row in result:
            print(f"  {row}", file=sys.stderr)

        # Verify upload
        stage_file = f"@{stage}/{yaml_path.name}"
        cur.execute(f"SELECT $1 FROM {stage_file}")
        rows = cur.fetchall()
        if rows:
            print(
                f"✓ Verified: {stage_file} ({len(rows)} lines)", file=sys.stderr
            )
        else:
            print(f"⚠ Warning: {stage_file} appears empty", file=sys.stderr)

    except Exception as e:
        print(f"Error during upload: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def _execute_ai_evaluation(cur, action, run_name, stage_file):
    """Execute EXECUTE_AI_EVALUATION with validated parameters."""
    _validate_literal(run_name, "run name")
    sql = f"""
        CALL EXECUTE_AI_EVALUATION(
            '{action}',
            OBJECT_CONSTRUCT('run_name', '{run_name}'),
            '{stage_file}'
        )
    """
    cur.execute(sql)
    return cur.fetchall(), cur.description


def start(args):
    """Start an evaluation run via EXECUTE_AI_EVALUATION."""
    stage = _validate_identifier(args.stage, "stage")
    config_filename = _validate_literal(args.config_filename, "config filename")
    run_name = _validate_literal(args.run_name, "run name")

    conn, cur = _connect(args)

    try:
        stage_file = f"@{stage}/{config_filename}"
        result, _ = _execute_ai_evaluation(cur, "START", run_name, stage_file)
        print(f"✓ Evaluation started: {run_name}", file=sys.stderr)
        for row in result:
            print(f"  {row}")

    except Exception as e:
        print(f"Error starting evaluation: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def _get_status_value(result, description):
    """Extract the STATUS column value from a result set."""
    if not description or not result:
        return None
    col_names = [col[0] for col in description]
    if "STATUS" in col_names:
        idx = col_names.index("STATUS")
        return str(result[0][idx])
    return None


def _print_status_table(result, description):
    """Print status result as a tab-separated table."""
    if description and result:
        col_names = [col[0] for col in description]
        print("\t".join(col_names))
        for row in result:
            print("\t".join(str(v) for v in row))
    else:
        print("No status returned.", file=sys.stderr)


def status(args):
    """Check evaluation status via EXECUTE_AI_EVALUATION.

    If --wait is specified, polls until COMPLETED or FAILED.
    """
    stage = _validate_identifier(args.stage, "stage")
    config_filename = _validate_literal(args.config_filename, "config filename")
    run_name = _validate_literal(args.run_name, "run name")

    conn, cur = _connect(args)
    stage_file = f"@{stage}/{config_filename}"

    try:
        if not args.wait:
            # Single status check
            result, description = _execute_ai_evaluation(
                cur, "STATUS", run_name, stage_file
            )
            _print_status_table(result, description)
            return

        # Polling mode
        interval = args.poll_interval
        timeout = args.timeout
        elapsed = 0
        terminal_statuses = {"COMPLETED", "FAILED"}

        print(
            f"Polling every {interval}s (timeout {timeout}s)...",
            file=sys.stderr,
        )

        while elapsed < timeout:
            result, description = _execute_ai_evaluation(
                cur, "STATUS", run_name, stage_file
            )
            status_val = _get_status_value(result, description)
            print(
                f"  [{elapsed:>4}s] STATUS: {status_val or 'UNKNOWN'}",
                file=sys.stderr,
            )

            if status_val in terminal_statuses:
                _print_status_table(result, description)
                if status_val == "FAILED":
                    sys.exit(1)
                return

            time.sleep(interval)
            elapsed += interval

        print(
            f"Timeout after {timeout}s. Last status: {status_val or 'UNKNOWN'}",
            file=sys.stderr,
        )
        _print_status_table(result, description)
        sys.exit(2)

    except Exception as e:
        print(f"Error checking status: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Cortex Agent evaluation helper — upload configs and run evaluations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- upload subcommand ---
    upload_parser = subparsers.add_parser(
        "upload", help="Upload YAML config to a Snowflake stage"
    )
    _add_common_args(upload_parser)
    upload_parser.add_argument(
        "--yaml-file", required=True, help="Local path to the YAML config file"
    )
    upload_parser.add_argument(
        "--stage",
        required=True,
        help="Fully qualified stage name (e.g., MYDB.MYSCHEMA.EVAL_CONFIG_STAGE)",
    )

    # --- start subcommand ---
    start_parser = subparsers.add_parser("start", help="Start an evaluation run")
    _add_common_args(start_parser)
    start_parser.add_argument(
        "--run-name", required=True, help="Name for the evaluation run"
    )
    start_parser.add_argument(
        "--stage",
        required=True,
        help="Fully qualified stage name where config is stored",
    )
    start_parser.add_argument(
        "--config-filename",
        required=True,
        help="YAML config filename on the stage",
    )

    # --- status subcommand ---
    status_parser = subparsers.add_parser(
        "status", help="Check evaluation run status"
    )
    _add_common_args(status_parser)
    status_parser.add_argument(
        "--run-name", required=True, help="Name of the evaluation run"
    )
    status_parser.add_argument(
        "--stage",
        required=True,
        help="Fully qualified stage name where config is stored",
    )
    status_parser.add_argument(
        "--config-filename",
        required=True,
        help="YAML config filename on the stage",
    )
    status_parser.add_argument(
        "--wait",
        action="store_true",
        help="Poll until evaluation reaches COMPLETED or FAILED",
    )
    status_parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Seconds between status polls (default: 30)",
    )
    status_parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Max seconds to wait before giving up (default: 600)",
    )

    args = parser.parse_args()

    if args.command == "upload":
        upload(args)
    elif args.command == "start":
        start(args)
    elif args.command == "status":
        status(args)


if __name__ == "__main__":
    main()

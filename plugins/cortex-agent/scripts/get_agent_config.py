#!/usr/bin/env python3
"""
Script to retrieve agent configuration from Snowflake.
Fetches the complete agent specification including instructions and tools.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import requests
import snowflake.connector


def find_latest_version(workspace_dir: Path) -> Path | None:
    """Find the most recent version directory in the workspace.
    
    Version directories follow the pattern vYYYYMMDD-HHMM inside
    the versions/ subdirectory of the workspace.
    
    Args:
        workspace_dir: Path to the agent workspace directory
        
    Returns:
        Path to the latest version directory, or None if not found
    """
    versions_dir = workspace_dir / "versions"
    if not versions_dir.exists():
        return None
    
    version_dirs = sorted(
        [d for d in versions_dir.iterdir() if d.is_dir() and d.name.startswith('v')],
        reverse=True  # Most recent first
    )
    
    return version_dirs[0] if version_dirs else None


def get_agent_config(agent_name: str, database: str, schema: str, connection_name: str) -> dict:
    """
    Retrieve agent configuration via REST API.
    
    Args:
        agent_name: Name of the agent
        database: Database name
        schema: Schema name
        connection_name: Snowflake connection name
        
    Returns:
        Agent configuration as dictionary
    """
    conn = snowflake.connector.connect(connection_name=connection_name)
    
    url = f"https://{conn.host}/api/v2/databases/{database}/schemas/{schema}/agents/{agent_name}"
    
    headers = {
        "Authorization": f'Snowflake Token="{conn.rest.token}"',
        "Content-Type": "application/json"
    }
    
    response = requests.get(url, headers=headers, verify=False)
    
    if response.status_code != 200:
        raise Exception(f"Failed to retrieve agent config: {response.status_code} - {response.text}")
    
    return response.json()


def main():
    parser = argparse.ArgumentParser(
        description="Retrieve agent configuration from Snowflake",
        epilog="""
Examples:
  # Output to stdout
  %(prog)s --agent-name MY_AGENT

  # Output to specific file path (explicit path)
  %(prog)s --agent-name MY_AGENT --output config.json

  # Output to workspace (auto-resolves latest version folder)
  %(prog)s --agent-name MY_AGENT --workspace MY_DB_SCHEMA_AGENT --output-name current_agent_spec.json

  # Full example with workspace
  %(prog)s --agent-name MY_AGENT --database MY_DB --schema AGENTS \\
    --workspace MY_DB_AGENTS_MY_AGENT --output-name current_agent_spec.json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--agent-name", required=True, help="Name of the agent")
    parser.add_argument("--database", default="SNOWFLAKE_INTELLIGENCE", help="Database name (default: SNOWFLAKE_INTELLIGENCE)")
    parser.add_argument("--schema", default="AGENTS", help="Schema name (default: AGENTS)")
    parser.add_argument("--connection", default=os.getenv("SNOWFLAKE_CONNECTION_NAME", "snowhouse"), 
                        help="Snowflake connection name")
    parser.add_argument("--output", help="Output file path where agent config will be saved (default: stdout)")
    parser.add_argument("--workspace", help="Path to agent workspace directory (auto-resolves latest version folder)")
    parser.add_argument("--output-name", help="Output filename when using --workspace (e.g., current_agent_spec.json)")
    
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.workspace and args.output:
        parser.error("Cannot use both --output and --workspace. Use --output for explicit paths or --workspace with --output-name for auto-resolution.")
    
    if args.workspace and not args.output_name:
        parser.error("--output-name is required when using --workspace")
    
    if args.output_name and not args.workspace:
        parser.error("--output-name requires --workspace")
    
    # Determine output path
    output_path = None
    if args.workspace:
        workspace_dir = Path(args.workspace)
        if not workspace_dir.exists():
            print(f"Error: Workspace directory does not exist: {workspace_dir}", file=sys.stderr)
            sys.exit(1)
        
        version_dir = find_latest_version(workspace_dir)
        if version_dir is None:
            print(f"Error: No version directory found in {workspace_dir}/versions/", file=sys.stderr)
            sys.exit(1)
        
        output_path = version_dir / args.output_name
        print(f"Auto-resolved output path: {output_path}", file=sys.stderr)
    elif args.output:
        output_path = Path(args.output)
    
    try:
        config = get_agent_config(args.agent_name, args.database, args.schema, args.connection)
        
        if "agent_spec" in config:
            spec = config["agent_spec"]
            if isinstance(spec, str):
                config = json.loads(spec)
            else:
                config = spec
        
        output = json.dumps(config, indent=2)
        
        if output_path:
            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w') as f:
                f.write(output)
            print(f"✓ Agent configuration saved to {output_path}", file=sys.stderr)
        else:
            print(output)
            
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

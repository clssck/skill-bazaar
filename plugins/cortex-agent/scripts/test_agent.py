#!/usr/bin/env python3
"""
Test agent with a question and save the response.

This script sends a request to a Snowflake agent and saves the response
to the appropriate location in the agent's workspace.
"""

import argparse
import os
import json
import requests
import snowflake.connector
import urllib3
from pathlib import Path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


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


def test_agent(agent_name, question, output_file, 
               database="SNOWFLAKE_INTELLIGENCE", 
               schema="AGENTS",
               connection_name=None,
               enable_research_mode=False,
               current_date_override=None):
    """
    Send a request to an agent and save the response.
    
    Args:
        agent_name: Name of the agent
        question: Question to ask the agent
        output_file: Path to save the response
        database: Database name (default: SNOWFLAKE_INTELLIGENCE)
        schema: Schema name (default: AGENTS)
        connection_name: Snowflake connection name (default: from env or 'snowhouse')
        enable_research_mode: Enable experimental staged reasoning agent flow type (default: False)
        current_date_override: Optional date string timestamp (e.g., "2024-01-01") for CurrentDateOverride experimental flag (default: None)
    """
    if connection_name is None:
        connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME", "snowhouse")
    
    conn = snowflake.connector.connect(connection_name=connection_name)
    
    try:
        cursor = conn.cursor()
        
        token = conn.rest.token
        host = conn.host
        
        url = f"https://{host}/api/v2/databases/{database}/schemas/{schema}/agents/{agent_name}:run"
        
        headers = {
            "Authorization": f"Snowflake Token=\"{token}\"",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": question
                        }
                    ]
                }
            ]
        }

        # Add experimental flags if any are enabled
        experimental_flags = {}

        if enable_research_mode:
            experimental_flags["ReasoningAgentFlowType"] = "staged"
            print("Research mode enabled: staged reasoning agent flow type")

        if current_date_override:
            experimental_flags["CurrentDateOverride"] = current_date_override
            print(f"Current date override enabled: {current_date_override}")

        if experimental_flags:
            payload["experimental"] = experimental_flags
        
        print(f"Sending request to agent {database}.{schema}.{agent_name}")
        print(f"Question: '{question}'")
        print(f"Streaming response...\n")
        
        response = requests.post(url, headers=headers, json=payload, stream=True, verify=False)
        
        if response.status_code != 200:
            print(f"✗ Error: Status Code {response.status_code}")
            print(f"Response: {response.text}")
            return None
        else:
            final_response = None
            event_type = None
            
            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith('event: '):
                        event_type = decoded[7:].strip()
                    elif decoded.startswith('data: '):
                        try:
                            data = json.loads(decoded[6:])
                            if event_type == 'response':
                                final_response = data
                        except:
                            pass
            
            if final_response:
                print("\n" + "="*60)
                print("✓ Request completed successfully!")
                print(f"Saving response to: {output_file}")
                
                # Ensure directory exists
                Path(output_file).parent.mkdir(parents=True, exist_ok=True)
                
                with open(output_file, 'w') as f:
                    f.write(json.dumps(final_response, indent=2))
                
                print(f"✓ Response saved to {output_file}")
                print("="*60)
                
                # Extract and display the final text answer
                if 'content' in final_response:
                    for item in final_response['content']:
                        if item.get('type') == 'text':
                            print(f"\nAgent Response:\n{item['text']}\n")
                
                return final_response
            else:
                print("✗ No final response received")
                return None
            
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test agent with a question and save the response",
        epilog="""
Examples:
  # Output to specific file path (explicit path)
  %(prog)s --agent-name MY_AGENT --question "What can you do?" --output-file ./response.json

  # Output to workspace (auto-resolves latest version folder)
  %(prog)s --agent-name MY_AGENT --question "What can you do?" \\
    --workspace MY_DB_AGENTS_MY_AGENT --output-name test_verification.json

  # Full example with workspace
  %(prog)s --agent-name MY_AGENT --question "What can you do?" \\
    --database MY_DB --schema AGENTS \\
    --workspace MY_DB_AGENTS_MY_AGENT --output-name test_verification.json
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--agent-name", required=True, help="Name of the agent")
    parser.add_argument("--question", required=True, help="Question to ask the agent")
    parser.add_argument("--output-file", help="Path to save the response (explicit path)")
    parser.add_argument("--workspace", help="Path to agent workspace directory (auto-resolves latest version folder)")
    parser.add_argument("--output-name", help="Output filename when using --workspace (e.g., test_verification.json)")
    parser.add_argument("--database", default="SNOWFLAKE_INTELLIGENCE", help="Database name (default: SNOWFLAKE_INTELLIGENCE)")
    parser.add_argument("--schema", default="AGENTS", help="Schema name (default: AGENTS)")
    parser.add_argument("--connection", help="Snowflake connection name")
    parser.add_argument("--current-date-override", default=None, help="Override current date (e.g., '2024-01-15') for testing time-sensitive queries (default: None)")
    parser.add_argument("--enable-research-mode", default=False, help="Enable research mode (default: False)")
    
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.workspace and args.output_file:
        parser.error("Cannot use both --output-file and --workspace. Use --output-file for explicit paths or --workspace with --output-name for auto-resolution.")
    
    if args.workspace and not args.output_name:
        parser.error("--output-name is required when using --workspace")
    
    if args.output_name and not args.workspace:
        parser.error("--output-name requires --workspace")
    
    if not args.workspace and not args.output_file:
        parser.error("Either --output-file or --workspace with --output-name is required")
    
    # Determine output path
    if args.workspace:
        workspace_dir = Path(args.workspace)
        if not workspace_dir.exists():
            print(f"Error: Workspace directory does not exist: {workspace_dir}")
            exit(1)
        
        version_dir = find_latest_version(workspace_dir)
        if version_dir is None:
            print(f"Error: No version directory found in {workspace_dir}/versions/")
            exit(1)
        
        output_path = str(version_dir / args.output_name)
        print(f"Auto-resolved output path: {output_path}")
    else:
        output_path = args.output_file
    
    test_agent(args.agent_name, args.question, output_path, args.database, args.schema, args.connection, current_date_override=args.current_date_override, enable_research_mode=args.enable_research_mode)

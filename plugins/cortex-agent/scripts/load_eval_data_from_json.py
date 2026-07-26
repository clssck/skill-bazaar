#!/usr/bin/env python3
"""
Load evaluation dataset from JSON file into Snowflake table. Should be use after annotating the dataset with `agent_events_explorer.py`.

USAGE:
    uv run python load_eval_data_from_json.py <json_file> <database> <schema> <agent_name> --connection <connection_name>
OUTPUT:
    Creates table: <database>.<schema>.EVAL_DATASET_{<agent_name>}
    Table schema:
      - timestamp (TIMESTAMP)
      - request_id (VARCHAR)
      - question (VARCHAR)
      - answer (VARCHAR)
      - expected_answer (VARCHAR)
      - feedback (VARIANT)
      - trace (VARIANT)
"""

import argparse
import sys
import json
import snowflake.connector
import os
from pathlib import Path


def load_eval_data(json_file, database, schema, agent_name, connection_name=None):
    """
    Load evaluation dataset from JSON file into Snowflake table.
    
    Args:
        json_file (str): Path to JSON file
        database (str): Database name
        schema (str): Schema name
        agent_name (str): Agent name
        connection_name (str): Snowflake connection name (optional)
    
    Returns:
        int: Number of records loaded
    """
    # Use provided connection or fall back to environment/default
    if connection_name is None:
        connection_name = os.getenv("SNOWFLAKE_CONNECTION_NAME") or "nvytla-snowhouse-all"
    
    table_name = f"EVAL_DATASET_{agent_name}"
    table_fqn = f"{database}.{schema}.{table_name}"
    
    # Connect to Snowflake
    conn = snowflake.connector.connect(connection_name=connection_name)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    print(f"Creating table if not exists: {table_fqn}")
    cursor.execute(f"""
    CREATE TABLE IF NOT EXISTS {table_fqn} (
      timestamp TIMESTAMP,
      request_id VARCHAR,
      question VARCHAR,
      answer VARCHAR,
      expected_answer VARCHAR,
      feedback VARIANT,
      trace VARIANT
    )
    """)
    
    # Read the JSON file
    print(f"Reading JSON file: {json_file}")
    with open(json_file, 'r') as f:
        data = json.load(f)
    
    print(f"Found {len(data)} records to load")
    
    # Insert each record
    for i, record in enumerate(data, 1):
        cursor.execute(f"""
            INSERT INTO {table_fqn}
            (timestamp, request_id, question, answer, expected_answer, feedback, trace)
            SELECT %s, %s, %s, %s, %s, PARSE_JSON(%s), PARSE_JSON(%s)
        """, (
            record.get('timestamp'),
            record.get('request_id'),
            record.get('question'),
            record.get('answer'),
            record.get('expected_answer'),
            record.get('feedback'),
            record.get('trace')
        ))
        
        if i % 10 == 0:
            print(f"Loaded {i}/{len(data)} records...")
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\n✓ Successfully loaded {len(data)} records into {table_fqn}")
    return len(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Load evaluation dataset from JSON file into Snowflake table",
        epilog="""
Examples:
  %(prog)s --json-file eval_dataset.json --database TEMP --schema NVYTLA --agent-name MY_AGENT
  %(prog)s --json-file eval_dataset.json --database TEMP --schema NVYTLA --agent-name MY_AGENT --connection my_connection

Output:
  Creates table: <database>.<schema>.EVAL_DATASET_<agent_name>
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--json-file", required=True, help="Path to the eval dataset JSON file")
    parser.add_argument("--database", required=True, help="Database name (e.g., TEMP)")
    parser.add_argument("--schema", required=True, help="Schema name (e.g., NVYTLA)")
    parser.add_argument("--agent-name", required=True, help="Agent name (e.g., AIOBS_PDS_AGENT_CLONE_V3)")
    parser.add_argument("--connection", help="Snowflake connection name")
    
    args = parser.parse_args()
    
    # Verify JSON file exists
    if not Path(args.json_file).exists():
        print(f"Error: JSON file not found: {args.json_file}")
        sys.exit(1)
    
    print(f"\nLoad Evaluation Data")
    print(f"{'='*80}")
    print(f"JSON File: {args.json_file}")
    print(f"Target Table: {args.database}.{args.schema}.EVAL_DATASET_{args.agent_name}")
    print(f"Connection: {args.connection or 'default'}")
    print(f"{'='*80}\n")
    
    try:
        load_eval_data(args.json_file, args.database, args.schema, args.agent_name, args.connection)
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)

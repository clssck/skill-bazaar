#!/usr/bin/env python3
"""
Create or alter Snowflake Cortex Agents via SQL.

This script consolidates agent creation and modification into a single tool with two commands:
- create: Create a new agent from a full specification (CREATE OR REPLACE AGENT)
- alter: Modify an existing agent (ALTER AGENT)
"""

import argparse
import json
import os
import sys

import snowflake.connector

# Keys that belong in the SPECIFICATION (MODIFY LIVE VERSION / FROM SPECIFICATION)
SPECIFICATION_KEYS = {
    "models", "instructions", "orchestration", "tools", "tool_resources",
    "experimental"
}

# Keys that are SET properties (ALTER AGENT SET / CREATE AGENT params)
SET_KEYS = {"comment", "profile"}

# All valid top-level keys in input JSON
VALID_TOP_LEVEL_KEYS = SPECIFICATION_KEYS | SET_KEYS


def deep_merge(base: dict, changes: dict) -> dict:
    """
    Deep merge changes into base dictionary.
    
    For nested dicts, recursively merges. For other types (including lists),
    the value from changes replaces the base value.
    
    Args:
        base: The base dictionary to merge into
        changes: The changes to apply
        
    Returns:
        dict: New dictionary with changes merged into base
    """
    result = base.copy()
    for key, value in changes.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_current_agent_spec(merge_with_file: str) -> dict:
    """
    Load and parse the current agent specification from a get_agent_config.py output file.
    
    Accepts two formats:
    1. Wrapper format (legacy): {"agent_spec": "{\"instructions\": {...}, ...}", "name": "AGENT_NAME", ...}
    2. Bare spec format: {"instructions": {...}, "tools": [...], ...}
    
    Args:
        merge_with_file: Path to the current_agent_spec.json file
        
    Returns:
        dict: Parsed agent specification
        
    Raises:
        FileNotFoundError: If file doesn't exist
        ValueError: If JSON parsing fails
    """
    if not os.path.exists(merge_with_file):
        raise FileNotFoundError(f"Merge-with file not found: {merge_with_file}")
    
    with open(merge_with_file, 'r') as f:
        data = json.load(f)
    
    # Handle both wrapper format ({"agent_spec": "..."}) and bare spec format ({"instructions": ...})
    if "agent_spec" not in data:
        # Bare spec format — already a parsed agent spec dict
        return data
    
    agent_spec_str = data["agent_spec"]
    if isinstance(agent_spec_str, str):
        try:
            return json.loads(agent_spec_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse agent_spec JSON string: {e}")
    elif isinstance(agent_spec_str, dict):
        # Already a dict (shouldn't happen but handle it)
        return agent_spec_str
    else:
        raise ValueError(f"agent_spec must be a string or dict, got {type(agent_spec_str)}")


def validate_agent_spec(agent_spec: dict) -> list:
    """
    Validate agent specification JSON structure.
    
    Args:
        agent_spec: The agent specification dictionary
        
    Returns:
        list: List of validation errors (empty if valid)
    """
    errors = []
    
    # Check that agent_spec is a dictionary
    if not isinstance(agent_spec, dict):
        errors.append("Agent specification must be a JSON object")
        return errors
    
    # Check for invalid top-level keys
    invalid_keys = set(agent_spec.keys()) - VALID_TOP_LEVEL_KEYS
    if invalid_keys:
        errors.append(f"Invalid top-level keys found: {', '.join(sorted(invalid_keys))}")
        errors.append(f"Valid keys are: {', '.join(sorted(VALID_TOP_LEVEL_KEYS))}")
    
    # Validate models structure
    if "models" in agent_spec:
        models = agent_spec["models"]
        if not isinstance(models, dict):
            errors.append("'models' must be an object")
        elif "orchestration" in models:
            if not isinstance(models["orchestration"], str):
                errors.append("'models.orchestration' must be a string")
    
    # Validate instructions structure
    if "instructions" in agent_spec:
        instructions = agent_spec["instructions"]
        if not isinstance(instructions, dict):
            errors.append("'instructions' must be an object")
        else:
            valid_instruction_keys = {"orchestration", "response", "system", "sample_questions"}
            for key, value in instructions.items():
                if key not in valid_instruction_keys:
                    errors.append(f"Invalid instruction key: '{key}'. Valid keys: {', '.join(valid_instruction_keys)}")
                elif key == "sample_questions":
                    if not isinstance(value, list):
                        errors.append("'instructions.sample_questions' must be an array")
                    else:
                        for i, question in enumerate(value):
                            if not isinstance(question, (str, dict)):
                                errors.append(f"'instructions.sample_questions[{i}]' must be a string or object")
                elif not isinstance(value, str):
                    errors.append(f"'instructions.{key}' must be a string")
    
    # Validate orchestration structure
    if "orchestration" in agent_spec:
        orchestration = agent_spec["orchestration"]
        if not isinstance(orchestration, dict):
            errors.append("'orchestration' must be an object")
        elif "budget" in orchestration:
            budget = orchestration["budget"]
            if not isinstance(budget, dict):
                errors.append("'orchestration.budget' must be an object")
            else:
                if "seconds" in budget and not isinstance(budget["seconds"], int):
                    errors.append("'orchestration.budget.seconds' must be an integer")
                if "tokens" in budget and not isinstance(budget["tokens"], int):
                    errors.append("'orchestration.budget.tokens' must be an integer")
    
    # Validate tools structure
    if "tools" in agent_spec:
        tools = agent_spec["tools"]
        if not isinstance(tools, list):
            errors.append("'tools' must be an array")
        else:
            for i, tool in enumerate(tools):
                if not isinstance(tool, dict):
                    errors.append(f"'tools[{i}]' must be an object")
                elif "tool_spec" not in tool:
                    errors.append(f"'tools[{i}].tool_spec' is required")
                else:
                    tool_spec = tool["tool_spec"]
                    if not isinstance(tool_spec, dict):
                        errors.append(f"'tools[{i}].tool_spec' must be an object")
                    else:
                        if "type" in tool_spec and not isinstance(tool_spec["type"], str):
                            errors.append(f"'tools[{i}].tool_spec.type' must be a string")
                        if "name" in tool_spec and not isinstance(tool_spec["name"], str):
                            errors.append(f"'tools[{i}].tool_spec.name' must be a string")
                        if "description" in tool_spec and not isinstance(tool_spec["description"], str):
                            errors.append(f"'tools[{i}].tool_spec.description' must be a string")
    
    # Validate tool_resources structure
    if "tool_resources" in agent_spec:
        tool_resources = agent_spec["tool_resources"]
        if not isinstance(tool_resources, dict):
            errors.append("'tool_resources' must be an object")
    
    # Validate profile structure
    if "profile" in agent_spec:
        profile = agent_spec["profile"]
        if not isinstance(profile, dict):
            errors.append("'profile' must be an object")
    
    # Validate comment
    if "comment" in agent_spec:
        if not isinstance(agent_spec["comment"], str):
            errors.append("'comment' must be a string")
    
    # Validate experimental
    if "experimental" in agent_spec:
        if not isinstance(agent_spec["experimental"], dict):
            errors.append("'experimental' must be an object")
    
    return errors


def load_and_validate_json(config_file: str) -> dict:
    """
    Load and validate JSON configuration file.
    
    Args:
        config_file: Path to JSON configuration file
        
    Returns:
        dict: Validated agent specification
        
    Raises:
        ValueError: If JSON is invalid or validation fails
        FileNotFoundError: If config file doesn't exist
    """
    # Check if file exists
    if not os.path.exists(config_file):
        raise FileNotFoundError(f"Configuration file not found: {config_file}")
    
    # Load JSON
    try:
        with open(config_file, 'r') as f:
            agent_spec = json.load(f)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in configuration file: {e}")
    
    # Validate structure
    errors = validate_agent_spec(agent_spec)
    if errors:
        error_msg = "JSON validation failed:\n  " + "\n  ".join(errors)
        raise ValueError(error_msg)
    
    return agent_spec


def read_instructions(instructions_arg: str) -> str:
    """
    Read instructions from file or use as direct text.
    
    Args:
        instructions_arg: File path or instruction text
        
    Returns:
        str: Instructions text
    """
    if os.path.isfile(instructions_arg):
        with open(instructions_arg, 'r') as f:
            return f.read()
    return instructions_arg


def fetch_current_spec(agent_name: str, database: str, schema: str, connection: str) -> dict:
    """
    Fetch and parse the current agent specification from Snowflake.
    
    Uses get_agent_config.py's REST API function to retrieve the current spec,
    then parses the agent_spec field into a bare spec dictionary.
    
    Args:
        agent_name: Name of the agent
        database: Database name
        schema: Schema name
        connection: Snowflake connection name
        
    Returns:
        dict: Parsed agent specification
    """
    from get_agent_config import get_agent_config as _get_config
    
    raw = _get_config(agent_name, database, schema, connection)
    if "agent_spec" in raw:
        spec = raw["agent_spec"]
        return json.loads(spec) if isinstance(spec, str) else spec
    return raw


def split_spec(agent_spec: dict) -> tuple:
    """
    Split agent spec into (specification_body, set_properties).
    
    Separates comment/profile (which use ALTER AGENT SET or CREATE AGENT params)
    from the specification body (which goes into SPECIFICATION).
    
    Args:
        agent_spec: Full agent specification dict (may include comment/profile)
        
    Returns:
        Tuple of (spec_body, set_props) where spec_body contains SPECIFICATION keys
        and set_props contains comment/profile.
    """
    spec_body = {}
    set_props = {}
    for key, value in agent_spec.items():
        if key in SET_KEYS:
            set_props[key] = value
        else:
            spec_body[key] = value
    return spec_body, set_props


def escape_sql_string(s: str) -> str:
    """Escape single quotes for SQL string literals."""
    return s.replace("'", "''")


def handle_create(args):
    """Handle create subcommand using CREATE OR REPLACE AGENT SQL."""
    # Load and validate agent spec
    agent_spec = load_and_validate_json(args.config_file)
    
    # Separate comment/profile from specification body
    spec_body, set_props = split_spec(agent_spec)
    
    fqn = f"{args.database}.{args.schema}.{args.agent_name}"
    
    # Build CREATE OR REPLACE AGENT SQL
    sql_parts = [f"CREATE OR REPLACE AGENT {fqn}"]
    
    if "comment" in set_props:
        sql_parts.append(f"  COMMENT = '{escape_sql_string(set_props['comment'])}'")
    
    if "profile" in set_props:
        profile_val = set_props["profile"]
        profile_str = json.dumps(profile_val) if isinstance(profile_val, dict) else profile_val
        sql_parts.append(f"  PROFILE = '{escape_sql_string(profile_str)}'")
    
    spec_json = json.dumps(spec_body, indent=2)
    sql_parts.append(f"  FROM SPECIFICATION $$\n{spec_json}\n$$")
    
    sql = "\n".join(sql_parts)
    
    # Connect and execute
    conn = snowflake.connector.connect(connection_name=args.connection)
    try:
        cursor = conn.cursor()
        try:
            if args.role:
                cursor.execute(f"USE ROLE {args.role}")
                print(f"Using role: {args.role}")
            
            print(f"Creating agent {args.agent_name} in {args.database}.{args.schema}...")
            cursor.execute(sql)
            print(f"✓ Successfully created agent {args.agent_name}")
            print(f"  Location: {fqn}")
        finally:
            cursor.close()
    finally:
        conn.close()


def handle_alter(args):
    """Handle alter subcommand using ALTER AGENT SQL."""
    # Validate that at least one input is provided
    if not args.config_file and not args.instructions:
        raise ValueError("alter requires at least one of: --config-file or --instructions")
    
    # Validate --merge-with usage
    if args.merge_with and not args.config_file:
        raise ValueError("--merge-with requires --config-file to be specified")
    
    # Determine what to alter
    if args.config_file and args.instructions:
        # Load config and override instructions
        print("Loading full spec and overriding instructions...")
        agent_spec = load_and_validate_json(args.config_file)
        instructions_text = read_instructions(args.instructions)
        
        # Override orchestration instructions
        if "instructions" not in agent_spec:
            agent_spec["instructions"] = {}
        agent_spec["instructions"]["orchestration"] = instructions_text
        
        final_spec = agent_spec
        
    elif args.config_file:
        # Full spec update (or partial with merge)
        agent_spec = load_and_validate_json(args.config_file)
        
        if args.merge_with:
            # Merge changes with current config
            print(f"Loading current config from {args.merge_with}...")
            current_spec = load_current_agent_spec(args.merge_with)
            
            print("Merging changes with current configuration...")
            merged_spec = deep_merge(current_spec, agent_spec)
            
            # Validate merged result
            errors = validate_agent_spec(merged_spec)
            if errors:
                error_msg = "Merged spec validation failed:\n  " + "\n  ".join(errors)
                raise ValueError(error_msg)
            
            print(f"  Merged keys: {', '.join(merged_spec.keys())}")
            final_spec = merged_spec
        else:
            print("Altering agent with full specification...")
            final_spec = agent_spec
        
    else:  # args.instructions only — auto-merge to prevent destructive update
        print("Fetching current agent configuration for safe merge...")
        current_spec = fetch_current_spec(
            args.agent_name, args.database, args.schema, args.connection
        )
        
        instructions_text = read_instructions(args.instructions)
        changes = {
            "instructions": {
                "orchestration": instructions_text
            }
        }
        final_spec = deep_merge(current_spec, changes)
        print(f"  Auto-merged instructions into existing spec ({len(current_spec)} keys preserved)")
    
    # Separate comment/profile from specification body
    spec_body, set_props = split_spec(final_spec)
    
    fqn = f"{args.database}.{args.schema}.{args.agent_name}"
    
    # Connect and execute
    conn = snowflake.connector.connect(connection_name=args.connection)
    try:
        cursor = conn.cursor()
        try:
            if args.role:
                cursor.execute(f"USE ROLE {args.role}")
                print(f"Using role: {args.role}")
            
            print(f"Altering agent {args.agent_name} in {args.database}.{args.schema}...")
            
            # ALTER AGENT SET for comment/profile
            if set_props:
                set_clauses = []
                if "comment" in set_props:
                    set_clauses.append(f"COMMENT = '{escape_sql_string(set_props['comment'])}'")
                if "profile" in set_props:
                    profile_val = set_props["profile"]
                    profile_str = json.dumps(profile_val) if isinstance(profile_val, dict) else profile_val
                    set_clauses.append(f"PROFILE = '{escape_sql_string(profile_str)}'")
                
                set_sql = f"ALTER AGENT {fqn} SET\n  " + ",\n  ".join(set_clauses)
                cursor.execute(set_sql)
                print(f"  ✓ Updated: {', '.join(set_props.keys())}")
            
            # ALTER AGENT MODIFY LIVE VERSION for specification
            if spec_body:
                spec_json = json.dumps(spec_body, indent=2)
                spec_sql = (
                    f"ALTER AGENT {fqn} MODIFY LIVE VERSION SET\n"
                    f"  SPECIFICATION = $$\n{spec_json}\n$$"
                )
                cursor.execute(spec_sql)
                print(f"  ✓ Updated specification: {', '.join(spec_body.keys())}")
            
            print(f"✓ Successfully altered agent {args.agent_name}")
            print(f"  Location: {fqn}")
        finally:
            cursor.close()
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Create or alter Snowflake Cortex Agents via SQL",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True, help='Command to execute')
    
    # CREATE subcommand
    create_parser = subparsers.add_parser(
        'create',
        help='Create a new agent from full specification',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --agent-name MY_AGENT --config-file full_spec.json
  %(prog)s --agent-name MY_AGENT --config-file spec.json --database MY_DB --schema MY_SCHEMA --role MY_ROLE
        """
    )
    create_parser.add_argument('--agent-name', required=True, help='Name for the new agent')
    create_parser.add_argument('--config-file', required=True, help='Path to full agent specification JSON')
    create_parser.add_argument('--database', required=True, 
                              help='Database name')
    create_parser.add_argument('--schema', required=True, 
                              help='Schema name')
    create_parser.add_argument('--role', required=True,
                              help='Snowflake role to use')
    create_parser.add_argument('--connection', default=os.getenv('SNOWFLAKE_CONNECTION_NAME', 'snowhouse'),
                              help='Snowflake connection name')
    
    # ALTER subcommand
    alter_parser = subparsers.add_parser(
        'alter',
        help='Alter an existing agent',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Alter instructions only (auto-merges with current config):
  %(prog)s --agent-name MY_AGENT --instructions instructions.txt
  %(prog)s --agent-name MY_AGENT --instructions "Always be polite and concise"

  # Alter full specification (replaces entire config):
  %(prog)s --agent-name MY_AGENT --config-file full_spec.json

  # Partial edit with merge (recommended for partial changes):
  %(prog)s --agent-name MY_AGENT --config-file edit_spec.json --merge-with current_agent_spec.json

  # Alter full spec but override instructions:
  %(prog)s --agent-name MY_AGENT --config-file full_spec.json --instructions custom_instructions.txt

Note: At least one of --config-file or --instructions is required.
      Use --merge-with when making partial changes to preserve existing config.
      When using --instructions alone, the script auto-merges with the current
      agent config to prevent destructive updates.
        """
    )
    alter_parser.add_argument('--agent-name', required=True, help='Name of the agent to alter')
    alter_parser.add_argument('--config-file', help='Path to agent specification JSON (full or partial)')
    alter_parser.add_argument('--merge-with', 
                             help='Path to current_agent_spec.json to merge changes with (for partial edits)')
    alter_parser.add_argument('--instructions', help='Path to instructions file or instructions text')
    alter_parser.add_argument('--database', default='SNOWFLAKE_INTELLIGENCE',
                             help='Database name (default: SNOWFLAKE_INTELLIGENCE)')
    alter_parser.add_argument('--schema', default='AGENTS',
                             help='Schema name (default: AGENTS)')
    alter_parser.add_argument('--role',
                             help='Snowflake role to use (optional)')
    alter_parser.add_argument('--connection', default=os.getenv('SNOWFLAKE_CONNECTION_NAME', 'snowhouse'),
                             help='Snowflake connection name')
    
    args = parser.parse_args()
    
    try:
        if args.command == 'create':
            handle_create(args)
        elif args.command == 'alter':
            handle_alter(args)
    except ValueError as e:
        print(f"Validation Error: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"File Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

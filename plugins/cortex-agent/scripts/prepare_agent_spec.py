#!/usr/bin/env python3
"""
Prepare agent specification for SQL execution.

Reads from the agent workspace, validates, optionally merges (for edit flows),
and prints the ready-to-execute spec JSON to stdout.

Auto-detects create vs edit based on which files exist in the latest version folder:
  - edit_spec.json + agent_metadata.json → extract agent_spec from metadata,
    deep_merge with edit, validate, write full_agent_spec.json
  - agent_spec.json only → validate (create flow)
  - Neither → error

For the edit flow, agent_metadata.json contains the raw DESCRIBE AGENT output.
This script extracts the agent_spec column, parses it (JSON or YAML string),
and uses it as the base for merging.

No Snowflake connector dependency. Self-contained validation and merge logic.

Usage:
  uv run python ../scripts/prepare_agent_spec.py --fqn DB.SCHEMA.NAME
"""

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Keys that belong in the SPECIFICATION (MODIFY LIVE VERSION / FROM SPECIFICATION)
SPECIFICATION_KEYS = {
    "models", "instructions", "orchestration", "tools", "tool_resources",
    "experimental"
}

# Keys that are SET properties (ALTER AGENT SET / CREATE AGENT params)
SET_KEYS = {"comment", "profile"}

# All valid top-level keys in input JSON
VALID_TOP_LEVEL_KEYS = SPECIFICATION_KEYS | SET_KEYS


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def deep_merge(base: dict, changes: dict) -> dict:
    """
    Deep merge changes into base dictionary.

    For nested dicts, recursively merges. For other types (including lists),
    the value from changes replaces the base value.
    """
    result = base.copy()
    for key, value in changes.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def validate_agent_spec(agent_spec: dict) -> list:
    """
    Validate agent specification JSON structure.

    Returns:
        list: List of validation errors (empty if valid)
    """
    errors = []

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
        if not isinstance(agent_spec["tool_resources"], dict):
            errors.append("'tool_resources' must be an object")

    # Validate profile structure
    if "profile" in agent_spec:
        if not isinstance(agent_spec["profile"], dict):
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


def extract_agent_spec_from_metadata(metadata: dict) -> dict:
    """
    Extract the agent_spec from raw DESCRIBE AGENT output.

    DESCRIBE AGENT returns columns: name, database_name, schema_name, owner,
    comment, profile, agent_spec, created_on. The agent_spec column contains
    a YAML/JSON string with the full specification.

    This function handles multiple input formats:
    1. Dict with "agent_spec" key (e.g. {"agent_spec": "<yaml/json-string>", "name": "...", ...})
    2. Bare spec format (e.g. {"instructions": {...}, "tools": [...]}) — returned as-is

    Returns:
        dict: Parsed agent specification
    """
    if "agent_spec" not in metadata:
        # Bare spec format — already a parsed agent spec dict
        return metadata

    agent_spec_value = metadata["agent_spec"]

    if isinstance(agent_spec_value, dict):
        return agent_spec_value

    if isinstance(agent_spec_value, str):
        # Try JSON first
        try:
            return json.loads(agent_spec_value)
        except json.JSONDecodeError:
            pass

        # Try YAML (agent_spec column can be YAML per Snowflake docs)
        try:
            import yaml
            return yaml.safe_load(agent_spec_value)
        except Exception:
            pass

        raise ValueError(
            f"Failed to parse agent_spec value as JSON or YAML. "
            f"First 200 chars: {agent_spec_value[:200]}"
        )

    raise ValueError(f"agent_spec must be a string or dict, got {type(agent_spec_value)}")


# ---------------------------------------------------------------------------
# Workspace helpers
# ---------------------------------------------------------------------------

def fqn_to_workspace_dir(fqn: str, base_dir: Path = None) -> Path:
    """Convert a fully qualified name (DB.SCHEMA.NAME) to workspace directory path."""
    if base_dir is None:
        base_dir = Path.cwd()
    return base_dir / fqn.replace('.', '_')


def find_latest_version(workspace_dir: Path) -> Path:
    """Find the most recent version directory in the workspace."""
    versions_dir = workspace_dir / "versions"
    if not versions_dir.exists():
        raise FileNotFoundError(f"No versions/ directory found in {workspace_dir}")

    version_dirs = sorted(
        [d for d in versions_dir.iterdir() if d.is_dir() and d.name.startswith('v')],
        reverse=True
    )

    if not version_dirs:
        raise FileNotFoundError(f"No version directories found in {versions_dir}")

    return version_dirs[0]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Prepare agent spec for SQL execution",
        epilog="""
Auto-detects create vs edit based on files in the workspace:
  - edit_spec.json + agent_metadata.json → extract spec, merge, validate (edit)
  - agent_spec.json → validate only (create)

Examples:
  %(prog)s --fqn DB.SCHEMA.NAME
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fqn", required=True, help="Fully qualified agent name (DB.SCHEMA.NAME)")

    args = parser.parse_args()

    # Resolve workspace
    workspace_dir = fqn_to_workspace_dir(args.fqn)
    if not workspace_dir.exists():
        print(f"Error: Workspace directory does not exist: {workspace_dir}", file=sys.stderr)
        sys.exit(1)

    # Find latest version
    try:
        version_dir = find_latest_version(workspace_dir)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    edit_spec_path = version_dir / "edit_spec.json"
    agent_metadata_path = version_dir / "agent_metadata.json"
    agent_spec_path = version_dir / "agent_spec.json"

    # Auto-detect mode
    if edit_spec_path.exists() and agent_metadata_path.exists():
        # Edit mode: extract spec from metadata, merge, and validate
        print("Mode: edit (extracting spec from agent_metadata.json, merging with edit_spec.json)", file=sys.stderr)

        with open(agent_metadata_path) as f:
            metadata = json.load(f)

        try:
            current_spec = extract_agent_spec_from_metadata(metadata)
        except ValueError as e:
            print(f"Error extracting agent_spec from metadata: {e}", file=sys.stderr)
            sys.exit(1)

        with open(edit_spec_path) as f:
            edit_spec = json.load(f)

        # Merge
        merged_spec = deep_merge(current_spec, edit_spec)

        # Reject comment/profile
        unsupported = set(merged_spec.keys()) & SET_KEYS
        if unsupported:
            print(f"Error: Unsupported keys in spec: {', '.join(sorted(unsupported))}. "
                  f"comment/profile are not supported in this flow.", file=sys.stderr)
            sys.exit(1)

        # Validate
        errors = validate_agent_spec(merged_spec)
        if errors:
            print("Validation failed after merge:", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            sys.exit(1)

        # Write full_agent_spec.json
        full_spec_path = version_dir / "full_agent_spec.json"
        with open(full_spec_path, 'w') as f:
            json.dump(merged_spec, f, indent=2)
        print(f"✓ Merged spec written to {full_spec_path}", file=sys.stderr)

        # Print to stdout for LLM to use in sql_execute
        print(json.dumps(merged_spec, indent=2))

    elif agent_spec_path.exists():
        # Create mode: validate only
        print("Mode: create (validating agent_spec.json)", file=sys.stderr)

        with open(agent_spec_path) as f:
            agent_spec = json.load(f)

        # Reject comment/profile
        unsupported = set(agent_spec.keys()) & SET_KEYS
        if unsupported:
            print(f"Error: Unsupported keys in spec: {', '.join(sorted(unsupported))}. "
                  f"comment/profile are not supported in this flow.", file=sys.stderr)
            sys.exit(1)

        # Validate
        errors = validate_agent_spec(agent_spec)
        if errors:
            print("Validation failed:", file=sys.stderr)
            for e in errors:
                print(f"  {e}", file=sys.stderr)
            sys.exit(1)

        print(f"✓ Spec validated", file=sys.stderr)

        # Print to stdout for LLM to use in sql_execute
        print(json.dumps(agent_spec, indent=2))

    else:
        print(f"Error: No spec files found in {version_dir}", file=sys.stderr)
        print(f"  Expected one of:", file=sys.stderr)
        print(f"    - agent_spec.json (for create)", file=sys.stderr)
        print(f"    - edit_spec.json + agent_metadata.json (for edit)", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

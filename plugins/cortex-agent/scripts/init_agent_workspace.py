#!/usr/bin/env python3
"""
Initialize or load workspace for agent optimization.

This script creates a structured working directory for optimizing a specific agent,
following the agent-system-of-record protocol with versioned folders and optimization logs.
"""

import argparse
import json
from datetime import datetime
from pathlib import Path


def init_agent_workspace(agent_name, database="SNOWFLAKE_INTELLIGENCE", schema="AGENTS", base_dir=None, quiet=False):
    """
    Initialize or load workspace for an agent optimization session.

    Creates workspace following the agent-system-of-record structure:
    - Workspace directory named with underscores (e.g., SNOWFLAKE_INTELLIGENCE_AGENTS_AGENT_NAME)
    - optimization_log.md for tracking changes
    - versions/ directory for versioned snapshots

    Args:
        agent_name: Name of the agent to optimize
        database: Database name (default: SNOWFLAKE_INTELLIGENCE)
        schema: Schema name (default: AGENTS)
        base_dir: Base directory for agent workspaces (default: current directory)
        quiet: When True, suppress progress prints (used by --json mode for parseable stdout)

    Returns:
        dict: Workspace information including paths and version directory
    """
    def _log(msg):
        """Print progress message unless running in quiet mode."""
        if not quiet:
            print(msg)

    if base_dir is None:
        base_dir = Path.cwd()
    else:
        base_dir = Path(base_dir)

    agent_fqn = f"{database}.{schema}.{agent_name}"
    agent_dir_name = agent_fqn.replace('.', '_')
    workspace_dir = base_dir / agent_dir_name

    workspace_exists = workspace_dir.exists()

    if workspace_exists:
        _log(f"✓ Found existing workspace for agent '{agent_fqn}'")
    else:
        _log(f"Creating new workspace for agent '{agent_fqn}'")
        workspace_dir.mkdir(parents=True, exist_ok=True)

    versions_dir = workspace_dir / "versions"
    versions_dir.mkdir(exist_ok=True)

    metadata_file = workspace_dir / "metadata.yaml"
    if not metadata_file.exists():
        metadata_content = f"""database: {database}
schema: {schema}
name: {agent_name}
"""
        with open(metadata_file, 'w') as f:
            f.write(metadata_content)
        _log("✓ Created metadata.yaml")
    else:
        _log("✓ Found existing metadata.yaml")

    optimization_log_file = workspace_dir / "optimization_log.md"
    if not optimization_log_file.exists():
        _create_optimization_log(optimization_log_file, agent_fqn, agent_name, database, schema)
        _log("✓ Created optimization_log.md")
    else:
        _log("✓ Found existing optimization_log.md")
    
    version_timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M")
    version_name = f"v{version_timestamp}"
    version_dir = versions_dir / version_name
    version_dir.mkdir(exist_ok=True)

    evals_dir = version_dir / "evals"
    evals_dir.mkdir(exist_ok=True)
    
    workspace_info = {
        'agent_name': agent_name,
        'agent_fqn': agent_fqn,
        'database': database,
        'schema': schema,
        'workspace_dir': str(workspace_dir),
        'optimization_log_file': str(optimization_log_file),
        'versions_dir': str(versions_dir),
        'version_name': version_name,
        'version_dir': str(version_dir),
        'evals_dir': str(evals_dir),
        'agent_config_file': str(version_dir / 'agent_config.json'),
        'instructions_file': str(version_dir / 'instructions_orchestration.txt'),
        'tools_summary_file': str(version_dir / 'tools_summary.txt'),
        'change_manifest_file': str(version_dir / 'change_manifest.md'),
        'existing_workspace': workspace_exists
    }
    
    _log(f"\n{'='*60}")
    _log("Workspace Information:")
    _log(f"{'='*60}")
    _log(f"Agent FQN: {agent_fqn}")
    _log(f"Workspace Directory: {workspace_dir}")
    _log(f"Version: {version_name}")
    _log(f"Version Directory: {version_dir}")
    _log(f"{'='*60}\n")

    return workspace_info


def _create_optimization_log(log_file, agent_fqn, agent_name, database, schema):
    """
    Create initial optimization_log.md from template.
    
    Args:
        log_file: Path to optimization_log.md
        agent_fqn: Fully qualified agent name
        agent_name: Agent name
        database: Database name
        schema: Schema name
    """
    template = f"""# Optimization Log

## Agent details
- Fully qualified agent name: {agent_fqn}
- Clone FQN (if production): <CLONE_DATABASE.CLONE_SCHEMA.CLONE_AGENT_NAME>
- Owner / stakeholders: <names>
- Purpose / domain: <short description>
- Current status: <draft | staging | production>

## Evaluation dataset
- Location: <local path or DATABASE.SCHEMA.TABLE/VIEW>
- Coverage: <question count, categories>

## Agent versions
- <vYYYYMMDD-HHMM>: <short title> — <summary>

## Optimization details
### Entry: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}
- Version: <vYYYYMMDD-HHMM>
- Goal: <what we intended to improve>
- Changes made: <list>
- Rationale: <why>
- Eval: <path, metrics>
- Result: <observations>
- Next steps: <follow-ups>
"""
    with open(log_file, 'w') as f:
        f.write(template)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Initialize workspace for agent optimization",
        epilog="""
Examples:
  %(prog)s --agent-name MY_AGENT
  %(prog)s --agent-name MY_AGENT --database TEMP --schema MY_SCHEMA
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--agent-name", required=True, help="Name of the agent to optimize")
    parser.add_argument("--database", default="SNOWFLAKE_INTELLIGENCE", help="Database name (default: SNOWFLAKE_INTELLIGENCE)")
    parser.add_argument("--schema", default="AGENTS", help="Schema name (default: AGENTS)")
    parser.add_argument("--base-dir", default=None, help="Base directory for the workspace (default: current working directory)")
    parser.add_argument("--json", dest="json_output", action="store_true", help="Emit workspace info as a single JSON object on stdout (suppresses human-readable output)")
    
    args = parser.parse_args()
    
    workspace = init_agent_workspace(
        args.agent_name,
        args.database,
        args.schema,
        args.base_dir,
        quiet=args.json_output,
    )

    if args.json_output:
        print(json.dumps(workspace, indent=2))
    else:
        print("Workspace initialized successfully!")
        print("\nNext steps:")
        print(f"1. Get agent config snapshot: {workspace['agent_config_file']}")
        print(f"2. Save instructions to: {workspace['instructions_file']}")
        print(f"3. Run evaluations in: {workspace['evals_dir']}")
        print(f"4. Document changes in: {workspace['change_manifest_file']}")
        print(f"5. Update optimization log: {workspace['optimization_log_file']}")

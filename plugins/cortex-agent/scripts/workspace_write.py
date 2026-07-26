#!/usr/bin/env python3
"""
Write a file to the latest version folder in an agent workspace.

Resolves the workspace directory from a fully qualified agent name (DB.SCHEMA.NAME),
finds the latest version folder, and writes the provided content there.

Usage:
  echo '{"instructions": {...}}' | python workspace_write.py --fqn DB.SCHEMA.NAME --file agent_spec.json
  python workspace_write.py --fqn DB.SCHEMA.NAME --file agent_spec.json --content '{"key": "value"}'
"""

import argparse
import sys
from pathlib import Path


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


def main():
    parser = argparse.ArgumentParser(
        description="Write a file to the latest version folder in an agent workspace",
        epilog="""
Examples:
  echo '{"instructions": {...}}' | %(prog)s --fqn DB.SCHEMA.NAME --file agent_spec.json
  %(prog)s --fqn DB.SCHEMA.NAME --file agent_spec.json --content '{"key": "value"}'
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--fqn", required=True, help="Fully qualified agent name (DB.SCHEMA.NAME)")
    parser.add_argument("--file", required=True, help="Filename to write (e.g., agent_spec.json)")
    parser.add_argument("--content", help="Content to write (alternative to stdin)")
    parser.add_argument("--stdin", action="store_true", help="Read content from stdin")

    args = parser.parse_args()

    # Get content
    if args.stdin or (not args.content and not sys.stdin.isatty()):
        content = sys.stdin.read()
    elif args.content:
        content = args.content
    else:
        print("Error: Provide content via --content or --stdin (or pipe to stdin)", file=sys.stderr)
        sys.exit(1)

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

    # Write file
    file_path = version_dir / args.file
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"✓ Written {file_path}")


if __name__ == "__main__":
    main()

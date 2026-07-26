#!/usr/bin/env python3
"""
Script to extract agent configuration into separate text files.
Creates a directory with instructions and tool descriptions as individual files.
"""

import argparse
import json
import os
import sys
from pathlib import Path


def extract_agent_config(config_file: str, output_dir: str):
    """
    Extract agent configuration into separate files.
    
    Args:
        config_file: Path to agent configuration JSON file
        output_dir: Directory to save extracted files
    """
    with open(config_file, 'r') as f:
        config = json.load(f)
    
    # Handle both wrapper format ({"agent_spec": "...", "name": ...}) and bare spec ({"instructions": ...})
    if 'agent_spec' in config:
        raw = config['agent_spec']
        agent_spec = json.loads(raw) if isinstance(raw, str) else raw
        metadata = {
            'name': config.get('name', ''),
            'database': config.get('database_name', ''),
            'schema': config.get('schema_name', ''),
            'owner': config.get('owner', ''),
            'created_on': config.get('created_on', '')
        }
    else:
        agent_spec = config
        metadata = {}
    
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Save metadata
    with open(output_path / 'metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"✓ Saved metadata to {output_path / 'metadata.json'}")
    
    # Extract and save instructions
    instructions = agent_spec.get('instructions', {})
    
    if 'orchestration' in instructions:
        with open(output_path / 'instructions_orchestration.txt', 'w') as f:
            f.write(instructions['orchestration'])
        print(f"✓ Saved orchestration instructions to {output_path / 'instructions_orchestration.txt'}")
    
    if 'response' in instructions:
        with open(output_path / 'instructions_response.txt', 'w') as f:
            f.write(instructions['response'])
        print(f"✓ Saved response instructions to {output_path / 'instructions_response.txt'}")
    
    if 'system' in instructions:
        with open(output_path / 'instructions_system.txt', 'w') as f:
            f.write(instructions['system'])
        print(f"✓ Saved system instructions to {output_path / 'instructions_system.txt'}")
    
    # Extract and save tools
    tools = agent_spec.get('tools', [])
    
    tools_dir = output_path / 'tools'
    tools_dir.mkdir(exist_ok=True)
    
    tool_summary = []
    
    for i, tool in enumerate(tools):
        # Handle both direct tool format and tool_spec wrapper
        tool_data = tool.get('tool_spec', tool)
        
        tool_type = tool_data.get('type', 'unknown')
        name = tool_data.get('name', f'tool_{i}')
        description = tool_data.get('description', '')
        
        safe_name = name.replace('/', '_').replace(' ', '_').replace('.', '_')
        
        # Save as text file for better readability
        tool_file = tools_dir / f'{safe_name}.txt'
        
        with open(tool_file, 'w') as f:
            f.write(f"Tool Name: {name}\n")
            f.write(f"Tool Type: {tool_type}\n")
            f.write(f"\n{'='*80}\n")
            f.write(f"DESCRIPTION:\n")
            f.write(f"{'='*80}\n\n")
            f.write(f"{description}\n")
            
            # Add additional metadata based on tool type
            if tool_type == 'cortex_analyst_text_to_sql':
                if 'cortex_analyst_semantic_model_file' in tool_data:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"SEMANTIC MODEL:\n")
                    f.write(f"{'='*80}\n\n")
                    f.write(f"{tool_data['cortex_analyst_semantic_model_file']}\n")
        
        print(f"✓ Saved tool '{name}' to {tool_file}")
        tool_summary.append({
            'name': name, 
            'type': tool_type, 
            'file': str(tool_file.name),
            'description_length': len(description)
        })
        
        # Also save full JSON for reference
        json_file = tools_dir / f'{safe_name}.json'
        with open(json_file, 'w') as f:
            json.dump(tool, f, indent=2)
    
    # Save tool summary
    with open(output_path / 'tools_summary.json', 'w') as f:
        json.dump(tool_summary, f, indent=2)
    print(f"✓ Saved tool summary to {output_path / 'tools_summary.json'}")
    
    # Save full agent spec for reference
    with open(output_path / 'full_agent_spec.json', 'w') as f:
        json.dump(agent_spec, f, indent=2)
    print(f"✓ Saved full agent spec to {output_path / 'full_agent_spec.json'}")
    
    print(f"\n✓ Successfully extracted agent configuration to {output_path}")
    print(f"  - Instructions: {len([f for f in output_path.glob('instructions_*.txt')])} file(s)")
    print(f"  - Tools: {len(tools)} tool(s)")


def main():
    parser = argparse.ArgumentParser(
        description="Extract agent configuration into separate files",
        epilog="""
Examples:
  %(prog)s --config-file agent_config.json --output-dir ./extracted
  %(prog)s --config-file config.json --output-dir ./agent_files
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--config-file", required=True, help="Path to agent configuration JSON file")
    parser.add_argument("--output-dir", required=True, help="Output directory for extracted files")
    
    args = parser.parse_args()
    
    try:
        extract_agent_config(args.config_file, args.output_dir)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

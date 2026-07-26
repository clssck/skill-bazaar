#!/usr/bin/env python3
"""Update agent workspace metadata.yaml file."""

import argparse
import yaml
from datetime import datetime

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Update agent workspace metadata.yaml file",
        epilog="""
Examples:
  # Add a test question:
  %(prog)s --metadata-file ./workspace/metadata.yaml --add-question "What is the price of AAPL?"

  # Add a round entry:
  %(prog)s --metadata-file ./workspace/metadata.yaml --round-number 2 --feedback "Improve formatting" --result "Updated date format"

  # Add both:
  %(prog)s --metadata-file ./workspace/metadata.yaml --add-question "Price for AAPL" --round-number 1 --status completed
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--metadata-file", required=True, help="Path to metadata.yaml file")
    parser.add_argument("--add-question", help="Add a test question if not present")
    parser.add_argument("--round-number", type=int, help="Round number to add")
    parser.add_argument("--feedback", help="Feedback for the round")
    parser.add_argument("--status", default="completed", help="Status for the round (default: completed)")
    parser.add_argument("--result", help="Result description for the round")
    
    args = parser.parse_args()
    
    with open(args.metadata_file, 'r') as f:
        metadata = yaml.safe_load(f)
    
    # Add test question if provided
    if args.add_question and args.add_question not in metadata.get('test_questions', []):
        metadata.setdefault('test_questions', []).append(args.add_question)
    
    # Add round entry if round number provided
    if args.round_number:
        round_entry = {
            'round_number': args.round_number,
            'status': args.status,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
        }
        if args.feedback:
            round_entry['feedback'] = args.feedback
        if args.result:
            round_entry['result'] = args.result
        
        metadata.setdefault('rounds', []).append(round_entry)
    
    with open(args.metadata_file, 'w') as f:
        yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)
    
    print(f"✓ Updated {args.metadata_file}")

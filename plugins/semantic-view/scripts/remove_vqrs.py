#!/usr/bin/env python3
"""
Remove Verified Query Repository (VQR) entries from semantic model YAML files.

This script creates a clean version of the semantic model without VQR hints,
which is useful for testing whether the semantic model can generate correct
SQL based solely on its table definitions, dimensions, measures, and relationships.

Usage:
    python3 remove_vqrs.py <input_yaml> <output_yaml>

Example:
    python3 remove_vqrs.py semantic_model.yaml semantic_model_no_vqrs.yaml
"""

import sys
from pathlib import Path

import yaml


def remove_vqrs_from_yaml(input_file: str, output_file: str) -> int:
    """
    Remove verified_queries section from semantic model YAML.

    Args:
        input_file: Path to input semantic model YAML file
        output_file: Path to output YAML file (without VQRs)

    Returns:
        Number of VQRs that were removed
    """
    try:
        # Read input YAML
        with open(input_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ Error: Input file '{input_file}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"❌ Error parsing YAML file: {e}")
        sys.exit(1)

    # Count VQRs before removal
    vqr_count = len(data.get("verified_queries", []))

    # Remove verified_queries section
    if "verified_queries" in data:
        del data["verified_queries"]
        print(f"✅ Removed {vqr_count} VQR(s) from semantic model")
    else:
        print("⚠️  No verified_queries section found in semantic model")

    # Write output YAML
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            yaml.dump(
                data, f, default_flow_style=False, sort_keys=False, allow_unicode=True
            )

        output_size = Path(output_file).stat().st_size
        print(f"✅ Saved VQR-free semantic model to: {output_file}")
        print(f"📁 File size: {output_size} bytes")

    except Exception as e:
        print(f"❌ Error writing output file: {e}")
        sys.exit(1)

    return vqr_count


def main() -> int:
    """Main function for command line usage."""
    if len(sys.argv) != 3:
        print("Usage: python3 remove_vqrs.py <input_yaml> <output_yaml>")
        print()
        print("Example:")
        print(
            "  python3 remove_vqrs.py semantic_model.yaml semantic_model_no_vqrs.yaml"
        )
        print()
        print("Purpose:")
        print("  Creates a clean version of the semantic model without VQR hints")
        print("  for testing whether the model can generate correct SQL independently.")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2]

    # Perform removal
    vqr_count = remove_vqrs_from_yaml(input_file, output_file)

    return vqr_count


if __name__ == "__main__":
    main()

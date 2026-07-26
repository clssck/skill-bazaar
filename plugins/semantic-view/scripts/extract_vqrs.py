#!/usr/bin/env python3
"""
Extract Verified Query Repository (VQR) entries from semantic model YAML files
and output them in CSV format with question and golden_sql columns.

Usage:
    python extract_vqrs.py <yaml_file> [output_csv]
"""

import csv
import sys
from pathlib import Path
from typing import Any

import yaml


def extract_vqrs_from_yaml(yaml_file_path: str) -> list[dict[str, Any]]:
    """
    Extract VQR entries from a semantic model YAML file.

    Args:
        yaml_file_path: Path to the semantic model YAML file

    Returns:
        List of dictionaries containing question and sql pairs
    """
    try:
        with open(yaml_file_path, "r", encoding="utf-8") as file:
            data = yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Error: File '{yaml_file_path}' not found.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing YAML file: {e}")
        sys.exit(1)

    vqrs = []

    # Extract verified_queries section
    verified_queries = data.get("verified_queries", [])

    for vqr in verified_queries:
        question = vqr.get("question", "")
        sql = vqr.get("sql", "")
        name = vqr.get("name", "")
        verified_at = vqr.get("verified_at", "")
        verified_by = vqr.get("verified_by", "")

        vqrs.append(
            {
                "question": question,
                "golden_sql": sql,
                "name": name,
                "verified_at": verified_at,
                "verified_by": verified_by,
            }
        )

    return vqrs


def write_vqrs_to_csv(vqrs: list[dict[str, Any]], output_file: str) -> None:
    """
    Write VQR entries to a CSV file.

    Args:
        vqrs: List of VQR dictionaries
        output_file: Path to output CSV file
    """
    if not vqrs:
        print("No VQRs found in the YAML file.")
        return

    try:
        with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
            fieldnames = [
                "question",
                "golden_sql",
                "name",
                "verified_at",
                "verified_by",
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

            # Write header
            writer.writeheader()

            # Write VQR data
            for vqr in vqrs:
                writer.writerow(vqr)

        print(f"Successfully extracted {len(vqrs)} VQR(s) to '{output_file}'")

    except Exception as e:
        print(f"Error writing CSV file: {e}")
        sys.exit(1)


def print_vqrs_summary(vqrs: list[dict[str, Any]]) -> None:
    """
    Print a summary of extracted VQRs.

    Args:
        vqrs: List of VQR dictionaries
    """
    if not vqrs:
        print("No VQRs found in the YAML file.")
        return

    print("\n=== VQR Summary ===")
    print(f"Total VQRs found: {len(vqrs)}")
    print()

    for i, vqr in enumerate(vqrs, 1):
        print(
            f"{i}. Question: {vqr['question'][:100]}{'...' if len(vqr['question']) > 100 else ''}"
        )
        print(
            f"   SQL: {vqr['golden_sql'][:150]}{'...' if len(vqr['golden_sql']) > 150 else ''}"
        )
        if vqr["name"]:
            print(f"   Name: {vqr['name']}")
        if vqr["verified_by"]:
            print(f"   Verified by: {vqr['verified_by']}")
        print()


def main() -> int:
    """Main function for command line usage."""
    if len(sys.argv) < 2:
        print("Usage: python extract_vqrs.py <yaml_file> [output_csv]")
        print("Example: python extract_vqrs.py semantic_models/my_model.yaml vqrs.csv")
        sys.exit(1)

    yaml_file = sys.argv[1]

    # Generate default output filename if not provided
    if len(sys.argv) >= 3:
        output_file = sys.argv[2]
    else:
        yaml_path = Path(yaml_file)
        output_file = f"{yaml_path.stem}_vqrs.csv"

    # Extract VQRs from YAML
    vqrs = extract_vqrs_from_yaml(yaml_file)

    # Print summary
    print_vqrs_summary(vqrs)

    # Write to CSV
    if vqrs:
        write_vqrs_to_csv(vqrs, output_file)

    return len(vqrs)


if __name__ == "__main__":
    main()

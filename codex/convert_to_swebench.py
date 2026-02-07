#!/usr/bin/env python3
"""
Convert Codex output to Multi-SWE-Bench official evaluation format

The Multi-SWE-Bench official format requires each line to contain:
- instance_id: Instance ID (must match instance_id in Multi-SWE-Bench dataset)
- model_name_or_path: Model name
- model_patch: Generated patch (git diff format)

Reference: https://github.com/multi-swe-bench/multi-swe-bench
"""

import json
import argparse
import os
from pathlib import Path


def convert_to_multi_swe_bench_format(
    input_file: str, 
    output_file: str, 
    model_name: str = "codex-cli"
) -> dict:
    """
    Convert output.jsonl to Multi-SWE-Bench official evaluation format
    
    Args:
        input_file: Codex output file (output.jsonl)
        output_file: Output file path
        model_name: Model name
    
    Returns:
        dict: Statistics
    """
    results = []
    
    with open(input_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            
            # Multi-SWE-Bench official format
            entry = {
                "instance_id": data["instance_id"],
                "model_name_or_path": model_name,
                "model_patch": data.get("patch", ""),
            }
            results.append(entry)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    
    with open(output_file, 'w') as f:
        for entry in results:
            f.write(json.dumps(entry) + "\n")
    
    # Statistics
    total = len(results)
    with_patch = sum(1 for r in results if r["model_patch"])
    
    stats = {
        "total": total,
        "with_patch": with_patch,
        "without_patch": total - with_patch,
        "output_file": output_file,
    }
    
    return stats


def validate_patch_format(patch: str) -> bool:
    """Validate whether a patch is in valid git diff format"""
    if not patch:
        return False
    return patch.startswith("diff --git") or patch.startswith("---")


def print_stats(stats: dict):
    """Print statistics"""
    print("=" * 60)
    print("Multi-SWE-Bench Patch Conversion Results")
    print("=" * 60)
    print(f"Total instances: {stats['total']}")
    print(f"With patches: {stats['with_patch']}")
    print(f"Without patches: {stats['without_patch']}")
    print(f"Output file: {stats['output_file']}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Convert Codex output to Multi-SWE-Bench evaluation format"
    )
    parser.add_argument(
        "--input", "-i", 
        required=True, 
        help="Input file (output.jsonl from Codex run)"
    )
    parser.add_argument(
        "--output", "-o", 
        required=True, 
        help="Output file (Multi-SWE-Bench format)"
    )
    parser.add_argument(
        "--model-name", "-m", 
        default="codex-cli", 
        help="Model name to use in output"
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return 1
    
    stats = convert_to_multi_swe_bench_format(
        args.input, 
        args.output, 
        args.model_name
    )
    print_stats(stats)
    
    return 0


if __name__ == "__main__":
    exit(main())

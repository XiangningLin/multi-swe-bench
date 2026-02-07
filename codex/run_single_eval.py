#!/usr/bin/env python3
"""
Single instance evaluation script
"""

import argparse
import json
import os
import subprocess
import sys

def main():
    parser = argparse.ArgumentParser(description="Evaluate a single instance")
    parser.add_argument("--instance-id", "-i", required=True, help="Instance ID to evaluate (e.g., clap-rs__clap-3975)")
    parser.add_argument("--codex-output", default="outputs/rust/output.jsonl", help="Codex output file")
    parser.add_argument("--dataset", default="datasets/rust/clap-rs__clap_dataset.jsonl", help="Dataset file")
    parser.add_argument("--output-dir", default="outputs/rust/single_eval", help="Output directory")
    args = parser.parse_args()

    instance_id = args.instance_id
    
    # Create a temporary output file containing only the specified instance
    temp_output = os.path.join(args.output_dir, f"{instance_id}_output.jsonl")
    os.makedirs(args.output_dir, exist_ok=True)
    
    found = False
    with open(args.codex_output, 'r') as f_in:
        with open(temp_output, 'w') as f_out:
            for line in f_in:
                if not line.strip():
                    continue
                data = json.loads(line)
                if data['instance_id'] == instance_id:
                    f_out.write(line)
                    found = True
                    break  # Take only the first match
    
    if not found:
        print(f"Instance {instance_id} not found in {args.codex_output}")
        return 1
    
    print(f"Found instance: {instance_id}")
    print(f"Created temp file: {temp_output}")
    
    # Run evaluation
    eval_dir = os.path.join(args.output_dir, instance_id.replace("__", "_"))
    cmd = [
        sys.executable, "run_multi_swe_eval.py",
        "--codex-output", temp_output,
        "--dataset", args.dataset,
        "--output-dir", eval_dir,
        "--max-workers", "1"
    ]
    
    print(f"\nRunning evaluation command:")
    print(f"  {' '.join(cmd)}\n")
    
    result = subprocess.run(cmd)
    return result.returncode

if __name__ == "__main__":
    sys.exit(main())

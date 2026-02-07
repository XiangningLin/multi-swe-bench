#!/usr/bin/env python3
"""Batch evaluation script for all generated patches."""
import os
import json
import subprocess
from pathlib import Path

def run_eval(instance_id):
    """Run evaluation for a single instance."""
    output_dir = Path(f"./outputs/{instance_id}")
    # Use the original dataset file (has org, repo, number fields)
    dataset_file = Path(f"./datasets/{instance_id}.jsonl")
    output_jsonl = output_dir / "output.jsonl"
    eval_dir = output_dir / "eval_results"
    
    # Check if patch exists and has content
    patch_file = output_dir / "patches" / f"{instance_id}.patch"
    if not patch_file.exists() or patch_file.stat().st_size == 0:
        return {"instance_id": instance_id, "status": "skipped", "reason": "no patch"}
    
    # Check if dataset exists
    if not dataset_file.exists():
        return {"instance_id": instance_id, "status": "skipped", "reason": "dataset not found"}
    
    # Create necessary directories
    (eval_dir / "workdir").mkdir(parents=True, exist_ok=True)
    (eval_dir / "repos").mkdir(parents=True, exist_ok=True)
    
    # Run evaluation
    cmd = [
        "python", "run_multi_swe_eval.py",
        "--codex-output", str(output_jsonl),
        "--dataset", str(dataset_file),  # Use the original dataset
        "--output-dir", str(eval_dir),
        "--skip-check"
    ]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        
        # Check for results
        report_file = eval_dir / "eval_report.json"
        if report_file.exists():
            with open(report_file) as f:
                report = json.load(f)
            return {
                "instance_id": instance_id,
                "status": "completed",
                "resolved": report.get("resolved_instances", 0),
                "total": report.get("total_instances", 1)
            }
        
        # Check stdout for results
        if "resolved_instances" in result.stdout:
            return {
                "instance_id": instance_id,
                "status": "completed",
                "output": result.stdout[-500:]
            }
        
        return {
            "instance_id": instance_id, 
            "status": "error",
            "reason": result.stderr[-500:] if result.stderr else result.stdout[-500:]
        }
    except subprocess.TimeoutExpired:
        return {"instance_id": instance_id, "status": "timeout"}
    except Exception as e:
        return {"instance_id": instance_id, "status": "error", "reason": str(e)}

if __name__ == "__main__":
    instances = [
        "cli__cli-10043", "cli__cli-10139", "cli__cli-10154", "cli__cli-3270",
        "cli__cli-3519", "cli__cli-3827", "cli__cli-4146", "cli__cli-4534",
        "cli__cli-4845", "cli__cli-5595", "cli__cli-5597", "cli__cli-668",
        "cli__cli-7440", "cli__cli-7626", "cli__cli-8030", "cli__cli-885",
        "cli__cli-8934"
    ]
    
    results = []
    for i, instance_id in enumerate(instances, 1):
        print(f"\n=== [{i}/{len(instances)}] Evaluating {instance_id} ===")
        result = run_eval(instance_id)
        results.append(result)
        print(f"Result: {result}")
    
    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    resolved = sum(1 for r in results if r.get("resolved", 0) > 0)
    completed = sum(1 for r in results if r.get("status") == "completed")
    skipped = sum(1 for r in results if r.get("status") == "skipped")
    errors = sum(1 for r in results if r.get("status") == "error")
    print(f"Total: {len(results)}")
    print(f"Completed: {completed}")
    print(f"Resolved: {resolved}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")
    
    # Save results
    with open("batch_eval_results.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nResults saved to batch_eval_results.json")

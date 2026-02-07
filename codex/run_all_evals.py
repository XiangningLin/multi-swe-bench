#!/usr/bin/env python3
"""
Batch evaluation runner for all models and languages in new_outputs
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime


BASE_PATH = Path(__file__).resolve().parent

# Language to dataset file mapping (relative to project root)
LANGUAGE_DATASETS = {
    "go": [str(BASE_PATH / "datasets" / "go" / "cli__cli_dataset.jsonl")],
    "java": [str(BASE_PATH / "datasets" / "java" / "java_merged_dataset.jsonl")],
    "rust": [str(BASE_PATH / "datasets" / "rust" / "clap-rs__clap_dataset.jsonl")],
    "typescript": [str(BASE_PATH / "datasets" / "ts" / "mui__material-ui_dataset.jsonl")],
}


def generate_eval_config(model: str, language: str, base_dir: Path) -> dict:
    """Generate evaluation configuration"""
    eval_dir = base_dir / "eval_outputs" / model / language
    
    config = {
        "mode": "evaluation",
        "workdir": str(eval_dir / "workdir"),
        "patch_files": [str(eval_dir / "patches.jsonl")],
        "dataset_files": LANGUAGE_DATASETS.get(language, []),
        "force_build": False,
        "output_dir": str(eval_dir / "results"),
        "repo_dir": str(eval_dir / "repos"),
        "need_clone": True,
        "max_workers": 4,
        "log_dir": str(eval_dir / "logs"),
        "log_level": "INFO",
        "clear_env": True
    }
    
    return config


def save_eval_config(config: dict, config_path: Path):
    """Save evaluation configuration file"""
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    print(f"  Config saved: {config_path}")


def run_evaluation(config_path: Path, base_dir: Path) -> bool:
    """Run evaluation"""
    print(f"\n  Running evaluation with config: {config_path}")
    
    # Use multi-swe-bench evaluation script
    cmd = [
        "python", "-m", "multi_swe_bench.harness.run_evaluation",
        "--config", str(config_path)
    ]
    
    try:
        result = subprocess.run(
            cmd,
            cwd=str(base_dir.parent / "multi-swe-bench-repo"),
            capture_output=False,
            timeout=7200,  # 2 hour timeout
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"  ERROR: Evaluation timed out")
        return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def get_eval_results(results_dir: Path) -> dict:
    """Read evaluation results"""
    report_path = results_dir / "final_report.json"
    if report_path.exists():
        with open(report_path, 'r') as f:
            return json.load(f)
    return None


def main():
    base_dir = Path(__file__).resolve().parent
    eval_outputs_dir = base_dir / "eval_outputs"
    
    # Collect all evaluation tasks
    tasks = []
    for model_dir in sorted(eval_outputs_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model = model_dir.name
        for lang_dir in sorted(model_dir.iterdir()):
            if not lang_dir.is_dir():
                continue
            lang = lang_dir.name
            patches_file = lang_dir / "patches.jsonl"
            if patches_file.exists():
                tasks.append((model, lang))
    
    print("=" * 60)
    print("Multi-SWE-Bench Batch Evaluation")
    print("=" * 60)
    print(f"\nFound {len(tasks)} evaluation tasks:\n")
    
    for i, (model, lang) in enumerate(tasks, 1):
        patches_file = eval_outputs_dir / model / lang / "patches.jsonl"
        with open(patches_file, 'r') as f:
            count = sum(1 for _ in f)
        print(f"  {i}. {model}/{lang}: {count} patches")
    
    print("\n" + "-" * 60)
    print("Options:")
    print("  1. Generate all config files only")
    print("  2. Run all evaluations (this may take hours)")
    print("  3. Run specific model/language evaluation")
    print("  4. Exit")
    print("-" * 60)
    
    choice = input("\nSelect option (1-4): ").strip()
    
    if choice == "1":
        # Generate config files only
        print("\n=== Generating config files ===\n")
        for model, lang in tasks:
            eval_dir = eval_outputs_dir / model / lang
            config = generate_eval_config(model, lang, base_dir)
            save_eval_config(config, eval_dir / "eval_config.json")
        print("\nDone! Config files generated.")
        print("\nTo run evaluation manually:")
        print("  cd /path/to/multi-swe-bench-repo")
        print("  python -m multi_swe_bench.harness.run_evaluation --config <config_path>")
        
    elif choice == "2":
        # Run all evaluations
        print("\n=== Running all evaluations ===\n")
        print("WARNING: This may take several hours!")
        confirm = input("Continue? (y/N): ").strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            return
        
        results = {}
        for model, lang in tasks:
            print(f"\n{'='*60}")
            print(f"Evaluating: {model}/{lang}")
            print(f"{'='*60}")
            
            eval_dir = eval_outputs_dir / model / lang
            config = generate_eval_config(model, lang, base_dir)
            config_path = eval_dir / "eval_config.json"
            save_eval_config(config, config_path)
            
            success = run_evaluation(config_path, base_dir)
            
            if success:
                result = get_eval_results(eval_dir / "results")
                if result:
                    results[f"{model}/{lang}"] = result
                    resolved = result.get("resolved_instances", 0)
                    total = result.get("total_instances", 0)
                    print(f"\n  Result: {resolved}/{total} resolved")
            else:
                print(f"\n  Evaluation failed")
        
        # Print summary
        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)
        for key, result in results.items():
            resolved = result.get("resolved_instances", 0)
            total = result.get("total_instances", 0)
            rate = (resolved / total * 100) if total > 0 else 0
            print(f"  {key}: {resolved}/{total} ({rate:.1f}%)")
            
    elif choice == "3":
        # Run specific evaluation
        print("\nAvailable tasks:")
        for i, (model, lang) in enumerate(tasks, 1):
            print(f"  {i}. {model}/{lang}")
        
        idx = input("\nSelect task number: ").strip()
        try:
            idx = int(idx) - 1
            if 0 <= idx < len(tasks):
                model, lang = tasks[idx]
                eval_dir = eval_outputs_dir / model / lang
                config = generate_eval_config(model, lang, base_dir)
                config_path = eval_dir / "eval_config.json"
                save_eval_config(config, config_path)
                
                print(f"\nRunning evaluation for {model}/{lang}...")
                success = run_evaluation(config_path, base_dir)
                
                if success:
                    result = get_eval_results(eval_dir / "results")
                    if result:
                        resolved = result.get("resolved_instances", 0)
                        total = result.get("total_instances", 0)
                        print(f"\nResult: {resolved}/{total} resolved")
            else:
                print("Invalid selection")
        except ValueError:
            print("Invalid input")
    else:
        print("Exiting.")


if __name__ == "__main__":
    main()

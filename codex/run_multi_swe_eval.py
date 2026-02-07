#!/usr/bin/env python3
"""
Run evaluation using the Multi-SWE-Bench official harness

This script integrates the complete evaluation pipeline:
1. Convert Codex output to Multi-SWE-Bench format
2. Call the Multi-SWE-Bench official harness for evaluation
3. Output evaluation results

Prerequisites:
- Install multi-swe-bench: pip install multi-swe-bench
- Install Docker (evaluation runs in Docker containers)

Usage:
    python run_multi_swe_eval.py \
        --codex-output ./outputs/go/output.jsonl \
        --dataset ./datasets/multi_swe_bench_go.jsonl \
        --output-dir ./eval_results/go \
        --model-name codex-cli
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_instance_id(instance_id: str) -> tuple:
    """
    Parse instance_id to extract org, repo, number
    
    Format: org__repo-number (e.g., cli__cli-5595)
    """
    # Format: org__repo-number
    parts = instance_id.rsplit("-", 1)
    if len(parts) != 2:
        return None, None, None
    
    org_repo = parts[0]
    number = parts[1]
    
    org_repo_parts = org_repo.split("__", 1)
    if len(org_repo_parts) != 2:
        return None, None, None
    
    org = org_repo_parts[0]
    repo = org_repo_parts[1]
    
    return org, repo, number


def convert_codex_to_multi_swe_format(
    codex_output: str,
    output_file: str,
    model_name: str = "codex-cli",
    dataset_file: str = None
) -> int:
    """
    Convert Codex output to Multi-SWE-Bench format
    
    Args:
        codex_output: Codex output file (output.jsonl)
        output_file: Output file path (Multi-SWE-Bench format)
        model_name: Model name
        dataset_file: Dataset file (for extracting additional fields)
    
    Returns:
        int: Number of converted instances
    """
    # Load dataset for additional information
    dataset_info = {}
    if dataset_file and os.path.exists(dataset_file):
        with open(dataset_file, 'r') as f:
            for line in f:
                if not line.strip():
                    continue
                data = json.loads(line)
                instance_id = data.get("instance_id")
                if instance_id:
                    dataset_info[instance_id] = data
    
    results = []
    
    with open(codex_output, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            instance_id = data["instance_id"]
            
            # Parse instance_id to get org, repo, number
            org, repo, number = parse_instance_id(instance_id)
            
            # Get additional info from dataset
            ds_info = dataset_info.get(instance_id, {})
            
            entry = {
                "org": org or ds_info.get("org", ""),
                "repo": repo or ds_info.get("repo", ""),
                "number": number or str(ds_info.get("number", "")),
                "instance_id": instance_id,
                "model_name_or_path": model_name,
                "fix_patch": data.get("patch", ""),  # Multi-SWE-Bench requires fix_patch
                "model_patch": data.get("patch", ""),
            }
            results.append(entry)
    
    os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
    
    with open(output_file, 'w') as f:
        for entry in results:
            f.write(json.dumps(entry) + "\n")
    
    logger.info(f"Converted {len(results)} instances to Multi-SWE-Bench format")
    return len(results)


def create_eval_config(
    patch_file: str,
    dataset_file: str,
    output_dir: str,
    config_file: str,
    max_workers: int = 4,
) -> str:
    """
    Create Multi-SWE-Bench evaluation configuration file
    
    Args:
        patch_file: Patch file path
        dataset_file: Dataset file path
        output_dir: Output directory
        config_file: Configuration file save path
        max_workers: Number of parallel workers
    
    Returns:
        str: Configuration file path
    """
    config = {
        "mode": "evaluation",
        "workdir": os.path.join(output_dir, "workdir"),
        "patch_files": [patch_file],
        "dataset_files": [dataset_file],
        "force_build": False,
        "output_dir": os.path.join(output_dir, "results"),
        "repo_dir": os.path.join(output_dir, "repos"),
        "need_clone": True,
        "max_workers": max_workers,
        "log_dir": os.path.join(output_dir, "logs"),
        "log_level": "INFO",
        "clear_env": True,
    }
    
    os.makedirs(os.path.dirname(config_file) if os.path.dirname(config_file) else ".", exist_ok=True)
    
    with open(config_file, 'w') as f:
        json.dump(config, f, indent=2)
    
    logger.info(f"Created evaluation config: {config_file}")
    return config_file


def run_multi_swe_bench_eval(config_file: str) -> Dict[str, Any]:
    """
    Run the Multi-SWE-Bench official evaluation
    
    Args:
        config_file: Configuration file path
    
    Returns:
        dict: Evaluation results
    """
    logger.info("Running Multi-SWE-Bench evaluation...")
    logger.info("This requires Docker to be running.")
    
    try:
        # Call the Multi-SWE-Bench official harness
        cmd = [
            sys.executable,
            "-m", "multi_swe_bench.harness.run_evaluation",
            "--config", config_file
        ]
        
        logger.info(f"Command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,  # 2 hour timeout
        )
        
        if result.returncode == 0:
            logger.info("Evaluation completed successfully")
            logger.info(result.stdout)
        else:
            logger.error(f"Evaluation failed with code {result.returncode}")
            logger.error(result.stderr)
        
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
        
    except subprocess.TimeoutExpired:
        logger.error("Evaluation timed out")
        return {"success": False, "error": "Timeout"}
    except FileNotFoundError:
        logger.error("multi_swe_bench not found. Please install it: pip install multi-swe-bench")
        return {"success": False, "error": "multi_swe_bench not installed"}
    except Exception as e:
        logger.error(f"Error running evaluation: {e}")
        return {"success": False, "error": str(e)}


def check_dependencies() -> bool:
    """Check if required dependencies are installed"""
    # Check multi_swe_bench
    try:
        import multi_swe_bench
        logger.info(f"multi_swe_bench version: {getattr(multi_swe_bench, '__version__', 'unknown')}")
    except ImportError:
        logger.error("multi_swe_bench not installed. Please run: pip install multi-swe-bench")
        return False
    
    # Check Docker
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.error("Docker is not running. Please start Docker.")
            return False
        logger.info("Docker is running")
    except FileNotFoundError:
        logger.error("Docker not found. Please install Docker.")
        return False
    except Exception as e:
        logger.error(f"Error checking Docker: {e}")
        return False
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Run Multi-SWE-Bench evaluation with Codex patches"
    )
    parser.add_argument(
        "--codex-output",
        type=str,
        required=True,
        help="Path to Codex output file (output.jsonl)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Path to Multi-SWE-Bench dataset file",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./eval_results",
        help="Output directory for evaluation results",
    )
    parser.add_argument(
        "--model-name",
        type=str,
        default="codex-cli",
        help="Model name to use in evaluation",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=4,
        help="Number of parallel workers for evaluation",
    )
    parser.add_argument(
        "--skip-check",
        action="store_true",
        help="Skip dependency checks",
    )
    parser.add_argument(
        "--convert-only",
        action="store_true",
        help="Only convert Codex output to Multi-SWE-Bench format (skip evaluation)",
    )
    
    args = parser.parse_args()
    
    # Check input files
    if not os.path.exists(args.codex_output):
        logger.error(f"Codex output file not found: {args.codex_output}")
        return 1
    
    if not os.path.exists(args.dataset):
        logger.error(f"Dataset file not found: {args.dataset}")
        return 1
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Convert format
    patch_file = os.path.join(args.output_dir, "patches.jsonl")
    count = convert_codex_to_multi_swe_format(
        args.codex_output,
        patch_file,
        args.model_name,
        args.dataset,  # Pass dataset file
    )
    
    if count == 0:
        logger.error("No instances to evaluate")
        return 1
    
    if args.convert_only:
        logger.info(f"Conversion complete. Patch file: {patch_file}")
        return 0
    
    # Check dependencies
    if not args.skip_check:
        if not check_dependencies():
            logger.error("Dependency check failed. Use --skip-check to bypass.")
            return 1
    
    # Create configuration file
    config_file = os.path.join(args.output_dir, "eval_config.json")
    create_eval_config(
        patch_file=patch_file,
        dataset_file=args.dataset,
        output_dir=args.output_dir,
        config_file=config_file,
        max_workers=args.max_workers,
    )
    
    # Run evaluation
    result = run_multi_swe_bench_eval(config_file)
    
    if result["success"]:
        logger.info("=" * 60)
        logger.info("Evaluation completed successfully!")
        logger.info(f"Results saved to: {args.output_dir}")
        logger.info("=" * 60)
        return 0
    else:
        logger.error("Evaluation failed")
        return 1


if __name__ == "__main__":
    exit(main())

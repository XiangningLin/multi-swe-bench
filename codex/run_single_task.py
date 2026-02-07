#!/usr/bin/env python3
"""
Single Task Runner - Run one Multi-SWE-Bench instance at a time

Usage:
    # Load dataset from HuggingFace and run a specific instance
    python run_single_task.py --instance-id cli__cli-10239 --language go
    
    # Load from a local JSONL file
    python run_single_task.py --dataset ./datasets/go.jsonl --instance-id cli__cli-10239 --language go
    
    # List all instances in the dataset
    python run_single_task.py --dataset ./datasets/go.jsonl --list-instances
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from data_loader import load_multi_swe_bench, validate_instance
from instruction import get_instruction
from codex_runner import CodexRunner
from utils import (
    setup_logging,
    prepare_workspace,
    save_patch,
    save_result,
    cleanup_workspace,
    get_timestamp,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Multi-SWE-Bench HuggingFace datasets
HUGGINGFACE_DATASETS = {
    "go": "ByteDance-Seed/Multi-SWE-bench",
    "python": "ByteDance-Seed/Multi-SWE-bench", 
    "java": "ByteDance-Seed/Multi-SWE-bench",
    "rust": "ByteDance-Seed/Multi-SWE-bench",
    "typescript": "ByteDance-Seed/Multi-SWE-bench",
    "javascript": "ByteDance-Seed/Multi-SWE-bench",
    "c": "ByteDance-Seed/Multi-SWE-bench",
    "cpp": "ByteDance-Seed/Multi-SWE-bench",
}


def list_instances(dataset_path: str, language: str = None, limit: int = 20):
    """List instances in the dataset"""
    try:
        df = load_multi_swe_bench(dataset_path, split="train", limit=None)
        
        print(f"\n{'='*80}")
        print(f"Dataset: {dataset_path}")
        print(f"Total instances: {len(df)}")
        print(f"{'='*80}\n")
        
        # Filter by language (if specified)
        if language and "language" in df.columns:
            df = df[df["language"] == language]
            print(f"Filtered by language '{language}': {len(df)} instances\n")
        
        print(f"{'Instance ID':<50} {'Repo':<30}")
        print("-" * 80)
        
        for i, (_, row) in enumerate(df.iterrows()):
            if i >= limit:
                print(f"... and {len(df) - limit} more instances")
                break
            print(f"{row['instance_id']:<50} {row['repo']:<30}")
        
        print()
        return df
        
    except Exception as e:
        logger.error(f"Error loading dataset: {e}")
        return None


def run_single_instance(
    instance_id: str,
    dataset_path: str,
    language: str,
    output_dir: str,
    keep_workspace: bool = False,
    dry_run: bool = False,
):
    """Run a single instance"""
    
    logger.info(f"{'='*60}")
    logger.info(f"Running single instance: {instance_id}")
    logger.info(f"{'='*60}")
    
    # Load dataset
    logger.info(f"Loading dataset from: {dataset_path}")
    df = load_multi_swe_bench(
        dataset_path=dataset_path,
        split="train",
        instance_ids=[instance_id],
    )
    
    if len(df) == 0:
        logger.error(f"Instance not found: {instance_id}")
        logger.info("Use --list-instances to see available instances")
        return None
    
    instance = df.iloc[0]
    
    # Display instance information
    logger.info(f"\nInstance Details:")
    logger.info(f"  ID: {instance['instance_id']}")
    logger.info(f"  Repo: {instance['repo']}")
    logger.info(f"  Base Commit: {instance['base_commit']}")
    logger.info(f"  Problem Statement (first 200 chars):")
    logger.info(f"    {instance['problem_statement'][:200]}...")
    
    if dry_run:
        logger.info("\n[DRY RUN] Would run Codex on this instance")
        return {"instance_id": instance_id, "dry_run": True}
    
    # Validate instance
    if not validate_instance(instance):
        logger.error("Instance validation failed")
        return None
    
    # Initialize Codex Runner
    # Get model from config.yaml or environment variable
    import yaml
    config_path = Path(__file__).parent / "config.yaml"
    config = {}
    if config_path.exists():
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
    
    codex_config = config.get("codex", {})
    model = os.environ.get("CODEX_MODEL", codex_config.get("model", "o4-mini"))
    codex_runner = CodexRunner(
        timeout=codex_config.get("timeout", 1800),
        auto_approve=codex_config.get("auto_approve", True),
        model=model
    )
    
    if not codex_runner.check_codex_installed():
        logger.error("Codex CLI not installed. Please run: npm i -g @openai/codex")
        return None
    
    # Prepare result
    result = {
        "instance_id": instance_id,
        "success": False,
        "patch": "",
        "error": None,
        "start_time": get_timestamp(),
        "end_time": None,
        "codex_output": "",
    }
    
    workspace_dir = None
    try:
        # Prepare workspace
        workspace_base = "./workspace"
        os.makedirs(workspace_base, exist_ok=True)
        
        logger.info(f"\nPreparing workspace...")
        workspace_dir = prepare_workspace(
            instance_id=instance_id,
            repo=instance["repo"],
            base_commit=instance["base_commit"],
            workspace_base=workspace_base,
        )
        logger.info(f"Workspace: {workspace_dir}")
        
        # Construct instruction
        instruction = get_instruction(instance, language)
        logger.info(f"Instruction length: {len(instruction)} chars")
        
        # Run Codex
        logger.info(f"\nRunning Codex CLI...")
        codex_result = codex_runner.run(workspace_dir, instruction, base_commit=instance["base_commit"])
        
        result["success"] = codex_result["success"]
        result["patch"] = codex_result["patch"]
        result["codex_output"] = codex_result["output"]
        
        if codex_result["error"]:
            result["error"] = codex_result["error"]
        
        # Save patch
        if result["patch"]:
            os.makedirs(output_dir, exist_ok=True)
            os.makedirs(os.path.join(output_dir, "patches"), exist_ok=True)
            save_patch(result["patch"], output_dir, instance_id)
            logger.info(f"Patch saved to: {output_dir}/patches/{instance_id}.patch")
        
    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up workspace
        if workspace_dir and not keep_workspace:
            cleanup_workspace(workspace_dir)
            logger.info("Workspace cleaned up")
        elif workspace_dir:
            logger.info(f"Workspace kept at: {workspace_dir}")
        
        result["end_time"] = get_timestamp()
    
    # Save result
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "output.jsonl")
    save_result(result, output_file)
    logger.info(f"Result saved to: {output_file}")
    
    # Print result summary
    logger.info(f"\n{'='*60}")
    logger.info(f"Result Summary")
    logger.info(f"{'='*60}")
    logger.info(f"Instance: {instance_id}")
    logger.info(f"Success: {result['success']}")
    logger.info(f"Patch generated: {'Yes' if result['patch'] else 'No'}")
    if result["error"]:
        logger.info(f"Error: {result['error']}")
    logger.info(f"{'='*60}")
    
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run a single Multi-SWE-Bench instance with Codex"
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        help="Instance ID to run (e.g., cli__cli-10239)",
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Path to dataset (JSONL) or HuggingFace dataset name. If not specified, uses ByteDance-Seed/Multi-SWE-bench",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="go",
        choices=["python", "java", "go", "rust", "typescript", "javascript", "c", "cpp"],
        help="Programming language",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./outputs/single",
        help="Output directory",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep workspace after running",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without running Codex",
    )
    parser.add_argument(
        "--list-instances",
        action="store_true",
        help="List available instances in the dataset",
    )
    parser.add_argument(
        "--list-limit",
        type=int,
        default=20,
        help="Number of instances to show when listing",
    )
    
    args = parser.parse_args()
    
    # Determine dataset path
    dataset_path = args.dataset
    if dataset_path is None:
        # Prefer using local dataset
        local_dataset_paths = {
            "go": "datasets/go/cli__cli_dataset.jsonl",
            "java": "datasets/java/java_merged_dataset.jsonl",
            "rust": "datasets/rust/clap-rs__clap_dataset.jsonl",
            "typescript": "datasets/ts/mui__material-ui_dataset.jsonl",
        }
        
        local_path = local_dataset_paths.get(args.language)
        if local_path and os.path.exists(local_path):
            dataset_path = local_path
            logger.info(f"Using local dataset: {dataset_path}")
        else:
            dataset_path = HUGGINGFACE_DATASETS.get(args.language, "ByteDance-Seed/Multi-SWE-bench")
            logger.info(f"Using HuggingFace dataset: {dataset_path}")
            logger.warning("If HuggingFace loading fails, consider downloading local dataset files")
    
    # List instances
    if args.list_instances:
        list_instances(dataset_path, args.language, args.list_limit)
        return 0
    
    # Run single instance
    if not args.instance_id:
        parser.error("--instance-id is required (or use --list-instances to see available instances)")
    
    result = run_single_instance(
        instance_id=args.instance_id,
        dataset_path=dataset_path,
        language=args.language,
        output_dir=args.output_dir,
        keep_workspace=args.keep_workspace,
        dry_run=args.dry_run,
    )
    
    if result and result.get("success"):
        return 0
    return 1


if __name__ == "__main__":
    exit(main())

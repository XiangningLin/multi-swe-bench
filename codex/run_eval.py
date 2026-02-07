#!/usr/bin/env python3
"""
Codex Multi-SWE-Bench Evaluation Main Entry

Run Multi-SWE-Bench evaluation using OpenAI Codex CLI

Usage:
    python run_eval.py --dataset path/to/dataset.jsonl --output-dir ./outputs --language python
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from tqdm import tqdm

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from data_loader import (
    load_multi_swe_bench,
    iterate_instances,
    validate_instance,
)
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

logger = logging.getLogger(__name__)


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """Load configuration file"""
    default_config = {
        "codex": {
            "timeout": 1800,
            "auto_approve": True,
            "model": "gpt-5-nano",
        },
        "evaluation": {
            "workspace_dir": "./workspace",
            "output_dir": "./outputs",
            "keep_workspace": False,
            "num_workers": 1,
        },
        "logging": {
            "level": "INFO",
            "file": None,
        },
    }

    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            file_config = yaml.safe_load(f)
            if file_config:
                # Merge configuration
                for key in file_config:
                    if key in default_config and isinstance(default_config[key], dict):
                        default_config[key].update(file_config[key])
                    else:
                        default_config[key] = file_config[key]

    return default_config


def process_instance(
    instance: Any,
    language: str,
    codex_runner: CodexRunner,
    config: Dict[str, Any],
    output_dir: str,
) -> Dict[str, Any]:
    """
    Process a single instance

    Args:
        instance: Instance data
        language: Programming language
        codex_runner: Codex runner
        config: Configuration
        output_dir: Output directory

    Returns:
        dict: Processing result
    """
    instance_id = instance["instance_id"]
    result = {
        "instance_id": instance_id,
        "success": False,
        "patch": "",
        "error": None,
        "start_time": get_timestamp(),
        "end_time": None,
        "codex_output": "",
    }

    logger.info(f"Processing instance: {instance_id}")

    # Validate instance
    if not validate_instance(instance):
        result["error"] = "Invalid instance data"
        result["end_time"] = get_timestamp()
        return result

    workspace_dir = None
    try:
        # Prepare workspace
        workspace_base = config["evaluation"]["workspace_dir"]
        workspace_dir = prepare_workspace(
            instance_id=instance_id,
            repo=instance["repo"],
            base_commit=instance["base_commit"],
            workspace_base=workspace_base,
        )

        # Construct instruction
        instruction = get_instruction(instance, language)
        logger.debug(f"Instruction length: {len(instruction)} chars")

        # Run Codex
        codex_result = codex_runner.run(workspace_dir, instruction)

        result["success"] = codex_result["success"]
        result["patch"] = codex_result["patch"]
        result["codex_output"] = codex_result["output"]

        if codex_result["error"]:
            result["error"] = codex_result["error"]

        # Save patch
        if result["patch"]:
            save_patch(result["patch"], output_dir, instance_id)

    except Exception as e:
        result["error"] = str(e)
        logger.error(f"Error processing {instance_id}: {e}")

    finally:
        # Clean up workspace
        if workspace_dir and not config["evaluation"].get("keep_workspace", False):
            cleanup_workspace(workspace_dir)

        result["end_time"] = get_timestamp()

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Run Multi-SWE-Bench evaluation with Codex CLI"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="Path to dataset (JSONL file or HuggingFace dataset name)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./outputs",
        help="Output directory for results",
    )
    parser.add_argument(
        "--language",
        type=str,
        default="python",
        choices=["python", "java", "go", "rust", "typescript", "javascript", "c", "cpp"],
        help="Programming language",
    )
    parser.add_argument(
        "--split",
        type=str,
        default="train",
        help="Dataset split to use",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of instances to evaluate",
    )
    parser.add_argument(
        "--instance-id",
        type=str,
        default=None,
        help="Evaluate a single instance by ID",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="Path to config file",
    )
    parser.add_argument(
        "--keep-workspace",
        action="store_true",
        help="Keep workspace directories after evaluation",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run (don't actually run Codex)",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config(args.config)

    # Override configuration
    config["evaluation"]["output_dir"] = args.output_dir
    if args.keep_workspace:
        config["evaluation"]["keep_workspace"] = True
    config["logging"]["level"] = args.log_level

    # Set up logging
    log_file = os.path.join(args.output_dir, "logs", "eval.log")
    setup_logging(config["logging"]["level"], log_file)

    logger.info("=" * 60)
    logger.info("Codex Multi-SWE-Bench Evaluation")
    logger.info("=" * 60)
    logger.info(f"Dataset: {args.dataset}")
    logger.info(f"Language: {args.language}")
    logger.info(f"Output directory: {args.output_dir}")

    # Check Codex CLI
    codex_runner = CodexRunner(
        timeout=config["codex"]["timeout"],
        auto_approve=config["codex"]["auto_approve"],
        model=config["codex"].get("model", "gpt-5-nano"),
    )

    if not args.dry_run:
        if not codex_runner.check_codex_installed():
            logger.error("Codex CLI is not installed. Please run: npm i -g @openai/codex")
            sys.exit(1)

    # Load dataset
    instance_ids = [args.instance_id] if args.instance_id else None
    dataset = load_multi_swe_bench(
        dataset_path=args.dataset,
        split=args.split,
        limit=args.limit,
        instance_ids=instance_ids,
    )

    logger.info(f"Loaded {len(dataset)} instances")

    if len(dataset) == 0:
        logger.warning("No instances to evaluate")
        sys.exit(0)

    # Create output directories
    os.makedirs(args.output_dir, exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "patches"), exist_ok=True)
    os.makedirs(os.path.join(args.output_dir, "logs"), exist_ok=True)

    output_file = os.path.join(args.output_dir, "output.jsonl")

    # Process instances
    success_count = 0
    error_count = 0

    for instance in tqdm(iterate_instances(dataset), total=len(dataset), desc="Evaluating"):
        if args.dry_run:
            logger.info(f"[DRY RUN] Would process: {instance['instance_id']}")
            continue

        result = process_instance(
            instance=instance,
            language=args.language,
            codex_runner=codex_runner,
            config=config,
            output_dir=args.output_dir,
        )

        # Save result
        save_result(result, output_file)

        if result["success"]:
            success_count += 1
        else:
            error_count += 1

        # Output progress
        logger.info(
            f"Processed {instance['instance_id']}: "
            f"{'SUCCESS' if result['success'] else 'FAILED'}"
        )

    # Output statistics
    logger.info("=" * 60)
    logger.info("Evaluation Complete")
    logger.info("=" * 60)
    logger.info(f"Total instances: {len(dataset)}")
    logger.info(f"Successful: {success_count}")
    logger.info(f"Failed: {error_count}")
    logger.info(f"Results saved to: {output_file}")


if __name__ == "__main__":
    main()

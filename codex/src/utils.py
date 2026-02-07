"""
Utility Functions Module
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Dict

import git

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> None:
    """
    Set up logging configuration

    Args:
        log_level: Logging level
        log_file: Log file path
    """
    handlers = [logging.StreamHandler()]

    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=handlers,
    )


def clone_repo(repo_url: str, target_dir: str, base_commit: Optional[str] = None) -> str:
    """
    Clone a repository to the specified directory

    Args:
        repo_url: Repository URL
        target_dir: Target directory
        base_commit: Commit to checkout (optional)

    Returns:
        str: Path to the cloned repository
    """
    logger.info(f"Cloning {repo_url} to {target_dir}")

    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)

    repo = git.Repo.clone_from(repo_url, target_dir)

    if base_commit:
        logger.info(f"Checking out to {base_commit}")
        repo.git.checkout(base_commit)

    return target_dir


def prepare_workspace(
    instance_id: str,
    repo: str,
    base_commit: str,
    workspace_base: str,
) -> str:
    """
    Prepare the workspace directory

    Args:
        instance_id: Instance ID
        repo: Repository name (format: owner/repo)
        base_commit: Base commit
        workspace_base: Base path for workspace

    Returns:
        str: Path to the prepared workspace directory
    """
    # Construct repository URL
    repo_url = f"https://github.com/{repo}.git"

    # Construct target directory
    safe_instance_id = instance_id.replace("/", "__").replace(":", "_")
    target_dir = os.path.join(workspace_base, safe_instance_id)

    # Clone repository
    clone_repo(repo_url, target_dir, base_commit)

    return target_dir


def get_git_diff(repo_path: str) -> str:
    """
    Get git diff for the repository

    Args:
        repo_path: Repository path

    Returns:
        str: git diff output
    """
    try:
        repo = git.Repo(repo_path)
        # Get changes in tracked files
        diff = repo.git.diff()
        # Get untracked files
        untracked = repo.untracked_files

        result = diff
        if untracked:
            result += f"\n\nUntracked files:\n" + "\n".join(untracked)

        return result
    except Exception as e:
        logger.error(f"Error getting git diff: {e}")
        return ""


def save_patch(patch: str, output_dir: str, instance_id: str) -> str:
    """
    Save patch to a file

    Args:
        patch: Patch content
        output_dir: Output directory
        instance_id: Instance ID

    Returns:
        str: Patch file path
    """
    patches_dir = os.path.join(output_dir, "patches")
    os.makedirs(patches_dir, exist_ok=True)

    safe_instance_id = instance_id.replace("/", "__").replace(":", "_")
    patch_file = os.path.join(patches_dir, f"{safe_instance_id}.patch")

    with open(patch_file, "w") as f:
        f.write(patch)

    logger.info(f"Saved patch to {patch_file}")
    return patch_file


def save_result(
    result: Dict[str, Any],
    output_file: str,
) -> None:
    """
    Save evaluation result to a JSONL file

    Args:
        result: Evaluation result
        output_file: Output file path
    """
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    with open(output_file, "a") as f:
        f.write(json.dumps(result) + "\n")


def cleanup_workspace(workspace_dir: str) -> None:
    """
    Clean up the workspace directory

    Args:
        workspace_dir: Workspace directory path
    """
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
        logger.info(f"Cleaned up workspace: {workspace_dir}")


def get_timestamp() -> str:
    """
    Get the current timestamp

    Returns:
        str: ISO format timestamp
    """
    return datetime.now().isoformat()

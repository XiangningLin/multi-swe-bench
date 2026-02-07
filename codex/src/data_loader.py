"""
Data Loading Module - Load Multi-SWE-Bench datasets
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator, Optional, List

import pandas as pd
from datasets import load_dataset

logger = logging.getLogger(__name__)


def normalize_instance(instance: dict) -> dict:
    """
    Normalize instance data format for compatibility with different versions
    of the Multi-SWE-Bench dataset
    
    New format:
        - base: {"label": "...", "ref": "...", "sha": "commit_sha"}
        - org: "fasterxml"
        - repo: "jackson-core"
        - resolved_issues: [{"number": ..., "title": ..., "body": ...}]
    
    Old format / normalized:
        - base_commit: "commit_sha"
        - repo: "fasterxml/jackson-core"
        - problem_statement: "issue title\n\nissue body"
    """
    result = dict(instance)
    
    # Handle base_commit
    if "base_commit" not in result or pd.isna(result.get("base_commit")):
        base = result.get("base")
        if isinstance(base, dict):
            result["base_commit"] = base.get("sha", "HEAD")
        elif isinstance(base, str):
            result["base_commit"] = base
        else:
            result["base_commit"] = "HEAD"
    
    # Handle repo (needs to include org)
    org = result.get("org", "")
    repo = result.get("repo", "")
    if org and "/" not in repo:
        result["repo"] = f"{org}/{repo}"
    
    # Handle problem_statement
    if "problem_statement" not in result or pd.isna(result.get("problem_statement")):
        # Construct from resolved_issues or title/body
        title = result.get("title", "")
        body = result.get("body", "")
        
        resolved_issues = result.get("resolved_issues", [])
        if resolved_issues and isinstance(resolved_issues, list):
            # Use the first resolved issue
            issue = resolved_issues[0]
            if isinstance(issue, dict):
                title = issue.get("title", title)
                body = issue.get("body", body) or ""
        
        result["problem_statement"] = f"{title}\n\n{body}".strip()
    
    # Handle version
    if "version" not in result or pd.isna(result.get("version")):
        base = result.get("base")
        if isinstance(base, dict):
            result["version"] = base.get("ref", "main")
        else:
            result["version"] = "main"
    
    return result


def load_multi_swe_bench(
    dataset_path: str,
    split: str = "train",
    limit: Optional[int] = None,
    instance_ids: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Load a Multi-SWE-Bench dataset

    Args:
        dataset_path: Dataset path (JSONL file or HuggingFace dataset name)
        split: Dataset split (default "train")
        limit: Limit the number of instances to load
        instance_ids: List of specific instance IDs to load

    Returns:
        pd.DataFrame: DataFrame containing the dataset
    """
    logger.info(f"Loading dataset from {dataset_path}")

    # Determine if it's a local file or HuggingFace dataset
    if dataset_path.endswith(".jsonl") or dataset_path.endswith(".json"):
        # Local JSONL file - load directly with JSON (avoids complex structure issues with datasets lib)
        records = []
        with open(dataset_path, 'r') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        df = pd.DataFrame(records)
    else:
        # HuggingFace dataset
        try:
            logger.info(f"Loading from HuggingFace: {dataset_path}")
            # Try to load; provide more detailed error info on failure
            dataset = load_dataset(
                dataset_path, 
                split=split, 
                trust_remote_code=True,
                num_proc=1,  # Use single process to avoid concurrency issues
            )
            df = dataset.to_pandas()
        except Exception as e:
            logger.error(f"Failed to load from HuggingFace: {e}")
            logger.error("This might be due to:")
            logger.error("  1. Network connectivity issues")
            logger.error("  2. HuggingFace dataset format changes")
            logger.error("  3. Dataset download timeout")
            logger.info("")
            logger.info("Solutions:")
            logger.info("  1. Check your network connection")
            logger.info("  2. Use a local JSONL file with --dataset option")
            logger.info("  3. Try downloading the dataset manually from HuggingFace")
            raise

    logger.info(f"Loaded {len(df)} instances")

    # Normalize data format
    normalized_records = [normalize_instance(row.to_dict()) for _, row in df.iterrows()]
    df = pd.DataFrame(normalized_records)
    logger.info("Normalized instance data format")

    # Filter by instance_id
    if instance_ids:
        df = df[df["instance_id"].isin(instance_ids)]
        logger.info(f"Filtered to {len(df)} instances by instance_ids")

    # Limit count
    if limit and limit > 0:
        df = df.head(limit)
        logger.info(f"Limited to {len(df)} instances")

    return df


def iterate_instances(df: pd.DataFrame) -> Iterator[pd.Series]:
    """
    Iterate over instances in the dataset

    Args:
        df: Dataset DataFrame

    Yields:
        pd.Series: Each instance
    """
    for _, row in df.iterrows():
        yield row


def get_instance_by_id(df: pd.DataFrame, instance_id: str) -> Optional[pd.Series]:
    """
    Get an instance by instance_id

    Args:
        df: Dataset DataFrame
        instance_id: Instance ID

    Returns:
        pd.Series | None: Instance data, or None if not found
    """
    matches = df[df["instance_id"] == instance_id]
    if len(matches) == 0:
        return None
    return matches.iloc[0]


def validate_instance(instance: pd.Series) -> bool:
    """
    Validate that instance data is complete

    Args:
        instance: Instance data

    Returns:
        bool: Whether the data is valid
    """
    required_fields = [
        "instance_id",
        "repo",
        "base_commit",
        "problem_statement",
    ]

    for field in required_fields:
        if field not in instance or pd.isna(instance[field]):
            logger.warning(f"Instance missing required field: {field}")
            return False

    return True

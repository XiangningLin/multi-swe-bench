#!/usr/bin/env python3
"""
Simplified Multi-SWE-Bench Evaluation Script

Due to compatibility issues with the multi-swe-bench package on macOS,
this script implements a basic patch validation workflow:
1. Clone the repository and checkout to base_commit
2. Apply the patch
3. Run tests (if available)
4. Report results

Usage:
    python simple_eval.py --patch ./outputs/go/patches.jsonl --dataset ./datasets/example_go.jsonl
"""

import argparse
import json
import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def clone_repo(repo: str, target_dir: str, base_commit: str) -> bool:
    """Clone a repository and checkout to the specified commit"""
    repo_url = f"https://github.com/{repo}.git"
    print(f"Cloning {repo_url}...")
    
    try:
        result = subprocess.run(
            ["git", "clone", "--depth", "100", repo_url, target_dir],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            print(f"Clone failed: {result.stderr}")
            return False
        
        # Fetch more history if needed
        subprocess.run(
            ["git", "fetch", "--unshallow"],
            cwd=target_dir,
            capture_output=True,
            timeout=300,
        )
        
        # Checkout to base commit
        result = subprocess.run(
            ["git", "checkout", base_commit],
            cwd=target_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            print(f"Checkout failed: {result.stderr}")
            return False
        
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False


def apply_patch(patch_content: str, repo_dir: str) -> bool:
    """Apply a patch"""
    print("Applying patch...")
    
    try:
        result = subprocess.run(
            ["git", "apply", "--check", "-"],
            input=patch_content,
            cwd=repo_dir,
            capture_output=True,
            text=True,
            timeout=60,
        )
        
        if result.returncode != 0:
            print(f"Patch check failed: {result.stderr}")
            # Try with --3way
            result = subprocess.run(
                ["git", "apply", "-"],
                input=patch_content,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                print(f"Patch apply failed: {result.stderr}")
                return False
        else:
            # Apply the patch
            result = subprocess.run(
                ["git", "apply", "-"],
                input=patch_content,
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode != 0:
                print(f"Patch apply failed: {result.stderr}")
                return False
        
        print("Patch applied successfully!")
        return True
    except Exception as e:
        print(f"Error applying patch: {e}")
        return False


def run_tests(repo_dir: str, language: str) -> dict:
    """Run tests"""
    print(f"Running tests for {language}...")
    
    result = {
        "tests_run": False,
        "tests_passed": False,
        "output": "",
        "error": "",
    }
    
    try:
        if language == "go":
            # For Go, try to run tests
            proc = subprocess.run(
                ["go", "test", "./..."],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=600,
            )
            result["tests_run"] = True
            result["output"] = proc.stdout
            result["error"] = proc.stderr
            result["tests_passed"] = proc.returncode == 0
            
        elif language == "python":
            # For Python, try pytest
            proc = subprocess.run(
                ["python", "-m", "pytest", "-x", "-v"],
                cwd=repo_dir,
                capture_output=True,
                text=True,
                timeout=600,
            )
            result["tests_run"] = True
            result["output"] = proc.stdout
            result["error"] = proc.stderr
            result["tests_passed"] = proc.returncode == 0
            
        else:
            print(f"Test runner not implemented for {language}")
            
    except subprocess.TimeoutExpired:
        result["error"] = "Test timeout"
    except Exception as e:
        result["error"] = str(e)
    
    return result


def evaluate_instance(instance: dict, patch: dict, work_dir: str) -> dict:
    """Evaluate a single instance"""
    instance_id = instance["instance_id"]
    print(f"\n{'='*60}")
    print(f"Evaluating: {instance_id}")
    print(f"{'='*60}")
    
    result = {
        "instance_id": instance_id,
        "clone_success": False,
        "patch_applies": False,
        "tests_run": False,
        "tests_passed": False,
        "error": None,
    }
    
    repo_dir = os.path.join(work_dir, instance_id.replace("/", "__"))
    
    try:
        # Step 1: Clone repo
        if not clone_repo(instance["repo"], repo_dir, instance["base_commit"]):
            result["error"] = "Clone failed"
            return result
        result["clone_success"] = True
        
        # Step 2: Apply patch
        patch_content = patch.get("model_patch", "")
        if not patch_content:
            result["error"] = "No patch content"
            return result
        
        if not apply_patch(patch_content, repo_dir):
            result["error"] = "Patch apply failed"
            return result
        result["patch_applies"] = True
        
        # Step 3: Show diff
        diff_result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_dir,
            capture_output=True,
            text=True,
        )
        print(f"\nApplied changes:\n{diff_result.stdout[:500]}...")
        
        # Step 4: Run tests (optional)
        language = instance.get("language", "go")
        test_result = run_tests(repo_dir, language)
        result.update(test_result)
        
    except Exception as e:
        result["error"] = str(e)
    finally:
        # Cleanup
        if os.path.exists(repo_dir):
            shutil.rmtree(repo_dir, ignore_errors=True)
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Simple Multi-SWE-Bench Evaluation")
    parser.add_argument("--patch", "-p", required=True, help="Path to patches.jsonl")
    parser.add_argument("--dataset", "-d", required=True, help="Path to dataset.jsonl")
    parser.add_argument("--work-dir", "-w", default="./eval_workspace", help="Work directory")
    parser.add_argument("--instance-id", "-i", help="Evaluate specific instance only")
    
    args = parser.parse_args()
    
    # Load dataset
    print(f"Loading dataset from {args.dataset}...")
    instances = {}
    with open(args.dataset, "r") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                instances[data["instance_id"]] = data
    print(f"Loaded {len(instances)} instances")
    
    # Load patches
    print(f"Loading patches from {args.patch}...")
    patches = {}
    with open(args.patch, "r") as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                patches[data["instance_id"]] = data
    print(f"Loaded {len(patches)} patches")
    
    # Create work directory
    os.makedirs(args.work_dir, exist_ok=True)
    
    # Evaluate
    results = []
    for instance_id, patch in patches.items():
        if args.instance_id and instance_id != args.instance_id:
            continue
        
        if instance_id not in instances:
            print(f"Warning: Instance {instance_id} not found in dataset")
            continue
        
        instance = instances[instance_id]
        result = evaluate_instance(instance, patch, args.work_dir)
        results.append(result)
        
        # Print result
        print(f"\nResult for {instance_id}:")
        print(f"  Clone: {'OK' if result['clone_success'] else 'FAIL'}")
        print(f"  Patch: {'OK' if result['patch_applies'] else 'FAIL'}")
        print(f"  Tests: {'OK' if result.get('tests_passed') else 'FAIL' if result.get('tests_run') else '-'}")
        if result.get("error"):
            print(f"  Error: {result['error']}")
    
    # Summary
    print(f"\n{'='*60}")
    print("Summary")
    print(f"{'='*60}")
    print(f"Total: {len(results)}")
    print(f"Clone success: {sum(1 for r in results if r['clone_success'])}")
    print(f"Patch applies: {sum(1 for r in results if r['patch_applies'])}")
    print(f"Tests passed: {sum(1 for r in results if r.get('tests_passed'))}")
    
    # Save results
    output_file = os.path.join(args.work_dir, "eval_results.jsonl")
    with open(output_file, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\nResults saved to: {output_file}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Multi-SWE-Bench Complete Evaluation Pipeline
=============================================

This script integrates the complete pipeline from Codex patch generation
to Multi-SWE-Bench official evaluation:

1. Download dataset from HuggingFace
2. Prepare workspace (clone repo, checkout to specified commit)
3. Call Codex CLI to generate patches
4. Convert patch format to official format
5. Run Multi-SWE-Bench official evaluation (Docker)
6. Generate evaluation report

Usage:
    python scripts/run_full_pipeline.py --instance-id cli__cli-10239 --language go
    python scripts/run_full_pipeline.py --dataset ./datasets/example_go.jsonl --language go
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MultiSWEBenchPipeline:
    """Multi-SWE-Bench Complete Evaluation Pipeline"""
    
    def __init__(
        self,
        output_dir: str = "./outputs",
        workspace_dir: str = "./workspace",
        data_dir: str = "./data",
        timeout: int = 1800,
        skip_codex: bool = False,
        skip_eval: bool = False,
    ):
        self.output_dir = Path(output_dir)
        self.workspace_dir = Path(workspace_dir)
        self.data_dir = Path(data_dir)
        self.timeout = timeout
        self.skip_codex = skip_codex
        self.skip_eval = skip_eval
        
        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def download_dataset(self, language: str, repo_filter: Optional[str] = None) -> Path:
        """Download dataset from HuggingFace"""
        logger.info(f"Downloading dataset for language: {language}")
        
        from huggingface_hub import hf_hub_download, list_repo_files
        
        # List dataset files
        files = list_repo_files("ByteDance-Seed/Multi-SWE-bench", repo_type="dataset")
        
        # Find files for the corresponding language
        lang_files = [f for f in files if f.startswith(f"{language}/")]
        
        if repo_filter:
            lang_files = [f for f in lang_files if repo_filter in f]
        
        if not lang_files:
            raise ValueError(f"No dataset files found for language: {language}")
        
        # Download files
        datasets_dir = Path("datasets") / language
        datasets_dir.mkdir(parents=True, exist_ok=True)
        
        for file_path in lang_files:
            local_path = hf_hub_download(
                repo_id="ByteDance-Seed/Multi-SWE-bench",
                filename=file_path,
                repo_type="dataset"
            )
            # Copy to local directory
            dest_path = datasets_dir / Path(file_path).name
            shutil.copy(local_path, dest_path)
            logger.info(f"Downloaded: {dest_path}")
        
        return datasets_dir
    
    def load_instance(self, dataset_path: Path, instance_id: str) -> Optional[Dict]:
        """Load a specific instance from the dataset"""
        logger.info(f"Loading instance {instance_id} from {dataset_path}")
        
        # If it's a directory, iterate over all jsonl files
        if dataset_path.is_dir():
            for jsonl_file in dataset_path.glob("*.jsonl"):
                with open(jsonl_file, 'r') as f:
                    for line in f:
                        item = json.loads(line)
                        if item.get('instance_id') == instance_id:
                            return item
        else:
            with open(dataset_path, 'r') as f:
                for line in f:
                    item = json.loads(line)
                    if item.get('instance_id') == instance_id:
                        return item
        
        return None
    
    def prepare_workspace(self, instance: Dict) -> Path:
        """Prepare workspace: clone repo and checkout to specified commit"""
        org = instance.get('org', '')
        repo = instance.get('repo', '')
        
        # Handle base_commit - compatible with old and new formats
        base = instance.get('base', instance.get('base_commit', 'HEAD'))
        if isinstance(base, dict):
            base_commit = base.get('sha', 'HEAD')
        else:
            base_commit = base
        
        instance_id = instance['instance_id']
        
        # Ensure repo includes org
        if org and '/' not in repo:
            repo = f"{org}/{repo}"
        
        workspace = self.workspace_dir / instance_id
        
        if workspace.exists():
            logger.info(f"Workspace already exists: {workspace}")
            # Reset to specified commit
            subprocess.run(
                ["git", "checkout", base_commit],
                cwd=workspace,
                capture_output=True
            )
            subprocess.run(
                ["git", "reset", "--hard", base_commit],
                cwd=workspace,
                capture_output=True
            )
            return workspace
        
        logger.info(f"Cloning {repo} to {workspace}")
        
        # Clone repository
        clone_url = f"https://github.com/{repo}.git"
        result = subprocess.run(
            ["git", "clone", "--depth", "100", clone_url, str(workspace)],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # Try full clone
            result = subprocess.run(
                ["git", "clone", clone_url, str(workspace)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to clone repository: {result.stderr}")
        
        # Fetch specified commit
        subprocess.run(
            ["git", "fetch", "origin", base_commit],
            cwd=workspace,
            capture_output=True
        )
        
        # Checkout to specified commit
        result = subprocess.run(
            ["git", "checkout", base_commit],
            cwd=workspace,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            logger.warning(f"Failed to checkout {base_commit}: {result.stderr}")
        
        return workspace
    
    def build_instruction(self, instance: Dict) -> str:
        """Build Codex instruction"""
        problem_statement = instance.get('body', instance.get('problem_statement', ''))
        title = instance.get('title', '')
        
        instruction = f"""I've uploaded a code repository in the current directory. Consider the following issue description:

<issue_description>
{title}

{problem_statement}
</issue_description>

Can you help me implement the necessary changes to the repository so that the requirements specified in the <issue_description> are met?

Your task is to make the minimal changes to non-test files in the workspace directory to ensure the <issue_description> is satisfied.

Follow these steps to resolve the issue:
1. First, explore the repo structure to understand the codebase.
2. Identify the files that need to be modified.
3. Make the minimal necessary changes to fix the issue.
4. Ensure your changes don't break existing functionality.

Your thinking should be thorough. Focus on making correct, minimal changes."""

        return instruction
    
    def run_codex(self, workspace: Path, instruction: str) -> Dict[str, Any]:
        """Run Codex CLI to generate patches"""
        logger.info(f"Running Codex CLI in {workspace}")
        
        result = {
            "success": False,
            "output": "",
            "error": None,
            "patch": "",
        }
        
        # Detect Codex command
        codex_cmd = self._detect_codex_command()
        if not codex_cmd:
            result["error"] = "Codex CLI not found. Please install: npm i -g @openai/codex"
            return result
        
        # Build command
        cmd = codex_cmd + ["exec", "--full-auto", "-C", str(workspace), instruction]
        
        logger.info(f"Command: {' '.join(cmd[:5])}... (instruction truncated)")
        
        try:
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=os.environ.copy()
            )
            
            result["output"] = process.stdout
            if process.stderr:
                result["output"] += f"\n\nStderr:\n{process.stderr}"
            
            if process.returncode == 0:
                result["success"] = True
                logger.info("Codex CLI completed successfully")
            else:
                result["error"] = f"Codex CLI exited with code {process.returncode}"
                logger.warning(result["error"])
            
            # Get git diff
            result["patch"] = self._get_patch(workspace)
            
        except subprocess.TimeoutExpired:
            result["error"] = f"Codex CLI timed out after {self.timeout} seconds"
            result["patch"] = self._get_patch(workspace)
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def _detect_codex_command(self) -> Optional[List[str]]:
        """Detect available Codex command"""
        # Try codex command
        try:
            result = subprocess.run(["codex", "--help"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return ["codex"]
        except:
            pass
        
        # Try openai codex
        try:
            result = subprocess.run(["openai", "codex", "--help"], capture_output=True, timeout=5)
            if result.returncode == 0:
                return ["openai", "codex"]
        except:
            pass
        
        return None
    
    def _get_patch(self, workspace: Path) -> str:
        """Get git diff"""
        try:
            result = subprocess.run(
                ["git", "diff", "HEAD"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=30
            )
            return result.stdout if result.returncode == 0 else ""
        except:
            return ""
    
    def convert_to_official_format(self, instance: Dict, patch: str) -> Dict:
        """Convert to Multi-SWE-Bench official format"""
        return {
            "org": instance['org'],
            "repo": instance['repo'],
            "number": instance['number'],
            "fix_patch": patch
        }
    
    def save_results(
        self,
        instance: Dict,
        codex_result: Dict,
        output_subdir: str
    ) -> Dict[str, Path]:
        """Save results"""
        output_path = self.output_dir / output_subdir
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save Codex raw output
        codex_output_path = output_path / "output.jsonl"
        with open(codex_output_path, 'w') as f:
            output_data = {
                "instance_id": instance['instance_id'],
                "success": codex_result['success'],
                "patch": codex_result['patch'],
                "error": codex_result.get('error'),
                "codex_output": codex_result.get('output', '')[:5000]  # Truncate
            }
            f.write(json.dumps(output_data) + '\n')
        
        # Save official format patch
        official_patch_path = output_path / "official_patch.jsonl"
        official_format = self.convert_to_official_format(instance, codex_result['patch'])
        with open(official_patch_path, 'w') as f:
            f.write(json.dumps(official_format) + '\n')
        
        # Save dataset copy
        dataset_path = output_path / "dataset.jsonl"
        with open(dataset_path, 'w') as f:
            f.write(json.dumps(instance) + '\n')
        
        logger.info(f"Results saved to {output_path}")
        
        return {
            "codex_output": codex_output_path,
            "official_patch": official_patch_path,
            "dataset": dataset_path
        }
    
    def run_official_evaluation(
        self,
        patch_file: Path,
        dataset_file: Path,
        output_subdir: str
    ) -> Dict:
        """Run Multi-SWE-Bench official evaluation"""
        logger.info("Running Multi-SWE-Bench official evaluation...")
        
        # Create evaluation config
        eval_config = {
            "mode": "evaluation",
            "workdir": str(self.data_dir / "workdir"),
            "patch_files": [str(patch_file.absolute())],
            "dataset_files": [str(dataset_file.absolute())],
            "force_build": False,
            "output_dir": str(self.data_dir / "results" / output_subdir),
            "specifics": [],
            "skips": [],
            "repo_dir": str(self.data_dir / "repos"),
            "need_clone": True,
            "global_env": [],
            "clear_env": True,
            "stop_on_error": False,
            "max_workers": 1,
            "max_workers_build_image": 1,
            "max_workers_run_instance": 1,
            "log_dir": str(self.data_dir / "logs" / output_subdir),
            "log_level": "INFO"
        }
        
        config_path = self.data_dir / f"eval_config_{output_subdir}.json"
        with open(config_path, 'w') as f:
            json.dump(eval_config, f, indent=2)
        
        # Run evaluation
        try:
            result = subprocess.run(
                [
                    sys.executable, "-m",
                    "multi_swe_bench.harness.run_evaluation",
                    "--config", str(config_path)
                ],
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                logger.info("Evaluation completed successfully")
                
                # Read results
                result_path = Path(eval_config["output_dir"]) / "final_report.json"
                if result_path.exists():
                    with open(result_path) as f:
                        return json.load(f)
            else:
                logger.error(f"Evaluation failed: {result.stderr}")
                return {"error": result.stderr}
                
        except subprocess.TimeoutExpired:
            logger.error("Evaluation timed out")
            return {"error": "Evaluation timed out"}
        except Exception as e:
            logger.error(f"Evaluation error: {e}")
            return {"error": str(e)}
        
        return {}
    
    def run(
        self,
        instance_id: str,
        language: str,
        dataset_path: Optional[Path] = None
    ) -> Dict:
        """Run the complete pipeline"""
        logger.info(f"=" * 60)
        logger.info(f"Running Multi-SWE-Bench Pipeline for {instance_id}")
        logger.info(f"=" * 60)
        
        results = {
            "instance_id": instance_id,
            "language": language,
            "success": False,
            "steps": {}
        }
        
        try:
            # Step 1: Load dataset
            if dataset_path is None:
                dataset_path = self.download_dataset(language)
            
            instance = self.load_instance(Path(dataset_path), instance_id)
            if instance is None:
                raise ValueError(f"Instance {instance_id} not found in dataset")
            
            results["steps"]["load_dataset"] = "success"
            logger.info(f"Loaded instance: {instance_id}")
            
            # Step 2: Prepare workspace
            workspace = self.prepare_workspace(instance)
            results["steps"]["prepare_workspace"] = str(workspace)
            
            # Step 3: Run Codex
            output_subdir = f"{language}/{instance_id}"
            
            if self.skip_codex:
                # Try to load existing results
                existing_output = self.output_dir / output_subdir / "output.jsonl"
                if existing_output.exists():
                    with open(existing_output) as f:
                        codex_result = json.loads(f.readline())
                    logger.info("Using existing Codex output")
                else:
                    raise ValueError("No existing Codex output found and --skip-codex is set")
            else:
                instruction = self.build_instruction(instance)
                codex_result = self.run_codex(workspace, instruction)
            
            results["steps"]["run_codex"] = {
                "success": codex_result.get('success', False),
                "patch_length": len(codex_result.get('patch', ''))
            }
            
            if not codex_result.get('patch'):
                logger.warning("No patch generated")
                results["error"] = "No patch generated"
                return results
            
            # Step 4: Save results
            saved_files = self.save_results(instance, codex_result, output_subdir)
            results["steps"]["save_results"] = {k: str(v) for k, v in saved_files.items()}
            
            # Step 5: Run official evaluation
            if not self.skip_eval:
                eval_result = self.run_official_evaluation(
                    saved_files["official_patch"],
                    saved_files["dataset"],
                    output_subdir
                )
                results["steps"]["evaluation"] = eval_result
                results["success"] = eval_result.get("resolved_instances", 0) > 0
            else:
                results["success"] = codex_result.get('success', False)
            
            logger.info(f"Pipeline completed. Success: {results['success']}")
            
        except Exception as e:
            logger.error(f"Pipeline error: {e}")
            results["error"] = str(e)
        
        return results


def main():
    parser = argparse.ArgumentParser(
        description="Multi-SWE-Bench Complete Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single instance
  python scripts/run_full_pipeline.py --instance-id cli__cli-10239 --language go
  
  # Use a local dataset
  python scripts/run_full_pipeline.py --instance-id cli__cli-10239 --dataset ./datasets/example_go.jsonl
  
  # Skip Codex (use existing patch)
  python scripts/run_full_pipeline.py --instance-id cli__cli-10239 --language go --skip-codex
  
  # Only generate patch, skip evaluation
  python scripts/run_full_pipeline.py --instance-id cli__cli-10239 --language go --skip-eval
"""
    )
    
    parser.add_argument(
        "--instance-id",
        required=True,
        help="Instance ID (e.g., cli__cli-10239)"
    )
    parser.add_argument(
        "--language",
        default="go",
        help="Programming language (go, java, js, ts, rust, c, cpp)"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        help="Path to local dataset file or directory"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("./outputs"),
        help="Output directory"
    )
    parser.add_argument(
        "--workspace-dir",
        type=Path,
        default=Path("./workspace"),
        help="Workspace directory for cloned repos"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="Codex timeout in seconds"
    )
    parser.add_argument(
        "--skip-codex",
        action="store_true",
        help="Skip Codex and use existing patch"
    )
    parser.add_argument(
        "--skip-eval",
        action="store_true",
        help="Skip official evaluation"
    )
    
    args = parser.parse_args()
    
    pipeline = MultiSWEBenchPipeline(
        output_dir=str(args.output_dir),
        workspace_dir=str(args.workspace_dir),
        timeout=args.timeout,
        skip_codex=args.skip_codex,
        skip_eval=args.skip_eval
    )
    
    results = pipeline.run(
        instance_id=args.instance_id,
        language=args.language,
        dataset_path=args.dataset
    )
    
    # Print results
    print("\n" + "=" * 60)
    print("PIPELINE RESULTS")
    print("=" * 60)
    print(json.dumps(results, indent=2))
    
    # Return status code
    sys.exit(0 if results.get("success") else 1)


if __name__ == "__main__":
    main()

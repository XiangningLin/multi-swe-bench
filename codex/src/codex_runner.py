"""
Codex CLI Runner Module
Reference: https://uibakery.io/blog/how-to-use-codex
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CodexRunner:
    """Codex CLI Runner"""

    def __init__(
        self,
        timeout: int = 1800,
        auto_approve: bool = True,
        model: str = "gpt-5-nano",

    ):
        """
        Initialize the Codex Runner

        Args:
            timeout: Timeout in seconds
            auto_approve: Whether to auto-approve edits
            model: Model name (o4-mini, o3-mini, gpt-4o, gpt-4.1, etc.)
        """
        self.timeout = timeout
        self.auto_approve = auto_approve
        self.model = model

    def check_codex_installed(self) -> bool:
        """
        Check if Codex CLI is installed

        Returns:
            bool: Whether Codex CLI is installed
        """
        try:
            # Try the codex command
            result = subprocess.run(
                ["codex", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"Codex CLI version: {result.stdout.strip()}")
                return True
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"codex command check failed: {e}")

        # Try the openai codex command
        try:
            result = subprocess.run(
                ["openai", "codex", "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                logger.info(f"OpenAI Codex CLI version: {result.stdout.strip()}")
                return True
            else:
                logger.warning(f"Codex CLI check failed: {result.stderr}")
                return False
        except FileNotFoundError:
            logger.error("Codex CLI not found. Please install it with: npm i -g @openai/codex")
            return False
        except Exception as e:
            logger.error(f"Error checking Codex CLI: {e}")
            return False

    def run(
        self,
        workspace_dir: str,
        instruction: str,
        base_commit: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run Codex in the specified working directory

        Args:
            workspace_dir: Working directory path
            instruction: Instruction/task description

        Returns:
            dict: Dictionary containing execution results
                - success: bool, whether execution succeeded
                - output: str, Codex output
                - error: str | None, error message
                - patch: str, generated patch
        """
        result = {
            "success": False,
            "output": "",
            "error": None,
            "patch": "",
        }

        # Check working directory
        if not os.path.exists(workspace_dir):
            result["error"] = f"Workspace directory does not exist: {workspace_dir}"
            return result

        # Write instruction to a temporary file
        instruction_file = os.path.join(workspace_dir, ".codex_instruction.txt")
        with open(instruction_file, "w") as f:
            f.write(instruction)

        try:
            # Build Codex CLI command
            # Use exec subcommand for non-interactive execution
            cmd = self._build_command(workspace_dir, instruction)

            logger.info(f"Running Codex CLI in {workspace_dir}")
            logger.info(f"Command: {' '.join(cmd[:5])}... (prompt truncated)")
            logger.debug(f"Full command: {' '.join(cmd)}")

            # Execute command (no need to specify cwd since -C parameter is used)
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=self._get_env(),
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

            # Get the generated patch
            result["patch"] = self._get_patch(workspace_dir, base_commit)

        except subprocess.TimeoutExpired:
            result["error"] = f"Codex CLI timed out after {self.timeout} seconds"
            logger.error(result["error"])
            # Try to get patch even on timeout
            result["patch"] = self._get_patch(workspace_dir, base_commit)

        except Exception as e:
            result["error"] = f"Error running Codex CLI: {str(e)}"
            logger.error(result["error"])

        finally:
            # Clean up temporary file
            if os.path.exists(instruction_file):
                os.remove(instruction_file)

        return result

    def _build_command(self, workspace_dir: str, instruction: str) -> List[str]:
        """
        Build the Codex CLI command
        Aligned with harbor/src/harbor/agents/installed/codex.py

        Args:
            workspace_dir: Working directory
            instruction: Instruction

        Returns:
            list[str]: Command list
        """
        # Codex CLI command
        # Use exec subcommand for non-interactive execution
        # Aligned with harbor: use --dangerously-bypass-approvals-and-sandbox and --skip-git-repo-check
        # Reference: harbor/src/harbor/agents/installed/codex.py
        
        # First detect the available command
        codex_cmd = self._detect_codex_command()
        
        cmd = codex_cmd.copy()
        
        # Use exec subcommand for non-interactive execution
        cmd.append("exec")
        
        # Add options - aligned with harbor
        if self.auto_approve:
            # Use the same options as harbor
            # --dangerously-bypass-approvals-and-sandbox: bypass approvals and sandbox (equivalent to --full-auto)
            cmd.append("--dangerously-bypass-approvals-and-sandbox")
            # --skip-git-repo-check: skip git repository check
            cmd.append("--skip-git-repo-check")
        
        # Specify model
        if self.model:
            cmd.extend(["--model", self.model])
        
        # Set working directory (needed for codex-agent since it runs locally)
        # Note: harbor runs inside a Docker container and doesn't need the -C parameter
        cmd.extend(["-C", workspace_dir])
        
        # Add --json option for JSON output (aligned with harbor)
        cmd.append("--json")
        
        # Use -- separator to clearly separate options from arguments (aligned with harbor)
        cmd.append("--")
        
        # Add instruction as prompt (after --)
        cmd.append(instruction)

        return cmd
    
    def _detect_codex_command(self) -> List[str]:
        """
        Detect the available Codex command

        Returns:
            List[str]: Command prefix list
        """
        # Try the codex command
        try:
            result = subprocess.run(
                ["codex", "--help"],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0:
                return ["codex"]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Default to openai codex
        return ["openai", "codex"]

    def _get_env(self) -> Dict[str, str]:
        """
        Get execution environment variables

        Returns:
            dict: Environment variables
        """
        env = os.environ.copy()
        # Ensure OPENAI_API_KEY exists
        if "OPENAI_API_KEY" not in env:
            logger.warning("OPENAI_API_KEY not set in environment")
        return env

    def _get_patch(self, workspace_dir: str, base_commit: Optional[str] = None) -> str:
        """
        Get code changes from the working directory (git diff)

        Args:
            workspace_dir: Working directory
            base_commit: Base commit; if provided, diff against this commit; otherwise diff against HEAD

        Returns:
            str: git diff output
        """
        try:
            # If base_commit is provided, diff between base_commit and current HEAD
            # Otherwise, diff between HEAD and working directory (uncommitted changes)
            if base_commit:
                # Diff between base_commit and current HEAD (includes all committed changes)
                diff_target = base_commit
            else:
                # Diff between HEAD and working directory (uncommitted changes)
                diff_target = "HEAD"
            
            # Get all changes (including unstaged)
            # Note: don't use text=True, manually decode to handle binary content
            result = subprocess.run(
                ["git", "diff", diff_target],
                cwd=workspace_dir,
                capture_output=True,
                timeout=30,
            )

            if result.returncode == 0:
                # Use errors='replace' to handle bytes that can't be decoded (e.g., binary files)
                patch = result.stdout.decode('utf-8', errors='replace')
                
                # Validate patch content (check for changes outside the workspace)
                if patch and self._validate_patch(patch, workspace_dir):
                    return patch
                elif patch:
                    logger.warning(f"Patch validation failed - may contain changes outside workspace")
                    # Try to filter and keep only target repo changes
                    return self._filter_patch(patch, workspace_dir)
                return patch
            else:
                stderr = result.stderr.decode('utf-8', errors='replace')
                logger.warning(f"git diff failed: {stderr}")
                return ""

        except Exception as e:
            logger.error(f"Error getting git diff: {e}")
            return ""
    
    def _validate_patch(self, patch: str, workspace_dir: str) -> bool:
        """
        Validate that the patch only contains changes from the target repository
        
        Args:
            patch: Patch content
            workspace_dir: Working directory
            
        Returns:
            bool: Whether the patch is valid
        """
        if not patch:
            return True
            
        # Check if patch file paths contain directories that shouldn't appear
        suspicious_patterns = [
            'codex-multi-swe-bench/',
            'workspace/',
            '../',
        ]
        
        for pattern in suspicious_patterns:
            if pattern in patch:
                logger.warning(f"Patch contains suspicious path: {pattern}")
                return False
        
        return True
    
    def _filter_patch(self, patch: str, workspace_dir: str) -> str:
        """
        Filter patch to keep only changes from the target repository
        
        Args:
            patch: Original patch content
            workspace_dir: Working directory
            
        Returns:
            str: Filtered patch
        """
        # Simple implementation: if patch contains suspicious paths, return empty
        # A more complex implementation could parse the diff and keep only legitimate files
        if 'codex-multi-swe-bench/' in patch:
            logger.error("Patch contains changes to codex-multi-swe-bench project itself - discarding")
            return ""
        return patch


class CodexRunnerMock(CodexRunner):
    """
    Codex CLI Mock Runner (for testing)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.mock_responses: List[dict] = []
        self.call_count = 0

    def set_mock_response(self, responses: List[dict]) -> None:
        """Set mock responses"""
        self.mock_responses = responses

    def run(self, workspace_dir: str, instruction: str) -> dict[str, Any]:
        """Mock run"""
        if self.call_count < len(self.mock_responses):
            response = self.mock_responses[self.call_count]
        else:
            response = {
                "success": True,
                "output": "Mock output",
                "error": None,
                "patch": "# Mock patch\n",
            }
        self.call_count += 1
        return response

    def check_codex_installed(self) -> bool:
        """Mock check"""
        return True

#!/usr/bin/env python3
"""
Run tasks with missing patches
Automatically detect which tasks are missing patches and only run those
"""

import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path

# Model
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gpt-5-mini"

# Task and language mapping
TASKS = {
    "go": [
        "cli__cli-5595", "cli__cli-10239", "cli__cli-7626", "cli__cli-4146",
        "cli__cli-7440", "cli__cli-885", "cli__cli-10139", "cli__cli-668",
        "cli__cli-3827", "cli__cli-5597", "cli__cli-4534", "cli__cli-3270",
        "cli__cli-2251", "cli__cli-8030", "cli__cli-8934", "cli__cli-4845",
        "cli__cli-3519", "cli__cli-10154", "cli__cli-10043", "grpc__grpc-go-2629"
    ],
    "java": [
        "fasterxml__jackson-core-370", "fasterxml__jackson-core-1182",
        "fasterxml__jackson-databind-4228", "fasterxml__jackson-databind-4311",
        "fasterxml__jackson-core-964", "fasterxml__jackson-core-566",
        "fasterxml__jackson-databind-4360", "fasterxml__jackson-databind-4365",
        "fasterxml__jackson-databind-4487", "fasterxml__jackson-core-729",
        "fasterxml__jackson-databind-4013", "fasterxml__jackson-databind-3509",
        "fasterxml__jackson-dataformat-xml-644", "mockito__mockito-3220",
        "mockito__mockito-3424", "mockito__mockito-3167", "alibaba__fastjson2-2775",
        "googlecontainertools__jib-4144", "google__gson-1391", "fasterxml__jackson-core-1208"
    ],
    "rust": [
        "clap-rs__clap-3453", "clap-rs__clap-2058", "clap-rs__clap-2168",
        "clap-rs__clap-3975", "clap-rs__clap-1869", "clap-rs__clap-2309",
        "clap-rs__clap-3455", "clap-rs__clap-3225", "clap-rs__clap-1958",
        "clap-rs__clap-3972", "clap-rs__clap-2611", "nushell__nushell-11493",
        "nushell__nushell-11292", "nushell__nushell-10613", "tokio-rs__tokio-5781",
        "tokio-rs__tracing-1045", "tokio-rs__tracing-1853", "sharkdp__fd-555",
        "sharkdp__fd-497", "rayon-rs__rayon-863"
    ],
    "typescript": [
        "mui__material-ui-34207", "mui__material-ui-39688", "mui__material-ui-26186",
        "mui__material-ui-36400", "mui__material-ui-30788", "mui__material-ui-39196",
        "mui__material-ui-29317", "mui__material-ui-34437", "mui__material-ui-37855",
        "mui__material-ui-32401", "mui__material-ui-38788", "mui__material-ui-23778",
        "mui__material-ui-26170", "vuejs__core-10004", "vuejs__core-10027",
        "vuejs__core-9507", "vuejs__core-11165", "vuejs__core-11694",
        "vuejs__core-8402", "darkreader__darkreader-6747"
    ]
}

OUTPUT_DIRS = {
    "go": f"outputs/go20_{MODEL}_3times",
    "java": f"outputs/java20_{MODEL}_3times",
    "rust": f"outputs/rust20_{MODEL}_3times",
    "typescript": f"outputs/ts20_{MODEL}_3times"
}

# Actual directory names (may differ)
ACTUAL_DIRS = {
    "go": f"outputs/go20_{MODEL}_3times",
    "java": f"outputs/java20_{MODEL}_3times",
    "rust": f"outputs/rust20_{MODEL}_3times",
    "typescript": f"outputs/ts20_{MODEL}_3times"
}

def check_missing_patches():
    """Check for missing patches"""
    missing_tasks = []
    
    for lang, tasks in TASKS.items():
        output_dir = OUTPUT_DIRS[lang]
        
        # Check if directory exists
        if not os.path.exists(output_dir):
            # If directory doesn't exist, all tasks need to run
            for task in tasks:
                for run_num in [1, 2, 3]:
                    missing_tasks.append((task, lang, run_num))
            continue
        
        for task in tasks:
            for run_num in [1, 2, 3]:
                patch_file = f"{output_dir}/{task}_run{run_num}/patches/{task}.patch"
                if not os.path.exists(patch_file):
                    missing_tasks.append((task, lang, run_num))
    
    return missing_tasks

def run_task(task, lang, run_num):
    """Run a single task"""
    output_dir = OUTPUT_DIRS[lang]
    run_output_dir = f"{output_dir}/{task}_run{run_num}"
    os.makedirs(run_output_dir, exist_ok=True)
    
    cmd = [
        sys.executable, "run_single_task.py",
        "--instance-id", task,
        "--language", lang,
        "--output-dir", run_output_dir
    ]
    
    env = os.environ.copy()
    env["CODEX_MODEL"] = MODEL
    
    # Get API key
    try:
        with open(os.path.expanduser("~/.zshrc"), "r") as f:
            for line in f:
                if line.startswith("export OPENAI_API_KEY="):
                    api_key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    env["OPENAI_API_KEY"] = api_key
                    break
    except:
        pass
    
    result = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return result.returncode == 0

def main():
    print("=== Running tasks with missing patches ===")
    print(f"Model: {MODEL}")
    print("")
    
    # Check for missing patches
    print("=== Checking for missing patches ===")
    missing_tasks = check_missing_patches()
    
    if not missing_tasks:
        print("All patches are complete, nothing to run")
        return 0
    
    print(f"Found {len(missing_tasks)} missing patches")
    print("")
    
    # Create log file
    log_file = f"outputs/missing_patches_{MODEL}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    
    print(f"Log file: {log_file}")
    print("")
    
    success_count = 0
    fail_count = 0
    
    # Run missing tasks
    for idx, (task, lang, run_num) in enumerate(missing_tasks, 1):
        print("=" * 50)
        print(f"[{idx}/{len(missing_tasks)}] Running: {task} (language: {lang}, run #{run_num})")
        print("=" * 50)
        
        try:
            if run_task(task, lang, run_num):
                print(f"Completed: {task} (run #{run_num})")
                success_count += 1
            else:
                print(f"Failed: {task} (run #{run_num})")
                fail_count += 1
        except Exception as e:
            print(f"Error: {task} (run #{run_num}) - {e}")
            fail_count += 1
        
        print("---")
    
    print("")
    print("=== Complete ===")
    print(f"Total missing tasks: {len(missing_tasks)}")
    print(f"Succeeded: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Log file: {log_file}")
    
    return 0 if fail_count == 0 else 1

if __name__ == "__main__":
    sys.exit(main())

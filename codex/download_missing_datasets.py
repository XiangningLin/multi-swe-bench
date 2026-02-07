#!/usr/bin/env python3
"""
Download Missing Dataset Tasks

Download Multi-SWE-Bench datasets from HuggingFace and extract missing tasks.
Uses huggingface_hub to download files directly, avoiding type conversion issues
with the datasets library.
"""

import json
import os
import sys
from pathlib import Path

try:
    from huggingface_hub import hf_hub_download, list_repo_files
except ImportError:
    print("huggingface_hub is required: pip install huggingface_hub")
    sys.exit(1)

# HuggingFace dataset name
HUGGINGFACE_DATASET = "ByteDance-Seed/Multi-SWE-bench"

# Tasks to download
MISSING_TASKS = {
    "go": ["grpc__grpc-go-2629"],
    "java": [
        "alibaba__fastjson2-2775",
        "mockito__mockito-3220",
        "mockito__mockito-3424",
        "mockito__mockito-3167",
        "googlecontainertools__jib-4144",
        "google__gson-1391",
        "fasterxml__jackson-dataformat-xml-644"
    ],
    "rust": [
        "nushell__nushell-11493",
        "nushell__nushell-11292",
        "nushell__nushell-10613",
        "tokio-rs__tokio-5781",
        "tokio-rs__tracing-1045",
        "tokio-rs__tracing-1853",
        "sharkdp__fd-555",
        "sharkdp__fd-497",
        "rayon-rs__rayon-863"
    ],
    "typescript": [
        "vuejs__core-10004",
        "vuejs__core-10027",
        "vuejs__core-9507",
        "vuejs__core-11165",
        "vuejs__core-11694",
        "vuejs__core-8402",
        "darkreader__darkreader-6747"
    ]
}

def download_dataset_for_language(language: str, output_dir: str = "datasets"):
    """Download dataset for the specified language from HuggingFace"""
    print(f"\n{'='*80}")
    print(f"Downloading {language.upper()} language dataset")
    print(f"{'='*80}")
    
    try:
        # Language mapping (directory names in HuggingFace)
        lang_mapping = {
            "go": "go",
            "java": "java",
            "rust": "rust",
            "typescript": "ts",  # TypeScript is "ts" in HuggingFace
            "ts": "ts"
        }
        
        hf_lang = lang_mapping.get(language.lower(), language.lower())
        
        # List files in the HuggingFace repository
        print(f"Listing HuggingFace repository files...")
        files = list_repo_files(HUGGINGFACE_DATASET, repo_type="dataset")
        
        # Find JSONL files for the corresponding language (check directory prefix)
        lang_files = [f for f in files if f.endswith('.jsonl') and f.startswith(f"{hf_lang}/")]
        
        if not lang_files:
            print(f"WARNING: No JSONL files found for {language}")
            print(f"Available files: {[f for f in files if f.endswith('.jsonl')][:10]}")
            return False
        
        print(f"Found {len(lang_files)} dataset files for {language}")
        
        # Download all related files and merge
        all_instances = {}
        for file_path in lang_files:
            print(f"Downloading: {file_path}")
            local_path = hf_hub_download(
                repo_id=HUGGINGFACE_DATASET,
                filename=file_path,
                repo_type="dataset"
            )
            
            # Read JSONL file
            with open(local_path, 'r') as f:
                for line in f:
                    if line.strip():
                        instance = json.loads(line)
                        instance_id = instance.get('instance_id', '')
                        if instance_id:
                            all_instances[instance_id] = instance
        
        print(f"Loaded {len(all_instances)} instances total")
        
        # Filter missing tasks
        missing_task_ids = MISSING_TASKS.get(language, [])
        if language == "typescript":
            missing_task_ids = MISSING_TASKS.get("typescript", [])
        
        found_instances = []
        for task_id in missing_task_ids:
            if task_id in all_instances:
                found_instances.append(all_instances[task_id])
            else:
                print(f"  WARNING: Not found: {task_id}")
        
        if not found_instances:
            print(f"WARNING: No missing tasks found")
            return False
        
        # Save to file
        os.makedirs(output_dir, exist_ok=True)
        lang_subdir = os.path.join(output_dir, language)
        os.makedirs(lang_subdir, exist_ok=True)
        output_file = os.path.join(lang_subdir, f"{language}_missing_tasks.jsonl")
        
        with open(output_file, 'w') as f:
            for instance in found_instances:
                f.write(json.dumps(instance) + '\n')
        
        print(f"Found {len(found_instances)} missing tasks")
        print(f"Saved to: {output_file}")
        
        # Display found tasks
        found_ids = [inst.get('instance_id') for inst in found_instances]
        print(f"\nFound tasks:")
        for task_id in found_ids:
            print(f"  - {task_id}")
        
        return True
        
    except Exception as e:
        print(f"Download failed: {e}")
        import traceback
        traceback.print_exc()
        print(f"\nHint: If download fails, you can manually download the dataset files")
        print(f"  https://huggingface.co/datasets/{HUGGINGFACE_DATASET}")
        return False

def download_all_missing_tasks():
    """Download all missing tasks"""
    print("="*80)
    print("Downloading Missing Dataset Tasks")
    print("="*80)
    
    results = {}
    for language in ["go", "java", "rust", "typescript"]:
        if language in MISSING_TASKS and MISSING_TASKS[language]:
            success = download_dataset_for_language(language)
            results[language] = success
    
    print("\n" + "="*80)
    print("Download Results Summary")
    print("="*80)
    for language, success in results.items():
        status = "Success" if success else "Failed"
        print(f"{language}: {status}")
    
    return all(results.values())

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Download for specified language
        language = sys.argv[1]
        download_dataset_for_language(language)
    else:
        # Download all missing tasks
        success = download_all_missing_tasks()
        sys.exit(0 if success else 1)

#!/usr/bin/env python3
"""
Convert output.jsonl files in new_outputs to the patches.jsonl format required for evaluation
"""

import json
import os
import re
from pathlib import Path


def clean_patch(patch: str) -> str:
    """
    Clean patch content by removing non-diff format text
    
    The model may append "Phase 7. VERIFICATION" or similar explanation text
    at the end of the patch, which needs to be removed to ensure the patch
    can be applied correctly.
    """
    if not patch:
        return patch
    
    lines = patch.split('\n')
    clean_lines = []
    
    for line in lines:
        # Detect non-diff format lines
        # Valid diff format lines typically start with:
        # - diff, ---, +++, @@, +, -, space, or are empty lines
        stripped = line.strip()
        
        # If we encounter "Phase X." or similar non-diff content, stop
        if stripped.startswith('Phase ') and '. ' in stripped:
            break
        
        # If we encounter "Note:" or "VERIFICATION" keywords, stop
        if stripped.startswith('Note:') or stripped == 'VERIFICATION' or stripped == 'FINAL REVIEW':
            break
        
        # Check if this is a valid diff line
        if line.startswith('diff ') or line.startswith('---') or line.startswith('+++') or \
           line.startswith('@@') or line.startswith('+') or line.startswith('-') or \
           line.startswith(' ') or line == '' or line.startswith('index ') or \
           line.startswith('new file') or line.startswith('deleted file') or \
           line.startswith('Binary files') or line.startswith('rename from') or \
           line.startswith('rename to') or line.startswith('similarity index') or \
           line.startswith('copy from') or line.startswith('copy to'):
            clean_lines.append(line)
        else:
            # Non-diff format line, possibly model-added explanation
            # If we already have diff content, stop at non-diff line
            if clean_lines and any(l.startswith('diff ') for l in clean_lines):
                break
            # Otherwise skip this line (may be introductory text)
            continue
    
    # Remove trailing empty lines
    while clean_lines and clean_lines[-1] == '':
        clean_lines.pop()
    
    return '\n'.join(clean_lines)


def parse_instance_id(instance_id: str) -> dict:
    """
    Parse instance_id to extract org, repo, number
    
    Examples:
        cli__cli-10043 -> {"org": "cli", "repo": "cli", "number": "10043"}
        fasterxml__jackson-core-1182 -> {"org": "fasterxml", "repo": "jackson-core", "number": "1182"}
        clap-rs__clap-1869 -> {"org": "clap-rs", "repo": "clap", "number": "1869"}
        vuejs__core-10289 -> {"org": "vuejs", "repo": "core", "number": "10289"}
        mui__material-ui-39688 -> {"org": "mui", "repo": "material-ui", "number": "39688"}
    """
    # Split by __ to get org and repo-number
    parts = instance_id.split("__")
    if len(parts) != 2:
        raise ValueError(f"Invalid instance_id format: {instance_id}")
    
    org = parts[0]
    repo_and_number = parts[1]
    
    # Find the last occurrence of - followed by digits to split repo and number
    match = re.match(r"(.+)-(\d+)$", repo_and_number)
    if not match:
        raise ValueError(f"Cannot parse repo and number from: {repo_and_number}")
    
    repo = match.group(1)
    number = match.group(2)
    
    return {"org": org, "repo": repo, "number": number}


def convert_output_to_patches(input_file: str, output_file: str, model_name: str):
    """
    Convert output.jsonl to patches.jsonl format
    """
    patches = []
    
    with open(input_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            
            data = json.loads(line)
            instance_id = data.get("instance_id", "")
            raw_patch = data.get("patch", "")
            raw_model_patch = data.get("model_patch", raw_patch)
            
            # Clean patch content
            patch = clean_patch(raw_patch)
            model_patch = clean_patch(raw_model_patch)
            
            # Skip records without patches
            if not patch:
                print(f"  Skipping {instance_id}: no patch")
                continue
            
            try:
                parsed = parse_instance_id(instance_id)
            except ValueError as e:
                print(f"  Error parsing {instance_id}: {e}")
                continue
            
            patch_entry = {
                "org": parsed["org"],
                "repo": parsed["repo"],
                "number": parsed["number"],
                "instance_id": instance_id,
                "model_name_or_path": model_name,
                "fix_patch": patch,
                "model_patch": model_patch
            }
            patches.append(patch_entry)
    
    # Write output file
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, 'w') as f:
        for patch in patches:
            f.write(json.dumps(patch) + '\n')
    
    print(f"  Converted {len(patches)} patches -> {output_file}")
    return len(patches)


def main():
    base_dir = Path(__file__).resolve().parent
    new_outputs_dir = base_dir / "new_outputs"
    eval_outputs_dir = base_dir / "eval_outputs"
    
    # Iterate over all models and languages
    total_converted = 0
    
    for model_dir in sorted(new_outputs_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        
        model_name = model_dir.name
        print(f"\n=== Model: {model_name} ===")
        
        for lang_dir in sorted(model_dir.iterdir()):
            if not lang_dir.is_dir():
                continue
            
            lang = lang_dir.name
            input_file = lang_dir / "output.jsonl"
            
            if not input_file.exists():
                print(f"  {lang}: No output.jsonl found")
                continue
            
            output_dir = eval_outputs_dir / model_name / lang
            output_file = output_dir / "patches.jsonl"
            
            print(f"  Processing {lang}...")
            count = convert_output_to_patches(str(input_file), str(output_file), model_name)
            total_converted += count
    
    print(f"\n=== Total: {total_converted} patches converted ===")
    print(f"\nOutput directory: {eval_outputs_dir}")


if __name__ == "__main__":
    main()

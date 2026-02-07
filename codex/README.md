# Codex Multi-SWE-Bench

Run Multi-SWE-Bench evaluation using OpenAI Codex CLI, integrated with the official Multi-SWE-Bench harness for validation.

## 📋 Complete Evaluation Pipeline

```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  Multi-SWE-Bench │ ───► │   Codex CLI     │ ───► │  Multi-SWE-Bench │
│     Dataset      │      │  Generate Patch │      │  Official Harness│
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                        │                        │
        ▼                        ▼                        ▼
   instance_id            output.jsonl            Evaluation Results
   Problem Description     git diff patch         Resolved Rate
```

## 🧠 How Codex CLI Works

Codex CLI is OpenAI's AI coding assistant that understands code repositories and automatically fixes issues.

### Core Workflow

```
┌────────────────────────────────────────────────────────────────────┐
│                  How Codex CLI Generates Patches                    │
├────────────────────────────────────────────────────────────────────┤
│                                                                    │
│  Input:                                                            │
│    • workspace_dir: Cloned repo directory (checked out to          │
│      base_commit)                                                  │
│    • instruction: Problem description (issue title + body)         │
│                                                                    │
│  Command:                                                          │
│    codex exec --full-auto -C <workspace_dir> "<instruction>"       │
│                                                                    │
│  Internal Process:                                                 │
│    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐          │
│    │ 1. Analyze   │ -> │ 2. Understand│ -> │ 3. Generate  │          │
│    │    Repo      │    │    Issue     │    │    Changes   │          │
│    └─────────────┘    └─────────────┘    └─────────────┘          │
│          │                  │                  │                   │
│          ▼                  ▼                  ▼                   │
│    • Browse file        • Analyze issue    • Edit files directly  │
│      structure          • Locate problem   • Auto-save changes    │
│    • Read source code     code                                    │
│    • Search related     • Design fix                              │
│      code                 strategy                                │
│                                                                    │
│  Output:                                                           │
│    git diff HEAD  ->  Unified diff of all code changes             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

### Practical Example

Using `cli__cli-10239` as an example, the Codex output log shows:

```
workdir: /workspace/cli__cli-10239
model: gpt-5-nano
approval: never (--full-auto mode)
sandbox: workspace-write

Operations automatically performed by Codex:
1. Explore repository structure with ls, cat, etc.
2. Read pkg/cmd/root/extension.go to understand the code
3. Identify blocking channel read issue in PostRun
4. Modify code: use buffered channel + select/default pattern
5. Save file

Final git diff outputs the fix patch (2229 chars)
```

## 🚀 Quick Start

### One-Click Run (Recommended)

```bash
# Run the complete pipeline for a single instance
python scripts/run_full_pipeline.py \
    --instance-id cli__cli-10239 \
    --language go

# Or use the shell script
./scripts/run_pipeline.sh cli__cli-10239 go
```

### Install Dependencies

```bash
# 1. Install Codex CLI
npm i -g @openai/codex
codex auth login

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Ensure Docker is running (required for evaluation)
docker --version
```

## 📖 Detailed Usage

### Method 1: Python One-Click Script

```bash
# Full pipeline (Codex + evaluation)
python scripts/run_full_pipeline.py \
    --instance-id cli__cli-10239 \
    --language go

# Use a local dataset
python scripts/run_full_pipeline.py \
    --instance-id cli__cli-10239 \
    --dataset ./datasets/example_go.jsonl

# Run Codex only, skip evaluation
python scripts/run_full_pipeline.py \
    --instance-id cli__cli-10239 \
    --language go \
    --skip-eval

# Skip Codex, run evaluation only (use existing patch)
python scripts/run_full_pipeline.py \
    --instance-id cli__cli-10239 \
    --language go \
    --skip-codex
```

### Method 2: Step-by-Step Execution

#### Step 1: Download Dataset

```bash
# Automatically download from HuggingFace
python -c "
from huggingface_hub import hf_hub_download
local = hf_hub_download('ByteDance-Seed/Multi-SWE-bench', 'go/cli__cli_dataset.jsonl', repo_type='dataset')
print(f'Downloaded: {local}')
"
```

#### Step 2: Generate Patches

```bash
python run_eval.py \
    --dataset datasets/go/cli__cli_dataset.jsonl \
    --output-dir ./outputs/go \
    --language go \
    --instance-ids cli__cli-10239
```

#### Step 3: Convert Format

```bash
python convert_to_swebench.py \
    --input ./outputs/go/output.jsonl \
    --output ./outputs/go/official_patch.jsonl
```

#### Step 4: Run Evaluation

```bash
python -m multi_swe_bench.harness.run_evaluation \
    --config data/eval_config.json
```

## 📁 Project Structure

```
codex-multi-swe-bench/
├── README.md
├── requirements.txt
├── config.yaml                    # Codex runtime configuration
├── .gitignore
│
├── scripts/
│   ├── run_full_pipeline.py      # ⭐ One-click full pipeline (recommended)
│   ├── run_pipeline.sh           # Shell version
│   └── full_eval.sh              # Batch evaluation script
│
├── src/
│   ├── codex_runner.py           # Codex CLI wrapper
│   ├── data_loader.py            # Data loading
│   ├── instruction.py            # Instruction construction
│   └── utils.py                  # Utility functions
│
├── run_eval.py                   # Main entry for Codex patch generation
├── convert_to_swebench.py        # Format conversion tool
├── run_multi_swe_eval.py         # Multi-SWE-Bench evaluation script
│
├── datasets/                     # Datasets (gitignored)
│   ├── example_go.jsonl          # Example dataset
│   └── go/                       # Downloaded full datasets
│
├── outputs/                      # Output results (gitignored)
│   └── go/
│       ├── output.jsonl          # Codex raw output
│       └── official_patch.jsonl  # Official format patches
│
├── workspace/                    # Workspace (gitignored)
│   └── cli__cli-10239/           # Cloned repository
│
└── data/                         # Evaluation data (gitignored)
    ├── workdir/                  # Docker working directory
    ├── repos/                    # Cloned repos for evaluation
    ├── logs/                     # Evaluation logs
    └── results/                  # Evaluation results
```

## 📊 Data Formats

### Input: Multi-SWE-Bench Dataset

```json
{
  "org": "cli",
  "repo": "cli",
  "number": 10239,
  "instance_id": "cli__cli-10239",
  "title": "Extension update notices should be non-blocking",
  "body": "### Describe the bug\n\nAfter #9934 was merged...",
  "base": "6fe21d8f5224c5d8a58d210bd2bc70f5a008294c",
  "fix_patch": "diff --git a/...",
  "test_patch": "diff --git a/..."
}
```

### Output: Codex Results

```json
{
  "instance_id": "cli__cli-10239",
  "success": true,
  "patch": "diff --git a/pkg/cmd/root/extension.go...",
  "error": null,
  "start_time": "2026-01-22T11:39:35",
  "end_time": "2026-01-22T11:43:15"
}
```

### Official Evaluation Format

```json
{
  "org": "cli",
  "repo": "cli",
  "number": 10239,
  "fix_patch": "diff --git a/..."
}
```

## 📈 Evaluation Metrics

How Multi-SWE-Bench validates patches:

| Metric | Description |
|--------|-------------|
| `fixed_tests` | Tests fixed by the patch |
| `f2p_tests` | Fail → Pass: Tests that previously failed now pass |
| `p2p_tests` | Pass → Pass: Tests remain passing (no regression) |
| `resolved` | Whether the issue is fully resolved |

**Resolved Rate** = Number of fully resolved instances / Total instances

## 🔧 Configuration

### Codex Configuration (config.yaml)

```yaml
timeout: 1800          # Timeout in seconds
auto_approve: true     # Auto-approve changes
```

### Evaluation Configuration (eval_config.json)

```json
{
  "mode": "evaluation",
  "patch_files": ["./outputs/go/official_patch.jsonl"],
  "dataset_files": ["./datasets/go/cli__cli_10239.jsonl"],
  "max_workers": 1,
  "need_clone": true
}
```

## ⚠️ Important Notes

1. **Docker must be running**: Multi-SWE-Bench official evaluation requires Docker
2. **OPENAI_API_KEY**: Codex CLI requires a valid API key
3. **instance_id matching**: Must exactly match the ID in the dataset
4. **Resource requirements**: Evaluation requires significant memory (16GB+ recommended)

## 🔗 References

- [OpenAI Codex CLI](https://github.com/openai/codex)
- [Multi-SWE-Bench](https://github.com/multi-swe-bench/multi-swe-bench)
- [Multi-SWE-Bench Dataset](https://huggingface.co/datasets/ByteDance-Seed/Multi-SWE-bench)

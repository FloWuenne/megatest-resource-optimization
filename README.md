# megatest-resource-optimization
This repository contains scripts to fetch optimized Nextflow configurations and/or task-level execution metrics for nf-core pipeline AWS Megatests.

## Overview

The main script automatically fetches the latest nf-core pipeline releases from https://nf-co.re/pipelines.json and matches them against Megatest runs by commit ID. This ensures you're always getting resource configurations for the **most recent official releases**.

You can find all resource optimized configs based on previous runs under `/optimized_configs` and task execution metrics under `/task_metrics`.

## Basic Usage

If you have a Token on Seqera Platform with permissions to access the AWS Megatests workspace, you can run the following:

### Quick Start - Get Latest Release Configs

**Recommended: Fetch optimized configs and task metrics for latest releases**

This command will automatically match workflows to the latest nf-core releases and generate both optimized configs and task metrics for workflows with either `test_full` or `test_full_aws` profiles:

```bash
python get_workflow_configurations_metrics.py \
  -w [workspace_id] \
  -o \
  -m \
  -p test_full,test_full_aws
```

**What this does:**
- `-o`: Fetches optimized resource configurations for each pipeline
- `-m`: Fetches detailed task-level execution metrics
- `-p test_full,test_full_aws`: Includes workflows with either profile
- Automatically matches workflows to latest official nf-core releases by commit ID
- Outputs configs named with release tags (e.g., `ampliseq_2.15.0_optimized.config`)

### Additional Examples

```bash
# Fetch with default profile (test_full only)
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m

# Filter by specific profile (e.g., docker profile)
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -p docker

# Filter by specific labels (e.g., only optimized test runs)
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -l test_full_optimized

# Combine profile and label filters
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -p test_full -l test_full_optimized

# Specify custom output directory
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m --output-dir ./my_output
```

## Command Line Parameters

### Required
- `-w, --workspace-id`: Filter workflows by workspace ID
- At least one of `-o` or `-m` must be specified

### Filtering Options
- `-d, --days`: Number of days to look back for workflows (default: 4)
- `-s, --status`: Filter workflows by status (choices: SUBMITTED, RUNNING, SUCCEEDED, FAILED, CANCELLED)
- `-p, --profile`: Filter workflows by profile (comma-separated list for multiple profiles, e.g., 'test_full,docker'). Default: test_full
- `-l, --labels`: Filter workflows by labels (comma-separated list, e.g., 'test_full,test_full_optimized')

### Data Fetching Options
- `-o, --fetch-optimized-config`: Fetch and store optimized resource configurations
- `-m, --fetch-task-metrics`: Fetch and store task-level metrics

### API Options
- `-u, --base-url`: Base URL for the Tower API (default: https://api.cloud.seqera.io)
- `--max-pages`: Maximum number of pages to fetch (default: fetch all pages)
- `--items-per-page`: Number of items to fetch per page (default: 100)

### Output Options
- `--output-dir`: Base directory for all output files (default: current directory)

### CPU Adjustment Options
- `--adjust-cpu`: Adjust optimized CPU allocations based on actual task metrics (requires both -o and -m)
- `--cpu-safety-margin`: Safety margin multiplier for CPU adjustments (default: 1.2)
- `--cpu-reduction-threshold`: Only adjust CPUs if recommended < threshold * current (default: 0.5)

## Prerequisites

**Before running the script, ensure you have:**

1. **Seqera Platform Access Token**
   ```bash
   export TOWER_ACCESS_TOKEN="your_token_here"
   ```

2. **Python Dependencies**
   ```bash
   pip install requests
   ```

3. **Workspace ID**: The ID of your Seqera Platform workspace with Megatest runs

## Output Structure

The script organizes outputs in subdirectories:

- `workflow_info/all_workflows_info.csv` - Workflow metadata including release tags
- `optimized_configs/{pipeline}_{version}_optimized.config` - Optimized resource configurations
- `task_metrics/{pipeline}_{version}_tasks.csv` - Task-level execution metrics

Files are named using release tags (e.g., `ampliseq_2.15.0_optimized.config`) when available, otherwise using revision strings.

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

This repository provides tools to fetch optimized Nextflow resource configurations and/or task-level execution metrics for nf-core pipeline AWS Megatests. It queries the Seqera Platform API to find successful test_full workflow runs, then optionally retrieves:
- Optimized CPU and memory configurations per process
- Task-level execution metrics (CPU, memory, duration, I/O statistics)

## Key Architecture

### Core Script: get_workflow_configurations_metrics.py

**SeqeraAPI Client Class (lines 15-163)**
- Handles authentication and pagination for Seqera Platform API
- `get_workflows()` method fetches all workflows with pagination support
- `get_workflow_tasks()` method fetches task-level metrics for a workflow with pagination
- Returns combined results from multiple API pages

**Workflow Filtering Logic (lines 176-241)**
- Filters for workflows with profile containing 'test_full' and status 'SUCCEEDED'
- Implements revision selection strategy: prefers numeric revisions over 'dev', picks highest numeric revision per repository
- Groups workflows by repository to ensure one optimized config per pipeline

**Output Generation**
- CSV tracking: Overwrites workflow metadata to `workflow_info/all_workflows_info.csv` (asks for confirmation if file exists)
- Optimized configs (optional with `-o` flag): Fetches from `/workflow/{id}/optimal` endpoint with `optimizationTargets=cpus,memory`
  - Config files saved as: `optimized_configs/{pipeline_name}_{revision}_optimized.config`
  - Directory is cleared before writing new configs (after user confirmation)
- Task metrics (optional with `-m` flag): Fetches from `/workflow/{id}/tasks` endpoint with pagination
  - Task CSV files saved as: `task_metrics/{pipeline_name}_{revision}_tasks.csv`
  - Directory is cleared before writing new metrics (after user confirmation)

**Task Metrics Helper Functions (lines 217-309)**
- `write_tasks_to_csv()`: Writes task metrics to CSV with 19 metric columns
- `fetch_and_store_task_metrics()`: Orchestrates fetching and storing task data
- Handles task field variations (camelCase vs snake_case) from API responses

### Data Structure

All outputs are organized in subdirectories under the specified output directory (default: current directory):

**{output_dir}/workflow_info/** - Contains CSV tracking all processed workflows with columns: Workflow ID, Repository, Revision, Run Name, Workspace ID, Commit ID, Profile, Submit Time

**{output_dir}/optimized_configs/** - Nextflow config files with process-specific resource optimizations using `withName` selectors and `task.attempt` multipliers

**{output_dir}/task_metrics/** - CSV files (one per pipeline) with task-level execution metrics including: Pipeline, Revision, Workflow ID, Task ID, Task Name, Status, CPUs, Memory, Duration, Realtime, CPU %, Memory %, RSS, Peak RSS, VMem, Peak VMem, Read Bytes, Write Bytes, Attempt

## Commands

### Basic Usage
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] [OPTIONS]
```

**Required:**
- Set `TOWER_ACCESS_TOKEN` environment variable with Seqera Platform access token
- Specify at least one option: `-o` (optimized configs) or `-m` (task metrics) or both

**Important Behavior:**
- The script overwrites existing output files (does not append)
- Before overwriting, the script will:
  - List all existing files/directories that will be affected
  - Ask for user confirmation (yes/no)
  - Only proceed if user confirms with 'yes' or 'y'
  - Clear affected directories before writing new data

### Command Options
- `-w, --workspace-id`: Filter workflows by workspace ID (required)
- `-o, --fetch-optimized-config`: Fetch and store optimized resource configurations (optional)
- `-m, --fetch-task-metrics`: Fetch and store task-level metrics (optional)
- `--output-dir`: Base directory for all output files (default: current directory)
- `-d, --days`: Number of days to look back (default: 4)
- `-s, --status`: Filter by workflow status (SUBMITTED, RUNNING, SUCCEEDED, FAILED, CANCELLED)
- `-u, --base-url`: Tower API base URL (default: https://api.cloud.seqera.io)
- `-p, --max-pages`: Limit number of pages to fetch
- `--items-per-page`: Items per page (default: 100)

### Common Development Tasks

Fetch only optimized configs:
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o
```

Fetch only task metrics:
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -m
```

Fetch both optimized configs AND task metrics:
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m
```

Specify custom output directory:
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m --output-dir /path/to/output
```

Run script with debugging (limited to 1 page):
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -d 7 -p 1
```

Check latest workflow info (default output directory):
```bash
tail -n 20 workflow_info/all_workflows_info.csv
```

Check latest workflow info (custom output directory):
```bash
tail -n 20 /path/to/output/workflow_info/all_workflows_info.csv
```

Count generated configs:
```bash
ls optimized_configs/ | wc -l
```

View task metrics for a specific pipeline:
```bash
head -20 task_metrics/ampliseq_dev_tasks.csv
```

## API Integration Notes

**Seqera Platform API Endpoints**
- Workflow listing: `GET /workflow` with query params for filtering and pagination
- Optimal config: `GET /workflow/{workflowId}/optimal?workspaceId={id}&optimizationTargets=cpus,memory`
- Task metrics: `GET /workflow/{workflowId}/tasks?workspaceId={id}` with pagination support

**Pagination Pattern**: Uses offset-based pagination, incrementing offset by `items_per_page` until response contains fewer items than page size.

**Authentication**: Bearer token in Authorization header from `TOWER_ACCESS_TOKEN` environment variable.

## Output Format

**Optimized Config Structure**: Nextflow process scopes with `withName` selectors, setting `cpus` and `memory` with `task.attempt` multipliers for automatic retry scaling.

Example:
```groovy
process {
  withName: 'PIPELINE:MODULE:PROCESS_NAME' {
    cpus = { 4 * task.attempt }
    memory = { 2.GB * task.attempt }
  }
}
```

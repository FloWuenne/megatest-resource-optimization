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

**Workflow Filtering Logic**
- Filters for workflows by status 'SUCCEEDED' (always applied)
- **Profile Filtering** (with `-p, --profile` flag, default: 'test_full'):
  - Allows filtering workflows by one or more profiles (comma-separated)
  - Workflows must have at least one matching profile to be included
  - Example: `-p test_full,docker` includes workflows with either profile in their profile string
- **Optional Label Filtering** (with `-l, --labels` flag):
  - Allows filtering workflows by one or more labels (comma-separated)
  - Only workflows with at least one matching label are included
  - Example: `-l test_full,test_full_optimized` includes workflows with either label
- **NEW: Latest Release Matching Strategy** (primary):
  - Fetches latest release information from `https://nf-co.re/pipelines.json`
  - Matches workflow commit IDs (`commitId`) against the latest release's `tag_sha` (git commit hash)
  - Only selects workflows where the commit ID exactly matches the latest release commit
  - This ensures configs are generated for the most recent official release of each pipeline
- **Fallback Strategy** (if nf-co.re fetch fails):
  - Prefers numeric revisions over 'dev', picks highest numeric revision per repository
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

**CPU Validation Functions (lines 485-722)**
- `parse_config_cpu_allocations()`: Parses Nextflow config files to extract CPU allocations per process
- `calculate_process_cpu_usage()`: Calculates average CPU usage (pcpu) AND originally reserved CPUs per process from task metrics CSV
- `validate_and_adjust_cpu_config()`: Validates CPU allocations against actual usage and adjusts configs
  - **Validation Logic**: Compares actual CPU usage (`pcpu / 100`) against originally reserved CPUs from metrics
  - **Detection**: If `pcpu / 100 > reserved_cpu_from_metrics`, this indicates the process is over-subscribed
  - **Action**: Sets the config CPU value to the **original reserved CPU** from metrics (fixed value, no multiplier)
  - **Rationale**: Processes that are already over-subscribed should not be "optimized" - they should keep their original reservation
  - **In-place Modification**: Overwrites config files in `optimized_configs/` directory (after user confirmation)
  - **User Confirmation**: Asks for explicit user approval before modifying any files

**CPU Validation Workflow**
- Automatically triggers when both `-o` (optimized configs) and `-m` (task metrics) flags are used
- Runs after all configs and metrics are fetched
- For each pipeline:
  1. Reads the optimized config and task metrics CSV
  2. Extracts originally reserved CPUs from the metrics CSV "CPUs" column
  3. Matches processes between config and metrics
  4. Calculates actual CPU cores used: `actual_cpu_cores = pcpu / 100`
  5. Compares: if `actual_cpu_cores > reserved_cpu_from_metrics`, marks for adjustment
  6. Sets config CPU to the original reserved value (no multiplier, fixed value)
  7. Overwrites the config file with adjusted configuration
- Provides detailed summary showing which processes were adjusted and why
- Example output: `PROCESS_NAME: pcpu=250.5% (≈2.51 cores) > 2 cores reserved → set to 2 CPUs`

### Data Structure

All outputs are organized in subdirectories under the specified output directory (default: current directory):

**{output_dir}/workflow_info/** - Contains CSV tracking all processed workflows with columns: Workflow ID, Repository, Revision, **Release Tag** (matched from nf-co.re), Run Name, Workspace ID, Commit ID, Profile, Submit Time, Duration (ms), CPU Efficiency (%), Memory Efficiency (%)

**{output_dir}/optimized_configs/** - Nextflow config files with process-specific resource optimizations using `withName` selectors and `task.attempt` multipliers. Files are named using release tags (e.g., `ampliseq_2.15.0_optimized.config`) when available, otherwise using revision strings.

**{output_dir}/task_metrics/** - CSV files (one per pipeline) with task-level execution metrics including: Pipeline, Revision/Release Tag, Workflow ID, Task ID, Task Name, Status, CPUs, Memory, Duration, Realtime, CPU %, Memory %, RSS, Peak RSS, VMem, Peak VMem, Read Bytes, Write Bytes, Attempt. Files are named using release tags (e.g., `ampliseq_2.15.0_tasks.csv`) when available.

### Runtime Metrics Calculation

The script automatically calculates workflow-level runtime metrics for each workflow:

**Duration (ms):** Total workflow execution time in milliseconds
- Extracted from workflow response `duration` field if available
- Otherwise calculated from `submit` and `complete` timestamps
- Empty if workflow is still running or timestamps unavailable

**CPU Efficiency (%):** Average CPU utilization across all tasks
- Extracted from workflow response `stats.cpuEfficiency` if available
- Otherwise calculated as the mean of task-level `pcpu` values
- Represents the percentage of allocated CPU actually used

**Memory Efficiency (%):** Average memory utilization across all tasks
- Extracted from workflow response `stats.memoryEfficiency` if available
- Otherwise calculated as the mean of task-level `pmem` values
- Represents the percentage of allocated memory actually used

**Note:** Efficiency calculations require fetching task-level metrics. The script automatically fetches task data for all workflows to enable runtime metrics calculation, regardless of whether the `-m` flag is specified.

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
- `-p, --profile`: Filter by workflow profile (comma-separated list for multiple profiles, default: 'test_full')
- `-l, --labels`: Filter by workflow labels (comma-separated list, e.g., 'test_full,test_full_optimized')
- `-u, --base-url`: Tower API base URL (default: https://api.cloud.seqera.io)
- `--max-pages`: Limit number of pages to fetch
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

Fetch both optimized configs AND task metrics (with automatic CPU validation):
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m
```
**Note:** When both `-o` and `-m` flags are used, the script will automatically offer to validate CPU allocations after fetching data. It will:
- Check if any processes are using more CPU than originally reserved (pcpu/100 > reserved_cpu_from_metrics)
- Ask for user confirmation before modifying configs
- Set CPU allocations to the original reserved value (from metrics) for over-subscribed processes
- Rationale: Processes already over-subscribed should not be "optimized" - they need their original reservation
- Overwrite configs in `optimized_configs/` with validated configurations

Filter by specific profile (e.g., docker profile):
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -p docker
```

Filter by multiple profiles:
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -p test_full,docker
```

Filter by specific labels (e.g., only optimized runs):
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -l test_full_optimized
```

Combine profile and label filters:
```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m -p test_full -l test_full_optimized
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

**nf-core Pipelines Registry**
- Registry URL: `https://nf-co.re/pipelines.json`
- Provides metadata for all nf-core pipelines including latest releases
- Key fields used:
  - `name`: Pipeline name (e.g., "ampliseq")
  - `releases[0].tag_name`: Latest release version (e.g., "2.15.0")
  - `releases[0].tag_sha`: Git commit hash for that release
  - `releases[0].published_at`: Release publication timestamp
- **Commit Matching Logic**:
  - The script compares workflow `commitId` from Seqera Platform against `tag_sha` from nf-co.re
  - Supports both full SHA matching and prefix matching (shortened commits)
  - Only workflows with matching commits are selected, ensuring accuracy

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

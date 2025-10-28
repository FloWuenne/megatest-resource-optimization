# megatest-resource-optimization
This repository contains scripts to fetch optimized Nextflow configurations and/or task-level execution metrics for nf-core pipeline AWS Megatests.

You can find all resource optimized configs based on previous runs under `/optimized_configs` and task execution metrics under `/task_metrics`.

If you have a Token on Seqera Platform with permissions to access the AWS Megatests workspace, you can run the following:

```bash
python get_workflow_configurations_metrics.py -w [workspace_id] -o -m
```

Available command line parameters:
- `-w, --workspace-id`: Filter workflows by workspace ID (required)
- `-o, --fetch-optimized-config`: Fetch and store optimized resource configurations (optional)
- `-m, --fetch-task-metrics`: Fetch and store task-level metrics (optional)
- `-d, --days`: Number of days to look back for workflows (default: 4)
- `-s, --status`: Filter workflows by status (choices: SUBMITTED, RUNNING, SUCCEEDED, FAILED, CANCELLED)
- `-u, --base-url`: Base URL for the Tower API (default: https://api.cloud.seqera.io)
- `-p, --max-pages`: Maximum number of pages to fetch (default: fetch all pages)
- `--items-per-page`: Number of items to fetch per page (default: 100)

**Note:**
- The TOWER_ACCESS_TOKEN environment variable must be set with your Seqera Platform access token
- At least one option (`-o` or `-m`) must be specified

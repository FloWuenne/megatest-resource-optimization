# megatest-resource-optimization
This repository contains scripts to generate optimized Neextflow configurations for resource utilization for nf-core pipeline AWS Megatests.

You can find all resource optimized configs based on previous runs under `/optimized_configs`.

If you have a Token on Seqera Platform with permissions to access the AWS Megatests workspace, you can run the following:

`python get_megatest_workflow_configurations.py -w 59994744926013 -p 8`

Available command line parameters:
- `-w, --workspace_id`: The Seqera Platform workspace ID to fetch workflows from (required)
- `-p, --pages`: Maximum number of pages to fetch (default: all pages)
- `-t, --token`: Seqera Platform access token (can also be set via TOWER_ACCESS_TOKEN env var)
- `-b, --base_url`: Base URL for API endpoints (default: https://api.cloud.seqera.io)
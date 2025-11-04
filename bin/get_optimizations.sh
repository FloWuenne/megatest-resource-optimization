#!/bin/bash

###############################################################################
# Script: fetch_optimized_configs.sh
# Purpose: Retrieve optimized Nextflow config files for successful runs
#          filtered by a specific label from Seqera Tower.
# Author: Regan Hamel
# Date: October 28, 2025
###############################################################################
echo
echo "Fetching optimized Nextflow config files ..."

set -euo pipefail

# Make a directory to save the optimized configs
mkdir -p optimized_configs_tests
cd optimized_configs_tests

# Set the label to filter runs
LABEL="testCLI"

# Set the workspace ID
WORKSPACE_ID="80750985193419"

# Get the runs and their corresponding project names in one go
tw runs list --filter "label:$LABEL status:SUCCEEDED" -w $WORKSPACE_ID | while read -r line; do
    if [[ $line =~ SUCCEEDED ]]; then
        RUNID=$(echo "$line" | awk '{print $1}')
        PROJECT=$(echo "$line" | awk '{print $5}' | sed 's|.*/||')
        
        echo
        echo "Processing RUNID: $RUNID, Project: $PROJECT"
        
        curl "https://cloud.seqera.io/api/workflow/$RUNID/optimal?workspaceId=$WORKSPACE_ID&optimizationTargets=cpus,memory" \
            -H "Authorization: Bearer $TOWER_ACCESS_TOKEN" | jq -r ".config" > "${PROJECT}-${RUNID}_config.json"
    fi
done

echo
echo "Config files saved in the optimized_configs/ directory!"
echo
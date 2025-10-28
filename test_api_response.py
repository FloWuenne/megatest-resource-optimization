#!/usr/bin/env python3
"""
Quick diagnostic script to inspect the actual structure of task data from Seqera API
"""

import requests
import json
import os

# Get one workflow ID from the existing CSV
workflow_id = "2Tyut2OkofOvio"  # atacseq workflow from the CSV
workspace_id = "43561622610020"  # workspace from the CSV

# Get access token from environment
access_token = os.getenv('TOWER_ACCESS_TOKEN')
if not access_token:
    print("ERROR: TOWER_ACCESS_TOKEN not set")
    exit(1)

# API setup
base_url = "https://api.cloud.seqera.io"
headers = {
    "Authorization": f"Bearer {access_token}",
    "Content-Type": "application/json"
}

# Fetch tasks
endpoint = f"{base_url}/workflow/{workflow_id}/tasks"
params = {
    'workspaceId': workspace_id,
    'max': 1,  # Just get 1 task to inspect
    'offset': 0
}

print(f"🔍 Fetching task data from: {endpoint}")
print(f"   Workspace: {workspace_id}")
print(f"   Workflow: {workflow_id}\n")

try:
    response = requests.get(endpoint, headers=headers, params=params)
    response.raise_for_status()
    data = response.json()

    # Check if response is a dict with 'tasks' key or a list
    if isinstance(data, dict) and 'tasks' in data:
        tasks = data['tasks']
        print(f"✅ Response is a dict with 'tasks' key containing {len(tasks)} task(s)\n")
    elif isinstance(data, list):
        tasks = data
        print(f"✅ Response is a list containing {len(tasks)} task(s)\n")
    else:
        tasks = []
        print(f"⚠️  Unexpected response type: {type(data)}\n")
        print("Full response:")
        print(json.dumps(data, indent=2))

    if tasks and len(tasks) > 0:
        print("📋 First task structure:")
        print("=" * 80)
        print(json.dumps(tasks[0], indent=2, sort_keys=True))
        print("=" * 80)
        print(f"\n🔑 Available keys: {sorted(tasks[0].keys())}")
    else:
        print("⚠️  No tasks found in response")

except requests.exceptions.RequestException as e:
    print(f"❌ API request failed: {e}")
except Exception as e:
    print(f"❌ Error: {e}")

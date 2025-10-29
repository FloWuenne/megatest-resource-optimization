#!/usr/bin/env python3

import requests
import json
from typing import Optional
import os
from datetime import datetime, timedelta
import argparse
import logging
import csv
import shutil
import sys
import re

# ANSI color codes for colorful terminal output
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    GRAY = '\033[90m'

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class SeqeraAPI:
    """Client for interacting with Seqera Platform API"""
    
    def __init__(self, access_token: str, base_url: str = "https://api.cloud.seqera.io"):
        """
        Initialize Seqera API client
        
        Args:
            access_token (str): Your Seqera Platform access token
            base_url (str): Base URL for API endpoints (default: https://api.cloud.seqera.io)
        """
        self.base_url = base_url.rstrip('/')
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
    
    def get_workflows(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        max_pages: Optional[int] = None,
        items_per_page: int = 100
    ) -> dict:
        """
        Get workflow execution information with pagination support
        
        Args:
            workspace_id (str, optional): Filter by workspace ID
            status (str, optional): Filter by workflow status
            start_date (datetime, optional): Filter by start date
            end_date (datetime, optional): Filter by end date
            max_pages (int, optional): Maximum number of pages to fetch (None for all)
            items_per_page (int): Number of items per page (default: 100)
            
        Returns:
            dict: Combined response from all pages with workflows list
        """
        endpoint = f"{self.base_url}/workflow"
        
        # Build query parameters
        params = {
            'max': items_per_page,
            'offset': 0
        }
        if workspace_id:
            params['workspaceId'] = workspace_id
        if status:
            params['status'] = status
        if start_date:
            params['start'] = start_date.isoformat()
        if end_date:
            params['end'] = end_date.isoformat()

        # Log the query parameters for debugging
        logger.info(f"🔍 Query parameters: {params}")

        all_workflows = []
        seen_workflow_ids = set()
        page = 1

        while True:
            try:
                logger.info(f"📄 Fetching page {page} (offset: {params['offset']})")
                response = requests.get(endpoint, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                # Handle both list and dict response formats
                workflows = data.get('workflows', data if isinstance(data, list) else [])

                # Check if we got no results (end of data)
                if len(workflows) == 0:
                    logger.info(f"✅ No more workflows to fetch (empty page)")
                    break

                # Track new workflows and detect duplicates
                new_workflows_count = 0
                outside_date_range_count = 0
                for wf in workflows:
                    wf_id = wf.get('workflow', {}).get('id', '')
                    if wf_id and wf_id not in seen_workflow_ids:
                        # Additional date filtering on client side as safeguard
                        if start_date or end_date:
                            submit_time_str = wf.get('workflow', {}).get('submit', '')
                            if submit_time_str:
                                try:
                                    # Parse ISO format date (handles both with and without timezone)
                                    # Example: "2024-10-25T21:34:07Z" or "2024-10-25T21:34:07"
                                    submit_time = datetime.fromisoformat(submit_time_str.replace('Z', '+00:00'))
                                    # Remove timezone info for comparison if present
                                    if submit_time.tzinfo:
                                        submit_time = submit_time.replace(tzinfo=None)
                                    if start_date and submit_time < start_date:
                                        outside_date_range_count += 1
                                        continue
                                    if end_date and submit_time > end_date:
                                        outside_date_range_count += 1
                                        continue
                                except (ValueError, AttributeError):
                                    pass  # If date parsing fails, include the workflow

                        seen_workflow_ids.add(wf_id)
                        all_workflows.append(wf)
                        new_workflows_count += 1

                if outside_date_range_count > 0:
                    logger.info(f"⏰ Filtered out {outside_date_range_count} workflows outside date range")

                logger.info(f"📊 Page {page}: {len(workflows)} workflows returned, {new_workflows_count} new, {len(workflows) - new_workflows_count} duplicates")

                # If we got no new workflows, we're likely seeing duplicates - stop pagination
                if new_workflows_count == 0:
                    logger.info(f"⚠️  No new workflows on page {page}, stopping pagination")
                    break

                # Check if we've reached the end of the data (less than full page)
                if len(workflows) < items_per_page:
                    logger.info(f"✅ Received partial page ({len(workflows)} < {items_per_page}), end of data")
                    break

                # Check if we've reached max_pages
                if max_pages and page >= max_pages:
                    logger.info(f"⚠️  Reached maximum number of pages ({max_pages})")
                    break

                # Update offset for next page
                params['offset'] += items_per_page
                page += 1

            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Request failed on page {page}: {str(e)}")
                break

        logger.info(f"✅ Total unique workflows fetched: {len(all_workflows)}")
        return {'workflows': all_workflows}

    def get_workflow_tasks(
        self,
        workflow_id: str,
        workspace_id: str,
        max_pages: Optional[int] = None,
        items_per_page: int = 100
    ) -> list:
        """
        Get task-level metrics for a workflow with pagination support

        Args:
            workflow_id (str): Workflow ID to fetch tasks for
            workspace_id (str): Workspace ID
            max_pages (int, optional): Maximum number of pages to fetch (None for all)
            items_per_page (int): Number of items per page (default: 100)

        Returns:
            list: List of all tasks with their metrics
        """
        endpoint = f"{self.base_url}/workflow/{workflow_id}/tasks"

        params = {
            'workspaceId': workspace_id,
            'max': items_per_page,
            'offset': 0
        }

        all_tasks = []
        page = 1

        while True:
            try:
                logger.debug(f"Fetching tasks page {page} for workflow {workflow_id}")
                response = requests.get(endpoint, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()

                # Handle both list and dict response formats
                tasks = data.get('tasks', data if isinstance(data, list) else [])

                # Unwrap nested 'task' object from each item
                for task_item in tasks:
                    if isinstance(task_item, dict) and 'task' in task_item:
                        all_tasks.append(task_item['task'])
                    else:
                        all_tasks.append(task_item)

                # Check if we've reached the end of the data
                if len(tasks) < items_per_page:
                    break

                # Check if we've reached max_pages
                if max_pages and page >= max_pages:
                    logger.debug(f"⚠️  Reached maximum number of pages ({max_pages})")
                    break

                # Update offset for next page
                params['offset'] += items_per_page
                page += 1

            except requests.exceptions.RequestException as e:
                logger.error(f"❌ Request failed on page {page} for workflow {workflow_id}: {str(e)}")
                break

        logger.info(f"✅ Fetched {len(all_tasks)} tasks for workflow {workflow_id}")
        return all_tasks

def parse_args():
    """Parse command line arguments"""
    parser = argparse.ArgumentParser(
        description="Query Seqera/Tower API for workflow information",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    
    parser.add_argument(
        "-w", "--workspace-id",
        help="Filter workflows by workspace ID"
    )
    
    parser.add_argument(
        "-d", "--days",
        type=int,
        default=4,
        help="Number of days to look back for workflows"
    )

    parser.add_argument(
        "-s", "--status",
        choices=["SUBMITTED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"],
        help="Filter workflows by status"
    )

    parser.add_argument(
        "-p", "--profile",
        default="test_full",
        help="Filter workflows by profile (comma-separated list for multiple profiles, e.g., 'test_full,docker'). Default: test_full"
    )

    parser.add_argument(
        "-l", "--labels",
        help="Filter workflows by labels (comma-separated list, e.g., 'test_full,test_full_optimized')"
    )

    parser.add_argument(
        "-u", "--base-url",
        default="https://api.cloud.seqera.io",
        help="Base URL for the Tower API"
    )

    parser.add_argument(
        "--max-pages",
        type=int,
        help="Maximum number of pages to fetch (default: fetch all pages)"
    )
    
    parser.add_argument(
        "--items-per-page",
        type=int,
        default=100,
        help="Number of items to fetch per page (default: 100)"
    )

    parser.add_argument(
        "-o", "--fetch-optimized-config",
        action="store_true",
        help="Fetch and store optimized resource configurations for each workflow"
    )

    parser.add_argument(
        "-m", "--fetch-task-metrics",
        action="store_true",
        help="Fetch and store task-level metrics for each workflow"
    )

    parser.add_argument(
        "--output-dir",
        default=".",
        help="Base directory for all output files (default: current directory)"
    )

    return parser.parse_args()

def display_startup_banner(args):
    """Display colorful startup banner with configuration"""
    print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}{Colors.MAGENTA}🚀 Seqera Platform Workflow Configuration & Metrics Fetcher{Colors.RESET}")
    print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

    print(f"{Colors.BOLD}{Colors.YELLOW}⚙️  Configuration:{Colors.RESET}")
    print(f"{Colors.CYAN}┌{'─'*78}┐{Colors.RESET}")

    # Workspace ID
    if args.workspace_id:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}✓{Colors.RESET} Workspace ID:        {Colors.BOLD}{args.workspace_id}{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.YELLOW}⚠{Colors.RESET} Workspace ID:        {Colors.GRAY}Not specified{Colors.RESET}")

    # Time range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=args.days)
    print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}📅{Colors.RESET} Time Range:          {Colors.BOLD}{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}{Colors.RESET} ({args.days} days)")

    # Status filter
    if args.status:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}🔍{Colors.RESET} Status Filter:       {Colors.BOLD}{args.status}{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.BLUE}🔍{Colors.RESET} Status Filter:       {Colors.GRAY}All statuses{Colors.RESET}")

    # Profile filter
    print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}📋{Colors.RESET} Profile Filter:      {Colors.BOLD}{args.profile}{Colors.RESET}")

    # Label filter
    if args.labels:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}🏷️ {Colors.RESET} Label Filter:        {Colors.BOLD}{args.labels}{Colors.RESET}")
    else:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.BLUE}🏷️ {Colors.RESET} Label Filter:        {Colors.GRAY}All labels{Colors.RESET}")

    # API Base URL
    print(f"{Colors.CYAN}│{Colors.RESET} {Colors.BLUE}🌐{Colors.RESET} API Base URL:        {Colors.BOLD}{args.base_url}{Colors.RESET}")

    # Pagination
    if args.max_pages:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.YELLOW}📄{Colors.RESET} Max Pages:           {Colors.BOLD}{args.max_pages}{Colors.RESET} (limited)")
    else:
        print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}📄{Colors.RESET} Max Pages:           {Colors.BOLD}Unlimited{Colors.RESET}")

    print(f"{Colors.CYAN}│{Colors.RESET} {Colors.BLUE}📊{Colors.RESET} Items per Page:      {Colors.BOLD}{args.items_per_page}{Colors.RESET}")

    # Output directory
    print(f"{Colors.CYAN}│{Colors.RESET} {Colors.GREEN}📁{Colors.RESET} Output Directory:    {Colors.BOLD}{args.output_dir}{Colors.RESET}")

    print(f"{Colors.CYAN}├{'─'*78}┤{Colors.RESET}")
    print(f"{Colors.CYAN}│{Colors.RESET} {Colors.BOLD}{Colors.YELLOW}📥 Data to Fetch:{Colors.RESET}")

    # What to fetch
    if args.fetch_optimized_config:
        print(f"{Colors.CYAN}│{Colors.RESET}   {Colors.GREEN}✓{Colors.RESET} Optimized Resource Configurations")
    else:
        print(f"{Colors.CYAN}│{Colors.RESET}   {Colors.GRAY}✗ Optimized Resource Configurations{Colors.RESET}")

    if args.fetch_task_metrics:
        print(f"{Colors.CYAN}│{Colors.RESET}   {Colors.GREEN}✓{Colors.RESET} Task-level Execution Metrics")
    else:
        print(f"{Colors.CYAN}│{Colors.RESET}   {Colors.GRAY}✗ Task-level Execution Metrics{Colors.RESET}")

    print(f"{Colors.CYAN}└{'─'*78}┘{Colors.RESET}\n")
    print(f"{Colors.GREEN}🎯 Starting workflow query...{Colors.RESET}\n")

def write_tasks_to_csv(tasks: list, file_path: str, pipeline_name: str, revision: str, workflow_id: str, mode: str = 'w'):
    """
    Write task metrics to CSV file

    Args:
        tasks (list): List of task dictionaries with metrics
        file_path (str): Path to output CSV file
        pipeline_name (str): Name of the pipeline
        revision (str): Pipeline revision
        workflow_id (str): Workflow ID
        mode (str): File mode - 'w' for write/overwrite, 'a' for append (default: 'w')
    """
    headers = [
        'Pipeline', 'Revision', 'Workflow ID', 'Task ID', 'Task Name', 'Status',
        'CPUs', 'Memory (bytes)', 'Duration (ms)', 'Realtime (ms)',
        'CPU %', 'Memory %', 'RSS (bytes)', 'Peak RSS (bytes)',
        'VMem (bytes)', 'Peak VMem (bytes)', 'Read Bytes', 'Write Bytes', 'Attempt'
    ]

    # Debug: Log the structure of the first task to understand API response
    if tasks and len(tasks) > 0:
        logger.debug(f"🔍 DEBUG - First task structure: {json.dumps(tasks[0], indent=2)}")
        logger.debug(f"🔍 DEBUG - First task keys: {list(tasks[0].keys())}")

    # Always write headers when in write mode, or when file doesn't exist in append mode
    file_exists = os.path.isfile(file_path)
    write_headers = (mode == 'w') or (not file_exists)

    with open(file_path, mode, newline='') as csvfile:
        writer = csv.writer(csvfile)

        if write_headers:
            writer.writerow(headers)

        for task in tasks:
            # Extract task metrics with safe defaults
            row = [
                pipeline_name,
                revision,
                workflow_id,
                task.get('taskId', task.get('id', '')),
                task.get('name', task.get('process', '')),
                task.get('status', ''),
                task.get('cpus', ''),
                task.get('memory', ''),
                task.get('duration', ''),
                task.get('realtime', ''),
                task.get('pcpu', ''),
                task.get('pmem', ''),
                task.get('rss', ''),
                task.get('peakRss', task.get('peak_rss', '')),
                task.get('vmem', ''),
                task.get('peakVmem', task.get('peak_vmem', '')),
                task.get('readBytes', task.get('read_bytes', '')),
                task.get('writeBytes', task.get('write_bytes', '')),
                task.get('attempt', '')
            ]
            writer.writerow(row)

    action = "Overwrote" if mode == 'w' and file_exists else "Wrote"
    logger.info(f"💾 {action} {len(tasks)} tasks to {file_path}")

def fetch_and_store_task_metrics(
    client: SeqeraAPI,
    workflow_id: str,
    workspace_id: str,
    pipeline_name: str,
    revision: str,
    output_dir: str
):
    """
    Fetch task metrics for a workflow and store to CSV

    Args:
        client (SeqeraAPI): API client instance
        workflow_id (str): Workflow ID to fetch tasks for
        workspace_id (str): Workspace ID
        pipeline_name (str): Pipeline name for file naming
        revision (str): Pipeline revision for file naming
        output_dir (str): Directory to store CSV files
    """
    try:
        logger.info(f"📊 Fetching task metrics for workflow {workflow_id} (pipeline: {pipeline_name}, workspace: {workspace_id})")

        # Fetch all tasks for the workflow
        tasks = client.get_workflow_tasks(workflow_id, workspace_id)

        if not tasks:
            logger.warning(f"⚠️  No tasks found for workflow {workflow_id} (pipeline: {pipeline_name})")
            return

        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Create filename based on pipeline and revision
        file_name = f"{pipeline_name}_{revision}_tasks.csv"
        file_path = os.path.join(output_dir, file_name)

        # Write tasks to CSV
        write_tasks_to_csv(tasks, file_path, pipeline_name, revision, workflow_id)
        logger.info(f"✅ Successfully wrote {len(tasks)} tasks to {file_path}")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ API request failed for workflow {workflow_id} (pipeline: {pipeline_name}, workspace: {workspace_id}): {e}")
    except Exception as e:
        logger.error(f"❌ Failed to fetch/store task metrics for workflow {workflow_id} (pipeline: {pipeline_name}): {e}")

def parse_config_cpu_allocations(config_content: str) -> dict:
    """
    Parse optimized config file to extract CPU allocations per process

    Args:
        config_content (str): Content of the config file

    Returns:
        dict: Mapping of process name to base CPU value
              {process_name: base_cpu_value}
    """
    process_cpus = {}

    # Pattern to match process blocks with CPU allocations
    # Matches: withName: 'PROCESS_NAME' { cpus = { X * task.attempt }
    # or: withName: 'PROCESS_NAME' { cpus = X
    process_pattern = r"withName:\s*['\"]([^'\"]+)['\"]"
    cpu_pattern = r"cpus\s*=\s*\{?\s*(\d+(?:\.\d+)?)\s*(?:\*\s*task\.attempt\s*)?\}?"

    lines = config_content.split('\n')
    current_process = None

    for line in lines:
        # Check if this line defines a process
        process_match = re.search(process_pattern, line)
        if process_match:
            current_process = process_match.group(1)
            continue

        # Check if this line defines CPUs for the current process
        if current_process:
            cpu_match = re.search(cpu_pattern, line)
            if cpu_match:
                base_cpu = float(cpu_match.group(1))
                process_cpus[current_process] = base_cpu
                current_process = None  # Reset after finding CPU

    return process_cpus

def calculate_process_cpu_usage(metrics_path: str) -> dict:
    """
    Calculate average CPU usage (pcpu) and reserved CPUs per process from task metrics CSV

    Args:
        metrics_path (str): Path to task metrics CSV file

    Returns:
        dict: Mapping of process name to usage data
              {process_name: {'avg_pcpu': float, 'reserved_cpus': float}}
    """
    process_data = {}

    if not os.path.exists(metrics_path):
        logger.warning(f"⚠️  Metrics file not found: {metrics_path}")
        return process_data

    try:
        with open(metrics_path, 'r') as csvfile:
            reader = csv.DictReader(csvfile)

            # Group tasks by process name
            process_tasks = {}
            for row in reader:
                task_name = row.get('Task Name', '')
                pcpu_str = row.get('CPU %', '')
                cpus_str = row.get('CPUs', '')

                if not task_name:
                    continue

                # Extract base process name by removing sample suffix (text in parentheses)
                # E.g., "PROCESS_NAME (sample1)" -> "PROCESS_NAME"
                process_name = re.sub(r'\s*\([^)]+\)\s*$', '', task_name).strip()

                if process_name not in process_tasks:
                    process_tasks[process_name] = {'pcpu_values': [], 'reserved_cpus': []}

                # Collect pcpu values
                if pcpu_str:
                    try:
                        pcpu = float(pcpu_str)
                        process_tasks[process_name]['pcpu_values'].append(pcpu)
                    except ValueError:
                        pass

                # Collect reserved CPU values
                if cpus_str:
                    try:
                        cpus = float(cpus_str)
                        process_tasks[process_name]['reserved_cpus'].append(cpus)
                    except ValueError:
                        pass

            # Calculate averages per process
            for process_name, data in process_tasks.items():
                result = {}

                if data['pcpu_values']:
                    result['avg_pcpu'] = sum(data['pcpu_values']) / len(data['pcpu_values'])
                else:
                    result['avg_pcpu'] = None

                if data['reserved_cpus']:
                    # Use the most common reserved CPU value (mode), or average if varied
                    result['reserved_cpus'] = sum(data['reserved_cpus']) / len(data['reserved_cpus'])
                else:
                    result['reserved_cpus'] = None

                if result['avg_pcpu'] is not None or result['reserved_cpus'] is not None:
                    process_data[process_name] = result

    except Exception as e:
        logger.error(f"❌ Error reading metrics file {metrics_path}: {e}")

    return process_data

def validate_and_adjust_cpu_config(
    config_path: str,
    metrics_path: str,
    pipeline_name: str
) -> dict:
    """
    Validate CPU allocations against actual usage and adjust if needed

    Compares actual CPU usage (pcpu) against originally reserved CPUs from metrics.
    If pcpu/100 > reserved_cpu (from metrics), sets config to use the original reserved CPU value.

    Args:
        config_path (str): Path to optimized config file
        metrics_path (str): Path to task metrics CSV file
        pipeline_name (str): Name of the pipeline (for logging)

    Returns:
        dict: Summary with 'adjusted' count, 'no_change' count, and 'adjustments' list
    """
    summary = {
        'adjusted': 0,
        'no_change': 0,
        'adjustments': []
    }

    # Read config content
    try:
        with open(config_path, 'r') as f:
            config_content = f.read()
    except Exception as e:
        logger.error(f"❌ Error reading config {config_path}: {e}")
        return summary

    # Parse CPU allocations from config (only needed to find processes to check)
    config_cpus = parse_config_cpu_allocations(config_content)

    # Get actual CPU usage and reserved CPUs from metrics
    metrics_data = calculate_process_cpu_usage(metrics_path)

    if not config_cpus or not metrics_data:
        logger.debug(f"No CPU data to validate for {pipeline_name}")
        return summary

    # Track which processes need adjustment
    adjustments_needed = {}

    for process_name in config_cpus.keys():
        # Match process name (handle different formats)
        # Config might have full path like "PIPELINE:MODULE:PROCESS"
        # Metrics should now have the same format (without sample suffixes)

        matched_data = None

        # Try exact match first
        if process_name in metrics_data:
            matched_data = metrics_data[process_name]
        else:
            # Try fuzzy matching: check if config process name matches or is contained in any metric process
            for metric_process, data in metrics_data.items():
                # Check if they're the same or if one is a suffix of the other
                if (metric_process == process_name or
                    metric_process in process_name or
                    process_name in metric_process or
                    process_name.endswith(metric_process.split(':')[-1])):
                    matched_data = data
                    break

        if matched_data is None:
            logger.debug(f"No metrics found for process {process_name}")
            summary['no_change'] += 1
            continue

        avg_pcpu = matched_data.get('avg_pcpu')
        reserved_cpus = matched_data.get('reserved_cpus')

        if avg_pcpu is None or reserved_cpus is None:
            logger.debug(f"Incomplete data for process {process_name}")
            summary['no_change'] += 1
            continue

        # Calculate actual CPU cores used (pcpu is percentage, typically per core)
        # pcpu / 100 gives us the fraction of a core used
        actual_cpu_cores = avg_pcpu / 100

        # Check if actual usage exceeds originally reserved CPUs
        if actual_cpu_cores > reserved_cpus:
            logger.info(f"🔍 {process_name}: pcpu={avg_pcpu:.1f}% (≈{actual_cpu_cores:.2f} cores) > reserved={reserved_cpus} cores")
            adjustments_needed[process_name] = {
                'reserved_cpus': reserved_cpus,
                'actual_usage': actual_cpu_cores,
                'pcpu': avg_pcpu
            }
            summary['adjusted'] += 1
        else:
            summary['no_change'] += 1

    # If no adjustments needed, return
    if not adjustments_needed:
        logger.info(f"✅ {pipeline_name}: No CPU adjustments needed")
        return summary

    # Adjust config content - set CPUs to original reserved value (no multiplier)
    modified_content = config_content

    for process_name, adjustment in adjustments_needed.items():
        # Pattern to match the entire CPU line (with or without multiplier)
        # Matches: cpus = { X * task.attempt } or cpus = X or cpus = { X }
        pattern = rf"(withName:\s*['\"]" + re.escape(process_name) + r"['\"].*?cpus\s*=\s*)\{{?\s*\d+(?:\.\d+)?(?:\s*\*\s*task\.attempt)?\s*\}}?"

        # Replace with fixed CPU value from original metrics (no multiplier, no braces)
        reserved_cpu_int = int(adjustment['reserved_cpus'])
        replacement = rf"\g<1>{reserved_cpu_int}"

        modified_content = re.sub(
            pattern,
            replacement,
            modified_content,
            flags=re.DOTALL
        )

        summary['adjustments'].append({
            'process': process_name,
            'reserved_cpus': adjustment['reserved_cpus'],
            'actual_usage': adjustment['actual_usage'],
            'pcpu': adjustment['pcpu']
        })

    # Write modified config back to file
    try:
        with open(config_path, 'w') as f:
            f.write(modified_content)
        logger.info(f"💾 Updated {config_path} with CPU adjustments")
    except Exception as e:
        logger.error(f"❌ Error writing config {config_path}: {e}")

    return summary

def fetch_nfcore_latest_releases() -> dict:
    """
    Fetch the latest release information from nf-co.re/pipelines.json

    Returns:
        dict: Mapping of pipeline name to latest release info
              {pipeline_name: {'tag_name': '2.15.0', 'tag_sha': 'abc123...', 'published_at': '...'}}
    """
    try:
        logger.info("🌐 Fetching latest release information from nf-co.re...")
        response = requests.get("https://nf-co.re/pipelines.json", timeout=30)
        response.raise_for_status()
        data = response.json()

        latest_releases = {}
        workflows = data.get('remote_workflows', [])

        for workflow in workflows:
            pipeline_name = workflow.get('name', '')
            releases = workflow.get('releases', [])

            if pipeline_name and releases:
                # The first release in the array is typically the latest
                latest_release = releases[0]
                latest_releases[pipeline_name] = {
                    'tag_name': latest_release.get('tag_name', ''),
                    'tag_sha': latest_release.get('tag_sha', ''),
                    'published_at': latest_release.get('published_at', '')
                }

        logger.info(f"✅ Retrieved latest release info for {len(latest_releases)} pipelines")
        return latest_releases

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Failed to fetch nf-co.re pipelines.json: {e}")
        return {}
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"❌ Error parsing nf-co.re pipelines.json: {e}")
        return {}

def get_workflow_runtime_metrics(
    workflow_data: dict,
    client: SeqeraAPI,
    workflow_id: str,
    workspace_id: str
) -> tuple:
    """
    Extract or calculate workflow runtime metrics

    Args:
        workflow_data (dict): The workflow object from API response
        client (SeqeraAPI): API client instance
        workflow_id (str): Workflow ID
        workspace_id (str): Workspace ID

    Returns:
        tuple: (duration_ms, cpu_efficiency, memory_efficiency)
               Returns (None, None, None) if metrics cannot be calculated
    """
    try:
        nested = workflow_data.get('workflow', {})

        # Try to get duration from workflow-level fields
        duration_ms = None

        # Check for various possible duration fields in the API response
        if 'duration' in nested:
            duration_ms = nested.get('duration')
        elif 'submit' in nested and 'complete' in nested:
            # Calculate duration from submit and complete timestamps
            try:
                submit_str = nested.get('submit', '')
                complete_str = nested.get('complete', '')
                if submit_str and complete_str:
                    submit_time = datetime.fromisoformat(submit_str.replace('Z', '+00:00'))
                    complete_time = datetime.fromisoformat(complete_str.replace('Z', '+00:00'))
                    duration_ms = int((complete_time - submit_time).total_seconds() * 1000)
            except (ValueError, AttributeError) as e:
                logger.debug(f"Could not calculate duration from timestamps: {e}")

        # Try to get efficiency metrics from workflow-level fields
        cpu_efficiency = nested.get('stats', {}).get('cpuEfficiency') if isinstance(nested.get('stats'), dict) else None
        memory_efficiency = nested.get('stats', {}).get('memoryEfficiency') if isinstance(nested.get('stats'), dict) else None

        # If workflow-level metrics aren't available, calculate from task data
        if cpu_efficiency is None or memory_efficiency is None:
            logger.debug(f"Workflow-level efficiency metrics not available, calculating from tasks for workflow {workflow_id}")

            # Fetch tasks for this workflow
            tasks = client.get_workflow_tasks(workflow_id, workspace_id)

            if tasks and len(tasks) > 0:
                # Calculate CPU efficiency (average of task pcpu values)
                cpu_values = [task.get('pcpu', 0) for task in tasks if task.get('pcpu') is not None]
                if cpu_values:
                    cpu_efficiency = sum(cpu_values) / len(cpu_values)

                # Calculate memory efficiency (average of task pmem values)
                mem_values = [task.get('pmem', 0) for task in tasks if task.get('pmem') is not None]
                if mem_values:
                    memory_efficiency = sum(mem_values) / len(mem_values)

                logger.debug(f"Calculated efficiency from {len(tasks)} tasks: CPU={cpu_efficiency:.2f}%, Memory={memory_efficiency:.2f}%")
            else:
                logger.debug(f"No tasks found for workflow {workflow_id}, cannot calculate efficiency")

        return (duration_ms, cpu_efficiency, memory_efficiency)

    except Exception as e:
        logger.error(f"❌ Error getting runtime metrics for workflow {workflow_id}: {e}")
        return (None, None, None)

def main():
    args = parse_args()

    # Display startup banner
    display_startup_banner(args)

    # Validate that at least one option is selected
    if not args.fetch_optimized_config and not args.fetch_task_metrics:
        print(f"{Colors.RED}❌ Error: Please specify at least one option: -o/--fetch-optimized-config or -m/--fetch-task-metrics{Colors.RESET}\n")
        raise ValueError("Please specify at least one option: -o/--fetch-optimized-config or -m/--fetch-task-metrics")

    # Get access token from environment variable
    access_token = os.getenv('TOWER_ACCESS_TOKEN')
    if not access_token:
        print(f"{Colors.RED}❌ Error: TOWER_ACCESS_TOKEN environment variable not set{Colors.RESET}\n")
        raise ValueError("Please set TOWER_ACCESS_TOKEN environment variable")
    
    # Initialize API client
    client = SeqeraAPI(access_token, base_url=args.base_url)
    
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
        
        # Get workflows and print the raw response
        response_data = client.get_workflows(
            workspace_id=args.workspace_id,
            status=args.status,
            start_date=start_date,
            end_date=end_date,
            max_pages=args.max_pages,
            items_per_page=args.items_per_page
        )
        
        # Filter workflows by profile and status
        workflows = response_data.get('workflows', [])
        if not workflows:
            logger.info("ℹ️  No workflows found matching the criteria")
            return

        # Parse profile filter
        allowed_profiles = [p.strip() for p in args.profile.split(',')]
        logger.info(f"📋 Filtering by profiles: {allowed_profiles}")

        # Parse label filter if provided
        allowed_labels = None
        if args.labels:
            allowed_labels = [label.strip() for label in args.labels.split(',')]
            logger.info(f"🏷️  Filtering by labels: {allowed_labels}")

        filtered = []
        for wf in workflows:
            nested = wf.get('workflow', {})
            # Extract profile and status from nested workflow
            profile = nested.get('profile', '') or ''
            # status field might be a string or dict
            raw_status = nested.get('status', '')
            status_val = raw_status if isinstance(raw_status, str) else raw_status.get('status', '')

            # Check status first
            if status_val.upper() != 'SUCCEEDED':
                continue

            # Check if workflow has any of the allowed profiles
            has_allowed_profile = any(allowed_profile in profile for allowed_profile in allowed_profiles)
            if not has_allowed_profile:
                continue

            # Check labels if filter is specified
            if allowed_labels:
                workflow_labels = nested.get('labels', [])
                # Labels might be a list or comma-separated string
                if isinstance(workflow_labels, str):
                    workflow_labels = [label.strip() for label in workflow_labels.split(',')]
                elif not isinstance(workflow_labels, list):
                    workflow_labels = []

                # Check if workflow has at least one of the allowed labels
                has_allowed_label = any(label in allowed_labels for label in workflow_labels)
                if not has_allowed_label:
                    continue

            filtered.append(wf)

        if not filtered:
            logger.info(f"ℹ️  No workflows found matching profile(s) {allowed_profiles}, status 'SUCCEEDED', and label filter")
            return

        # Fetch latest release information from nf-co.re
        nfcore_latest = fetch_nfcore_latest_releases()

        if not nfcore_latest:
            logger.warning("⚠️  Failed to fetch nf-co.re releases, falling back to old revision logic")
            # Fallback to old logic if nf-co.re fetch fails
            repo_map = {}
            for wf in filtered:
                repo = wf.get('workflow', {}).get('repository', '')
                if repo:
                    repo_map.setdefault(repo, []).append(wf)

            latest_by_repo = {}
            for repo, wfs in repo_map.items():
                numeric_revs = []
                dev_revs = []
                for wf in wfs:
                    rev_str = str(wf.get('workflow', {}).get('revision', ''))
                    # Treat None or empty as 'dev'
                    if not rev_str or rev_str == 'None':
                        dev_revs.append(wf)
                        continue
                    if rev_str.lower() == 'dev':
                        dev_revs.append(wf)
                    else:
                        try:
                            rev_int = int(rev_str)
                            numeric_revs.append((rev_int, wf))
                        except ValueError:
                            continue

                if numeric_revs:
                    latest_wf = max(numeric_revs, key=lambda x: x[0])[1]
                elif dev_revs:
                    latest_wf = dev_revs[0]
                elif wfs:
                    latest_wf = wfs[0]
                else:
                    continue

                latest_by_repo[repo] = latest_wf

            filtered = list(latest_by_repo.values())
        else:
            # New logic: Match workflows by commit ID against latest release tag_sha
            logger.info("🔍 Matching workflows to latest releases by commit ID...")

            # Group workflows by repository
            repo_map = {}
            for wf in filtered:
                repo = wf.get('workflow', {}).get('repository', '')
                if repo:
                    repo_map.setdefault(repo, []).append(wf)

            latest_by_repo = {}
            matched_count = 0
            unmatched_count = 0

            for repo, wfs in repo_map.items():
                # Extract pipeline name from repository (e.g., "nf-core/ampliseq" -> "ampliseq")
                pipeline_name = repo.split('/')[-1] if repo else ''

                # Get latest release info for this pipeline
                latest_release = nfcore_latest.get(pipeline_name)

                if not latest_release or not latest_release.get('tag_sha'):
                    logger.debug(f"⚠️  No latest release info for {pipeline_name}, skipping")
                    unmatched_count += len(wfs)
                    continue

                expected_commit = latest_release['tag_sha']
                expected_version = latest_release['tag_name']

                # Try to find a workflow with matching commit ID
                matched_wf = None
                for wf in wfs:
                    commit_id = wf.get('workflow', {}).get('commitId', '')

                    # Match commit ID (can be full SHA or shortened)
                    if commit_id and (commit_id == expected_commit or expected_commit.startswith(commit_id) or commit_id.startswith(expected_commit)):
                        matched_wf = wf
                        matched_count += 1
                        logger.info(f"✅ Matched {pipeline_name}: commit {commit_id[:8]} = release {expected_version} ({expected_commit[:8]})")
                        break

                if matched_wf:
                    latest_by_repo[repo] = matched_wf
                else:
                    logger.debug(f"⚠️  No workflow found for {pipeline_name} matching latest release {expected_version} (commit: {expected_commit[:8]})")
                    unmatched_count += len(wfs)

            filtered = list(latest_by_repo.values())

            logger.info(f"📊 Commit matching results: {matched_count} matched, {unmatched_count} unmatched")

        if not filtered:
            logger.info("ℹ️  No valid workflows found after filtering by latest releases")
            return

        print(f"{Colors.GREEN}✅ Found {len(filtered)} workflows to process{Colors.RESET}\n")

        # Debug: Log the structure of the first workflow to understand available metrics
        if filtered and len(filtered) > 0:
            logger.debug(f"🔍 DEBUG - First workflow structure: {json.dumps(filtered[0], indent=2)}")
            logger.debug(f"🔍 DEBUG - First workflow keys: {list(filtered[0].get('workflow', {}).keys())}")

        # Create the workflows info directory if it doesn't exist
        info_dir = os.path.join(args.output_dir, 'workflow_info')
        os.makedirs(info_dir, exist_ok=True)

        # Use a fixed filename for the CSV
        csv_filename = os.path.join(info_dir, 'all_workflows_info.csv')

        # Check if output files exist and ask for confirmation
        files_to_check = [csv_filename]
        if args.fetch_optimized_config:
            optimized_dir = os.path.join(args.output_dir, 'optimized_configs')
            if os.path.isdir(optimized_dir) and os.listdir(optimized_dir):
                files_to_check.append(optimized_dir)
        if args.fetch_task_metrics:
            task_metrics_dir = os.path.join(args.output_dir, 'task_metrics')
            if os.path.isdir(task_metrics_dir) and os.listdir(task_metrics_dir):
                files_to_check.append(task_metrics_dir)

        existing_files = [f for f in files_to_check if os.path.exists(f)]

        if existing_files:
            print(f"{Colors.YELLOW}⚠️  Warning: The following output files/directories already exist:{Colors.RESET}")
            for f in existing_files:
                if os.path.isdir(f):
                    file_count = len([name for name in os.listdir(f) if os.path.isfile(os.path.join(f, name))])
                    print(f"  📁 {f} ({file_count} files)")
                else:
                    print(f"  📄 {f}")
            print()

            # Ask user for confirmation
            response = input(f"{Colors.BOLD}Do you want to overwrite these files? (yes/no): {Colors.RESET}").strip().lower()
            if response not in ['yes', 'y']:
                print(f"{Colors.RED}❌ Operation cancelled by user{Colors.RESET}\n")
                return
            print(f"{Colors.GREEN}✅ Proceeding with overwrite...{Colors.RESET}\n")

            # Clear existing directories if they exist
            if args.fetch_optimized_config:
                optimized_dir = os.path.join(args.output_dir, 'optimized_configs')
                if os.path.isdir(optimized_dir):
                    shutil.rmtree(optimized_dir)
                    logger.info(f"🗑️  Cleared directory: {optimized_dir}")

            if args.fetch_task_metrics:
                task_metrics_dir = os.path.join(args.output_dir, 'task_metrics')
                if os.path.isdir(task_metrics_dir):
                    shutil.rmtree(task_metrics_dir)
                    logger.info(f"🗑️  Cleared directory: {task_metrics_dir}")

        # Define CSV headers
        headers = [
            'Workflow ID', 'Repository', 'Revision', 'Release Tag', 'Run Name', 'Workspace ID',
            'Commit ID', 'Profile', 'Submit Time', 'Duration (ms)',
            'CPU Efficiency (%)', 'Memory Efficiency (%)'
        ]

        # Write to CSV file in write mode (overwrite)
        with open(csv_filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            for wf in filtered:
                nested = wf.get('workflow', {})
                wf_id = nested.get('id', '')
                workspace = args.workspace_id if args.workspace_id else nested.get('workspaceId', '')
                repo = nested.get('repository', '')
                pipeline_name = repo.split('/')[-1] if repo else ''
                commit_id = nested.get('commitId', '')

                # Get runtime metrics (duration, CPU efficiency, memory efficiency)
                duration_ms, cpu_efficiency, memory_efficiency = get_workflow_runtime_metrics(
                    wf, client, wf_id, workspace
                )

                # Try to match commit ID with nf-core release to get the release tag
                release_tag = ''
                if nfcore_latest and pipeline_name:
                    latest_release = nfcore_latest.get(pipeline_name, {})
                    expected_commit = latest_release.get('tag_sha', '')
                    if commit_id and expected_commit and (commit_id == expected_commit or expected_commit.startswith(commit_id) or commit_id.startswith(expected_commit)):
                        release_tag = latest_release.get('tag_name', '')

                # Format efficiency values as percentages with 2 decimal places, or empty string if None
                cpu_eff_str = f"{cpu_efficiency:.2f}" if cpu_efficiency is not None else ''
                mem_eff_str = f"{memory_efficiency:.2f}" if memory_efficiency is not None else ''
                duration_str = str(duration_ms) if duration_ms is not None else ''

                # Handle revision - replace None or empty with 'dev'
                revision_str = str(nested.get('revision', ''))
                if not revision_str or revision_str == 'None':
                    revision_str = 'dev'

                row = [
                    wf_id,
                    repo,
                    revision_str,
                    release_tag,
                    nested.get('runName', '') or nested.get('run_name', '') or nested.get('name', ''),
                    workspace,
                    commit_id,
                    nested.get('profile', ''),
                    nested.get('submit', ''),
                    duration_str,
                    cpu_eff_str,
                    mem_eff_str
                ]
                writer.writerow(row)

        logger.info(f"💾 Workflow information written to {csv_filename} ({len(filtered)} workflows)")

        # Print formatted table via logger
        print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
        profile_display = args.profile if ',' not in args.profile else f"[{args.profile}]"
        print(f"{Colors.BOLD}{Colors.YELLOW}📊 Filtered Workflows (profile={profile_display}, latest releases):{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*80}{Colors.RESET}")
        logger.info("%-36s %-30s %-15s %-15s %-40s %-20s",
                   "ID", "REPOSITORY", "RELEASE TAG", "REVISION", "COMMIT ID", "SUBMIT TIME")

        for wf in filtered:
            nested = wf.get('workflow', {})
            repo = nested.get('repository', '')
            pipeline_name = repo.split('/')[-1] if repo else ''
            commit_id = nested.get('commitId', '')

            # Get release tag
            release_tag = ''
            if nfcore_latest and pipeline_name:
                latest_release = nfcore_latest.get(pipeline_name, {})
                expected_commit = latest_release.get('tag_sha', '')
                if commit_id and expected_commit and (commit_id == expected_commit or expected_commit.startswith(commit_id) or commit_id.startswith(expected_commit)):
                    release_tag = latest_release.get('tag_name', '')

            # Handle revision display - replace None or empty with 'dev'
            revision_display = str(nested.get('revision', ''))
            if not revision_display or revision_display == 'None':
                revision_display = 'dev'

            logger.info("%-36s %-30s %-15s %-15s %-40s %-20s",
                nested.get('id', ''),
                repo,
                release_tag,
                revision_display,
                commit_id,
                nested.get('submit', '')
            )
        
        # FETCH OPTIMIZED CONFIGURATION AND/OR TASK METRICS FOR EACH WORKFLOW
        print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.MAGENTA}🔄 Processing Workflows{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

        for idx, wf in enumerate(filtered, 1):
            nested = wf.get('workflow', {})
            wf_id = nested.get('id', '')
            if not wf_id:  # Skip if no workflow ID
                logger.warning("⚠️  Skipping workflow with no ID")
                continue

            workspace = args.workspace_id if args.workspace_id else nested.get('workspaceId', '')
            repo = nested.get('repository', '')
            # pipeline name is last segment of repo
            pipeline_name = repo.split('/')[-1] if repo else wf_id
            commit_id = nested.get('commitId', '')
            revision = str(nested.get('revision', ''))  # Convert to string and handle None
            # Replace None or empty string with 'dev'
            if not revision or revision == 'None':
                revision = 'dev'

            # Get release tag for file naming
            release_tag = ''
            if nfcore_latest and pipeline_name:
                latest_release = nfcore_latest.get(pipeline_name, {})
                expected_commit = latest_release.get('tag_sha', '')
                if commit_id and expected_commit and (commit_id == expected_commit or expected_commit.startswith(commit_id) or commit_id.startswith(expected_commit)):
                    release_tag = latest_release.get('tag_name', '')

            # Use release tag for file naming if available, otherwise fall back to revision
            version_string = release_tag if release_tag else revision

            print(f"{Colors.CYAN}[{idx}/{len(filtered)}]{Colors.RESET} {Colors.BOLD}{pipeline_name}{Colors.RESET} (version: {Colors.YELLOW}{version_string}{Colors.RESET})")
            logger.info(f"🔍 Processing workflow {wf_id} with workspace {workspace}")

            # Fetch optimized configuration if flag is enabled
            if args.fetch_optimized_config:
                optimized_dir = os.path.join(args.output_dir, 'optimized_configs')
                os.makedirs(optimized_dir, exist_ok=True)
                file_name = f"{pipeline_name}_{version_string}_optimized.config"
                file_path = os.path.join(optimized_dir, file_name)
                optimal_endpoint = f"{args.base_url}/workflow/{wf_id}/optimal"
                params = {
                    'workspaceId': workspace,
                    'optimizationTargets': 'cpus,memory'
                }
                logger.info("📥 Fetching optimized config for workflow %s", wf_id)
                try:
                    response_opt = requests.get(optimal_endpoint, headers=client.headers, params=params)
                    response_opt.raise_for_status()
                    config_str = response_opt.json().get('config', '')
                    # Write config to file
                    with open(file_path, 'w') as f:
                        f.write(config_str)
                    logger.info("✅ Saved optimized config to %s", file_path)
                except requests.exceptions.RequestException as e:
                    logger.error("❌ Failed to fetch optimized config for %s: %s", wf_id, e)
                except json.JSONDecodeError:
                    logger.error("❌ JSON parse error for optimal config for %s", wf_id)
                except IOError as e:
                    logger.error("❌ Failed to write optimized config to %s: %s", file_path, e)

            # Fetch task metrics if flag is enabled
            if args.fetch_task_metrics:
                task_metrics_dir = os.path.join(args.output_dir, 'task_metrics')
                fetch_and_store_task_metrics(
                    client=client,
                    workflow_id=wf_id,
                    workspace_id=workspace,
                    pipeline_name=pipeline_name,
                    revision=version_string,
                    output_dir=task_metrics_dir
                )

        # Print completion summary
        print(f"\n{Colors.GREEN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.GREEN}🎉 Processing Complete!{Colors.RESET}")
        print(f"{Colors.GREEN}{'='*80}{Colors.RESET}\n")

        print(f"{Colors.CYAN}📊 Summary:{Colors.RESET}")
        print(f"  {Colors.GREEN}✓{Colors.RESET} Processed {Colors.BOLD}{len(filtered)}{Colors.RESET} workflows")
        print(f"  {Colors.GREEN}✓{Colors.RESET} Workflow info saved to: {Colors.BOLD}{csv_filename}{Colors.RESET}")

        if args.fetch_optimized_config:
            optimized_path = os.path.join(args.output_dir, 'optimized_configs')
            print(f"  {Colors.GREEN}✓{Colors.RESET} Optimized configs saved to: {Colors.BOLD}{optimized_path}/{Colors.RESET}")
        if args.fetch_task_metrics:
            metrics_path = os.path.join(args.output_dir, 'task_metrics')
            print(f"  {Colors.GREEN}✓{Colors.RESET} Task metrics saved to: {Colors.BOLD}{metrics_path}/{Colors.RESET}")

        # Validate and adjust CPU configurations based on actual metrics
        # This runs when both -o and -m flags are enabled
        if args.fetch_optimized_config and args.fetch_task_metrics:
            print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
            print(f"{Colors.BOLD}{Colors.YELLOW}🔍 Validating CPU Allocations Against Actual Usage{Colors.RESET}")
            print(f"{Colors.CYAN}{'='*80}{Colors.RESET}\n")

            print(f"{Colors.YELLOW}ℹ️  This will check if processes are using more CPU than originally reserved.{Colors.RESET}")
            print(f"{Colors.YELLOW}ℹ️  If pcpu/100 > reserved_cpu (from metrics), config will be set to original reserved CPU.{Colors.RESET}")
            print(f"{Colors.YELLOW}ℹ️  Rationale: Over-subscribed processes should not be optimized further.{Colors.RESET}")
            print(f"{Colors.YELLOW}ℹ️  Configs in optimized_configs/ will be OVERWRITTEN.{Colors.RESET}\n")

            # Ask user for confirmation
            response = input(f"{Colors.BOLD}Do you want to proceed with CPU validation? (yes/no): {Colors.RESET}").strip().lower()
            if response not in ['yes', 'y']:
                print(f"{Colors.YELLOW}⏭️  Skipping CPU validation{Colors.RESET}\n")
            else:
                print(f"{Colors.GREEN}✅ Proceeding with CPU validation...{Colors.RESET}\n")

                optimized_dir = os.path.join(args.output_dir, 'optimized_configs')
                task_metrics_dir = os.path.join(args.output_dir, 'task_metrics')

                total_adjusted = 0
                total_unchanged = 0
                total_validated = 0

                for wf in filtered:
                    nested = wf.get('workflow', {})
                    repo = nested.get('repository', '')
                    pipeline_name = repo.split('/')[-1] if repo else ''
                    commit_id = nested.get('commitId', '')
                    revision = str(nested.get('revision', ''))
                    # Replace None or empty string with 'dev'
                    if not revision or revision == 'None':
                        revision = 'dev'

                    # Get release tag for file naming
                    release_tag = ''
                    if nfcore_latest and pipeline_name:
                        latest_release = nfcore_latest.get(pipeline_name, {})
                        expected_commit = latest_release.get('tag_sha', '')
                        if commit_id and expected_commit and (commit_id == expected_commit or expected_commit.startswith(commit_id) or commit_id.startswith(expected_commit)):
                            release_tag = latest_release.get('tag_name', '')

                    # Use release tag for file naming if available, otherwise fall back to revision
                    version_string = release_tag if release_tag else revision

                    if not pipeline_name:
                        continue

                    config_file = f"{pipeline_name}_{version_string}_optimized.config"
                    metrics_file = f"{pipeline_name}_{version_string}_tasks.csv"

                    config_path = os.path.join(optimized_dir, config_file)
                    metrics_path = os.path.join(task_metrics_dir, metrics_file)

                    if not os.path.exists(config_path):
                        logger.warning(f"⚠️  Skipping {pipeline_name}: config not found")
                        continue

                    if not os.path.exists(metrics_path):
                        logger.warning(f"⚠️  Skipping {pipeline_name}: metrics not found")
                        continue

                    print(f"{Colors.CYAN}🔍 Validating {pipeline_name} (version: {version_string}){Colors.RESET}")

                    try:
                        summary = validate_and_adjust_cpu_config(
                            config_path=config_path,
                            metrics_path=metrics_path,
                            pipeline_name=pipeline_name
                        )

                        total_adjusted += summary['adjusted']
                        total_unchanged += summary['no_change']
                        total_validated += 1

                        if summary['adjusted'] > 0:
                            print(f"  {Colors.GREEN}✓{Colors.RESET} Adjusted {summary['adjusted']} processes (set to original reserved CPUs)")
                            for adj in summary['adjustments'][:5]:  # Show first 5
                                process_short = adj['process'].split(':')[-1]
                                print(f"    • {process_short}: pcpu={adj['pcpu']:.1f}% (≈{adj['actual_usage']:.2f} cores) > {int(adj['reserved_cpus'])} cores reserved → set to {int(adj['reserved_cpus'])} CPUs")
                            if summary['adjusted'] > 5:
                                print(f"    ... and {summary['adjusted'] - 5} more")
                        else:
                            print(f"  {Colors.GRAY}• No adjustments needed{Colors.RESET}")

                    except Exception as e:
                        logger.error(f"❌ Error validating {pipeline_name}: {e}")

                print(f"\n{Colors.GREEN}{'='*80}{Colors.RESET}")
                print(f"{Colors.BOLD}{Colors.GREEN}✅ CPU Validation Complete!{Colors.RESET}")
                print(f"{Colors.GREEN}{'='*80}{Colors.RESET}\n")
                print(f"{Colors.CYAN}📊 Validation Summary:{Colors.RESET}")
                print(f"  {Colors.GREEN}✓{Colors.RESET} Total pipelines validated: {Colors.BOLD}{total_validated}{Colors.RESET}")
                print(f"  {Colors.GREEN}✓{Colors.RESET} Total processes adjusted: {Colors.BOLD}{total_adjusted}{Colors.RESET}")
                print(f"  {Colors.GRAY}•{Colors.RESET} Processes unchanged: {Colors.BOLD}{total_unchanged}{Colors.RESET}")
                print(f"  {Colors.GREEN}✓{Colors.RESET} Configs overwritten in: {Colors.BOLD}{optimized_dir}/{Colors.RESET}\n")

        print(f"\n{Colors.MAGENTA}✨ All done! Have a great day! ✨{Colors.RESET}\n")

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Error making API request: {e}")
        print(f"\n{Colors.RED}❌ Error: API request failed. Check your connection and token.{Colors.RESET}\n")
    except json.JSONDecodeError as e:
        logger.error(f"❌ Error parsing JSON response: {e}")
        print(f"\n{Colors.RED}❌ Error: Failed to parse API response.{Colors.RESET}\n")
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        print(f"\n{Colors.RED}❌ Unexpected error occurred. See log for details.{Colors.RESET}\n")
        raise  # Add this to see the full traceback during development

if __name__ == "__main__":
    main() 
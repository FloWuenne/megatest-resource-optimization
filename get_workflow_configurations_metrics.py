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
        "-u", "--base-url",
        default="https://api.cloud.seqera.io",
        help="Base URL for the Tower API"
    )
    
    parser.add_argument(
        "-p", "--max-pages",
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
        
        # Filter workflows by nested workflow.profile containing 'test_full'
        workflows = response_data.get('workflows', [])
        if not workflows:
            logger.info("ℹ️  No workflows found matching the criteria")
            return

        filtered = []
        for wf in workflows:
            nested = wf.get('workflow', {})
            # Extract profile and status from nested workflow
            profile = nested.get('profile', '') or ''
            # status field might be a string or dict
            raw_status = nested.get('status', '')
            status_val = raw_status if isinstance(raw_status, str) else raw_status.get('status', '')
            # Only include workflows with profile containing 'test_full' and status 'SUCCEEDED'
            if 'test_full' in profile and status_val.upper() == 'SUCCEEDED':
                filtered.append(wf)

        if not filtered:
            logger.info("ℹ️  No workflows found with profile 'test_full' and status 'SUCCEEDED'")
            return

        # For each repository, choose numeric revision if present, otherwise dev
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
                rev_str = str(wf.get('workflow', {}).get('revision', ''))  # Convert to string and handle None
                if not rev_str:  # Skip empty revisions
                    continue
                if rev_str.lower() == 'dev':
                    dev_revs.append(wf)
                else:
                    try:
                        rev_int = int(rev_str)
                        numeric_revs.append((rev_int, wf))
                    except ValueError:
                        # skip non-numeric, non-dev revisions
                        continue
            
            if numeric_revs:
                # pick the entry with the highest numeric revision
                latest_wf = max(numeric_revs, key=lambda x: x[0])[1]
            elif dev_revs:
                # if only dev exists, keep the dev run
                latest_wf = dev_revs[0]
            elif wfs:  # Fallback only if we have any workflows
                # fallback to first available
                latest_wf = wfs[0]
            else:
                continue  # Skip if no valid workflows for this repo
                
            latest_by_repo[repo] = latest_wf

        filtered = list(latest_by_repo.values())

        if not filtered:
            logger.info("ℹ️  No valid workflows found after filtering by revision")
            return

        print(f"{Colors.GREEN}✅ Found {len(filtered)} workflows to process{Colors.RESET}\n")

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
            'Workflow ID', 'Repository', 'Revision', 'Run Name', 'Workspace ID',
            'Commit ID', 'Profile', 'Submit Time'
        ]

        # Write to CSV file in write mode (overwrite)
        with open(csv_filename, 'w', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(headers)

            for wf in filtered:
                nested = wf.get('workflow', {})
                wf_id = nested.get('id', '')

                row = [
                    wf_id,
                    nested.get('repository', ''),
                    str(nested.get('revision', '')),
                    nested.get('runName', '') or nested.get('run_name', '') or nested.get('name', ''),
                    args.workspace_id if args.workspace_id else nested.get('workspaceId', ''),
                    nested.get('commitId', ''),
                    nested.get('profile', ''),
                    nested.get('submit', '')
                ]
                writer.writerow(row)

        logger.info(f"💾 Workflow information written to {csv_filename} ({len(filtered)} workflows)")

        # Print formatted table via logger
        print(f"\n{Colors.CYAN}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.YELLOW}📊 Filtered Workflows (profile=test_full):{Colors.RESET}")
        print(f"{Colors.CYAN}{'='*80}{Colors.RESET}")
        logger.info("%-36s %-30s %-10s %-20s %-20s %-40s %-20s %-20s",
                   "ID", "REPOSITORY", "REVISION", "RUN NAME", "WORKSPACE ID",
                   "COMMIT ID", "PROFILE", "SUBMIT TIME")

        for wf in filtered:
            nested = wf.get('workflow', {})
            logger.info("%-36s %-30s %-10s %-20s %-20s %-40s %-20s %-20s",
                nested.get('id', ''),
                nested.get('repository', ''),
                str(nested.get('revision', '')),
                nested.get('runName', '') or nested.get('run_name', '') or nested.get('name', ''),
                args.workspace_id if args.workspace_id else nested.get('workspaceId', ''),
                nested.get('commitId', ''),
                nested.get('profile', ''),
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
            revision = str(nested.get('revision', ''))  # Convert to string and handle None

            print(f"{Colors.CYAN}[{idx}/{len(filtered)}]{Colors.RESET} {Colors.BOLD}{pipeline_name}{Colors.RESET} (revision: {Colors.YELLOW}{revision}{Colors.RESET})")
            logger.info(f"🔍 Processing workflow {wf_id} with workspace {workspace}")

            # Fetch optimized configuration if flag is enabled
            if args.fetch_optimized_config:
                optimized_dir = os.path.join(args.output_dir, 'optimized_configs')
                os.makedirs(optimized_dir, exist_ok=True)
                file_name = f"{pipeline_name}_{revision}_optimized.config"
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
                    revision=revision,
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
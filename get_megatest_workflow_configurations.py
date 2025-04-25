#!/usr/bin/env python3

import requests
import json
from typing import Optional
import os
from datetime import datetime, timedelta
import argparse
import logging
import csv

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
            
        all_workflows = []
        page = 1
        
        while True:
            try:
                logger.info(f"Fetching page {page} (offset: {params['offset']})")
                response = requests.get(endpoint, headers=self.headers, params=params)
                response.raise_for_status()
                data = response.json()
                
                # Handle both list and dict response formats
                workflows = data.get('workflows', data if isinstance(data, list) else [])
                all_workflows.extend(workflows)
                
                # Check if we've reached the end of the data
                if len(workflows) < items_per_page:
                    break
                    
                # Check if we've reached max_pages
                if max_pages and page >= max_pages:
                    logger.info(f"Reached maximum number of pages ({max_pages})")
                    break
                
                # Update offset for next page
                params['offset'] += items_per_page
                page += 1
                
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed on page {page}: {str(e)}")
                break
                
        return {'workflows': all_workflows}

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
    
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Get access token from environment variable
    access_token = os.getenv('TOWER_ACCESS_TOKEN')
    if not access_token:
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
            logger.info("No workflows found matching the criteria")
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
            logger.info("No workflows found with profile 'test_full' and status 'SUCCEEDED'")
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
            logger.info("No valid workflows found after filtering by revision")
            return

        # Create the workflows info directory if it doesn't exist
        info_dir = 'workflow_info'
        os.makedirs(info_dir, exist_ok=True)
        
        # Use a fixed filename for the CSV
        csv_filename = os.path.join(info_dir, 'all_workflows_info.csv')
        
        # Define CSV headers
        headers = [
            'Workflow ID', 'Repository', 'Revision', 'Run Name', 'Workspace ID',
            'Commit ID', 'Profile', 'Submit Time'
        ]
        
        # Check if file exists to determine if we need to write headers
        file_exists = os.path.isfile(csv_filename)
        
        # Write to CSV file in append mode
        with open(csv_filename, 'a', newline='') as csvfile:
            writer = csv.writer(csvfile)
            
            # Write headers only if file is new
            if not file_exists:
                writer.writerow(headers)
            
            for wf in filtered:
                nested = wf.get('workflow', {})
                row = [
                    nested.get('id', ''),
                    nested.get('repository', ''),
                    str(nested.get('revision', '')),
                    nested.get('runName', '') or nested.get('run_name', '') or nested.get('name', ''),
                    nested.get('workspaceId', args.workspace_id or ''),
                    nested.get('commitId', ''),
                    nested.get('profile', ''),
                    nested.get('submit', '')
                ]
                writer.writerow(row)
        
        logger.info(f"Workflow information appended to {csv_filename}")

        # Print formatted table via logger
        logger.info("Filtered Workflows (profile=test_full):")
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
                nested.get('workspaceId', args.workspace_id or ''),
                nested.get('commitId', ''),
                nested.get('profile', ''),
                nested.get('submit', '')
            )
        
        # FETCH OPTIMIZED CONFIGURATION FOR EACH WORKFLOW
        optimized_dir = 'optimized_configs'
        os.makedirs(optimized_dir, exist_ok=True)
        for wf in filtered:
            nested = wf.get('workflow', {})
            wf_id = nested.get('id', '')
            if not wf_id:  # Skip if no workflow ID
                logger.warning("Skipping workflow with no ID")
                continue
                
            workspace = nested.get('workspaceId', args.workspace_id or '')
            repo = nested.get('repository', '')
            # pipeline name is last segment of repo
            pipeline_name = repo.split('/')[-1] if repo else wf_id
            revision = str(nested.get('revision', ''))  # Convert to string and handle None
            file_name = f"{pipeline_name}_{revision}_optimized.config"
            file_path = os.path.join(optimized_dir, file_name)
            optimal_endpoint = f"{args.base_url}/workflow/{wf_id}/optimal"
            params = {
                'workspaceId': workspace,
                'optimizationTargets': 'cpus,memory'
            }
            logger.info("Fetching optimized config for workflow %s", wf_id)
            try:
                response_opt = requests.get(optimal_endpoint, headers=client.headers, params=params)
                response_opt.raise_for_status()
            except requests.exceptions.RequestException as e:
                logger.error("Failed to fetch optimized config for %s: %s", wf_id, e)
                continue
            try:
                config_str = response_opt.json().get('config', '')
            except json.JSONDecodeError:
                logger.error("JSON parse error for optimal config for %s", wf_id)
                continue
            # Write config to file
            try:
                with open(file_path, 'w') as f:
                    f.write(config_str)
                logger.info("Saved optimized config to %s", file_path)
            except IOError as e:
                logger.error("Failed to write optimized config to %s: %s", file_path, e)
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Error making API request: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing JSON response: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise  # Add this to see the full traceback during development

if __name__ == "__main__":
    main() 
"""
Scheduler for periodic processing of papers from data sources.
This script is designed to be run as a cron job.
"""

import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List
import pandas as pd

from utils.database import (
    get_all_scheduled_jobs,
    get_data_source,
    update_scheduled_job_run_time,
    record_scheduled_job_run,
    update_scheduled_job_run,
    get_column_mapping_dict
)
from utils.google_sheets import load_sheet_data
from utils.multi_source_pipeline import process_multi_source_pipeline


def calculate_next_run(schedule_type: str, schedule_config: Dict, current_time: datetime) -> datetime:
    """Calculate the next run time based on schedule type."""
    
    if schedule_type == 'hourly':
        return current_time + timedelta(hours=1)
    
    elif schedule_type == 'daily':
        hour = schedule_config.get('hour', 0)
        next_run = current_time.replace(hour=hour, minute=0, second=0, microsecond=0)
        if next_run <= current_time:
            next_run += timedelta(days=1)
        return next_run
    
    elif schedule_type == 'weekly':
        day_of_week = schedule_config.get('day_of_week', 0)
        hour = schedule_config.get('hour', 0)
        days_ahead = day_of_week - current_time.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        next_run = current_time + timedelta(days=days_ahead)
        next_run = next_run.replace(hour=hour, minute=0, second=0, microsecond=0)
        return next_run
    
    elif schedule_type == 'interval':
        interval_hours = schedule_config.get('interval_hours', 24)
        return current_time + timedelta(hours=interval_hours)
    
    else:
        return current_time + timedelta(days=1)


def get_new_papers_since_last_run(
    source_id: int,
    sheet_data: pd.DataFrame,
    last_processed_row: int,
    max_papers_per_run: int = 100
) -> List[int]:
    """Get indices of new papers since last run."""
    
    total_rows = len(sheet_data)
    
    if last_processed_row >= total_rows:
        return []
    
    start_row = last_processed_row
    end_row = min(start_row + max_papers_per_run, total_rows)
    
    return list(range(start_row, end_row))


def run_scheduled_job(scheduled_job: Dict) -> Dict:
    """Run a single scheduled job."""
    
    job_id = scheduled_job['id']
    source_id = scheduled_job['source_id']
    
    print(f"Running scheduled job: {scheduled_job['job_name']} (ID: {job_id})")
    
    source_info = get_data_source(source_id)
    if not source_info:
        return {
            'status': 'failed',
            'error': f'Data source {source_id} not found'
        }
    
    if not source_info['active']:
        return {
            'status': 'skipped',
            'error': 'Data source is inactive'
        }
    
    try:
        print(f"Loading sheet data from: {source_info['sheet_url']}")
        
        google_creds_path = os.getenv('GOOGLE_CREDENTIALS_PATH')
        if not google_creds_path or not os.path.exists(google_creds_path):
            return {
                'status': 'failed',
                'error': 'Google credentials not configured'
            }
        
        with open(google_creds_path, 'r') as f:
            import json
            google_credentials = json.load(f)
        
        sheet_data = load_sheet_data(
            source_info['sheet_url'],
            source_info['sheet_tab_name'],
            google_credentials
        )
        
        total_rows = len(sheet_data)
        last_processed = source_info.get('last_processed_row', 0)
        
        schedule_config = scheduled_job.get('schedule_config', {})
        max_papers = schedule_config.get('max_papers_per_run', 100)
        
        new_indices = get_new_papers_since_last_run(
            source_id,
            sheet_data,
            last_processed,
            max_papers
        )
        
        if not new_indices:
            print(f"No new papers found for source {source_info['name']}")
            return {
                'status': 'completed',
                'papers_found': 0,
                'papers_processed': 0,
                'papers_skipped_duplicate': 0,
                'papers_failed': 0
            }
        
        print(f"Found {len(new_indices)} new papers to process")
        
        source_configs = [{
            'source_id': source_id,
            'data': sheet_data,
            'selected_indices': new_indices
        }]
        
        config = {
            'llama_api_key': os.getenv('LLAMA_CLOUD_API_KEY'),
            'pinecone_api_key': os.getenv('PINECONE_API_KEY'),
            'openai_api_key': os.getenv('OPENAI_API_KEY'),
            'google_credentials': google_credentials,
            'parsing_mode': schedule_config.get('parsing_mode', 'auto'),
            'result_type': schedule_config.get('result_type', 'markdown'),
            'language': schedule_config.get('language', 'en'),
            'use_vendor_multimodal': schedule_config.get('use_vendor_multimodal', True),
            'page_separator': '\\n---\\n',
            'chunking_strategy': schedule_config.get('chunking_strategy', 'Token-based'),
            'chunk_size': schedule_config.get('chunk_size', 512),
            'chunk_overlap': schedule_config.get('chunk_overlap', 50),
            'semantic_buffer_size': schedule_config.get('semantic_buffer_size', 1),
            'embedding_model': schedule_config.get('embedding_model', 'text-embedding-3-small'),
            'embedding_dimension': schedule_config.get('embedding_dimension', 1536),
            'index_name': schedule_config.get('index_name', 'pdf-embeddings'),
            'dedup_layer1': schedule_config.get('dedup_layer1', True),
            'dedup_layer2': schedule_config.get('dedup_layer2', True)
        }
        
        print("Starting processing pipeline...")
        
        results = process_multi_source_pipeline(
            source_configs=source_configs,
            config=config,
            progress_callback=None,
            preview_mode=False
        )
        
        duplicates_skipped = sum(
            1 for d in results.get('details', [])
            if d.get('status') == 'skipped_duplicate'
        )
        
        failures = sum(
            1 for d in results.get('details', [])
            if d.get('status') == 'error'
        )
        
        return {
            'status': 'completed',
            'processing_job_id': results.get('job_id'),
            'papers_found': len(new_indices),
            'papers_processed': results.get('total_pdfs', 0),
            'papers_skipped_duplicate': duplicates_skipped,
            'papers_failed': failures
        }
        
    except Exception as e:
        print(f"Error running scheduled job: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'status': 'failed',
            'error': str(e)
        }


def run_scheduler():
    """Main scheduler function - runs all due scheduled jobs."""
    
    print(f"Scheduler started at {datetime.now()}")
    
    scheduled_jobs = get_all_scheduled_jobs(enabled_only=True)
    
    if not scheduled_jobs:
        print("No enabled scheduled jobs found")
        return
    
    current_time = datetime.now()
    
    for job in scheduled_jobs:
        next_run = job.get('next_run_at')
        
        if next_run is None or (isinstance(next_run, datetime) and next_run <= current_time):
            print(f"\n{'='*60}")
            print(f"Processing scheduled job: {job['job_name']}")
            print(f"{'='*60}\n")
            
            run_id = record_scheduled_job_run(
                scheduled_job_id=job['id'],
                processing_job_id='',
                status='running'
            )
            
            try:
                result = run_scheduled_job(job)
                
                update_scheduled_job_run(
                    run_id=run_id,
                    status=result['status'],
                    papers_processed=result.get('papers_processed', 0),
                    papers_skipped_duplicate=result.get('papers_skipped_duplicate', 0),
                    papers_failed=result.get('papers_failed', 0),
                    error_message=result.get('error')
                )
                
                print(f"Job completed: {result['status']}")
                print(f"Papers processed: {result.get('papers_processed', 0)}")
                print(f"Duplicates skipped: {result.get('papers_skipped_duplicate', 0)}")
                
            except Exception as e:
                print(f"Error: {str(e)}")
                update_scheduled_job_run(
                    run_id=run_id,
                    status='failed',
                    error_message=str(e)
                )
            
            next_run_time = calculate_next_run(
                job['schedule_type'],
                job.get('schedule_config', {}),
                datetime.now()
            )
            
            update_scheduled_job_run_time(
                job_id=job['id'],
                next_run_at=next_run_time,
                last_run_at=datetime.now()
            )
            
            print(f"Next run scheduled for: {next_run_time}")
    
    print(f"\nScheduler completed at {datetime.now()}")


if __name__ == '__main__':
    run_scheduler()

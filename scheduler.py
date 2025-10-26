"""
Scheduler for periodic processing of papers from data sources.
This script is designed to be run as a cron job.

Improvements (October 2025):
- Added distributed locking to prevent concurrent runs
- Fixed weekly scheduling bug
- Replaced print() with proper logging
- Added input validation
- Added retry logic for transient failures
- Extracted config builder
- Added monitoring hooks
"""

import os
import sys
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from contextlib import contextmanager
from dataclasses import dataclass
import pandas as pd

from utils.database import (
    get_all_scheduled_jobs,
    get_data_source,
    update_scheduled_job_run_time,
    record_scheduled_job_run,
    update_scheduled_job_run,
    get_column_mapping_dict,
    get_product,
    get_product_api_keys
)
from utils.google_sheets import load_sheet_data
from utils.multi_source_pipeline import process_multi_source_pipeline


# ============================================
# CONSTANTS
# ============================================

DEFAULT_MAX_PAPERS_PER_RUN = 100
DEFAULT_RETRY_ATTEMPTS = 3
SCHEDULER_LOCK_TIMEOUT = 3600  # 1 hour in seconds
GOOGLE_CREDS_ENV_VAR = 'GOOGLE_CREDENTIALS_PATH'

# Retry backoff settings
RETRY_INITIAL_WAIT = 2  # seconds
RETRY_BACKOFF_MULTIPLIER = 2
RETRY_MAX_WAIT = 60  # seconds


# ============================================
# LOGGING SETUP
# ============================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


# ============================================
# MONITORING & METRICS
# ============================================

@dataclass
class JobMetrics:
    """Metrics for a scheduled job run."""
    job_id: int
    job_name: str
    start_time: datetime
    end_time: datetime
    duration_seconds: float
    papers_found: int
    papers_processed: int
    papers_skipped: int
    papers_failed: int
    status: str
    error_message: Optional[str] = None


def emit_metrics(metrics: JobMetrics):
    """Send metrics to monitoring system."""
    logger.info(
        f"JOB_METRICS: {metrics.job_name} | "
        f"Duration: {metrics.duration_seconds:.2f}s | "
        f"Found: {metrics.papers_found} | "
        f"Processed: {metrics.papers_processed} | "
        f"Skipped: {metrics.papers_skipped} | "
        f"Failed: {metrics.papers_failed} | "
        f"Status: {metrics.status}"
    )


# ============================================
# DISTRIBUTED LOCKING
# ============================================

@contextmanager
def scheduler_lock(job_id: int, timeout: int = SCHEDULER_LOCK_TIMEOUT):
    """
    Distributed lock to prevent concurrent execution of same job.
    Uses Redis if available, falls back to local file lock.
    """
    lock_acquired = False
    redis_client = None
    lock_key = f"scheduler_lock:job_{job_id}"
    
    try:
        # Try Redis lock first
        import redis
        redis_host = os.getenv('REDIS_HOST')
        redis_port = os.getenv('REDIS_PORT')
        redis_password = os.getenv('REDIS_PASSWORD')
        
        if redis_host:
            redis_client = redis.Redis(
                host=redis_host,
                port=int(redis_port) if redis_port else 6379,
                password=redis_password,
                decode_responses=True,
                ssl=os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'
            )
            
            lock_acquired = redis_client.set(
                lock_key, str(os.getpid()), nx=True, ex=timeout
            )
            
            if not lock_acquired:
                raise RuntimeError(f"Job {job_id} is already running (Redis lock exists)")
            
            logger.info(f"Acquired Redis lock for job {job_id}")
    
    except ImportError:
        logger.warning("Redis not available, using file-based locking")
        redis_client = None
    except Exception as e:
        logger.warning(f"Redis lock failed, using file-based locking: {e}")
        redis_client = None
    
    # Fallback to file-based lock
    if not redis_client:
        lock_file = f"/tmp/scheduler_lock_{job_id}.lock"
        
        if os.path.exists(lock_file):
            lock_age = time.time() - os.path.getmtime(lock_file)
            if lock_age < timeout:
                raise RuntimeError(f"Job {job_id} is already running (file lock exists)")
            else:
                logger.warning(f"Removing stale lock file (age: {lock_age:.0f}s)")
                os.remove(lock_file)
        
        with open(lock_file, 'w') as f:
            f.write(str(os.getpid()))
        lock_acquired = True
        logger.info(f"Acquired file lock for job {job_id}")
    
    try:
        yield
    finally:
        if redis_client and lock_acquired:
            redis_client.delete(lock_key)
            logger.info(f"Released Redis lock for job {job_id}")
        elif lock_acquired:
            lock_file = f"/tmp/scheduler_lock_{job_id}.lock"
            if os.path.exists(lock_file):
                os.remove(lock_file)
            logger.info(f"Released file lock for job {job_id}")


# ============================================
# VALIDATION
# ============================================

class ScheduleValidationError(ValueError):
    """Raised when schedule configuration is invalid."""
    pass


def validate_schedule_config(schedule_type: str, config: Dict) -> None:
    """Validate schedule configuration."""
    if schedule_type == 'daily':
        hour = config.get('hour', 0)
        if not isinstance(hour, int) or not (0 <= hour <= 23):
            raise ScheduleValidationError(f"Invalid hour for daily schedule: {hour}")
    
    elif schedule_type == 'weekly':
        day = config.get('day_of_week', 0)
        if not isinstance(day, int) or not (0 <= day <= 6):
            raise ScheduleValidationError(f"Invalid day_of_week: {day}")
        
        hour = config.get('hour', 0)
        if not isinstance(hour, int) or not (0 <= hour <= 23):
            raise ScheduleValidationError(f"Invalid hour: {hour}")
    
    elif schedule_type == 'interval':
        hours = config.get('interval_hours', 24)
        if not isinstance(hours, (int, float)) or hours <= 0:
            raise ScheduleValidationError(f"Invalid interval_hours: {hours}")
    
    max_papers = config.get('max_papers_per_run', DEFAULT_MAX_PAPERS_PER_RUN)
    if not isinstance(max_papers, int) or not (1 <= max_papers <= 10000):
        raise ScheduleValidationError(f"Invalid max_papers_per_run: {max_papers}")


# ============================================
# SCHEDULE CALCULATION
# ============================================

def calculate_next_run(schedule_type: str, schedule_config: Dict, current_time: datetime) -> datetime:
    """Calculate the next run time based on schedule type."""
    try:
        validate_schedule_config(schedule_type, schedule_config)
    except ScheduleValidationError as e:
        logger.error(f"Invalid schedule config: {e}")
        return current_time + timedelta(days=1)
    
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
        
        # FIXED: Changed from <= to < (bug fix)
        days_ahead = day_of_week - current_time.weekday()
        if days_ahead < 0:
            days_ahead += 7
        elif days_ahead == 0 and current_time.hour >= hour:
            days_ahead = 7  # Schedule for next week if already passed today
        
        next_run = current_time + timedelta(days=days_ahead)
        next_run = next_run.replace(hour=hour, minute=0, second=0, microsecond=0)
        return next_run
    
    elif schedule_type == 'interval':
        interval_hours = schedule_config.get('interval_hours', 24)
        return current_time + timedelta(hours=interval_hours)
    
    else:
        logger.warning(f"Unknown schedule type: {schedule_type}")
        return current_time + timedelta(days=1)


# ============================================
# CONFIGURATION BUILDER
# ============================================

def build_processing_config(
    source_info: Dict,
    schedule_config: Dict,
    google_credentials: Dict
) -> Dict:
    """Build processing configuration from multiple sources."""
    config = {
        'llama_api_key': os.getenv('LLAMA_CLOUD_API_KEY'),
        'pinecone_api_key': os.getenv('PINECONE_API_KEY'),
        'openai_api_key': os.getenv('OPENAI_API_KEY'),
        'google_credentials': google_credentials,
        'page_separator': '\\n---\\n',
        'parsing_mode': 'auto',
        'result_type': 'markdown',
        'language': 'en',
        'use_vendor_multimodal': True,
        'chunking_strategy': 'Token-based',
        'chunk_size': 512,
        'chunk_overlap': 50,
        'semantic_buffer_size': 1,
        'embedding_model': 'text-embedding-3-small',
        'embedding_dimension': 1536,
        'index_name': 'pdf-embeddings',
        'dedup_layer1': True,
        'dedup_layer2': True
    }
    
    # Apply schedule overrides
    schedule_overrides = {
        'parsing_mode', 'result_type', 'language', 'use_vendor_multimodal',
        'chunking_strategy', 'chunk_size', 'chunk_overlap', 'semantic_buffer_size',
        'embedding_model', 'embedding_dimension', 'index_name',
        'dedup_layer1', 'dedup_layer2'
    }
    
    for key in schedule_overrides:
        if key in schedule_config:
            config[key] = schedule_config[key]
    
    # Apply product-specific overrides
    if source_info.get('product_id'):
        product_info = get_product(source_info['product_id'])
        if product_info and product_info['active']:
            logger.info(f"Using product-specific settings for: {product_info['name']}")
            
            product_api_keys = get_product_api_keys(source_info['product_id'])
            
            if product_api_keys.get('LLAMA_CLOUD_API_KEY'):
                config['llama_api_key'] = product_api_keys['LLAMA_CLOUD_API_KEY']
                logger.info("  - Using product-specific LlamaParse API key")
            
            if product_api_keys.get('OPENAI_API_KEY'):
                config['openai_api_key'] = product_api_keys['OPENAI_API_KEY']
                logger.info("  - Using product-specific OpenAI API key")
            
            if product_api_keys.get('PINECONE_API_KEY'):
                config['pinecone_api_key'] = product_api_keys['PINECONE_API_KEY']
                logger.info("  - Using product-specific Pinecone API key")
            
            if product_api_keys.get('GOOGLE_CREDENTIALS'):
                config['google_credentials'] = product_api_keys['GOOGLE_CREDENTIALS']
                logger.info("  - Using product-specific Google credentials")
            
            config['index_name'] = product_info['pinecone_index']
            logger.info(f"  - Using product-specific Pinecone index: {product_info['pinecone_index']}")
            
            if product_info.get('default_chunking_strategy'):
                config['chunking_strategy'] = product_info['default_chunking_strategy']
            if product_info.get('default_chunk_size'):
                config['chunk_size'] = product_info['default_chunk_size']
            if product_info.get('default_embedding_model'):
                config['embedding_model'] = product_info['default_embedding_model']
            
            logger.info(f"  - Chunking: {config['chunking_strategy']} (size: {config['chunk_size']})")
            logger.info(f"  - Embedding model: {config['embedding_model']}")
    
    return config


# ============================================
# PAPER PROCESSING
# ============================================

def get_new_papers_since_last_run(
    source_id: int,
    sheet_data: pd.DataFrame,
    last_processed_row: int,
    max_papers_per_run: int = DEFAULT_MAX_PAPERS_PER_RUN
) -> List[int]:
    """Get indices of new papers since last run."""
    total_rows = len(sheet_data)
    
    if last_processed_row >= total_rows:
        logger.info(f"No new papers (last processed: {last_processed_row}, total: {total_rows})")
        return []
    
    start_row = last_processed_row
    end_row = min(start_row + max_papers_per_run, total_rows)
    
    new_papers = list(range(start_row, end_row))
    logger.info(f"Found {len(new_papers)} new papers (rows {start_row} to {end_row-1})")
    
    return new_papers


# ============================================
# JOB EXECUTION
# ============================================

class TransientError(Exception):
    """Exception for transient errors that should be retried."""
    pass


def run_scheduled_job_with_retry(
    scheduled_job: Dict,
    max_retries: int = DEFAULT_RETRY_ATTEMPTS
) -> Dict:
    """Run scheduled job with retry logic for transient failures."""
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return run_scheduled_job(scheduled_job)
        
        except TransientError as e:
            last_error = e
            
            if attempt == max_retries - 1:
                logger.error(f"Job failed after {max_retries} attempts: {e}")
                raise
            
            # Exponential backoff with cap
            wait_time = min(
                RETRY_INITIAL_WAIT * (RETRY_BACKOFF_MULTIPLIER ** attempt),
                RETRY_MAX_WAIT
            )
            
            logger.warning(
                f"Transient error on attempt {attempt + 1}/{max_retries}: {e}. "
                f"Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)
        
        except Exception as e:
            logger.error(f"Non-retryable error: {e}", exc_info=True)
            raise
    
    raise last_error if last_error else Exception("Unknown error in retry loop")


def run_scheduled_job(scheduled_job: Dict) -> Dict:
    """Run a single scheduled job."""
    job_id = scheduled_job['id']
    source_id = scheduled_job['source_id']
    
    logger.info(f"Running scheduled job: {scheduled_job['job_name']} (ID: {job_id})")
    
    source_info = get_data_source(source_id)
    if not source_info:
        return {'status': 'failed', 'error': f'Data source {source_id} not found'}
    
    if not source_info['active']:
        logger.info(f"Skipping inactive data source: {source_info['name']}")
        return {'status': 'skipped', 'error': 'Data source is inactive'}
    
    try:
        google_creds_path = os.getenv(GOOGLE_CREDS_ENV_VAR)
        if not google_creds_path or not os.path.exists(google_creds_path):
            raise Exception('Google credentials not configured')
        
        import json
        with open(google_creds_path, 'r') as f:
            google_credentials = json.load(f)
        
        logger.info(f"Loading sheet data from: {source_info['sheet_url']}")
        sheet_data = load_sheet_data(
            source_info['sheet_url'],
            source_info['sheet_tab_name'],
            google_credentials
        )
        
        total_rows = len(sheet_data)
        last_processed = source_info.get('last_processed_row', 0)
        
        schedule_config = scheduled_job.get('schedule_config', {})
        max_papers = schedule_config.get('max_papers_per_run', DEFAULT_MAX_PAPERS_PER_RUN)
        
        new_indices = get_new_papers_since_last_run(
            source_id, sheet_data, last_processed, max_papers
        )
        
        if not new_indices:
            logger.info(f"No new papers found for source {source_info['name']}")
            return {
                'status': 'completed',
                'papers_found': 0,
                'papers_processed': 0,
                'papers_skipped_duplicate': 0,
                'papers_failed': 0
            }
        
        logger.info(f"Processing {len(new_indices)} new papers")
        
        config = build_processing_config(source_info, schedule_config, google_credentials)
        
        source_configs = [{
            'source_id': source_id,
            'data': sheet_data,
            'selected_indices': new_indices
        }]
        
        logger.info("Starting processing pipeline...")
        results = process_multi_source_pipeline(
            source_configs=source_configs,
            config=config,
            progress_callback=None,
            preview_mode=False
        )
        
        details = results.get('details', [])
        duplicates_skipped = sum(1 for d in details if d.get('status') == 'skipped_duplicate')
        failures = sum(1 for d in details if d.get('status') == 'error')
        
        logger.info(
            f"Pipeline completed: "
            f"Processed={results.get('total_pdfs', 0)}, "
            f"Duplicates={duplicates_skipped}, "
            f"Failures={failures}"
        )
        
        return {
            'status': 'completed',
            'processing_job_id': results.get('job_id'),
            'papers_found': len(new_indices),
            'papers_processed': results.get('total_pdfs', 0),
            'papers_skipped_duplicate': duplicates_skipped,
            'papers_failed': failures
        }
        
    except (ConnectionError, TimeoutError) as e:
        raise TransientError(f"Transient failure: {e}") from e
    
    except Exception as e:
        logger.error(f"Error running scheduled job: {e}", exc_info=True)
        return {'status': 'failed', 'error': str(e)}


# ============================================
# MAIN SCHEDULER
# ============================================

def run_scheduler():
    """Main scheduler function - runs all due scheduled jobs."""
    logger.info("=" * 70)
    logger.info(f"Scheduler started at {datetime.now()}")
    logger.info("=" * 70)
    
    scheduled_jobs = get_all_scheduled_jobs(enabled_only=True)
    
    if not scheduled_jobs:
        logger.info("No enabled scheduled jobs found")
        return
    
    logger.info(f"Found {len(scheduled_jobs)} enabled scheduled jobs")
    
    current_time = datetime.now()
    jobs_run = 0
    
    for job in scheduled_jobs:
        next_run = job.get('next_run_at')
        
        if next_run is None or (isinstance(next_run, datetime) and next_run <= current_time):
            jobs_run += 1
            
            logger.info("")
            logger.info("=" * 70)
            logger.info(f"Processing scheduled job: {job['job_name']} (ID: {job['id']})")
            logger.info("=" * 70)
            
            run_id = record_scheduled_job_run(
                scheduled_job_id=job['id'],
                processing_job_id='',
                status='running'
            )
            
            start_time = datetime.now()
            result = None
            
            try:
                with scheduler_lock(job['id']):
                    result = run_scheduled_job_with_retry(job)
                
                end_time = datetime.now()
                
                update_scheduled_job_run(
                    run_id=run_id,
                    status=result['status'],
                    papers_processed=result.get('papers_processed', 0),
                    papers_skipped_duplicate=result.get('papers_skipped_duplicate', 0),
                    papers_failed=result.get('papers_failed', 0),
                    error_message=result.get('error')
                )
                
                metrics = JobMetrics(
                    job_id=job['id'],
                    job_name=job['job_name'],
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=(end_time - start_time).total_seconds(),
                    papers_found=result.get('papers_found', 0),
                    papers_processed=result.get('papers_processed', 0),
                    papers_skipped=result.get('papers_skipped_duplicate', 0),
                    papers_failed=result.get('papers_failed', 0),
                    status=result['status'],
                    error_message=result.get('error')
                )
                emit_metrics(metrics)
                
                logger.info(f"Job completed: {result['status']}")
                
            except RuntimeError as e:
                logger.warning(f"Skipping job (already running): {e}")
                update_scheduled_job_run(
                    run_id=run_id,
                    status='skipped',
                    error_message=str(e)
                )
                
            except Exception as e:
                end_time = datetime.now()
                logger.error(f"Job failed with error: {e}", exc_info=True)
                
                update_scheduled_job_run(
                    run_id=run_id,
                    status='failed',
                    error_message=str(e)
                )
                
                metrics = JobMetrics(
                    job_id=job['id'],
                    job_name=job['job_name'],
                    start_time=start_time,
                    end_time=end_time,
                    duration_seconds=(end_time - start_time).total_seconds(),
                    papers_found=0,
                    papers_processed=0,
                    papers_skipped=0,
                    papers_failed=0,
                    status='failed',
                    error_message=str(e)
                )
                emit_metrics(metrics)
            
            try:
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
                
                logger.info(f"Next run scheduled for: {next_run_time}")
                
            except Exception as e:
                logger.error(f"Error calculating next run time: {e}")
        else:
            logger.debug(f"Job '{job['job_name']}' not due yet (next run: {next_run})")
    
    logger.info("")
    logger.info("=" * 70)
    logger.info(f"Scheduler completed at {datetime.now()}")
    logger.info(f"Jobs run: {jobs_run}/{len(scheduled_jobs)}")
    logger.info("=" * 70)


# ============================================
# ENTRY POINT
# ============================================

if __name__ == '__main__':
    try:
        run_scheduler()
    except KeyboardInterrupt:
        logger.info("Scheduler interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Scheduler crashed: {e}", exc_info=True)
        sys.exit(1)

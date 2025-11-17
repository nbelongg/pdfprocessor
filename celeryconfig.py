"""
Celery configuration for background task processing.

This module configures Celery with Redis as broker/backend and sets up
task queues for PDF processing pipeline.

Improvements (October 2025):
- Added logging for Redis connection setup
- Extracted constants for task limits, worker settings, retry config
- Consistent with scheduler.py and tasks.py logging patterns
"""

import os
import logging
from celery import Celery
from kombu import Queue

# Initialize Sentry for error tracking in Celery workers
from utils.sentry_config import init_sentry
init_sentry()


# ============================================
# LOGGING SETUP
# ============================================

logger = logging.getLogger(__name__)


# ============================================
# CONSTANTS
# ============================================

# Task time limits (seconds)
TASK_HARD_TIME_LIMIT = 28800  # 8 hours - hard kill for hung tasks (increased for large batches)
TASK_SOFT_TIME_LIMIT = 28500  # 7h 55min - warning before hard kill

# Worker settings
WORKER_MAX_TASKS_PER_CHILD = 50  # Restart worker after N tasks (prevents memory leaks)
WORKER_PREFETCH_MULTIPLIER = 1   # Only fetch 1 task at a time (good for long-running tasks)

# Retry settings
TASK_DEFAULT_RETRY_DELAY = 60   # Wait 60 seconds before retry
TASK_MAX_RETRIES = 3             # Maximum 3 retry attempts

# Result settings
RESULT_EXPIRES = 86400  # 24 hours in seconds

# Broker settings
BROKER_CONNECTION_MAX_RETRIES = 10  # Max retry attempts for broker connection

# Default Redis settings
DEFAULT_REDIS_HOST = 'localhost'
DEFAULT_REDIS_PORT = '6379'
DEFAULT_REDIS_DB = '0'  # Default to database 0 for dev

# SSL parameters
SSL_CERT_REQS = 'required'


# ============================================
# REDIS URL BUILDER
# ============================================

def get_redis_url():
    """
    Get Redis connection URL from environment variables.
    
    Supports:
    - Upstash Redis (TLS): rediss://default:password@host:port
    - Local Redis: redis://host:port
    - Redis with password: redis://default:password@host:port
    
    Automatically detects production vs dev environment and uses separate Redis databases:
    - Production (.replit.app): Database 1
    - Development: Database 0
    
    Returns:
        str: Fully qualified Redis connection URL
    """
    import re
    
    redis_host_raw = os.getenv('REDIS_HOST', DEFAULT_REDIS_HOST)
    redis_port = os.getenv('REDIS_PORT', DEFAULT_REDIS_PORT)
    redis_password = os.getenv('REDIS_PASSWORD', '')
    redis_use_tls = os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'
    
    # Auto-detect environment for key prefixing (Upstash Redis only supports DB 0)
    # Check multiple environment indicators for production
    is_production = (
        os.getenv('REPLIT_DEPLOYMENT') == '1' or  # Replit deployment flag
        os.getenv('REPL_SLUG', '').endswith('.replit.app') or  # Production URL pattern
        'replit.app' in os.getenv('REPLIT_DOMAINS', '')  # Domain check
    )
    
    # Upstash Redis only supports database 0, so we use key prefixes for isolation
    redis_db = '0'  # Always use database 0 (Upstash limitation)
    
    # Set environment name for logging and key prefixing
    if is_production:
        env_name = 'PRODUCTION'
    else:
        env_name = 'DEVELOPMENT'
    
    logger.info(f"Configuring Redis connection (Environment: {env_name}, TLS: {redis_use_tls}, DB: {redis_db})")
    
    # Parse if REDIS_HOST contains a full connection string
    if 'redis://' in redis_host_raw or 'rediss://' in redis_host_raw:
        logger.debug("Parsing Redis connection string from REDIS_HOST")
        
        # Pattern matches: redis[s]://[default:]password@host:port
        match = re.search(
            r'redis(?:s)?://(?:default:)?([^@]+)@([^:]+):(\d+)',
            redis_host_raw
        )
        
        if match:
            redis_password = match.group(1)
            redis_host = match.group(2)
            redis_port = match.group(3)
            
            if 'rediss://' in redis_host_raw:
                redis_use_tls = True
            
            logger.info(f"Parsed Redis connection: {redis_host}:{redis_port} (TLS: {redis_use_tls})")
        else:
            logger.warning("Failed to parse Redis connection string, using localhost")
            redis_host = DEFAULT_REDIS_HOST
    else:
        redis_host = redis_host_raw
        logger.info(f"Using Redis host: {redis_host}:{redis_port}")
    
    # Build connection URL with database number for environment separation
    if redis_use_tls and redis_password:
        connection_url = (
            f"rediss://default:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
            f"?ssl_cert_reqs={SSL_CERT_REQS}"
        )
        logger.info(f"Built TLS Redis connection for {redis_host}:{redis_port} (DB: {redis_db})")
    elif redis_password:
        connection_url = f"redis://default:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        logger.info(f"Built authenticated Redis connection for {redis_host}:{redis_port} (DB: {redis_db})")
    else:
        connection_url = f"redis://{redis_host}:{redis_port}/{redis_db}"
        logger.info(f"Built Redis connection for {redis_host}:{redis_port} (DB: {redis_db})")
    
    return connection_url


# ============================================
# CELERY INITIALIZATION
# ============================================

# Detect environment for key prefixing
is_production = (
    os.getenv('REPLIT_DEPLOYMENT') == '1' or
    os.getenv('REPL_SLUG', '').endswith('.replit.app') or
    'replit.app' in os.getenv('REPLIT_DOMAINS', '')
)
env_prefix = 'prod' if is_production else 'dev'

redis_url = get_redis_url()

celery_app = Celery(
    'pdf_processor',
    broker=redis_url,
    backend=redis_url,
    include=['tasks', 'tasks_metadata']
)

# Set key prefix for environment isolation (since Upstash only supports DB 0)
logger.info(f"Setting Celery key prefix: '{env_prefix}' for environment isolation")


# ============================================
# CELERY CONFIGURATION
# ============================================

celery_app.conf.update(
    # Serialization
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    
    # Timezone
    timezone='UTC',
    enable_utc=True,
    
    # Broker settings
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=BROKER_CONNECTION_MAX_RETRIES,
    
    # Environment isolation via key prefixing (Upstash limitation workaround)
    broker_transport_options={
        'global_keyprefix': f'{env_prefix}_',  # Prefix all Redis keys with environment
        'visibility_timeout': 3600,  # 1 hour visibility timeout
    },
    result_backend_transport_options={
        'global_keyprefix': f'{env_prefix}_',  # Prefix result keys too
    },
    
    # Task acknowledgment (prevents message loss on worker crash)
    task_acks_late=True,
    
    # Worker settings
    worker_prefetch_multiplier=WORKER_PREFETCH_MULTIPLIER,  # Only fetch 1 task at a time
    worker_max_tasks_per_child=WORKER_MAX_TASKS_PER_CHILD,  # Restart after N tasks
    
    # Task time limits (prevents hung tasks)
    task_time_limit=TASK_HARD_TIME_LIMIT,      # Hard kill after 3 hours
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT, # Soft timeout at 2h 55min
    
    # Retry settings
    task_default_retry_delay=TASK_DEFAULT_RETRY_DELAY,
    task_max_retries=TASK_MAX_RETRIES,
    
    # Task routing (separate queues for different task types)
    task_routes={
        'tasks.process_pdf_task': {'queue': 'pdf_processing'},
        'tasks.process_batch_task': {'queue': 'batch_processing'},
        'tasks_metadata.update_metadata_task': {'queue': 'metadata_updates'},
        'tasks_metadata.update_metadata_batch_task': {'queue': 'metadata_updates'},
    },
    
    # Queue configuration
    task_queues=(
        Queue('pdf_processing', routing_key='pdf.#'),
        Queue('batch_processing', routing_key='batch.#'),
        Queue('metadata_updates', routing_key='metadata.#'),
    ),
    
    # Result backend settings
    result_expires=RESULT_EXPIRES,  # Results expire after 24 hours
)

logger.info("Celery app configured successfully")


# ============================================
# CELERY SIGNAL HANDLERS
# ============================================

from celery import signals


@signals.task_prerun.connect
def task_prerun_handler(sender=None, task_id=None, task=None, **kwargs):
    """
    Automatically update job status to 'running' when task starts execution.
    
    This signal fires when a task is about to run, ensuring status updates
    even if the task fails before reaching its own status update code.
    
    Args:
        sender: The task class
        task_id: Unique task identifier
        task: Task instance
        **kwargs: Additional signal parameters
    """
    from utils.db.jobs import update_celery_job_status, get_celery_job
    from utils.diagnostic_logger import (
        log_signal_handler_entry,
        log_signal_handler_db_attempt,
        log_signal_handler_success,
        log_signal_handler_failure,
        log_worker_task_received
    )
    
    try:
        log_signal_handler_entry('task_prerun', task_id)
        log_worker_task_received(task_id, task.name if task else 'unknown')
        
        # Check if this job exists in our tracking table
        logger.info(f"🔍 Attempting to fetch job from database: task_id={task_id}")
        job = get_celery_job(task_id)
        
        if job:
            logger.info(f"✅ Job found in database: status={job['status']}")
            
            if job['status'] == 'pending':
                log_signal_handler_db_attempt('task_prerun', task_id, 'running')
                logger.info(f"🔔 Signal: Task {task_id} starting, updating status to 'running'")
                update_celery_job_status(
                    task_id, 
                    'running',
                    progress_message='Task execution started via signal handler'
                )
                log_signal_handler_success('task_prerun', task_id)
            else:
                logger.debug(f"🔔 Signal: Task {task_id} already has status '{job['status']}'")
        else:
            logger.warning(f"⚠️ Task {task_id} NOT FOUND in celery_jobs table!")
            logger.warning(f"⚠️ This could mean: 1) Preview mode, 2) DB connection issue, 3) Job not created")
            
    except Exception as e:
        # Don't fail the task just because status tracking failed
        log_signal_handler_failure('task_prerun', task_id, e)
        logger.error(f"❌ CRITICAL: Signal handler exception type: {type(e).__name__}")
        logger.error(f"❌ CRITICAL: Signal handler exception message: {str(e)}")
        logger.exception("Full traceback:")


@signals.task_failure.connect
def task_failure_handler(sender=None, task_id=None, exception=None, traceback=None, **kwargs):
    """
    Automatically update job status to 'failed' when task raises an exception.
    
    This signal fires when a task fails, ensuring status updates even if the
    task's own error handling doesn't update the status.
    
    Args:
        sender: The task class
        task_id: Unique task identifier
        exception: The exception that caused the failure
        traceback: Exception traceback object
        **kwargs: Additional signal parameters
    """
    from utils.db.jobs import update_celery_job_status, get_celery_job
    from utils.diagnostic_logger import (
        log_signal_handler_entry,
        log_signal_handler_db_attempt,
        log_signal_handler_success,
        log_signal_handler_failure
    )
    
    try:
        log_signal_handler_entry('task_failure', task_id)
        
        job = get_celery_job(task_id)
        
        if job:
            error_message = f"{type(exception).__name__}: {str(exception)}"
            logger.error(f"🔔 Signal: Task {task_id} failed with error: {error_message}")
            
            # Only update if not already marked as failed (task may have handled it)
            if job['status'] != 'failed':
                log_signal_handler_db_attempt('task_failure', task_id, 'failed')
                update_celery_job_status(
                    task_id,
                    'failed',
                    error_message=error_message[:1000]  # Truncate long errors
                )
                log_signal_handler_success('task_failure', task_id)
        else:
            logger.warning(f"⚠️ Failed task {task_id} NOT FOUND in celery_jobs table!")
            
    except Exception as e:
        # Don't fail the task just because status tracking failed
        log_signal_handler_failure('task_failure', task_id, e)
        logger.exception("Full traceback:")


@signals.task_success.connect
def task_success_handler(sender=None, task_id=None, result=None, **kwargs):
    """
    Log when task completes successfully (status updated by task itself).
    
    This is primarily for logging/monitoring. The task should handle its own
    success status update, but this provides a fallback.
    
    Args:
        sender: The task class
        task_id: Unique task identifier  
        result: Task return value
        **kwargs: Additional signal parameters
    """
    from utils.db.jobs import get_celery_job
    
    try:
        job = get_celery_job(task_id)
        
        if job:
            logger.info(f"🔔 Signal: Task {task_id} completed successfully (status: {job['status']})")
            
            # Note: We don't forcibly update status here because the task itself
            # should handle success status updates with detailed results
        else:
            logger.debug(f"🔔 Signal: Successful task {task_id} not found in celery_jobs table")
            
    except Exception as e:
        logger.warning(f"⚠️ Success signal handler error for {task_id}: {e}")


logger.info("Celery signal handlers registered successfully")


if __name__ == '__main__':
    celery_app.start()

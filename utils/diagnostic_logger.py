"""
Comprehensive diagnostic logging for debugging production issues.

This module provides detailed logging at every stage of the task lifecycle:
1. Environment detection
2. Task submission from UI
3. Task pickup by worker
4. Database operations
5. Status transitions
"""
import logging
import os
import json
from datetime import datetime
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def get_environment_info() -> Dict[str, Any]:
    """Get comprehensive environment information for diagnostics."""
    return {
        'REPLIT_DEPLOYMENT': os.getenv('REPLIT_DEPLOYMENT', 'not set'),
        'REPL_SLUG': os.getenv('REPL_SLUG', 'not set'),
        'REPLIT_DOMAINS': os.getenv('REPLIT_DOMAINS', 'not set'),
        'REDIS_HOST': os.getenv('REDIS_HOST', 'not set')[:50] + '...' if os.getenv('REDIS_HOST') else 'not set',
        'REDIS_PORT': os.getenv('REDIS_PORT', 'not set'),
        'REDIS_USE_TLS': os.getenv('REDIS_USE_TLS', 'not set'),
        'DATABASE_URL': 'SET' if os.getenv('DATABASE_URL') else 'NOT SET',
    }


def detect_environment() -> str:
    """
    Detect if we're in production or development.
    Returns: 'PRODUCTION' or 'DEVELOPMENT'
    """
    is_production = (
        os.getenv('REPLIT_DEPLOYMENT') == '1' or
        os.getenv('REPL_SLUG', '').endswith('.replit.app') or
        'replit.app' in os.getenv('REPLIT_DOMAINS', '')
    )
    return 'PRODUCTION' if is_production else 'DEVELOPMENT'


def get_redis_key_prefix() -> str:
    """Get the Redis key prefix being used."""
    env = detect_environment()
    return 'prod' if env == 'PRODUCTION' else 'dev'


def log_environment_diagnostic():
    """Log comprehensive environment diagnostic information."""
    env = detect_environment()
    prefix = get_redis_key_prefix()
    env_info = get_environment_info()
    
    logger.info("=" * 80)
    logger.info("ENVIRONMENT DIAGNOSTIC")
    logger.info("=" * 80)
    logger.info(f"Environment Detected: {env}")
    logger.info(f"Redis Key Prefix: {prefix}_")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("-" * 80)
    logger.info("Environment Variables:")
    for key, value in env_info.items():
        logger.info(f"  {key}: {value}")
    logger.info("=" * 80)


def log_task_submission(
    task_id: str,
    task_name: str,
    source_id: int,
    queue: str,
    row_count: int
):
    """Log comprehensive information when submitting a task."""
    env = detect_environment()
    prefix = get_redis_key_prefix()
    
    logger.info("🚀" * 40)
    logger.info("TASK SUBMISSION DIAGNOSTIC")
    logger.info("🚀" * 40)
    logger.info(f"Task ID: {task_id}")
    logger.info(f"Task Name: {task_name}")
    logger.info(f"Source ID: {source_id}")
    logger.info(f"Queue: {queue}")
    logger.info(f"Row Count: {row_count}")
    logger.info(f"Environment: {env}")
    logger.info(f"Redis Prefix: {prefix}_")
    logger.info(f"Expected Redis Key: {prefix}_celery-task-meta-{task_id}")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("🚀" * 40)


def log_task_submission_success(task_id: str):
    """Log successful task submission (after apply_async)."""
    logger.info(f"✅ apply_async() COMPLETED SUCCESSFULLY for task {task_id}")
    logger.info(f"✅ Task should now be in Redis queue")


def log_task_submission_failure(task_id: str, error: Exception):
    """Log task submission failure."""
    logger.error(f"❌ apply_async() FAILED for task {task_id}")
    logger.error(f"❌ Error type: {type(error).__name__}")
    logger.error(f"❌ Error message: {str(error)}")
    logger.exception("Full traceback:")


def log_worker_task_received(task_id: str, task_name: str):
    """Log when worker receives a task."""
    env = detect_environment()
    prefix = get_redis_key_prefix()
    
    logger.info("👷" * 40)
    logger.info("WORKER TASK RECEIVED")
    logger.info("👷" * 40)
    logger.info(f"Task ID: {task_id}")
    logger.info(f"Task Name: {task_name}")
    logger.info(f"Worker Environment: {env}")
    logger.info(f"Worker Redis Prefix: {prefix}_")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")
    logger.info("👷" * 40)


def log_db_status_update(
    task_id: str,
    old_status: str,
    new_status: str,
    success: bool,
    error: Optional[str] = None
):
    """Log database status update attempts."""
    if success:
        logger.info(f"✅ DB STATUS UPDATE SUCCESS: {task_id} | {old_status} → {new_status}")
    else:
        logger.error(f"❌ DB STATUS UPDATE FAILED: {task_id} | {old_status} → {new_status}")
        if error:
            logger.error(f"❌ Error: {error}")


def log_signal_handler_entry(signal_name: str, task_id: str):
    """Log when a Celery signal handler is triggered."""
    logger.info(f"📡 SIGNAL HANDLER: {signal_name} triggered for task {task_id}")


def log_signal_handler_db_attempt(signal_name: str, task_id: str, status: str):
    """Log database update attempt from signal handler."""
    logger.info(f"📡 {signal_name}: Attempting DB update for {task_id} → status={status}")


def log_signal_handler_success(signal_name: str, task_id: str):
    """Log successful signal handler execution."""
    logger.info(f"✅ SIGNAL HANDLER SUCCESS: {signal_name} completed for {task_id}")


def log_signal_handler_failure(signal_name: str, task_id: str, error: Exception):
    """Log signal handler failure."""
    logger.error(f"❌ SIGNAL HANDLER FAILED: {signal_name} for {task_id}")
    logger.error(f"❌ Error: {str(error)}")
    logger.exception("Full traceback:")

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


# ============================================
# LOGGING SETUP
# ============================================

logger = logging.getLogger(__name__)


# ============================================
# CONSTANTS
# ============================================

# Task time limits (seconds)
TASK_HARD_TIME_LIMIT = 1800  # 30 minutes - hard kill for hung tasks
TASK_SOFT_TIME_LIMIT = 1500  # 25 minutes - warning before hard kill

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
    
    Returns:
        str: Fully qualified Redis connection URL
    """
    import re
    
    redis_host_raw = os.getenv('REDIS_HOST', DEFAULT_REDIS_HOST)
    redis_port = os.getenv('REDIS_PORT', DEFAULT_REDIS_PORT)
    redis_password = os.getenv('REDIS_PASSWORD', '')
    redis_use_tls = os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'
    
    logger.info(f"Configuring Redis connection (TLS: {redis_use_tls})")
    
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
    
    # Build connection URL
    if redis_use_tls and redis_password:
        connection_url = (
            f"rediss://default:{redis_password}@{redis_host}:{redis_port}"
            f"?ssl_cert_reqs={SSL_CERT_REQS}"
        )
        logger.info(f"Built TLS Redis connection for {redis_host}:{redis_port}")
    elif redis_password:
        connection_url = f"redis://default:{redis_password}@{redis_host}:{redis_port}/0"
        logger.info(f"Built authenticated Redis connection for {redis_host}:{redis_port}")
    else:
        connection_url = f"redis://{redis_host}:{redis_port}/0"
        logger.info(f"Built Redis connection for {redis_host}:{redis_port}")
    
    return connection_url


# ============================================
# CELERY INITIALIZATION
# ============================================

redis_url = get_redis_url()

celery_app = Celery(
    'pdf_processor',
    broker=redis_url,
    backend=redis_url,
    include=['tasks']
)


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
    
    # Task acknowledgment (prevents message loss on worker crash)
    task_acks_late=True,
    
    # Worker settings
    worker_prefetch_multiplier=WORKER_PREFETCH_MULTIPLIER,  # Only fetch 1 task at a time
    worker_max_tasks_per_child=WORKER_MAX_TASKS_PER_CHILD,  # Restart after N tasks
    
    # Task time limits (prevents hung tasks)
    task_time_limit=TASK_HARD_TIME_LIMIT,      # Hard kill after 30 min
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT, # Soft timeout at 25 min
    
    # Retry settings
    task_default_retry_delay=TASK_DEFAULT_RETRY_DELAY,
    task_max_retries=TASK_MAX_RETRIES,
    
    # Task routing (separate queues for different task types)
    task_routes={
        'tasks.process_pdf_task': {'queue': 'pdf_processing'},
        'tasks.process_batch_task': {'queue': 'batch_processing'},
    },
    
    # Queue configuration
    task_queues=(
        Queue('pdf_processing', routing_key='pdf.#'),
        Queue('batch_processing', routing_key='batch.#'),
    ),
    
    # Result backend settings
    result_expires=RESULT_EXPIRES,  # Results expire after 24 hours
)

logger.info("Celery app configured successfully")


if __name__ == '__main__':
    celery_app.start()

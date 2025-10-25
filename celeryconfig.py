"""
Celery configuration for background task processing.
"""

import os
from celery import Celery
from kombu import Queue

def get_redis_url():
    """
    Get Redis connection URL from environment variables.
    Supports both Upstash Redis (TLS) and local Redis.
    """
    redis_host = os.getenv('REDIS_HOST', 'localhost')
    redis_port = os.getenv('REDIS_PORT', '6379')
    redis_password = os.getenv('REDIS_PASSWORD', '')
    redis_use_tls = os.getenv('REDIS_USE_TLS', 'false').lower() == 'true'
    
    if redis_use_tls and redis_password:
        connection_url = f"rediss://:{redis_password}@{redis_host}:{redis_port}/0?ssl_cert_reqs=required"
    elif redis_password:
        connection_url = f"redis://:{redis_password}@{redis_host}:{redis_port}/0"
    else:
        connection_url = f"redis://{redis_host}:{redis_port}/0"
    
    return connection_url


redis_url = get_redis_url()

celery_app = Celery(
    'pdf_processor',
    broker=redis_url,
    backend=redis_url,
    include=['tasks']
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    
    broker_connection_retry_on_startup=True,
    
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    
    task_time_limit=1800,
    task_soft_time_limit=1500,
    
    worker_max_tasks_per_child=50,
    
    task_default_retry_delay=60,
    task_max_retries=3,
    
    task_routes={
        'tasks.process_pdf_task': {'queue': 'pdf_processing'},
        'tasks.process_batch_task': {'queue': 'batch_processing'},
    },
    
    task_queues=(
        Queue('pdf_processing', routing_key='pdf.#'),
        Queue('batch_processing', routing_key='batch.#'),
    ),
    
    result_expires=86400,
)


if __name__ == '__main__':
    celery_app.start()

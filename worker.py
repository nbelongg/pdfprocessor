"""
Celery worker startup script.
"""

import os
import sys
from celeryconfig import celery_app

if __name__ == '__main__':
    celery_app.worker_main([
        'worker',
        '--loglevel=info',
        '--concurrency=3',
        '--max-tasks-per-child=50',
        '--time-limit=1800',
        '--soft-time-limit=1500'
    ])

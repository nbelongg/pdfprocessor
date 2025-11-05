"""
Monitoring utilities for cost tracking, runtime monitoring, and failure handling.

This module provides functions to:
- Track API costs (LlamaParse, OpenAI, Pinecone)
- Monitor task runtimes and SLA compliance
- Manage failed task queue
- Monitor Celery queue depth
"""

import logging
import time
from typing import Dict, Optional, Any, Union
from datetime import datetime, timedelta
from utils.db_utils import get_db_transaction, with_db_error_handling

logger = logging.getLogger(__name__)


# ============================================
# COST TRACKING
# ============================================

# Cost constants (updated pricing as of Nov 2025)
LLAMAPARSE_COST_PER_PAGE = 0.01  # $0.01 per page
OPENAI_EMBEDDING_COST_PER_MILLION_TOKENS = 0.02  # $0.02 per 1M tokens
PINECONE_COST_PER_1K_VECTORS_PER_MONTH = 0.0007  # Approximate serverless cost


@with_db_error_handling
def track_api_cost(
    job_id: str,
    service: str,
    units: float,
    cost_usd: float,
    details: Optional[Dict] = None
) -> None:
    """
    Track API usage and costs in the database.
    
    Args:
        job_id: Processing job ID
        service: Service name (llamaparse, openai_embeddings, pinecone)
        units: Number of units consumed (pages, tokens, vectors)
        cost_usd: Cost in USD
        details: Optional additional details as JSON
        
    Examples:
        track_api_cost(job_id, 'llamaparse', 42, 0.42, {'mode': 'premium'})
        track_api_cost(job_id, 'openai_embeddings', 15000, 0.0003)
    """
    from psycopg2.extras import Json
    
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO api_costs (job_id, service, units, cost_usd, details)
                VALUES (%s, %s, %s, %s, %s)
            """, (job_id, service, units, cost_usd, Json(details) if details else None))
            
            logger.info(f"💰 Cost tracked: {service} = ${cost_usd:.4f} ({units} units) for job {job_id}")


def calculate_llamaparse_cost(num_pages: int) -> float:
    """Calculate LlamaParse cost based on page count."""
    return num_pages * LLAMAPARSE_COST_PER_PAGE


def calculate_openai_embedding_cost(num_tokens: int) -> float:
    """Calculate OpenAI embedding cost based on token count."""
    return (num_tokens / 1_000_000) * OPENAI_EMBEDDING_COST_PER_MILLION_TOKENS


def estimate_tokens_from_text(text: str) -> int:
    """
    Estimate token count from text.
    Rough approximation: 1 token ≈ 4 characters
    """
    return len(text) // 4


# ============================================
# RUNTIME TRACKING
# ============================================

SLA_WARNING_THRESHOLD_SECONDS = 900  # 15 minutes


@with_db_error_handling
def update_job_runtime(
    job_id: str,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    processing_time_seconds: Optional[int] = None
) -> None:
    """
    Update processing job runtime metrics.
    
    Args:
        job_id: Processing job ID
        started_at: When processing started
        completed_at: When processing completed
        processing_time_seconds: Total processing time in seconds
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            updates = []
            params = []
            
            if started_at is not None:
                updates.append("started_at = %s")
                params.append(started_at)
            
            if completed_at is not None:
                updates.append("completed_at = %s")
                params.append(completed_at)
                
            if processing_time_seconds is not None:
                updates.append("processing_time_seconds = %s")
                params.append(processing_time_seconds)
                
                # Log SLA warning
                if processing_time_seconds > SLA_WARNING_THRESHOLD_SECONDS:
                    minutes = processing_time_seconds / 60
                    logger.warning(
                        f"⚠️ SLA WARNING: Job {job_id} took {minutes:.1f} minutes "
                        f"(threshold: {SLA_WARNING_THRESHOLD_SECONDS/60} minutes)"
                    )
            
            if updates:
                params.append(job_id)
                query = f"UPDATE processing_jobs SET {', '.join(updates)} WHERE job_id = %s"
                cur.execute(query, params)
                logger.info(f"⏱️ Runtime updated for job {job_id}: {processing_time_seconds}s")


# ============================================
# FAILED TASK QUEUE
# ============================================

@with_db_error_handling
def save_to_failed_queue(
    task_id: str,
    job_id: Optional[str],
    task_name: str,
    error_message: str,
    error_type: str,
    task_args: Optional[Dict] = None,
    retry_count: int = 0
) -> None:
    """
    Save a failed task to the dead letter queue.
    
    Args:
        task_id: Celery task ID
        job_id: Processing job ID (if available)
        task_name: Name of the task that failed
        error_message: Error message/traceback
        error_type: Exception type name
        task_args: Task arguments for potential retry
        retry_count: Number of retries attempted
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO failed_tasks 
                (task_id, job_id, task_name, error_message, error_type, task_args, retry_count, last_retry_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
            """, (task_id, job_id, task_name, error_message, error_type, task_args, retry_count))
            
            logger.error(
                f"❌ DEAD LETTER QUEUE: Task {task_name} (ID: {task_id}) failed after {retry_count} retries. "
                f"Error: {error_type}: {error_message[:200]}"
            )


@with_db_error_handling
def get_failed_tasks(limit: int = 100) -> list:
    """
    Retrieve recent failed tasks from the dead letter queue.
    
    Args:
        limit: Maximum number of tasks to retrieve
        
    Returns:
        List of failed task records
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    id, task_id, job_id, task_name, error_message, 
                    error_type, task_args, retry_count, created_at, last_retry_at
                FROM failed_tasks
                ORDER BY created_at DESC
                LIMIT %s
            """, (limit,))
            
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


# ============================================
# QUEUE DEPTH MONITORING
# ============================================

def get_queue_depth() -> Dict[str, Union[int, str]]:
    """
    Get the current depth of Celery queues.
    
    Returns:
        Dictionary with queue names and their depths
    """
    try:
        from celeryconfig import celery_app
        
        inspector = celery_app.control.inspect()
        
        # Get active tasks
        active = inspector.active()
        active_count = sum(len(tasks) for tasks in (active or {}).values()) if active else 0
        
        # Get scheduled tasks
        scheduled = inspector.scheduled()
        scheduled_count = sum(len(tasks) for tasks in (scheduled or {}).values()) if scheduled else 0
        
        # Get reserved tasks
        reserved = inspector.reserved()
        reserved_count = sum(len(tasks) for tasks in (reserved or {}).values()) if reserved else 0
        
        total_pending = active_count + scheduled_count + reserved_count
        
        result = {
            'active': active_count,
            'scheduled': scheduled_count,
            'reserved': reserved_count,
            'total_pending': total_pending
        }
        
        # Alert if queue depth exceeds threshold
        if total_pending > 100:
            logger.warning(
                f"⚠️ QUEUE DEPTH ALERT: {total_pending} tasks pending "
                f"(active: {active_count}, scheduled: {scheduled_count}, reserved: {reserved_count})"
            )
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get queue depth: {e}")
        return {
            'active': 0,
            'scheduled': 0,
            'reserved': 0,
            'total_pending': 0,
            'error': str(e)
        }


# ============================================
# COST SUMMARY
# ============================================

@with_db_error_handling
def get_cost_summary(days: int = 30) -> Dict[str, Any]:
    """
    Get cost summary for the last N days.
    
    Args:
        days: Number of days to look back
        
    Returns:
        Dictionary with cost breakdown by service
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    service,
                    SUM(units) as total_units,
                    SUM(cost_usd) as total_cost,
                    COUNT(*) as num_calls,
                    MIN(created_at) as first_call,
                    MAX(created_at) as last_call
                FROM api_costs
                WHERE created_at >= NOW() - INTERVAL '%s days'
                GROUP BY service
                ORDER BY total_cost DESC
            """, (days,))
            
            services = {}
            total_cost = 0.0
            
            for row in cur.fetchall():
                service_data = {
                    'total_units': float(row[1]),
                    'total_cost': float(row[2]),
                    'num_calls': row[3],
                    'first_call': row[4],
                    'last_call': row[5]
                }
                services[row[0]] = service_data
                total_cost += service_data['total_cost']
            
            return {
                'total_cost': total_cost,
                'services': services,
                'period_days': days
            }


@with_db_error_handling
def get_daily_costs(days: int = 30) -> list:
    """
    Get daily cost breakdown for the last N days.
    
    Args:
        days: Number of days to look back
        
    Returns:
        List of daily cost records
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    DATE(created_at) as date,
                    service,
                    SUM(units) as total_units,
                    SUM(cost_usd) as total_cost
                FROM api_costs
                WHERE created_at >= NOW() - INTERVAL '%s days'
                GROUP BY DATE(created_at), service
                ORDER BY date DESC, service
            """, (days,))
            
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]

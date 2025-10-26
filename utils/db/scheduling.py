"""
Scheduled jobs database operations.

This module handles:
- Scheduled job creation and management
- Job run tracking and history
- Schedule status updates
"""

import logging
from typing import Dict, List, Optional
from psycopg2.extras import Json

from utils.exceptions import DatabaseError, DatabaseTransientError
from utils.db_utils import get_db_transaction, with_db_error_handling
from utils.db.connection import get_db_connection

logger = logging.getLogger(__name__)


# ===== Scheduled Jobs =====

@with_db_error_handling
def create_scheduled_job(source_id: int, job_name: str, schedule_type: str, schedule_config: Dict) -> int:
    """Create a new scheduled job for a data source."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduled_jobs (source_id, job_name, schedule_type, schedule_config)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE
                SET job_name = EXCLUDED.job_name,
                    schedule_type = EXCLUDED.schedule_type,
                    schedule_config = EXCLUDED.schedule_config,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id
                """,
                (source_id, job_name, schedule_type, Json(schedule_config))
            )
            return cur.fetchone()['id']


def get_scheduled_job(source_id: int) -> Optional[Dict]:
    """Get scheduled job for a data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM scheduled_jobs WHERE source_id = %s", (source_id,))
            return cur.fetchone()
    finally:
        conn.close()


def get_all_scheduled_jobs(enabled_only: bool = False) -> List[Dict]:
    """Get all scheduled jobs."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if enabled_only:
                cur.execute("SELECT * FROM scheduled_jobs WHERE enabled = TRUE ORDER BY next_run_at")
            else:
                cur.execute("SELECT * FROM scheduled_jobs ORDER BY created_at DESC")
            return cur.fetchall()
    finally:
        conn.close()


@with_db_error_handling
def update_scheduled_job_status(job_id: int, enabled: bool):
    """Enable or disable a scheduled job."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scheduled_jobs SET enabled = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (enabled, job_id)
            )


@with_db_error_handling
def update_scheduled_job_run_time(job_id: int, next_run_at, last_run_at=None):
    """Update scheduled job run times."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            if last_run_at:
                cur.execute(
                    """
                    UPDATE scheduled_jobs 
                    SET last_run_at = %s, next_run_at = %s, total_runs = total_runs + 1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = %s
                    """,
                    (last_run_at, next_run_at, job_id)
                )
            else:
                cur.execute(
                    "UPDATE scheduled_jobs SET next_run_at = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                    (next_run_at, job_id)
                )


@with_db_error_handling
def delete_scheduled_job(job_id: int):
    """Delete a scheduled job."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scheduled_jobs WHERE id = %s", (job_id,))


# ===== Scheduled Job Runs =====

@with_db_error_handling
def record_scheduled_job_run(scheduled_job_id: int, processing_job_id: str, status: str, **kwargs) -> int:
    """Record a scheduled job run."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO scheduled_job_runs 
                (scheduled_job_id, processing_job_id, status, papers_found, papers_processed, 
                 papers_skipped_duplicate, papers_failed, error_message, run_metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    scheduled_job_id,
                    processing_job_id,
                    status,
                    kwargs.get('papers_found', 0),
                    kwargs.get('papers_processed', 0),
                    kwargs.get('papers_skipped_duplicate', 0),
                    kwargs.get('papers_failed', 0),
                    kwargs.get('error_message'),
                    Json(kwargs.get('run_metadata', {}))
                )
            )
            return cur.fetchone()['id']


@with_db_error_handling
def update_scheduled_job_run(run_id: int, status: str, **kwargs):
    """Update a scheduled job run."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            set_clauses = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
            values = [status]
            
            if status in ['completed', 'failed']:
                set_clauses.append("run_completed_at = CURRENT_TIMESTAMP")
            
            if 'papers_processed' in kwargs:
                set_clauses.append("papers_processed = %s")
                values.append(kwargs['papers_processed'])
            if 'papers_skipped_duplicate' in kwargs:
                set_clauses.append("papers_skipped_duplicate = %s")
                values.append(kwargs['papers_skipped_duplicate'])
            if 'papers_failed' in kwargs:
                set_clauses.append("papers_failed = %s")
                values.append(kwargs['papers_failed'])
            if 'error_message' in kwargs:
                set_clauses.append("error_message = %s")
                values.append(kwargs['error_message'])
            
            values.append(run_id)
            
            cur.execute(
                f"UPDATE scheduled_job_runs SET {', '.join(set_clauses)} WHERE id = %s",
                values
            )
            
            if status == 'completed':
                cur.execute(
                    "UPDATE scheduled_jobs SET successful_runs = successful_runs + 1 WHERE id = (SELECT scheduled_job_id FROM scheduled_job_runs WHERE id = %s)",
                    (run_id,)
                )
            elif status == 'failed':
                cur.execute(
                    "UPDATE scheduled_jobs SET failed_runs = failed_runs + 1 WHERE id = (SELECT scheduled_job_id FROM scheduled_job_runs WHERE id = %s)",
                    (run_id,)
                )


def get_scheduled_job_runs(scheduled_job_id: int, limit: int = 20) -> List[Dict]:
    """Get run history for a scheduled job."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM scheduled_job_runs WHERE scheduled_job_id = %s ORDER BY run_started_at DESC LIMIT %s",
                (scheduled_job_id, limit)
            )
            return cur.fetchall()
    finally:
        conn.close()

"""
Processing jobs and chunks database operations.

This module handles:
- Processing job CRUD operations
- Job status tracking and metrics  
- Chunk storage and retrieval
- Metadata transformations
- Celery job tracking
"""

import logging
from typing import Dict, List, Optional, Any
from psycopg2.extras import Json

from utils.exceptions import DatabaseError, DatabaseTransientError
from utils.db_utils import get_db_transaction, with_db_error_handling
from utils.db.connection import get_db_connection, _row_to_dict

logger = logging.getLogger(__name__)


# ===== Processing Jobs =====

@with_db_error_handling
def create_processing_job(job_id: str, config: Dict[str, Any]) -> Optional[int]:
    """Create a new processing job in the database."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processing_jobs 
                (job_id, status, sheet_url, sheet_tab, config)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    job_id,
                    'pending',
                    config.get('sheet_url'),
                    config.get('sheet_tab'),
                    Json(config)
                )
            )
            result = cur.fetchone()
            return result['id'] if result else None


@with_db_error_handling
def update_job_status(job_id: str, status: str, **kwargs):
    """Update processing job status and metrics."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            set_clauses = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
            values = [status]
            
            if 'total_pdfs' in kwargs:
                set_clauses.append("total_pdfs = %s")
                values.append(kwargs['total_pdfs'])
            if 'processed_pdfs' in kwargs:
                set_clauses.append("processed_pdfs = %s")
                values.append(kwargs['processed_pdfs'])
            if 'total_chunks' in kwargs:
                set_clauses.append("total_chunks = %s")
                values.append(kwargs['total_chunks'])
            if 'total_embeddings' in kwargs:
                set_clauses.append("total_embeddings = %s")
                values.append(kwargs['total_embeddings'])
            if 'vectors_stored' in kwargs:
                set_clauses.append("vectors_stored = %s")
                values.append(kwargs['vectors_stored'])
            if 'error_message' in kwargs:
                set_clauses.append("error_message = %s")
                values.append(kwargs['error_message'])
            if status == 'completed':
                set_clauses.append("completed_at = CURRENT_TIMESTAMP")
            
            values.append(job_id)
            
            cur.execute(
                f"UPDATE processing_jobs SET {', '.join(set_clauses)} WHERE job_id = %s",
                values
            )


def get_job_history(limit: int = 50) -> List[Dict[str, Any]]:
    """Get processing job history."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_id, status, sheet_url, sheet_tab,
                       total_pdfs, processed_pdfs, total_chunks,
                       total_embeddings, vectors_stored,
                       created_at, completed_at
                FROM processing_jobs
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


def get_job_details(job_id: str) -> Optional[Dict[str, Any]]:
    """Get detailed information about a specific job."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM processing_jobs WHERE job_id = %s
                """,
                (job_id,)
            )
            return _row_to_dict(cur.fetchone())
    finally:
        conn.close()


@with_db_error_handling
def delete_job(job_id: str):
    """Delete a job and all its chunks (cascades)."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM processing_jobs WHERE job_id = %s",
                (job_id,)
            )


# ===== Chunks =====

@with_db_error_handling
def save_chunks(job_id: str, file_id: str, filename: str, chunks: List[Dict]):
    """Save chunks to database."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            for idx, chunk in enumerate(chunks):
                cur.execute(
                    """
                    INSERT INTO processing_chunks
                    (job_id, file_id, filename, chunk_index, chunk_text, metadata, namespace)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        job_id,
                        file_id,
                        filename,
                        idx,
                        chunk.get('text', ''),
                        Json(chunk.get('metadata', {})),
                        chunk.get('namespace', 'default')
                    )
                )


def get_job_chunks(job_id: str) -> List[Dict[str, Any]]:
    """Get all chunks for a specific job."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM processing_chunks
                WHERE job_id = %s
                ORDER BY file_id, chunk_index
                """,
                (job_id,)
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


@with_db_error_handling
def mark_chunks_uploaded(job_id: str, file_id: str):
    """Mark chunks as uploaded to Pinecone."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE processing_chunks 
                SET embedding_stored = TRUE
                WHERE job_id = %s AND file_id = %s
                """,
                (job_id, file_id)
            )


# ===== Metadata Transformations =====

@with_db_error_handling
def save_metadata_transformation(name: str, description: str, rules: Dict):
    """Save a metadata transformation rule."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO metadata_transformations (name, description, rules)
                VALUES (%s, %s, %s)
                ON CONFLICT (name) 
                DO UPDATE SET description = %s, rules = %s, updated_at = CURRENT_TIMESTAMP
                """,
                (name, description, Json(rules), description, Json(rules))
            )


def get_metadata_transformations() -> List[Dict[str, Any]]:
    """Get all metadata transformations."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM metadata_transformations ORDER BY name"
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


@with_db_error_handling
def delete_metadata_transformation(name: str):
    """Delete a metadata transformation."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM metadata_transformations WHERE name = %s",
                (name,)
            )


# ===== Celery Jobs =====

@with_db_error_handling
def init_celery_tables():
    """Initialize Celery job tracking tables."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS celery_jobs (
                    id SERIAL PRIMARY KEY,
                    task_id VARCHAR(255) UNIQUE NOT NULL,
                    task_name VARCHAR(255) NOT NULL,
                    source_id INTEGER REFERENCES data_sources(id) ON DELETE SET NULL,
                    status VARCHAR(50) DEFAULT 'pending',
                    progress_current INTEGER DEFAULT 0,
                    progress_total INTEGER DEFAULT 0,
                    progress_message TEXT,
                    result JSONB,
                    error_message TEXT,
                    submitted_by VARCHAR(100),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP
                )
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_celery_jobs_task_id ON celery_jobs(task_id)
            """)
            
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_celery_jobs_status ON celery_jobs(status)
            """)


@with_db_error_handling
def create_celery_job(task_id: str, task_name: str, source_id: Optional[int] = None, submitted_by: str = 'system') -> int:
    """Create a new Celery job record."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO celery_jobs (task_id, task_name, source_id, submitted_by, status)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (task_id, task_name, source_id, submitted_by, 'pending')
            )
            job_id = cur.fetchone()['id']
            return job_id


def _serialize_for_json(obj):
    """
    Recursively convert datetime objects to ISO format strings for JSON serialization.
    
    Args:
        obj: Any object that may contain datetime objects
        
    Returns:
        Object with datetime instances converted to strings
    """
    from datetime import datetime, date
    
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: _serialize_for_json(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_serialize_for_json(item) for item in obj]
    else:
        return obj


@with_db_error_handling
def update_celery_job_status(task_id: str, status: str, **kwargs):
    """Update Celery job status and metadata."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            set_clauses = ["status = %s", "updated_at = CURRENT_TIMESTAMP"]
            values = [status]
            
            if 'progress_current' in kwargs:
                set_clauses.append("progress_current = %s")
                values.append(kwargs['progress_current'])
            if 'progress_total' in kwargs:
                set_clauses.append("progress_total = %s")
                values.append(kwargs['progress_total'])
            if 'progress_message' in kwargs:
                set_clauses.append("progress_message = %s")
                values.append(kwargs['progress_message'])
            if 'result' in kwargs:
                set_clauses.append("result = %s")
                # Serialize datetime objects before JSON encoding
                serialized_result = _serialize_for_json(kwargs['result'])
                values.append(Json(serialized_result))
            if 'error_message' in kwargs:
                set_clauses.append("error_message = %s")
                values.append(kwargs['error_message'])
            if status in ['completed', 'failed']:
                set_clauses.append("completed_at = CURRENT_TIMESTAMP")
            
            values.append(task_id)
            
            cur.execute(
                f"UPDATE celery_jobs SET {', '.join(set_clauses)} WHERE task_id = %s",
                values
            )


def get_celery_job(task_id: str) -> Optional[Dict]:
    """Get a Celery job by task ID."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM celery_jobs WHERE task_id = %s",
                (task_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()


def get_all_celery_jobs(limit: int = 100, status_filter: Optional[str] = None) -> List[Dict]:
    """Get all Celery jobs with optional status filter."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if status_filter:
                cur.execute(
                    """
                    SELECT * FROM celery_jobs 
                    WHERE status = %s
                    ORDER BY created_at DESC 
                    LIMIT %s
                    """,
                    (status_filter, limit)
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM celery_jobs 
                    ORDER BY created_at DESC 
                    LIMIT %s
                    """,
                    (limit,)
                )
            return cur.fetchall()
    finally:
        conn.close()


def cancel_celery_job(task_id: str):
    """Mark a Celery job as cancelled."""
    update_celery_job_status(task_id, 'cancelled')

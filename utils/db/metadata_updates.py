"""
Database functions for metadata-only updates.

This module handles retrieval and updating of chunk metadata and embeddings
without re-parsing PDFs.
"""

import logging
from typing import List, Dict, Any, Optional
from psycopg2.extras import Json
from utils.db_utils import get_db_transaction, with_db_error_handling

logger = logging.getLogger(__name__)


@with_db_error_handling
def get_chunks_with_embeddings(file_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve all chunks and their embeddings for a specific paper.
    
    Args:
        file_id: Google Drive file ID
        
    Returns:
        List of dicts with chunk_id, chunk_text, embedding, metadata, chunk_index, namespace
        
    Raises:
        ValueError: If no chunks found for file_id
    """
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                id,
                chunk_index,
                chunk_text,
                embedding,
                metadata,
                namespace
            FROM processing_chunks
            WHERE file_id = %s
            ORDER BY chunk_index
            """,
            (file_id,)
        )
        
        rows = cursor.fetchall()
        
        if not rows:
            raise ValueError(f"No chunks found for file_id: {file_id}")
        
        chunks = []
        for row in rows:
            chunks.append({
                'chunk_id': row['id'],
                'chunk_index': row['chunk_index'],
                'chunk_text': row['chunk_text'],
                'embedding': row['embedding'],  # PostgreSQL array of floats
                'metadata': dict(row['metadata']) if row['metadata'] else {},
                'namespace': row['namespace']
            })
        
        logger.info(f"Retrieved {len(chunks)} chunks with embeddings for file_id: {file_id}")
        return chunks


@with_db_error_handling
def update_chunk_metadata(
    file_id: str,
    chunk_updates: List[Dict[str, Any]]
) -> int:
    """
    Update metadata for multiple chunks of a paper.
    
    Args:
        file_id: Google Drive file ID
        chunk_updates: List of dicts with chunk_index and metadata to update
        
    Returns:
        Number of chunks updated
    """
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        
        updated_count = 0
        for update in chunk_updates:
            chunk_index = update['chunk_index']
            new_metadata = update['metadata']
            
            cursor.execute(
                """
                UPDATE processing_chunks
                SET metadata = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE file_id = %s AND chunk_index = %s
                """,
                (Json(new_metadata), file_id, chunk_index)
            )
            updated_count += cursor.rowcount
        
        logger.info(f"Updated metadata for {updated_count} chunks of file_id: {file_id}")
        return updated_count


@with_db_error_handling
def create_metadata_update_job(
    job_id: str,
    source_id: int,
    total_papers: int
) -> int:
    """
    Create a new metadata update job record.
    
    Args:
        job_id: Unique job identifier
        source_id: Data source ID
        total_papers: Total number of papers to update
        
    Returns:
        Database ID of created job
    """
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO metadata_update_jobs 
            (job_id, source_id, total_papers, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING id
            """,
            (job_id, source_id, total_papers)
        )
        
        job_db_id = cursor.fetchone()['id']
        logger.info(f"Created metadata update job {job_id} (DB ID: {job_db_id})")
        return job_db_id


@with_db_error_handling
def update_metadata_job_progress(
    job_id: str,
    papers_updated: Optional[int] = None,
    papers_failed: Optional[int] = None,
    status: Optional[str] = None,
    error_message: Optional[str] = None
):
    """
    Update progress of a metadata update job.
    
    Args:
        job_id: Job identifier
        papers_updated: Number of papers successfully updated
        papers_failed: Number of papers that failed
        status: Job status (pending, running, completed, failed)
        error_message: Error message if job failed
    """
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        
        # Build dynamic UPDATE query
        update_fields = []
        params = []
        
        if papers_updated is not None:
            update_fields.append("papers_updated = %s")
            params.append(papers_updated)
        
        if papers_failed is not None:
            update_fields.append("papers_failed = %s")
            params.append(papers_failed)
        
        if status:
            update_fields.append("status = %s")
            params.append(status)
            
            if status in ['completed', 'failed']:
                update_fields.append("completed_at = CURRENT_TIMESTAMP")
            elif status == 'running':
                update_fields.append("started_at = CURRENT_TIMESTAMP")
        
        if error_message:
            update_fields.append("error_message = %s")
            params.append(error_message)
        
        if not update_fields:
            logger.warning(f"No fields to update for job {job_id}")
            return
        
        params.append(job_id)
        query = f"""
            UPDATE metadata_update_jobs
            SET {', '.join(update_fields)}
            WHERE job_id = %s
        """
        
        cursor.execute(query, params)
        logger.debug(f"Updated metadata job {job_id}: {dict(zip(['papers_updated', 'papers_failed', 'status'], [papers_updated, papers_failed, status]))}")


@with_db_error_handling
def increment_metadata_job_counter(
    job_id: str,
    counter: str,
    increment: int = 1
):
    """
    Atomically increment a counter for a metadata update job.
    
    Args:
        job_id: Job identifier
        counter: Counter name ('papers_updated' or 'papers_failed')
        increment: Amount to increment (default: 1)
    """
    if counter not in ['papers_updated', 'papers_failed']:
        raise ValueError(f"Invalid counter: {counter}")
    
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE metadata_update_jobs
            SET {counter} = {counter} + %s
            WHERE job_id = %s
            """,
            (increment, job_id)
        )


@with_db_error_handling
def get_metadata_update_job(job_id: str) -> Optional[Dict[str, Any]]:
    """
    Get status and details of a metadata update job.
    
    Args:
        job_id: Job identifier
        
    Returns:
        Dict with job details or None if not found
    """
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                id,
                job_id,
                source_id,
                total_papers,
                papers_updated,
                papers_failed,
                status,
                started_at,
                completed_at,
                error_message,
                created_at
            FROM metadata_update_jobs
            WHERE job_id = %s
            """,
            (job_id,)
        )
        
        row = cursor.fetchone()
        return dict(row) if row else None


@with_db_error_handling
def get_recent_metadata_update_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    """
    Get recent metadata update jobs.
    
    Args:
        limit: Maximum number of jobs to return
        
    Returns:
        List of job dictionaries
    """
    with get_db_transaction() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 
                job_id,
                source_id,
                total_papers,
                papers_updated,
                papers_failed,
                status,
                started_at,
                completed_at,
                created_at
            FROM metadata_update_jobs
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (limit,)
        )
        
        rows = cursor.fetchall()
        return [dict(row) for row in rows]

import psycopg2
from psycopg2.extras import RealDictCursor, Json
import os
from typing import Dict, List, Optional
import json
from datetime import datetime

def get_db_connection():
    """Get database connection."""
    return psycopg2.connect(
        os.getenv('DATABASE_URL'),
        cursor_factory=RealDictCursor
    )

def create_processing_job(job_id: str, config: Dict) -> int:
    """Create a new processing job in the database."""
    conn = get_db_connection()
    try:
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
            result = cur.execute("SELECT lastval()").fetchone()
            conn.commit()
            return result['lastval'] if result else None
    finally:
        conn.close()

def update_job_status(job_id: str, status: str, **kwargs):
    """Update processing job status and metrics."""
    conn = get_db_connection()
    try:
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
            if status == 'completed':
                set_clauses.append("completed_at = CURRENT_TIMESTAMP")
            
            values.append(job_id)
            
            cur.execute(
                f"UPDATE processing_jobs SET {', '.join(set_clauses)} WHERE job_id = %s",
                values
            )
            conn.commit()
    finally:
        conn.close()

def save_chunks(job_id: str, file_id: str, filename: str, chunks: List[Dict]):
    """Save chunks to database."""
    conn = get_db_connection()
    try:
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
            conn.commit()
    finally:
        conn.close()

def mark_chunks_uploaded(job_id: str, file_id: str):
    """Mark chunks as uploaded to Pinecone."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE processing_chunks 
                SET embedding_stored = TRUE
                WHERE job_id = %s AND file_id = %s
                """,
                (job_id, file_id)
            )
            conn.commit()
    finally:
        conn.close()

def get_job_history(limit: int = 50) -> List[Dict]:
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
            return cur.fetchall()
    finally:
        conn.close()

def get_job_details(job_id: str) -> Optional[Dict]:
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
            return cur.fetchone()
    finally:
        conn.close()

def get_job_chunks(job_id: str) -> List[Dict]:
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
            return cur.fetchall()
    finally:
        conn.close()

def delete_job(job_id: str):
    """Delete a job and all its chunks (cascades)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM processing_jobs WHERE job_id = %s",
                (job_id,)
            )
            conn.commit()
    finally:
        conn.close()

def save_metadata_transformation(name: str, description: str, rules: Dict):
    """Save a metadata transformation rule."""
    conn = get_db_connection()
    try:
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
            conn.commit()
    finally:
        conn.close()

def get_metadata_transformations() -> List[Dict]:
    """Get all metadata transformations."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM metadata_transformations ORDER BY name"
            )
            return cur.fetchall()
    finally:
        conn.close()

def delete_metadata_transformation(name: str):
    """Delete a metadata transformation."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM metadata_transformations WHERE name = %s",
                (name,)
            )
            conn.commit()
    finally:
        conn.close()

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

# Data Sources Functions

def create_data_source(name: str, sheet_url: str, sheet_tab: str, topic: str = None, 
                       default_namespace: str = 'default') -> int:
    """Create a new data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_sources (name, sheet_url, sheet_tab, topic, default_namespace)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, sheet_url, sheet_tab, topic, default_namespace)
            )
            result = cur.fetchone()
            conn.commit()
            return result['id'] if result else None
    finally:
        conn.close()

def get_data_sources(active_only: bool = False) -> List[Dict]:
    """Get all data sources."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if active_only:
                cur.execute(
                    "SELECT * FROM data_sources WHERE active = TRUE ORDER BY name"
                )
            else:
                cur.execute(
                    "SELECT * FROM data_sources ORDER BY name"
                )
            return cur.fetchall()
    finally:
        conn.close()

def get_data_source(source_id: int) -> Optional[Dict]:
    """Get a specific data source by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM data_sources WHERE id = %s",
                (source_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()

def update_data_source(source_id: int, **kwargs):
    """Update a data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
            values = []
            
            for key in ['name', 'sheet_url', 'sheet_tab', 'topic', 'default_namespace', 'active']:
                if key in kwargs:
                    set_clauses.append(f"{key} = %s")
                    values.append(kwargs[key])
            
            values.append(source_id)
            
            cur.execute(
                f"UPDATE data_sources SET {', '.join(set_clauses)} WHERE id = %s",
                values
            )
            conn.commit()
    finally:
        conn.close()

def delete_data_source(source_id: int):
    """Delete a data source and its column mappings (cascade)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM data_sources WHERE id = %s",
                (source_id,)
            )
            conn.commit()
    finally:
        conn.close()

def update_last_processed(source_id: int, row_number: int):
    """Update the last processed row for a data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE data_sources 
                SET last_processed_row = %s, last_processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (row_number, source_id)
            )
            conn.commit()
    finally:
        conn.close()

# Column Mapping Functions

def save_column_mapping(source_id: int, column_role: str, column_name: str, is_required: bool = False):
    """Save a column mapping for a data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO column_mappings (source_id, column_role, column_name, is_required)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_id, column_role)
                DO UPDATE SET column_name = %s, is_required = %s
                """,
                (source_id, column_role, column_name, is_required, column_name, is_required)
            )
            conn.commit()
    finally:
        conn.close()

def get_column_mappings(source_id: int) -> List[Dict]:
    """Get all column mappings for a data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM column_mappings WHERE source_id = %s ORDER BY column_role",
                (source_id,)
            )
            return cur.fetchall()
    finally:
        conn.close()

def delete_column_mapping(source_id: int, column_role: str):
    """Delete a column mapping."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM column_mappings WHERE source_id = %s AND column_role = %s",
                (source_id, column_role)
            )
            conn.commit()
    finally:
        conn.close()

def get_column_mapping_dict(source_id: int) -> Dict[str, str]:
    """Get column mappings as a dictionary {role: column_name}."""
    mappings = get_column_mappings(source_id)
    return {m['column_role']: m['column_name'] for m in mappings}

def check_paper_processed(drive_file_id: str) -> Optional[Dict]:
    """Check if a paper has been processed before by Drive file ID."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM processed_papers WHERE drive_file_id = %s",
                (drive_file_id,)
            )
            return cur.fetchone()
    finally:
        conn.close()

def check_paper_by_content_hash(content_hash: str) -> Optional[Dict]:
    """Check if a paper has been processed before by content hash."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM processed_papers WHERE content_hash = %s",
                (content_hash,)
            )
            return cur.fetchone()
    finally:
        conn.close()

def record_processed_paper(
    drive_file_id: str,
    content_hash: str,
    paper_title: str,
    authors: str,
    metadata: Dict,
    pinecone_namespace: str,
    source_id: int,
    row_number: int
) -> int:
    """Record a newly processed paper."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_papers
                (drive_file_id, content_hash, paper_title, authors, metadata, pinecone_namespace)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (drive_file_id, content_hash, paper_title, authors, Json(metadata), pinecone_namespace)
            )
            paper_id = cur.fetchone()['id']
            
            cur.execute(
                """
                INSERT INTO source_paper_mapping (source_id, paper_id, row_number)
                VALUES (%s, %s, %s)
                """,
                (source_id, paper_id, row_number)
            )
            
            conn.commit()
            return paper_id
    finally:
        conn.close()

def update_processed_paper(paper_id: int, source_id: int, row_number: int):
    """Update existing processed paper (increment count, update timestamp)."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE processed_papers
                SET processing_count = processing_count + 1,
                    last_processed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (paper_id,)
            )
            
            cur.execute(
                """
                INSERT INTO source_paper_mapping (source_id, paper_id, row_number)
                VALUES (%s, %s, %s)
                ON CONFLICT (source_id, paper_id) DO UPDATE
                SET last_seen_at = CURRENT_TIMESTAMP
                """,
                (source_id, paper_id, row_number)
            )
            
            conn.commit()
    finally:
        conn.close()

def get_deduplication_stats() -> Dict:
    """Get statistics about processed papers and deduplication."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) as total FROM processed_papers")
            total = cur.fetchone()['total']
            
            cur.execute("SELECT COUNT(*) as duplicates FROM processed_papers WHERE processing_count > 1")
            duplicates = cur.fetchone()['duplicates']
            
            cur.execute("SELECT SUM(processing_count) as total_attempts FROM processed_papers")
            total_attempts = cur.fetchone()['total_attempts'] or 0
            
            return {
                'unique_papers': total,
                'duplicate_attempts': total_attempts - total,
                'papers_seen_multiple_times': duplicates
            }
    finally:
        conn.close()

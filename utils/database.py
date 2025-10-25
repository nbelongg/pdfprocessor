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

def init_products_table():
    """Initialize products table."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    description TEXT,
                    pinecone_index VARCHAR(255) NOT NULL,
                    llamaparse_api_key_secret VARCHAR(255),
                    openai_api_key_secret VARCHAR(255),
                    pinecone_api_key_secret VARCHAR(255),
                    google_credentials_secret VARCHAR(255),
                    default_chunking_strategy VARCHAR(50) DEFAULT 'Token-based',
                    default_chunk_size INTEGER DEFAULT 1024,
                    default_embedding_model VARCHAR(100) DEFAULT 'text-embedding-3-small',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add all processing settings columns
            cur.execute("""
                ALTER TABLE products 
                ADD COLUMN IF NOT EXISTS google_credentials_secret VARCHAR(255),
                ADD COLUMN IF NOT EXISTS parsing_mode VARCHAR(50) DEFAULT 'auto',
                ADD COLUMN IF NOT EXISTS result_type VARCHAR(50) DEFAULT 'markdown',
                ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en',
                ADD COLUMN IF NOT EXISTS use_vendor_multimodal BOOLEAN DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS page_separator VARCHAR(50) DEFAULT '\n---\n',
                ADD COLUMN IF NOT EXISTS chunk_overlap INTEGER DEFAULT 200,
                ADD COLUMN IF NOT EXISTS semantic_buffer_size INTEGER DEFAULT 1,
                ADD COLUMN IF NOT EXISTS pinecone_environment VARCHAR(100) DEFAULT 'us-east-1',
                ADD COLUMN IF NOT EXISTS default_namespace VARCHAR(255) DEFAULT 'default'
            """)
            
            # Add product_id to data_sources if not exists
            cur.execute("""
                ALTER TABLE data_sources 
                ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES products(id) ON DELETE SET NULL
            """)
            
            conn.commit()
    finally:
        conn.close()

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
                       default_namespace: str = 'default', product_id: int = None) -> int:
    """Create a new data source."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_sources (name, sheet_url, sheet_tab, topic, default_namespace, product_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, sheet_url, sheet_tab, topic, default_namespace, product_id)
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
            
            for key in ['name', 'sheet_url', 'sheet_tab', 'topic', 'default_namespace', 'active', 'product_id']:
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

def create_scheduled_job(source_id: int, job_name: str, schedule_type: str, schedule_config: Dict) -> int:
    """Create a new scheduled job for a data source."""
    conn = get_db_connection()
    try:
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
    finally:
        conn.close()

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

def update_scheduled_job_status(job_id: int, enabled: bool):
    """Enable or disable a scheduled job."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE scheduled_jobs SET enabled = %s, updated_at = CURRENT_TIMESTAMP WHERE id = %s",
                (enabled, job_id)
            )
            conn.commit()
    finally:
        conn.close()

def update_scheduled_job_run_time(job_id: int, next_run_at, last_run_at=None):
    """Update scheduled job run times."""
    conn = get_db_connection()
    try:
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
            conn.commit()
    finally:
        conn.close()

def record_scheduled_job_run(scheduled_job_id: int, processing_job_id: str, status: str, **kwargs) -> int:
    """Record a scheduled job run."""
    conn = get_db_connection()
    try:
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
    finally:
        conn.close()

def update_scheduled_job_run(run_id: int, status: str, **kwargs):
    """Update a scheduled job run."""
    conn = get_db_connection()
    try:
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
            conn.commit()
            
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
            
            conn.commit()
    finally:
        conn.close()

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

def delete_scheduled_job(job_id: int):
    """Delete a scheduled job."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM scheduled_jobs WHERE id = %s", (job_id,))
            conn.commit()
    finally:
        conn.close()

# ============================================
# PRODUCT MANAGEMENT FUNCTIONS
# ============================================

def get_products(active_only: bool = False) -> List[Dict]:
    """Get all products."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            if active_only:
                cur.execute("SELECT * FROM products WHERE active = TRUE ORDER BY name")
            else:
                cur.execute("SELECT * FROM products ORDER BY name")
            return cur.fetchall()
    finally:
        conn.close()

def get_product(product_id: int) -> Optional[Dict]:
    """Get a single product by ID."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            return cur.fetchone()
    finally:
        conn.close()

def create_product(
    name: str,
    pinecone_index: str,
    description: str = None,
    llamaparse_secret: str = None,
    openai_secret: str = None,
    pinecone_secret: str = None,
    google_credentials_secret: str = None,
    chunking_strategy: str = 'Token-based',
    chunk_size: int = 1024,
    chunk_overlap: int = 200,
    embedding_model: str = 'text-embedding-3-small',
    parsing_mode: str = 'auto',
    result_type: str = 'markdown',
    language: str = 'en',
    use_vendor_multimodal: bool = True,
    page_separator: str = '\n---\n',
    semantic_buffer_size: int = 1,
    pinecone_environment: str = 'us-east-1',
    default_namespace: str = 'default'
) -> int:
    """Create a new product with full processing configuration."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO products 
                (name, description, pinecone_index, llamaparse_api_key_secret,
                 openai_api_key_secret, pinecone_api_key_secret, google_credentials_secret,
                 default_chunking_strategy, default_chunk_size, chunk_overlap, default_embedding_model,
                 parsing_mode, result_type, language, use_vendor_multimodal, page_separator,
                 semantic_buffer_size, pinecone_environment, default_namespace)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, description, pinecone_index, llamaparse_secret, openai_secret,
                 pinecone_secret, google_credentials_secret, chunking_strategy, chunk_size, chunk_overlap,
                 embedding_model, parsing_mode, result_type, language, use_vendor_multimodal,
                 page_separator, semantic_buffer_size, pinecone_environment, default_namespace)
            )
            result = cur.fetchone()
            conn.commit()
            return result['id'] if result else None
    finally:
        conn.close()

def update_product(
    product_id: int,
    name: str = None,
    description: str = None,
    pinecone_index: str = None,
    llamaparse_secret: str = None,
    openai_secret: str = None,
    pinecone_secret: str = None,
    google_credentials_secret: str = None,
    chunking_strategy: str = None,
    chunk_size: int = None,
    chunk_overlap: int = None,
    embedding_model: str = None,
    parsing_mode: str = None,
    result_type: str = None,
    language: str = None,
    use_vendor_multimodal: bool = None,
    page_separator: str = None,
    semantic_buffer_size: int = None,
    pinecone_environment: str = None,
    default_namespace: str = None,
    active: bool = None
):
    """Update a product."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
            values = []
            
            if name is not None:
                set_clauses.append("name = %s")
                values.append(name)
            if description is not None:
                set_clauses.append("description = %s")
                values.append(description)
            if pinecone_index is not None:
                set_clauses.append("pinecone_index = %s")
                values.append(pinecone_index)
            if llamaparse_secret is not None:
                set_clauses.append("llamaparse_api_key_secret = %s")
                values.append(llamaparse_secret)
            if openai_secret is not None:
                set_clauses.append("openai_api_key_secret = %s")
                values.append(openai_secret)
            if pinecone_secret is not None:
                set_clauses.append("pinecone_api_key_secret = %s")
                values.append(pinecone_secret)
            if google_credentials_secret is not None:
                set_clauses.append("google_credentials_secret = %s")
                values.append(google_credentials_secret)
            if chunking_strategy is not None:
                set_clauses.append("default_chunking_strategy = %s")
                values.append(chunking_strategy)
            if chunk_size is not None:
                set_clauses.append("default_chunk_size = %s")
                values.append(chunk_size)
            if chunk_overlap is not None:
                set_clauses.append("chunk_overlap = %s")
                values.append(chunk_overlap)
            if embedding_model is not None:
                set_clauses.append("default_embedding_model = %s")
                values.append(embedding_model)
            if parsing_mode is not None:
                set_clauses.append("parsing_mode = %s")
                values.append(parsing_mode)
            if result_type is not None:
                set_clauses.append("result_type = %s")
                values.append(result_type)
            if language is not None:
                set_clauses.append("language = %s")
                values.append(language)
            if use_vendor_multimodal is not None:
                set_clauses.append("use_vendor_multimodal = %s")
                values.append(use_vendor_multimodal)
            if page_separator is not None:
                set_clauses.append("page_separator = %s")
                values.append(page_separator)
            if semantic_buffer_size is not None:
                set_clauses.append("semantic_buffer_size = %s")
                values.append(semantic_buffer_size)
            if pinecone_environment is not None:
                set_clauses.append("pinecone_environment = %s")
                values.append(pinecone_environment)
            if default_namespace is not None:
                set_clauses.append("default_namespace = %s")
                values.append(default_namespace)
            if active is not None:
                set_clauses.append("active = %s")
                values.append(active)
            
            values.append(product_id)
            
            cur.execute(
                f"UPDATE products SET {', '.join(set_clauses)} WHERE id = %s",
                values
            )
            conn.commit()
    finally:
        conn.close()

def delete_product(product_id: int):
    """Delete a product."""
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM products WHERE id = %s", (product_id,))
            conn.commit()
    finally:
        conn.close()

def get_product_api_keys(product_id: int) -> Dict:
    """Get API keys and credentials for a product from environment variables."""
    product = get_product(product_id)
    if not product:
        return {}
    
    api_keys = {}
    
    if product.get('llamaparse_api_key_secret'):
        api_keys['LLAMA_CLOUD_API_KEY'] = os.getenv(product['llamaparse_api_key_secret'], '')
    
    if product.get('openai_api_key_secret'):
        api_keys['OPENAI_API_KEY'] = os.getenv(product['openai_api_key_secret'], '')
    
    if product.get('pinecone_api_key_secret'):
        api_keys['PINECONE_API_KEY'] = os.getenv(product['pinecone_api_key_secret'], '')
    
    if product.get('google_credentials_secret'):
        google_creds_json = os.getenv(product['google_credentials_secret'], '')
        if google_creds_json:
            try:
                api_keys['GOOGLE_CREDENTIALS'] = json.loads(google_creds_json)
            except json.JSONDecodeError:
                api_keys['GOOGLE_CREDENTIALS'] = None
    
    return api_keys

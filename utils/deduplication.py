"""
Robust deduplication system for PDF processing pipeline.

This module implements a two-layer deduplication approach with self-healing capabilities:
- Layer 1: Drive File ID check in processed_papers table (fast, primary)
- Layer 2: Content hash comparison (title + authors fallback)

The system uses a 4-state check to handle edge cases and timeouts:
1. In processed_papers + has uploaded chunks → SKIP (complete)
2. In processed_papers but NO uploaded chunks → REPROCESS (previous failure)
3. NOT in processed_papers but HAS uploaded chunks → SKIP + backfill (timeout recovery)
4. NOT in processed_papers and NO uploaded chunks → PROCESS (new paper)

This approach ensures:
- Duplicates are detected BEFORE expensive processing
- System self-heals from timeouts and inconsistent states
- Database and Pinecone stay synchronized
"""

import hashlib
import logging
from typing import Dict, Optional, Tuple
from utils.db.connection import get_db_connection
import psycopg2.extras

logger = logging.getLogger(__name__)


def generate_content_hash(paper_title: str, authors: str) -> str:
    """
    Generate a content hash from paper title and authors.
    
    Args:
        paper_title: Paper title
        authors: Paper authors
        
    Returns:
        SHA256 hash of normalized title and authors
    """
    normalized_title = paper_title.lower().strip() if paper_title else ""
    normalized_authors = authors.lower().strip() if authors else ""
    
    content = f"{normalized_title}|{normalized_authors}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def check_in_processed_papers(drive_file_id: str, product_id: Optional[int] = None) -> Optional[Dict]:
    """
    Check if paper exists in processed_papers table.
    
    Args:
        drive_file_id: Google Drive file ID
        product_id: Optional product ID for product-scoped check
        
    Returns:
        Paper data dict if found, None otherwise
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        if product_id is not None:
            query = """
                SELECT id, drive_file_id, paper_title, authors, created_at, product_id
                FROM processed_papers
                WHERE drive_file_id = %s AND product_id = %s
                LIMIT 1
            """
            cur.execute(query, (drive_file_id, product_id))
        else:
            query = """
                SELECT id, drive_file_id, paper_title, authors, created_at, product_id
                FROM processed_papers
                WHERE drive_file_id = %s AND product_id IS NULL
                LIMIT 1
            """
            cur.execute(query, (drive_file_id,))
        
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
        
    finally:
        cur.close()
        conn.close()


def check_has_uploaded_chunks(drive_file_id: str, namespace: Optional[str] = None) -> bool:
    """
    Check if paper has uploaded chunks in processing_chunks table.
    
    For product-scoped deduplication, this checks by file_id AND namespace
    to prevent cross-product false positives.
    
    Args:
        drive_file_id: Google Drive file ID
        namespace: Optional Pinecone namespace (product-specific)
        
    Returns:
        True if uploaded chunks exist, False otherwise
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if namespace:
            # Product-scoped check: file_id AND namespace
            query = """
                SELECT COUNT(*) as count
                FROM processing_chunks
                WHERE file_id = %s 
                  AND namespace = %s 
                  AND embedding_stored = TRUE
            """
            cur.execute(query, (drive_file_id, namespace))
        else:
            # Legacy global check: file_id only
            query = """
                SELECT COUNT(*) as count
                FROM processing_chunks
                WHERE file_id = %s AND embedding_stored = TRUE
            """
            cur.execute(query, (drive_file_id,))
        
        result = cur.fetchone()
        return result[0] > 0 if result else False
        
    finally:
        cur.close()
        conn.close()


def backfill_processed_paper(
    drive_file_id: str, 
    product_id: Optional[int] = None,
    namespace: str = 'default'
):
    """
    Backfill a missing processed_papers record (State 3: timeout recovery).
    
    This happens when:
    - Upload to Pinecone succeeded
    - Job timed out before marking in processed_papers
    - Next run detects uploaded chunks but no processed_papers record
    
    Tries to hydrate metadata from existing chunks to create accurate record.
    
    Args:
        drive_file_id: Google Drive file ID
        product_id: Optional product ID
        namespace: Pinecone namespace (defaults to 'default')
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Try to get metadata from existing chunks
        cur.execute("""
            SELECT metadata, namespace
            FROM processing_chunks
            WHERE file_id = %s AND namespace = %s AND embedding_stored = TRUE
            LIMIT 1
        """, (drive_file_id, namespace))
        
        chunk_row = cur.fetchone()
        
        if chunk_row and chunk_row[0]:
            # Hydrate from chunk metadata
            chunk_metadata = chunk_row[0]
            actual_namespace = chunk_row[1] or namespace
            paper_title = chunk_metadata.get('paper_title', chunk_metadata.get('title', 'Backfilled record'))
            authors = chunk_metadata.get('authors', '')
            content_hash = generate_content_hash(paper_title, authors)
        else:
            # Minimal fallback
            paper_title = 'Backfilled record'
            authors = ''
            content_hash = ''
            actual_namespace = namespace
            chunk_metadata = {}
        
        # Create backfilled record with best available metadata
        query = """
            INSERT INTO processed_papers
            (drive_file_id, content_hash, paper_title, authors, metadata, 
             pinecone_namespace, product_id, metadata_json)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (drive_file_id, product_id) DO NOTHING
        """
        
        cur.execute(query, (
            drive_file_id,
            content_hash,
            paper_title,
            authors,
            chunk_metadata,
            actual_namespace,
            product_id,
            chunk_metadata
        ))
        
        conn.commit()
        logger.info(
            f"✅ Backfilled processed_papers record for {drive_file_id}\n"
            f"   Product ID: {product_id}\n"
            f"   Namespace: {actual_namespace}\n"
            f"   Title: {paper_title}"
        )
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Failed to backfill processed_papers: {e}")
        
    finally:
        cur.close()
        conn.close()


def remove_from_processed_papers(drive_file_id: str, product_id: Optional[int] = None):
    """
    Remove a paper from processed_papers (State 2: cleanup before reprocessing).
    
    This happens when:
    - Paper is in processed_papers
    - But has no uploaded chunks (upload failed or chunks were deleted)
    - Need to clean up before reprocessing
    
    Args:
        drive_file_id: Google Drive file ID
        product_id: Optional product ID
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        if product_id is not None:
            query = "DELETE FROM processed_papers WHERE drive_file_id = %s AND product_id = %s"
            cur.execute(query, (drive_file_id, product_id))
        else:
            query = "DELETE FROM processed_papers WHERE drive_file_id = %s AND product_id IS NULL"
            cur.execute(query, (drive_file_id,))
        
        conn.commit()
        logger.info(f"🗑️  Removed incomplete record from processed_papers: {drive_file_id} (product_id={product_id})")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Failed to remove from processed_papers: {e}")
        
    finally:
        cur.close()
        conn.close()


def check_by_content_hash(paper_title: str, authors: str, product_id: Optional[int] = None) -> Optional[Dict]:
    """
    Check if paper exists by content hash (Layer 2 fallback).
    
    This catches cases where the Drive link changed but it's the same paper.
    
    Args:
        paper_title: Paper title
        authors: Paper authors
        product_id: Optional product ID
        
    Returns:
        Paper data dict if found, None otherwise
    """
    if not paper_title and not authors:
        return None
    
    content_hash = generate_content_hash(paper_title, authors)
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        if product_id is not None:
            query = """
                SELECT id, drive_file_id, paper_title, authors, created_at, product_id
                FROM processed_papers
                WHERE content_hash = %s AND product_id = %s
                LIMIT 1
            """
            cur.execute(query, (content_hash, product_id))
        else:
            query = """
                SELECT id, drive_file_id, paper_title, authors, created_at, product_id
                FROM processed_papers
                WHERE content_hash = %s AND product_id IS NULL
                LIMIT 1
            """
            cur.execute(query, (content_hash,))
        
        row = cur.fetchone()
        if row:
            return dict(row)
        return None
        
    finally:
        cur.close()
        conn.close()


def should_process_paper(
    drive_file_id: str,
    paper_title: str,
    authors: str,
    product_id: Optional[int] = None,
    namespace: str = 'default',
    enable_layer1: bool = True,
    enable_layer2: bool = True
) -> Dict:
    """
    Determine if a paper should be processed using 4-state robust check.
    
    States:
    1. In processed_papers + has uploaded chunks → SKIP (already complete)
    2. In processed_papers but NO uploaded chunks → REPROCESS (previous failure, clean up first)
    3. NOT in processed_papers but HAS uploaded chunks → SKIP + backfill (timeout recovery)
    4. NOT in processed_papers and NO uploaded chunks → PROCESS (truly new)
    
    Args:
        drive_file_id: Google Drive file ID
        paper_title: Paper title
        authors: Paper authors
        product_id: Optional product ID for product-scoped deduplication
        namespace: Pinecone namespace (product-specific, defaults to 'default')
        enable_layer1: Enable Drive File ID check
        enable_layer2: Enable content hash check
        
    Returns:
        {
            'should_process': bool,
            'reason': str,
            'state': str ('state1'|'state2'|'state3'|'state4'),
            'duplicate_layer': str or None,
            'existing_paper': dict or None,
            'content_hash': str
        }
    """
    content_hash = generate_content_hash(paper_title, authors)
    
    # Layer 1: Check by Drive File ID (with product-scoped chunk check)
    if enable_layer1:
        in_processed = check_in_processed_papers(drive_file_id, product_id)
        has_chunks = check_has_uploaded_chunks(drive_file_id, namespace)
        
        # State 1: Complete (in DB + has chunks)
        if in_processed and has_chunks:
            return {
                'should_process': False,
                'reason': 'Already processed and uploaded',
                'state': 'state1',
                'duplicate_layer': 'layer1_file_id',
                'existing_paper': in_processed,
                'content_hash': content_hash
            }
        
        # State 2: Incomplete (in DB but no chunks - previous failure)
        if in_processed and not has_chunks:
            logger.warning(
                f"⚠️  Paper {drive_file_id} in processed_papers but no uploaded chunks. "
                f"Cleaning up and reprocessing..."
            )
            remove_from_processed_papers(drive_file_id, product_id)
            return {
                'should_process': True,
                'reason': 'Reprocessing (previous upload failed)',
                'state': 'state2',
                'duplicate_layer': None,
                'existing_paper': None,
                'content_hash': content_hash
            }
        
        # State 3: Timeout recovery (not in DB but has chunks)
        if not in_processed and has_chunks:
            logger.info(
                f"✅ Paper {drive_file_id} has uploaded chunks but not in processed_papers. "
                f"Backfilling record (namespace={namespace})..."
            )
            backfill_processed_paper(drive_file_id, product_id, namespace)
            return {
                'should_process': False,
                'reason': 'Already uploaded (backfilled record)',
                'state': 'state3',
                'duplicate_layer': 'layer1_file_id_backfilled',
                'existing_paper': {'drive_file_id': drive_file_id, 'product_id': product_id},
                'content_hash': content_hash
            }
    
    # Layer 2: Check by content hash (fallback for same paper, different Drive link)
    if enable_layer2:
        existing = check_by_content_hash(paper_title, authors, product_id)
        if existing:
            return {
                'should_process': False,
                'reason': f"Duplicate content (same title/authors, different Drive link)",
                'state': 'state1',
                'duplicate_layer': 'layer2_content_hash',
                'existing_paper': existing,
                'content_hash': content_hash
            }
    
    # State 4: New paper (not in DB, no chunks)
    return {
        'should_process': True,
        'reason': 'New paper',
        'state': 'state4',
        'duplicate_layer': None,
        'existing_paper': None,
        'content_hash': content_hash
    }


def record_processed_paper(
    drive_file_id: str,
    content_hash: str,
    paper_title: str,
    authors: str,
    metadata: Dict,
    pinecone_namespace: str,
    metadata_fingerprint: Optional[str] = None,
    product_id: Optional[int] = None
) -> int:
    """
    Record a successfully processed paper in processed_papers table.
    
    IMPORTANT: Only call this AFTER confirming Pinecone upload succeeded.
    
    Args:
        drive_file_id: Google Drive file ID
        content_hash: SHA256 hash of title + authors
        paper_title: Paper title
        authors: Paper authors
        metadata: Paper metadata
        pinecone_namespace: Pinecone namespace
        metadata_fingerprint: Optional metadata fingerprint
        product_id: Optional product ID
        
    Returns:
        Paper ID
    """
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        query = """
            INSERT INTO processed_papers
            (drive_file_id, content_hash, paper_title, authors, metadata, 
             pinecone_namespace, metadata_fingerprint, metadata_json, product_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (drive_file_id, product_id) 
            DO UPDATE SET
                content_hash = EXCLUDED.content_hash,
                paper_title = EXCLUDED.paper_title,
                authors = EXCLUDED.authors,
                metadata = EXCLUDED.metadata,
                metadata_json = EXCLUDED.metadata_json,
                metadata_fingerprint = EXCLUDED.metadata_fingerprint,
                updated_at = CURRENT_TIMESTAMP
            RETURNING id
        """
        
        cur.execute(query, (
            drive_file_id,
            content_hash,
            paper_title,
            authors,
            metadata,
            pinecone_namespace,
            metadata_fingerprint,
            metadata,
            product_id
        ))
        
        paper_id = cur.fetchone()[0]
        conn.commit()
        
        logger.info(f"✅ Recorded processed paper: {drive_file_id} (product_id={product_id})")
        return paper_id
        
    except Exception as e:
        conn.rollback()
        logger.error(f"❌ Failed to record processed paper: {e}")
        raise
        
    finally:
        cur.close()
        conn.close()

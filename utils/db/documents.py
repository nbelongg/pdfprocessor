"""
Parsed documents and deduplication database operations.

This module handles:
- Parsed document storage and retrieval
- AI-generated tag management  
- Document deduplication tracking
- Content hash lookups
"""

import logging
from typing import Dict, List, Optional, Any
from psycopg2.extras import Json

from utils.exceptions import DatabaseError, DatabaseTransientError
from utils.db_utils import get_db_transaction, with_db_error_handling
from utils.db.connection import get_db_connection, _row_to_dict

logger = logging.getLogger(__name__)


# ===== Parsed Documents =====

@with_db_error_handling
def save_parsed_document(file_id: str, filename: str, parsed_text: str, 
                         parsing_config: Dict = None, file_metadata: Dict = None,
                         sheet_metadata: Dict = None):
    """
    Save raw parsed text from LlamaParse for future re-processing (as JSON).
    
    Args:
        file_id: Google Drive file ID
        filename: PDF filename
        parsed_text: Parsed text from LlamaParse
        parsing_config: LlamaParse configuration used
        file_metadata: Google Drive file metadata (size, dates, etc.)
        sheet_metadata: Google Sheets row metadata (title, authors, year, topic, etc.)
    
    The file_metadata JSONB column will contain merged data:
    - Google Drive metadata (id, name, size, mimeType, createdTime, modifiedTime)
    - Google Sheets metadata (paper_title, authors, publication_year, topic, drive_link, etc.)
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            # Convert parsed text to JSON structure
            if isinstance(parsed_text, str):
                parsed_json = {
                    'text': parsed_text,
                    'format': 'text',
                    'length': len(parsed_text)
                }
            else:
                # If already a dict/object, use as-is
                parsed_json = parsed_text
            
            # Merge Google Drive metadata with Google Sheets metadata
            merged_metadata = {}
            
            # Start with Google Drive metadata (base layer)
            if file_metadata:
                merged_metadata.update(file_metadata)
            
            # Add/override with Google Sheets metadata (enrichment layer)
            if sheet_metadata:
                merged_metadata.update(sheet_metadata)
            
            # Ensure we have a drive_url constructed from file_id
            if file_id and 'drive_url' not in merged_metadata:
                merged_metadata['drive_url'] = f"https://drive.google.com/file/d/{file_id}/view"
            
            cur.execute(
                """
                INSERT INTO parsed_documents 
                (file_id, filename, parsed_text, parse_mode, result_type, parsing_config, file_metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (file_id) 
                DO UPDATE SET 
                    parsed_text = EXCLUDED.parsed_text,
                    filename = EXCLUDED.filename,
                    parse_mode = EXCLUDED.parse_mode,
                    result_type = EXCLUDED.result_type,
                    parsing_config = EXCLUDED.parsing_config,
                    file_metadata = EXCLUDED.file_metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    file_id,
                    filename,
                    Json(parsed_json),
                    parsing_config.get('parsing_mode') if parsing_config else None,
                    parsing_config.get('result_type') if parsing_config else None,
                    Json(parsing_config) if parsing_config else None,
                    Json(merged_metadata) if merged_metadata else None
                )
            )


@with_db_error_handling
def get_parsed_document(file_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve raw parsed text for a file (returns JSON)."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM parsed_documents WHERE file_id = %s",
                (file_id,)
            )
            return _row_to_dict(cur.fetchone())


def get_parsed_text_for_rechunking(file_id: str) -> Optional[str]:
    """
    Retrieve the parsed text string for re-chunking/re-embedding.
    Extracts the 'text' field from the JSON.
    """
    doc = get_parsed_document(file_id)
    if not doc:
        return None
    
    parsed_json = doc.get('parsed_text', {})
    
    # If it's stored as JSON with 'text' field
    if isinstance(parsed_json, dict) and 'text' in parsed_json:
        return parsed_json['text']
    # If it's just a string (shouldn't happen with new format, but handle legacy)
    elif isinstance(parsed_json, str):
        return parsed_json
    else:
        # Try to extract text from any structure
        return str(parsed_json)


@with_db_error_handling
def get_all_parsed_documents(limit: int = 100) -> List[Dict[str, Any]]:
    """Get list of all parsed documents."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT file_id, filename, 
                       jsonb_typeof(parsed_text) as json_type,
                       CASE 
                           WHEN parsed_text ? 'text' THEN LENGTH(parsed_text->>'text')
                           ELSE 0
                       END as text_length,
                       tags,
                       tagging_completed,
                       tagging_model_used,
                       parse_mode, result_type,
                       created_at, updated_at
                FROM parsed_documents
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (limit,)
            )
            return [dict(row) for row in cur.fetchall()]


# ===== AI Tagging =====

@with_db_error_handling
def update_document_tags(file_id: str, tags: List[str], model_used: str):
    """
    Update tags for a parsed document.
    
    Args:
        file_id: Google Drive file ID
        tags: List of tag strings
        model_used: OpenAI model used for tagging
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE parsed_documents 
                SET tags = %s,
                    tagging_completed = TRUE,
                    tagging_model_used = %s,
                    tagging_timestamp = CURRENT_TIMESTAMP
                WHERE file_id = %s
                """,
                (Json(tags), model_used, file_id)
            )


def get_document_tags(file_id: str) -> List[str]:
    """
    Get tags for a parsed document.
    
    Args:
        file_id: Google Drive file ID
        
    Returns:
        List of tag strings, or empty list if no tags
    """
    doc = get_parsed_document(file_id)
    if not doc:
        return []
    
    tags = doc.get('tags', [])
    return tags if tags else []


def is_document_tagged(file_id: str) -> bool:
    """
    Check if a document has been tagged.
    
    Args:
        file_id: Google Drive file ID
        
    Returns:
        True if document has been tagged, False otherwise
    """
    doc = get_parsed_document(file_id)
    if not doc:
        return False
    
    return doc.get('tagging_completed', False)


# ===== Deduplication =====

@with_db_error_handling
def check_paper_processed(drive_file_id: str) -> Optional[Dict[str, Any]]:
    """Check if a paper has been processed before by Drive file ID."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM processed_papers WHERE drive_file_id = %s",
                (drive_file_id,)
            )
            return _row_to_dict(cur.fetchone())


@with_db_error_handling
def check_paper_by_content_hash(content_hash: str) -> Optional[Dict[str, Any]]:
    """Check if a paper has been processed before by content hash."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM processed_papers WHERE content_hash = %s",
                (content_hash,)
            )
            return _row_to_dict(cur.fetchone())


@with_db_error_handling
def record_processed_paper(
    drive_file_id: str,
    content_hash: str,
    paper_title: str,
    authors: str,
    metadata: Dict,
    pinecone_namespace: str,
    source_id: int,
    row_number: int,
    metadata_fingerprint: str = None
) -> int:
    """Record a newly processed paper with optional metadata fingerprint."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_papers
                (drive_file_id, content_hash, paper_title, authors, metadata, pinecone_namespace, metadata_fingerprint, metadata_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (drive_file_id, content_hash, paper_title, authors, Json(metadata), pinecone_namespace, metadata_fingerprint, Json(metadata) if metadata_fingerprint else None)
            )
            paper_id = cur.fetchone()['id']
            
            cur.execute(
                """
                INSERT INTO source_paper_mapping (source_id, paper_id, row_number)
                VALUES (%s, %s, %s)
                """,
                (source_id, paper_id, row_number)
            )
            
            return paper_id


@with_db_error_handling
def update_processed_paper(paper_id: int, source_id: int, row_number: int):
    """Update existing processed paper (increment count, update timestamp)."""
    with get_db_transaction() as conn:
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


@with_db_error_handling
def get_deduplication_stats() -> Dict:
    """Get statistics about processed papers and deduplication."""
    with get_db_transaction() as conn:
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


@with_db_error_handling
def get_processed_identifiers_for_source(source_id: int) -> set:
    """
    Get all Drive File IDs and content hashes already processed for this source.
    
    This enables hash-based detection of new papers regardless of their position
    in the Google Sheet (handles mid-sheet insertions, reordering, etc.)
    
    Args:
        source_id: Data source ID
        
    Returns:
        Set of identifier strings (both drive_file_ids and content_hashes)
        
    Example:
        {'1a2b3c4d5e6f7g', '8h9i0j1k2l3m4n', 'abc123def456...'}
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            # Get all paper_ids for this source from mapping table
            cur.execute(
                """
                SELECT DISTINCT p.drive_file_id, p.content_hash
                FROM processed_papers p
                INNER JOIN source_paper_mapping spm ON p.id = spm.paper_id
                WHERE spm.source_id = %s
                """,
                (source_id,)
            )
            
            identifiers = set()
            for row in cur.fetchall():
                # Add drive_file_id if present
                if row['drive_file_id']:
                    identifiers.add(row['drive_file_id'])
                # Add content_hash if present
                if row['content_hash']:
                    identifiers.add(row['content_hash'])
            
            logger.info(f"Found {len(identifiers)} processed identifiers for source {source_id}")
            return identifiers


@with_db_error_handling
def update_processed_paper_fingerprint(
    file_id: str,
    metadata_fingerprint: str,
    metadata_json: Dict[str, Any]
):
    """
    Update the metadata fingerprint and JSON for a processed paper.
    
    Used after metadata-only updates to track the new metadata state.
    
    Args:
        file_id: Google Drive file ID
        metadata_fingerprint: New SHA256 fingerprint of metadata
        metadata_json: New metadata dictionary
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE processed_papers
                SET metadata_fingerprint = %s,
                    metadata_json = %s,
                    last_processed_at = CURRENT_TIMESTAMP
                WHERE drive_file_id = %s
                """,
                (metadata_fingerprint, Json(metadata_json), file_id)
            )
            logger.info(f"Updated metadata fingerprint for file_id: {file_id}")

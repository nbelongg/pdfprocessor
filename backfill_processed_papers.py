#!/usr/bin/env python3
"""
Backfill processed_papers table with records for PDFs that completed processing
but never got deduplication records due to Celery timeout failures.

This script:
1. Finds all file_ids in processing_chunks (PDFs that were chunked/uploaded)
2. Checks which ones are missing from processed_papers
3. Backfills missing records using metadata from parsed_documents
4. Creates proper deduplication records to prevent reprocessing

Usage:
    python backfill_processed_papers.py --dry-run   # Preview changes (default)
    python backfill_processed_papers.py --execute   # Apply changes

Safety:
    - Idempotent: Safe to run multiple times
    - Dry-run by default: Shows what would change
    - Non-destructive: Only adds records, never deletes
"""

import argparse
import sys
from datetime import datetime
from typing import Dict, List, Set
from utils.db.connection import get_db_connection
from utils.deduplication import generate_content_hash
from utils.metadata_fingerprint import calculate_metadata_fingerprint
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_processed_file_ids() -> Set[str]:
    """Get all file_ids that have chunks in processing_chunks table."""
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("""
            SELECT DISTINCT file_id 
            FROM processing_chunks
            WHERE file_id IS NOT NULL
            ORDER BY file_id
        """)
        
        file_ids = {row['file_id'] for row in cur.fetchall()}
        logger.info(f"Found {len(file_ids)} unique file_ids in processing_chunks")
        return file_ids
        
    finally:
        cur.close()
        conn.close()


def get_existing_processed_papers() -> Set[str]:
    """Get all drive_file_ids already in processed_papers table."""
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("""
            SELECT DISTINCT drive_file_id 
            FROM processed_papers
            WHERE drive_file_id IS NOT NULL
            ORDER BY drive_file_id
        """)
        
        file_ids = {row['drive_file_id'] for row in cur.fetchall()}
        logger.info(f"Found {len(file_ids)} existing records in processed_papers")
        return file_ids
        
    finally:
        cur.close()
        conn.close()


def get_parsed_document_metadata(file_id: str) -> Dict:
    """Get metadata for a file_id from parsed_documents table."""
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("""
            SELECT 
                file_id,
                filename,
                file_metadata,
                created_at
            FROM parsed_documents
            WHERE file_id = %s
        """, (file_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            'file_id': row['file_id'],
            'filename': row['filename'],
            'file_metadata': row['file_metadata'] or {},
            'created_at': row['created_at']
        }
        
    finally:
        cur.close()
        conn.close()


def get_chunk_info(file_id: str) -> Dict:
    """Get chunk information (namespace, source) for a file_id."""
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("""
            SELECT 
                namespace,
                metadata,
                created_at
            FROM processing_chunks
            WHERE file_id = %s
            LIMIT 1
        """, (file_id,))
        
        row = cur.fetchone()
        if not row:
            return None
        
        return {
            'namespace': row['namespace'],
            'chunk_metadata': row['metadata'] or {},
            'chunk_created_at': row['created_at']
        }
        
    finally:
        cur.close()
        conn.close()


def create_processed_paper_record(file_id: str, metadata: Dict, chunk_info: Dict, dry_run: bool = True) -> bool:
    """
    Create a processed_papers record for a file that completed processing.
    
    Args:
        file_id: Google Drive file ID
        metadata: Metadata from parsed_documents
        chunk_info: Information from processing_chunks
        dry_run: If True, only log what would be done
        
    Returns:
        True if successful, False otherwise
    """
    file_metadata = metadata.get('file_metadata', {})
    chunk_metadata = chunk_info.get('chunk_metadata', {})
    
    # Extract metadata fields (prefer parsed_documents, fallback to chunk metadata)
    paper_title = (
        file_metadata.get('paper_title') or 
        chunk_metadata.get('paper_title') or 
        metadata.get('filename', 'Unknown')
    )
    
    authors = (
        file_metadata.get('authors') or 
        chunk_metadata.get('authors') or 
        ''
    )
    
    # Get source information from chunk metadata
    source_id = chunk_metadata.get('source_id')
    source_name = chunk_metadata.get('source', 'Unknown')
    
    # Generate content hash for deduplication
    content_hash = generate_content_hash(paper_title, authors)
    
    # Get namespace from chunks
    namespace = chunk_info.get('namespace', 'default')
    
    # Build complete metadata for fingerprint calculation
    complete_metadata = {
        'paper_title': paper_title,
        'authors': authors,
        'publication_year': file_metadata.get('publication_year') or chunk_metadata.get('publication_year'),
        'topic': file_metadata.get('topic') or chunk_metadata.get('topic'),
        'source': source_name,
        'source_id': source_id,
    }
    
    # Calculate metadata fingerprint
    metadata_fingerprint = calculate_metadata_fingerprint(complete_metadata)
    
    # Use earliest timestamp (when chunks were created)
    created_at = chunk_info.get('chunk_created_at') or metadata.get('created_at')
    
    if dry_run:
        logger.info(f"\n[DRY-RUN] Would create processed_papers record:")
        logger.info(f"  File ID: {file_id}")
        logger.info(f"  Title: {paper_title[:60]}...")
        logger.info(f"  Authors: {authors[:60]}...")
        logger.info(f"  Content Hash: {content_hash}")
        logger.info(f"  Namespace: {namespace}")
        logger.info(f"  Source: {source_name} (ID: {source_id})")
        logger.info(f"  Fingerprint: {metadata_fingerprint[:16]}...")
        return True
    
    # Actually create the record
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Insert into processed_papers
        cur.execute("""
            INSERT INTO processed_papers (
                drive_file_id,
                content_hash,
                paper_title,
                authors,
                metadata,
                pinecone_namespace,
                processed_at,
                metadata_fingerprint
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (drive_file_id) DO NOTHING
            RETURNING id
        """, (
            file_id,
            content_hash,
            paper_title,
            authors,
            complete_metadata,
            namespace,
            created_at,
            metadata_fingerprint
        ))
        
        result = cur.fetchone()
        if result:
            paper_id = result['id']
            logger.info(f"✅ Created processed_papers record (ID: {paper_id}) for {file_id}")
            
            # Create source_paper_mapping if we have source_id
            if source_id:
                cur.execute("""
                    INSERT INTO source_paper_mapping (
                        source_id,
                        paper_id,
                        row_number,
                        created_at
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (source_id, paper_id) DO NOTHING
                """, (
                    source_id,
                    paper_id,
                    0,  # Row number unknown, use 0
                    created_at
                ))
                logger.info(f"✅ Created source_paper_mapping for source {source_id}")
            
            conn.commit()
            return True
        else:
            logger.warning(f"⚠️ Record already exists for {file_id}, skipped")
            conn.rollback()
            return False
        
    except Exception as e:
        logger.error(f"❌ Error creating record for {file_id}: {e}")
        conn.rollback()
        return False
        
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Backfill processed_papers table with missing records',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview what would be backfilled (safe, read-only)
  python backfill_processed_papers.py --dry-run
  
  # Actually backfill the missing records
  python backfill_processed_papers.py --execute
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview changes without applying them (default)'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually apply the changes to the database'
    )
    
    args = parser.parse_args()
    
    # Determine mode
    dry_run = not args.execute
    
    if dry_run:
        logger.info("=" * 80)
        logger.info("DRY-RUN MODE: No changes will be made to the database")
        logger.info("=" * 80)
    else:
        logger.info("=" * 80)
        logger.info("EXECUTE MODE: Changes will be applied to the database")
        logger.info("=" * 80)
    
    print()
    
    # Step 1: Get all file_ids with chunks
    logger.info("📊 Step 1: Finding all PDFs that have chunks...")
    processed_file_ids = get_processed_file_ids()
    
    # Step 2: Get existing processed_papers records
    logger.info("📊 Step 2: Finding existing processed_papers records...")
    existing_papers = get_existing_processed_papers()
    
    # Step 3: Find missing records
    missing_file_ids = processed_file_ids - existing_papers
    logger.info(f"\n📊 Step 3: Analysis complete!")
    logger.info(f"  Total PDFs with chunks: {len(processed_file_ids)}")
    logger.info(f"  Already in processed_papers: {len(existing_papers)}")
    logger.info(f"  Missing from processed_papers: {len(missing_file_ids)}")
    
    if not missing_file_ids:
        logger.info("\n✅ All processed PDFs already have deduplication records!")
        logger.info("   Nothing to backfill.")
        return 0
    
    # Step 4: Backfill missing records
    logger.info(f"\n📊 Step 4: Backfilling {len(missing_file_ids)} missing records...")
    print()
    
    success_count = 0
    error_count = 0
    skip_count = 0
    
    for idx, file_id in enumerate(sorted(missing_file_ids), 1):
        logger.info(f"\n[{idx}/{len(missing_file_ids)}] Processing {file_id}...")
        
        # Get metadata from parsed_documents
        metadata = get_parsed_document_metadata(file_id)
        if not metadata:
            logger.warning(f"⚠️ No parsed_document found for {file_id}, skipping")
            skip_count += 1
            continue
        
        # Get chunk info
        chunk_info = get_chunk_info(file_id)
        if not chunk_info:
            logger.warning(f"⚠️ No chunks found for {file_id}, skipping")
            skip_count += 1
            continue
        
        # Create record
        if create_processed_paper_record(file_id, metadata, chunk_info, dry_run):
            success_count += 1
        else:
            error_count += 1
    
    # Summary
    print()
    logger.info("=" * 80)
    logger.info("BACKFILL SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total missing records:     {len(missing_file_ids)}")
    logger.info(f"Successfully backfilled:   {success_count}")
    logger.info(f"Skipped (no metadata):     {skip_count}")
    logger.info(f"Errors:                    {error_count}")
    logger.info("=" * 80)
    
    if dry_run:
        logger.info("\n💡 This was a DRY-RUN. No changes were made to the database.")
        logger.info("   To apply these changes, run with --execute flag:")
        logger.info("   python backfill_processed_papers.py --execute")
    else:
        logger.info(f"\n✅ Backfill completed successfully!")
        logger.info(f"✅ {success_count} records added to processed_papers table")
        logger.info(f"✅ Your deduplication system is now complete!")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

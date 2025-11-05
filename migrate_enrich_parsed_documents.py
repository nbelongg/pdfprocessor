#!/usr/bin/env python3
"""
Migration Script: Enrich parsed_documents with Google Sheets Metadata

This script backfills the file_metadata JSONB column in parsed_documents table
with rich metadata from processed_papers table (paper_title, authors, publication_year, 
topic, drive_link, etc.).

Usage:
    python migrate_enrich_parsed_documents.py --dry-run  # Preview changes
    python migrate_enrich_parsed_documents.py --execute  # Apply changes

Safety Features:
- Dry-run mode by default
- Shows detailed preview of changes
- Safe to run multiple times (idempotent)
- Preserves existing file_metadata (merges, doesn't overwrite)
"""

import os
import sys
import logging
import argparse
from typing import Dict, List, Any
from psycopg2.extras import Json

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db_utils import get_db_transaction

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_parsed_documents_without_enrichment() -> List[Dict[str, Any]]:
    """
    Get all parsed_documents that don't have Google Sheets metadata yet.
    Returns list of dicts with file_id and current file_metadata.
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    pd.file_id,
                    pd.filename,
                    pd.file_metadata
                FROM parsed_documents pd
                ORDER BY pd.created_at
            """)
            
            results = []
            for row in cur.fetchall():
                results.append({
                    'file_id': row['file_id'],
                    'filename': row['filename'],
                    'file_metadata': row['file_metadata'] or {}
                })
            
            return results


def get_processed_paper_metadata(file_id: str) -> Dict[str, Any]:
    """
    Get Google Sheets metadata for a file from processed_papers table.
    Returns enriched metadata dict or None if not found.
    """
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    paper_title,
                    authors,
                    metadata,
                    pinecone_namespace,
                    first_processed_at,
                    processing_count
                FROM processed_papers
                WHERE drive_file_id = %s
                LIMIT 1
            """, (file_id,))
            
            row = cur.fetchone()
            if not row:
                return None
            
            # Extract metadata from the row
            enrichment = {}
            
            # Add structured fields
            if row['paper_title']:
                enrichment['paper_title'] = row['paper_title']
            if row['authors']:
                enrichment['authors'] = row['authors']
            
            # Merge the full metadata JSONB
            if row['metadata']:
                enrichment.update(row['metadata'])
            
            # Add processing info
            enrichment['pinecone_namespace'] = row['pinecone_namespace']
            enrichment['first_processed_at'] = row['first_processed_at'].isoformat() if row['first_processed_at'] else None
            enrichment['processing_count'] = row['processing_count']
            
            # Ensure drive_url is present
            enrichment['drive_url'] = enrichment.get('drive_link') or f"https://drive.google.com/file/d/{file_id}/view"
            
            return enrichment


def merge_metadata(base: Dict, enrichment: Dict) -> Dict:
    """
    Merge enrichment metadata into base metadata.
    Google Sheets metadata takes precedence over Google Drive metadata.
    """
    merged = base.copy()
    merged.update(enrichment)
    return merged


def update_parsed_document_metadata(file_id: str, merged_metadata: Dict, dry_run: bool = True) -> bool:
    """
    Update the file_metadata JSONB column for a parsed document.
    
    Args:
        file_id: Google Drive file ID
        merged_metadata: Complete merged metadata dict
        dry_run: If True, don't actually update (just log what would happen)
    
    Returns:
        True if update would succeed/succeeded
    """
    if dry_run:
        logger.info(f"  [DRY-RUN] Would update file_id={file_id} with {len(merged_metadata)} metadata fields")
        return True
    
    try:
        with get_db_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE parsed_documents
                    SET file_metadata = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE file_id = %s
                """, (Json(merged_metadata), file_id))
                
                if cur.rowcount > 0:
                    logger.info(f"  ✅ Updated file_id={file_id}")
                    return True
                else:
                    logger.warning(f"  ⚠️  No rows updated for file_id={file_id}")
                    return False
    except Exception as e:
        logger.error(f"  ❌ Failed to update file_id={file_id}: {str(e)}")
        return False


def run_migration(dry_run: bool = True):
    """
    Main migration logic: enrich parsed_documents with Google Sheets metadata.
    
    Args:
        dry_run: If True, show preview without making changes
    """
    logger.info("=" * 80)
    logger.info("MIGRATION: Enrich parsed_documents with Google Sheets Metadata")
    logger.info("=" * 80)
    logger.info(f"Mode: {'DRY-RUN (preview only)' if dry_run else 'EXECUTE (will modify database)'}")
    logger.info("")
    
    # Get all parsed documents
    logger.info("Step 1: Fetching all parsed documents...")
    parsed_docs = get_parsed_documents_without_enrichment()
    logger.info(f"Found {len(parsed_docs)} parsed documents")
    logger.info("")
    
    # Process each document
    stats = {
        'total': len(parsed_docs),
        'enriched': 0,
        'not_found': 0,
        'already_rich': 0,
        'errors': 0
    }
    
    logger.info("Step 2: Enriching documents with Google Sheets metadata...")
    logger.info("")
    
    for i, doc in enumerate(parsed_docs, 1):
        file_id = doc['file_id']
        filename = doc['filename']
        current_metadata = doc['file_metadata']
        
        logger.info(f"[{i}/{len(parsed_docs)}] Processing: {filename} (file_id={file_id[:20]}...)")
        
        # Check if already has Google Sheets metadata
        has_paper_title = 'paper_title' in current_metadata
        has_authors = 'authors' in current_metadata
        has_publication_year = 'publication_year' in current_metadata
        
        if has_paper_title and has_authors:
            logger.info(f"  ℹ️  Already enriched (has paper_title and authors) - skipping")
            stats['already_rich'] += 1
            continue
        
        # Get enrichment from processed_papers
        enrichment = get_processed_paper_metadata(file_id)
        
        if not enrichment:
            logger.warning(f"  ⚠️  No match found in processed_papers table - skipping")
            stats['not_found'] += 1
            continue
        
        # Show what we found
        logger.info(f"  📊 Found metadata:")
        logger.info(f"     - paper_title: {enrichment.get('paper_title', 'N/A')[:60]}...")
        logger.info(f"     - authors: {enrichment.get('authors', 'N/A')[:60]}...")
        logger.info(f"     - publication_year: {enrichment.get('publication_year', 'N/A')}")
        logger.info(f"     - topic: {enrichment.get('topic', 'N/A')}")
        logger.info(f"     - Total fields: {len(enrichment)}")
        
        # Merge metadata
        merged = merge_metadata(current_metadata, enrichment)
        
        # Update (or show what would be updated)
        success = update_parsed_document_metadata(file_id, merged, dry_run=dry_run)
        
        if success:
            stats['enriched'] += 1
        else:
            stats['errors'] += 1
        
        logger.info("")
    
    # Show summary
    logger.info("=" * 80)
    logger.info("MIGRATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Total documents:        {stats['total']}")
    logger.info(f"Successfully enriched:  {stats['enriched']}")
    logger.info(f"Already enriched:       {stats['already_rich']}")
    logger.info(f"Not found in DB:        {stats['not_found']}")
    logger.info(f"Errors:                 {stats['errors']}")
    logger.info("=" * 80)
    
    if dry_run:
        logger.info("")
        logger.info("🔍 This was a DRY-RUN. No changes were made to the database.")
        logger.info("🚀 To apply these changes, run with --execute flag:")
        logger.info("   python migrate_enrich_parsed_documents.py --execute")
    else:
        logger.info("")
        logger.info("✅ Migration completed successfully!")
        logger.info(f"✅ {stats['enriched']} documents enriched with Google Sheets metadata")


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Enrich parsed_documents with Google Sheets metadata from processed_papers',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes (safe, read-only)
  python migrate_enrich_parsed_documents.py --dry-run
  
  # Apply changes to database
  python migrate_enrich_parsed_documents.py --execute
        """
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without modifying database (default)'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually apply changes to database'
    )
    
    args = parser.parse_args()
    
    # Default to dry-run if neither flag specified
    if not args.execute:
        dry_run = True
    else:
        dry_run = False
    
    try:
        run_migration(dry_run=dry_run)
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Migration cancelled by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n\n❌ Migration failed with error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

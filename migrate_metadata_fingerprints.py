"""
Migration script to backfill metadata fingerprints for existing processed papers.

This script:
1. Fetches all processed papers without metadata fingerprints
2. Calculates fingerprints from their metadata_json field
3. Updates the database with the fingerprints

Run this once after deploying the metadata update feature.
"""

import logging
from utils.db_utils import get_db_transaction
from utils.metadata_fingerprint import calculate_metadata_fingerprint
from psycopg2.extras import Json

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def backfill_metadata_fingerprints(dry_run=False, batch_size=100):
    """
    Backfill metadata fingerprints for existing papers.
    
    Args:
        dry_run: If True, only show what would be updated without writing
        batch_size: Number of papers to process per batch
        
    Returns:
        Number of papers updated
    """
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Starting metadata fingerprint backfill...")
    
    total_updated = 0
    
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            # Get count of papers without fingerprints
            cur.execute("""
                SELECT COUNT(*) FROM processed_papers
                WHERE metadata_fingerprint IS NULL
            """)
            total_papers = cur.fetchone()['count']
            
            logger.info(f"Found {total_papers} papers without metadata fingerprints")
            
            if total_papers == 0:
                logger.info("All papers already have metadata fingerprints!")
                return 0
            
            # Process in batches
            offset = 0
            while offset < total_papers:
                logger.info(f"Processing batch {offset // batch_size + 1} (papers {offset + 1}-{min(offset + batch_size, total_papers)})")
                
                # Fetch batch of papers without fingerprints
                cur.execute("""
                    SELECT id, drive_file_id, metadata, metadata_json
                    FROM processed_papers
                    WHERE metadata_fingerprint IS NULL
                    ORDER BY id
                    LIMIT %s OFFSET %s
                """, (batch_size, offset))
                
                papers = cur.fetchall()
                
                if not papers:
                    break
                
                # Calculate fingerprints for each paper
                updates = []
                for paper in papers:
                    paper_id = paper['id']
                    file_id = paper['drive_file_id']
                    
                    # Try metadata_json first (new field), fall back to metadata
                    metadata = paper.get('metadata_json') or paper.get('metadata') or {}
                    
                    if not metadata:
                        logger.warning(f"Paper {paper_id} has no metadata, skipping")
                        continue
                    
                    # Calculate fingerprint
                    fingerprint = calculate_metadata_fingerprint(metadata)
                    
                    updates.append((fingerprint, metadata, paper_id))
                    
                    logger.debug(f"Paper {paper_id} ({file_id[:16]}...): fingerprint = {fingerprint[:16]}...")
                
                # Batch update
                if updates and not dry_run:
                    cur.executemany("""
                        UPDATE processed_papers
                        SET metadata_fingerprint = %s,
                            metadata_json = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE id = %s
                    """, [(fp, Json(meta), pid) for fp, meta, pid in updates])
                    
                    logger.info(f"✅ Updated {len(updates)} papers with metadata fingerprints")
                elif updates:
                    logger.info(f"[DRY RUN] Would update {len(updates)} papers")
                
                total_updated += len(updates)
                offset += batch_size
    
    logger.info(f"{'[DRY RUN] ' if dry_run else ''}Backfill complete! Total papers updated: {total_updated}")
    return total_updated


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Backfill metadata fingerprints for existing papers')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without writing')
    parser.add_argument('--batch-size', type=int, default=100, help='Number of papers to process per batch')
    
    args = parser.parse_args()
    
    try:
        count = backfill_metadata_fingerprints(dry_run=args.dry_run, batch_size=args.batch_size)
        print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Successfully backfilled {count} papers!")
        
        if args.dry_run:
            print("\nRun without --dry-run to apply changes.")
    except Exception as e:
        logger.error(f"Migration failed: {e}", exc_info=True)
        raise

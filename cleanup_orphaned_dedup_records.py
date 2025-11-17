#!/usr/bin/env python3
"""
Cleanup orphaned deduplication records from processed_papers table.

This script removes records where:
1. A processed_papers entry exists (marking paper as "processed")
2. But NO chunks exist in processing_chunks (meaning it never completed)
3. The vectors were never uploaded to Pinecone

This happens when a job crashes after creating the dedup record but before
completing the processing pipeline.

Usage:
    python cleanup_orphaned_dedup_records.py --dry-run              # Preview (default)
    python cleanup_orphaned_dedup_records.py --execute              # Apply changes
    python cleanup_orphaned_dedup_records.py --product-id 7         # Filter by product
    python cleanup_orphaned_dedup_records.py --execute --product-id 7

Safety:
    - Idempotent: Safe to run multiple times
    - Dry-run by default: Shows what would be deleted
    - Non-destructive: Only removes incomplete records
"""

import argparse
import sys
from datetime import datetime
from typing import Dict, List, Set, Optional
from utils.db.connection import get_db_connection
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_orphaned_records(product_id: Optional[int] = None) -> List[Dict]:
    """
    Find processed_papers records that have no chunks in processing_chunks.
    
    These are orphaned records from jobs that failed after creating the
    deduplication entry but before completing processing.
    
    Args:
        product_id: Optional filter by product ID
        
    Returns:
        List of orphaned record dictionaries
    """
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Find processed_papers records without corresponding chunks
        if product_id is not None:
            query = """
                SELECT 
                    pp.id,
                    pp.drive_file_id,
                    pp.paper_title,
                    pp.authors,
                    pp.product_id,
                    pp.created_at,
                    pp.pinecone_namespace
                FROM processed_papers pp
                LEFT JOIN processing_chunks pc ON pp.drive_file_id = pc.file_id
                WHERE pc.file_id IS NULL
                    AND pp.product_id = %s
                ORDER BY pp.created_at DESC
            """
            cur.execute(query, (product_id,))
        else:
            query = """
                SELECT 
                    pp.id,
                    pp.drive_file_id,
                    pp.paper_title,
                    pp.authors,
                    pp.product_id,
                    pp.created_at,
                    pp.pinecone_namespace
                FROM processed_papers pp
                LEFT JOIN processing_chunks pc ON pp.drive_file_id = pc.file_id
                WHERE pc.file_id IS NULL
                ORDER BY pp.created_at DESC
            """
            cur.execute(query)
        
        records = []
        for row in cur.fetchall():
            records.append({
                'id': row['id'],
                'drive_file_id': row['drive_file_id'],
                'paper_title': row['paper_title'],
                'authors': row['authors'],
                'product_id': row['product_id'],
                'created_at': row['created_at'],
                'pinecone_namespace': row['pinecone_namespace']
            })
        
        logger.info(f"Found {len(records)} orphaned records")
        return records
        
    finally:
        cur.close()
        conn.close()


def delete_orphaned_record(record_id: int, dry_run: bool = True) -> bool:
    """
    Delete an orphaned processed_papers record.
    
    Args:
        record_id: ID of the processed_papers record to delete
        dry_run: If True, only log what would be done
        
    Returns:
        True if successful, False otherwise
    """
    if dry_run:
        return True
    
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Delete from processed_papers (cascade will handle source_paper_mapping)
        cur.execute("""
            DELETE FROM processed_papers
            WHERE id = %s
        """, (record_id,))
        
        conn.commit()
        return True
        
    except Exception as e:
        logger.error(f"❌ Error deleting record {record_id}: {e}")
        conn.rollback()
        return False
        
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Cleanup orphaned deduplication records',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview all orphaned records (safe, read-only)
  python cleanup_orphaned_dedup_records.py --dry-run
  
  # Preview orphaned records for Product 7
  python cleanup_orphaned_dedup_records.py --product-id 7
  
  # Actually delete orphaned records for Product 7
  python cleanup_orphaned_dedup_records.py --execute --product-id 7
  
  # Delete all orphaned records (use with caution)
  python cleanup_orphaned_dedup_records.py --execute
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
    
    parser.add_argument(
        '--product-id',
        type=int,
        help='Filter by product ID (only clean orphaned records for this product)'
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
        logger.info("⚠️  EXECUTE MODE: Changes will be applied to the database")
        logger.info("=" * 80)
    
    if args.product_id:
        logger.info(f"🔍 Filtering by Product ID: {args.product_id}")
    
    print()
    
    # Step 1: Find orphaned records
    logger.info("📊 Step 1: Finding orphaned deduplication records...")
    logger.info("   (Records in processed_papers but no chunks in processing_chunks)")
    print()
    
    orphaned_records = get_orphaned_records(args.product_id)
    
    if not orphaned_records:
        logger.info("✅ No orphaned records found!")
        logger.info("   All processed_papers records have corresponding chunks.")
        return 0
    
    # Step 2: Display what will be deleted
    logger.info(f"📊 Found {len(orphaned_records)} orphaned records:")
    print()
    
    # Group by product for better visibility
    by_product = {}
    for record in orphaned_records:
        product_id = record['product_id']
        product_key = f"Product {product_id}" if product_id else "Global (no product)"
        if product_key not in by_product:
            by_product[product_key] = []
        by_product[product_key].append(record)
    
    for product_key, records in sorted(by_product.items()):
        logger.info(f"\n{product_key}: {len(records)} records")
        logger.info("-" * 80)
        for idx, record in enumerate(records[:5], 1):  # Show first 5
            title = record['paper_title'][:60] + "..." if len(record['paper_title']) > 60 else record['paper_title']
            logger.info(f"  {idx}. {title}")
            logger.info(f"     File ID: {record['drive_file_id']}")
            logger.info(f"     Created: {record['created_at']}")
            logger.info(f"     Namespace: {record['pinecone_namespace']}")
        
        if len(records) > 5:
            logger.info(f"  ... and {len(records) - 5} more")
    
    print()
    
    # Step 3: Delete orphaned records
    if dry_run:
        logger.info("\n💡 This was a DRY-RUN. No changes were made to the database.")
        logger.info("   To delete these orphaned records, run with --execute flag:")
        if args.product_id:
            logger.info(f"   python cleanup_orphaned_dedup_records.py --execute --product-id {args.product_id}")
        else:
            logger.info("   python cleanup_orphaned_dedup_records.py --execute")
    else:
        logger.info(f"\n🗑️  Step 2: Deleting {len(orphaned_records)} orphaned records...")
        print()
        
        success_count = 0
        error_count = 0
        
        for idx, record in enumerate(orphaned_records, 1):
            title = record['paper_title'][:40] + "..." if len(record['paper_title']) > 40 else record['paper_title']
            logger.info(f"[{idx}/{len(orphaned_records)}] Deleting: {title}")
            
            if delete_orphaned_record(record['id'], dry_run=False):
                success_count += 1
            else:
                error_count += 1
        
        # Summary
        print()
        logger.info("=" * 80)
        logger.info("CLEANUP SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Total orphaned records:    {len(orphaned_records)}")
        logger.info(f"Successfully deleted:      {success_count}")
        logger.info(f"Errors:                    {error_count}")
        logger.info("=" * 80)
        
        if success_count > 0:
            logger.info(f"\n✅ Cleanup completed successfully!")
            logger.info(f"✅ {success_count} orphaned records removed")
            logger.info(f"✅ These papers can now be processed again")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

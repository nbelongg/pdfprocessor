#!/usr/bin/env python3
"""
Delete deduplication records by date range and product ID.

This script removes processed_papers records created within a specific time range,
useful for cleaning up orphaned records from failed jobs.

Usage:
    # Preview deletion for Product 7, Nov 13 11:35-11:45
    python delete_dedup_by_daterange.py --product-id 7 \
        --start "2025-11-13 11:35:00" \
        --end "2025-11-13 11:45:00" \
        --dry-run
    
    # Actually delete them
    python delete_dedup_by_daterange.py --product-id 7 \
        --start "2025-11-13 11:35:00" \
        --end "2025-11-13 11:45:00" \
        --execute

Safety:
    - Dry-run by default: Shows what would be deleted
    - Requires explicit --execute flag to make changes
    - Shows detailed preview before deletion
"""

import argparse
import sys
from datetime import datetime
from typing import List, Dict, Optional
from utils.db.connection import get_db_connection
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_records_in_range(
    product_id: Optional[int],
    start_date: str,
    end_date: str
) -> List[Dict]:
    """
    Find processed_papers records created within a date range.
    
    Args:
        product_id: Product ID to filter by (None for all)
        start_date: Start datetime (ISO format)
        end_date: End datetime (ISO format)
        
    Returns:
        List of matching records
    """
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        if product_id is not None:
            query = """
                SELECT 
                    pp.id,
                    pp.drive_file_id,
                    pp.paper_title,
                    pp.authors,
                    pp.product_id,
                    pp.created_at,
                    pp.pinecone_namespace,
                    CASE 
                        WHEN pc.file_id IS NOT NULL THEN true 
                        ELSE false 
                    END as has_chunks
                FROM processed_papers pp
                LEFT JOIN processing_chunks pc ON pp.drive_file_id = pc.file_id
                WHERE pp.product_id = %s
                    AND pp.created_at >= %s
                    AND pp.created_at <= %s
                ORDER BY pp.created_at DESC
            """
            cur.execute(query, (product_id, start_date, end_date))
        else:
            query = """
                SELECT 
                    pp.id,
                    pp.drive_file_id,
                    pp.paper_title,
                    pp.authors,
                    pp.product_id,
                    pp.created_at,
                    pp.pinecone_namespace,
                    CASE 
                        WHEN pc.file_id IS NOT NULL THEN true 
                        ELSE false 
                    END as has_chunks
                FROM processed_papers pp
                LEFT JOIN processing_chunks pc ON pp.drive_file_id = pc.file_id
                WHERE pp.created_at >= %s
                    AND pp.created_at <= %s
                ORDER BY pp.created_at DESC
            """
            cur.execute(query, (start_date, end_date))
        
        records = []
        for row in cur.fetchall():
            records.append({
                'id': row['id'],
                'drive_file_id': row['drive_file_id'],
                'paper_title': row['paper_title'],
                'authors': row['authors'],
                'product_id': row['product_id'],
                'created_at': row['created_at'],
                'pinecone_namespace': row['pinecone_namespace'],
                'has_chunks': row['has_chunks']
            })
        
        logger.info(f"Found {len(records)} records in date range")
        return records
        
    finally:
        cur.close()
        conn.close()


def delete_records(record_ids: List[int], dry_run: bool = True) -> int:
    """
    Delete processed_papers records by ID.
    
    Args:
        record_ids: List of record IDs to delete
        dry_run: If True, don't actually delete
        
    Returns:
        Number of records deleted
    """
    if dry_run:
        return len(record_ids)
    
    import psycopg2.extras
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Delete records (cascade will handle source_paper_mapping)
        cur.execute("""
            DELETE FROM processed_papers
            WHERE id = ANY(%s)
        """, (record_ids,))
        
        deleted_count = cur.rowcount
        conn.commit()
        return deleted_count
        
    except Exception as e:
        logger.error(f"❌ Error deleting records: {e}")
        conn.rollback()
        return 0
        
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description='Delete deduplication records by date range',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview deletion for Product 7 on Nov 13
  python delete_dedup_by_daterange.py --product-id 7 \\
      --start "2025-11-13 11:35:00" \\
      --end "2025-11-13 11:45:00"
  
  # Actually delete them
  python delete_dedup_by_daterange.py --product-id 7 \\
      --start "2025-11-13 11:35:00" \\
      --end "2025-11-13 11:45:00" \\
      --execute
  
  # Delete for Product 7 on Nov 16 (different batch)
  python delete_dedup_by_daterange.py --product-id 7 \\
      --start "2025-11-16 04:00:00" \\
      --end "2025-11-16 05:00:00" \\
      --execute
        """
    )
    
    parser.add_argument(
        '--product-id',
        type=int,
        help='Product ID to filter by'
    )
    
    parser.add_argument(
        '--start',
        required=True,
        help='Start datetime (e.g., "2025-11-13 11:35:00")'
    )
    
    parser.add_argument(
        '--end',
        required=True,
        help='End datetime (e.g., "2025-11-13 11:45:00")'
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
    
    # Validate dates
    try:
        datetime.fromisoformat(args.start)
        datetime.fromisoformat(args.end)
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        logger.error('Use format: "YYYY-MM-DD HH:MM:SS"')
        return 1
    
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
    
    logger.info(f"Product ID: {args.product_id if args.product_id else 'ALL'}")
    logger.info(f"Date Range: {args.start} to {args.end}")
    print()
    
    # Step 1: Find matching records
    logger.info("📊 Step 1: Finding records in date range...")
    records = get_records_in_range(args.product_id, args.start, args.end)
    
    if not records:
        logger.info("✅ No records found in this date range!")
        return 0
    
    # Step 2: Display what will be deleted
    logger.info(f"\n📊 Found {len(records)} records to delete:")
    logger.info("=" * 80)
    
    # Group by product and chunks status
    with_chunks = [r for r in records if r['has_chunks']]
    without_chunks = [r for r in records if not r['has_chunks']]
    
    logger.info(f"\n⚠️  Records WITH chunks (will be deleted, but chunks remain): {len(with_chunks)}")
    logger.info(f"✓  Records WITHOUT chunks (true orphans): {len(without_chunks)}")
    
    # Show sample records
    logger.info("\nSample records (first 10):")
    logger.info("-" * 80)
    for idx, record in enumerate(records[:10], 1):
        title = record['paper_title'][:50] + "..." if len(record['paper_title']) > 50 else record['paper_title']
        chunks_status = "✓ has chunks" if record['has_chunks'] else "✗ no chunks"
        logger.info(f"{idx}. {title}")
        logger.info(f"   File ID: {record['drive_file_id']}")
        logger.info(f"   Created: {record['created_at']}")
        logger.info(f"   Status: {chunks_status}")
    
    if len(records) > 10:
        logger.info(f"\n... and {len(records) - 10} more records")
    
    print()
    
    # Step 3: Delete or preview
    if dry_run:
        logger.info("\n💡 This was a DRY-RUN. No changes were made to the database.")
        logger.info("   To delete these records, run with --execute flag:")
        if args.product_id:
            logger.info(f'   python delete_dedup_by_daterange.py --product-id {args.product_id} \\')
        logger.info(f'       --start "{args.start}" \\')
        logger.info(f'       --end "{args.end}" \\')
        logger.info('       --execute')
    else:
        logger.info(f"\n🗑️  Step 2: Deleting {len(records)} records...")
        print()
        
        record_ids = [r['id'] for r in records]
        deleted_count = delete_records(record_ids, dry_run=False)
        
        # Summary
        print()
        logger.info("=" * 80)
        logger.info("DELETION SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Records found:             {len(records)}")
        logger.info(f"Successfully deleted:      {deleted_count}")
        logger.info("=" * 80)
        
        if deleted_count > 0:
            logger.info(f"\n✅ Deletion completed successfully!")
            logger.info(f"✅ {deleted_count} deduplication records removed")
            logger.info(f"✅ These papers can now be processed again")
            
            if with_chunks:
                logger.info(f"\nℹ️  Note: {len(with_chunks)} papers have chunks in the database")
                logger.info("   They can be reprocessed faster (parsing already done)")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""
Database migration script to fix row_number values in source_paper_mapping table.

Problem:
- Old code stored DataFrame index (0-based) as row_number
- Should store actual Google Sheets row number (DataFrame index + 2)
  - +1 for header row
  - +1 for 0-based to 1-based indexing

This script adds 2 to all existing row_number values.

Usage:
    python migrate_row_numbers.py --dry-run  # Preview changes
    python migrate_row_numbers.py            # Apply changes
"""

import argparse
import logging
from utils.db_utils import get_db_transaction, with_db_error_handling

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@with_db_error_handling
def get_migration_stats():
    """Get statistics about what will be migrated."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            # Count total mappings
            cur.execute("SELECT COUNT(*) as count FROM source_paper_mapping")
            total_count = cur.fetchone()['count']
            
            # Get row number distribution
            cur.execute("""
                SELECT 
                    MIN(row_number) as min_row,
                    MAX(row_number) as max_row,
                    AVG(row_number) as avg_row
                FROM source_paper_mapping
            """)
            stats = cur.fetchone()
            
            # Get sample of records that will change
            cur.execute("""
                SELECT 
                    spm.id,
                    spm.source_id,
                    spm.paper_id,
                    spm.row_number as old_row_number,
                    spm.row_number + 2 as new_row_number,
                    pp.paper_title
                FROM source_paper_mapping spm
                JOIN processed_papers pp ON spm.paper_id = pp.id
                ORDER BY spm.id
                LIMIT 10
            """)
            samples = cur.fetchall()
            
            return {
                'total_count': total_count,
                'min_row': stats['min_row'] if stats else None,
                'max_row': stats['max_row'] if stats else None,
                'avg_row': float(stats['avg_row']) if stats and stats['avg_row'] else None,
                'samples': samples
            }


@with_db_error_handling
def migrate_row_numbers(dry_run: bool = False):
    """
    Migrate row_number values by adding 2.
    
    Args:
        dry_run: If True, only show what would be changed
    """
    logger.info("=" * 70)
    logger.info("ROW NUMBER MIGRATION SCRIPT")
    logger.info("=" * 70)
    
    # Get statistics
    logger.info("\n📊 Analyzing current data...")
    stats = get_migration_stats()
    
    logger.info(f"\nTotal records to update: {stats['total_count']}")
    logger.info(f"Current row_number range: {stats['min_row']} - {stats['max_row']}")
    logger.info(f"Current average row_number: {stats['avg_row']:.1f}")
    logger.info(f"After migration range: {stats['min_row'] + 2 if stats['min_row'] else 'N/A'} - {stats['max_row'] + 2 if stats['max_row'] else 'N/A'}")
    
    if stats['samples']:
        logger.info("\n📋 Sample records (first 10):")
        logger.info("-" * 70)
        for sample in stats['samples']:
            logger.info(
                f"  ID: {sample['id']:<6} | "
                f"Paper: {sample['paper_title'][:30]:<30} | "
                f"Old: {sample['old_row_number']:<4} → New: {sample['new_row_number']}"
            )
        logger.info("-" * 70)
    
    if dry_run:
        logger.info("\n🔍 DRY RUN MODE - No changes will be made")
        logger.info(f"Would update {stats['total_count']} records")
        return {
            'dry_run': True,
            'records_updated': 0,
            'records_analyzed': stats['total_count']
        }
    
    # Perform the migration
    logger.info("\n🚀 Applying migration...")
    
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            # Update all row_number values by adding 2
            cur.execute("""
                UPDATE source_paper_mapping
                SET row_number = row_number + 2
            """)
            
            updated_count = cur.rowcount
            
            logger.info(f"✅ Successfully updated {updated_count} records")
            
            # Verify the changes
            cur.execute("""
                SELECT 
                    MIN(row_number) as min_row,
                    MAX(row_number) as max_row,
                    AVG(row_number) as avg_row
                FROM source_paper_mapping
            """)
            new_stats = cur.fetchone()
            
            logger.info("\n📊 Post-migration statistics:")
            logger.info(f"  New row_number range: {new_stats['min_row']} - {new_stats['max_row']}")
            logger.info(f"  New average: {float(new_stats['avg_row']):.1f}")
            
            return {
                'dry_run': False,
                'records_updated': updated_count,
                'old_stats': stats,
                'new_stats': new_stats
            }


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate row_number values in source_paper_mapping table'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without applying them'
    )
    
    args = parser.parse_args()
    
    try:
        result = migrate_row_numbers(dry_run=args.dry_run)
        
        logger.info("\n" + "=" * 70)
        if result['dry_run']:
            logger.info("✅ DRY RUN COMPLETE - Ready to migrate")
            logger.info("Run without --dry-run to apply changes")
        else:
            logger.info("✅ MIGRATION COMPLETE")
            logger.info(f"Updated {result['records_updated']} records")
        logger.info("=" * 70)
        
        return 0
        
    except Exception as e:
        logger.error(f"\n❌ Migration failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return 1


if __name__ == '__main__':
    exit(main())

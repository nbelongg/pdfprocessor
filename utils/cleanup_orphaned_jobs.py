"""
Database cleanup utility for orphaned jobs.

This script identifies and optionally removes orphaned job records:
- Jobs referencing deleted data sources
- Jobs older than a certain threshold
- Jobs stuck in pending/running status

Usage:
    python utils/cleanup_orphaned_jobs.py --dry-run      # Show what would be cleaned
    python utils/cleanup_orphaned_jobs.py --execute      # Actually perform cleanup
    python utils/cleanup_orphaned_jobs.py --stats        # Show statistics only
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
from typing import Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection():
    """Get database connection from environment."""
    database_url = os.getenv('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable not set")
    return psycopg2.connect(database_url, cursor_factory=RealDictCursor)


def get_orphaned_jobs_stats(conn) -> Dict:
    """Get statistics about orphaned and problematic jobs."""
    with conn.cursor() as cur:
        stats = {}
        
        # Jobs with non-existent source_id
        cur.execute("""
            SELECT COUNT(*) as count
            FROM celery_jobs job
            LEFT JOIN data_sources source ON job.source_id = source.id
            WHERE job.source_id IS NOT NULL
            AND source.id IS NULL
        """)
        stats['orphaned_source'] = cur.fetchone()['count']
        
        # Jobs stuck in pending for > 1 hour
        cur.execute("""
            SELECT COUNT(*) as count
            FROM celery_jobs
            WHERE status = 'pending'
            AND created_at < NOW() - INTERVAL '1 hour'
        """)
        stats['stuck_pending'] = cur.fetchone()['count']
        
        # Jobs stuck in running for > 2 hours
        cur.execute("""
            SELECT COUNT(*) as count
            FROM celery_jobs
            WHERE status = 'running'
            AND updated_at < NOW() - INTERVAL '2 hours'
        """)
        stats['stuck_running'] = cur.fetchone()['count']
        
        # Failed jobs older than 30 days
        cur.execute("""
            SELECT COUNT(*) as count
            FROM celery_jobs
            WHERE status = 'failed'
            AND created_at < NOW() - INTERVAL '30 days'
        """)
        stats['old_failed'] = cur.fetchone()['count']
        
        # Completed jobs older than 90 days
        cur.execute("""
            SELECT COUNT(*) as count
            FROM celery_jobs
            WHERE status = 'completed'
            AND created_at < NOW() - INTERVAL '90 days'
        """)
        stats['old_completed'] = cur.fetchone()['count']
        
        # Total jobs
        cur.execute("SELECT COUNT(*) as count FROM celery_jobs")
        stats['total'] = cur.fetchone()['count']
        
    return stats


def get_orphaned_jobs_details(conn) -> List[Dict]:
    """Get detailed list of orphaned jobs."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                job.id,
                job.task_id,
                job.task_name,
                job.source_id,
                job.status,
                job.created_at,
                job.error_message
            FROM celery_jobs job
            LEFT JOIN data_sources source ON job.source_id = source.id
            WHERE job.source_id IS NOT NULL
            AND source.id IS NULL
            ORDER BY job.created_at DESC
            LIMIT 100
        """)
        return cur.fetchall()


def get_stuck_jobs_details(conn) -> List[Dict]:
    """Get detailed list of stuck jobs."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                id,
                task_id,
                task_name,
                source_id,
                status,
                created_at,
                updated_at,
                error_message,
                EXTRACT(EPOCH FROM (NOW() - created_at))/3600 as hours_since_created,
                EXTRACT(EPOCH FROM (NOW() - updated_at))/3600 as hours_since_updated
            FROM celery_jobs
            WHERE (
                (status = 'pending' AND created_at < NOW() - INTERVAL '1 hour')
                OR 
                (status = 'running' AND updated_at < NOW() - INTERVAL '2 hours')
            )
            ORDER BY created_at DESC
            LIMIT 100
        """)
        return cur.fetchall()


def cleanup_orphaned_jobs(conn, dry_run=True) -> int:
    """Remove jobs with non-existent source_id."""
    with conn.cursor() as cur:
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM celery_jobs job
                LEFT JOIN data_sources source ON job.source_id = source.id
                WHERE job.source_id IS NOT NULL
                AND source.id IS NULL
            """)
            return cur.fetchone()['count']
        else:
            cur.execute("""
                DELETE FROM celery_jobs
                WHERE id IN (
                    SELECT job.id
                    FROM celery_jobs job
                    LEFT JOIN data_sources source ON job.source_id = source.id
                    WHERE job.source_id IS NOT NULL
                    AND source.id IS NULL
                )
            """)
            conn.commit()
            return cur.rowcount


def cleanup_stuck_pending(conn, dry_run=True, hours=24) -> int:
    """Mark stuck pending jobs as failed."""
    with conn.cursor() as cur:
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM celery_jobs
                WHERE status = 'pending'
                AND created_at < NOW() - INTERVAL '%s hours'
            """, (hours,))
            return cur.fetchone()['count']
        else:
            cur.execute("""
                UPDATE celery_jobs
                SET status = 'failed',
                    error_message = 'Job stuck in pending status - automatically marked as failed',
                    updated_at = NOW()
                WHERE status = 'pending'
                AND created_at < NOW() - INTERVAL '%s hours'
            """, (hours,))
            conn.commit()
            return cur.rowcount


def cleanup_old_jobs(conn, dry_run=True, failed_days=30, completed_days=90) -> Dict[str, int]:
    """Remove old completed and failed jobs."""
    counts = {'failed': 0, 'completed': 0}
    
    with conn.cursor() as cur:
        # Old failed jobs
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM celery_jobs
                WHERE status = 'failed'
                AND created_at < NOW() - INTERVAL '%s days'
            """, (failed_days,))
            counts['failed'] = cur.fetchone()['count']
        else:
            cur.execute("""
                DELETE FROM celery_jobs
                WHERE status = 'failed'
                AND created_at < NOW() - INTERVAL '%s days'
            """, (failed_days,))
            counts['failed'] = cur.rowcount
        
        # Old completed jobs
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) as count
                FROM celery_jobs
                WHERE status = 'completed'
                AND created_at < NOW() - INTERVAL '%s days'
            """, (completed_days,))
            counts['completed'] = cur.fetchone()['count']
        else:
            cur.execute("""
                DELETE FROM celery_jobs
                WHERE status = 'completed'
                AND created_at < NOW() - INTERVAL '%s days'
            """, (completed_days,))
            counts['completed'] = cur.rowcount
            conn.commit()
    
    return counts


def print_stats(stats: Dict):
    """Print formatted statistics."""
    print("\n" + "="*60)
    print("DATABASE CLEANUP STATISTICS")
    print("="*60)
    print(f"\nTotal Jobs:               {stats['total']:,}")
    print(f"\nProblematic Jobs:")
    print(f"  Orphaned (deleted source): {stats['orphaned_source']:,}")
    print(f"  Stuck in pending (>1h):    {stats['stuck_pending']:,}")
    print(f"  Stuck in running (>2h):    {stats['stuck_running']:,}")
    print(f"\nOld Jobs (candidates for cleanup):")
    print(f"  Failed (>30 days):         {stats['old_failed']:,}")
    print(f"  Completed (>90 days):      {stats['old_completed']:,}")
    print("\n" + "="*60 + "\n")


def print_details(jobs: List[Dict], title: str):
    """Print detailed job information."""
    if not jobs:
        return
    
    print(f"\n{'='*60}")
    print(f"{title} ({len(jobs)} shown, max 100)")
    print('='*60)
    
    for job in jobs[:10]:  # Show first 10
        print(f"\nID: {job['id']}")
        print(f"  Task ID: {job['task_id'][:16]}...")
        print(f"  Name: {job['task_name']}")
        print(f"  Source ID: {job.get('source_id', 'N/A')}")
        print(f"  Status: {job['status']}")
        print(f"  Created: {job['created_at']}")
        if 'hours_since_created' in job:
            print(f"  Hours since created: {job['hours_since_created']:.1f}")
        if job.get('error_message'):
            error = job['error_message'][:100]
            print(f"  Error: {error}...")
    
    if len(jobs) > 10:
        print(f"\n... and {len(jobs) - 10} more")
    print()


def main():
    parser = argparse.ArgumentParser(
        description='Clean up orphaned and problematic jobs in the database'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show statistics only (default)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be cleaned without making changes'
    )
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually perform cleanup operations'
    )
    parser.add_argument(
        '--details',
        action='store_true',
        help='Show detailed information about problematic jobs'
    )
    
    args = parser.parse_args()
    
    # Default to stats if nothing specified
    if not any([args.stats, args.dry_run, args.execute, args.details]):
        args.stats = True
    
    try:
        conn = get_db_connection()
        
        # Always show stats first
        stats = get_orphaned_jobs_stats(conn)
        print_stats(stats)
        
        # Show details if requested
        if args.details or args.dry_run or args.execute:
            orphaned = get_orphaned_jobs_details(conn)
            if orphaned:
                print_details(orphaned, "ORPHANED JOBS (Deleted Data Source)")
            
            stuck = get_stuck_jobs_details(conn)
            if stuck:
                print_details(stuck, "STUCK JOBS")
        
        # Perform cleanup operations
        if args.dry_run or args.execute:
            dry_run = not args.execute
            mode = "DRY RUN" if dry_run else "EXECUTING"
            
            print(f"\n{'='*60}")
            print(f"CLEANUP OPERATIONS - {mode}")
            print('='*60)
            
            # Clean orphaned jobs
            orphaned_count = cleanup_orphaned_jobs(conn, dry_run=dry_run)
            verb = "Would remove" if dry_run else "Removed"
            print(f"\n✓ {verb} {orphaned_count} orphaned jobs (deleted sources)")
            
            # Mark stuck pending jobs as failed
            stuck_count = cleanup_stuck_pending(conn, dry_run=dry_run, hours=24)
            verb = "Would mark" if dry_run else "Marked"
            print(f"✓ {verb} {stuck_count} stuck pending jobs as failed")
            
            # Remove old jobs
            old_counts = cleanup_old_jobs(
                conn, 
                dry_run=dry_run,
                failed_days=30,
                completed_days=90
            )
            verb = "Would remove" if dry_run else "Removed"
            print(f"✓ {verb} {old_counts['failed']} old failed jobs (>30 days)")
            print(f"✓ {verb} {old_counts['completed']} old completed jobs (>90 days)")
            
            total = orphaned_count + stuck_count + old_counts['failed'] + old_counts['completed']
            print(f"\nTotal: {total} job records")
            
            if dry_run:
                print("\n⚠️  This was a DRY RUN - no changes were made")
                print("   Run with --execute to actually perform cleanup")
            else:
                print("\n✅ Cleanup completed successfully!")
            
            print()
        
        conn.close()
        
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()

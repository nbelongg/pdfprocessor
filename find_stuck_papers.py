#!/usr/bin/env python3
"""
Find papers that might be stuck (have dedup records but may be incomplete).

This script helps identify the date ranges when stuck papers were created.
"""

import sys
from utils.db.connection import get_db_connection
import psycopg2.extras

def find_stuck_papers(product_id=None):
    """
    Find processed_papers records and show when they were created.
    Groups by date to help identify problematic batches.
    """
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        if product_id is not None:
            query = """
                SELECT 
                    pp.id,
                    pp.drive_file_id,
                    pp.paper_title,
                    pp.created_at,
                    pp.product_id,
                    CASE 
                        WHEN pc.file_id IS NOT NULL THEN true 
                        ELSE false 
                    END as has_chunks
                FROM processed_papers pp
                LEFT JOIN processing_chunks pc ON pp.drive_file_id = pc.file_id
                WHERE pp.product_id = %s
                ORDER BY pp.created_at DESC
                LIMIT 100
            """
            cur.execute(query, (product_id,))
        else:
            query = """
                SELECT 
                    pp.id,
                    pp.drive_file_id,
                    pp.paper_title,
                    pp.created_at,
                    pp.product_id,
                    CASE 
                        WHEN pc.file_id IS NOT NULL THEN true 
                        ELSE false 
                    END as has_chunks
                FROM processed_papers pp
                LEFT JOIN processing_chunks pc ON pp.drive_file_id = pc.file_id
                ORDER BY pp.created_at DESC
                LIMIT 100
            """
            cur.execute(query)
        
        records = cur.fetchall()
        
        if not records:
            print(f"\n✅ No processed papers found for Product {product_id if product_id else 'ALL'}")
            print("This means either:")
            print("  - No papers have been processed yet")
            print("  - All stuck papers were already cleaned up")
            return
        
        print(f"\n📊 Found {len(records)} processed papers (showing most recent 100)")
        print("=" * 100)
        
        # Group by date
        from collections import defaultdict
        by_date = defaultdict(list)
        
        for record in records:
            date_str = record['created_at'].strftime('%Y-%m-%d')
            by_date[date_str].append(record)
        
        # Show summary by date
        print("\nPapers by Date:")
        print("-" * 100)
        for date in sorted(by_date.keys(), reverse=True):
            papers = by_date[date]
            with_chunks = sum(1 for p in papers if p['has_chunks'])
            without_chunks = len(papers) - with_chunks
            
            print(f"\n{date}:")
            print(f"  Total: {len(papers)} papers")
            print(f"  With chunks: {with_chunks}")
            print(f"  Without chunks (orphans): {without_chunks}")
            
            # Show time range for this date
            times = [p['created_at'] for p in papers]
            earliest = min(times)
            latest = max(times)
            print(f"  Time range: {earliest.strftime('%H:%M:%S')} to {latest.strftime('%H:%M:%S')}")
            
            # Show a few sample titles
            print(f"  Sample papers:")
            for paper in papers[:3]:
                title = paper['paper_title'][:60] + "..." if len(paper['paper_title']) > 60 else paper['paper_title']
                status = "✓ has chunks" if paper['has_chunks'] else "✗ no chunks"
                time = paper['created_at'].strftime('%H:%M:%S')
                print(f"    - [{time}] {title} ({status})")
        
        print("\n" + "=" * 100)
        print("\n💡 To clean up papers from a specific date, use:")
        print('   python delete_dedup_by_daterange.py --product-id 7 \\')
        print('       --start "YYYY-MM-DD HH:MM:SS" \\')
        print('       --end "YYYY-MM-DD HH:MM:SS" \\')
        print('       --dry-run')
        
    finally:
        cur.close()
        conn.close()


if __name__ == '__main__':
    product_id = None
    
    # Check for --product-id argument
    if len(sys.argv) > 2 and sys.argv[1] == '--product-id':
        product_id = int(sys.argv[2])
    
    print("\n🔍 Finding processed papers...")
    if product_id:
        print(f"Filtering by Product ID: {product_id}")
    
    find_stuck_papers(product_id)

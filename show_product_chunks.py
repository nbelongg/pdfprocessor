#!/usr/bin/env python3
"""
Show processing chunks for a specific product.

Usage:
    python show_product_chunks.py --product-id 6
"""

import argparse
import sys
from utils.db.connection import get_db_connection
import psycopg2.extras


def show_chunks_for_product(product_id):
    """Display all chunks for a specific product."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get chunks by joining with processed_papers
        query = """
            SELECT 
                pc.id,
                pc.file_id,
                pc.filename,
                pc.chunk_index,
                pc.embedding_stored,
                pc.created_at,
                pp.paper_title,
                pp.product_id,
                LENGTH(pc.chunk_text) as text_length
            FROM processing_chunks pc
            INNER JOIN processed_papers pp ON pc.file_id = pp.drive_file_id
            WHERE pp.product_id = %s
            ORDER BY pc.file_id, pc.chunk_index
        """
        
        cur.execute(query, (product_id,))
        chunks = cur.fetchall()
        
        if not chunks:
            print(f"\n✅ No chunks found for Product {product_id}")
            return
        
        print(f"\n📊 Found {len(chunks)} chunks for Product {product_id}")
        print("=" * 120)
        
        # Group by file
        current_file = None
        file_chunk_count = 0
        uploaded_count = 0
        
        for chunk in chunks:
            if current_file != chunk['file_id']:
                # Print summary for previous file
                if current_file:
                    print(f"   Total: {file_chunk_count} chunks, Uploaded: {uploaded_count}")
                    print("-" * 120)
                
                # New file header
                current_file = chunk['file_id']
                file_chunk_count = 0
                uploaded_count = 0
                
                title = chunk['paper_title'][:80] + "..." if len(chunk['paper_title']) > 80 else chunk['paper_title']
                print(f"\n📄 {title}")
                print(f"   File ID: {chunk['file_id']}")
            
            # Count chunks
            file_chunk_count += 1
            if chunk['embedding_stored']:
                uploaded_count += 1
            
            # Show chunk details
            status = "✅ Uploaded" if chunk['embedding_stored'] else "❌ Not uploaded"
            print(f"   Chunk {chunk['chunk_index']:3d}: {chunk['text_length']:6d} chars - {status}")
        
        # Print summary for last file
        if current_file:
            print(f"   Total: {file_chunk_count} chunks, Uploaded: {uploaded_count}")
        
        print("\n" + "=" * 120)
        
        # Overall summary
        total_uploaded = sum(1 for c in chunks if c['embedding_stored'])
        total_not_uploaded = len(chunks) - total_uploaded
        
        print("\nSUMMARY:")
        print(f"  Total chunks: {len(chunks)}")
        print(f"  ✅ Uploaded to Pinecone: {total_uploaded}")
        print(f"  ❌ Not uploaded: {total_not_uploaded}")
        
    finally:
        cur.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='Show processing chunks for a product')
    parser.add_argument('--product-id', type=int, required=True, help='Product ID to filter by')
    
    args = parser.parse_args()
    
    print(f"🔍 Loading chunks for Product {args.product_id}...")
    show_chunks_for_product(args.product_id)


if __name__ == '__main__':
    sys.exit(main())

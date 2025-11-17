#!/usr/bin/env python3
"""
Verify if vectors exist in Pinecone for specific papers.

Usage:
    python verify_pinecone_vectors.py --product-id 6 --file-id "1__gE5enoX-mcZMgSWQ16_ZhTuv_c7Kic"
"""

import argparse
import os
import sys
from utils.db.connection import get_db_connection
from utils.db.products import get_product
import psycopg2.extras


def check_database_chunks(file_id):
    """Check if chunks exist in database and if they're marked as uploaded."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("""
            SELECT 
                COUNT(*) as total_chunks,
                COUNT(CASE WHEN embedding_stored = TRUE THEN 1 END) as uploaded_chunks,
                COUNT(CASE WHEN embedding_stored = FALSE OR embedding_stored IS NULL THEN 1 END) as not_uploaded_chunks
            FROM processing_chunks
            WHERE file_id = %s
        """, (file_id,))
        
        result = cur.fetchone()
        return dict(result) if result else None
        
    finally:
        cur.close()
        conn.close()


def check_pinecone_vectors(file_id, product_id):
    """Check if vectors actually exist in Pinecone."""
    from pinecone import Pinecone
    
    # Get product configuration
    product = get_product(product_id)
    if not product:
        print(f"❌ Product {product_id} not found")
        return None
    
    # Get Pinecone credentials
    pinecone_key_secret = product.get('pinecone_key_secret')
    if not pinecone_key_secret:
        print(f"❌ No Pinecone key configured for Product {product_id}")
        return None
    
    pinecone_key = os.getenv(pinecone_key_secret)
    if not pinecone_key:
        print(f"❌ Pinecone key not found in environment: {pinecone_key_secret}")
        return None
    
    pinecone_index_name = product.get('pinecone_index_name')
    pinecone_namespace = product.get('pinecone_namespace', 'default')
    
    print(f"\n🔍 Checking Pinecone:")
    print(f"   Index: {pinecone_index_name}")
    print(f"   Namespace: {pinecone_namespace}")
    
    # Connect to Pinecone
    pc = Pinecone(api_key=pinecone_key)
    index = pc.Index(pinecone_index_name)
    
    # Try to fetch first chunk vector
    vector_id = f"{file_id}_0"
    
    try:
        result = index.fetch(ids=[vector_id], namespace=pinecone_namespace)
        
        if result and result.vectors and vector_id in result.vectors:
            print(f"✅ Found vector in Pinecone: {vector_id}")
            
            # Try to get more vectors to count total
            chunk_count = 0
            for i in range(100):  # Try up to 100 chunks
                test_id = f"{file_id}_{i}"
                test_result = index.fetch(ids=[test_id], namespace=pinecone_namespace)
                if test_result and test_result.vectors and test_id in test_result.vectors:
                    chunk_count += 1
                else:
                    break
            
            return {
                'found': True,
                'chunk_count': chunk_count,
                'first_vector_id': vector_id
            }
        else:
            print(f"❌ Vector NOT found in Pinecone: {vector_id}")
            return {'found': False}
            
    except Exception as e:
        print(f"❌ Error checking Pinecone: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description='Verify if vectors exist in Pinecone')
    parser.add_argument('--product-id', type=int, required=True, help='Product ID')
    parser.add_argument('--file-id', required=True, help='Drive file ID to check')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print(f"Verifying vectors for file: {args.file_id}")
    print(f"Product ID: {args.product_id}")
    print("=" * 80)
    
    # Step 1: Check database
    print("\n📊 Step 1: Checking database...")
    db_result = check_database_chunks(args.file_id)
    
    if not db_result or db_result['total_chunks'] == 0:
        print("❌ No chunks found in database for this file")
        print("   This paper was never processed or chunks were deleted")
        return 1
    
    print(f"✅ Found {db_result['total_chunks']} chunks in database")
    print(f"   - Marked as uploaded: {db_result['uploaded_chunks']}")
    print(f"   - Not uploaded: {db_result['not_uploaded_chunks']}")
    
    # Step 2: Check Pinecone
    print("\n🔍 Step 2: Checking Pinecone...")
    pinecone_result = check_pinecone_vectors(args.file_id, args.product_id)
    
    if not pinecone_result:
        print("❌ Could not check Pinecone (configuration issue)")
        return 1
    
    # Step 3: Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if pinecone_result['found']:
        print(f"✅ SUCCESS: Vectors ARE in Pinecone")
        print(f"   - Database chunks: {db_result['total_chunks']}")
        print(f"   - Pinecone vectors: {pinecone_result['chunk_count']}")
        
        if db_result['uploaded_chunks'] == 0:
            print("\n⚠️  WARNING: Database says not uploaded, but vectors exist in Pinecone")
            print("   This might be from an old processing run")
    else:
        print(f"❌ PROBLEM: Vectors NOT in Pinecone")
        print(f"   - Database has {db_result['total_chunks']} chunks")
        print(f"   - But Pinecone has 0 vectors")
        print("\n💡 This paper needs to be reprocessed")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

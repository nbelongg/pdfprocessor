#!/usr/bin/env python3
"""
Reprocess papers from parsed_documents table.

This script takes already-parsed documents and:
1. Chunks them
2. Generates embeddings
3. Uploads to Pinecone
4. Creates records in processing_chunks and processed_papers

Usage:
    # Preview what will be processed
    python reprocess_from_parsed.py --product-id 6 --dry-run
    
    # Actually process
    python reprocess_from_parsed.py --product-id 6 --execute
    
    # Process specific batch size
    python reprocess_from_parsed.py --product-id 6 --batch-size 50 --execute
"""

import argparse
import sys
import os
import logging
from typing import List, Dict, Optional
from utils.db.connection import get_db_connection
from utils.db.documents import get_parsed_document, get_document_tags
from utils.db.jobs import save_chunks, mark_chunks_uploaded
from utils.db.products import get_product
from utils.config_builder import build_product_config
from utils.chunker import chunk_parsed_text
from utils.embedder import generate_embeddings
from utils.pinecone_uploader import upload_to_pinecone
from utils.deduplication import generate_content_hash
from utils.metadata_fingerprint import calculate_metadata_fingerprint
from pinecone import Pinecone
import psycopg2.extras
from llama_index.core.schema import TextNode

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_parsed_documents_for_product(product_id: int) -> List[Dict]:
    """Get all parsed documents that need reprocessing."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get all parsed documents (you'll need to filter by product somehow)
        # This depends on how you identify which parsed docs belong to which product
        query = """
            SELECT 
                pd.file_id,
                pd.parsed_text,
                pd.metadata,
                pd.created_at
            FROM parsed_documents pd
            WHERE pd.file_id NOT IN (
                SELECT DISTINCT drive_file_id 
                FROM processed_papers 
                WHERE product_id = %s
            )
            ORDER BY pd.created_at
        """
        
        cur.execute(query, (product_id,))
        docs = []
        
        for row in cur.fetchall():
            docs.append({
                'file_id': row['file_id'],
                'parsed_text': row['parsed_text'],
                'metadata': row['metadata'] or {},
                'created_at': row['created_at']
            })
        
        return docs
        
    finally:
        cur.close()
        conn.close()


def reprocess_document(
    file_id: str,
    parsed_text: str,
    metadata: Dict,
    product_config: Dict,
    product_id: int,
    job_id: str,
    dry_run: bool = True
) -> Dict:
    """
    Reprocess a single document from parsed text.
    
    Returns dict with status and stats.
    """
    try:
        logger.info(f"📄 Processing: {metadata.get('filename', file_id)}")
        
        # Get tags if they exist
        tags = get_document_tags(file_id)
        
        # Step 1: Chunk
        logger.info(f"   Chunking...")
        chunking_config = {
            'chunk_size': product_config.get('chunk_size', 512),
            'chunk_overlap': product_config.get('chunk_overlap', 128),
            'include_tags_in_chunks': product_config.get('include_tags_in_chunks', True)
        }
        
        nodes = chunk_parsed_text(
            parsed_text=parsed_text,
            file_metadata=metadata,
            tags=tags,
            config=chunking_config
        )
        
        if not nodes:
            logger.warning(f"   ⚠️  No chunks created")
            return {'status': 'error', 'error': 'No chunks created'}
        
        logger.info(f"   ✅ Created {len(nodes)} chunks")
        
        if dry_run:
            return {
                'status': 'preview',
                'chunks': len(nodes),
                'file_id': file_id
            }
        
        # Step 2: Generate embeddings
        logger.info(f"   Generating embeddings...")
        embedding_config = {
            'openai_api_key': os.getenv(product_config['openai_key_secret']),
            'embedding_model': product_config.get('embedding_model', 'text-embedding-3-small'),
            'embedding_dimensions': product_config.get('embedding_dimensions')
        }
        
        texts = [node.get_content() for node in nodes]
        embeddings = generate_embeddings(texts, embedding_config)
        
        logger.info(f"   ✅ Generated {len(embeddings)} embeddings")
        
        # Step 3: Prepare metadata for each chunk
        metadata_list = []
        for i, node in enumerate(nodes):
            chunk_metadata = metadata.copy()
            chunk_metadata['chunk_index'] = i
            chunk_metadata['total_chunks'] = len(nodes)
            
            # Add tags to metadata if they exist
            if tags:
                chunk_metadata['tags'] = tags
            
            metadata_list.append(chunk_metadata)
        
        # Step 4: Save chunks to database
        logger.info(f"   Saving chunks to database...")
        chunks_data = []
        for i, (node, embedding, chunk_meta) in enumerate(zip(nodes, embeddings, metadata_list)):
            chunks_data.append({
                'chunk_index': i,
                'chunk_text': node.get_content(),
                'metadata': chunk_meta,
                'embedding': embedding,
                'namespace': product_config.get('pinecone_namespace', 'default')
            })
        
        save_chunks(
            job_id=job_id,
            file_id=file_id,
            filename=metadata.get('filename', ''),
            chunks=chunks_data
        )
        
        logger.info(f"   ✅ Saved chunks to database")
        
        # Step 5: Upload to Pinecone
        logger.info(f"   Uploading to Pinecone...")
        
        # Connect to Pinecone
        pinecone_key = os.getenv(product_config['pinecone_key_secret'])
        pc = Pinecone(api_key=pinecone_key)
        index = pc.Index(product_config['pinecone_index_name'])
        
        uploaded_count = upload_to_pinecone(
            index=index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list,
            namespace=product_config.get('pinecone_namespace', 'default')
        )
        
        logger.info(f"   ✅ Uploaded {uploaded_count} vectors to Pinecone")
        
        # Step 6: Mark chunks as uploaded
        mark_chunks_uploaded(job_id, file_id)
        
        # Step 7: Record in processed_papers
        logger.info(f"   Recording in processed_papers...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        try:
            paper_title = metadata.get('paper_title', metadata.get('title', ''))
            authors = metadata.get('authors', '')
            content_hash = generate_content_hash(paper_title, authors)
            metadata_fp = calculate_metadata_fingerprint(metadata)
            
            cur.execute("""
                INSERT INTO processed_papers
                (drive_file_id, content_hash, paper_title, authors, metadata, 
                 pinecone_namespace, metadata_fingerprint, metadata_json, product_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (drive_file_id, product_id) DO NOTHING
            """, (
                file_id,
                content_hash,
                paper_title,
                authors,
                metadata,
                product_config.get('pinecone_namespace', 'default'),
                metadata_fp,
                metadata,
                product_id
            ))
            
            conn.commit()
            logger.info(f"   ✅ Recorded in processed_papers")
            
        finally:
            cur.close()
            conn.close()
        
        return {
            'status': 'success',
            'chunks': len(nodes),
            'vectors_uploaded': uploaded_count,
            'file_id': file_id
        }
        
    except Exception as e:
        logger.error(f"   ❌ Error: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'file_id': file_id
        }


def main():
    parser = argparse.ArgumentParser(
        description='Reprocess documents from parsed_documents table',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        '--product-id',
        type=int,
        required=True,
        help='Product ID to reprocess for'
    )
    
    parser.add_argument(
        '--batch-size',
        type=int,
        default=None,
        help='Only process first N documents (for testing)'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Preview without actually processing (default)'
    )
    
    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually process the documents'
    )
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    if dry_run:
        logger.info("=" * 80)
        logger.info("DRY-RUN MODE: No changes will be made")
        logger.info("=" * 80)
    else:
        logger.info("=" * 80)
        logger.info("⚠️  EXECUTE MODE: Documents will be reprocessed")
        logger.info("=" * 80)
    
    # Load product config
    logger.info(f"Loading Product {args.product_id} configuration...")
    product_config = build_product_config(args.product_id)
    
    if not product_config:
        logger.error(f"❌ Product {args.product_id} not found")
        return 1
    
    logger.info(f"✅ Product configuration loaded")
    
    # Get parsed documents
    logger.info(f"\n📊 Finding parsed documents to reprocess...")
    documents = get_parsed_documents_for_product(args.product_id)
    
    if not documents:
        logger.info("✅ No documents found to reprocess")
        return 0
    
    if args.batch_size:
        documents = documents[:args.batch_size]
        logger.info(f"📦 Limited to {args.batch_size} documents (batch mode)")
    
    logger.info(f"📄 Found {len(documents)} documents to process")
    
    if dry_run:
        logger.info("\n" + "=" * 80)
        logger.info("PREVIEW - Documents that would be processed:")
        logger.info("=" * 80)
        for i, doc in enumerate(documents[:10], 1):
            logger.info(f"{i}. {doc['file_id']} - {doc['metadata'].get('filename', 'Unknown')}")
        if len(documents) > 10:
            logger.info(f"... and {len(documents) - 10} more")
        
        logger.info("\n💡 To actually process these documents, run with --execute")
        return 0
    
    # Process documents
    job_id = f"reprocess_{args.product_id}"
    
    logger.info("\n" + "=" * 80)
    logger.info("Starting reprocessing...")
    logger.info("=" * 80)
    
    results = {
        'success': 0,
        'error': 0,
        'total_chunks': 0,
        'total_vectors': 0
    }
    
    for i, doc in enumerate(documents, 1):
        logger.info(f"\n[{i}/{len(documents)}] Processing {doc['file_id']}...")
        
        result = reprocess_document(
            file_id=doc['file_id'],
            parsed_text=doc['parsed_text'],
            metadata=doc['metadata'],
            product_config=product_config,
            product_id=args.product_id,
            job_id=job_id,
            dry_run=False
        )
        
        if result['status'] == 'success':
            results['success'] += 1
            results['total_chunks'] += result['chunks']
            results['total_vectors'] += result['vectors_uploaded']
        else:
            results['error'] += 1
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("REPROCESSING COMPLETE")
    logger.info("=" * 80)
    logger.info(f"Total documents: {len(documents)}")
    logger.info(f"✅ Successful: {results['success']}")
    logger.info(f"❌ Errors: {results['error']}")
    logger.info(f"📦 Total chunks created: {results['total_chunks']}")
    logger.info(f"🚀 Total vectors uploaded: {results['total_vectors']}")
    logger.info("=" * 80)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())

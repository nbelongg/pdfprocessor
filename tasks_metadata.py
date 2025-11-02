"""
Celery tasks for metadata-only updates (without re-parsing PDFs).

These tasks handle updating metadata for existing papers when metadata changes
in Google Sheets, avoiding expensive LlamaParse API calls.
"""

import logging
from celery import current_task
from celeryconfig import celery_app
from utils.db.metadata_updates import (
    get_chunks_with_embeddings,
    update_chunk_metadata,
    increment_metadata_job_counter,
    update_metadata_job_progress,
)
from utils.pinecone_uploader import initialize_pinecone
from utils.metadata_fingerprint import calculate_metadata_fingerprint
from utils.db.documents import update_processed_paper_fingerprint

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, queue='metadata_updates')
def update_metadata_task(
    self,
    file_id: str,
    new_metadata: dict,
    new_fingerprint: str,
    product_config: dict,
    job_id: str = None
):
    """
    Update metadata for a single paper without re-parsing.
    
    This task:
    1. Retrieves existing chunks and embeddings from database
    2. Applies new metadata to chunks
    3. Updates database (processing_chunks table)
    4. Uploads to Pinecone with same vector IDs but new metadata
    5. Updates metadata fingerprint in processed_papers
    
    Args:
        file_id: Google Drive file ID
        new_metadata: New metadata dictionary to apply
        new_fingerprint: New metadata fingerprint
        product_config: Product configuration with Pinecone settings
        job_id: Optional job ID for tracking
        
    Returns:
        Dict with status and number of chunks updated
    """
    try:
        logger.info(f"🔄 Starting metadata update for file_id: {file_id}")
        
        # Step 1: Retrieve existing chunks with embeddings from database
        chunks = get_chunks_with_embeddings(file_id)
        logger.info(f"📦 Retrieved {len(chunks)} chunks with embeddings from database")
        
        if not chunks:
            raise ValueError(f"No chunks found for file_id: {file_id}")
        
        # Step 2: Apply new metadata to each chunk
        # Use dict mapping to handle non-contiguous chunk indices safely
        chunk_updates_dict = {}
        for chunk in chunks:
            # Merge old metadata with new metadata
            updated_metadata = {
                **chunk['metadata'],  # Keep structural fields (file_id, filename, etc.)
                **new_metadata  # Overwrite with new metadata (tags, year, topic, etc.)
            }
            
            chunk_updates_dict[chunk['chunk_index']] = {
                'chunk_index': chunk['chunk_index'],
                'metadata': updated_metadata
            }
        
        # Convert back to list for update function
        chunk_updates = list(chunk_updates_dict.values())
        
        logger.info(f"✏️  Prepared metadata updates for {len(chunk_updates)} chunks")
        
        # Step 3: Update chunks in database
        updated_count = update_chunk_metadata(file_id, chunk_updates)
        logger.info(f"💾 Updated {updated_count} chunks in database")
        
        # Step 4: Upload to Pinecone with same vector IDs but new metadata
        try:
            # Initialize Pinecone
            index = initialize_pinecone(product_config)
            
            # Prepare vectors for Pinecone upsert
            vectors = []
            for chunk in chunks:
                chunk_index = chunk['chunk_index']
                vector_id = f"{file_id}_{chunk_index}"
                
                # Get updated metadata from chunk_updates_dict (safe lookup)
                updated_metadata = chunk_updates_dict[chunk_index]['metadata']
                
                # Sanitize metadata for Pinecone (convert lists to strings)
                vector_metadata = {
                    'text': chunk['chunk_text'],
                    **updated_metadata
                }
                
                # Convert lists to comma-separated strings
                for key, value in vector_metadata.items():
                    if isinstance(value, list):
                        vector_metadata[key] = ', '.join(str(item) for item in value) if value else ""
                    elif isinstance(value, dict):
                        vector_metadata[key] = str(value)
                    elif value is None:
                        vector_metadata[key] = ""
                
                vectors.append({
                    'id': vector_id,
                    'values': chunk['embedding'],  # Same embedding values from DB
                    'metadata': vector_metadata  # New metadata
                })
            
            # Upsert to Pinecone (replaces existing vectors with same IDs)
            namespace = chunks[0]['namespace'] if chunks else 'default'
            index.upsert(vectors=vectors, namespace=namespace)
            logger.info(f"☁️  Uploaded {len(vectors)} vectors to Pinecone namespace '{namespace}'")
            
        except Exception as e:
            logger.error(f"Failed to upload to Pinecone: {e}")
            raise
        
        # Step 5: Update metadata fingerprint in processed_papers
        update_processed_paper_fingerprint(file_id, new_fingerprint, new_metadata)
        logger.info(f"🔖 Updated metadata fingerprint for file_id: {file_id}")
        
        # Step 6: Update job progress if job_id provided
        if job_id:
            increment_metadata_job_counter(job_id, 'papers_updated')
        
        logger.info(f"✅ Metadata update complete for file_id: {file_id} ({len(chunks)} chunks)")
        
        return {
            'status': 'success',
            'file_id': file_id,
            'chunks_updated': len(chunks),
            'vectors_uploaded': len(vectors)
        }
        
    except Exception as e:
        logger.error(f"❌ Metadata update failed for file_id {file_id}: {str(e)}")
        
        if job_id:
            increment_metadata_job_counter(job_id, 'papers_failed')
        
        raise


@celery_app.task(bind=True, queue='metadata_updates')
def update_metadata_batch_task(
    self,
    job_id: str,
    papers_to_update: list,
    product_config: dict
):
    """
    Coordinate metadata updates for multiple papers.
    
    Args:
        job_id: Metadata update job ID
        papers_to_update: List of dicts with file_id, new_metadata, new_fingerprint
        product_config: Product configuration
        
    Returns:
        Dict with job summary
    """
    try:
        logger.info(f"🚀 Starting batch metadata update job {job_id} for {len(papers_to_update)} papers")
        
        # Update job status to running
        update_metadata_job_progress(job_id, status='running')
        
        # Queue individual update tasks
        for paper in papers_to_update:
            update_metadata_task.apply_async(
                args=(
                    paper['file_id'],
                    paper['new_metadata'],
                    paper['new_fingerprint'],
                    product_config,
                    job_id
                ),
                queue='metadata_updates'
            )
        
        logger.info(f"📤 Queued {len(papers_to_update)} metadata update tasks for job {job_id}")
        
        return {
            'status': 'queued',
            'job_id': job_id,
            'total_papers': len(papers_to_update)
        }
        
    except Exception as e:
        logger.error(f"Failed to queue batch metadata update job {job_id}: {str(e)}")
        update_metadata_job_progress(job_id, status='failed', error_message=str(e))
        raise

"""
Celery tasks for PDF processing pipeline.

This module defines background tasks for processing PDFs through the complete pipeline:
download → parse → tag → chunk → embed → upload to Pinecone.

Improvements (October 2025):
- Replaced print() with proper logging
- Extracted constants section
- Simplified config builder with PRODUCT_CONFIG_MAPPING
- Improved type hints throughout
- Added TransientError exception class
- Moved all imports to top of file
"""

import logging
import time
import traceback
import uuid
from typing import Dict, List, Optional, Callable, Tuple, Any

import pandas as pd
from celery import Task
from celeryconfig import celery_app

from utils.google_sheets import extract_file_id_from_drive_link, load_sheet_data
from utils.google_drive import download_pdf_from_drive, get_file_metadata
from utils.llama_parser import parse_pdf_with_llamaparse
from utils.chunker import chunk_text
from utils.embedder import create_embeddings
from utils.pinecone_uploader import initialize_pinecone, upload_to_pinecone
from utils.database import (
    create_processing_job, update_job_status,
    save_chunks, mark_chunks_uploaded,
    get_data_source, get_column_mapping_dict,
    get_product, get_product_api_keys,
    update_document_tags, get_document_tags, is_document_tagged,
    save_parsed_document
)
from utils.tagger import generate_tags_with_openai, validate_tags
from utils.exceptions import TransientError
from utils.config_builder import build_product_config
from utils.deduplication import check_all_layers, record_or_update_paper
from utils.monitoring import (
    track_api_cost, calculate_llamaparse_cost, calculate_openai_embedding_cost,
    estimate_tokens_from_text, update_job_runtime, save_to_failed_queue
)
from datetime import datetime


# ============================================
# LOGGING SETUP
# ============================================

logger = logging.getLogger(__name__)


# ============================================
# CONSTANTS
# ============================================

# Retry settings
DEFAULT_MAX_RETRIES = 3
DEFAULT_BACKOFF_FACTOR = 2

# Celery task retry settings
CELERY_RETRY_COUNTDOWN = 60  # seconds
CELERY_MAX_RETRIES = 3

# Processing settings
EMBEDDING_PREVIEW_SIZE = 5

# Progress milestones (percentage)
PROGRESS_DOWNLOAD = 0
PROGRESS_PARSE = 20
PROGRESS_TAG = 30
PROGRESS_CHUNK = 40
PROGRESS_EMBED = 60
PROGRESS_UPLOAD = 80
PROGRESS_COMPLETE = 100


# ============================================
# TASK BASE CLASS
# ============================================

class CallbackTask(Task):
    """Base task class that handles progress callbacks."""
    
    def update_progress(self, current: int, total: int, message: str) -> None:
        """
        Update task progress.
        
        Args:
            current: Current progress value
            total: Total progress value
            message: Progress message to display
        """
        self.update_state(
            state='PROGRESS',
            meta={
                'current': current,
                'total': total,
                'message': message,
                'percent': int((current / total) * 100) if total > 0 else 0
            }
        )


# ============================================
# UTILITIES
# ============================================

def call_with_retry(
    func: Callable[[], Any],
    max_retries: int = DEFAULT_MAX_RETRIES,
    backoff_factor: int = DEFAULT_BACKOFF_FACTOR,
    exceptions: tuple[type[Exception], ...] = (Exception,)
) -> Any:
    """
    Call a function with exponential backoff retry logic.
    
    Args:
        func: Function to call
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for wait time between retries
        exceptions: Tuple of exceptions to catch and retry on
        
    Returns:
        Function result
        
    Raises:
        Last exception if all retries fail
    """
    for attempt in range(max_retries):
        try:
            return func()
        except exceptions as e:
            if attempt == max_retries - 1:
                raise
            
            wait_time = backoff_factor ** attempt
            logger.warning(
                f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)
    
    raise RuntimeError("Max retries exceeded")




# ============================================
# TASKS
# ============================================

def _process_single_pdf_logic(
    file_id: str,
    filename: str,
    row_metadata: Dict[str, Any],
    config: Dict[str, Any],
    job_id: str,
    namespace: str = 'default',
    progress_callback: Optional[Callable[[int, int, str], None]] = None
) -> Dict[str, Any]:
    """
    Core PDF processing logic (extracted for reuse).
    
    Args:
        file_id: Google Drive file ID
        filename: PDF filename
        row_metadata: Metadata from Google Sheets row
        config: Processing configuration
        job_id: Parent processing job ID
        namespace: Pinecone namespace
        progress_callback: Optional callback for progress updates
        
    Returns:
        Dictionary with processing results
    """
    # Track runtime
    start_time = time.time()
    started_at = datetime.now()
    
    try:
        # Update job start time
        update_job_runtime(job_id, started_at=started_at)
        
        if progress_callback:
            progress_callback(PROGRESS_DOWNLOAD, 100, f"Downloading {filename}...")
        
        pdf_content = call_with_retry(
            lambda: download_pdf_from_drive(file_id, config['google_credentials'])
        )
        
        file_metadata = call_with_retry(
            lambda: get_file_metadata(file_id, config['google_credentials'])
        )
        
        if progress_callback:
            progress_callback(PROGRESS_PARSE, 100, f"Parsing {filename} with LlamaParse...")
        
        parsed_text = call_with_retry(
            lambda: parse_pdf_with_llamaparse(pdf_content, filename, config)
        )
        
        # Track LlamaParse costs
        num_pages = file_metadata.get('num_pages', 0)
        if num_pages > 0:
            llamaparse_cost = calculate_llamaparse_cost(num_pages)
            track_api_cost(
                job_id=job_id,
                service='llamaparse',
                units=num_pages,
                cost_usd=llamaparse_cost,
                details={
                    'filename': filename,
                    'file_id': file_id,
                    'parsing_mode': config.get('parsing_mode', 'auto'),
                    'result_type': config.get('result_type', 'markdown')
                }
            )
        
        # Save the expensive parsed text for future re-processing WITH Google Sheets metadata
        # This enriches the parsed_documents table with paper title, authors, year, topic, etc.
        save_parsed_document(
            file_id=file_id,
            filename=filename,
            parsed_text=parsed_text,
            parsing_config=config,
            file_metadata=file_metadata,
            sheet_metadata=row_metadata  # Include Google Sheets metadata
        )
        
        # Generate AI tags if enabled in product configuration
        tagging_enabled = config.get('tagging_enabled', False)
        if tagging_enabled:
            if progress_callback:
                progress_callback(PROGRESS_TAG, 100, f"Generating AI tags for {filename}...")
            
            try:
                # Check if already tagged
                if not is_document_tagged(file_id):
                    tagging_model = config.get('tagging_model', 'gpt-4o-mini')
                    prompt_template = config.get('tagging_prompt_template')
                    openai_api_key = config.get('openai_api_key')
                    
                    # Generate tags
                    tags = call_with_retry(
                        lambda: generate_tags_with_openai(
                            text=parsed_text,
                            filename=filename,
                            model=tagging_model,
                            prompt_template=prompt_template,
                            api_key=openai_api_key,
                            metadata=row_metadata
                        )
                    )
                    
                    # Validate and save tags
                    validated_tags = validate_tags(tags)
                    update_document_tags(file_id, validated_tags, tagging_model)
                    
                    logger.info(
                        f"Generated {len(validated_tags)} tags for {filename}: {validated_tags}"
                    )
                else:
                    # Load existing tags
                    validated_tags = get_document_tags(file_id)
                    logger.info(
                        f"Using existing {len(validated_tags)} tags for {filename}"
                    )
                    
                # Add tags to row_metadata so they get propagated to chunks
                row_metadata['tags'] = validated_tags
                row_metadata['auto_generated_tags'] = True
                
            except Exception as e:
                # Don't fail the entire pipeline if tagging fails
                logger.warning(
                    f"Tagging failed for {filename}: {str(e)}\n{traceback.format_exc()}"
                )
                row_metadata['tags'] = []
        
        if progress_callback:
            progress_callback(PROGRESS_CHUNK, 100, f"Chunking {filename}...")
        
        nodes = chunk_text(parsed_text, config, row_metadata)
        
        if progress_callback:
            progress_callback(
                PROGRESS_EMBED,
                100,
                f"Creating embeddings for {filename} ({len(nodes)} chunks)..."
            )
        
        embeddings = call_with_retry(
            lambda: create_embeddings(nodes, config)
        )
        
        # Track OpenAI embedding costs
        total_tokens = sum(estimate_tokens_from_text(node.get_content()) for node in nodes)
        embedding_cost = calculate_openai_embedding_cost(total_tokens)
        track_api_cost(
            job_id=job_id,
            service='openai_embeddings',
            units=total_tokens,
            cost_usd=embedding_cost,
            details={
                'filename': filename,
                'file_id': file_id,
                'num_chunks': len(nodes),
                'embedding_model': config.get('embedding_model', 'text-embedding-3-small'),
                'embedding_dimension': config.get('embedding_dimension', 1536)
            }
        )
        
        if progress_callback:
            progress_callback(PROGRESS_UPLOAD, 100, f"Uploading {filename} to Pinecone...")
        
        pinecone_index = initialize_pinecone(config)
        
        metadata_list = [node.metadata for node in nodes]
        
        vectors_uploaded = call_with_retry(
            lambda: upload_to_pinecone(
                pinecone_index,
                embeddings,
                nodes,
                metadata_list,
                namespace
            )
        )
        
        chunks_data = []
        for i, (node, embedding) in enumerate(zip(nodes, embeddings)):
            chunks_data.append({
                'chunk_id': str(uuid.uuid4()),
                'text': node.get_content(),
                'metadata': node.metadata,
                'embedding_preview': embedding[:EMBEDDING_PREVIEW_SIZE]
            })
        
        save_chunks(job_id, file_id, filename, chunks_data)
        mark_chunks_uploaded(job_id, file_id)
        
        if progress_callback:
            progress_callback(PROGRESS_COMPLETE, 100, f"Completed {filename}")
        
        # Track runtime
        processing_time = int(time.time() - start_time)
        completed_at = datetime.now()
        update_job_runtime(
            job_id=job_id,
            completed_at=completed_at,
            processing_time_seconds=processing_time
        )
        
        return {
            'status': 'success',
            'file_id': file_id,
            'filename': filename,
            'chunks': len(nodes),
            'vectors_uploaded': vectors_uploaded,
            'processing_time_seconds': processing_time
        }
        
    except Exception as e:
        error_msg = f"Error processing {filename}: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        # Track failed runtime
        processing_time = int(time.time() - start_time)
        update_job_runtime(
            job_id=job_id,
            completed_at=datetime.now(),
            processing_time_seconds=processing_time
        )
        
        return {
            'status': 'error',
            'file_id': file_id,
            'filename': filename,
            'error': str(e),
            'processing_time_seconds': processing_time
        }


@celery_app.task(bind=True, base=CallbackTask, name='tasks.process_pdf_task')
def process_pdf_task(
    self,
    file_id: str,
    filename: str,
    row_metadata: Dict[str, Any],
    config: Dict[str, Any],
    job_id: str,
    namespace: str = 'default'
) -> Dict[str, Any]:
    """
    Celery task wrapper for PDF processing (for standalone task execution).
    
    Args:
        file_id: Google Drive file ID
        filename: PDF filename
        row_metadata: Metadata from Google Sheets row
        config: Processing configuration
        job_id: Parent processing job ID
        namespace: Pinecone namespace
        
    Returns:
        Dictionary with processing results
    """
    return _process_single_pdf_logic(
        file_id, filename, row_metadata, config, job_id, namespace,
        progress_callback=self.update_progress
    )


@celery_app.task(bind=True, base=CallbackTask, name='tasks.process_batch_task')
def process_batch_task(
    self,
    source_id: int,
    selected_indices: List[int],
    config: Dict[str, Any],
    preview_mode: bool = False
) -> Dict[str, Any]:
    """
    Process a batch of PDFs from a data source.
    
    Args:
        source_id: Data source ID
        selected_indices: List of row indices to process
        config: Processing configuration
        preview_mode: If True, only parse and chunk without uploading
        
    Returns:
        Dictionary with batch processing results
    """
    # Use Celery's task ID (already created in celery_jobs table)
    from utils.db.jobs import update_celery_job_status
    from utils.diagnostic_logger import log_environment_diagnostic
    
    job_id = self.request.id
    
    try:
        logger.info("=" * 80)
        logger.info(f"🎯 TASK EXECUTION STARTED: process_batch_task")
        logger.info("=" * 80)
        logger.info(f"Task ID (job_id): {job_id}")
        logger.info(f"Source ID: {source_id}")
        logger.info(f"Papers to process: {len(selected_indices)}")
        logger.info(f"Preview mode: {preview_mode}")
        
        # Log comprehensive environment info when task starts
        log_environment_diagnostic()
        
        logger.info(f"Starting batch task: job_id={job_id}, source_id={source_id}, papers={len(selected_indices)}")
        
        # CRITICAL: Update status to 'running' FIRST (before any failures can occur)
        if not preview_mode:
            try:
                update_celery_job_status(
                    job_id,
                    'running',
                    progress_current=0,
                    progress_total=len(selected_indices),
                    progress_message='Starting batch processing...'
                )
                logger.info(f"✅ Status updated to 'running' for job {job_id}")
            except Exception as status_error:
                logger.error(f"❌ Failed to update status to running: {status_error}")
                # Continue anyway - don't fail the whole job just because status update failed
        
        # Now check if source exists
        logger.info(f"Fetching data source {source_id}...")
        source_info = get_data_source(source_id)
        
        if not source_info:
            error_msg = f'Data source {source_id} not found'
            logger.error(error_msg)
            if not preview_mode:
                update_celery_job_status(job_id, 'failed', error_message=error_msg)
            return {
                'status': 'error',
                'job_id': job_id,
                'error': error_msg
            }
        
        logger.info(f"✅ Data source found: {source_info.get('name', 'Unknown')}")
        
        # Apply product-specific configuration using centralized builder
        product_id = source_info.get('product_id')
        if product_id:
            product_config = build_product_config(product_id, base_config=config)
        else:
            product_config = config.copy()
        
        sheet_data = load_sheet_data(
            source_info['sheet_url'],
            source_info['sheet_tab'],
            product_config['google_credentials']
        )
        
        column_mapping = get_column_mapping_dict(source_id)
        drive_link_column = column_mapping.get('drive_link', 'Drive Link')
        metadata_columns = column_mapping.get('metadata_columns', [])
        namespace_column = column_mapping.get('namespace')
        default_namespace = product_config.get('default_namespace', 'default')
        
        total_files = len(selected_indices)
        results = {
            'job_id': job_id,
            'total_pdfs': 0,
            'total_chunks': 0,
            'total_embeddings': 0,
            'vectors_stored': 0,
            'new_papers_count': 0,
            'skipped_papers_count': 0,
            'details': []
        }
        
        # Process all PDFs sequentially (inline, no subtasks to avoid .get() deadlock)
        completed = 0
        total_tasks = len(selected_indices)
        
        # Get deduplication settings from product config
        enable_dedup_l1 = product_config.get('dedup_layer1', True)
        enable_dedup_l2 = product_config.get('dedup_layer2', True)
        
        for idx, row_idx in enumerate(selected_indices):
            try:
                row = sheet_data.iloc[row_idx]
                
                # Access pandas Series using bracket notation
                drive_link = row[drive_link_column] if drive_link_column in row and pd.notna(row[drive_link_column]) else ''
                file_id = extract_file_id_from_drive_link(drive_link)
                
                if not file_id:
                    results['details'].append({
                        'row': row_idx,
                        'status': 'skipped',
                        'reason': 'No valid Drive link found'
                    })
                    results['skipped_papers_count'] += 1
                    continue
                
                row_metadata = {
                    'file_id': file_id,
                    'filename': '',
                    'drive_link': drive_link
                }
                
                for col in metadata_columns:
                    if col in row:
                        row_metadata[col] = str(row[col]) if pd.notna(row[col]) else ""
                
                namespace = default_namespace
                if namespace_column and namespace_column in row and pd.notna(row[namespace_column]):
                    namespace = str(row[namespace_column])
                
                filename = row_metadata.get('filename', f'file_{file_id}.pdf')
                
                # Check for duplicates before processing (unless in preview mode)
                if not preview_mode:
                    paper_title_col = column_mapping.get('paper_title', '')
                    paper_title = row[paper_title_col] if paper_title_col and paper_title_col in row and pd.notna(row[paper_title_col]) else ''
                    
                    authors_col = column_mapping.get('authors', '')
                    authors = row[authors_col] if authors_col and authors_col in row and pd.notna(row[authors_col]) else ''
                    
                    dedup_result = check_all_layers(
                        drive_file_id=file_id,
                        paper_title=str(paper_title) if pd.notna(paper_title) else '',
                        authors=str(authors) if pd.notna(authors) else '',
                        embedding=None,
                        namespace=namespace,
                        pinecone_index=None,
                        enable_layer1=enable_dedup_l1,
                        enable_layer2=enable_dedup_l2,
                        enable_layer3=False,
                        product_id=product_id
                    )
                    
                    if dedup_result['is_duplicate']:
                        logger.info(f"Skipping duplicate paper: {filename} (Layer: {dedup_result['duplicate_layer']})")
                        results['details'].append({
                            'row': row_idx,
                            'file_id': file_id,
                            'filename': filename,
                            'status': 'skipped',
                            'reason': f"Duplicate detected ({dedup_result['duplicate_layer']})",
                            'existing_paper': dedup_result.get('existing_paper')
                        })
                        results['skipped_papers_count'] += 1
                        completed += 1
                        continue
                
                # Process PDF inline (no subtask spawning)
                logger.info(f"Processing {idx + 1}/{total_tasks}: {filename}")
                pdf_result_data = _process_single_pdf_logic(
                    file_id=file_id,
                    filename=filename,
                    row_metadata=row_metadata,
                    config=product_config,
                    job_id=job_id,
                    namespace=namespace,
                    progress_callback=None  # Don't update progress for each file step
                )
                
                results['details'].append(pdf_result_data)
                
                if pdf_result_data['status'] == 'success':
                    results['total_pdfs'] += 1
                    results['total_chunks'] += pdf_result_data.get('chunks', 0)
                    results['vectors_stored'] += pdf_result_data.get('vectors_uploaded', 0)
                    results['new_papers_count'] += 1
                
                completed += 1
                
                # Update progress after each PDF
                progress_msg = f"Completed {completed}/{total_tasks} PDFs..."
                self.update_progress(completed, total_tasks, progress_msg)
                
                if not preview_mode:
                    update_celery_job_status(
                        job_id,
                        'running',
                        progress_current=completed,
                        progress_total=total_tasks,
                        progress_message=progress_msg
                    )
                
            except Exception as e:
                logger.error(f"Error processing row {row_idx}: {str(e)}\n{traceback.format_exc()}")
                results['details'].append({
                    'row': row_idx,
                    'status': 'error',
                    'error': str(e)
                })
                completed += 1
        
        # Final progress update
        self.update_progress(total_tasks, total_tasks, "Batch processing completed")
        
        if not preview_mode:
            update_celery_job_status(
                job_id,
                'completed',
                progress_current=total_tasks,
                progress_total=total_tasks,
                progress_message=f"Completed! Processed {results['new_papers_count']} new papers, skipped {results['skipped_papers_count']} duplicates",
                result=results,
                new_papers_count=results['new_papers_count'],
                skipped_papers_count=results['skipped_papers_count']
            )
        
        return results
        
    except TransientError as e:
        # Transient errors should be retried (network, timeouts, rate limits)
        error_msg = f"Transient error in batch processing: {str(e)}"
        logger.warning(f"{error_msg} - will retry")
        
        if not preview_mode:
            update_celery_job_status(
                job_id,
                'running',
                progress_message=f"Retrying after: {str(e)}"
            )
        
        raise self.retry(exc=e, countdown=CELERY_RETRY_COUNTDOWN, max_retries=CELERY_MAX_RETRIES)
        
    except Exception as e:
        # Permanent errors should fail immediately
        error_msg = f"Error in batch processing: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        if not preview_mode:
            update_celery_job_status(job_id, 'failed', error_message=str(e))
        
        return {
            'status': 'error',
            'job_id': job_id,
            'error': error_msg,
            'traceback': traceback.format_exc()
        }

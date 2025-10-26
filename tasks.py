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

# Product config mapping (reduces duplication)
PRODUCT_CONFIG_MAPPING = {
    'llama_api_key': 'LLAMA_CLOUD_API_KEY',
    'openai_api_key': 'OPENAI_API_KEY',
    'pinecone_api_key': 'PINECONE_API_KEY',
    'google_credentials': 'GOOGLE_CREDENTIALS'
}

# Product settings mapping
PRODUCT_SETTINGS_MAPPING = {
    'index_name': 'pinecone_index',
    'pinecone_environment': 'pinecone_environment',
    'default_namespace': 'default_namespace',
    'parsing_mode': 'parsing_mode',
    'result_type': 'result_type',
    'language': 'language',
    'use_vendor_multimodal': 'use_vendor_multimodal',
    'page_separator': 'page_separator',
    'chunking_strategy': 'default_chunking_strategy',
    'chunk_size': 'default_chunk_size',
    'chunk_overlap': 'chunk_overlap',
    'semantic_buffer_size': 'semantic_buffer_size',
    'embedding_model': 'default_embedding_model',
    'embedding_dimension': 'embedding_dimension',
    'tagging_enabled': 'tagging_enabled',
    'tagging_model': 'tagging_model',
    'tagging_prompt_template': 'tagging_prompt_template',
    'tagging_config': 'tagging_config'
}


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
    exceptions: Tuple[type, ...] = (Exception,)
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


def apply_product_config(config: Dict[str, Any], product_info: Dict[str, Any]) -> None:
    """
    Apply product-specific configuration in place.
    
    Simplifies config building by using mapping dictionaries instead of
    repetitive if-statements.
    
    Args:
        config: Configuration dictionary to update
        product_info: Product information from database
    """
    if not product_info or not product_info['active']:
        return
    
    logger.info(f"Applying product-specific settings: {product_info['name']}")
    
    # Apply API keys using mapping dict
    product_api_keys = get_product_api_keys(product_info['id'])
    for config_key, api_key in PRODUCT_CONFIG_MAPPING.items():
        if product_api_keys.get(api_key):
            config[config_key] = product_api_keys[api_key]
            logger.debug(f"  - Applied {api_key}")
    
    # Apply product settings using mapping dict
    for config_key, product_key in PRODUCT_SETTINGS_MAPPING.items():
        value = product_info.get(product_key)
        if value is not None:
            config[config_key] = value


# ============================================
# TASKS
# ============================================

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
    Process a single PDF: download, parse, chunk, embed, and upload to Pinecone.
    
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
    try:
        self.update_progress(PROGRESS_DOWNLOAD, 100, f"Downloading {filename}...")
        
        pdf_content = call_with_retry(
            lambda: download_pdf_from_drive(file_id, config['google_credentials'])
        )
        
        file_metadata = call_with_retry(
            lambda: get_file_metadata(file_id, config['google_credentials'])
        )
        
        self.update_progress(PROGRESS_PARSE, 100, f"Parsing {filename} with LlamaParse...")
        
        parsed_text = call_with_retry(
            lambda: parse_pdf_with_llamaparse(pdf_content, filename, config)
        )
        
        # Save the expensive parsed text for future re-processing
        save_parsed_document(
            file_id=file_id,
            filename=filename,
            parsed_text=parsed_text,
            parsing_config=config,
            file_metadata=file_metadata
        )
        
        # Generate AI tags if enabled in product configuration
        tagging_enabled = config.get('tagging_enabled', False)
        if tagging_enabled:
            self.update_progress(PROGRESS_TAG, 100, f"Generating AI tags for {filename}...")
            
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
        
        self.update_progress(PROGRESS_CHUNK, 100, f"Chunking {filename}...")
        
        nodes = chunk_text(parsed_text, config, row_metadata)
        
        self.update_progress(
            PROGRESS_EMBED,
            100,
            f"Creating embeddings for {filename} ({len(nodes)} chunks)..."
        )
        
        embeddings = call_with_retry(
            lambda: create_embeddings(nodes, config)
        )
        
        self.update_progress(PROGRESS_UPLOAD, 100, f"Uploading {filename} to Pinecone...")
        
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
        
        self.update_progress(PROGRESS_COMPLETE, 100, f"Completed {filename}")
        
        return {
            'status': 'success',
            'file_id': file_id,
            'filename': filename,
            'chunks': len(nodes),
            'vectors_uploaded': vectors_uploaded
        }
        
    except Exception as e:
        error_msg = f"Error processing {filename}: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        try:
            raise self.retry(exc=e, countdown=CELERY_RETRY_COUNTDOWN, max_retries=CELERY_MAX_RETRIES)
        except self.MaxRetriesExceededError:
            return {
                'status': 'error',
                'file_id': file_id,
                'filename': filename,
                'error': f"Max retries exceeded: {str(e)}"
            }


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
    job_id = str(uuid.uuid4())
    
    try:
        if not preview_mode:
            create_processing_job(job_id, config)
            update_job_status(job_id, 'running')
        
        source_info = get_data_source(source_id)
        
        if not source_info:
            return {
                'status': 'error',
                'error': f'Data source {source_id} not found'
            }
        
        product_config = config.copy()
        
        # Apply product-specific configuration using simplified mapping approach
        if source_info.get('product_id'):
            product_info = get_product(source_info['product_id'])
            if product_info:
                apply_product_config(product_config, product_info)
        
        sheet_data = load_sheet_data(
            source_info['sheet_url'],
            source_info['sheet_tab_name'],
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
            'details': []
        }
        
        for idx, row_idx in enumerate(selected_indices):
            self.update_progress(
                idx,
                total_files,
                f"Processing PDF {idx + 1} of {total_files}..."
            )
            
            row = sheet_data.iloc[row_idx]
            
            drive_link = row.get(drive_link_column, '')
            file_id = extract_file_id_from_drive_link(drive_link)
            
            if not file_id:
                results['details'].append({
                    'row': row_idx,
                    'status': 'skipped',
                    'reason': 'No valid Drive link found'
                })
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
            
            pdf_result = process_pdf_task.apply_async(args=[
                file_id,
                row_metadata.get('filename', f'file_{file_id}.pdf'),
                row_metadata,
                product_config,
                job_id,
                namespace
            ])
            
            pdf_result_data = pdf_result.get()
            
            results['details'].append(pdf_result_data)
            
            if pdf_result_data['status'] == 'success':
                results['total_pdfs'] += 1
                results['total_chunks'] += pdf_result_data.get('chunks', 0)
                results['vectors_stored'] += pdf_result_data.get('vectors_uploaded', 0)
        
        if not preview_mode:
            update_job_status(
                job_id,
                'completed',
                total_pdfs=results['total_pdfs'],
                total_chunks=results['total_chunks'],
                vectors_stored=results['vectors_stored']
            )
        
        self.update_progress(total_files, total_files, "Batch processing completed")
        
        return results
        
    except Exception as e:
        error_msg = f"Error in batch processing: {str(e)}"
        logger.error(f"{error_msg}\n{traceback.format_exc()}")
        
        if not preview_mode:
            update_job_status(job_id, 'error')
        
        try:
            raise self.retry(exc=e, countdown=CELERY_RETRY_COUNTDOWN, max_retries=CELERY_MAX_RETRIES)
        except self.MaxRetriesExceededError:
            return {
                'status': 'error',
                'job_id': job_id,
                'error': f"Max retries exceeded: {str(e)}"
            }

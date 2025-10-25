"""
Celery tasks for PDF processing pipeline.
"""

from celery import Task
from celeryconfig import celery_app
import pandas as pd
from typing import Dict, List, Optional
import uuid
import time
import traceback

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
    get_product, get_product_api_keys
)


class CallbackTask(Task):
    """Base task class that handles progress callbacks."""
    
    def update_progress(self, current, total, message):
        """Update task progress."""
        self.update_state(
            state='PROGRESS',
            meta={
                'current': current,
                'total': total,
                'message': message,
                'percent': int((current / total) * 100) if total > 0 else 0
            }
        )


def call_with_retry(func, max_retries=3, backoff_factor=2, exceptions=(Exception,)):
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
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            return func()
        except exceptions as e:
            last_exception = e
            if attempt == max_retries - 1:
                raise
            
            wait_time = backoff_factor ** attempt
            print(f"Attempt {attempt + 1} failed: {str(e)}. Retrying in {wait_time}s...")
            time.sleep(wait_time)
    
    raise last_exception


@celery_app.task(bind=True, base=CallbackTask, name='tasks.process_pdf_task')
def process_pdf_task(
    self,
    file_id: str,
    filename: str,
    row_metadata: Dict,
    config: Dict,
    job_id: str,
    namespace: str = 'default'
) -> Dict:
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
        self.update_progress(0, 100, f"Downloading {filename}...")
        
        pdf_content = call_with_retry(
            lambda: download_pdf_from_drive(file_id, config['google_credentials'])
        )
        
        file_metadata = call_with_retry(
            lambda: get_file_metadata(file_id, config['google_credentials'])
        )
        
        self.update_progress(20, 100, f"Parsing {filename} with LlamaParse...")
        
        parsed_text = call_with_retry(
            lambda: parse_pdf_with_llamaparse(pdf_content, filename, config)
        )
        
        self.update_progress(40, 100, f"Chunking {filename}...")
        
        nodes = chunk_text(parsed_text, config, row_metadata)
        
        self.update_progress(60, 100, f"Creating embeddings for {filename} ({len(nodes)} chunks)...")
        
        embeddings = call_with_retry(
            lambda: create_embeddings(nodes, config)
        )
        
        self.update_progress(80, 100, f"Uploading {filename} to Pinecone...")
        
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
                'embedding_preview': embedding[:5]
            })
        
        save_chunks(job_id, file_id, filename, chunks_data)
        mark_chunks_uploaded(job_id, file_id)
        
        self.update_progress(100, 100, f"Completed {filename}")
        
        return {
            'status': 'success',
            'file_id': file_id,
            'filename': filename,
            'chunks': len(nodes),
            'vectors_uploaded': vectors_uploaded
        }
        
    except Exception as e:
        error_msg = f"Error processing {filename}: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        
        return {
            'status': 'error',
            'file_id': file_id,
            'filename': filename,
            'error': str(e)
        }


@celery_app.task(bind=True, base=CallbackTask, name='tasks.process_batch_task')
def process_batch_task(
    self,
    source_id: int,
    selected_indices: List[int],
    config: Dict,
    preview_mode: bool = False
) -> Dict:
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
        
        sheet_data = load_sheet_data(
            source_info['sheet_url'],
            source_info['sheet_tab_name'],
            config['google_credentials']
        )
        
        column_mapping = get_column_mapping_dict(source_id)
        drive_link_column = column_mapping.get('drive_link', 'Drive Link')
        metadata_columns = column_mapping.get('metadata_columns', [])
        namespace_column = column_mapping.get('namespace')
        default_namespace = config.get('default_namespace', 'default')
        
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
            
            pdf_result = process_pdf_task.apply(args=[
                file_id,
                row_metadata.get('filename', f'file_{file_id}.pdf'),
                row_metadata,
                config,
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
        print(error_msg)
        print(traceback.format_exc())
        
        if not preview_mode:
            update_job_status(job_id, 'error')
        
        return {
            'status': 'error',
            'job_id': job_id,
            'error': str(e)
        }

import pandas as pd
from typing import List, Dict, Callable, Optional
import uuid
from utils.google_sheets import extract_file_id_from_drive_link
from utils.google_drive import download_pdf_from_drive, get_file_metadata
from utils.llama_parser import parse_pdf_with_llamaparse
from utils.chunker import chunk_text
from utils.embedder import create_embeddings
from utils.pinecone_uploader import initialize_pinecone, upload_to_pinecone
from utils.database import (
    create_processing_job, update_job_status, 
    save_chunks, mark_chunks_uploaded
)

def process_pipeline(
    sheet_data: pd.DataFrame,
    selected_indices: List[int],
    config: Dict,
    progress_callback: Optional[Callable] = None,
    preview_mode: bool = False
) -> Dict:
    """
    Main processing pipeline for PDF chunking and embedding.
    
    Args:
        sheet_data: DataFrame containing metadata from Google Sheets
        selected_indices: List of row indices to process
        config: Configuration dictionary
        progress_callback: Optional callback function for progress updates
        preview_mode: If True, only parse and chunk without uploading to Pinecone
        
    Returns:
        Dictionary containing processing results
    """
    job_id = str(uuid.uuid4())
    
    create_processing_job(job_id, config)
    update_job_status(job_id, 'running')
    
    results = {
        'job_id': job_id,
        'total_pdfs': 0,
        'total_chunks': 0,
        'total_embeddings': 0,
        'vectors_stored': 0,
        'details': [],
        'preview_chunks': [] if preview_mode else None
    }
    
    drive_link_column = config.get('drive_link_column', 'Drive Link')
    metadata_columns = config.get('metadata_columns', [])
    namespace_column = config.get('namespace_column')
    default_namespace = config.get('default_namespace', 'default')
    
    if not preview_mode:
        pinecone_index = initialize_pinecone(config)
    else:
        pinecone_index = None
    
    total_files = len(selected_indices)
    
    for idx, row_idx in enumerate(selected_indices):
        try:
            if progress_callback:
                progress_callback(
                    int((idx / total_files) * 100),
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
            
            if progress_callback:
                progress_callback(
                    int((idx / total_files) * 100),
                    f"Downloading PDF {idx + 1}..."
                )
            
            pdf_content = download_pdf_from_drive(file_id, config['google_credentials'])
            file_metadata = get_file_metadata(file_id, config['google_credentials'])
            
            if progress_callback:
                progress_callback(
                    int((idx / total_files) * 100),
                    f"Parsing PDF {idx + 1} with LlamaParse..."
                )
            
            parsed_text = parse_pdf_with_llamaparse(
                pdf_content,
                file_metadata.get('name', f'file_{file_id}.pdf'),
                config
            )
            
            row_metadata = {
                'file_id': file_id,
                'filename': file_metadata.get('name', ''),
                'drive_link': drive_link
            }
            
            for col in metadata_columns:
                if col in row:
                    row_metadata[col] = str(row[col]) if pd.notna(row[col]) else ""
            
            if progress_callback:
                progress_callback(
                    int((idx / total_files) * 100),
                    f"Chunking PDF {idx + 1}..."
                )
            
            nodes = chunk_text(parsed_text, config, row_metadata)
            
            if progress_callback:
                progress_callback(
                    int((idx / total_files) * 100),
                    f"Creating embeddings for PDF {idx + 1} ({len(nodes)} chunks)..."
                )
            
            embeddings = create_embeddings(nodes, config)
            
            namespace = default_namespace
            if namespace_column and namespace_column in row:
                namespace_value = row[namespace_column]
                if pd.notna(namespace_value) and str(namespace_value).strip():
                    namespace = str(namespace_value).strip()
            
            metadata_list = [row_metadata.copy() for _ in range(len(nodes))]
            
            chunks_data = []
            for i, node in enumerate(nodes):
                chunks_data.append({
                    'text': node.get_content(),
                    'metadata': metadata_list[i],
                    'namespace': namespace
                })
            
            save_chunks(job_id, file_id, file_metadata.get('name', ''), chunks_data)
            
            if preview_mode:
                results['preview_chunks'].extend(chunks_data)
            else:
                if progress_callback:
                    progress_callback(
                        int((idx / total_files) * 100),
                        f"Uploading to Pinecone (namespace: {namespace})..."
                    )
                
                uploaded_count = upload_to_pinecone(
                    pinecone_index,
                    embeddings,
                    nodes,
                    metadata_list,
                    namespace
                )
                
                mark_chunks_uploaded(job_id, file_id)
                results['vectors_stored'] += uploaded_count
            
            results['total_pdfs'] += 1
            results['total_chunks'] += len(nodes)
            results['total_embeddings'] += len(embeddings)
            
            results['details'].append({
                'row': row_idx,
                'file_id': file_id,
                'filename': file_metadata.get('name', ''),
                'chunks': len(nodes),
                'namespace': namespace,
                'status': 'success'
            })
            
        except Exception as e:
            results['details'].append({
                'row': row_idx,
                'status': 'error',
                'error': str(e)
            })
            update_job_status(job_id, 'error')
    
    if progress_callback:
        progress_callback(100, "Processing complete!")
    
    update_job_status(
        job_id, 
        'completed' if not preview_mode else 'preview',
        total_pdfs=results['total_pdfs'],
        processed_pdfs=results['total_pdfs'],
        total_chunks=results['total_chunks'],
        total_embeddings=results['total_embeddings'],
        vectors_stored=results.get('vectors_stored', 0)
    )
    
    return results

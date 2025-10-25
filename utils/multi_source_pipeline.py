"""
Multi-source pipeline for processing papers from multiple data sources.
"""

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
    save_chunks, mark_chunks_uploaded, update_last_processed,
    get_data_source, get_column_mapping_dict
)


def process_multi_source_pipeline(
    source_configs: List[Dict],
    config: Dict,
    progress_callback: Optional[Callable] = None,
    preview_mode: bool = False
) -> Dict:
    """
    Process papers from multiple data sources.
    
    Args:
        source_configs: List of dicts with keys: source_id, data (DataFrame), selected_indices
        config: Global configuration dictionary
        progress_callback: Optional callback for progress updates
        preview_mode: If True, only parse and chunk without uploading
        
    Returns:
        Dictionary containing processing results
    """
    job_id = str(uuid.uuid4())
    has_errors = False
    
    if not preview_mode:
        create_processing_job(job_id, config)
        update_job_status(job_id, 'running')
    
    results = {
        'job_id': job_id,
        'total_pdfs': 0,
        'total_chunks': 0,
        'total_embeddings': 0,
        'vectors_stored': 0,
        'details': [],
        'preview_chunks': [] if preview_mode else None,
        'sources_processed': {}
    }
    
    if not preview_mode:
        pinecone_index = initialize_pinecone(config)
    else:
        pinecone_index = None
    
    total_papers = sum(len(sc.get('selected_indices', [])) for sc in source_configs)
    processed_papers = 0
    
    for source_config in source_configs:
        source_id = source_config['source_id']
        sheet_data = source_config['data']
        selected_indices = source_config.get('selected_indices', [])
        
        source_info = get_data_source(source_id)
        if not source_info:
            results['details'].append({
                'source_id': source_id,
                'status': 'error',
                'error': 'Source not found'
            })
            continue
        
        column_mappings = get_column_mapping_dict(source_id)
        drive_link_column = column_mappings.get('drive_link', 'Drive Link')
        default_namespace = source_info['default_namespace']
        
        source_results = {
            'source_id': source_id,
            'source_name': source_info['name'],
            'papers_processed': 0,
            'chunks_created': 0,
            'last_row_processed': 0
        }
        
        for idx in selected_indices:
            try:
                processed_papers += 1
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Processing paper {processed_papers}/{total_papers} from {source_info['name']}..."
                    )
                
                row = sheet_data.iloc[idx]
                
                drive_link = row.get(drive_link_column, '')
                file_id = extract_file_id_from_drive_link(drive_link)
                
                if not file_id:
                    results['details'].append({
                        'source': source_info['name'],
                        'row': idx,
                        'status': 'skipped',
                        'reason': 'No valid Drive link'
                    })
                    continue
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Downloading PDF from {source_info['name']}..."
                    )
                
                pdf_content = download_pdf_from_drive(file_id, config['google_credentials'])
                file_metadata = get_file_metadata(file_id, config['google_credentials'])
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Parsing PDF with LlamaParse..."
                    )
                
                parsed_text = parse_pdf_with_llamaparse(
                    pdf_content,
                    file_metadata.get('name', f'file_{file_id}.pdf'),
                    config
                )
                
                row_metadata = {
                    'file_id': file_id,
                    'filename': file_metadata.get('name', ''),
                    'drive_link': drive_link,
                    'source': source_info['name'],
                    'source_id': source_id,
                    'topic': source_info.get('topic', '')
                }
                
                for role, col_name in column_mappings.items():
                    if role != 'drive_link' and col_name in row:
                        value = row[col_name]
                        if pd.notna(value):
                            row_metadata[role] = str(value)
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Chunking text..."
                    )
                
                nodes = chunk_text(parsed_text, config, row_metadata)
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Creating embeddings ({len(nodes)} chunks)..."
                    )
                
                embeddings = create_embeddings(nodes, config)
                
                namespace = default_namespace
                namespace_col = column_mappings.get('namespace')
                if namespace_col and namespace_col in row:
                    namespace_value = row[namespace_col]
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
                
                if preview_mode:
                    results['preview_chunks'].extend(chunks_data)
                else:
                    save_chunks(job_id, file_id, file_metadata.get('name', ''), chunks_data)
                    
                    if progress_callback:
                        progress_callback(
                            int((processed_papers / total_papers) * 100),
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
                source_results['papers_processed'] += 1
                source_results['chunks_created'] += len(nodes)
                source_results['last_row_processed'] = idx + 1
                
                results['details'].append({
                    'source': source_info['name'],
                    'row': idx,
                    'file_id': file_id,
                    'filename': file_metadata.get('name', ''),
                    'chunks': len(nodes),
                    'namespace': namespace,
                    'status': 'success'
                })
                
            except Exception as e:
                has_errors = True
                results['details'].append({
                    'source': source_info['name'],
                    'row': idx,
                    'status': 'error',
                    'error': str(e)
                })
                if not preview_mode:
                    update_job_status(job_id, 'error')
        
        if not preview_mode and source_results['papers_processed'] > 0:
            update_last_processed(source_id, source_results['last_row_processed'])
        
        results['sources_processed'][source_info['name']] = source_results
    
    if progress_callback:
        progress_callback(100, "Processing complete!")
    
    if not preview_mode:
        if has_errors:
            final_status = 'error'
        else:
            final_status = 'completed'
        
        update_job_status(
            job_id,
            final_status,
            total_pdfs=results['total_pdfs'],
            processed_pdfs=results['total_pdfs'],
            total_chunks=results['total_chunks'],
            total_embeddings=results['total_embeddings'],
            vectors_stored=results.get('vectors_stored', 0)
        )
    
    return results

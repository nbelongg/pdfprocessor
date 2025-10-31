"""
Multi-source pipeline for processing papers from multiple data sources.
"""

import pandas as pd
from typing import List, Dict, Callable, Optional
import uuid
import logging
from utils.google_sheets import extract_file_id_from_drive_link, extract_tags_from_row

logger = logging.getLogger(__name__)
from utils.google_drive import download_pdf_from_drive, get_file_metadata
from utils.llama_parser import parse_pdf_with_llamaparse
from utils.chunker import chunk_text
from utils.embedder import create_embeddings
from utils.pinecone_uploader import initialize_pinecone, upload_to_pinecone
from utils.database import (
    create_processing_job, update_job_status, 
    save_chunks, mark_chunks_uploaded, update_last_processed,
    get_data_source, get_column_mapping_dict, get_product, get_product_api_keys,
    update_document_tags, get_document_tags, is_document_tagged
)
from utils.db.tag_configs import get_tag_configurations
from utils.deduplication import check_all_layers, record_or_update_paper
from utils.tagger import generate_tags_with_openai, validate_tags
from utils.config_builder import build_product_config
import os


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
        
        # Load product-specific configuration using centralized builder
        product_index = None
        
        if source_info.get('product_id'):
            try:
                # Build product-specific config using centralized function
                product_config = build_product_config(source_info['product_id'], base_config=config)
                
                # Initialize product-specific Pinecone index if not already done
                if not preview_mode and product_index is None:
                    product_index = initialize_pinecone(product_config)
            except ValueError as e:
                # Product not found or config error, use global config
                product_config = config
                product_index = pinecone_index
        else:
            # No product assigned, use global config
            product_config = config
            product_index = pinecone_index
        
        column_mappings = get_column_mapping_dict(source_id)
        drive_link_column = column_mappings.get('drive_link', 'Drive Link')
        default_namespace = source_info['default_namespace']
        
        # Debug: Log available columns and what we're looking for
        if not sheet_data.empty:
            available_columns = list(sheet_data.columns)
            logger.info(f"Source '{source_info['name']}' - Looking for column '{drive_link_column}'")
            logger.info(f"Available columns: {available_columns}")
            logger.info(f"Sheet data shape: {sheet_data.shape}")
            logger.info(f"First few values in '{drive_link_column}': {sheet_data[drive_link_column].head(3).tolist() if drive_link_column in sheet_data.columns else 'COLUMN NOT FOUND'}")
            if drive_link_column not in available_columns:
                logger.warning(f"Drive link column '{drive_link_column}' not found in sheet! Available columns: {available_columns}")
        
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
                    # Add debug info to help diagnose the issue
                    available_cols = list(sheet_data.columns)
                    drive_link_value = row.get(drive_link_column, '<NOT FOUND>')
                    
                    # Also check if value looks like a URL vs filename
                    value_analysis = "LOOKS LIKE FILENAME" if (isinstance(drive_link_value, str) and drive_link_value.endswith('.pdf')) else "UNKNOWN FORMAT"
                    if isinstance(drive_link_value, str) and 'drive.google.com' in drive_link_value:
                        value_analysis = "LOOKS LIKE URL (but file_id extraction failed)"
                    
                    results['details'].append({
                        'source': source_info['name'],
                        'row': idx,
                        'status': 'skipped',
                        'reason': f'No valid Drive link ({value_analysis}). Column: "{drive_link_column}", Value: "{str(drive_link_value)[:100]}"'
                    })
                    continue
                
                paper_title = row.get(column_mappings.get('paper_title', ''), '') if column_mappings.get('paper_title') else ''
                authors = row.get(column_mappings.get('authors', ''), '') if column_mappings.get('authors') else ''
                
                dedup_result = None
                if not preview_mode:
                    enable_dedup_l1 = product_config.get('dedup_layer1', True)
                    enable_dedup_l2 = product_config.get('dedup_layer2', True)
                    
                    dedup_result = check_all_layers(
                        drive_file_id=file_id,
                        paper_title=str(paper_title) if pd.notna(paper_title) else '',
                        authors=str(authors) if pd.notna(authors) else '',
                        embedding=None,
                        namespace='default',
                        pinecone_index=None,
                        enable_layer1=enable_dedup_l1,
                        enable_layer2=enable_dedup_l2,
                        enable_layer3=False
                    )
                    
                    if dedup_result['is_duplicate']:
                        results['details'].append({
                            'source': source_info['name'],
                            'row': idx,
                            'file_id': file_id,
                            'status': 'skipped_duplicate',
                            'duplicate_layer': dedup_result['duplicate_layer'],
                            'existing_paper': dedup_result['existing_paper']
                        })
                        
                        record_or_update_paper(
                            drive_file_id=file_id,
                            content_hash=dedup_result['content_hash'],
                            paper_title=str(paper_title) if pd.notna(paper_title) else '',
                            authors=str(authors) if pd.notna(authors) else '',
                            metadata={},
                            pinecone_namespace='default',
                            source_id=source_id,
                            row_number=idx,
                            is_duplicate=True,
                            existing_paper=dedup_result['existing_paper']
                        )
                        continue
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Downloading PDF from {source_info['name']}..."
                    )
                
                pdf_content = download_pdf_from_drive(file_id, product_config['google_credentials'])
                file_metadata = get_file_metadata(file_id, product_config['google_credentials'])
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Parsing PDF with LlamaParse..."
                    )
                
                parsed_text = parse_pdf_with_llamaparse(
                    pdf_content,
                    file_metadata.get('name', f'file_{file_id}.pdf'),
                    product_config
                )
                
                # Save the expensive parsed text for future re-processing
                from utils.database import save_parsed_document
                save_parsed_document(
                    file_id=file_id,
                    filename=file_metadata.get('name', f'file_{file_id}.pdf'),
                    parsed_text=parsed_text,
                    parsing_config=product_config,
                    file_metadata=file_metadata
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
                
                # Extract tags from spreadsheet columns based on tag configurations
                spreadsheet_tags = []
                try:
                    tag_configs = get_tag_configurations(source_id)
                    if tag_configs:
                        spreadsheet_tags = extract_tags_from_row(row, tag_configs, column_mappings)
                        logger.info(f"Extracted {len(spreadsheet_tags)} tags from spreadsheet: {spreadsheet_tags}")
                except Exception as e:
                    logger.warning(f"Failed to extract spreadsheet tags: {str(e)}")
                
                # Generate AI tags if enabled in product configuration
                tagging_enabled = product_config.get('tagging_enabled', False)
                if tagging_enabled:
                    if progress_callback:
                        progress_callback(
                            int((processed_papers / total_papers) * 100),
                            f"Generating AI tags..."
                        )
                    
                    try:
                        # Check if already tagged
                        if not is_document_tagged(file_id):
                            tagging_model = product_config.get('tagging_model', 'gpt-4o-mini')
                            prompt_template = product_config.get('tagging_prompt_template')
                            openai_api_key = product_config.get('openai_api_key')
                            
                            # Generate tags
                            tags = generate_tags_with_openai(
                                text=parsed_text,
                                filename=file_metadata.get('name', f'file_{file_id}.pdf'),
                                model=tagging_model,
                                prompt_template=prompt_template,
                                api_key=openai_api_key,
                                metadata=row_metadata
                            )
                            
                            # Validate and save tags
                            validated_tags = validate_tags(tags)
                            update_document_tags(file_id, validated_tags, tagging_model)
                        else:
                            # Load existing tags
                            validated_tags = get_document_tags(file_id)
                            
                        # Merge AI tags with spreadsheet tags
                        all_tags = list(spreadsheet_tags) + list(validated_tags)
                        # Deduplicate while preserving order
                        seen = set()
                        unique_tags = []
                        for tag in all_tags:
                            if tag not in seen:
                                seen.add(tag)
                                unique_tags.append(tag)
                        
                        row_metadata['tags'] = unique_tags
                        row_metadata['auto_generated_tags'] = True
                        row_metadata['spreadsheet_tags_count'] = len(spreadsheet_tags)
                        row_metadata['ai_tags_count'] = len(validated_tags)
                        
                    except Exception as e:
                        # Don't fail the entire pipeline if tagging fails
                        logger.warning(f"Tagging failed for {file_metadata.get('name', '')}: {str(e)}")
                        # Use spreadsheet tags only if AI tagging fails
                        row_metadata['tags'] = spreadsheet_tags if spreadsheet_tags else []
                else:
                    # If AI tagging is disabled, use spreadsheet tags only
                    if spreadsheet_tags:
                        row_metadata['tags'] = spreadsheet_tags
                        row_metadata['spreadsheet_tags_only'] = True
                        logger.info(f"Using {len(spreadsheet_tags)} spreadsheet tags (AI tagging disabled)")
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Chunking text..."
                    )
                
                nodes = chunk_text(parsed_text, product_config, row_metadata)
                
                if progress_callback:
                    progress_callback(
                        int((processed_papers / total_papers) * 100),
                        f"Creating embeddings ({len(nodes)} chunks)..."
                    )
                
                embeddings = create_embeddings(nodes, product_config)
                
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
                        product_index,
                        embeddings,
                        nodes,
                        metadata_list,
                        namespace
                    )
                    
                    mark_chunks_uploaded(job_id, file_id)
                    results['vectors_stored'] += uploaded_count
                    
                    from utils.deduplication import generate_content_hash
                    content_hash = generate_content_hash(
                        str(paper_title) if pd.notna(paper_title) else '',
                        str(authors) if pd.notna(authors) else ''
                    )
                    
                    record_or_update_paper(
                        drive_file_id=file_id,
                        content_hash=content_hash,
                        paper_title=str(paper_title) if pd.notna(paper_title) else '',
                        authors=str(authors) if pd.notna(authors) else '',
                        metadata=row_metadata,
                        pinecone_namespace=namespace,
                        source_id=source_id,
                        row_number=idx,
                        is_duplicate=False,
                        existing_paper=None
                    )
                
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

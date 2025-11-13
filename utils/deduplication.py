"""
Three-layer deduplication system for PDF processing.

This module implements a multi-tiered approach to prevent duplicate processing:
- Layer 1: Google Drive file ID lookup (fastest)
- Layer 2: Content hash comparison (title + authors)
- Layer 3: Embedding similarity search (most thorough)

Usage:
    from utils.deduplication import check_all_layers
    
    is_duplicate, existing_data = check_all_layers(
        drive_file_id='abc123',
        paper_title='Sample Paper',
        authors='John Doe',
        embedding=[0.1, 0.2, ...],
        namespace='research',
        pinecone_index=index
    )
"""

import hashlib
import logging
from typing import Dict, List, Optional, Tuple
from utils.database import (
    check_paper_processed,
    check_paper_by_content_hash,
    record_processed_paper,
    update_processed_paper
)

logger = logging.getLogger(__name__)

def generate_content_hash(paper_title: str, authors: str) -> str:
    """Generate a content hash from paper title and authors."""
    normalized_title = paper_title.lower().strip() if paper_title else ""
    normalized_authors = authors.lower().strip() if authors else ""
    
    content = f"{normalized_title}|{normalized_authors}"
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def check_duplicate_layer1(drive_file_id: str, product_id: int = None) -> Tuple[bool, Optional[Dict]]:
    """
    Layer 1: Check if paper already processed by Drive file ID.
    
    Args:
        drive_file_id: Google Drive file ID
        product_id: Optional product ID for product-scoped deduplication
        
    Returns:
        (is_duplicate, existing_paper_data)
    """
    existing = check_paper_processed(drive_file_id, product_id)
    if existing:
        return True, existing
    return False, None

def check_duplicate_layer2(paper_title: str, authors: str, product_id: int = None) -> Tuple[bool, Optional[Dict]]:
    """
    Layer 2: Check if paper already processed by content hash (title + authors).
    
    Args:
        paper_title: Paper title
        authors: Paper authors  
        product_id: Optional product ID for product-scoped deduplication
        
    Returns:
        (is_duplicate, existing_paper_data)
    """
    if not paper_title and not authors:
        return False, None
    
    content_hash = generate_content_hash(paper_title, authors)
    existing = check_paper_by_content_hash(content_hash, product_id)
    if existing:
        return True, existing
    return False, None

def check_duplicate_layer3(embedding: List[float], namespace: str, pinecone_index, similarity_threshold: float = 0.95) -> Tuple[bool, Optional[Dict]]:
    """
    Layer 3: Check if paper already processed by embedding similarity.
    Returns: (is_duplicate, similar_paper_metadata)
    """
    try:
        if not pinecone_index:
            return False, None
        
        results = pinecone_index.query(
            vector=embedding,
            namespace=namespace,
            top_k=1,
            include_metadata=True
        )
        
        if results.matches and len(results.matches) > 0:
            top_match = results.matches[0]
            if top_match.score >= similarity_threshold:
                return True, {
                    'score': top_match.score,
                    'metadata': top_match.metadata
                }
        
        return False, None
    except Exception as e:
        logger.warning(f"Layer 3 similarity check failed: {e}")
        return False, None

def check_all_layers(
    drive_file_id: str,
    paper_title: str,
    authors: str,
    embedding: Optional[List[float]] = None,
    namespace: str = "default",
    pinecone_index = None,
    enable_layer1: bool = True,
    enable_layer2: bool = True,
    enable_layer3: bool = False,
    similarity_threshold: float = 0.95,
    product_id: int = None
) -> Dict:
    """
    Check all enabled deduplication layers with optional product-scoped checking.
    
    Args:
        drive_file_id: Google Drive file ID
        paper_title: Paper title
        authors: Paper authors
        embedding: Optional embedding vector for Layer 3
        namespace: Pinecone namespace
        pinecone_index: Pinecone index instance
        enable_layer1: Enable Drive File ID check
        enable_layer2: Enable content hash check
        enable_layer3: Enable embedding similarity check
        similarity_threshold: Threshold for Layer 3 similarity (default 0.95)
        product_id: Optional product ID for product-scoped deduplication
        
    Returns:
        {
            'is_duplicate': bool,
            'duplicate_layer': str (None, 'layer1', 'layer2', or 'layer3'),
            'existing_paper': Dict or None,
            'content_hash': str
        }
    """
    content_hash = generate_content_hash(paper_title, authors)
    
    if enable_layer1:
        is_dup, existing = check_duplicate_layer1(drive_file_id, product_id)
        if is_dup:
            return {
                'is_duplicate': True,
                'duplicate_layer': 'layer1_file_id',
                'existing_paper': existing,
                'content_hash': content_hash
            }
    
    if enable_layer2:
        is_dup, existing = check_duplicate_layer2(paper_title, authors, product_id)
        if is_dup:
            return {
                'is_duplicate': True,
                'duplicate_layer': 'layer2_content_hash',
                'existing_paper': existing,
                'content_hash': content_hash
            }
    
    if enable_layer3 and embedding and pinecone_index:
        is_dup, similar = check_duplicate_layer3(embedding, namespace, pinecone_index, similarity_threshold)
        if is_dup:
            return {
                'is_duplicate': True,
                'duplicate_layer': 'layer3_embedding_similarity',
                'existing_paper': similar,
                'content_hash': content_hash
            }
    
    return {
        'is_duplicate': False,
        'duplicate_layer': None,
        'existing_paper': None,
        'content_hash': content_hash
    }

def record_or_update_paper(
    drive_file_id: str,
    content_hash: str,
    paper_title: str,
    authors: str,
    metadata: Dict,
    pinecone_namespace: str,
    source_id: int,
    row_number: int,
    is_duplicate: bool,
    existing_paper: Optional[Dict] = None,
    metadata_fingerprint: str = None,
    product_id: int = None
) -> int:
    """
    Record new paper or update existing one with optional metadata fingerprint and product ID.
    
    Args:
        drive_file_id: Google Drive file ID
        content_hash: SHA256 hash of title + authors
        paper_title: Paper title
        authors: Paper authors
        metadata: Paper metadata
        pinecone_namespace: Pinecone namespace
        source_id: Data source ID
        row_number: Row number in sheet
        is_duplicate: Whether this is a duplicate
        existing_paper: Existing paper data if duplicate
        metadata_fingerprint: Optional metadata fingerprint
        product_id: Optional product ID for product-scoped deduplication
        
    Returns:
        Paper ID
    """
    if is_duplicate and existing_paper:
        paper_id = existing_paper['id']
        update_processed_paper(paper_id, source_id, row_number)
        return paper_id
    else:
        return record_processed_paper(
            drive_file_id,
            content_hash,
            paper_title,
            authors,
            metadata,
            pinecone_namespace,
            source_id,
            row_number,
            metadata_fingerprint,
            product_id
        )

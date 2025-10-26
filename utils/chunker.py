"""
Text chunking utilities for PDF processing pipeline.

This module provides multiple chunking strategies:
- Token-based: Fixed token count chunks with overlap
- Sentence-based: Semantic sentence boundary splitting
- Semantic: AI-powered semantic similarity clustering

All strategies use LlamaIndex node parsers for consistency.

Usage:
    from utils.chunker import chunk_text
    
    config = {'chunking_strategy': 'Token-based', 'chunk_size': 1024}
    nodes = chunk_text(parsed_text, config, metadata={'source': 'paper.pdf'})
"""

from llama_index.core.node_parser import (
    SentenceSplitter,
    SemanticSplitterNodeParser,
    TokenTextSplitter
)
from llama_index.core import Document
from typing import List, Dict, Optional
from llama_index.core.schema import TextNode, BaseNode

from utils.embedding_factory import create_embedding_model


def chunk_text(text: str, config: Dict, metadata: Optional[Dict] = None) -> List[BaseNode]:
    """
    Chunk text using specified strategy.
    
    Args:
        text: Text content to chunk
        config: Configuration dictionary with chunking settings
        metadata: Metadata to attach to chunks
        
    Returns:
        List of BaseNode objects
    """
    strategy = config.get('chunking_strategy', 'Token-based')
    
    if metadata is None:
        metadata = {}
    
    doc = Document(text=text, metadata=metadata)
    
    if strategy == "Token-based":
        splitter = TokenTextSplitter(
            chunk_size=config.get('chunk_size', 1024),
            chunk_overlap=config.get('chunk_overlap', 200),
            separator=" "
        )
    
    elif strategy == "Sentence-based":
        splitter = SentenceSplitter(
            chunk_size=config.get('chunk_size', 1024),
            chunk_overlap=config.get('chunk_overlap', 200)
        )
    
    elif strategy == "Semantic":
        # Use centralized embedding factory
        embed_model = create_embedding_model(config)
        splitter = SemanticSplitterNodeParser(
            buffer_size=config.get('semantic_buffer_size', 1),
            embed_model=embed_model,
            breakpoint_percentile_threshold=95
        )
    
    else:
        splitter = TokenTextSplitter(
            chunk_size=1024,
            chunk_overlap=200
        )
    
    nodes = splitter.get_nodes_from_documents([doc])
    
    return nodes

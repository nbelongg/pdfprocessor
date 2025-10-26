"""
Centralized embedding model factory.

This module provides a single source of truth for creating LlamaIndex
embedding models, eliminating code duplication between chunker.py and embedder.py.

Usage:
    from utils.embedding_factory import create_embedding_model
    
    config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': '...'}
    embed_model = create_embedding_model(config)
    embedding = embed_model.get_text_embedding("some text")
"""

import logging
from typing import Dict, Optional
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.embeddings import BaseEmbedding

logger = logging.getLogger(__name__)


def create_embedding_model(config: Dict) -> BaseEmbedding:
    """
    Create embedding model based on configuration.
    
    This function handles:
    - OpenAI embedding models (text-embedding-3-small, text-embedding-3-large, ada-002)
    - HuggingFace embedding models (if installed)
    - Custom embedding dimensions
    - Legacy format parsing ("OpenAI (model-name)")
    
    Args:
        config: Configuration dict with:
            - embedding_model: Model name or format (str)
            - embedding_dimension: Optional custom dimension (int)
            - openai_api_key: API key for OpenAI models (str)
            
    Returns:
        BaseEmbedding instance ready to use
        
    Raises:
        ValueError: If configuration is invalid or API key is missing
        ImportError: If required packages are not installed
        
    Examples:
        >>> config = {
        ...     'embedding_model': 'text-embedding-3-small',
        ...     'openai_api_key': 'sk-...'
        ... }
        >>> model = create_embedding_model(config)
        >>> embedding = model.get_text_embedding("Hello world")
    """
    embedding_model = config.get('embedding_model', '')
    embedding_dimension = config.get('embedding_dimension')
    
    # OpenAI models (most common case)
    if embedding_model.startswith('text-embedding-') or 'OpenAI' in embedding_model:
        model_name = _parse_openai_model_name(embedding_model)
        return _create_openai_embedding(
            model_name=model_name,
            api_key=config.get('openai_api_key'),
            dimension=embedding_dimension
        )
    
    # HuggingFace models
    elif 'HuggingFace' in embedding_model:
        return _create_huggingface_embedding(embedding_model)
    
    # Default fallback: OpenAI text-embedding-3-small
    else:
        logger.warning(
            f"Unknown embedding model '{embedding_model}', "
            f"falling back to text-embedding-3-small"
        )
        return _create_openai_embedding(
            model_name='text-embedding-3-small',
            api_key=config.get('openai_api_key'),
            dimension=embedding_dimension
        )


def _parse_openai_model_name(embedding_model: str) -> str:
    """
    Extract OpenAI model name from various formats.
    
    Handles:
    - Direct format: "text-embedding-3-small"
    - Legacy format: "OpenAI (text-embedding-3-small)"
    
    Args:
        embedding_model: Model string in various formats
        
    Returns:
        Clean model name
    """
    if 'OpenAI' in embedding_model and '(' in embedding_model and ')' in embedding_model:
        # Legacy format: "OpenAI (text-embedding-3-small)" -> "text-embedding-3-small"
        model_name = embedding_model.split('(')[1].split(')')[0].strip()
        return model_name
    
    # Direct format
    return embedding_model


def _create_openai_embedding(
    model_name: str,
    api_key: Optional[str],
    dimension: Optional[int]
) -> OpenAIEmbedding:
    """
    Create OpenAI embedding model.
    
    Args:
        model_name: OpenAI model name (e.g., "text-embedding-3-small")
        api_key: OpenAI API key
        dimension: Optional custom dimension (for models that support it)
        
    Returns:
        OpenAIEmbedding instance
        
    Raises:
        ValueError: If API key is missing
    """
    if not api_key:
        raise ValueError(
            "OpenAI API key required for OpenAI embedding models. "
            "Set 'openai_api_key' in config or OPENAI_API_KEY environment variable."
        )
    
    embed_kwargs = {
        'api_key': api_key,
        'model': model_name
    }
    
    # Add custom dimension if specified
    if dimension is not None:
        embed_kwargs['dimensions'] = dimension
        logger.info(f"Using custom embedding dimension: {dimension}")
    
    return OpenAIEmbedding(**embed_kwargs)


def _create_huggingface_embedding(embedding_model: str) -> BaseEmbedding:
    """
    Create HuggingFace embedding model.
    
    Args:
        embedding_model: HuggingFace model string (format: "HuggingFace (model-name)")
        
    Returns:
        HuggingFaceEmbedding instance
        
    Raises:
        ImportError: If llama-index-embeddings-huggingface is not installed
    """
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    except ImportError:
        raise ImportError(
            "HuggingFace embeddings require additional package. Install with:\n"
            "pip install llama-index-embeddings-huggingface"
        )
    
    # Extract model name from format "HuggingFace (model-name)"
    # FIXED: Extract text between parentheses, not before them
    if '(' in embedding_model and ')' in embedding_model:
        model_name = embedding_model.split('(')[1].split(')')[0].strip()
    else:
        model_name = embedding_model
    
    logger.info(f"Creating HuggingFace embedding model: {model_name}")
    return HuggingFaceEmbedding(model_name=model_name)


def get_embedding_dimension(config: Dict) -> int:
    """
    Get the dimension of embeddings based on the model and config.
    
    Args:
        config: Configuration dict with embedding_model and optional embedding_dimension
        
    Returns:
        Embedding dimension (int)
    """
    # Check if custom dimension is set first
    if config.get('embedding_dimension') is not None:
        return config.get('embedding_dimension')
    
    # Otherwise use default dimensions based on model
    embedding_model = config.get('embedding_model', '')
    
    dimension_map = {
        'text-embedding-3-small': 1536,
        'text-embedding-3-large': 3072,
        'text-embedding-ada-002': 1536,
        'BAAI/bge-small-en-v1.5': 384,
        'BAAI/bge-base-en-v1.5': 768,
        'sentence-transformers/all-MiniLM-L6-v2': 384
    }
    
    for model_key, dim in dimension_map.items():
        if model_key in embedding_model:
            return dim
    
    # Default fallback
    return 1536

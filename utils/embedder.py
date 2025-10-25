from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.schema import TextNode
from typing import List, Dict
import numpy as np
import os

os.environ['HF_HOME'] = '/tmp/.huggingface'
os.environ['TRANSFORMERS_CACHE'] = '/tmp/.huggingface/transformers'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = '/tmp/.huggingface/sentence-transformers'

def create_embeddings(nodes: List[TextNode], config: Dict) -> List[List[float]]:
    """
    Create embeddings for text nodes.
    
    Args:
        nodes: List of TextNode objects
        config: Configuration dictionary with embedding settings
        
    Returns:
        List of embedding vectors
    """
    embedding_model = config.get('embedding_model', '')
    embedding_dimension = config.get('embedding_dimension')
    
    # Check if it's an OpenAI model (starts with 'text-embedding-' or contains 'OpenAI')
    if embedding_model.startswith('text-embedding-') or 'OpenAI' in embedding_model:
        # For legacy format like "OpenAI (text-embedding-3-small)", extract model name from inside parentheses
        if 'OpenAI' in embedding_model and '(' in embedding_model and ')' in embedding_model:
            # Extract text between parentheses: "OpenAI (text-embedding-3-small)" -> "text-embedding-3-small"
            model_name = embedding_model.split('(')[1].split(')')[0].strip()
        else:
            # Direct model name like "text-embedding-3-small"
            model_name = embedding_model
        
        embed_kwargs = {
            'api_key': config.get('openai_api_key'),
            'model': model_name
        }
        if embedding_dimension is not None:
            embed_kwargs['dimensions'] = embedding_dimension
        embed_model = OpenAIEmbedding(**embed_kwargs)
    elif 'HuggingFace' in embedding_model:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        model_name = embedding_model.split('(')[0].strip()
        embed_model = HuggingFaceEmbedding(
            model_name=model_name
        )
    else:
        # Default fallback to text-embedding-3-small
        embed_kwargs = {
            'api_key': config.get('openai_api_key'),
            'model': 'text-embedding-3-small'
        }
        if embedding_dimension is not None:
            embed_kwargs['dimensions'] = embedding_dimension
        embed_model = OpenAIEmbedding(**embed_kwargs)
    
    embeddings = []
    for node in nodes:
        embedding = embed_model.get_text_embedding(node.get_content())
        embeddings.append(embedding)
    
    return embeddings

def get_embedding_dimension(config: Dict) -> int:
    """Get the dimension of embeddings based on the model and config."""
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
    
    return 1536

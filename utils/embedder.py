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
    
    if 'OpenAI' in embedding_model:
        model_name = embedding_model.split('(')[0].strip()
        embed_model = OpenAIEmbedding(
            api_key=config.get('openai_api_key'),
            model=model_name
        )
    elif 'HuggingFace' in embedding_model:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
        model_name = embedding_model.split('(')[0].strip()
        embed_model = HuggingFaceEmbedding(
            model_name=model_name
        )
    else:
        embed_model = OpenAIEmbedding(
            api_key=config.get('openai_api_key'),
            model='text-embedding-3-small'
        )
    
    embeddings = []
    for node in nodes:
        embedding = embed_model.get_text_embedding(node.get_content())
        embeddings.append(embedding)
    
    return embeddings

def get_embedding_dimension(config: Dict) -> int:
    """Get the dimension of embeddings based on the model."""
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
    
    return config.get('embedding_dimension', 1536)

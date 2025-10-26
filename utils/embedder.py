from llama_index.core.schema import TextNode
from typing import List, Dict
import os

from utils.embedding_factory import create_embedding_model, get_embedding_dimension

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
    # Use centralized embedding factory
    embed_model = create_embedding_model(config)
    
    embeddings = []
    for node in nodes:
        embedding = embed_model.get_text_embedding(node.get_content())
        embeddings.append(embedding)
    
    return embeddings

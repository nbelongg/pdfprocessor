from llama_index.core.node_parser import (
    SentenceSplitter,
    SemanticSplitterNodeParser,
    TokenTextSplitter
)
from llama_index.core import Document
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from typing import List, Dict
from llama_index.core.schema import TextNode

def chunk_text(text: str, config: Dict, metadata: Dict = None) -> List[TextNode]:
    """
    Chunk text using specified strategy.
    
    Args:
        text: Text content to chunk
        config: Configuration dictionary with chunking settings
        metadata: Metadata to attach to chunks
        
    Returns:
        List of TextNode objects
    """
    strategy = config.get('chunking_strategy', 'Token-based')
    
    doc = Document(text=text, metadata=metadata or {})
    
    if strategy == "Token-based":
        splitter = TokenTextSplitter(
            chunk_size=config.get('chunk_size', 512),
            chunk_overlap=config.get('chunk_overlap', 50),
            separator=" "
        )
    
    elif strategy == "Sentence-based":
        splitter = SentenceSplitter(
            chunk_size=config.get('chunk_size', 1024),
            chunk_overlap=config.get('chunk_overlap', 200)
        )
    
    elif strategy == "Semantic":
        embed_model = get_embed_model(config)
        splitter = SemanticSplitterNodeParser(
            buffer_size=config.get('semantic_buffer_size', 1),
            embed_model=embed_model,
            breakpoint_percentile_threshold=95
        )
    
    else:
        splitter = TokenTextSplitter(
            chunk_size=512,
            chunk_overlap=50
        )
    
    nodes = splitter.get_nodes_from_documents([doc])
    
    return nodes

def get_embed_model(config: Dict):
    """Get the embedding model based on configuration."""
    embedding_model = config.get('embedding_model', '')
    
    if 'OpenAI' in embedding_model:
        model_name = embedding_model.split('(')[0].strip()
        return OpenAIEmbedding(
            api_key=config.get('openai_api_key'),
            model=model_name
        )
    elif 'HuggingFace' in embedding_model:
        model_name = embedding_model.split('(')[0].strip()
        return HuggingFaceEmbedding(
            model_name=model_name
        )
    else:
        return OpenAIEmbedding(
            api_key=config.get('openai_api_key'),
            model='text-embedding-3-small'
        )

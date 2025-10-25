from pinecone import Pinecone, ServerlessSpec
from typing import List, Dict
import time

def initialize_pinecone(config: Dict):
    """Initialize Pinecone client and ensure index exists."""
    api_key = config.get('pinecone_api_key')
    
    pc = Pinecone(api_key=api_key)
    
    index_name = config.get('index_name', 'research-papers')
    dimension = config.get('embedding_dimension', 1536)
    
    existing_indexes = pc.list_indexes()
    
    index_exists = False
    for index_info in existing_indexes:
        if hasattr(index_info, 'name') and index_info.name == index_name:
            index_exists = True
            break
        elif isinstance(index_info, dict) and index_info.get('name') == index_name:
            index_exists = True
            break
    
    if not index_exists:
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric='cosine',
            spec=ServerlessSpec(
                cloud='aws',
                region='us-east-1'
            )
        )
        
        time.sleep(1)
    
    index = pc.Index(index_name)
    
    return index

def upload_to_pinecone(
    index,
    embeddings: List[List[float]],
    nodes: List,
    metadata_list: List[Dict],
    namespace: str = "default"
) -> int:
    """
    Upload embeddings to Pinecone.
    
    Args:
        index: Pinecone index object
        embeddings: List of embedding vectors
        nodes: List of TextNode objects
        metadata_list: List of metadata dictionaries
        namespace: Pinecone namespace
        
    Returns:
        Number of vectors uploaded
    """
    vectors = []
    
    for i, (embedding, node, metadata) in enumerate(zip(embeddings, nodes, metadata_list)):
        vector_id = f"{metadata.get('file_id', 'unknown')}_{i}"
        
        vector_metadata = {
            'text': node.get_content(),
            **metadata
        }
        
        for key, value in vector_metadata.items():
            if isinstance(value, (list, dict)):
                vector_metadata[key] = str(value)
            elif value is None:
                vector_metadata[key] = ""
        
        vectors.append({
            'id': vector_id,
            'values': embedding,
            'metadata': vector_metadata
        })
    
    batch_size = 100
    total_uploaded = 0
    
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        index.upsert(vectors=batch, namespace=namespace)
        total_uploaded += len(batch)
    
    return total_uploaded

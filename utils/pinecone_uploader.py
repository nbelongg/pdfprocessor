try:
    from pinecone import Pinecone, ServerlessSpec
except ImportError:
    from pinecone.grpc import PineconeGRPC as Pinecone
    from pinecone import ServerlessSpec
from typing import List, Dict
import time
import logging
from utils.exceptions import TransientError

logger = logging.getLogger(__name__)


def initialize_pinecone(config: Dict):
    """
    Initialize Pinecone client and ensure index exists.
    
    Args:
        config: Configuration dictionary with pinecone_api_key, index_name, embedding_dimension
        
    Returns:
        Pinecone index object
        
    Raises:
        ValueError: If configuration is invalid or API key is missing
        TransientError: If network/API issues occur (retryable)
    """
    try:
        api_key = config.get('pinecone_api_key')
        if not api_key:
            raise ValueError("pinecone_api_key missing from config")
        
        index_name = config.get('index_name', 'research-papers')
        dimension = config.get('embedding_dimension', 1536)
        
        # Initialize Pinecone client
        try:
            pc = Pinecone(api_key=api_key)
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['unauthorized', 'invalid', 'api key']):
                raise ValueError(f"Invalid Pinecone API key: {e}") from e
            else:
                raise TransientError(f"Failed to initialize Pinecone client: {e}") from e
        
        # List existing indexes
        try:
            existing_indexes = pc.list_indexes()
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['timeout', 'connection', 'network', 'rate limit']):
                raise TransientError(f"Network error listing Pinecone indexes: {e}") from e
            else:
                raise ValueError(f"Failed to list Pinecone indexes: {e}") from e
        
        # Check if index exists
        index_exists = False
        for index_info in existing_indexes:
            if hasattr(index_info, 'name') and index_info.name == index_name:
                index_exists = True
                break
            elif isinstance(index_info, dict) and index_info.get('name') == index_name:
                index_exists = True
                break
        
        # Create index if it doesn't exist
        if not index_exists:
            try:
                logger.info(f"Creating Pinecone index '{index_name}' with dimension {dimension}")
                pc.create_index(
                    name=index_name,
                    dimension=dimension,
                    metric='cosine',
                    spec=ServerlessSpec(
                        cloud='aws',
                        region='us-east-1'
                    )
                )
                time.sleep(1)  # Wait for index creation
            except Exception as e:
                error_msg = str(e).lower()
                if any(keyword in error_msg for keyword in ['timeout', 'connection', 'network', 'rate limit']):
                    raise TransientError(f"Network error creating Pinecone index: {e}") from e
                elif 'already exists' in error_msg:
                    logger.warning(f"Index {index_name} already exists (created by another process)")
                else:
                    raise ValueError(f"Failed to create Pinecone index: {e}") from e
        
        # Get index reference
        try:
            index = pc.Index(index_name)
            return index
        except Exception as e:
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['timeout', 'connection', 'network']):
                raise TransientError(f"Network error accessing Pinecone index: {e}") from e
            else:
                raise ValueError(f"Failed to get Pinecone index '{index_name}': {e}") from e
                
    except (TransientError, ValueError):
        raise
    except Exception as e:
        logger.error(f"Unexpected error initializing Pinecone: {e}")
        raise ValueError(f"Unexpected error initializing Pinecone: {e}") from e

def upload_to_pinecone(
    index,
    embeddings: List[List[float]],
    nodes: List,
    metadata_list: List[Dict],
    namespace: str = "default"
) -> int:
    """
    Upload embeddings to Pinecone with error handling.
    
    Args:
        index: Pinecone index object
        embeddings: List of embedding vectors
        nodes: List of TextNode objects
        metadata_list: List of metadata dictionaries
        namespace: Pinecone namespace
        
    Returns:
        Number of vectors uploaded
        
    Raises:
        ValueError: If inputs are invalid
        TransientError: If network/API issues occur (retryable)
    """
    if not embeddings or not nodes or not metadata_list:
        raise ValueError("Empty embeddings, nodes, or metadata_list provided")
    
    if not (len(embeddings) == len(nodes) == len(metadata_list)):
        raise ValueError(
            f"Length mismatch: embeddings={len(embeddings)}, "
            f"nodes={len(nodes)}, metadata={len(metadata_list)}"
        )
    
    vectors = []
    
    # Prepare vectors
    try:
        for i, (embedding, node, metadata) in enumerate(zip(embeddings, nodes, metadata_list)):
            vector_id = f"{metadata.get('file_id', 'unknown')}_{i}"
            
            vector_metadata = {
                'text': node.get_content(),
                **metadata
            }
            
            # Sanitize metadata for Pinecone
            for key, value in vector_metadata.items():
                if isinstance(value, list):
                    # Convert lists to comma-separated strings for readability
                    # e.g., ['tag1', 'tag2'] → "tag1, tag2" (not "['tag1', 'tag2']")
                    vector_metadata[key] = ', '.join(str(item) for item in value) if value else ""
                elif isinstance(value, dict):
                    # Convert dicts to JSON-like string
                    vector_metadata[key] = str(value)
                elif value is None:
                    vector_metadata[key] = ""
            
            # Log tags for first chunk of each file (for debugging)
            if i == 0 and 'tags' in vector_metadata:
                logger.info(f"🏷️  Pinecone upload - tags for chunk 0: '{vector_metadata['tags']}'")
            
            vectors.append({
                'id': vector_id,
                'values': embedding,
                'metadata': vector_metadata
            })
    except Exception as e:
        logger.error(f"Error preparing vectors for upload: {e}")
        raise ValueError(f"Failed to prepare vectors: {e}") from e
    
    # Upload in batches with error handling
    batch_size = 100
    total_uploaded = 0
    
    for i in range(0, len(vectors), batch_size):
        batch = vectors[i:i + batch_size]
        batch_num = i // batch_size + 1
        
        try:
            index.upsert(vectors=batch, namespace=namespace)
            total_uploaded += len(batch)
            logger.debug(f"Uploaded batch {batch_num} ({len(batch)} vectors) to namespace '{namespace}'")
            
        except Exception as e:
            error_msg = str(e).lower()
            logger.error(f"Failed to upload batch {batch_num} to Pinecone: {e}")
            
            # Classify error as transient or permanent
            if any(keyword in error_msg for keyword in [
                'rate limit', 'timeout', 'connection', 'network',
                'unavailable', '503', '429', '502', '504'
            ]):
                raise TransientError(
                    f"Network/rate limit error uploading batch {batch_num}/{len(vectors)//batch_size + 1}: {e}"
                ) from e
            else:
                raise ValueError(
                    f"Pinecone upload failed on batch {batch_num}: {e}"
                ) from e
    
    logger.info(f"Successfully uploaded {total_uploaded} vectors to Pinecone namespace '{namespace}'")
    return total_uploaded

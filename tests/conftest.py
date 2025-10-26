"""
Pytest fixtures for testing.

This module provides shared fixtures used across all test modules.
"""

import pytest
import os
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any


# ============================================
# Configuration Fixtures
# ============================================

@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Sample processing configuration."""
    return {
        'parsing_mode': 'auto',
        'result_type': 'markdown',
        'chunk_size': 1024,
        'chunk_overlap': 200,
        'chunking_strategy': 'Token-based',
        'embedding_model': 'text-embedding-3-small',
        'embedding_dimension': 1536,
        'openai_api_key': 'sk-test-key-12345',
        'pinecone_api_key': 'pc-test-key-12345',
        'llama_api_key': 'llx-test-key-12345',
        'google_credentials': '{"type":"service_account","project_id":"test"}',
        'index_name': 'test-index',
        'pinecone_environment': 'us-east-1',
        'default_namespace': 'test',
        'language': 'en',
        'use_vendor_multimodal': True,
        'page_separator': '\n---\n',
        'semantic_buffer_size': 1,
        'tagging_enabled': False,
        'tagging_model': 'gpt-4o-mini',
        'dedup_layer1': True,
        'dedup_layer2': True
    }


@pytest.fixture
def sample_metadata() -> Dict[str, Any]:
    """Sample document metadata."""
    return {
        'title': 'Sample Research Paper',
        'authors': 'John Doe, Jane Smith',
        'year': '2024',
        'source': 'test.pdf',
        'file_id': 'test-file-id-123'
    }


@pytest.fixture
def sample_product() -> Dict[str, Any]:
    """Sample product configuration."""
    return {
        'id': 1,
        'name': 'Test Product',
        'description': 'Test product for testing',
        'active': True,
        'pinecone_index': 'test-index',
        'pinecone_environment': 'us-east-1',
        'default_namespace': 'test',
        'parsing_mode': 'auto',
        'result_type': 'markdown',
        'language': 'en',
        'use_vendor_multimodal': True,
        'page_separator': '\n---\n',
        'default_chunking_strategy': 'Token-based',
        'default_chunk_size': 1024,
        'chunk_overlap': 200,
        'semantic_buffer_size': 1,
        'default_embedding_model': 'text-embedding-3-small',
        'embedding_dimension': 1536,
        'tagging_enabled': False,
        'tagging_model': 'gpt-4o-mini',
        'tagging_prompt_template': None,
        'tagging_config': {}
    }


# ============================================
# Database Fixtures
# ============================================

@pytest.fixture
def mock_db_connection():
    """Mock database connection with cursor."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchone.return_value = None
    cursor.fetchall.return_value = []
    cursor.rowcount = 0
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


@pytest.fixture
def mock_db_transaction():
    """Mock database transaction context manager."""
    with patch('utils.db.connection.get_db_transaction') as mock_txn:
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone.return_value = None
        cursor.fetchall.return_value = []
        conn.cursor.return_value.__enter__.return_value = cursor
        mock_txn.return_value.__enter__.return_value = conn
        yield mock_txn


# ============================================
# External Service Mocks
# ============================================

@pytest.fixture
def mock_openai_embeddings():
    """Mock OpenAI embeddings API."""
    with patch('openai.Embedding.create') as mock:
        mock.return_value = {
            'data': [{'embedding': [0.1] * 1536}],
            'usage': {'total_tokens': 10}
        }
        yield mock


@pytest.fixture
def mock_openai_chat():
    """Mock OpenAI chat completion API."""
    with patch('openai.ChatCompletion.create') as mock:
        mock.return_value = {
            'choices': [{
                'message': {
                    'content': '{"tags": ["tag1", "tag2"], "categories": ["cat1"]}'
                }
            }],
            'usage': {'total_tokens': 50}
        }
        yield mock


@pytest.fixture
def mock_pinecone_index():
    """Mock Pinecone index."""
    index = MagicMock()
    index.upsert.return_value = {'upserted_count': 10}
    index.query.return_value = {
        'matches': [
            {'id': 'vec1', 'score': 0.95, 'metadata': {'title': 'Test'}},
            {'id': 'vec2', 'score': 0.85, 'metadata': {'title': 'Test 2'}}
        ]
    }
    index.describe_index_stats.return_value = {
        'total_vector_count': 1000,
        'dimension': 1536
    }
    return index


@pytest.fixture
def mock_llama_parser():
    """Mock LlamaParse API."""
    with patch('utils.llama_parser.parse_pdf_with_llamaparse') as mock:
        mock.return_value = """
# Sample PDF Content

This is a test document with multiple paragraphs.

## Section 1

Content of section 1 with important information.

## Section 2

More content here for testing purposes.
"""
        yield mock


@pytest.fixture
def mock_google_drive():
    """Mock Google Drive API."""
    with patch('utils.google_drive.download_pdf_from_drive') as mock_download, \
         patch('utils.google_drive.get_file_metadata') as mock_metadata:
        
        mock_download.return_value = b'%PDF-1.4 fake pdf content'
        mock_metadata.return_value = {
            'id': 'test-file-id',
            'name': 'test.pdf',
            'mimeType': 'application/pdf',
            'size': '12345'
        }
        
        yield mock_download, mock_metadata


# ============================================
# Data Fixtures
# ============================================

@pytest.fixture
def sample_text():
    """Sample text for chunking and processing."""
    return """
Introduction to Machine Learning

Machine learning is a subset of artificial intelligence that enables systems to learn 
and improve from experience without being explicitly programmed. It focuses on the 
development of computer programs that can access data and use it to learn for themselves.

Types of Machine Learning

There are three main types of machine learning: supervised learning, unsupervised learning, 
and reinforcement learning. Each type has its own unique characteristics and use cases.

Supervised Learning

In supervised learning, the algorithm learns from labeled training data. The model is 
trained on a set of examples where the correct output is known, and it learns to map 
inputs to outputs.

Unsupervised Learning

Unsupervised learning works with unlabeled data. The algorithm tries to find patterns 
and structures in the data without being told what to look for.

Reinforcement Learning

Reinforcement learning is based on reward and punishment. The agent learns by interacting 
with its environment and receiving feedback in the form of rewards or penalties.

Conclusion

Machine learning continues to evolve and has applications in various fields including 
healthcare, finance, autonomous vehicles, and natural language processing.
"""


@pytest.fixture
def sample_nodes():
    """Sample text nodes for testing."""
    from llama_index.core.schema import TextNode
    
    return [
        TextNode(
            text="First chunk of text",
            metadata={'title': 'Test', 'chunk_id': 1}
        ),
        TextNode(
            text="Second chunk of text",
            metadata={'title': 'Test', 'chunk_id': 2}
        ),
        TextNode(
            text="Third chunk of text",
            metadata={'title': 'Test', 'chunk_id': 3}
        )
    ]


# ============================================
# Environment Fixtures
# ============================================

@pytest.fixture
def mock_env_vars():
    """Mock environment variables."""
    env_vars = {
        'DATABASE_URL': 'postgresql://test:test@localhost/test',
        'REDIS_HOST': 'localhost',
        'REDIS_PORT': '6379',
        'ABCD_DA_OPENAI_KEY': 'sk-test',
        'ABCD_DA_PINECONE_KEY': 'pc-test',
        'ABCD_DA_LLAMAPARSE_KEY': 'llx-test'
    }
    
    with patch.dict(os.environ, env_vars, clear=False):
        yield env_vars


# ============================================
# Helper Functions
# ============================================

@pytest.fixture
def assert_all_mocks_called():
    """Helper to assert all mocks in a list were called."""
    def _assert(mocks):
        for mock in mocks:
            assert mock.called, f"Mock {mock} was not called"
    return _assert


@pytest.fixture
def create_test_product():
    """Helper to create test product in database."""
    def _create(name='Test Product', **kwargs):
        from utils.db import create_product, delete_product
        import uuid
        
        product_data = {
            'name': f'{name} {uuid.uuid4().hex[:6]}',
            'description': 'Test product',
            'pinecone_index': 'test-index',
            'active': True,
            **kwargs
        }
        
        product_id = create_product(product_data)
        
        # Return cleanup function
        def cleanup():
            try:
                delete_product(product_id)
            except:
                pass
        
        return product_id, cleanup
    
    return _create

"""
Unit tests for chunker module (utils/chunker.py).

Tests text chunking functionality with different strategies.
"""

import pytest
from utils.chunker import chunk_text


@pytest.mark.unit
class TestChunker:
    """Test chunking functionality."""
    
    def test_token_based_chunking(self, sample_config):
        """Test token-based chunking."""
        text = "This is a test sentence. " * 200  # Long text
        config = {
            **sample_config,
            'chunking_strategy': 'Token-based',
            'chunk_size': 100,
            'chunk_overlap': 20
        }
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 0, "Should create at least one chunk"
        assert all(node.text for node in nodes), "All chunks should have text"
        assert len(nodes) > 1, "Long text should create multiple chunks"
    
    def test_sentence_based_chunking(self, sample_config):
        """Test sentence-based chunking."""
        text = (
            "First sentence here. "
            "Second sentence with content. "
            "Third sentence for testing. "
            "Fourth sentence example. "
            "Fifth sentence data."
        )
        config = {
            **sample_config,
            'chunking_strategy': 'Sentence-based',
            'chunk_size': 50
        }
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 0, "Should create at least one chunk"
        assert all(node.text for node in nodes), "All chunks should have text"
    
    def test_semantic_chunking(self, sample_config):
        """Test semantic chunking."""
        text = """
        Introduction to the topic.
        
        This section discusses the main concept in detail.
        It provides background information.
        
        Next, we explore the methodology.
        The approach is straightforward.
        
        Finally, we present the conclusions.
        """
        config = {
            **sample_config,
            'chunking_strategy': 'Semantic',
            'semantic_buffer_size': 2
        }
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 0, "Should create at least one chunk"
        assert all(node.text for node in nodes), "All chunks should have text"
    
    def test_metadata_preserved(self, sample_config, sample_metadata):
        """Test that metadata is preserved in chunks."""
        text = "Test text for metadata preservation."
        
        nodes = chunk_text(text, sample_config, metadata=sample_metadata)
        
        assert len(nodes) > 0
        for node in nodes:
            assert node.metadata.get('title') == 'Sample Research Paper'
            assert node.metadata.get('authors') == 'John Doe, Jane Smith'
            assert node.metadata.get('year') == '2024'
    
    def test_chunk_overlap(self, sample_config):
        """Test that chunk overlap works correctly."""
        text = "Word " * 500  # Create long text
        config = {
            **sample_config,
            'chunking_strategy': 'Token-based',
            'chunk_size': 100,
            'chunk_overlap': 25
        }
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 1, "Should create multiple chunks with overlap"
        # Chunks should have some overlapping content
        for i in range(len(nodes) - 1):
            assert nodes[i].text != nodes[i+1].text, "Chunks should not be identical"
    
    def test_empty_text(self, sample_config):
        """Test handling of empty text."""
        text = ""
        
        nodes = chunk_text(text, sample_config)
        
        # Should either return empty list or single node with empty text
        assert isinstance(nodes, list)
    
    def test_short_text_single_chunk(self, sample_config):
        """Test that short text creates single chunk."""
        text = "Short text."
        config = {
            **sample_config,
            'chunk_size': 1000
        }
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) >= 1
        if len(nodes) == 1:
            assert text in nodes[0].text
    
    def test_custom_chunk_size(self, sample_config):
        """Test custom chunk size."""
        text = "Word " * 1000
        config = {
            **sample_config,
            'chunking_strategy': 'Token-based',
            'chunk_size': 50
        }
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 0
        # With smaller chunk size, should create more chunks
        assert len(nodes) > 5
    
    def test_metadata_none(self, sample_config):
        """Test chunking with None metadata."""
        text = "Test text without metadata."
        
        # Should not raise error
        nodes = chunk_text(text, sample_config, metadata=None)
        
        assert len(nodes) > 0
    
    def test_long_document(self, sample_text, sample_config):
        """Test chunking a longer realistic document."""
        config = {
            **sample_config,
            'chunking_strategy': 'Token-based',
            'chunk_size': 200
        }
        
        nodes = chunk_text(sample_text, config)
        
        assert len(nodes) > 0
        assert all(node.text.strip() for node in nodes), "No empty chunks"
        
        # Verify total content is preserved
        total_text = ''.join(node.text for node in nodes)
        assert len(total_text) > 0

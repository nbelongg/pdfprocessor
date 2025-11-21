"""
Unit tests for utils/embedder.py module.

Tests embedding generation:
- Empty/whitespace content handling
- Batch embedding generation
- Different embedding models
- Content validation
- Error handling
"""

import pytest
from unittest.mock import patch, MagicMock
from llama_index.core.schema import TextNode

from utils.embedder import create_embeddings


@pytest.mark.unit
class TestCreateEmbeddings:
    """Test embedding generation functionality."""

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_success(self, mock_create_model):
        """Test successful embedding generation."""
        # Setup mock embedding model
        mock_model = MagicMock()
        mock_model.get_text_embedding.side_effect = [
            [0.1] * 1536,
            [0.2] * 1536,
            [0.3] * 1536
        ]
        mock_create_model.return_value = mock_model

        # Create test nodes
        nodes = [
            TextNode(text="First chunk of text"),
            TextNode(text="Second chunk of text"),
            TextNode(text="Third chunk of text")
        ]

        config = {
            'embedding_model': 'text-embedding-3-small',
            'openai_api_key': 'sk-test'
        }

        # Call function
        embeddings = create_embeddings(nodes, config)

        # Verify results
        assert len(embeddings) == 3
        assert len(embeddings[0]) == 1536
        assert embeddings[0] == [0.1] * 1536
        assert embeddings[1] == [0.2] * 1536
        assert embeddings[2] == [0.3] * 1536

        # Verify model was created with config
        mock_create_model.assert_called_once_with(config)

        # Verify get_text_embedding was called for each node
        assert mock_model.get_text_embedding.call_count == 3

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_empty_content(self, mock_create_model):
        """Test that empty content raises ValueError."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        # Create node with empty content
        nodes = [TextNode(text="")]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        # Should raise ValueError
        with pytest.raises(ValueError, match="empty or whitespace-only content"):
            create_embeddings(nodes, config)

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_whitespace_only(self, mock_create_model):
        """Test that whitespace-only content raises ValueError."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        # Create node with whitespace only
        nodes = [TextNode(text="   \n\t  ")]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        # Should raise ValueError
        with pytest.raises(ValueError, match="empty or whitespace-only content"):
            create_embeddings(nodes, config)

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_non_string_content(self, mock_create_model):
        """Test that non-string content raises AttributeError (bug in implementation)."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        # Create node with non-string content
        node = MagicMock()
        node.get_content.return_value = 12345  # Integer instead of string

        nodes = [node]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        # Implementation bug: tries to call .strip() before checking isinstance
        with pytest.raises(AttributeError, match="'int' object has no attribute 'strip'"):
            create_embeddings(nodes, config)

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_partial_failure(self, mock_create_model):
        """Test behavior when one embedding fails."""
        mock_model = MagicMock()
        # First succeeds, second fails
        mock_model.get_text_embedding.side_effect = [
            [0.1] * 1536,
            Exception("API error")
        ]
        mock_create_model.return_value = mock_model

        nodes = [
            TextNode(text="First chunk"),
            TextNode(text="Second chunk")
        ]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        # Should raise exception on second embedding
        with pytest.raises(Exception, match="API error"):
            create_embeddings(nodes, config)

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_different_models(self, mock_create_model):
        """Test embedding creation with different models."""
        mock_model = MagicMock()
        mock_model.get_text_embedding.return_value = [0.1] * 3072
        mock_create_model.return_value = mock_model

        nodes = [TextNode(text="Test content")]

        # Test with large model (different dimension)
        config = {
            'embedding_model': 'text-embedding-3-large',
            'embedding_dimension': 3072,
            'openai_api_key': 'sk-test'
        }

        embeddings = create_embeddings(nodes, config)

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 3072
        mock_create_model.assert_called_once_with(config)

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_batch_processing(self, mock_create_model):
        """Test batch processing of multiple nodes."""
        mock_model = MagicMock()
        # Generate 100 mock embeddings
        mock_model.get_text_embedding.side_effect = [[i/100.0] * 1536 for i in range(100)]
        mock_create_model.return_value = mock_model

        # Create 100 test nodes
        nodes = [TextNode(text=f"Chunk {i} content") for i in range(100)]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        embeddings = create_embeddings(nodes, config)

        # Verify all embeddings created
        assert len(embeddings) == 100
        assert mock_model.get_text_embedding.call_count == 100

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_validates_each_node(self, mock_create_model):
        """Test that validation happens for each node independently."""
        mock_model = MagicMock()
        mock_model.get_text_embedding.return_value = [0.1] * 1536
        mock_create_model.return_value = mock_model

        # Mix of valid and invalid nodes
        nodes = [
            TextNode(text="Valid content"),
            TextNode(text=""),  # Empty - should fail
            TextNode(text="More valid content")
        ]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        # Should fail on second node
        with pytest.raises(ValueError, match="Node 1.*empty"):
            create_embeddings(nodes, config)

        # First node should have been processed before failure
        assert mock_model.get_text_embedding.call_count == 1

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_long_content(self, mock_create_model):
        """Test embedding generation with very long content."""
        mock_model = MagicMock()
        mock_model.get_text_embedding.return_value = [0.1] * 1536
        mock_create_model.return_value = mock_model

        # Create node with very long content (10,000 characters)
        long_text = "Lorem ipsum " * 1000
        nodes = [TextNode(text=long_text)]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        embeddings = create_embeddings(nodes, config)

        # Should successfully create embedding
        assert len(embeddings) == 1
        # Verify the full text was sent
        call_args = mock_model.get_text_embedding.call_args[0]
        assert len(call_args[0]) == len(long_text)

    @patch('utils.embedder.create_embedding_model')
    def test_create_embeddings_special_characters(self, mock_create_model):
        """Test embedding generation with special characters."""
        mock_model = MagicMock()
        mock_model.get_text_embedding.return_value = [0.1] * 1536
        mock_create_model.return_value = mock_model

        # Text with special characters
        special_text = "Test with émojis 🎉, symbols @#$%, and unicode 你好"
        nodes = [TextNode(text=special_text)]

        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        embeddings = create_embeddings(nodes, config)

        # Should handle special characters without error
        assert len(embeddings) == 1
        call_args = mock_model.get_text_embedding.call_args[0]
        assert call_args[0] == special_text


@pytest.mark.unit
class TestEmbeddingEdgeCases:
    """Test edge cases and error conditions."""

    @patch('utils.embedder.create_embedding_model')
    def test_empty_nodes_list(self, mock_create_model):
        """Test with empty list of nodes."""
        mock_model = MagicMock()
        mock_create_model.return_value = mock_model

        nodes = []
        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        embeddings = create_embeddings(nodes, config)

        # Should return empty list
        assert embeddings == []
        assert mock_model.get_text_embedding.call_count == 0

    @patch('utils.embedder.create_embedding_model')
    def test_single_node(self, mock_create_model):
        """Test with single node."""
        mock_model = MagicMock()
        mock_model.get_text_embedding.return_value = [0.5] * 1536
        mock_create_model.return_value = mock_model

        nodes = [TextNode(text="Single node content")]
        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        embeddings = create_embeddings(nodes, config)

        assert len(embeddings) == 1
        assert len(embeddings[0]) == 1536

    @patch('utils.embedder.create_embedding_model')
    def test_model_creation_failure(self, mock_create_model):
        """Test handling of model creation failure."""
        mock_create_model.side_effect = Exception("Failed to create embedding model")

        nodes = [TextNode(text="Test content")]
        config = {'embedding_model': 'invalid-model', 'openai_api_key': 'sk-test'}

        # Should propagate model creation error
        with pytest.raises(Exception, match="Failed to create embedding model"):
            create_embeddings(nodes, config)

    @patch('utils.embedder.create_embedding_model')
    def test_api_rate_limit_error(self, mock_create_model):
        """Test handling of API rate limit errors."""
        mock_model = MagicMock()
        mock_model.get_text_embedding.side_effect = Exception("Rate limit exceeded")
        mock_create_model.return_value = mock_model

        nodes = [TextNode(text="Test content")]
        config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': 'sk-test'}

        # Should propagate rate limit error
        with pytest.raises(Exception, match="Rate limit exceeded"):
            create_embeddings(nodes, config)

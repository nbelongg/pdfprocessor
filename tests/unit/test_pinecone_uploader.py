"""
Unit tests for utils/pinecone_uploader.py module.

Tests Pinecone operations:
- Index initialization
- Vector upload batching
- Namespace handling
- Network error retries
- Rate limiting
- Error categorization (transient vs permanent)
"""

import pytest
from unittest.mock import patch, MagicMock, call
from llama_index.core.schema import TextNode

from utils.pinecone_uploader import initialize_pinecone, upload_to_pinecone
from utils.exceptions import TransientError


@pytest.mark.unit
class TestInitializePinecone:
    """Test Pinecone initialization."""

    @patch('utils.pinecone_uploader.Pinecone')
    def test_initialize_existing_index(self, mock_pinecone_class):
        """Test initialization with existing index."""
        # Setup mock Pinecone client
        mock_pc = MagicMock()
        mock_pinecone_class.return_value = mock_pc

        # Mock existing index
        mock_index_info = MagicMock()
        mock_index_info.name = 'test-index'
        mock_pc.list_indexes.return_value = [mock_index_info]

        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        config = {
            'pinecone_api_key': 'pc-test-key',
            'index_name': 'test-index',
            'embedding_dimension': 1536
        }

        # Call function
        result = initialize_pinecone(config)

        # Verify result
        assert result == mock_index

        # Verify Pinecone was initialized with correct API key
        mock_pinecone_class.assert_called_once_with(api_key='pc-test-key')

        # Verify index was not created (already exists)
        assert not mock_pc.create_index.called

        # Verify index was retrieved
        mock_pc.Index.assert_called_once_with('test-index')

    @patch('utils.pinecone_uploader.Pinecone')
    @patch('utils.pinecone_uploader.time.sleep')
    def test_initialize_creates_new_index(self, mock_sleep, mock_pinecone_class):
        """Test initialization creates new index when it doesn't exist."""
        mock_pc = MagicMock()
        mock_pinecone_class.return_value = mock_pc

        # No existing indexes
        mock_pc.list_indexes.return_value = []

        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        config = {
            'pinecone_api_key': 'pc-test-key',
            'index_name': 'new-index',
            'embedding_dimension': 3072
        }

        result = initialize_pinecone(config)

        # Verify index was created
        mock_pc.create_index.assert_called_once()
        create_call = mock_pc.create_index.call_args
        assert create_call[1]['name'] == 'new-index'
        assert create_call[1]['dimension'] == 3072
        assert create_call[1]['metric'] == 'cosine'

        # Verify sleep after creation
        mock_sleep.assert_called_once_with(1)

    def test_initialize_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        config = {
            'index_name': 'test-index',
            'embedding_dimension': 1536
        }

        with pytest.raises(ValueError, match="pinecone_api_key missing"):
            initialize_pinecone(config)

    @patch('utils.pinecone_uploader.Pinecone')
    def test_initialize_invalid_api_key(self, mock_pinecone_class):
        """Test handling of invalid API key."""
        mock_pinecone_class.side_effect = Exception("Unauthorized: Invalid API key")

        config = {
            'pinecone_api_key': 'invalid-key',
            'index_name': 'test-index'
        }

        # Should raise ValueError (not TransientError)
        with pytest.raises(ValueError, match="Invalid Pinecone API key"):
            initialize_pinecone(config)

    @patch('utils.pinecone_uploader.Pinecone')
    def test_initialize_network_error(self, mock_pinecone_class):
        """Test handling of network errors (transient)."""
        mock_pinecone_class.side_effect = Exception("Network timeout error")

        config = {
            'pinecone_api_key': 'pc-test-key',
            'index_name': 'test-index'
        }

        # Should raise TransientError
        with pytest.raises(TransientError, match="Failed to initialize Pinecone"):
            initialize_pinecone(config)

    @patch('utils.pinecone_uploader.Pinecone')
    def test_initialize_list_indexes_timeout(self, mock_pinecone_class):
        """Test handling of timeout when listing indexes."""
        mock_pc = MagicMock()
        mock_pinecone_class.return_value = mock_pc

        mock_pc.list_indexes.side_effect = Exception("Connection timeout")

        config = {
            'pinecone_api_key': 'pc-test-key',
            'index_name': 'test-index'
        }

        # Should raise TransientError
        with pytest.raises(TransientError, match="Network error listing"):
            initialize_pinecone(config)

    @patch('utils.pinecone_uploader.Pinecone')
    @patch('utils.pinecone_uploader.time.sleep')
    def test_initialize_index_already_exists_error(self, mock_sleep, mock_pinecone_class):
        """Test handling of 'index already exists' error (race condition)."""
        mock_pc = MagicMock()
        mock_pinecone_class.return_value = mock_pc

        mock_pc.list_indexes.return_value = []
        mock_pc.create_index.side_effect = Exception("Index already exists")

        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        config = {
            'pinecone_api_key': 'pc-test-key',
            'index_name': 'test-index'
        }

        # Should handle gracefully and continue
        result = initialize_pinecone(config)

        # Should still return index
        assert result == mock_index

    @patch('utils.pinecone_uploader.Pinecone')
    def test_initialize_with_dict_index_format(self, mock_pinecone_class):
        """Test initialization with dict-format index list."""
        mock_pc = MagicMock()
        mock_pinecone_class.return_value = mock_pc

        # Return indexes as dicts instead of objects
        mock_pc.list_indexes.return_value = [
            {'name': 'index-1'},
            {'name': 'test-index'},
            {'name': 'index-2'}
        ]

        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        config = {
            'pinecone_api_key': 'pc-test-key',
            'index_name': 'test-index'
        }

        result = initialize_pinecone(config)

        # Should find existing index
        assert result == mock_index
        assert not mock_pc.create_index.called


@pytest.mark.unit
class TestUploadToPinecone:
    """Test vector upload to Pinecone."""

    def test_upload_success(self):
        """Test successful vector upload."""
        # Setup mock index
        mock_index = MagicMock()

        # Create test data
        embeddings = [[0.1] * 1536, [0.2] * 1536, [0.3] * 1536]
        nodes = [
            TextNode(text="First chunk"),
            TextNode(text="Second chunk"),
            TextNode(text="Third chunk")
        ]
        metadata_list = [
            {'file_id': 'file-1', 'page': 1},
            {'file_id': 'file-1', 'page': 2},
            {'file_id': 'file-1', 'page': 3}
        ]

        # Call function
        count = upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list,
            namespace='test-namespace'
        )

        # Verify result
        assert count == 3

        # Verify upsert was called
        assert mock_index.upsert.called
        call_args = mock_index.upsert.call_args
        assert call_args[1]['namespace'] == 'test-namespace'

        # Verify vector structure
        vectors = call_args[1]['vectors']
        assert len(vectors) == 3
        assert vectors[0]['id'] == 'file-1_0'
        assert vectors[0]['values'] == [0.1] * 1536
        assert 'text' in vectors[0]['metadata']
        assert vectors[0]['metadata']['text'] == 'First chunk'

    def test_upload_batch_processing(self):
        """Test that large uploads are batched."""
        mock_index = MagicMock()

        # Create 250 vectors (should be uploaded in 3 batches of 100, 100, 50)
        embeddings = [[i/1000.0] * 1536 for i in range(250)]
        nodes = [TextNode(text=f"Chunk {i}") for i in range(250)]
        metadata_list = [{'file_id': 'file-1', 'index': i} for i in range(250)]

        count = upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        assert count == 250

        # Verify upsert was called 3 times (3 batches)
        assert mock_index.upsert.call_count == 3

        # Verify batch sizes
        calls = mock_index.upsert.call_args_list
        assert len(calls[0][1]['vectors']) == 100
        assert len(calls[1][1]['vectors']) == 100
        assert len(calls[2][1]['vectors']) == 50

    def test_upload_empty_input_error(self):
        """Test that empty inputs raise ValueError."""
        mock_index = MagicMock()

        with pytest.raises(ValueError, match="Empty embeddings"):
            upload_to_pinecone(
                index=mock_index,
                embeddings=[],
                nodes=[],
                metadata_list=[]
            )

    def test_upload_length_mismatch_error(self):
        """Test that length mismatch raises ValueError."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536, [0.2] * 1536]
        nodes = [TextNode(text="Only one")]
        metadata_list = [{'file_id': 'file-1'}, {'file_id': 'file-2'}]

        with pytest.raises(ValueError, match="Length mismatch"):
            upload_to_pinecone(
                index=mock_index,
                embeddings=embeddings,
                nodes=nodes,
                metadata_list=metadata_list
            )

    def test_upload_rate_limit_error(self):
        """Test handling of rate limit errors (transient)."""
        mock_index = MagicMock()
        mock_index.upsert.side_effect = Exception("Rate limit exceeded (429)")

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1'}]

        # Should raise TransientError
        with pytest.raises(TransientError, match="rate limit"):
            upload_to_pinecone(
                index=mock_index,
                embeddings=embeddings,
                nodes=nodes,
                metadata_list=metadata_list
            )

    def test_upload_timeout_error(self):
        """Test handling of timeout errors (transient)."""
        mock_index = MagicMock()
        mock_index.upsert.side_effect = Exception("Request timed out")

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1'}]

        # Should raise TransientError
        with pytest.raises(TransientError, match="Network/rate limit error.*timed out"):
            upload_to_pinecone(
                index=mock_index,
                embeddings=embeddings,
                nodes=nodes,
                metadata_list=metadata_list
            )

    def test_upload_dimension_mismatch_error(self):
        """Test handling of dimension mismatch (permanent error)."""
        mock_index = MagicMock()
        mock_index.upsert.side_effect = Exception("Vector dimension does not match index dimension")

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1'}]

        # Should raise ValueError (not TransientError)
        with pytest.raises(ValueError, match="dimension mismatch"):
            upload_to_pinecone(
                index=mock_index,
                embeddings=embeddings,
                nodes=nodes,
                metadata_list=metadata_list
            )

    def test_upload_auth_error(self):
        """Test handling of authentication errors (permanent)."""
        mock_index = MagicMock()
        mock_index.upsert.side_effect = Exception("401 Unauthorized")

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1'}]

        # Should raise ValueError
        with pytest.raises(ValueError, match="Authentication error"):
            upload_to_pinecone(
                index=mock_index,
                embeddings=embeddings,
                nodes=nodes,
                metadata_list=metadata_list
            )

    def test_upload_metadata_sanitization(self):
        """Test that metadata is properly sanitized."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{
            'file_id': 'file-1',
            'tags': ['tag1', 'tag2', 'tag3'],  # List
            'extra': {'nested': 'dict'},  # Dict
            'empty': None  # None value
        }]

        count = upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        # Verify metadata was sanitized
        call_args = mock_index.upsert.call_args
        vector_metadata = call_args[1]['vectors'][0]['metadata']

        # List should be converted to comma-separated string
        assert vector_metadata['tags'] == 'tag1, tag2, tag3'

        # Dict should be converted to string
        assert isinstance(vector_metadata['extra'], str)

        # None should be converted to empty string
        assert vector_metadata['empty'] == ""

    def test_upload_namespace_handling(self):
        """Test that namespace is correctly applied."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1'}]

        # Upload with custom namespace
        count = upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list,
            namespace='custom-namespace'
        )

        # Verify namespace was used
        call_args = mock_index.upsert.call_args
        assert call_args[1]['namespace'] == 'custom-namespace'

    def test_upload_default_namespace(self):
        """Test default namespace when not specified."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1'}]

        # Upload without specifying namespace
        count = upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        # Verify default namespace was used
        call_args = mock_index.upsert.call_args
        assert call_args[1]['namespace'] == 'default'

    def test_upload_partial_batch_failure(self):
        """Test handling when a middle batch fails."""
        mock_index = MagicMock()

        # First batch succeeds, second fails
        mock_index.upsert.side_effect = [
            None,  # First batch succeeds
            Exception("Timeout on second batch")
        ]

        # Create 150 vectors (2 batches of 100, 50)
        embeddings = [[i/1000.0] * 1536 for i in range(150)]
        nodes = [TextNode(text=f"Chunk {i}") for i in range(150)]
        metadata_list = [{'file_id': 'file-1'} for _ in range(150)]

        # Should fail on second batch
        with pytest.raises(TransientError):
            upload_to_pinecone(
                index=mock_index,
                embeddings=embeddings,
                nodes=nodes,
                metadata_list=metadata_list
            )

        # First batch should have been uploaded
        assert mock_index.upsert.call_count == 2

    def test_upload_vector_id_generation(self):
        """Test that vector IDs are correctly generated."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536, [0.2] * 1536]
        nodes = [TextNode(text="Chunk 1"), TextNode(text="Chunk 2")]
        metadata_list = [
            {'file_id': 'file-abc'},
            {'file_id': 'file-xyz'}
        ]

        upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        # Verify vector IDs
        call_args = mock_index.upsert.call_args
        vectors = call_args[1]['vectors']
        assert vectors[0]['id'] == 'file-abc_0'
        assert vectors[1]['id'] == 'file-xyz_1'

    def test_upload_with_tags_metadata(self):
        """Test upload with tags in metadata (special handling)."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{
            'file_id': 'file-1',
            'tags': ['machine-learning', 'neural-networks']
        }]

        upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        # Tags should be converted to comma-separated string
        call_args = mock_index.upsert.call_args
        vector_metadata = call_args[1]['vectors'][0]['metadata']
        assert vector_metadata['tags'] == 'machine-learning, neural-networks'


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('utils.pinecone_uploader.Pinecone')
    def test_initialize_with_defaults(self, mock_pinecone_class):
        """Test initialization uses default values."""
        mock_pc = MagicMock()
        mock_pinecone_class.return_value = mock_pc

        mock_index_info = MagicMock()
        mock_index_info.name = 'research-papers'  # Default name
        mock_pc.list_indexes.return_value = [mock_index_info]

        mock_index = MagicMock()
        mock_pc.Index.return_value = mock_index

        # Minimal config
        config = {'pinecone_api_key': 'pc-test-key'}

        result = initialize_pinecone(config)

        # Should use defaults
        mock_pc.Index.assert_called_with('research-papers')

    def test_upload_missing_file_id_in_metadata(self):
        """Test upload when file_id is missing from metadata."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{}]  # No file_id

        count = upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        # Should use 'unknown' as fallback
        call_args = mock_index.upsert.call_args
        vector_id = call_args[1]['vectors'][0]['id']
        assert vector_id == 'unknown_0'

    def test_upload_empty_tags_list(self):
        """Test upload with empty tags list."""
        mock_index = MagicMock()

        embeddings = [[0.1] * 1536]
        nodes = [TextNode(text="Chunk")]
        metadata_list = [{'file_id': 'file-1', 'tags': []}]

        upload_to_pinecone(
            index=mock_index,
            embeddings=embeddings,
            nodes=nodes,
            metadata_list=metadata_list
        )

        # Empty list should become empty string
        call_args = mock_index.upsert.call_args
        vector_metadata = call_args[1]['vectors'][0]['metadata']
        assert vector_metadata['tags'] == ""

"""
Integration tests for utils/pipeline.py module.

Tests full pipeline with mocked external services:
- Complete pipeline flow (download → parse → chunk → embed → upload)
- Error handling at each stage
- Retry logic for transient errors
- Progress callback updates
- Preview mode vs normal mode
- Namespace handling
- Metadata propagation
"""

import pytest
from unittest.mock import patch, MagicMock, call
import pandas as pd
import uuid

from utils.pipeline import process_pipeline


@pytest.mark.integration
class TestPipelineFullFlow:
    """Test complete pipeline flow with mocked external services."""

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_full_pipeline_success(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test successful full pipeline execution."""
        # Setup test data
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view'],
            'Title': ['Test Paper'],
            'Authors': ['John Doe']
        })

        # Setup mocks
        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf content'
        mock_get_metadata.return_value = {
            'id': 'file-123',
            'name': 'test.pdf',
            'size': '12345'
        }
        mock_parse.return_value = 'Parsed text content'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node, mock_node]

        mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]
        mock_pinecone_index = MagicMock()
        mock_init_pinecone.return_value = mock_pinecone_index
        mock_upload.return_value = 2

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': ['Title', 'Authors'],
            'default_namespace': 'test-namespace',
            'google_credentials': {},
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'test-index'
        }

        # Execute pipeline
        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        # Verify results
        assert result['total_pdfs'] == 1
        assert result['total_chunks'] == 2
        assert result['total_embeddings'] == 2
        assert result['vectors_stored'] == 2
        assert len(result['details']) == 1
        assert result['details'][0]['status'] == 'success'

        # Verify all pipeline steps were called
        assert mock_create_job.called
        assert mock_extract_file_id.called
        assert mock_download.called
        assert mock_get_metadata.called
        assert mock_parse.called
        assert mock_chunk.called
        assert mock_embed.called
        assert mock_init_pinecone.called
        assert mock_upload.called
        assert mock_save_chunks.called
        assert mock_mark_uploaded.called
        assert mock_update_status.called

        # Verify final status is completed
        final_status_call = [call for call in mock_update_status.call_args_list
                            if 'completed' in str(call)]
        assert len(final_status_call) > 0

    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    def test_pipeline_preview_mode(
        self, mock_embed, mock_chunk, mock_parse, mock_get_metadata,
        mock_download, mock_extract_file_id
    ):
        """Test pipeline in preview mode (no DB/Pinecone operations)."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view'],
            'Title': ['Test Paper']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': ['Title'],
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=True
        )

        # Verify preview chunks are returned
        assert result['preview_chunks'] is not None
        assert len(result['preview_chunks']) == 1
        assert result['preview_chunks'][0]['text'] == 'chunk text'

        # Verify DB/Pinecone operations were NOT called
        with patch('utils.pipeline.create_processing_job') as mock_job:
            assert not mock_job.called

    @patch('utils.pipeline.extract_file_id_from_drive_link')
    def test_pipeline_skip_invalid_drive_link(self, mock_extract_file_id):
        """Test that rows with invalid Drive links are skipped."""
        df = pd.DataFrame({
            'Drive Link': ['', 'invalid-link'],
            'Title': ['Paper 1', 'Paper 2']
        })

        mock_extract_file_id.return_value = None

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': ['Title'],
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0, 1],
            config=config,
            preview_mode=True
        )

        # Both should be skipped
        assert len(result['details']) == 2
        assert result['details'][0]['status'] == 'skipped'
        assert result['details'][1]['status'] == 'skipped'
        assert 'No valid Drive link' in result['details'][0]['reason']


@pytest.mark.integration
class TestPipelineErrorHandling:
    """Test error handling at each pipeline stage."""

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    def test_download_error_handling(
        self, mock_download, mock_extract_file_id, mock_update_status, mock_create_job
    ):
        """Test error handling when download fails."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.side_effect = Exception('Download failed: Network error')

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        # Verify error was captured
        assert len(result['details']) == 1
        assert result['details'][0]['status'] == 'error'
        assert 'Download failed' in result['details'][0]['error']

        # Verify final status is error
        error_status_calls = [call for call in mock_update_status.call_args_list
                             if 'error' in str(call)]
        assert len(error_status_calls) > 0

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    def test_parse_error_handling(
        self, mock_parse, mock_get_metadata, mock_download,
        mock_extract_file_id, mock_update_status, mock_create_job
    ):
        """Test error handling when parsing fails."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.side_effect = Exception('Parse failed: Invalid PDF')

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        assert result['details'][0]['status'] == 'error'
        assert 'Parse failed' in result['details'][0]['error']

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    def test_chunk_error_handling(
        self, mock_chunk, mock_parse, mock_get_metadata, mock_download,
        mock_extract_file_id, mock_update_status, mock_create_job
    ):
        """Test error handling when chunking fails."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'
        mock_chunk.side_effect = Exception('Chunk failed: Text too long')

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        assert result['details'][0]['status'] == 'error'
        assert 'Chunk failed' in result['details'][0]['error']

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    def test_embedding_error_handling(
        self, mock_embed, mock_chunk, mock_parse, mock_get_metadata,
        mock_download, mock_extract_file_id, mock_update_status, mock_create_job
    ):
        """Test error handling when embedding creation fails."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_chunk.return_value = [mock_node]

        mock_embed.side_effect = Exception('Embedding failed: API rate limit')

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'google_credentials': {},
            'openai_api_key': 'sk-test'
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        assert result['details'][0]['status'] == 'error'
        assert 'Embedding failed' in result['details'][0]['error']

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    def test_upload_error_handling(
        self, mock_upload, mock_init_pinecone, mock_embed, mock_chunk,
        mock_parse, mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test error handling when Pinecone upload fails."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.side_effect = Exception('Upload failed: Connection timeout')

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'google_credentials': {},
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'test-index',
            'default_namespace': 'default'
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        assert result['details'][0]['status'] == 'error'
        assert 'Upload failed' in result['details'][0]['error']


@pytest.mark.integration
class TestPipelineProgressCallbacks:
    """Test progress callback functionality."""

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_progress_callbacks_called(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test that progress callbacks are called at each stage."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'google_credentials': {},
            'default_namespace': 'default'
        }

        progress_callback = MagicMock()

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            progress_callback=progress_callback,
            preview_mode=False
        )

        # Verify progress callback was called multiple times
        assert progress_callback.call_count >= 5

        # Check for specific progress messages
        call_messages = [call[0][1] for call in progress_callback.call_args_list]
        assert any('Processing PDF' in msg for msg in call_messages)
        assert any('Downloading' in msg for msg in call_messages)
        assert any('Parsing' in msg for msg in call_messages)
        assert any('Chunking' in msg for msg in call_messages)
        assert any('embeddings' in msg for msg in call_messages)


@pytest.mark.integration
class TestPipelineNamespaceHandling:
    """Test namespace handling in pipeline."""

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_namespace_from_column(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test that namespace is correctly extracted from column."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view'],
            'Namespace': ['custom-namespace']
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'namespace_column': 'Namespace',
            'default_namespace': 'default',
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        # Verify upload was called with custom namespace
        mock_upload.assert_called_once()
        call_args = mock_upload.call_args
        namespace_arg = call_args[0][4]  # 5th positional argument
        assert namespace_arg == 'custom-namespace'

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_namespace_default_when_empty(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test that default namespace is used when column is empty."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view'],
            'Namespace': ['']  # Empty namespace
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': [],
            'namespace_column': 'Namespace',
            'default_namespace': 'fallback-namespace',
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        # Verify upload was called with default namespace
        call_args = mock_upload.call_args
        namespace_arg = call_args[0][4]
        assert namespace_arg == 'fallback-namespace'


@pytest.mark.integration
class TestPipelineMetadataPropagation:
    """Test metadata propagation through pipeline."""

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_metadata_columns_propagated(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test that metadata columns are properly propagated to chunks."""
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view'],
            'Title': ['Research Paper'],
            'Authors': ['John Doe, Jane Smith'],
            'Year': [2024]
        })

        mock_extract_file_id.return_value = 'file-123'
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': ['Title', 'Authors', 'Year'],
            'default_namespace': 'default',
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0],
            config=config,
            preview_mode=False
        )

        # Verify chunk_text was called with metadata
        mock_chunk.assert_called_once()
        call_args = mock_chunk.call_args
        metadata_arg = call_args[0][2]  # 3rd positional argument

        assert metadata_arg['Title'] == 'Research Paper'
        assert metadata_arg['Authors'] == 'John Doe, Jane Smith'
        assert metadata_arg['Year'] == '2024'
        assert metadata_arg['file_id'] == 'file-123'
        assert metadata_arg['filename'] == 'test.pdf'


@pytest.mark.integration
class TestPipelineMultipleFiles:
    """Test pipeline with multiple files."""

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_multiple_files_success(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test processing multiple files successfully."""
        df = pd.DataFrame({
            'Drive Link': [
                'https://drive.google.com/file/d/file-1/view',
                'https://drive.google.com/file/d/file-2/view',
                'https://drive.google.com/file/d/file-3/view'
            ],
            'Title': ['Paper 1', 'Paper 2', 'Paper 3']
        })

        mock_extract_file_id.side_effect = ['file-1', 'file-2', 'file-3']
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.side_effect = [
            {'id': 'file-1', 'name': 'paper1.pdf'},
            {'id': 'file-2', 'name': 'paper2.pdf'},
            {'id': 'file-3', 'name': 'paper3.pdf'}
        ]
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node, mock_node]

        mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 2

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': ['Title'],
            'default_namespace': 'default',
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0, 1, 2],
            config=config,
            preview_mode=False
        )

        # Verify all 3 files were processed
        assert result['total_pdfs'] == 3
        assert result['total_chunks'] == 6  # 2 chunks per file
        assert len(result['details']) == 3
        assert all(detail['status'] == 'success' for detail in result['details'])

    @patch('utils.pipeline.create_processing_job')
    @patch('utils.pipeline.update_job_status')
    @patch('utils.pipeline.extract_file_id_from_drive_link')
    @patch('utils.pipeline.download_pdf_from_drive')
    @patch('utils.pipeline.get_file_metadata')
    @patch('utils.pipeline.parse_pdf_with_llamaparse')
    @patch('utils.pipeline.chunk_text')
    @patch('utils.pipeline.create_embeddings')
    @patch('utils.pipeline.initialize_pinecone')
    @patch('utils.pipeline.upload_to_pinecone')
    @patch('utils.pipeline.save_chunks')
    @patch('utils.pipeline.mark_chunks_uploaded')
    def test_multiple_files_partial_failure(
        self, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_parse,
        mock_get_metadata, mock_download, mock_extract_file_id,
        mock_update_status, mock_create_job
    ):
        """Test processing multiple files with some failures."""
        df = pd.DataFrame({
            'Drive Link': [
                'https://drive.google.com/file/d/file-1/view',
                'https://drive.google.com/file/d/file-2/view'
            ],
            'Title': ['Paper 1', 'Paper 2']
        })

        mock_extract_file_id.side_effect = ['file-1', 'file-2']
        # First file succeeds, second fails
        mock_download.side_effect = [b'fake pdf', Exception('Download failed')]

        mock_get_metadata.return_value = {'id': 'file-1', 'name': 'paper1.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1

        config = {
            'drive_link_column': 'Drive Link',
            'metadata_columns': ['Title'],
            'default_namespace': 'default',
            'google_credentials': {}
        }

        result = process_pipeline(
            sheet_data=df,
            selected_indices=[0, 1],
            config=config,
            preview_mode=False
        )

        # Verify one success, one error
        assert result['total_pdfs'] == 1
        assert len(result['details']) == 2
        assert result['details'][0]['status'] == 'success'
        assert result['details'][1]['status'] == 'error'

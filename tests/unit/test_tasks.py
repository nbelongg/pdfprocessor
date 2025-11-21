"""
Unit tests for tasks.py module.

Tests Celery task operations:
- Retry logic with exponential backoff
- PDF processing logic (_process_single_pdf_logic)
- Celery task wrappers (process_pdf_task, process_batch_task)
- Error categorization (transient vs permanent)
- Cost tracking integration
- Deduplication integration
"""

import pytest
from unittest.mock import patch, MagicMock, call, ANY
from datetime import datetime
import time

from tasks import (
    call_with_retry,
    _process_single_pdf_logic,
    process_pdf_task,
    process_batch_task,
    CallbackTask,
    DEFAULT_MAX_RETRIES,
    DEFAULT_BACKOFF_FACTOR,
    PROGRESS_DOWNLOAD,
    PROGRESS_PARSE,
    PROGRESS_CHUNK,
    PROGRESS_EMBED,
    PROGRESS_UPLOAD,
    PROGRESS_COMPLETE
)
from utils.exceptions import TransientError


@pytest.mark.unit
class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    def test_call_with_retry_success_first_attempt(self):
        """Test successful function call on first attempt."""
        mock_func = MagicMock(return_value='success')

        result = call_with_retry(mock_func)

        assert result == 'success'
        assert mock_func.call_count == 1

    def test_call_with_retry_success_after_retries(self):
        """Test successful function call after some retries."""
        mock_func = MagicMock(side_effect=[Exception('error1'), Exception('error2'), 'success'])

        result = call_with_retry(mock_func, max_retries=3)

        assert result == 'success'
        assert mock_func.call_count == 3

    @patch('tasks.time.sleep')
    def test_call_with_retry_exponential_backoff(self, mock_sleep):
        """Test exponential backoff timing."""
        mock_func = MagicMock(side_effect=[Exception('error1'), Exception('error2'), 'success'])

        result = call_with_retry(mock_func, max_retries=3, backoff_factor=2)

        assert result == 'success'
        # Should sleep 1s (2^0), then 2s (2^1)
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1)
        mock_sleep.assert_any_call(2)

    def test_call_with_retry_all_retries_fail(self):
        """Test when all retries are exhausted."""
        mock_func = MagicMock(side_effect=Exception('persistent error'))

        with pytest.raises(Exception, match='persistent error'):
            call_with_retry(mock_func, max_retries=3)

        assert mock_func.call_count == 3

    def test_call_with_retry_specific_exceptions(self):
        """Test retry only on specific exceptions."""
        mock_func = MagicMock(side_effect=ValueError('value error'))

        # Should retry on ValueError
        with pytest.raises(ValueError):
            call_with_retry(mock_func, max_retries=2, exceptions=(ValueError,))

        assert mock_func.call_count == 2

    def test_call_with_retry_non_matching_exception_fails_immediately(self):
        """Test that non-matching exceptions are not retried."""
        mock_func = MagicMock(side_effect=ValueError('value error'))

        # Should NOT retry on ValueError when looking for TypeError
        with pytest.raises(ValueError):
            call_with_retry(mock_func, max_retries=3, exceptions=(TypeError,))

        # Should fail on first attempt without retry
        assert mock_func.call_count == 1


@pytest.mark.unit
class TestProcessSinglePDFLogic:
    """Test core PDF processing logic."""

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    @patch('tasks.get_file_metadata')
    @patch('tasks.parse_pdf_with_llamaparse')
    @patch('tasks.save_parsed_document')
    @patch('tasks.chunk_text')
    @patch('tasks.create_embeddings')
    @patch('tasks.initialize_pinecone')
    @patch('tasks.upload_to_pinecone')
    @patch('tasks.save_chunks')
    @patch('tasks.mark_chunks_uploaded')
    @patch('tasks.record_processed_paper')
    @patch('tasks.track_api_cost')
    @patch('tasks.calculate_llamaparse_cost')
    @patch('tasks.calculate_openai_embedding_cost')
    @patch('tasks.estimate_tokens_from_text')
    def test_process_single_pdf_success(
        self, mock_estimate, mock_calc_embed, mock_calc_llama, mock_track_cost,
        mock_record, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_save_parsed,
        mock_parse, mock_get_metadata, mock_download, mock_update_runtime
    ):
        """Test successful PDF processing."""
        # Setup mocks
        mock_download.return_value = b'fake pdf content'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf', 'num_pages': 10}
        mock_parse.return_value = 'Parsed text content'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1
        mock_estimate.return_value = 100
        mock_calc_llama.return_value = 0.003
        mock_calc_embed.return_value = 0.0001

        # Call function
        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test Paper'},
            config={'google_credentials': {}, 'openai_api_key': 'sk-test'},
            job_id='job-123',
            namespace='default'
        )

        # Verify result
        assert result['status'] == 'success'
        assert result['file_id'] == 'file-123'
        assert result['filename'] == 'test.pdf'
        assert result['chunks'] == 1
        assert result['vectors_uploaded'] == 1
        assert 'processing_time_seconds' in result

        # Verify pipeline steps were called
        assert mock_download.called
        assert mock_get_metadata.called
        assert mock_parse.called
        assert mock_save_parsed.called
        assert mock_chunk.called
        assert mock_embed.called
        assert mock_upload.called
        assert mock_save_chunks.called
        assert mock_mark_uploaded.called
        assert mock_record.called

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    def test_process_single_pdf_download_failure(self, mock_download, mock_update_runtime):
        """Test handling of download failure."""
        mock_download.side_effect = Exception('Download failed')

        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test Paper'},
            config={'google_credentials': {}},
            job_id='job-123',
            namespace='default'
        )

        assert result['status'] == 'error'
        assert 'Download failed' in result['error']
        assert result['filename'] == 'test.pdf'

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    @patch('tasks.get_file_metadata')
    @patch('tasks.parse_pdf_with_llamaparse')
    def test_process_single_pdf_parse_failure(
        self, mock_parse, mock_get_metadata, mock_download, mock_update_runtime
    ):
        """Test handling of parsing failure."""
        mock_download.return_value = b'fake pdf content'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.side_effect = Exception('Parse failed')

        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test Paper'},
            config={'google_credentials': {}},
            job_id='job-123',
            namespace='default'
        )

        assert result['status'] == 'error'
        assert 'Parse failed' in result['error']

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    @patch('tasks.get_file_metadata')
    @patch('tasks.parse_pdf_with_llamaparse')
    @patch('tasks.save_parsed_document')
    @patch('tasks.chunk_text')
    @patch('tasks.create_embeddings')
    def test_process_single_pdf_embedding_failure(
        self, mock_embed, mock_chunk, mock_save_parsed, mock_parse,
        mock_get_metadata, mock_download, mock_update_runtime
    ):
        """Test handling of embedding failure."""
        mock_download.return_value = b'fake pdf content'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf'}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_chunk.return_value = [mock_node]

        mock_embed.side_effect = Exception('Embedding API error')

        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test Paper'},
            config={'google_credentials': {}},
            job_id='job-123',
            namespace='default'
        )

        assert result['status'] == 'error'
        assert 'Embedding API error' in result['error']

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    @patch('tasks.get_file_metadata')
    @patch('tasks.parse_pdf_with_llamaparse')
    @patch('tasks.save_parsed_document')
    @patch('tasks.is_document_tagged')
    @patch('tasks.generate_tags_with_openai')
    @patch('tasks.validate_tags')
    @patch('tasks.update_document_tags')
    @patch('tasks.chunk_text')
    @patch('tasks.create_embeddings')
    @patch('tasks.initialize_pinecone')
    @patch('tasks.upload_to_pinecone')
    @patch('tasks.save_chunks')
    @patch('tasks.mark_chunks_uploaded')
    @patch('tasks.record_processed_paper')
    @patch('tasks.track_api_cost')
    @patch('tasks.calculate_llamaparse_cost')
    @patch('tasks.calculate_openai_embedding_cost')
    @patch('tasks.estimate_tokens_from_text')
    def test_process_single_pdf_with_tagging(
        self, mock_estimate, mock_calc_embed, mock_calc_llama, mock_track_cost,
        mock_record, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_update_tags,
        mock_validate_tags, mock_generate_tags, mock_is_tagged,
        mock_save_parsed, mock_parse, mock_get_metadata, mock_download,
        mock_update_runtime
    ):
        """Test PDF processing with AI tagging enabled."""
        # Setup mocks
        mock_download.return_value = b'fake pdf content'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf', 'num_pages': 10}
        mock_parse.return_value = 'Parsed text content'
        mock_is_tagged.return_value = False
        mock_generate_tags.return_value = ['machine-learning', 'neural-networks']
        mock_validate_tags.return_value = ['machine-learning', 'neural-networks']

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1
        mock_estimate.return_value = 100
        mock_calc_llama.return_value = 0.003
        mock_calc_embed.return_value = 0.0001

        # Call with tagging enabled
        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test Paper'},
            config={
                'google_credentials': {},
                'openai_api_key': 'sk-test',
                'tagging_enabled': True,
                'tagging_model': 'gpt-4o-mini'
            },
            job_id='job-123',
            namespace='default'
        )

        # Verify tagging was performed
        assert result['status'] == 'success'
        assert mock_generate_tags.called
        assert mock_validate_tags.called
        assert mock_update_tags.called

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    @patch('tasks.get_file_metadata')
    @patch('tasks.parse_pdf_with_llamaparse')
    @patch('tasks.save_parsed_document')
    @patch('tasks.chunk_text')
    @patch('tasks.create_embeddings')
    @patch('tasks.initialize_pinecone')
    @patch('tasks.upload_to_pinecone')
    @patch('tasks.save_chunks')
    @patch('tasks.mark_chunks_uploaded')
    @patch('tasks.record_processed_paper')
    @patch('tasks.track_api_cost')
    @patch('tasks.calculate_llamaparse_cost')
    @patch('tasks.calculate_openai_embedding_cost')
    @patch('tasks.estimate_tokens_from_text')
    def test_process_single_pdf_progress_callback(
        self, mock_estimate, mock_calc_embed, mock_calc_llama, mock_track_cost,
        mock_record, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_save_parsed,
        mock_parse, mock_get_metadata, mock_download, mock_update_runtime
    ):
        """Test progress callback updates."""
        # Setup mocks
        mock_download.return_value = b'fake pdf content'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf', 'num_pages': 10}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node]

        mock_embed.return_value = [[0.1] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 1
        mock_estimate.return_value = 100
        mock_calc_llama.return_value = 0.003
        mock_calc_embed.return_value = 0.0001

        # Mock progress callback
        progress_callback = MagicMock()

        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test Paper'},
            config={'google_credentials': {}, 'openai_api_key': 'sk-test'},
            job_id='job-123',
            namespace='default',
            progress_callback=progress_callback
        )

        assert result['status'] == 'success'

        # Verify progress callbacks were made
        assert progress_callback.call_count >= 5
        # Check for specific progress milestones
        call_args_list = [call[0] for call in progress_callback.call_args_list]
        assert any(PROGRESS_DOWNLOAD in args for args in call_args_list)
        assert any(PROGRESS_PARSE in args for args in call_args_list)
        assert any(PROGRESS_CHUNK in args for args in call_args_list)
        assert any(PROGRESS_EMBED in args for args in call_args_list)
        assert any(PROGRESS_UPLOAD in args for args in call_args_list)


@pytest.mark.unit
class TestCeleryTaskWrappers:
    """Test Celery task wrappers."""

    @patch('tasks._process_single_pdf_logic')
    def test_process_pdf_task(self, mock_process_logic):
        """Test process_pdf_task Celery wrapper."""
        mock_process_logic.return_value = {
            'status': 'success',
            'file_id': 'file-123',
            'chunks': 10
        }

        # Create mock task instance
        mock_task = MagicMock(spec=CallbackTask)
        mock_task.update_progress = MagicMock()

        # Bind the function to the mock task
        result = process_pdf_task.__get__(mock_task, CallbackTask)(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test'},
            config={'google_credentials': {}},
            job_id='job-123',
            namespace='default'
        )

        assert result['status'] == 'success'
        assert mock_process_logic.called

    @patch('tasks.get_data_source')
    @patch('tasks.build_product_config')
    @patch('tasks.load_sheet_data')
    @patch('tasks.get_column_mapping_dict')
    @patch('tasks._process_single_pdf_logic')
    @patch('tasks.update_celery_job_status')
    @patch('tasks.log_environment_diagnostic')
    @patch('tasks.should_process_paper')
    def test_process_batch_task_success(
        self, mock_should_process, mock_log_env, mock_update_status,
        mock_process_logic, mock_get_mapping, mock_load_sheet,
        mock_build_config, mock_get_source
    ):
        """Test successful batch processing."""
        import pandas as pd

        # Setup mocks
        mock_get_source.return_value = {
            'id': 1,
            'name': 'Test Source',
            'sheet_url': 'https://docs.google.com/spreadsheets/test',
            'sheet_tab': 'Sheet1',
            'product_id': None
        }

        mock_build_config.return_value = {
            'google_credentials': {},
            'default_namespace': 'default',
            'dedup_layer1': True,
            'dedup_layer2': True
        }

        # Create test dataframe
        df = pd.DataFrame({
            'Drive Link': ['https://drive.google.com/file/d/file-123/view'],
            'Title': ['Test Paper']
        })
        mock_load_sheet.return_value = df

        mock_get_mapping.return_value = {
            'drive_link': 'Drive Link',
            'metadata_columns': ['Title']
        }

        mock_should_process.return_value = {
            'should_process': True,
            'reason': 'New paper',
            'state': 2
        }

        mock_process_logic.return_value = {
            'status': 'success',
            'file_id': 'file-123',
            'filename': 'test.pdf',
            'chunks': 10,
            'vectors_uploaded': 10
        }

        # Create mock task instance
        mock_task = MagicMock(spec=CallbackTask)
        mock_task.request = MagicMock(id='task-123')
        mock_task.update_progress = MagicMock()

        # Call batch task
        result = process_batch_task.__get__(mock_task, CallbackTask)(
            source_id=1,
            selected_indices=[0],
            config={'google_credentials': {}},
            preview_mode=False
        )

        assert result['job_id'] == 'task-123'
        assert result['new_papers_count'] == 1
        assert result['skipped_papers_count'] == 0
        assert result['total_pdfs'] == 1

    @patch('tasks.get_data_source')
    @patch('tasks.update_celery_job_status')
    def test_process_batch_task_source_not_found(self, mock_update_status, mock_get_source):
        """Test batch task when data source not found."""
        mock_get_source.return_value = None

        # Create mock task instance
        mock_task = MagicMock(spec=CallbackTask)
        mock_task.request = MagicMock(id='task-123')
        mock_task.update_progress = MagicMock()

        result = process_batch_task.__get__(mock_task, CallbackTask)(
            source_id=999,
            selected_indices=[0],
            config={'google_credentials': {}},
            preview_mode=False
        )

        assert result['status'] == 'error'
        assert 'not found' in result['error']
        assert mock_update_status.called

    @patch('tasks.get_data_source')
    @patch('tasks.build_product_config')
    @patch('tasks.load_sheet_data')
    @patch('tasks.get_column_mapping_dict')
    @patch('tasks._process_single_pdf_logic')
    @patch('tasks.update_celery_job_status')
    @patch('tasks.log_environment_diagnostic')
    @patch('tasks.should_process_paper')
    def test_process_batch_task_with_deduplication(
        self, mock_should_process, mock_log_env, mock_update_status,
        mock_process_logic, mock_get_mapping, mock_load_sheet,
        mock_build_config, mock_get_source
    ):
        """Test batch task with deduplication skipping papers."""
        import pandas as pd

        # Setup mocks
        mock_get_source.return_value = {
            'id': 1,
            'name': 'Test Source',
            'sheet_url': 'https://docs.google.com/spreadsheets/test',
            'sheet_tab': 'Sheet1',
            'product_id': None
        }

        mock_build_config.return_value = {
            'google_credentials': {},
            'default_namespace': 'default',
            'dedup_layer1': True,
            'dedup_layer2': True
        }

        df = pd.DataFrame({
            'Drive Link': [
                'https://drive.google.com/file/d/file-123/view',
                'https://drive.google.com/file/d/file-456/view'
            ],
            'Title': ['Paper 1', 'Paper 2']
        })
        mock_load_sheet.return_value = df

        mock_get_mapping.return_value = {
            'drive_link': 'Drive Link',
            'metadata_columns': ['Title'],
            'paper_title': 'Title',
            'authors': 'Authors'
        }

        # First paper is duplicate, second is new
        mock_should_process.side_effect = [
            {'should_process': False, 'reason': 'Duplicate', 'state': 1, 'duplicate_layer': 'layer1'},
            {'should_process': True, 'reason': 'New paper', 'state': 2}
        ]

        mock_process_logic.return_value = {
            'status': 'success',
            'file_id': 'file-456',
            'filename': 'paper2.pdf',
            'chunks': 10,
            'vectors_uploaded': 10
        }

        # Create mock task
        mock_task = MagicMock(spec=CallbackTask)
        mock_task.request = MagicMock(id='task-123')
        mock_task.update_progress = MagicMock()

        result = process_batch_task.__get__(mock_task, CallbackTask)(
            source_id=1,
            selected_indices=[0, 1],
            config={'google_credentials': {}},
            preview_mode=False
        )

        # Should skip first paper, process second
        assert result['new_papers_count'] == 1
        assert result['skipped_papers_count'] == 1
        assert len(result['details']) == 2

    @patch('tasks.get_data_source')
    def test_process_batch_task_transient_error_retry(self, mock_get_source):
        """Test that transient errors trigger retry."""
        mock_get_source.side_effect = TransientError('Network timeout')

        # Create mock task
        mock_task = MagicMock(spec=CallbackTask)
        mock_task.request = MagicMock(id='task-123')
        mock_task.retry = MagicMock(side_effect=Exception('Retry triggered'))

        with pytest.raises(Exception, match='Retry triggered'):
            process_batch_task.__get__(mock_task, CallbackTask)(
                source_id=1,
                selected_indices=[0],
                config={'google_credentials': {}},
                preview_mode=False
            )

        # Verify retry was called
        assert mock_task.retry.called


@pytest.mark.unit
class TestCallbackTask:
    """Test CallbackTask base class."""

    def test_update_progress(self):
        """Test progress update functionality."""
        task = CallbackTask()
        task.update_state = MagicMock()

        task.update_progress(50, 100, 'Processing...')

        task.update_state.assert_called_once_with(
            state='PROGRESS',
            meta={
                'current': 50,
                'total': 100,
                'message': 'Processing...',
                'percent': 50
            }
        )

    def test_update_progress_zero_total(self):
        """Test progress update with zero total."""
        task = CallbackTask()
        task.update_state = MagicMock()

        task.update_progress(0, 0, 'Starting...')

        # Should handle division by zero
        call_args = task.update_state.call_args[1]['meta']
        assert call_args['percent'] == 0


@pytest.mark.unit
class TestCostTracking:
    """Test cost tracking integration."""

    @patch('tasks.update_job_runtime')
    @patch('tasks.download_pdf_from_drive')
    @patch('tasks.get_file_metadata')
    @patch('tasks.parse_pdf_with_llamaparse')
    @patch('tasks.save_parsed_document')
    @patch('tasks.chunk_text')
    @patch('tasks.create_embeddings')
    @patch('tasks.initialize_pinecone')
    @patch('tasks.upload_to_pinecone')
    @patch('tasks.save_chunks')
    @patch('tasks.mark_chunks_uploaded')
    @patch('tasks.record_processed_paper')
    @patch('tasks.track_api_cost')
    @patch('tasks.calculate_llamaparse_cost')
    @patch('tasks.calculate_openai_embedding_cost')
    @patch('tasks.estimate_tokens_from_text')
    def test_cost_tracking_called(
        self, mock_estimate, mock_calc_embed, mock_calc_llama, mock_track_cost,
        mock_record, mock_mark_uploaded, mock_save_chunks, mock_upload,
        mock_init_pinecone, mock_embed, mock_chunk, mock_save_parsed,
        mock_parse, mock_get_metadata, mock_download, mock_update_runtime
    ):
        """Test that cost tracking is called for API services."""
        # Setup mocks
        mock_download.return_value = b'fake pdf'
        mock_get_metadata.return_value = {'id': 'file-123', 'name': 'test.pdf', 'num_pages': 15}
        mock_parse.return_value = 'Parsed text'

        mock_node = MagicMock()
        mock_node.get_content.return_value = 'chunk text'
        mock_node.metadata = {'page': 1}
        mock_chunk.return_value = [mock_node, mock_node]

        mock_embed.return_value = [[0.1] * 1536, [0.2] * 1536]
        mock_init_pinecone.return_value = MagicMock()
        mock_upload.return_value = 2
        mock_estimate.return_value = 150
        mock_calc_llama.return_value = 0.045  # 15 pages * $0.003
        mock_calc_embed.return_value = 0.0003  # 300 tokens * $0.000001

        result = _process_single_pdf_logic(
            file_id='file-123',
            filename='test.pdf',
            row_metadata={'title': 'Test'},
            config={'google_credentials': {}, 'openai_api_key': 'sk-test'},
            job_id='job-123',
            namespace='default'
        )

        assert result['status'] == 'success'

        # Verify cost tracking was called twice (LlamaParse + OpenAI embeddings)
        assert mock_track_cost.call_count == 2

        # Verify LlamaParse cost tracking
        llamaparse_call = [call for call in mock_track_cost.call_args_list
                          if call[1]['service'] == 'llamaparse'][0]
        assert llamaparse_call[1]['units'] == 15
        assert llamaparse_call[1]['cost_usd'] == 0.045

        # Verify OpenAI embedding cost tracking
        openai_call = [call for call in mock_track_cost.call_args_list
                      if call[1]['service'] == 'openai_embeddings'][0]
        assert openai_call[1]['units'] == 300  # 2 chunks * 150 tokens
        assert openai_call[1]['cost_usd'] == 0.0003

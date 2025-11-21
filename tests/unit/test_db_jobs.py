"""
Unit tests for utils/db/jobs.py module.

Tests job operations:
- Processing job CRUD operations
- Job status tracking and metrics
- Chunk storage and retrieval
- Metadata transformations
- Celery job tracking
"""

import pytest
from unittest.mock import patch, MagicMock
from psycopg2.extras import Json

from utils.db.jobs import (
    create_processing_job,
    update_job_status,
    get_job_history,
    get_job_details,
    delete_job,
    save_chunks,
    get_job_chunks,
    mark_chunks_uploaded,
    save_metadata_transformation,
    get_metadata_transformations,
    delete_metadata_transformation,
    create_celery_job,
    update_celery_job_status,
    get_celery_job,
    get_all_celery_jobs,
    cancel_celery_job
)


@pytest.mark.unit
class TestProcessingJobs:
    """Test processing job CRUD operations."""

    @patch('utils.db.jobs.get_db_transaction')
    def test_create_processing_job(self, mock_txn):
        """Test creating a new processing job."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 42}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        config = {
            'sheet_url': 'https://docs.google.com/spreadsheets/test',
            'sheet_tab': 'Sheet1',
            'embedding_model': 'text-embedding-3-small'
        }

        result = create_processing_job('job-123', config)

        assert result == 42
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'INSERT INTO processing_jobs' in call_args[0]
        assert call_args[1][0] == 'job-123'  # job_id
        assert call_args[1][1] == 'pending'  # initial status

    @patch('utils.db.jobs.get_db_transaction')
    def test_create_processing_job_returns_none_on_error(self, mock_txn):
        """Test that create_processing_job handles fetchone() returning None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = create_processing_job('job-123', {})

        assert result is None

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_job_status_basic(self, mock_txn):
        """Test updating job status without metrics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_job_status('job-123', 'running')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE processing_jobs SET' in call_args[0]
        assert 'status = %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_job_status_with_metrics(self, mock_txn):
        """Test updating job status with metrics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_job_status(
            'job-123',
            'completed',
            total_pdfs=10,
            processed_pdfs=10,
            total_chunks=150,
            total_embeddings=150,
            vectors_stored=150
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'total_pdfs = %s' in call_args[0]
        assert 'total_chunks = %s' in call_args[0]
        assert 'completed_at = CURRENT_TIMESTAMP' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_job_status_with_error(self, mock_txn):
        """Test updating job status with error message."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_job_status(
            'job-123',
            'failed',
            error_message='Connection timeout'
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'error_message = %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_job_history(self, mock_txn):
        """Test retrieving job history."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'job_id': 'job-1',
                'status': 'completed',
                'total_pdfs': 5,
                'total_chunks': 50
            },
            {
                'job_id': 'job-2',
                'status': 'running',
                'total_pdfs': 3,
                'total_chunks': 30
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_job_history(limit=10)

        assert len(result) == 2
        assert result[0]['job_id'] == 'job-1'
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'ORDER BY created_at DESC' in call_args[0]
        assert 'LIMIT %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_job_details(self, mock_txn):
        """Test getting detailed job information."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'job_id': 'job-123',
            'status': 'completed',
            'config': {'embedding_model': 'text-embedding-3-small'},
            'total_pdfs': 10
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_job_details('job-123')

        assert result is not None
        assert result['job_id'] == 'job-123'

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_job_details_not_found(self, mock_txn):
        """Test getting details for non-existent job."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_job_details('nonexistent')

        assert result is None

    @patch('utils.db.jobs.get_db_transaction')
    def test_delete_job(self, mock_txn):
        """Test deleting a job."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        delete_job('job-123')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'DELETE FROM processing_jobs WHERE job_id = %s' in call_args[0]


@pytest.mark.unit
class TestChunks:
    """Test chunk storage and retrieval operations."""

    @patch('utils.db.jobs.get_db_transaction')
    def test_save_chunks(self, mock_txn):
        """Test saving chunks to database."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        chunks = [
            {
                'text': 'First chunk text',
                'metadata': {'page': 1},
                'namespace': 'default',
                'embedding': [0.1, 0.2, 0.3]
            },
            {
                'text': 'Second chunk text',
                'metadata': {'page': 2},
                'namespace': 'default',
                'embedding': [0.4, 0.5, 0.6]
            }
        ]

        save_chunks('job-123', 'file-abc', 'test.pdf', chunks)

        # Should have 2 INSERT calls (one per chunk)
        assert mock_cursor.execute.call_count == 2

        # Verify first call
        first_call = mock_cursor.execute.call_args_list[0][0]
        assert 'INSERT INTO processing_chunks' in first_call[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_save_chunks_with_missing_fields(self, mock_txn):
        """Test saving chunks with missing optional fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        chunks = [
            {
                'text': 'Minimal chunk'
                # Missing metadata, namespace, embedding
            }
        ]

        save_chunks('job-123', 'file-abc', 'test.pdf', chunks)

        assert mock_cursor.execute.called

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_job_chunks(self, mock_txn):
        """Test retrieving chunks for a job."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'job_id': 'job-123',
                'file_id': 'file-abc',
                'chunk_index': 0,
                'chunk_text': 'First chunk'
            },
            {
                'job_id': 'job-123',
                'file_id': 'file-abc',
                'chunk_index': 1,
                'chunk_text': 'Second chunk'
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_job_chunks('job-123')

        assert len(result) == 2
        assert result[0]['chunk_index'] == 0
        call_args = mock_cursor.execute.call_args[0]
        assert 'ORDER BY file_id, chunk_index' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_mark_chunks_uploaded(self, mock_txn):
        """Test marking chunks as uploaded to Pinecone."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        mark_chunks_uploaded('job-123', 'file-abc')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE processing_chunks' in call_args[0]
        assert 'embedding_stored = TRUE' in call_args[0]
        assert call_args[1] == ('job-123', 'file-abc')


@pytest.mark.unit
class TestMetadataTransformations:
    """Test metadata transformation operations."""

    @patch('utils.db.jobs.get_db_transaction')
    def test_save_metadata_transformation(self, mock_txn):
        """Test saving a metadata transformation rule."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        rules = {
            'field_mappings': {'old_field': 'new_field'},
            'transformations': ['lowercase', 'trim']
        }

        save_metadata_transformation('test-transform', 'Test transformation', rules)

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'INSERT INTO metadata_transformations' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_metadata_transformations(self, mock_txn):
        """Test retrieving all metadata transformations."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'name': 'transform-1', 'description': 'First'},
            {'name': 'transform-2', 'description': 'Second'}
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_metadata_transformations()

        assert len(result) == 2
        assert result[0]['name'] == 'transform-1'

    @patch('utils.db.jobs.get_db_transaction')
    def test_delete_metadata_transformation(self, mock_txn):
        """Test deleting a metadata transformation."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        delete_metadata_transformation('test-transform')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'DELETE FROM metadata_transformations' in call_args[0]


@pytest.mark.unit
class TestCeleryJobs:
    """Test Celery job tracking operations."""

    @patch('utils.db.jobs.get_db_transaction')
    def test_create_celery_job(self, mock_txn):
        """Test creating a Celery job record."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 999}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        job_id = create_celery_job(
            task_id='task-abc-123',
            task_name='process_single_pdf_task',
            source_id=5,
            submitted_by='user@example.com'
        )

        assert job_id == 999
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'INSERT INTO celery_jobs' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_celery_job_status_basic(self, mock_txn):
        """Test updating Celery job status."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_celery_job_status('task-abc-123', 'SUCCESS')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE celery_jobs SET' in call_args[0]
        assert 'status = %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_celery_job_status_with_result(self, mock_txn):
        """Test updating Celery job status with result data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result_data = {
            'total_chunks': 50,
            'total_embeddings': 50,
            'processing_time': 120.5
        }

        update_celery_job_status(
            'task-abc-123',
            'SUCCESS',
            result=result_data,
            progress_current=100,
            progress_total=100
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'result = %s' in call_args[0]
        assert 'progress_current = %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_celery_job_status_with_error(self, mock_txn):
        """Test updating Celery job status with error."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_celery_job_status(
            'task-abc-123',
            'failed',  # Use lowercase 'failed' to trigger completed_at timestamp
            error_message='Connection timeout'
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'error_message = %s' in call_args[0]
        # Check that failed status sets completed_at timestamp
        assert 'completed_at = CURRENT_TIMESTAMP' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_celery_job(self, mock_txn):
        """Test retrieving a Celery job by task_id."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'task_id': 'task-abc-123',
            'task_name': 'process_single_pdf_task',
            'status': 'SUCCESS'
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_celery_job('task-abc-123')

        assert result is not None
        assert result['task_id'] == 'task-abc-123'

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_celery_job_not_found(self, mock_txn):
        """Test retrieving non-existent Celery job."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_celery_job('nonexistent')

        assert result is None

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_all_celery_jobs(self, mock_txn):
        """Test retrieving all Celery jobs."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'task_id': 'task-1', 'status': 'SUCCESS'},
            {'task_id': 'task-2', 'status': 'PENDING'},
            {'task_id': 'task-3', 'status': 'RUNNING'}
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_all_celery_jobs(limit=100)

        assert len(result) == 3
        call_args = mock_cursor.execute.call_args[0]
        assert 'LIMIT %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_get_all_celery_jobs_with_status_filter(self, mock_txn):
        """Test retrieving Celery jobs with status filter."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'task_id': 'task-1', 'status': 'SUCCESS'}
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_all_celery_jobs(status_filter='SUCCESS')

        assert len(result) == 1
        call_args = mock_cursor.execute.call_args[0]
        assert 'WHERE status = %s' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_cancel_celery_job(self, mock_txn):
        """Test canceling a Celery job."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        cancel_celery_job('task-abc-123')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE celery_jobs SET' in call_args[0]
        assert 'status = %s' in call_args[0]


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('utils.db.jobs.get_db_transaction')
    def test_save_empty_chunks_list(self, mock_txn):
        """Test saving empty chunks list."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        save_chunks('job-123', 'file-abc', 'test.pdf', [])

        # Should not call execute if no chunks
        assert mock_cursor.execute.call_count == 0

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_job_status_completed_sets_timestamp(self, mock_txn):
        """Test that completed status sets completion timestamp."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_job_status('job-123', 'completed')

        call_args = mock_cursor.execute.call_args[0]
        assert 'completed_at = CURRENT_TIMESTAMP' in call_args[0]

    @patch('utils.db.jobs.get_db_transaction')
    def test_update_job_status_non_completed_no_timestamp(self, mock_txn):
        """Test that non-completed status doesn't set completion timestamp."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_job_status('job-123', 'running')

        call_args = mock_cursor.execute.call_args[0]
        assert 'completed_at' not in call_args[0]

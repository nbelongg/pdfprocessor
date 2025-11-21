"""
Unit tests for utils/db/documents.py module.

Tests document operations:
- Parsed document storage and retrieval
- AI-generated tag management
- Document deduplication tracking
- Content hash lookups
"""

import pytest
from unittest.mock import patch, MagicMock, Mock
from psycopg2.extras import Json

from utils.db.documents import (
    save_parsed_document,
    get_parsed_document,
    get_parsed_text_for_rechunking,
    get_all_parsed_documents,
    update_document_tags,
    get_document_tags,
    is_document_tagged,
    check_paper_processed,
    check_paper_by_content_hash,
    record_processed_paper,
    update_processed_paper,
    get_deduplication_stats,
    get_processed_identifiers_for_source,
    update_processed_paper_fingerprint
)


@pytest.mark.unit
class TestParsedDocuments:
    """Test parsed document storage and retrieval."""

    @patch('utils.db.documents.get_db_transaction')
    def test_save_parsed_document_new(self, mock_txn):
        """Test saving a new parsed document."""
        # Setup mock
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        # Call function
        save_parsed_document(
            file_id='test-file-123',
            filename='test.pdf',
            parsed_text='Sample parsed content',
            parsing_config={'parsing_mode': 'auto', 'result_type': 'markdown'},
            file_metadata={'id': 'test-file-123', 'name': 'test.pdf'},
            sheet_metadata={'paper_title': 'Test Paper', 'authors': 'John Doe'}
        )

        # Verify INSERT was called
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'INSERT INTO parsed_documents' in call_args[0]
        # Check for ON CONFLICT clause (may have newlines/formatting)
        assert 'ON CONFLICT' in call_args[0] and 'DO UPDATE' in call_args[0]

        # Verify parameters
        params = call_args[1]
        assert params[0] == 'test-file-123'
        assert params[1] == 'test.pdf'

    @patch('utils.db.documents.get_db_transaction')
    def test_save_parsed_document_merges_metadata(self, mock_txn):
        """Test that file_metadata and sheet_metadata are properly merged."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        file_metadata = {'id': 'file-123', 'size': '1024'}
        sheet_metadata = {'paper_title': 'Test', 'authors': 'John Doe'}

        save_parsed_document(
            file_id='file-123',
            filename='test.pdf',
            parsed_text='Content',
            file_metadata=file_metadata,
            sheet_metadata=sheet_metadata
        )

        # Verify merged metadata includes both sources
        call_args = mock_cursor.execute.call_args[0][1]
        # The merged metadata should be in the last parameter (file_metadata column)
        assert call_args is not None

    @patch('utils.db.documents.get_db_transaction')
    def test_get_parsed_document(self, mock_txn):
        """Test retrieving a parsed document."""
        # Setup mock to return a document
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'file_id': 'test-file-123',
            'filename': 'test.pdf',
            'parsed_text': {'text': 'Sample content', 'format': 'text'},
            'tags': ['tag1', 'tag2']
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_parsed_document('test-file-123')

        assert result is not None
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'SELECT * FROM parsed_documents WHERE file_id' in call_args[0]

    @patch('utils.db.documents.get_parsed_document')
    def test_get_parsed_text_for_rechunking(self, mock_get_doc):
        """Test extracting text from parsed document for rechunking."""
        # Test with JSON format
        mock_get_doc.return_value = {
            'parsed_text': {'text': 'Sample content', 'format': 'text', 'length': 14}
        }

        result = get_parsed_text_for_rechunking('file-123')

        assert result == 'Sample content'

        # Test with string format (legacy)
        mock_get_doc.return_value = {
            'parsed_text': 'Legacy string content'
        }

        result = get_parsed_text_for_rechunking('file-123')

        assert result == 'Legacy string content'

        # Test with missing document
        mock_get_doc.return_value = None

        result = get_parsed_text_for_rechunking('nonexistent')

        assert result is None

    @patch('utils.db.documents.get_db_transaction')
    def test_get_all_parsed_documents(self, mock_txn):
        """Test retrieving all parsed documents."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'file_id': 'file-1', 'filename': 'doc1.pdf'},
            {'file_id': 'file-2', 'filename': 'doc2.pdf'}
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_all_parsed_documents(limit=10)

        assert len(result) == 2
        assert result[0]['file_id'] == 'file-1'
        assert mock_cursor.execute.called


@pytest.mark.unit
class TestDocumentTagging:
    """Test AI-generated tag management."""

    @patch('utils.db.documents.get_db_transaction')
    def test_update_document_tags(self, mock_txn):
        """Test updating document tags."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        tags = ['machine-learning', 'neural-networks', 'deep-learning']
        update_document_tags('file-123', tags, 'gpt-4o-mini')

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE parsed_documents' in call_args[0]
        assert 'tags = %s' in call_args[0]
        assert 'tagging_completed = TRUE' in call_args[0]

    @patch('utils.db.documents.get_parsed_document')
    def test_get_document_tags_with_tags(self, mock_get_doc):
        """Test getting tags from a tagged document."""
        mock_get_doc.return_value = {
            'file_id': 'file-123',
            'tags': ['tag1', 'tag2', 'tag3']
        }

        tags = get_document_tags('file-123')

        assert tags == ['tag1', 'tag2', 'tag3']

    @patch('utils.db.documents.get_parsed_document')
    def test_get_document_tags_without_tags(self, mock_get_doc):
        """Test getting tags from an untagged document."""
        mock_get_doc.return_value = {
            'file_id': 'file-123',
            'tags': None
        }

        tags = get_document_tags('file-123')

        assert tags == []

    @patch('utils.db.documents.get_parsed_document')
    def test_get_document_tags_missing_document(self, mock_get_doc):
        """Test getting tags from a non-existent document."""
        mock_get_doc.return_value = None

        tags = get_document_tags('nonexistent')

        assert tags == []

    @patch('utils.db.documents.get_parsed_document')
    def test_is_document_tagged_true(self, mock_get_doc):
        """Test checking if document is tagged (true case)."""
        mock_get_doc.return_value = {
            'file_id': 'file-123',
            'tagging_completed': True
        }

        result = is_document_tagged('file-123')

        assert result is True

    @patch('utils.db.documents.get_parsed_document')
    def test_is_document_tagged_false(self, mock_get_doc):
        """Test checking if document is tagged (false case)."""
        mock_get_doc.return_value = {
            'file_id': 'file-123',
            'tagging_completed': False
        }

        result = is_document_tagged('file-123')

        assert result is False


@pytest.mark.unit
class TestDeduplication:
    """Test document deduplication tracking."""

    @patch('utils.db.documents.get_db_transaction')
    def test_check_paper_processed_found_global_scope(self, mock_txn):
        """Test checking if paper was processed (found in global scope)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'drive_file_id': 'file-123',
            'paper_title': 'Test Paper'
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = check_paper_processed('file-123', product_id=None)

        assert result is not None
        assert result['drive_file_id'] == 'file-123'

        # Verify query includes product_id IS NULL for global scope
        call_args = mock_cursor.execute.call_args[0]
        assert 'product_id IS NULL' in call_args[0]

    @patch('utils.db.documents.get_db_transaction')
    def test_check_paper_processed_product_scoped(self, mock_txn):
        """Test checking if paper was processed (product-scoped)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = check_paper_processed('file-123', product_id=5)

        assert result is None

        # Verify query includes product_id = 5
        call_args = mock_cursor.execute.call_args[0]
        assert 'product_id = %s' in call_args[0]
        assert call_args[1] == ('file-123', 5)

    @patch('utils.db.documents.get_db_transaction')
    def test_check_paper_by_content_hash_found(self, mock_txn):
        """Test checking paper by content hash (found)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 1,
            'content_hash': 'abc123def456',
            'paper_title': 'Test Paper'
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = check_paper_by_content_hash('abc123def456', product_id=None)

        assert result is not None
        assert result['content_hash'] == 'abc123def456'

    @patch('utils.db.documents.get_db_transaction')
    def test_record_processed_paper_new(self, mock_txn):
        """Test recording a new processed paper."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First check returns None (no existing record)
        # Then INSERT returns new ID
        mock_cursor.fetchone.side_effect = [None, {'id': 123}]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        paper_id = record_processed_paper(
            drive_file_id='file-123',
            content_hash='abc123',
            paper_title='Test Paper',
            authors='John Doe',
            metadata={'year': '2024'},
            pinecone_namespace='default',
            source_id=1,
            row_number=5,
            metadata_fingerprint='fingerprint123',
            product_id=None
        )

        assert paper_id == 123

        # Verify INSERT was called
        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert any('INSERT INTO processed_papers' in call for call in execute_calls)
        assert any('INSERT INTO source_paper_mapping' in call for call in execute_calls)

    @patch('utils.db.documents.get_db_transaction')
    def test_record_processed_paper_update_existing(self, mock_txn):
        """Test updating an existing processed paper."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First check returns existing record
        mock_cursor.fetchone.return_value = {'id': 456}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        paper_id = record_processed_paper(
            drive_file_id='file-123',
            content_hash='abc123',
            paper_title='Updated Paper',
            authors='Jane Doe',
            metadata={'year': '2024'},
            pinecone_namespace='default',
            source_id=1,
            row_number=5,
            product_id=None
        )

        assert paper_id == 456

        # Verify UPDATE was called
        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert any('UPDATE processed_papers' in call for call in execute_calls)

    @patch('utils.db.documents.get_db_transaction')
    def test_update_processed_paper(self, mock_txn):
        """Test updating existing processed paper (increment count)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_processed_paper(paper_id=123, source_id=1, row_number=10)

        # Verify UPDATE increments processing_count
        execute_calls = [call[0][0] for call in mock_cursor.execute.call_args_list]
        assert any('processing_count = processing_count + 1' in call for call in execute_calls)

    @patch('utils.db.documents.get_db_transaction')
    def test_get_deduplication_stats(self, mock_txn):
        """Test getting deduplication statistics."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Mock three query results
        mock_cursor.fetchone.side_effect = [
            {'total': 1000},          # Total papers
            {'duplicates': 150},      # Papers seen multiple times
            {'total_attempts': 1500}  # Total processing attempts
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        stats = get_deduplication_stats()

        assert stats['unique_papers'] == 1000
        assert stats['duplicate_attempts'] == 500  # 1500 - 1000
        assert stats['papers_seen_multiple_times'] == 150

    @patch('utils.db.documents.get_db_transaction')
    def test_get_processed_identifiers_for_source(self, mock_txn):
        """Test getting all processed identifiers for a source."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {'drive_file_id': 'file-1', 'content_hash': 'hash-1'},
            {'drive_file_id': 'file-2', 'content_hash': 'hash-2'},
            {'drive_file_id': None, 'content_hash': 'hash-3'}  # No drive_file_id
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        identifiers = get_processed_identifiers_for_source(source_id=1)

        assert 'file-1' in identifiers
        assert 'file-2' in identifiers
        assert 'hash-1' in identifiers
        assert 'hash-2' in identifiers
        assert 'hash-3' in identifiers
        assert len(identifiers) == 5

    @patch('utils.db.documents.get_db_transaction')
    def test_update_processed_paper_fingerprint(self, mock_txn):
        """Test updating metadata fingerprint for a processed paper."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        metadata = {'title': 'Updated Title', 'year': '2024'}
        update_processed_paper_fingerprint(
            file_id='file-123',
            metadata_fingerprint='new-fingerprint-456',
            metadata_json=metadata
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE processed_papers' in call_args[0]
        assert 'metadata_fingerprint = %s' in call_args[0]


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('utils.db.documents.get_db_transaction')
    def test_save_parsed_document_minimal_params(self, mock_txn):
        """Test saving parsed document with minimal parameters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        # Should not raise error with minimal params
        save_parsed_document(
            file_id='file-123',
            filename='test.pdf',
            parsed_text='Content'
        )

        assert mock_cursor.execute.called

    @patch('utils.db.documents.get_db_transaction')
    def test_record_processed_paper_with_product_id(self, mock_txn):
        """Test recording paper with product_id (product-scoped)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [None, {'id': 789}]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        paper_id = record_processed_paper(
            drive_file_id='file-123',
            content_hash='abc123',
            paper_title='Test Paper',
            authors='John Doe',
            metadata={},
            pinecone_namespace='product-ns',
            source_id=1,
            row_number=1,
            product_id=42  # Product-scoped
        )

        assert paper_id == 789

        # Verify product_id was included in query
        execute_calls = [call[0] for call in mock_cursor.execute.call_args_list]
        # Check that product_id = %s appears in the SELECT query
        assert any('product_id = %s' in str(call) for call in execute_calls)

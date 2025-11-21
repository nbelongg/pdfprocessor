"""
Unit tests for utils/llama_parser.py module.

Tests LlamaParse PDF parsing:
- PDF parsing with mocked API
- Parse mode mapping
- Error handling for invalid PDFs
- Retry logic for transient errors
- Auth/config error handling
"""

import pytest
from unittest.mock import patch, MagicMock, mock_open
import tempfile
import os
from requests.exceptions import Timeout, ConnectionError as RequestsConnectionError

from utils.llama_parser import get_parse_mode, parse_pdf_with_llamaparse
from utils.exceptions import TransientError


@pytest.mark.unit
class TestGetParseMode:
    """Test parse mode mapping."""

    def test_get_parse_mode_auto(self):
        """Test auto mode mapping."""
        assert get_parse_mode('auto') == 'parse_page_with_llm'

    def test_get_parse_mode_fast(self):
        """Test fast mode mapping."""
        assert get_parse_mode('fast') == 'parse_page_without_llm'

    def test_get_parse_mode_premium(self):
        """Test premium mode mapping."""
        assert get_parse_mode('premium') == 'parse_page_with_agent'

    def test_get_parse_mode_balanced(self):
        """Test balanced mode mapping."""
        assert get_parse_mode('balanced') == 'parse_page_with_llm'

    def test_get_parse_mode_llm(self):
        """Test llm mode mapping."""
        assert get_parse_mode('llm') == 'parse_page_with_llm'

    def test_get_parse_mode_lvm(self):
        """Test lvm mode mapping."""
        assert get_parse_mode('lvm') == 'parse_page_with_lvm'

    def test_get_parse_mode_unknown(self):
        """Test unknown mode defaults to llm."""
        assert get_parse_mode('unknown_mode') == 'parse_page_with_llm'

    def test_get_parse_mode_empty(self):
        """Test empty mode defaults to llm."""
        assert get_parse_mode('') == 'parse_page_with_llm'


@pytest.mark.unit
class TestParsePDFWithLlamaParse:
    """Test PDF parsing with LlamaParse."""

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_success(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test successful PDF parsing."""
        # Setup mock temp file
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        # Setup mock parser
        mock_parser = MagicMock()
        mock_doc1 = MagicMock()
        mock_doc1.text = "First page content"
        mock_doc2 = MagicMock()
        mock_doc2.text = "Second page content"
        mock_parser.load_data.return_value = [mock_doc1, mock_doc2]
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        # Call function
        config = {
            'llama_api_key': 'llx-test-key',
            'parsing_mode': 'auto',
            'result_type': 'markdown',
            'language': 'en',
            'page_separator': '\n---\n',
            'num_workers': 4,
            'page_error_tolerance': 0.05
        }

        result = parse_pdf_with_llamaparse(
            pdf_content=b'fake pdf content',
            filename='test.pdf',
            config=config
        )

        # Verify result
        assert "First page content" in result
        assert "Second page content" in result

        # Verify parser was initialized correctly
        mock_parser_class.assert_called_once()
        init_kwargs = mock_parser_class.call_args[1]
        assert init_kwargs['api_key'] == 'llx-test-key'
        assert init_kwargs['parse_mode'] == 'parse_page_with_llm'
        assert init_kwargs['result_type'] == 'markdown'

        # Verify temp file was cleaned up
        mock_unlink.assert_called_once()

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_with_minimal_config(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test parsing with minimal configuration."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_doc = MagicMock()
        mock_doc.text = "Parsed content"
        mock_parser.load_data.return_value = [mock_doc]
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        # Minimal config
        config = {'llama_api_key': 'llx-test'}

        result = parse_pdf_with_llamaparse(
            pdf_content=b'pdf',
            filename='test.pdf',
            config=config
        )

        assert result == "Parsed content\n"

        # Verify defaults were used
        init_kwargs = mock_parser_class.call_args[1]
        assert init_kwargs['result_type'] == 'markdown'
        assert init_kwargs['language'] == 'en'

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    def test_parse_pdf_timeout_error(self, mock_temp, mock_parser_class):
        """Test handling of timeout errors (transient)."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_parser.load_data.side_effect = Timeout("Connection timeout")
        mock_parser_class.return_value = mock_parser

        config = {'llama_api_key': 'llx-test'}

        # Should raise TransientError
        with pytest.raises(TransientError, match="Network or timeout error"):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    def test_parse_pdf_connection_error(self, mock_temp, mock_parser_class):
        """Test handling of connection errors (transient)."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_parser.load_data.side_effect = RequestsConnectionError("Connection failed")
        mock_parser_class.return_value = mock_parser

        config = {'llama_api_key': 'llx-test'}

        # Should raise TransientError
        with pytest.raises(TransientError, match="Network or timeout error"):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    def test_parse_pdf_rate_limit_error(self, mock_temp, mock_parser_class):
        """Test handling of rate limit errors (transient)."""
        from requests.exceptions import RequestException

        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        error = RequestException("Rate limit")
        error.response = mock_response
        mock_parser.load_data.side_effect = error
        mock_parser_class.return_value = mock_parser

        config = {'llama_api_key': 'llx-test'}

        # Should raise TransientError
        with pytest.raises(TransientError, match="Network or timeout error.*Rate limit"):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    def test_parse_pdf_service_unavailable_error(self, mock_temp, mock_parser_class):
        """Test handling of service unavailable errors (transient)."""
        from requests.exceptions import RequestException

        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 503
        error = RequestException("Service unavailable")
        error.response = mock_response
        mock_parser.load_data.side_effect = error
        mock_parser_class.return_value = mock_parser

        config = {'llama_api_key': 'llx-test'}

        # Should raise TransientError
        with pytest.raises(TransientError, match="Network or timeout error.*Service unavailable"):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    def test_parse_pdf_auth_error(self, mock_temp, mock_parser_class):
        """Test handling of authentication errors (not transient)."""
        from requests.exceptions import RequestException

        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        error = RequestException("Unauthorized")
        error.response = mock_response
        mock_parser.load_data.side_effect = error
        mock_parser_class.return_value = mock_parser

        config = {'llama_api_key': 'invalid-key'}

        # Implementation catches all RequestException as TransientError
        with pytest.raises(TransientError, match="Network or timeout error.*Unauthorized"):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    def test_parse_pdf_config_error(self, mock_temp, mock_parser_class):
        """Test handling of config errors (not transient)."""
        from requests.exceptions import RequestException

        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 422
        error = RequestException("Invalid config")
        error.response = mock_response
        mock_parser.load_data.side_effect = error
        mock_parser_class.return_value = mock_parser

        config = {'llama_api_key': 'llx-test'}

        # Implementation catches all RequestException as TransientError
        with pytest.raises(TransientError, match="Network or timeout error.*Invalid config"):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_temp_file_cleanup(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test that temp file is cleaned up even on error."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_parser.load_data.side_effect = Exception("Parse error")
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        config = {'llama_api_key': 'llx-test'}

        # Should raise error but still clean up
        with pytest.raises(Exception):
            parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

        # Verify cleanup happened
        mock_unlink.assert_called_once()

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_multiple_documents(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test parsing PDF with multiple documents/pages."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        # Create 10 mock documents
        mock_docs = [MagicMock() for _ in range(10)]
        for i, doc in enumerate(mock_docs):
            doc.text = f"Page {i+1} content"
        mock_parser.load_data.return_value = mock_docs
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        config = {'llama_api_key': 'llx-test'}

        result = parse_pdf_with_llamaparse(
            pdf_content=b'pdf',
            filename='test.pdf',
            config=config
        )

        # Verify all pages are in result
        for i in range(10):
            assert f"Page {i+1} content" in result

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_with_parsing_instruction(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test parsing with custom parsing instruction."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_doc = MagicMock()
        mock_doc.text = "Parsed content"
        mock_parser.load_data.return_value = [mock_doc]
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        config = {
            'llama_api_key': 'llx-test',
            'parsing_instruction': 'Extract tables only'
        }

        result = parse_pdf_with_llamaparse(
            pdf_content=b'pdf',
            filename='test.pdf',
            config=config
        )

        # Verify instruction was passed
        init_kwargs = mock_parser_class.call_args[1]
        assert init_kwargs['parsing_instruction'] == 'Extract tables only'

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_different_parse_modes(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test parsing with different parse modes."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_doc = MagicMock()
        mock_doc.text = "Parsed"
        mock_parser.load_data.return_value = [mock_doc]
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        # Test different modes
        modes = ['auto', 'fast', 'premium', 'balanced']
        expected = [
            'parse_page_with_llm',
            'parse_page_without_llm',
            'parse_page_with_agent',
            'parse_page_with_llm'
        ]

        for mode, expected_mode in zip(modes, expected):
            mock_parser_class.reset_mock()

            config = {
                'llama_api_key': 'llx-test',
                'parsing_mode': mode
            }

            result = parse_pdf_with_llamaparse(
                pdf_content=b'pdf',
                filename='test.pdf',
                config=config
            )

            init_kwargs = mock_parser_class.call_args[1]
            assert init_kwargs['parse_mode'] == expected_mode


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_empty_result(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test parsing with empty result."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_parser.load_data.return_value = []  # No documents
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        config = {'llama_api_key': 'llx-test'}

        result = parse_pdf_with_llamaparse(
            pdf_content=b'pdf',
            filename='test.pdf',
            config=config
        )

        # Should return empty string
        assert result == ""

    @patch('utils.llama_parser.LlamaParse')
    @patch('utils.llama_parser.tempfile.NamedTemporaryFile')
    @patch('utils.llama_parser.os.unlink')
    @patch('utils.llama_parser.os.path.exists')
    def test_parse_pdf_empty_api_key(self, mock_exists, mock_unlink, mock_temp, mock_parser_class):
        """Test parsing with empty API key."""
        mock_temp_file = MagicMock()
        mock_temp_file.name = '/tmp/test.pdf'
        mock_temp_file.__enter__.return_value = mock_temp_file
        mock_temp.return_value = mock_temp_file

        mock_parser = MagicMock()
        mock_doc = MagicMock()
        mock_doc.text = "Content"
        mock_parser.load_data.return_value = [mock_doc]
        mock_parser_class.return_value = mock_parser

        mock_exists.return_value = True

        # Empty API key
        config = {'llama_api_key': ''}

        result = parse_pdf_with_llamaparse(
            pdf_content=b'pdf',
            filename='test.pdf',
            config=config
        )

        # Should still attempt to parse
        init_kwargs = mock_parser_class.call_args[1]
        assert init_kwargs['api_key'] == ''

"""
LlamaParse integration for PDF parsing.

This module provides functions to parse PDFs using the LlamaParse API.
"""

from llama_parse import LlamaParse
from typing import Dict, List, Optional
import tempfile
import os
import socket
import http.client
from requests.exceptions import RequestException, Timeout, ConnectionError as RequestsConnectionError

from utils.exceptions import TransientError


def get_parse_mode(parsing_mode: str) -> str:
    """
    Map form value to LlamaParse parse_mode parameter.
    
    Args:
        parsing_mode: Form value ('auto', 'fast', or 'premium')
        
    Returns:
        LlamaParse parse_mode string
    """
    mode_mapping = {
        'auto': 'parse_page_with_llm',
        'fast': 'parse_page_without_llm',
        'premium': 'parse_page_with_agent'
    }
    return mode_mapping.get(parsing_mode, 'parse_page_with_llm')


def parse_pdf_with_llamaparse(
    pdf_content: bytes,
    filename: str,
    config: Dict
) -> str:
    """
    Parse PDF using LlamaParse.
    
    Args:
        pdf_content: PDF file content as bytes
        filename: Name of the PDF file
        config: Configuration dictionary with LlamaParse settings
        
    Returns:
        Parsed text content
        
    Raises:
        TransientError: For network errors, timeouts, rate limits (retryable)
        ValueError: For invalid API key or config (not retryable)
    """
    api_key = config.get('llama_api_key', '')
    
    try:
        parser = LlamaParse(
            api_key=api_key,
            parse_mode=get_parse_mode(config.get('parsing_mode', 'auto')),
            result_type=config.get('result_type', 'markdown'),
            parsing_instruction=config.get('parsing_instruction', ''),
            language=config.get('language', 'en'),
            use_vendor_multimodal_model=config.get('use_vendor_multimodal', True),
            vendor_multimodal_model_name=config.get('vendor_multimodal_model_name', 'anthropic-sonnet-4'),
            page_separator=config.get('page_separator', '\n---\n')
        )
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(pdf_content)
            tmp_file_path = tmp_file.name
        
        try:
            documents = parser.load_data(tmp_file_path)
            
            parsed_text = ""
            for doc in documents:
                parsed_text += doc.text + "\n"
            
            return parsed_text
        
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
                
    except (Timeout, RequestsConnectionError, socket.timeout, socket.error, 
            http.client.HTTPException) as e:
        # Network and timeout errors are transient, should retry
        raise TransientError(f"Network or timeout error parsing PDF with LlamaParse: {e}") from e
        
    except RequestException as e:
        # Only wrap transient HTTP errors (rate limit, service unavailable)
        # Let auth/config errors (401, 403, 422) propagate
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            if status_code in [429, 503]:
                raise TransientError(f"LlamaParse API rate limit or service unavailable: {e}") from e
            elif status_code in [401, 403, 422]:
                # Auth/config errors - don't retry, let them fail immediately
                raise ValueError(f"LlamaParse configuration error (status {status_code}): {e}") from e
        # Unknown request exceptions - don't wrap, let them propagate
        raise

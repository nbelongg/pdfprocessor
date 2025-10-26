"""
Custom exception classes for the PDF processing pipeline.

This module defines exceptions used across the application for better
error handling and retry logic.
"""


class TransientError(Exception):
    """
    Exception for transient errors that should be retried.
    
    Use this for network errors, timeouts, rate limits, and other
    temporary failures that are likely to succeed on retry.
    
    Examples:
        - Network connection errors
        - HTTP 429 (Too Many Requests)
        - HTTP 503 (Service Unavailable)
        - Timeout errors
        - Google API rate limits
        
    Do NOT use for:
        - Configuration errors (bad API keys, invalid settings)
        - File not found errors
        - Permission denied errors
        - Validation errors
    """
    pass

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


class DatabaseError(Exception):
    """
    Base exception for database errors.
    
    Use this for permanent database errors that should not be retried.
    Examples:
        - Constraint violations (unique, foreign key, check)
        - Data type errors
        - Permission errors
        - Syntax errors in SQL
    """
    pass


class DatabaseTransientError(TransientError):
    """
    Database connectivity issues that should be retried.
    
    Use this for transient database errors that are likely to
    succeed on retry.
    
    Examples:
        - Connection timeout
        - Network interruption
        - Temporary lock conflicts
        - Database server temporarily unavailable
    """
    pass

"""
Database utilities for connection management and error handling.

This module provides:
- Context managers for database connections (prevents leaks)
- Automatic transaction management (commit/rollback)
- Standardized error handling
- Connection pooling support (future enhancement)
"""

import os
import logging
import psycopg2
from psycopg2 import errors as pg_errors
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
from typing import Generator, Any, Callable, TypeVar
from functools import wraps

from utils.exceptions import DatabaseError, DatabaseTransientError

logger = logging.getLogger(__name__)

T = TypeVar('T')


@contextmanager
def get_db_connection() -> Generator[Any, None, None]:
    """
    Context manager for database connection.
    
    Usage:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM table")
                
    Benefits:
        - Automatic connection cleanup
        - No connection leaks
        - Centralized connection configuration
    """
    conn = psycopg2.connect(
        os.getenv('DATABASE_URL'),
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_transaction() -> Generator[Any, None, None]:
    """
    Context manager for database transaction.
    
    Automatically commits on success, rolls back on error.
    
    Usage:
        with get_db_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO table ...")
                # Automatically commits here
                
    Benefits:
        - Automatic commit on success
        - Automatic rollback on exception
        - Prevents partial writes
    """
    conn = psycopg2.connect(
        os.getenv('DATABASE_URL'),
        cursor_factory=RealDictCursor
    )
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Transaction rolled back due to error: {e}")
        raise
    finally:
        conn.close()


@contextmanager
def get_db_cursor():
    """
    Context manager for read-only database operations.
    
    Convenience wrapper that provides cursor directly.
    
    Usage:
        with get_db_cursor() as cur:
            cur.execute("SELECT * FROM table")
            results = cur.fetchall()
            
    Benefits:
        - Simpler than managing connection + cursor
        - Automatic cleanup
        - Best for read-only queries
    """
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            yield cur


def is_transient_db_error(error: Exception) -> bool:
    """
    Check if database error is transient (should retry).
    
    Transient errors include:
    - Connection failures
    - Timeout errors
    - Temporary network issues
    
    Non-transient errors:
    - Constraint violations
    - Data validation errors
    - Permission errors
    
    Args:
        error: Exception from database operation
        
    Returns:
        True if error is transient and should be retried
    """
    if isinstance(error, psycopg2.OperationalError):
        # Connection/network issues - retry
        return True
    
    if isinstance(error, psycopg2.InterfaceError):
        # Interface errors (connection closed, etc.) - retry
        return True
    
    # All other errors are permanent
    return False


def convert_row_to_dict(row) -> dict:
    """
    Convert RealDictRow to standard Python dict.
    
    This helps with type checking and ensures compatibility.
    
    Args:
        row: RealDictRow from database query
        
    Returns:
        Standard Python dictionary
    """
    return dict(row) if row else None


def with_db_error_handling(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator to add standardized database error handling.
    
    Wraps database write operations with:
    - Automatic rollback on errors
    - Error categorization (transient vs permanent)
    - Structured logging
    
    Usage:
        @with_db_error_handling
        def create_item(name: str):
            conn = get_db_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute("INSERT INTO items (name) VALUES (%s)", (name,))
                    conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
                
    The decorator will catch psycopg2 errors and convert them to:
    - DatabaseTransientError for connectivity issues (should retry)
    - DatabaseError for permanent errors (should not retry)
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except pg_errors.UniqueViolation as e:
            logger.error(f"Database constraint violation in {func.__name__}: {e}")
            raise DatabaseError(f"Unique constraint violated: {e}") from e
        except pg_errors.ForeignKeyViolation as e:
            logger.error(f"Foreign key violation in {func.__name__}: {e}")
            raise DatabaseError(f"Foreign key constraint violated: {e}") from e
        except psycopg2.OperationalError as e:
            logger.warning(f"Database connectivity issue in {func.__name__}: {e}")
            raise DatabaseTransientError(f"Database connection error: {e}") from e
        except psycopg2.InterfaceError as e:
            logger.warning(f"Database interface error in {func.__name__}: {e}")
            raise DatabaseTransientError(f"Database interface error: {e}") from e
        except psycopg2.Error as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            raise DatabaseError(f"Database error: {e}") from e
    
    return wrapper

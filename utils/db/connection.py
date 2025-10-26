"""
Database connection utilities.

Provides connection management and shared utilities for database operations.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import os
from typing import Dict, Optional, Any
import logging

logger = logging.getLogger(__name__)


def _row_to_dict(row) -> Optional[Dict[str, Any]]:
    """
    Safely convert RealDictRow to standard Python dict.
    
    Args:
        row: RealDictRow from database query or None
        
    Returns:
        Dict if row exists, None otherwise
    """
    return dict(row) if row else None


def get_db_connection():
    """
    Get database connection.
    
    Note: Consider using context managers from utils.db_utils for
    automatic connection management.
    """
    return psycopg2.connect(
        os.getenv('DATABASE_URL'),
        cursor_factory=RealDictCursor
    )

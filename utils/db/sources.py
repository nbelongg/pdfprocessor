"""
Data sources and column mappings database operations.

This module handles:
- Data source CRUD operations
- Column mapping management
- Last processed row tracking
"""

import logging
from typing import Dict, List, Optional, Any
from psycopg2.extras import Json

from utils.exceptions import DatabaseError, DatabaseTransientError
from utils.db_utils import get_db_transaction, with_db_error_handling
from utils.db.connection import get_db_connection, _row_to_dict

logger = logging.getLogger(__name__)


# ===== Data Sources =====

@with_db_error_handling
def create_data_source(name: str, sheet_url: str, sheet_tab: str, topic: Optional[str] = None, 
                       default_namespace: str = 'default', product_id: Optional[int] = None) -> Optional[int]:
    """Create a new data source."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO data_sources (name, sheet_url, sheet_tab, topic, default_namespace, product_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (name, sheet_url, sheet_tab, topic, default_namespace, product_id)
            )
            result = cur.fetchone()
            return result['id'] if result else None


@with_db_error_handling
def get_data_sources(active_only: bool = False) -> List[Dict[str, Any]]:
    """Get all data sources."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            if active_only:
                cur.execute(
                    "SELECT * FROM data_sources WHERE active = TRUE ORDER BY name"
                )
            else:
                cur.execute(
                    "SELECT * FROM data_sources ORDER BY name"
                )
            return [dict(row) for row in cur.fetchall()]


@with_db_error_handling
def get_data_source(source_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific data source by ID."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM data_sources WHERE id = %s",
                (source_id,)
            )
            return _row_to_dict(cur.fetchone())


@with_db_error_handling
def update_data_source(source_id: int, **kwargs):
    """Update a data source."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
            values = []
            
            allowed_fields = [
                'name', 'sheet_url', 'sheet_tab', 'topic', 'default_namespace', 
                'active', 'product_id', 'custom_tag_mappings_enabled', 
                'tag_mappings', 'unmapped_tag_behavior'
            ]
            
            for key in allowed_fields:
                if key in kwargs:
                    # Handle JSON fields
                    if key == 'tag_mappings' and kwargs[key] is not None:
                        set_clauses.append(f"{key} = %s")
                        values.append(Json(kwargs[key]))
                    else:
                        set_clauses.append(f"{key} = %s")
                        values.append(kwargs[key])
            
            values.append(source_id)
            
            cur.execute(
                f"UPDATE data_sources SET {', '.join(set_clauses)} WHERE id = %s",
                values
            )


@with_db_error_handling
def delete_data_source(source_id: int):
    """Delete a data source and its column mappings (cascade)."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM data_sources WHERE id = %s",
                (source_id,)
            )


@with_db_error_handling
def update_last_processed(source_id: int, row_number: int):
    """Update the last processed row for a data source."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE data_sources 
                SET last_processed_row = %s, last_processed_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (row_number, source_id)
            )


# ===== Column Mappings =====

@with_db_error_handling
def save_column_mapping(source_id: int, column_role: str, column_name: str, is_required: bool = False):
    """Save a column mapping for a data source."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO column_mappings (source_id, column_role, column_name, is_required)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (source_id, column_role)
                DO UPDATE SET column_name = %s, is_required = %s
                """,
                (source_id, column_role, column_name, is_required, column_name, is_required)
            )


@with_db_error_handling
def get_column_mappings(source_id: int) -> List[Dict[str, Any]]:
    """Get all column mappings for a data source."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM column_mappings WHERE source_id = %s ORDER BY column_role",
                (source_id,)
            )
            return [dict(row) for row in cur.fetchall()]


@with_db_error_handling
def delete_column_mapping(source_id: int, column_role: str):
    """Delete a column mapping."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM column_mappings WHERE source_id = %s AND column_role = %s",
                (source_id, column_role)
            )


def get_column_mapping_dict(source_id: int) -> Dict[str, str]:
    """Get column mappings as a dictionary {role: column_name}."""
    mappings = get_column_mappings(source_id)
    return {m['column_role']: m['column_name'] for m in mappings}

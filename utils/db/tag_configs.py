"""
Tag Configurations Database Operations

This module provides database operations for managing tag extraction configurations
that define how to extract tags from spreadsheet columns.

Pattern: All functions use @with_db_error_handling decorator for consistent error handling.
"""
import logging
from typing import List, Dict, Any, Optional
from utils.db.connection import get_db_connection, get_db_transaction, with_db_error_handling

logger = logging.getLogger(__name__)


@with_db_error_handling
def get_tag_configurations(data_source_id: int) -> List[Dict[str, Any]]:
    """
    Get all tag configurations for a data source.
    
    Args:
        data_source_id: ID of the data source
        
    Returns:
        List of tag configuration dictionaries
    """
    with get_db_transaction() as (conn, cursor):
        cursor.execute("""
            SELECT 
                id,
                data_source_id,
                column_name,
                extraction_method,
                trigger_value,
                created_at
            FROM tag_configurations
            WHERE data_source_id = %s
            ORDER BY id
        """, (data_source_id,))
        
        columns = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        
        return [dict(zip(columns, row)) for row in rows]


@with_db_error_handling
def save_tag_configuration(
    data_source_id: int,
    column_name: str,
    extraction_method: str,
    trigger_value: str = '1'
) -> int:
    """
    Save a new tag configuration.
    
    Args:
        data_source_id: ID of the data source
        column_name: Name of the column to extract tags from
        extraction_method: 'header_based' or 'value_based'
        trigger_value: Value to trigger tag extraction (for header_based)
        
    Returns:
        ID of the created tag configuration
    """
    if extraction_method not in ['header_based', 'value_based']:
        raise ValueError(f"Invalid extraction_method: {extraction_method}")
    
    with get_db_transaction() as (conn, cursor):
        cursor.execute("""
            INSERT INTO tag_configurations (
                data_source_id,
                column_name,
                extraction_method,
                trigger_value
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """, (data_source_id, column_name, extraction_method, trigger_value))
        
        tag_config_id = cursor.fetchone()[0]
        logger.info(f"Created tag configuration {tag_config_id} for data source {data_source_id}")
        return tag_config_id


@with_db_error_handling
def update_tag_configuration(
    config_id: int,
    column_name: Optional[str] = None,
    extraction_method: Optional[str] = None,
    trigger_value: Optional[str] = None
) -> None:
    """
    Update an existing tag configuration.
    
    Args:
        config_id: ID of the tag configuration
        column_name: New column name (optional)
        extraction_method: New extraction method (optional)
        trigger_value: New trigger value (optional)
    """
    updates = []
    params = []
    
    if column_name is not None:
        updates.append("column_name = %s")
        params.append(column_name)
    
    if extraction_method is not None:
        if extraction_method not in ['header_based', 'value_based']:
            raise ValueError(f"Invalid extraction_method: {extraction_method}")
        updates.append("extraction_method = %s")
        params.append(extraction_method)
    
    if trigger_value is not None:
        updates.append("trigger_value = %s")
        params.append(trigger_value)
    
    if not updates:
        logger.warning(f"No updates provided for tag configuration {config_id}")
        return
    
    params.append(config_id)
    
    with get_db_transaction() as (conn, cursor):
        cursor.execute(f"""
            UPDATE tag_configurations
            SET {', '.join(updates)}
            WHERE id = %s
        """, params)
        
        logger.info(f"Updated tag configuration {config_id}")


@with_db_error_handling
def delete_tag_configuration(config_id: int) -> None:
    """
    Delete a tag configuration.
    
    Args:
        config_id: ID of the tag configuration to delete
    """
    with get_db_transaction() as (conn, cursor):
        cursor.execute("""
            DELETE FROM tag_configurations
            WHERE id = %s
        """, (config_id,))
        
        logger.info(f"Deleted tag configuration {config_id}")


@with_db_error_handling
def delete_all_tag_configurations(data_source_id: int) -> None:
    """
    Delete all tag configurations for a data source.
    
    Args:
        data_source_id: ID of the data source
    """
    with get_db_transaction() as (conn, cursor):
        cursor.execute("""
            DELETE FROM tag_configurations
            WHERE data_source_id = %s
        """, (data_source_id,))
        
        deleted_count = cursor.rowcount
        logger.info(f"Deleted {deleted_count} tag configurations for data source {data_source_id}")


@with_db_error_handling
def get_tag_configuration_by_id(config_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a specific tag configuration by ID.
    
    Args:
        config_id: ID of the tag configuration
        
    Returns:
        Tag configuration dictionary or None if not found
    """
    with get_db_transaction() as (conn, cursor):
        cursor.execute("""
            SELECT 
                id,
                data_source_id,
                column_name,
                extraction_method,
                trigger_value,
                created_at
            FROM tag_configurations
            WHERE id = %s
        """, (config_id,))
        
        row = cursor.fetchone()
        if not row:
            return None
        
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))

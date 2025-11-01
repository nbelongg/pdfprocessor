"""
Product management database operations.

This module handles all database operations for products:
- CRUD operations
- API key retrieval via Replit secrets
- Product configuration management
"""

import os
import logging
from typing import Dict, List, Optional, Any
from psycopg2.extras import Json

from utils.exceptions import DatabaseError, DatabaseTransientError
from utils.db_utils import get_db_transaction, with_db_error_handling
from utils.db.connection import _row_to_dict

logger = logging.getLogger(__name__)


@with_db_error_handling
def init_products_table():
    """Initialize products table."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS products (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) UNIQUE NOT NULL,
                    description TEXT,
                    pinecone_index VARCHAR(255) NOT NULL,
                    llamaparse_api_key_secret TEXT,
                    openai_api_key_secret TEXT,
                    pinecone_api_key_secret TEXT,
                    google_credentials_secret TEXT,
                    default_chunking_strategy VARCHAR(50) DEFAULT 'Token-based',
                    default_chunk_size INTEGER DEFAULT 1024,
                    default_embedding_model VARCHAR(100) DEFAULT 'text-embedding-3-small',
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Add all processing settings columns
            cur.execute("""
                ALTER TABLE products 
                ADD COLUMN IF NOT EXISTS google_credentials_secret TEXT,
                ADD COLUMN IF NOT EXISTS parsing_mode VARCHAR(50) DEFAULT 'auto',
                ADD COLUMN IF NOT EXISTS result_type VARCHAR(50) DEFAULT 'markdown',
                ADD COLUMN IF NOT EXISTS language VARCHAR(10) DEFAULT 'en',
                ADD COLUMN IF NOT EXISTS use_vendor_multimodal BOOLEAN DEFAULT TRUE,
                ADD COLUMN IF NOT EXISTS page_separator VARCHAR(50) DEFAULT '\n---\n',
                ADD COLUMN IF NOT EXISTS chunk_overlap INTEGER DEFAULT 200,
                ADD COLUMN IF NOT EXISTS semantic_buffer_size INTEGER DEFAULT 1,
                ADD COLUMN IF NOT EXISTS pinecone_environment VARCHAR(100) DEFAULT 'us-east-1',
                ADD COLUMN IF NOT EXISTS default_namespace VARCHAR(255) DEFAULT 'default',
                ADD COLUMN IF NOT EXISTS embedding_dimension INTEGER
            """)
            
            # Migrate existing VARCHAR(255) secret columns to TEXT
            cur.execute("""
                ALTER TABLE products 
                ALTER COLUMN llamaparse_api_key_secret TYPE TEXT,
                ALTER COLUMN openai_api_key_secret TYPE TEXT,
                ALTER COLUMN pinecone_api_key_secret TYPE TEXT,
                ALTER COLUMN google_credentials_secret TYPE TEXT
            """)
            
            # Add product_id to data_sources if not exists
            cur.execute("""
                ALTER TABLE data_sources 
                ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES products(id) ON DELETE SET NULL
            """)


@with_db_error_handling
def get_products(active_only: bool = False) -> List[Dict]:
    """Get all products."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            if active_only:
                cur.execute("SELECT * FROM products WHERE active = TRUE ORDER BY name")
            else:
                cur.execute("SELECT * FROM products ORDER BY name")
            return [dict(row) for row in cur.fetchall()]


@with_db_error_handling
def get_product(product_id: int) -> Optional[Dict]:
    """Get product by ID."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            return _row_to_dict(cur.fetchone())


@with_db_error_handling
def create_product(
    name: str,
    pinecone_index: str,
    description: str = '',
    llamaparse_api_key_secret: str = '',
    openai_api_key_secret: str = '',
    pinecone_api_key_secret: str = '',
    google_credentials_secret: str = '',
    **kwargs
) -> int:
    """Create a new product with processing settings."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            # Build column list and values dynamically
            columns = [
                'name', 'pinecone_index', 'description',
                'llamaparse_api_key_secret', 'openai_api_key_secret',
                'pinecone_api_key_secret', 'google_credentials_secret'
            ]
            values = [
                name, pinecone_index, description,
                llamaparse_api_key_secret, openai_api_key_secret,
                pinecone_api_key_secret, google_credentials_secret
            ]
            
            # Add any additional kwargs
            for key, value in kwargs.items():
                columns.append(key)
                values.append(value)
            
            placeholders = ', '.join(['%s'] * len(values))
            columns_str = ', '.join(columns)
            
            cur.execute(
                f"""
                INSERT INTO products ({columns_str})
                VALUES ({placeholders})
                RETURNING id
                """,
                values
            )
            result = cur.fetchone()
            return result['id'] if result else None


@with_db_error_handling
def update_product(
    product_id: int,
    **kwargs
):
    """Update product settings."""
    with get_db_transaction() as conn:
        with conn.cursor() as cur:
            set_clauses = ["updated_at = CURRENT_TIMESTAMP"]
            values = []
            
            # All allowed fields
            allowed_fields = [
                'name', 'description', 'pinecone_index',
                'llamaparse_api_key_secret', 'openai_api_key_secret',
                'pinecone_api_key_secret', 'google_credentials_secret',
                'default_chunking_strategy', 'default_chunk_size',
                'default_embedding_model', 'active',
                'parsing_mode', 'result_type', 'language',
                'use_vendor_multimodal', 'page_separator',
                'num_workers', 'page_error_tolerance',
                'chunk_overlap', 'semantic_buffer_size',
                'pinecone_environment', 'default_namespace',
                'embedding_dimension', 'tagging_enabled',
                'tagging_model', 'tagging_prompt_template',
                'tagging_config'
            ]
            
            for key in allowed_fields:
                if key in kwargs:
                    # Handle JSON fields
                    if key == 'tagging_config' and kwargs[key] is not None:
                        set_clauses.append(f"{key} = %s")
                        values.append(Json(kwargs[key]))
                    else:
                        set_clauses.append(f"{key} = %s")
                        values.append(kwargs[key])
            
            values.append(product_id)
            
            cur.execute(
                f"UPDATE products SET {', '.join(set_clauses)} WHERE id = %s",
                values
            )


@with_db_error_handling
def delete_product(product_id: int):
    """Delete a product (soft delete by setting active=false)."""
    update_product(product_id, active=False)


def get_product_api_keys(product_id: int) -> Dict:
    """
    Get API keys for a product from Replit secrets.
    
    Args:
        product_id: Product ID
        
    Returns:
        Dict with actual API key values from environment variables
    """
    product = get_product(product_id)
    if not product:
        return {}
    
    api_keys = {}
    
    # Map secret names to environment variables
    secret_mappings = {
        'LLAMA_CLOUD_API_KEY': product.get('llamaparse_api_key_secret'),
        'OPENAI_API_KEY': product.get('openai_api_key_secret'),
        'PINECONE_API_KEY': product.get('pinecone_api_key_secret'),
        'GOOGLE_CREDENTIALS': product.get('google_credentials_secret')
    }
    
    for env_key, secret_name in secret_mappings.items():
        if secret_name:
            # Get actual value from environment using the secret name
            actual_value = os.getenv(secret_name, '')
            if actual_value:
                # Special handling for Google credentials - parse JSON string to dict
                if env_key == 'GOOGLE_CREDENTIALS':
                    try:
                        import json
                        api_keys[env_key] = json.loads(actual_value)
                    except json.JSONDecodeError:
                        # If it's already a dict or invalid JSON, use as-is
                        api_keys[env_key] = actual_value
                else:
                    api_keys[env_key] = actual_value
    
    return api_keys

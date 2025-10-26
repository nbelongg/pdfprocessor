"""
Centralized product configuration builder.

This module provides a single source of truth for building product
configurations from database records, eliminating duplication across
tasks.py, scheduler.py, and pipeline modules.

Usage:
    from utils.config_builder import build_product_config
    
    # Build config for a product
    config = build_product_config(product_id=1)
    
    # Build config with base settings
    config = build_product_config(
        product_id=1,
        base_config={'extra_setting': 'value'}
    )
"""

import logging
from typing import Dict, Any, Optional

from utils.db import get_product, get_product_api_keys, get_data_source
from utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)


# ============================================
# CONSTANTS - Single Source of Truth
# ============================================

PRODUCT_CONFIG_MAPPING = {
    'llama_api_key': 'LLAMA_CLOUD_API_KEY',
    'openai_api_key': 'OPENAI_API_KEY',
    'pinecone_api_key': 'PINECONE_API_KEY',
    'google_credentials': 'GOOGLE_CREDENTIALS'
}

PRODUCT_SETTINGS_MAPPING = {
    'index_name': 'pinecone_index',
    'pinecone_environment': 'pinecone_environment',
    'default_namespace': 'default_namespace',
    'parsing_mode': 'parsing_mode',
    'result_type': 'result_type',
    'language': 'language',
    'use_vendor_multimodal': 'use_vendor_multimodal',
    'page_separator': 'page_separator',
    'chunking_strategy': 'default_chunking_strategy',
    'chunk_size': 'default_chunk_size',
    'chunk_overlap': 'chunk_overlap',
    'semantic_buffer_size': 'semantic_buffer_size',
    'embedding_model': 'default_embedding_model',
    'embedding_dimension': 'embedding_dimension',
    'tagging_enabled': 'tagging_enabled',
    'tagging_model': 'tagging_model',
    'tagging_prompt_template': 'tagging_prompt_template',
    'tagging_config': 'tagging_config'
}


# ============================================
# CONFIG BUILDER
# ============================================

def build_product_config(
    product_id: int,
    base_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build complete product configuration from database.
    
    This function:
    1. Loads product info from database
    2. Retrieves API keys from environment (via product secrets)
    3. Merges product settings with base config
    4. Returns complete configuration dict
    
    Args:
        product_id: Product ID to load config for
        base_config: Optional base configuration to extend
        
    Returns:
        Complete configuration dictionary ready for processing
        
    Raises:
        DatabaseError: If product not found or database error
        ValueError: If product not found or required API keys are missing
        
    Examples:
        >>> config = build_product_config(product_id=1)
        >>> print(config['parsing_mode'])
        'auto'
        
        >>> config = build_product_config(
        ...     product_id=1,
        ...     base_config={'custom_setting': 'value'}
        ... )
    """
    # Start with base config or empty dict
    config = base_config.copy() if base_config else {}
    
    # Load product info
    product = get_product(product_id)
    if not product:
        raise ValueError(f"Product {product_id} not found")
    
    if not product.get('active'):
        logger.warning(f"Product {product_id} is inactive")
    
    logger.info(f"Building config for product: {product.get('name')}")
    
    # Get API keys from environment (using secret names)
    api_keys = get_product_api_keys(product_id)
    
    # Apply API keys using mapping dict
    for config_key, api_key_name in PRODUCT_CONFIG_MAPPING.items():
        value = api_keys.get(api_key_name)
        if value:
            config[config_key] = value
            logger.debug(f"Set {config_key} from {api_key_name}")
        else:
            logger.warning(f"Missing API key: {api_key_name}")
    
    # Apply product settings using mapping dict
    for config_key, product_key in PRODUCT_SETTINGS_MAPPING.items():
        value = product.get(product_key)
        if value is not None:
            config[config_key] = value
            logger.debug(f"Set {config_key} = {value}")
    
    # Validate required keys exist
    required_keys = ['llama_api_key', 'openai_api_key', 'pinecone_api_key']
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        logger.error(f"Missing required API keys for product {product_id}: {missing}")
        raise ValueError(f"Missing required API keys for product {product_id}: {missing}")
    
    logger.info(f"Successfully built config for product {product_id}")
    return config


def get_product_config_from_source(
    source_id: int,
    base_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build product config from data source ID.
    
    Convenience function that looks up the product ID from a data source
    and builds the config.
    
    Args:
        source_id: Data source ID
        base_config: Optional base configuration to extend
        
    Returns:
        Complete product configuration
        
    Raises:
        ValueError: If data source not found or has no product assigned
    """
    source = get_data_source(source_id)
    if not source:
        raise ValueError(f"Data source {source_id} not found")
    
    product_id = source.get('product_id')
    if not product_id:
        raise ValueError(f"Data source {source_id} has no product assigned")
    
    return build_product_config(product_id, base_config)


def apply_product_settings_to_config(
    config: Dict[str, Any],
    product_id: int
) -> None:
    """
    Apply product-specific settings to existing config in place.
    
    This is a convenience function for backward compatibility with code
    that mutates config dicts. New code should use build_product_config().
    
    Args:
        config: Configuration dictionary to update
        product_id: Product ID to load settings from
    """
    product_config = build_product_config(product_id, base_config=config)
    config.update(product_config)

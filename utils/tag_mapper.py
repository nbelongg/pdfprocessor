"""
Tag mapping utility for standardizing tags from Google Sheets.

This module provides functionality to map source tags (from spreadsheet columns)
to internal standardized tags based on product and data source configuration.
"""

import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


def apply_tag_mappings(
    tags: List[str],
    tag_mappings: Dict[str, str],
    unmapped_behavior: str = 'keep'
) -> List[str]:
    """
    Apply tag mappings to transform source tags into internal tags.
    
    Args:
        tags: List of source tags from spreadsheet
        tag_mappings: Dictionary mapping source tag -> internal tag
        unmapped_behavior: How to handle unmapped tags ('keep' or 'skip')
        
    Returns:
        List of transformed tags (deduplicated)
        
    Example:
        tags = ["MBS (Marketing and Behavior Science 101)", "GPP (Governance...)"]
        mappings = {
            "MBS (Marketing and Behavior Science 101)": "C2: MBS and GPP",
            "GPP (Governance & Public Policy 101)": "C2: MBS and GPP"
        }
        result = apply_tag_mappings(tags, mappings, 'keep')
        # Returns: ["C2: MBS and GPP"]
    """
    if not tags:
        return []
    
    if not tag_mappings:
        # No mappings configured, return original tags
        return tags
    
    mapped_tags = []
    
    for tag in tags:
        # Check if mapping exists (case-insensitive)
        mapped_tag = None
        for source_tag, target_tag in tag_mappings.items():
            if source_tag.lower() == tag.lower():
                mapped_tag = target_tag
                break
        
        if mapped_tag:
            mapped_tags.append(mapped_tag)
            logger.debug(f"Tag mapping: '{tag}' -> '{mapped_tag}'")
        else:
            # Handle unmapped tag based on behavior setting
            if unmapped_behavior == 'keep':
                mapped_tags.append(tag)
                logger.debug(f"Tag unmapped (keeping): '{tag}'")
            else:  # skip
                logger.debug(f"Tag unmapped (skipping): '{tag}'")
    
    # Deduplicate while preserving order
    seen = set()
    unique_tags = []
    for tag in mapped_tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags


def resolve_tag_mapping_config(
    product_config: Dict,
    data_source_config: Optional[Dict] = None
) -> tuple[Dict[str, str], str]:
    """
    Resolve which tag mappings to use based on product and data source config.
    
    Resolution order:
    1. If data source has custom mappings enabled -> use data source mappings
    2. Otherwise -> use product-level mappings
    
    Args:
        product_config: Product configuration dict
        data_source_config: Data source configuration dict (optional)
        
    Returns:
        Tuple of (tag_mappings dict, unmapped_behavior string)
    """
    # Default values
    default_mappings = {}
    default_behavior = 'keep'
    
    # Check if data source has custom mappings enabled
    if data_source_config:
        custom_enabled = data_source_config.get('custom_tag_mappings_enabled', False)
        
        if custom_enabled:
            # Use data source mappings
            mappings = data_source_config.get('tag_mappings', {}) or {}
            behavior = data_source_config.get('unmapped_tag_behavior', 'keep') or 'keep'
            logger.info(f"Using data source-level tag mappings ({len(mappings)} mappings)")
            return mappings, behavior
    
    # Use product-level mappings
    mappings = product_config.get('tag_mappings', {}) or {}
    behavior = product_config.get('unmapped_tag_behavior', 'keep') or 'keep'
    
    if mappings:
        logger.info(f"Using product-level tag mappings ({len(mappings)} mappings)")
    else:
        logger.debug("No tag mappings configured")
    
    return mappings, behavior


def validate_tag_mappings(mappings: Dict[str, str]) -> Dict[str, str]:
    """
    Validate and sanitize tag mappings.
    
    Args:
        mappings: Dictionary of source -> target tag mappings
        
    Returns:
        Validated mappings dict
        
    Raises:
        ValueError: If mappings are invalid
    """
    if not isinstance(mappings, dict):
        raise ValueError("Tag mappings must be a dictionary")
    
    validated = {}
    
    for source, target in mappings.items():
        # Ensure both source and target are strings
        if not isinstance(source, str) or not isinstance(target, str):
            raise ValueError(f"Tag mapping keys and values must be strings: {source} -> {target}")
        
        # Strip whitespace
        source_clean = source.strip()
        target_clean = target.strip()
        
        if not source_clean or not target_clean:
            raise ValueError(f"Tag mapping cannot have empty source or target: '{source}' -> '{target}'")
        
        validated[source_clean] = target_clean
    
    return validated

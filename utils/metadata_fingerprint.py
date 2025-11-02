"""
Metadata fingerprint calculation for change detection.

This module calculates SHA256 hashes of metadata fields to detect when
metadata has changed without re-parsing PDFs.
"""

import hashlib
import json
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def calculate_metadata_fingerprint(metadata: Dict[str, Any]) -> str:
    """
    Calculate SHA256 fingerprint of metadata fields.
    
    This hash includes all metadata fields that might change and affect
    how the paper appears in search results (tags, year, topic, etc.)
    but excludes structural fields like file_id, filename, drive_link.
    
    Args:
        metadata: Dictionary of metadata fields
        
    Returns:
        64-character SHA256 hex digest
        
    Example:
        >>> metadata = {'tags': ['Primary Care'], 'publication_year': '2023', 'topic': 'Health'}
        >>> fingerprint = calculate_metadata_fingerprint(metadata)
        >>> len(fingerprint)
        64
    """
    # Fields to include in fingerprint (order matters for consistency)
    # These are metadata fields that can change and should trigger updates
    fingerprint_fields = [
        'tags',
        'publication_year',
        'topic',
        'journal',
        'doi',
        'authors',  # Authors included for completeness
        'paper_title',  # Title included for completeness
        # Add any other metadata fields that should trigger updates
    ]
    
    # Build normalized metadata dict
    normalized = {}
    for field in fingerprint_fields:
        if field in metadata:
            value = metadata[field]
            
            # Normalize tags list to sorted, comma-separated string
            if field == 'tags' and isinstance(value, list):
                normalized[field] = ','.join(sorted(str(tag) for tag in value))
            else:
                normalized[field] = str(value) if value is not None else ''
        else:
            normalized[field] = ''
    
    # Convert to deterministic JSON string (sorted keys)
    json_str = json.dumps(normalized, sort_keys=True, ensure_ascii=True)
    
    # Calculate SHA256 hash
    fingerprint = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    
    logger.debug(f"Calculated metadata fingerprint: {fingerprint} from {len(normalized)} fields")
    return fingerprint


def has_metadata_changed(
    old_fingerprint: str,
    new_metadata: Dict[str, Any]
) -> bool:
    """
    Check if metadata has changed by comparing fingerprints.
    
    Args:
        old_fingerprint: Previously stored fingerprint
        new_metadata: Current metadata from Google Sheet
        
    Returns:
        True if metadata has changed, False otherwise
    """
    new_fingerprint = calculate_metadata_fingerprint(new_metadata)
    changed = old_fingerprint != new_fingerprint
    
    if changed:
        logger.info(f"Metadata changed - old: {old_fingerprint[:8]}..., new: {new_fingerprint[:8]}...")
    
    return changed


def extract_metadata_for_fingerprint(row_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Extract only the fields needed for fingerprint calculation from row_metadata.
    
    This filters out structural fields like file_id, filename, drive_link
    and keeps only the semantic metadata fields.
    
    Args:
        row_metadata: Full metadata dict from pipeline
        
    Returns:
        Filtered metadata dict with only fingerprint-relevant fields
    """
    # Fields to exclude from fingerprint (structural, not semantic)
    exclude_fields = {
        'file_id',
        'filename',
        'drive_link',
        'source',
        'source_id',
        'auto_generated_tags',
        'spreadsheet_tags_only',
        'spreadsheet_tags_count',
        'ai_tags_count'
    }
    
    # Extract only relevant fields
    filtered = {
        k: v for k, v in row_metadata.items()
        if k not in exclude_fields
    }
    
    return filtered

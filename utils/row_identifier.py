"""
Row identifier extraction for hash-based paper detection.

This module provides functions to generate stable, unique identifiers for Google Sheet rows
without requiring any additional columns in the sheet. This enables detection of new papers
regardless of their position (handles mid-sheet insertions, reordering, etc.)

Identifier Strategy:
1. Primary: Google Drive File ID (stable, unique)
2. Fallback: Content hash (title + authors + year + url)
"""

import hashlib
import logging
import re
from typing import Optional, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


def extract_drive_file_id(drive_link: str) -> Optional[str]:
    """
    Extract Google Drive file ID from various Drive URL formats.
    
    Supported formats:
    - https://drive.google.com/file/d/FILE_ID/view
    - https://drive.google.com/open?id=FILE_ID
    - https://docs.google.com/document/d/FILE_ID/edit
    
    Args:
        drive_link: Google Drive URL
        
    Returns:
        File ID string or None if not found
        
    Examples:
        >>> extract_drive_file_id('https://drive.google.com/file/d/1a2b3c4d/view')
        '1a2b3c4d'
    """
    if not drive_link or not isinstance(drive_link, str):
        return None
    
    # Try multiple patterns
    patterns = [
        r'/file/d/([a-zA-Z0-9_-]+)',
        r'/folders/([a-zA-Z0-9_-]+)',
        r'[?&]id=([a-zA-Z0-9_-]+)',
        r'/d/([a-zA-Z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, drive_link)
        if match:
            return match.group(1)
    
    return None


def generate_content_hash(title: str = '', authors: str = '', year: str = '', url: str = '') -> str:
    """
    Generate a content hash from paper metadata fields.
    
    Uses SHA256 hash of concatenated fields: title|authors|year|url
    Returns full 64-character hex digest to match existing deduplication system.
    
    Args:
        title: Paper title
        authors: Authors string
        year: Publication year
        url: Paper URL or DOI
        
    Returns:
        64-character SHA256 hash string (full hex digest)
        
    Examples:
        >>> generate_content_hash('Neural Networks', 'Smith et al', '2024', 'arxiv.org/123')
        'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2'
        
    Note:
        Returns full 64-character digest to match stored hashes in processed_papers table.
        This ensures compatibility with existing deduplication records.
    """
    # Normalize fields (strip whitespace, lowercase)
    fields = [
        str(title).strip().lower() if title else '',
        str(authors).strip().lower() if authors else '',
        str(year).strip() if year else '',
        str(url).strip().lower() if url else '',
    ]
    
    # Concatenate with delimiter
    hash_input = '|'.join(fields)
    
    # Generate SHA256 hash
    hash_obj = hashlib.sha256(hash_input.encode('utf-8'))
    hash_hex = hash_obj.hexdigest()
    
    # Return full 64-character digest
    return hash_hex


def extract_row_identifier(
    row: pd.Series,
    column_mappings: Dict[str, str],
    verbose: bool = False
) -> Optional[str]:
    """
    Extract a stable identifier from a Google Sheet row.
    
    Priority:
    1. Google Drive File ID (if drive_link column exists and is populated)
    2. Content hash (from title, authors, year, url fields)
    
    Args:
        row: pandas Series representing a sheet row
        column_mappings: Dict mapping roles to column names
            Example: {'drive_link': 'PDF Link', 'title': 'Title', ...}
        verbose: If True, log detailed extraction info
        
    Returns:
        Identifier string or None if row cannot be identified
        
    Note:
        Returns None for empty rows (no data to identify)
    """
    # Helper to get column value safely
    def get_column_value(role: str) -> Optional[str]:
        col_name = column_mappings.get(role)
        if not col_name:
            return None
        
        value = row.get(col_name)
        
        # Handle pandas NaN and empty values
        if pd.isna(value) or value == '' or value is None:
            return None
        
        return str(value).strip()
    
    # Try Drive File ID first (highest priority)
    drive_link = get_column_value('drive_link')
    if drive_link:
        file_id = extract_drive_file_id(drive_link)
        if file_id:
            if verbose:
                logger.debug(f"Extracted Drive File ID: {file_id}")
            return file_id
    
    # Fallback to content hash
    title = get_column_value('title')
    authors = get_column_value('authors')
    year = get_column_value('year')
    url = get_column_value('url')
    
    # Need at least title OR url to generate hash
    if not title and not url:
        if verbose:
            logger.debug("Row has no title or URL - cannot generate identifier")
        return None
    
    content_hash = generate_content_hash(
        title=title or '',
        authors=authors or '',
        year=year or '',
        url=url or ''
    )
    
    if verbose:
        logger.debug(f"Generated content hash: {content_hash} for title='{title}'")
    
    return content_hash


def extract_all_row_identifiers(
    sheet_data: pd.DataFrame,
    column_mappings: Dict[str, str]
) -> Dict[int, str]:
    """
    Extract identifiers for all rows in a Google Sheet.
    
    Args:
        sheet_data: DataFrame containing the sheet data
        column_mappings: Dict mapping roles to column names
        
    Returns:
        Dict mapping row index to identifier string
        Only includes rows that have valid identifiers (skips empty rows)
        
    Example:
        {
            0: '1a2b3c4d5e6f7g',                                                   # Row 0: Drive File ID
            1: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2',  # Row 1: Content hash (64 chars)
            5: '9h8g7f6e5d4c3b'                                                    # Row 5: Another ID
        }
    """
    identifiers = {}
    
    for idx, row in sheet_data.iterrows():
        identifier = extract_row_identifier(row, column_mappings, verbose=False)
        if identifier:
            identifiers[idx] = identifier
    
    logger.info(
        f"Extracted {len(identifiers)} identifiers from {len(sheet_data)} sheet rows "
        f"({len(sheet_data) - len(identifiers)} rows skipped as empty)"
    )
    
    return identifiers


def get_unprocessed_row_indices(
    sheet_data: pd.DataFrame,
    column_mappings: Dict[str, str],
    processed_identifiers: set,
    max_papers: Optional[int] = None
) -> list:
    """
    Find indices of unprocessed rows in a Google Sheet.
    
    This is the core function for hash-based paper detection.
    It detects new papers regardless of their position in the sheet.
    
    Args:
        sheet_data: DataFrame containing all sheet rows
        column_mappings: Dict mapping roles to column names
        processed_identifiers: Set of already-processed identifiers
        max_papers: Optional limit on number of rows to return
        
    Returns:
        List of row indices (integers) that haven't been processed yet
        
    Example:
        >>> get_unprocessed_row_indices(sheet, mappings, {'abc123', 'def456'}, max_papers=100)
        [0, 5, 10, 15, ...]  # Up to 100 unprocessed row indices
    """
    # Get all identifiers from sheet
    all_identifiers = extract_all_row_identifiers(sheet_data, column_mappings)
    
    # Find unprocessed ones
    unprocessed_indices = []
    for idx, identifier in all_identifiers.items():
        if identifier not in processed_identifiers:
            unprocessed_indices.append(idx)
    
    logger.info(
        f"Found {len(unprocessed_indices)} unprocessed papers "
        f"(out of {len(all_identifiers)} total identifiable rows)"
    )
    
    # Apply max_papers limit if specified
    if max_papers and len(unprocessed_indices) > max_papers:
        limited_indices = unprocessed_indices[:max_papers]
        logger.info(f"Limiting to {max_papers} papers (max_papers_per_run)")
        return limited_indices
    
    return unprocessed_indices

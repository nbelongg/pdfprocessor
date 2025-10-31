"""
Google Sheets integration for loading data.

This module provides functions to load data from Google Sheets using
service account credentials.
"""

import gspread
from gspread.exceptions import APIError, GSpreadException
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from typing import Dict, Optional, List
import re
import socket
import http.client

from utils.exceptions import TransientError


def load_sheet_data(sheet_url: str, tab_name: str, credentials_dict: Optional[Dict] = None) -> pd.DataFrame:
    """
    Load data from Google Sheets using service account credentials.
    
    Args:
        sheet_url: Full URL of the Google Sheet
        tab_name: Name of the tab/worksheet to read
        credentials_dict: Service account credentials as dictionary
        
    Returns:
        DataFrame containing the sheet data
        
    Raises:
        TransientError: For network errors, timeouts, rate limits (retryable)
        ValueError: For missing credentials or invalid URL (not retryable)
        GSpreadException: For other gspread errors (not retryable)
    """
    try:
        scope = [
            'https://spreadsheets.google.com/feeds',
            'https://www.googleapis.com/auth/drive'
        ]
        
        if credentials_dict:
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        else:
            raise ValueError("Google credentials required")
        
        client = gspread.authorize(credentials)
        
        sheet_id = extract_sheet_id(sheet_url)
        spreadsheet = client.open_by_key(sheet_id)
        
        worksheet = spreadsheet.worksheet(tab_name)
        
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        return df
        
    except APIError as e:
        # Only wrap transient errors (rate limit, service unavailable)
        # Let permission/auth/not found errors propagate
        if hasattr(e, 'response') and e.response:
            status_code = e.response.get('code', 0)
            if status_code in [429, 503]:
                raise TransientError(f"Google Sheets API rate limit or service unavailable: {e}") from e
        # Don't wrap other API errors (403, 404, etc.) - let them propagate
        raise
        
    except (socket.timeout, socket.error, http.client.HTTPException, ConnectionError) as e:
        # Network errors are transient, should retry
        raise TransientError(f"Network error loading Google Sheets: {e}") from e


def extract_sheet_id(url: str) -> str:
    """
    Extract the sheet ID from a Google Sheets URL.
    
    Args:
        url: Google Sheets URL
        
    Returns:
        Sheet ID
        
    Raises:
        ValueError: If URL format is invalid
    """
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract sheet ID from URL: {url}")


def extract_file_id_from_drive_link(drive_link: str) -> Optional[str]:
    """
    Extract file ID from various Google Drive URL formats.
    
    Args:
        drive_link: Google Drive URL or file ID
        
    Returns:
        File ID or None if not found
    """
    if not drive_link or pd.isna(drive_link):
        return None
    
    patterns = [
        r'/file/d/([a-zA-Z0-9-_]+)',
        r'id=([a-zA-Z0-9-_]+)',
        r'/open\?id=([a-zA-Z0-9-_]+)',
        r'^([a-zA-Z0-9-_]{25,})$'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, str(drive_link))
        if match:
            return match.group(1)
    
    return None


def extract_tags_from_row(row: pd.Series, tag_configs: List[Dict], column_mappings: Dict[str, str]) -> List[str]:
    """
    Extract tags from a spreadsheet row based on tag configurations.
    
    Args:
        row: Pandas Series representing a single row from the sheet
        tag_configs: List of tag configuration dicts with column_name, extraction_method, trigger_value
        column_mappings: Dict mapping column roles to column names (e.g., {'tags': 'Keywords'})
        
    Returns:
        List of extracted tags (deduplicated)
    """
    tags = []
    
    # Extract tags from tag configurations
    for config in tag_configs:
        column_name = config.get('column_name', '')
        extraction_method = config.get('extraction_method', 'header_based')
        
        if not column_name or column_name not in row:
            continue
        
        cell_value = row[column_name]
        
        # Skip empty/null values
        if pd.isna(cell_value) or str(cell_value).strip() == '':
            continue
        
        cell_value_str = str(cell_value).strip()
        
        if extraction_method == 'header_based':
            # Header as tag: check if cell value matches trigger
            trigger_value = config.get('trigger_value', '1')
            if cell_value_str == str(trigger_value):
                tags.append(column_name)
        
        elif extraction_method == 'value_based':
            # Value as tag: use cell value directly
            # Split by comma if multiple values
            if ',' in cell_value_str:
                split_tags = [t.strip() for t in cell_value_str.split(',')]
                tags.extend([t for t in split_tags if t])
            else:
                tags.append(cell_value_str)
    
    # Also support legacy 'tags' column from column mappings
    if 'tags' in column_mappings:
        tags_column = column_mappings['tags']
        if tags_column in row:
            legacy_tags_value = row[tags_column]
            if not pd.isna(legacy_tags_value) and str(legacy_tags_value).strip():
                legacy_tags_str = str(legacy_tags_value).strip()
                if ',' in legacy_tags_str:
                    split_legacy = [t.strip() for t in legacy_tags_str.split(',')]
                    tags.extend([t for t in split_legacy if t])
                else:
                    tags.append(legacy_tags_str)
    
    # Deduplicate while preserving order
    seen = set()
    unique_tags = []
    for tag in tags:
        if tag not in seen:
            seen.add(tag)
            unique_tags.append(tag)
    
    return unique_tags

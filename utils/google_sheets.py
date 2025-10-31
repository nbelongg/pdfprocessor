"""
Google Sheets integration for loading data.

This module provides functions to load data from Google Sheets using
service account credentials.
"""

import gspread
from gspread.exceptions import APIError, GSpreadException
from oauth2client.service_account import ServiceAccountCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
from typing import Dict, Optional, List, Union
import re
import socket
import http.client
import json
import logging

from utils.exceptions import TransientError

logger = logging.getLogger(__name__)


def _extract_url_from_hyperlink_formula(formula: str) -> Optional[str]:
    """
    Extract URL from a HYPERLINK formula.
    
    Examples:
        =HYPERLINK("https://example.com", "text") -> https://example.com
        =HYPERLINK("https://example.com") -> https://example.com
    
    Args:
        formula: The HYPERLINK formula string
        
    Returns:
        The extracted URL or None if extraction fails
    """
    try:
        # Match HYPERLINK("url"...) or HYPERLINK('url'...)
        match = re.search(r'=HYPERLINK\s*\(\s*["\']([^"\']+)["\']', formula, re.IGNORECASE)
        if match:
            return match.group(1)
    except:
        pass
    return None


def load_sheet_data(sheet_url: str, tab_name: str, credentials_dict: Optional[Union[Dict, str]] = None) -> pd.DataFrame:
    """
    Load data from Google Sheets using service account credentials.
    Extracts hyperlinks from cells that contain HYPERLINK formulas.
    
    Args:
        sheet_url: Full URL of the Google Sheet
        tab_name: Name of the tab/worksheet to read
        credentials_dict: Service account credentials as dictionary or JSON string
        
    Returns:
        DataFrame containing the sheet data with hyperlinks extracted
        
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
            # Parse JSON string if needed
            if isinstance(credentials_dict, str):
                try:
                    credentials_dict = json.loads(credentials_dict)
                except json.JSONDecodeError as e:
                    raise ValueError(f"Invalid JSON in Google credentials: {e}")
            
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        else:
            raise ValueError("Google credentials required")
        
        client = gspread.authorize(credentials)
        
        sheet_id = extract_sheet_id(sheet_url)
        spreadsheet = client.open_by_key(sheet_id)
        
        worksheet = spreadsheet.worksheet(tab_name)
        
        # Get display values
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        
        # Extract hyperlinks from cells using Google Sheets API v4
        # This handles both HYPERLINK() formulas and regular hyperlinks
        print(f"📋 LOAD_SHEET_DATA: Starting hyperlink extraction for tab '{tab_name}'")
        try:
            # Build Sheets API v4 service
            service = build('sheets', 'v4', credentials=credentials, cache_discovery=False)
            
            print(f"📋 LOAD_SHEET_DATA: Built Sheets API v4 service")
            logger.info(f"Attempting to extract hyperlinks from sheet '{tab_name}'")
            
            # Get the worksheet ID
            worksheet_id = worksheet.id
            
            # Request cell data including hyperlinks
            print(f"📋 LOAD_SHEET_DATA: Requesting cell data with hyperlinks...")
            result = service.spreadsheets().get(
                spreadsheetId=sheet_id,
                ranges=f'{tab_name}!A:ZZ',
                fields='sheets(data(rowData(values(hyperlink,formattedValue))))'
            ).execute()
            
            print(f"📋 LOAD_SHEET_DATA: Successfully fetched hyperlink data from API")
            logger.info(f"Successfully fetched hyperlink data from API")
            
            sheets = result.get('sheets', [])
            print(f"📋 LOAD_SHEET_DATA: Got {len(sheets)} sheets from result")
            
            if sheets and 'data' in sheets[0]:
                row_data = sheets[0]['data'][0].get('rowData', [])
                print(f"📋 LOAD_SHEET_DATA: Got {len(row_data)} rows of data")
                
                # Skip header row, process data rows
                if len(row_data) > 1:
                    headers = [cell.get('formattedValue', '') for cell in row_data[0].get('values', [])]
                    print(f"📋 LOAD_SHEET_DATA: Found {len(headers)} columns")
                    logger.info(f"Found {len(headers)} columns: {headers[:5]}...")  # Log first 5 headers
                    
                    hyperlinks_found = 0
                    for row_idx in range(1, len(row_data)):
                        cells = row_data[row_idx].get('values', [])
                        for col_idx, cell in enumerate(cells):
                            if col_idx < len(headers) and headers[col_idx]:
                                column_name = headers[col_idx]
                                hyperlink = cell.get('hyperlink')
                                
                                # If cell has a hyperlink, replace the display value with the URL
                                if hyperlink and column_name in df.columns:
                                    df_row_idx = row_idx - 1  # Adjust for 0-indexed DataFrame
                                    if df_row_idx < len(df):
                                        df.at[df_row_idx, column_name] = hyperlink
                                        hyperlinks_found += 1
                                        logger.debug(f"Extracted hyperlink for row {df_row_idx}, col '{column_name}': {hyperlink}")
                    
                    print(f"📋 LOAD_SHEET_DATA: Successfully extracted {hyperlinks_found} hyperlinks from sheet")
                    logger.info(f"Successfully extracted {hyperlinks_found} hyperlinks from sheet")
                else:
                    print(f"📋 LOAD_SHEET_DATA: WARNING - Sheet appears to have no data rows")
                    logger.warning("Sheet appears to have no data rows")
            else:
                print(f"📋 LOAD_SHEET_DATA: WARNING - Sheet data structure unexpected")
                logger.warning("Sheet data structure unexpected - no sheets or data found")
        except Exception as e:
            # If hyperlink extraction fails, log and continue with display values
            import traceback
            error_details = traceback.format_exc()
            print(f"⚠️ HYPERLINK EXTRACTION FAILED: {e}")
            print(f"Error details:\n{error_details}")
            logger.error(f"Failed to extract hyperlinks from sheet: {e}", exc_info=True)
        
        # Debug: Show what the dataframe looks like after hyperlink extraction
        print(f"📋 LOAD_SHEET_DATA: Final dataframe shape: {df.shape}")
        print(f"📋 LOAD_SHEET_DATA: Column names: {list(df.columns)[:10]}")  # First 10 columns
        
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

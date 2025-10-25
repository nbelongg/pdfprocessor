import gspread
from oauth2client.service_account import ServiceAccountCredentials
import pandas as pd
from typing import Dict, Optional
import re

def load_sheet_data(sheet_url: str, tab_name: str, credentials_dict: Optional[Dict] = None) -> pd.DataFrame:
    """
    Load data from Google Sheets using service account credentials.
    
    Args:
        sheet_url: Full URL of the Google Sheet
        tab_name: Name of the tab/worksheet to read
        credentials_dict: Service account credentials as dictionary
        
    Returns:
        DataFrame containing the sheet data
    """
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

def extract_sheet_id(url: str) -> str:
    """Extract the sheet ID from a Google Sheets URL."""
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not extract sheet ID from URL: {url}")

def extract_file_id_from_drive_link(drive_link: str) -> Optional[str]:
    """Extract file ID from various Google Drive URL formats."""
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

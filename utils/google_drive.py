"""
Google Drive integration for downloading PDFs.

This module provides functions to download files from Google Drive using
service account credentials.
"""

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from googleapiclient.errors import HttpError
from oauth2client.service_account import ServiceAccountCredentials
import io
from typing import Dict, Optional
import socket
import http.client

from utils.exceptions import TransientError


def download_pdf_from_drive(file_id: str, credentials_dict: Dict) -> bytes:
    """
    Download a PDF file from Google Drive.
    
    Args:
        file_id: Google Drive file ID
        credentials_dict: Service account credentials as dictionary
        
    Returns:
        PDF file content as bytes
        
    Raises:
        TransientError: For network errors, timeouts, rate limits (retryable)
        HttpError: For permission errors, file not found (not retryable)
        ValueError: For invalid credentials (not retryable)
    """
    try:
        scope = ['https://www.googleapis.com/auth/drive.readonly']
        
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        
        service = build('drive', 'v3', credentials=credentials)
        
        request = service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        file_buffer.seek(0)
        return file_buffer.read()
        
    except HttpError as e:
        # Retry on rate limit (429) or service unavailable (503)
        if e.resp.status in [429, 503]:
            raise TransientError(f"Google Drive API rate limit or service unavailable: {e}") from e
        # Don't retry on permission errors (403) or not found (404)
        raise
        
    except (socket.timeout, socket.error, http.client.HTTPException, ConnectionError) as e:
        # Network errors are transient, should retry
        raise TransientError(f"Network error downloading from Google Drive: {e}") from e


def get_file_metadata(file_id: str, credentials_dict: Dict) -> Dict:
    """
    Get metadata for a file from Google Drive.
    
    Args:
        file_id: Google Drive file ID
        credentials_dict: Service account credentials as dictionary
        
    Returns:
        Dictionary containing file metadata
        
    Raises:
        TransientError: For network errors, timeouts, rate limits (retryable)
        HttpError: For permission errors, file not found (not retryable)
        ValueError: For invalid credentials (not retryable)
    """
    try:
        scope = ['https://www.googleapis.com/auth/drive.readonly']
        
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
        
        service = build('drive', 'v3', credentials=credentials)
        
        file_metadata = service.files().get(
            fileId=file_id,
            fields='id, name, mimeType, size, createdTime, modifiedTime'
        ).execute()
        
        return file_metadata
        
    except HttpError as e:
        # Retry on rate limit (429) or service unavailable (503)
        if e.resp.status in [429, 503]:
            raise TransientError(f"Google Drive API rate limit or service unavailable: {e}") from e
        # Don't retry on permission errors (403) or not found (404)
        raise
        
    except (socket.timeout, socket.error, http.client.HTTPException, ConnectionError) as e:
        # Network errors are transient, should retry
        raise TransientError(f"Network error getting metadata from Google Drive: {e}") from e

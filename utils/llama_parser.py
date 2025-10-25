from llama_parse import LlamaParse
from typing import Dict, List, Optional
import tempfile
import os

def parse_pdf_with_llamaparse(
    pdf_content: bytes,
    filename: str,
    config: Dict
) -> str:
    """
    Parse PDF using LlamaParse.
    
    Args:
        pdf_content: PDF file content as bytes
        filename: Name of the PDF file
        config: Configuration dictionary with LlamaParse settings
        
    Returns:
        Parsed text content
    """
    api_key = config.get('llama_api_key', '')
    
    parser = LlamaParse(
        api_key=api_key,
        result_type=config.get('result_type', 'markdown'),
        parsing_instruction=config.get('parsing_instruction', ''),
        language=config.get('language', 'en'),
        use_vendor_multimodal_model=config.get('use_vendor_multimodal', True),
        vendor_multimodal_model_name=config.get('vendor_multimodal_model_name', 'anthropic-sonnet-4'),
        fast_mode=config.get('parsing_mode', 'auto') == 'fast',
        premium_mode=config.get('parsing_mode', 'auto') == 'premium',
        page_separator=config.get('page_separator', '\n---\n')
    )
    
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
        tmp_file.write(pdf_content)
        tmp_file_path = tmp_file.name
    
    try:
        documents = parser.load_data(tmp_file_path)
        
        parsed_text = ""
        for doc in documents:
            parsed_text += doc.text + "\n"
        
        return parsed_text
    
    finally:
        if os.path.exists(tmp_file_path):
            os.unlink(tmp_file_path)

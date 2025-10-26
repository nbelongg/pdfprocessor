"""
AI-powered document tagging using OpenAI LLM.
Generates tags from parsed document content.
"""

import os
import json
from typing import List, Dict, Optional
from openai import OpenAI

DEFAULT_TAGGING_PROMPT = """Analyze the following document and generate 5-10 relevant tags that best describe its content, topics, and themes.

Filename: {filename}
Content Preview:
{text}

Instructions:
- Generate specific, descriptive tags (2-4 words each)
- Focus on: main topics, methodologies, domains, key concepts, and applications
- Avoid generic tags like "interesting" or "important"
- Return ONLY a JSON array of strings, nothing else

Example format: ["machine-learning", "neural-networks", "computer-vision", "deep-learning", "image-classification"]

Your response (JSON array only):"""

def generate_tags_with_openai(
    text: str,
    filename: str,
    model: str = "gpt-4o-mini",
    prompt_template: Optional[str] = None,
    api_key: Optional[str] = None,
    metadata: Optional[Dict] = None,
    max_text_length: int = 8000,
    temperature: float = 0.3,
    max_tokens: int = 500
) -> List[str]:
    """
    Generate tags for a document using OpenAI LLM.
    
    Args:
        text: The parsed document text
        filename: Document filename
        model: OpenAI model to use (gpt-4o, gpt-4o-mini, etc.)
        prompt_template: Custom prompt template with {text}, {filename} placeholders
        api_key: OpenAI API key (if not provided, uses environment variable)
        metadata: Optional metadata to include in prompt
        max_text_length: Maximum characters to send to LLM (cost optimization)
        temperature: LLM temperature (0-2)
        max_tokens: Maximum tokens in response
        
    Returns:
        List of tag strings
    """
    if not api_key:
        api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError("OpenAI API key not found. Set OPENAI_API_KEY environment variable or pass api_key parameter.")
    
    client = OpenAI(api_key=api_key)
    
    # Truncate text to save tokens
    text_preview = text[:max_text_length] if len(text) > max_text_length else text
    if len(text) > max_text_length:
        text_preview += f"\n\n... (truncated, total length: {len(text)} characters)"
    
    # Use custom or default prompt template
    template = prompt_template if prompt_template else DEFAULT_TAGGING_PROMPT
    
    # Prepare variables for template
    template_vars = {
        'text': text_preview,
        'filename': filename,
    }
    
    # Add metadata fields if available
    if metadata:
        for key, value in metadata.items():
            template_vars[key] = value
    
    # Format the prompt
    try:
        prompt = template.format(**template_vars)
    except KeyError as e:
        # If template has variables we don't have, just use what we can
        prompt = template.format(text=text_preview, filename=filename)
    
    # Call OpenAI API
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful assistant that generates relevant tags for documents. Always respond with valid JSON arrays."},
                {"role": "user", "content": prompt}
            ],
            temperature=temperature,
            max_tokens=max_tokens
        )
        
        # Extract response
        content = response.choices[0].message.content.strip()
        
        # Parse tags from response
        tags = parse_tag_response(content)
        
        return tags
        
    except Exception as e:
        raise Exception(f"Error calling OpenAI API: {str(e)}")

def parse_tag_response(response: str) -> List[str]:
    """
    Parse tag response from OpenAI into a list of strings.
    Handles both JSON arrays and comma-separated lists.
    """
    # Try to parse as JSON first
    try:
        # Remove markdown code blocks if present
        if response.startswith("```"):
            # Extract JSON from code block
            lines = response.split("\n")
            json_lines = []
            in_code_block = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_code_block = not in_code_block
                    continue
                if in_code_block or (not line.strip().startswith("```") and json_lines):
                    json_lines.append(line)
            response = "\n".join(json_lines)
        
        tags = json.loads(response)
        
        # Ensure it's a list
        if isinstance(tags, list):
            # Clean and validate tags
            cleaned_tags = []
            for tag in tags:
                if isinstance(tag, str):
                    tag = tag.strip().lower()
                    if tag and len(tag) > 0:
                        cleaned_tags.append(tag)
            return cleaned_tags
        else:
            raise ValueError("Response is not a JSON array")
            
    except (json.JSONDecodeError, ValueError):
        # Fallback: try to extract tags from text
        # Look for comma-separated values or quoted strings
        tags = []
        
        # Try splitting by comma
        parts = response.replace("[", "").replace("]", "").replace('"', "").replace("'", "").split(",")
        for part in parts:
            tag = part.strip().lower()
            if tag and len(tag) > 0:
                tags.append(tag)
        
        return tags if tags else ["untagged"]

def validate_tags(tags: List[str], max_tags: int = 20, max_tag_length: int = 100) -> List[str]:
    """
    Validate and clean tags.
    
    Args:
        tags: List of tag strings
        max_tags: Maximum number of tags allowed
        max_tag_length: Maximum length of each tag
        
    Returns:
        Cleaned and validated list of tags
    """
    if not tags:
        return []
    
    validated = []
    for tag in tags[:max_tags]:
        if isinstance(tag, str):
            # Clean the tag
            tag = tag.strip().lower()
            tag = tag[:max_tag_length]
            
            # Skip empty or very short tags
            if len(tag) > 1:
                validated.append(tag)
    
    return validated

def get_tagging_config(product_config: Dict) -> Dict:
    """
    Extract tagging configuration from product config.
    
    Args:
        product_config: Product configuration dictionary
        
    Returns:
        Dictionary with tagging settings
    """
    tagging_config = product_config.get('tagging_config', {})
    
    return {
        'model': product_config.get('tagging_model', 'gpt-4o-mini'),
        'prompt_template': product_config.get('tagging_prompt_template'),
        'temperature': tagging_config.get('temperature', 0.3),
        'max_tokens': tagging_config.get('max_tokens', 500),
        'max_text_length': tagging_config.get('max_text_length', 8000)
    }

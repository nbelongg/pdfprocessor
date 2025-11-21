"""
Unit tests for utils/tagger.py module.

Tests AI-powered document tagging:
- Tag generation with mocked LLM
- Tag validation
- Prompt template substitution
- Text truncation for long documents
- JSON parsing errors
- API error handling
"""

import pytest
from unittest.mock import patch, MagicMock
import json

from utils.tagger import (
    generate_tags_with_openai,
    parse_tag_response,
    validate_tags,
    get_tagging_config,
    DEFAULT_TAGGING_PROMPT
)


@pytest.mark.unit
class TestGenerateTagsWithOpenAI:
    """Test tag generation with OpenAI API."""

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_success(self, mock_openai_class):
        """Test successful tag generation."""
        # Setup mock OpenAI client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["machine-learning", "neural-networks", "deep-learning"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # Call function
        tags = generate_tags_with_openai(
            text="This paper discusses machine learning and neural networks...",
            filename="ml_paper.pdf",
            api_key="sk-test"
        )

        # Verify results
        assert len(tags) == 3
        assert "machine-learning" in tags
        assert "neural-networks" in tags
        assert "deep-learning" in tags

        # Verify API was called correctly
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs['model'] == 'gpt-4o-mini'
        assert call_kwargs['temperature'] == 0.3
        assert call_kwargs['max_tokens'] == 500

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_with_custom_model(self, mock_openai_class):
        """Test tag generation with custom model."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["tag1", "tag2"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        tags = generate_tags_with_openai(
            text="Test text",
            filename="test.pdf",
            model="gpt-4o",
            api_key="sk-test"
        )

        # Verify custom model was used
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs['model'] == 'gpt-4o'

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_text_truncation(self, mock_openai_class):
        """Test that long text is truncated."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["tag1"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        # Create very long text (20,000 characters)
        long_text = "Lorem ipsum " * 2000

        tags = generate_tags_with_openai(
            text=long_text,
            filename="long_doc.pdf",
            api_key="sk-test",
            max_text_length=8000
        )

        # Verify API was called
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        prompt_content = call_kwargs['messages'][1]['content']

        # The prompt should contain truncated marker
        assert "truncated" in prompt_content
        assert "total length: 24000" in prompt_content  # Original length mentioned

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_custom_prompt_template(self, mock_openai_class):
        """Test tag generation with custom prompt template."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["custom-tag"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        custom_template = "Analyze {filename} and generate tags: {text}"

        tags = generate_tags_with_openai(
            text="Sample text",
            filename="custom.pdf",
            prompt_template=custom_template,
            api_key="sk-test"
        )

        # Verify custom template was used
        call_kwargs = mock_client.chat.completions.create.call_args[1]
        prompt = call_kwargs['messages'][1]['content']
        assert "custom.pdf" in prompt
        assert "Analyze" in prompt

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_with_metadata(self, mock_openai_class):
        """Test tag generation with additional metadata."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["tag1"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        metadata = {
            'paper_title': 'Machine Learning Paper',
            'authors': 'John Doe',
            'year': '2024'
        }

        tags = generate_tags_with_openai(
            text="Sample text",
            filename="paper.pdf",
            metadata=metadata,
            api_key="sk-test"
        )

        # Metadata should be available for template variables
        assert len(tags) > 0

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_api_error(self, mock_openai_class):
        """Test handling of API errors."""
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error: Rate limit")
        mock_openai_class.return_value = mock_client

        with pytest.raises(Exception, match="Error calling OpenAI API"):
            generate_tags_with_openai(
                text="Test text",
                filename="test.pdf",
                api_key="sk-test"
            )

    @patch.dict('os.environ', {}, clear=True)
    def test_generate_tags_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        with pytest.raises(ValueError, match="OpenAI API key not found"):
            generate_tags_with_openai(
                text="Test text",
                filename="test.pdf"
            )

    @patch.dict('os.environ', {'OPENAI_API_KEY': 'sk-env-key'})
    @patch('utils.tagger.OpenAI')
    def test_generate_tags_uses_env_api_key(self, mock_openai_class):
        """Test that API key is read from environment if not provided."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["tag1"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        tags = generate_tags_with_openai(
            text="Test text",
            filename="test.pdf"
        )

        # Should use environment key
        mock_openai_class.assert_called_once_with(api_key='sk-env-key')

    @patch('utils.tagger.OpenAI')
    def test_generate_tags_custom_temperature(self, mock_openai_class):
        """Test tag generation with custom temperature."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = '["tag1"]'
        mock_client.chat.completions.create.return_value = mock_response
        mock_openai_class.return_value = mock_client

        tags = generate_tags_with_openai(
            text="Test",
            filename="test.pdf",
            temperature=0.7,
            api_key="sk-test"
        )

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs['temperature'] == 0.7


@pytest.mark.unit
class TestParseTagResponse:
    """Test tag response parsing."""

    def test_parse_json_array(self):
        """Test parsing valid JSON array."""
        response = '["machine-learning", "neural-networks", "deep-learning"]'
        tags = parse_tag_response(response)

        assert len(tags) == 3
        assert "machine-learning" in tags
        assert "neural-networks" in tags

    def test_parse_json_with_code_blocks(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = '''```json
["machine-learning", "neural-networks", "deep-learning"]
```'''
        tags = parse_tag_response(response)

        assert len(tags) == 3
        assert "machine-learning" in tags

    def test_parse_json_with_whitespace(self):
        """Test parsing JSON with extra whitespace."""
        response = '''

        ["machine-learning", "neural-networks"]

        '''
        tags = parse_tag_response(response)

        assert len(tags) == 2

    def test_parse_comma_separated_fallback(self):
        """Test fallback to comma-separated parsing."""
        response = 'machine-learning, neural-networks, deep-learning'
        tags = parse_tag_response(response)

        assert len(tags) == 3
        assert "machine-learning" in tags

    def test_parse_comma_separated_with_quotes(self):
        """Test parsing comma-separated with quotes."""
        response = '"machine-learning", "neural-networks", "deep-learning"'
        tags = parse_tag_response(response)

        assert len(tags) == 3

    def test_parse_invalid_json_returns_fallback(self):
        """Test that invalid JSON returns fallback tags."""
        response = 'This is not JSON or valid format'
        tags = parse_tag_response(response)

        # Should extract something or return untagged
        assert isinstance(tags, list)
        assert len(tags) > 0

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        response = '[]'
        tags = parse_tag_response(response)

        assert tags == []

    def test_parse_mixed_case_tags(self):
        """Test that tags are converted to lowercase."""
        response = '["Machine-Learning", "NEURAL-NETWORKS", "Deep-Learning"]'
        tags = parse_tag_response(response)

        assert all(tag.islower() for tag in tags)

    def test_parse_tags_with_spaces(self):
        """Test handling of tags with leading/trailing spaces."""
        response = '["  machine-learning  ", "  neural-networks  "]'
        tags = parse_tag_response(response)

        assert "machine-learning" in tags
        assert "neural-networks" in tags
        # No spaces in tags
        assert not any("  " in tag for tag in tags)

    def test_parse_non_string_in_array(self):
        """Test handling of non-string items in JSON array."""
        response = '["machine-learning", 123, "neural-networks", null]'
        tags = parse_tag_response(response)

        # Should filter out non-strings
        assert "machine-learning" in tags
        assert "neural-networks" in tags
        assert len(tags) == 2


@pytest.mark.unit
class TestValidateTags:
    """Test tag validation and cleaning."""

    def test_validate_normal_tags(self):
        """Test validation of normal tags."""
        tags = ["machine-learning", "neural-networks", "deep-learning"]
        validated = validate_tags(tags)

        assert len(validated) == 3
        assert validated == tags

    def test_validate_empty_list(self):
        """Test validation of empty list."""
        validated = validate_tags([])

        assert validated == []

    def test_validate_max_tags_limit(self):
        """Test that max_tags limit is enforced."""
        tags = [f"tag-{i}" for i in range(30)]
        validated = validate_tags(tags, max_tags=10)

        assert len(validated) == 10

    def test_validate_max_tag_length(self):
        """Test that max tag length is enforced."""
        tags = ["short-tag", "a" * 200]  # Second tag is very long
        validated = validate_tags(tags, max_tag_length=50)

        assert len(validated) == 2
        assert len(validated[0]) <= 50
        assert len(validated[1]) <= 50

    def test_validate_removes_empty_tags(self):
        """Test that empty tags are removed."""
        tags = ["machine-learning", "", "neural-networks", "  "]
        validated = validate_tags(tags)

        assert len(validated) == 2
        assert "machine-learning" in validated
        assert "neural-networks" in validated

    def test_validate_removes_single_char_tags(self):
        """Test that single character tags are removed."""
        tags = ["machine-learning", "a", "neural-networks", "b"]
        validated = validate_tags(tags)

        # Single char tags should be filtered
        assert len(validated) == 2
        assert "machine-learning" in validated
        assert "neural-networks" in validated

    def test_validate_lowercase_conversion(self):
        """Test that tags are converted to lowercase."""
        tags = ["Machine-Learning", "NEURAL-NETWORKS", "Deep-Learning"]
        validated = validate_tags(tags)

        assert all(tag.islower() for tag in validated)

    def test_validate_strips_whitespace(self):
        """Test that whitespace is stripped."""
        tags = ["  machine-learning  ", "\tneural-networks\t", "\ndeep-learning\n"]
        validated = validate_tags(tags)

        assert "machine-learning" in validated
        assert "neural-networks" in validated
        assert "deep-learning" in validated

    def test_validate_non_string_items(self):
        """Test handling of non-string items."""
        tags = ["machine-learning", 123, None, "neural-networks"]
        validated = validate_tags(tags)

        # Only strings should remain
        assert len(validated) == 2
        assert "machine-learning" in validated
        assert "neural-networks" in validated

    def test_validate_default_limits(self):
        """Test default max_tags and max_tag_length limits."""
        tags = [f"tag-{i}" for i in range(25)]
        validated = validate_tags(tags)

        # Default max is 20
        assert len(validated) == 20


@pytest.mark.unit
class TestGetTaggingConfig:
    """Test tagging configuration extraction."""

    def test_get_tagging_config_with_all_settings(self):
        """Test extracting full tagging configuration."""
        product_config = {
            'tagging_model': 'gpt-4o',
            'tagging_prompt_template': 'Custom prompt: {text}',
            'tagging_config': {
                'temperature': 0.5,
                'max_tokens': 1000,
                'max_text_length': 10000
            }
        }

        config = get_tagging_config(product_config)

        assert config['model'] == 'gpt-4o'
        assert config['prompt_template'] == 'Custom prompt: {text}'
        assert config['temperature'] == 0.5
        assert config['max_tokens'] == 1000
        assert config['max_text_length'] == 10000

    def test_get_tagging_config_with_defaults(self):
        """Test that defaults are used when settings missing."""
        product_config = {}

        config = get_tagging_config(product_config)

        # Should use defaults
        assert config['model'] == 'gpt-4o-mini'
        assert config['prompt_template'] is None
        assert config['temperature'] == 0.3
        assert config['max_tokens'] == 500
        assert config['max_text_length'] == 8000

    def test_get_tagging_config_partial_settings(self):
        """Test with partial configuration."""
        product_config = {
            'tagging_model': 'gpt-4o',
            'tagging_config': {
                'temperature': 0.7
                # Other settings missing
            }
        }

        config = get_tagging_config(product_config)

        assert config['model'] == 'gpt-4o'
        assert config['temperature'] == 0.7
        # Defaults for missing settings
        assert config['max_tokens'] == 500
        assert config['max_text_length'] == 8000


@pytest.mark.unit
class TestDefaultPrompt:
    """Test default tagging prompt."""

    def test_default_prompt_has_placeholders(self):
        """Test that default prompt has required placeholders."""
        assert '{filename}' in DEFAULT_TAGGING_PROMPT
        assert '{text}' in DEFAULT_TAGGING_PROMPT

    def test_default_prompt_requests_json(self):
        """Test that default prompt requests JSON format."""
        assert 'JSON' in DEFAULT_TAGGING_PROMPT or 'json' in DEFAULT_TAGGING_PROMPT

    def test_default_prompt_gives_instructions(self):
        """Test that default prompt provides clear instructions."""
        prompt_lower = DEFAULT_TAGGING_PROMPT.lower()
        assert 'tag' in prompt_lower or 'label' in prompt_lower
        assert 'array' in prompt_lower or 'list' in prompt_lower

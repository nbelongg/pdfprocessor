"""
Unit tests for config_builder module (utils/config_builder.py).

Tests centralized product configuration building.
"""

import pytest
from unittest.mock import patch, MagicMock
from utils.config_builder import (
    build_product_config,
    get_product_config_from_source,
    PRODUCT_CONFIG_MAPPING,
    PRODUCT_SETTINGS_MAPPING
)


@pytest.mark.unit
class TestConstants:
    """Test constant definitions."""
    
    def test_product_config_mapping_exists(self):
        """Test that PRODUCT_CONFIG_MAPPING is properly defined."""
        assert 'llama_api_key' in PRODUCT_CONFIG_MAPPING
        assert 'openai_api_key' in PRODUCT_CONFIG_MAPPING
        assert 'pinecone_api_key' in PRODUCT_CONFIG_MAPPING
        assert 'google_credentials' in PRODUCT_CONFIG_MAPPING
    
    def test_product_settings_mapping_exists(self):
        """Test that PRODUCT_SETTINGS_MAPPING is properly defined."""
        assert 'index_name' in PRODUCT_SETTINGS_MAPPING
        assert 'chunk_size' in PRODUCT_SETTINGS_MAPPING
        assert 'embedding_model' in PRODUCT_SETTINGS_MAPPING
        assert 'parsing_mode' in PRODUCT_SETTINGS_MAPPING
    
    def test_mapping_values_are_strings(self):
        """Test that all mapping values are strings."""
        for key, value in PRODUCT_CONFIG_MAPPING.items():
            assert isinstance(value, str)
        
        for key, value in PRODUCT_SETTINGS_MAPPING.items():
            assert isinstance(value, str)


@pytest.mark.unit
class TestBuildProductConfig:
    """Test build_product_config function."""
    
    @patch('utils.config_builder.get_product')
    @patch('utils.config_builder.get_product_api_keys')
    def test_build_basic_config(self, mock_api_keys, mock_get_product, sample_product):
        """Test building basic product configuration."""
        mock_get_product.return_value = sample_product
        mock_api_keys.return_value = {
            'LLAMA_CLOUD_API_KEY': 'llx-test',
            'OPENAI_API_KEY': 'sk-test',
            'PINECONE_API_KEY': 'pc-test',
            'GOOGLE_CREDENTIALS': '{"type":"service_account"}'
        }
        
        config = build_product_config(product_id=1)
        
        assert config['llama_api_key'] == 'llx-test'
        assert config['openai_api_key'] == 'sk-test'
        assert config['pinecone_api_key'] == 'pc-test'
        assert config['index_name'] == 'test-index'
        assert config['chunk_size'] == 1024
    
    @patch('utils.config_builder.get_product')
    @patch('utils.config_builder.get_product_api_keys')
    def test_build_with_base_config(self, mock_api_keys, mock_get_product, sample_product):
        """Test building config with base configuration."""
        mock_get_product.return_value = sample_product
        mock_api_keys.return_value = {
            'LLAMA_CLOUD_API_KEY': 'llx-test',
            'OPENAI_API_KEY': 'sk-test',
            'PINECONE_API_KEY': 'pc-test'
        }
        
        base_config = {
            'custom_setting': 'custom_value',
            'another_setting': 123
        }
        
        config = build_product_config(product_id=1, base_config=base_config)
        
        # Base config should be preserved
        assert config['custom_setting'] == 'custom_value'
        assert config['another_setting'] == 123
        
        # Product settings should be added
        assert config['index_name'] == 'test-index'
        assert config['llama_api_key'] == 'llx-test'
    
    @patch('utils.config_builder.get_product')
    def test_product_not_found(self, mock_get_product):
        """Test error handling when product not found."""
        mock_get_product.return_value = None
        
        with pytest.raises(ValueError, match="Product .* not found"):
            build_product_config(product_id=999)
    
    @patch('utils.config_builder.get_product')
    @patch('utils.config_builder.get_product_api_keys')
    def test_missing_required_api_keys(self, mock_api_keys, mock_get_product, sample_product):
        """Test error when required API keys are missing."""
        mock_get_product.return_value = sample_product
        mock_api_keys.return_value = {
            'LLAMA_CLOUD_API_KEY': 'llx-test'
            # Missing OPENAI and PINECONE keys
        }
        
        with pytest.raises(ValueError, match="Missing required API keys"):
            build_product_config(product_id=1)
    
    @patch('utils.config_builder.get_product')
    @patch('utils.config_builder.get_product_api_keys')
    def test_inactive_product_warning(self, mock_api_keys, mock_get_product, sample_product):
        """Test warning when product is inactive."""
        inactive_product = {**sample_product, 'active': False}
        mock_get_product.return_value = inactive_product
        mock_api_keys.return_value = {
            'LLAMA_CLOUD_API_KEY': 'llx-test',
            'OPENAI_API_KEY': 'sk-test',
            'PINECONE_API_KEY': 'pc-test'
        }
        
        # Should not raise error, just log warning
        config = build_product_config(product_id=1)
        assert 'index_name' in config
    
    @patch('utils.config_builder.get_product')
    @patch('utils.config_builder.get_product_api_keys')
    def test_all_settings_mapped(self, mock_api_keys, mock_get_product, sample_product):
        """Test that all settings from mapping are applied."""
        mock_get_product.return_value = sample_product
        mock_api_keys.return_value = {
            'LLAMA_CLOUD_API_KEY': 'llx-test',
            'OPENAI_API_KEY': 'sk-test',
            'PINECONE_API_KEY': 'pc-test',
            'GOOGLE_CREDENTIALS': '{}'
        }
        
        config = build_product_config(product_id=1)
        
        # Check API keys are mapped
        assert 'llama_api_key' in config
        assert 'openai_api_key' in config
        assert 'pinecone_api_key' in config
        assert 'google_credentials' in config
        
        # Check settings are mapped
        assert config['index_name'] == sample_product['pinecone_index']
        assert config['chunk_size'] == sample_product['default_chunk_size']
        assert config['embedding_model'] == sample_product['default_embedding_model']
        assert config['parsing_mode'] == sample_product['parsing_mode']


@pytest.mark.unit
class TestGetProductConfigFromSource:
    """Test get_product_config_from_source function."""
    
    @patch('utils.config_builder.get_data_source')
    @patch('utils.config_builder.build_product_config')
    def test_build_from_source(self, mock_build, mock_get_source):
        """Test building config from data source ID."""
        mock_get_source.return_value = {
            'id': 1,
            'name': 'Test Source',
            'product_id': 5
        }
        mock_build.return_value = {'config': 'data'}
        
        config = get_product_config_from_source(source_id=1)
        
        assert config == {'config': 'data'}
        mock_build.assert_called_once_with(5, base_config=None)
    
    @patch('utils.config_builder.get_data_source')
    def test_source_not_found(self, mock_get_source):
        """Test error when data source not found."""
        mock_get_source.return_value = None
        
        with pytest.raises(ValueError, match="Data source .* not found"):
            get_product_config_from_source(source_id=999)
    
    @patch('utils.config_builder.get_data_source')
    def test_source_no_product(self, mock_get_source):
        """Test error when source has no product assigned."""
        mock_get_source.return_value = {
            'id': 1,
            'name': 'Test Source',
            'product_id': None
        }
        
        with pytest.raises(ValueError, match="has no product assigned"):
            get_product_config_from_source(source_id=1)

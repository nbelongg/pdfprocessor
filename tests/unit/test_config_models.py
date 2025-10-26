"""
Unit tests for configuration models (config/models.py).

Tests type-safe configuration dataclasses with validation.
"""

import pytest
from config.models import (
    ParsingConfig,
    ChunkingConfig,
    EmbeddingConfig,
    PineconeConfig,
    TaggingConfig,
    ProcessingConfig
)


# ============================================
# ParsingConfig Tests
# ============================================

@pytest.mark.unit
class TestParsingConfig:
    """Test ParsingConfig dataclass."""
    
    def test_valid_config_auto_mode(self):
        """Test creating valid parsing config with auto mode."""
        config = ParsingConfig(parsing_mode='auto')
        assert config.parsing_mode == 'auto'
        assert config.result_type == 'markdown'  # default
        assert config.language == 'en'  # default
    
    def test_valid_config_fast_mode(self):
        """Test creating valid parsing config with fast mode."""
        config = ParsingConfig(parsing_mode='fast', result_type='text')
        assert config.parsing_mode == 'fast'
        assert config.result_type == 'text'
    
    def test_invalid_parsing_mode(self):
        """Test that invalid parsing_mode raises ValueError."""
        with pytest.raises(ValueError, match="parsing_mode must be one of"):
            ParsingConfig(parsing_mode='invalid_mode')
    
    def test_invalid_result_type(self):
        """Test that invalid result_type raises ValueError."""
        with pytest.raises(ValueError, match="result_type must be one of"):
            ParsingConfig(result_type='invalid')
    
    def test_from_dict(self):
        """Test creating config from dictionary."""
        data = {
            'parsing_mode': 'premium',
            'result_type': 'text',
            'language': 'es',
            'extra_key': 'ignored'
        }
        config = ParsingConfig.from_dict(data)
        assert config.parsing_mode == 'premium'
        assert config.result_type == 'text'
        assert config.language == 'es'
    
    def test_to_dict(self):
        """Test converting config to dictionary."""
        config = ParsingConfig(parsing_mode='fast', language='fr')
        d = config.to_dict()
        assert d['parsing_mode'] == 'fast'
        assert d['language'] == 'fr'
        assert 'result_type' in d


# ============================================
# ChunkingConfig Tests
# ============================================

@pytest.mark.unit
class TestChunkingConfig:
    """Test ChunkingConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid chunking config."""
        config = ChunkingConfig(
            strategy='Token-based',
            chunk_size=512,
            chunk_overlap=50
        )
        assert config.strategy == 'Token-based'
        assert config.chunk_size == 512
        assert config.chunk_overlap == 50
    
    def test_invalid_strategy(self):
        """Test that invalid strategy raises ValueError."""
        with pytest.raises(ValueError, match="strategy must be one of"):
            ChunkingConfig(strategy='invalid')
    
    def test_chunk_size_too_small(self):
        """Test that chunk_size < 100 raises ValueError."""
        with pytest.raises(ValueError, match="chunk_size must be >= 100"):
            ChunkingConfig(chunk_size=50)
    
    def test_chunk_overlap_too_large(self):
        """Test that overlap >= chunk_size raises ValueError."""
        with pytest.raises(ValueError, match="chunk_overlap must be < chunk_size"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)
    
    def test_semantic_buffer_size_negative(self):
        """Test that negative semantic_buffer_size raises ValueError."""
        with pytest.raises(ValueError, match="semantic_buffer_size must be >= 1"):
            ChunkingConfig(semantic_buffer_size=0)
    
    def test_defaults(self):
        """Test default values."""
        config = ChunkingConfig()
        assert config.strategy == 'Token-based'
        assert config.chunk_size == 1024
        assert config.chunk_overlap == 200


# ============================================
# EmbeddingConfig Tests
# ============================================

@pytest.mark.unit
class TestEmbeddingConfig:
    """Test EmbeddingConfig dataclass."""
    
    def test_valid_config_small_model(self):
        """Test creating valid embedding config with small model."""
        config = EmbeddingConfig(
            model='text-embedding-3-small',
            api_key='sk-test'
        )
        assert config.model == 'text-embedding-3-small'
        assert config.dimension == 1536  # default for small
    
    def test_valid_config_large_model(self):
        """Test creating valid embedding config with large model."""
        config = EmbeddingConfig(
            model='text-embedding-3-large',
            api_key='sk-test',
            dimension=3072
        )
        assert config.model == 'text-embedding-3-large'
        assert config.dimension == 3072
    
    def test_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        with pytest.raises(ValueError, match="api_key is required"):
            EmbeddingConfig(model='text-embedding-3-small', api_key='')
    
    def test_invalid_dimension(self):
        """Test that invalid dimension raises ValueError."""
        with pytest.raises(ValueError, match="dimension must be > 0"):
            EmbeddingConfig(
                model='text-embedding-3-small',
                dimension=0,
                api_key='sk-test'
            )
    
    def test_legacy_keys_from_dict(self):
        """Test backward compatibility with legacy dict keys."""
        data = {
            'embedding_model': 'text-embedding-3-large',
            'openai_api_key': 'sk-legacy',
            'embedding_dimension': 2048
        }
        config = EmbeddingConfig.from_dict(data)
        assert config.model == 'text-embedding-3-large'
        assert config.api_key == 'sk-legacy'
        assert config.dimension == 2048


# ============================================
# PineconeConfig Tests
# ============================================

@pytest.mark.unit
class TestPineconeConfig:
    """Test PineconeConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid Pinecone config."""
        config = PineconeConfig(
            api_key='pc-test',
            index_name='my-index',
            environment='us-east-1'
        )
        assert config.api_key == 'pc-test'
        assert config.index_name == 'my-index'
        assert config.environment == 'us-east-1'
    
    def test_missing_api_key(self):
        """Test that missing API key raises ValueError."""
        with pytest.raises(ValueError, match="api_key is required"):
            PineconeConfig(api_key='', index_name='test')
    
    def test_missing_index_name(self):
        """Test that missing index_name raises ValueError."""
        with pytest.raises(ValueError, match="index_name is required"):
            PineconeConfig(api_key='pc-test', index_name='')


# ============================================
# TaggingConfig Tests
# ============================================

@pytest.mark.unit
class TestTaggingConfig:
    """Test TaggingConfig dataclass."""
    
    def test_valid_config_enabled(self):
        """Test creating valid tagging config when enabled."""
        config = TaggingConfig(
            enabled=True,
            model='gpt-4o',
            api_key='sk-test'
        )
        assert config.enabled is True
        assert config.model == 'gpt-4o'
    
    def test_disabled_config(self):
        """Test tagging config when disabled."""
        config = TaggingConfig(enabled=False)
        assert config.enabled is False
        assert config.model == 'gpt-4o-mini'  # default
    
    def test_custom_prompt(self):
        """Test custom prompt template."""
        prompt = "Tag this document: {text}"
        config = TaggingConfig(
            enabled=True,
            api_key='sk-test',
            prompt_template=prompt
        )
        assert config.prompt_template == prompt


# ============================================
# ProcessingConfig Tests
# ============================================

@pytest.mark.unit
class TestProcessingConfig:
    """Test ProcessingConfig dataclass."""
    
    def test_from_flat_dict(self):
        """Test creating ProcessingConfig from flat dictionary."""
        data = {
            'parsing_mode': 'premium',
            'result_type': 'text',
            'chunk_size': 2048,
            'chunking_strategy': 'Sentence-based',
            'embedding_model': 'text-embedding-3-large',
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'my-index',
            'tagging_enabled': True
        }
        
        config = ProcessingConfig.from_dict(data)
        
        assert config.parsing.parsing_mode == 'premium'
        assert config.parsing.result_type == 'text'
        assert config.chunking.chunk_size == 2048
        assert config.chunking.strategy == 'Sentence-based'
        assert config.embedding.model == 'text-embedding-3-large'
        assert config.pinecone.index_name == 'my-index'
        assert config.tagging.enabled is True
    
    def test_to_flat_dict(self):
        """Test converting ProcessingConfig to flat dictionary."""
        config = ProcessingConfig(
            parsing=ParsingConfig(parsing_mode='auto'),
            chunking=ChunkingConfig(chunk_size=512),
            embedding=EmbeddingConfig(
                model='text-embedding-3-small',
                api_key='sk-test'
            ),
            pinecone=PineconeConfig(
                api_key='pc-test',
                index_name='test-index'
            )
        )
        
        d = config.to_dict()
        
        assert d['parsing_mode'] == 'auto'
        assert d['chunk_size'] == 512
        assert d['embedding_model'] == 'text-embedding-3-small'
        assert d['index_name'] == 'test-index'
    
    def test_nested_validation(self):
        """Test that nested config validation works."""
        data = {
            'parsing_mode': 'invalid',  # Should raise error
            'chunk_size': 1024,
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'test'
        }
        
        with pytest.raises(ValueError, match="parsing_mode"):
            ProcessingConfig.from_dict(data)

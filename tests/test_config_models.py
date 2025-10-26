"""
Unit tests for type-safe configuration models.

Tests validation, backward compatibility, and error handling.
"""

import pytest
from config.models import (
    ParsingConfig, ChunkingConfig, EmbeddingConfig, TaggingConfig,
    PineconeConfig, GoogleConfig, DeduplicationConfig, ScheduleConfig,
    ProcessingConfig
)


class TestParsingConfig:
    """Tests for ParsingConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid parsing config."""
        config = ParsingConfig(parsing_mode='auto', result_type='markdown')
        assert config.parsing_mode == 'auto'
        assert config.result_type == 'markdown'
        assert config.language == 'en'
    
    def test_invalid_parsing_mode(self):
        """Test that invalid parsing mode raises error."""
        with pytest.raises(ValueError, match="parsing_mode must be one of"):
            ParsingConfig(parsing_mode='invalid')
    
    def test_invalid_result_type(self):
        """Test that invalid result type raises error."""
        with pytest.raises(ValueError, match="result_type must be one of"):
            ParsingConfig(result_type='invalid')
    
    def test_invalid_language_code(self):
        """Test that invalid language code raises error."""
        with pytest.raises(ValueError, match="language must be 2-letter code"):
            ParsingConfig(language='english')
    
    def test_from_dict(self):
        """Test backward compatibility from dict."""
        data = {'parsing_mode': 'fast', 'result_type': 'text', 'extra_key': 'ignored'}
        config = ParsingConfig.from_dict(data)
        assert config.parsing_mode == 'fast'
        assert config.result_type == 'text'
    
    def test_to_dict(self):
        """Test conversion to dict."""
        config = ParsingConfig(parsing_mode='premium')
        d = config.to_dict()
        assert d['parsing_mode'] == 'premium'
        assert d['result_type'] == 'markdown'


class TestChunkingConfig:
    """Tests for ChunkingConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid chunking config."""
        config = ChunkingConfig(strategy='Token-based', chunk_size=512)
        assert config.strategy == 'Token-based'
        assert config.chunk_size == 512
    
    def test_invalid_strategy(self):
        """Test that invalid strategy raises error."""
        with pytest.raises(ValueError, match="strategy must be one of"):
            ChunkingConfig(strategy='invalid')
    
    def test_chunk_size_too_small(self):
        """Test that chunk_size < 100 raises error."""
        with pytest.raises(ValueError, match="chunk_size must be >= 100"):
            ChunkingConfig(chunk_size=50)
    
    def test_chunk_size_too_large(self):
        """Test that chunk_size > 8192 raises error."""
        with pytest.raises(ValueError, match="chunk_size must be <= 8192"):
            ChunkingConfig(chunk_size=10000)
    
    def test_overlap_too_large(self):
        """Test that overlap >= chunk_size raises error."""
        with pytest.raises(ValueError, match="chunk_overlap .* must be < chunk_size"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)
    
    def test_overlap_negative(self):
        """Test that negative overlap raises error."""
        with pytest.raises(ValueError, match="chunk_overlap must be >= 0"):
            ChunkingConfig(chunk_overlap=-10)
    
    def test_legacy_keys(self):
        """Test backward compatibility with legacy keys."""
        data = {
            'chunking_strategy': 'Sentence-based',
            'default_chunk_size': 2048
        }
        config = ChunkingConfig.from_dict(data)
        assert config.strategy == 'Sentence-based'
        assert config.chunk_size == 2048
    
    def test_to_dict_includes_legacy_keys(self):
        """Test that to_dict includes legacy keys."""
        config = ChunkingConfig(chunk_size=512)
        d = config.to_dict()
        assert d['chunking_strategy'] == 'Token-based'
        assert d['default_chunking_strategy'] == 'Token-based'
        assert d['default_chunk_size'] == 512


class TestEmbeddingConfig:
    """Tests for EmbeddingConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid embedding config."""
        config = EmbeddingConfig(
            model='text-embedding-3-small',
            api_key='sk-test'
        )
        assert config.model == 'text-embedding-3-small'
        assert config.api_key == 'sk-test'
    
    def test_missing_api_key(self):
        """Test that missing API key raises error."""
        with pytest.raises(ValueError, match="api_key is required"):
            EmbeddingConfig(model='text-embedding-3-small', api_key='')
    
    def test_invalid_model(self):
        """Test that invalid model raises error."""
        with pytest.raises(ValueError, match="model must contain one of"):
            EmbeddingConfig(model='invalid-model', api_key='sk-test')
    
    def test_custom_dimension(self):
        """Test custom dimension validation."""
        config = EmbeddingConfig(
            model='text-embedding-3-large',
            dimension=2048,
            api_key='sk-test'
        )
        assert config.dimension == 2048
    
    def test_invalid_dimension_zero(self):
        """Test that dimension = 0 raises error."""
        with pytest.raises(ValueError, match="dimension must be > 0"):
            EmbeddingConfig(
                model='text-embedding-3-small',
                dimension=0,
                api_key='sk-test'
            )
    
    def test_invalid_dimension_too_large(self):
        """Test that dimension > 3072 raises error."""
        with pytest.raises(ValueError, match="dimension must be <= 3072"):
            EmbeddingConfig(
                model='text-embedding-3-small',
                dimension=5000,
                api_key='sk-test'
            )
    
    def test_legacy_keys(self):
        """Test backward compatibility with legacy keys."""
        data = {
            'embedding_model': 'text-embedding-3-small',
            'openai_api_key': 'sk-test',
            'embedding_dimension': 1536
        }
        config = EmbeddingConfig.from_dict(data)
        assert config.model == 'text-embedding-3-small'
        assert config.api_key == 'sk-test'
        assert config.dimension == 1536
    
    def test_to_dict_includes_legacy_keys(self):
        """Test that to_dict includes legacy keys."""
        config = EmbeddingConfig(model='text-embedding-3-small', api_key='sk-test')
        d = config.to_dict()
        assert d['embedding_model'] == 'text-embedding-3-small'
        assert d['openai_api_key'] == 'sk-test'


class TestTaggingConfig:
    """Tests for TaggingConfig dataclass."""
    
    def test_disabled_config(self):
        """Test that disabled config doesn't require validation."""
        config = TaggingConfig(enabled=False)
        assert config.enabled is False
        # Should not raise even with empty api_key when disabled
    
    def test_enabled_requires_api_key(self):
        """Test that enabled config requires API key."""
        with pytest.raises(ValueError, match="api_key is required when tagging is enabled"):
            TaggingConfig(enabled=True, api_key='')
    
    def test_invalid_model(self):
        """Test that invalid model raises error when enabled."""
        with pytest.raises(ValueError, match="model must be one of"):
            TaggingConfig(enabled=True, model='invalid', api_key='sk-test')
    
    def test_max_tags_validation(self):
        """Test max_tags validation."""
        with pytest.raises(ValueError, match="max_tags must be >= 1"):
            TaggingConfig(enabled=True, max_tags=0, api_key='sk-test')
        
        with pytest.raises(ValueError, match="max_tags must be <= 50"):
            TaggingConfig(enabled=True, max_tags=100, api_key='sk-test')
    
    def test_valid_enabled_config(self):
        """Test valid enabled config."""
        config = TaggingConfig(
            enabled=True,
            model='gpt-4o',
            api_key='sk-test',
            max_tags=15
        )
        assert config.enabled is True
        assert config.model == 'gpt-4o'
        assert config.max_tags == 15
    
    def test_legacy_keys(self):
        """Test backward compatibility with legacy keys."""
        data = {
            'tagging_enabled': True,
            'tagging_model': 'gpt-4o-mini',
            'tagging_prompt_template': 'Generate tags: {text}',
            'openai_api_key': 'sk-test'
        }
        config = TaggingConfig.from_dict(data)
        assert config.enabled is True
        assert config.model == 'gpt-4o-mini'


class TestPineconeConfig:
    """Tests for PineconeConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid Pinecone config."""
        config = PineconeConfig(
            api_key='pc-test',
            index_name='my-index',
            environment='us-east-1'
        )
        assert config.api_key == 'pc-test'
        assert config.index_name == 'my-index'
    
    def test_missing_api_key(self):
        """Test that missing API key raises error."""
        with pytest.raises(ValueError, match="api_key is required"):
            PineconeConfig(api_key='', index_name='test')
    
    def test_missing_index_name(self):
        """Test that missing index name raises error."""
        with pytest.raises(ValueError, match="index_name is required"):
            PineconeConfig(api_key='pc-test', index_name='')
    
    def test_invalid_dimension(self):
        """Test that invalid dimension raises error."""
        with pytest.raises(ValueError, match="dimension must be > 0"):
            PineconeConfig(api_key='pc-test', index_name='test', dimension=0)
    
    def test_legacy_keys(self):
        """Test backward compatibility with legacy keys."""
        data = {
            'pinecone_api_key': 'pc-test',
            'pinecone_index': 'my-index',
            'pinecone_environment': 'us-west-1',
            'default_namespace': 'custom'
        }
        config = PineconeConfig.from_dict(data)
        assert config.api_key == 'pc-test'
        assert config.index_name == 'my-index'
        assert config.environment == 'us-west-1'
        assert config.namespace == 'custom'


class TestGoogleConfig:
    """Tests for GoogleConfig dataclass."""
    
    def test_valid_config_from_dict(self):
        """Test creating valid Google config from dict."""
        creds = {
            'type': 'service_account',
            'project_id': 'test-project',
            'private_key': '-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n',
            'client_email': 'test@test.iam.gserviceaccount.com'
        }
        config = GoogleConfig(credentials=creds)
        assert config.credentials['project_id'] == 'test-project'
    
    def test_valid_config_from_json_string(self):
        """Test creating valid Google config from JSON string."""
        creds_json = '{"type":"service_account","project_id":"test","private_key":"test","client_email":"test@test.com"}'
        config = GoogleConfig(credentials=creds_json)
        assert config.credentials['project_id'] == 'test'
    
    def test_missing_credentials(self):
        """Test that missing credentials raises error."""
        with pytest.raises(ValueError, match="Google credentials are required"):
            GoogleConfig(credentials='')
    
    def test_invalid_json(self):
        """Test that invalid JSON raises error."""
        with pytest.raises(ValueError, match="credentials must be valid JSON"):
            GoogleConfig(credentials='not-valid-json')
    
    def test_missing_required_keys(self):
        """Test that missing required keys raises error."""
        incomplete_creds = {'type': 'service_account'}
        with pytest.raises(ValueError, match="credentials missing required keys"):
            GoogleConfig(credentials=incomplete_creds)


class TestDeduplicationConfig:
    """Tests for DeduplicationConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid deduplication config."""
        config = DeduplicationConfig(
            enabled=True,
            check_layer1=True,
            check_layer2=True,
            check_layer3=False
        )
        assert config.enabled is True
        assert config.check_layer1 is True
    
    def test_similarity_threshold_range(self):
        """Test similarity threshold validation."""
        with pytest.raises(ValueError, match="similarity_threshold must be 0.0-1.0"):
            DeduplicationConfig(similarity_threshold=1.5)
        
        with pytest.raises(ValueError, match="similarity_threshold must be 0.0-1.0"):
            DeduplicationConfig(similarity_threshold=-0.1)
    
    def test_layer3_threshold_warning(self):
        """Test that layer3 with low threshold raises error."""
        with pytest.raises(ValueError, match="similarity_threshold should be >= 0.8"):
            DeduplicationConfig(check_layer3=True, similarity_threshold=0.5)
    
    def test_legacy_keys(self):
        """Test backward compatibility with legacy keys."""
        data = {
            'dedup_layer1': True,
            'dedup_layer2': False,
            'dedup_layer3': True,
            'similarity_threshold': 0.9
        }
        config = DeduplicationConfig.from_dict(data)
        assert config.check_layer1 is True
        assert config.check_layer2 is False
        assert config.check_layer3 is True


class TestScheduleConfig:
    """Tests for ScheduleConfig dataclass."""
    
    def test_valid_config(self):
        """Test creating valid schedule config."""
        config = ScheduleConfig(
            frequency='weekly',
            max_papers_per_run=50,
            enabled=True
        )
        assert config.frequency == 'weekly'
        assert config.max_papers_per_run == 50
    
    def test_invalid_frequency(self):
        """Test that invalid frequency raises error."""
        with pytest.raises(ValueError, match="frequency must be one of"):
            ScheduleConfig(frequency='hourly')
    
    def test_max_papers_validation(self):
        """Test max_papers_per_run validation."""
        with pytest.raises(ValueError, match="max_papers_per_run must be >= 1"):
            ScheduleConfig(max_papers_per_run=0)
        
        with pytest.raises(ValueError, match="max_papers_per_run must be <= 1000"):
            ScheduleConfig(max_papers_per_run=2000)


class TestProcessingConfig:
    """Tests for ProcessingConfig master config."""
    
    def test_from_flat_dict(self):
        """Test creating ProcessingConfig from flat dict."""
        data = {
            'parsing_mode': 'auto',
            'chunk_size': 1024,
            'embedding_model': 'text-embedding-3-small',
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'my-index',
            'google_credentials': '{"type":"service_account","project_id":"test","private_key":"test","client_email":"test@test.com"}',
        }
        
        config = ProcessingConfig.from_dict(data)
        
        assert config.parsing.parsing_mode == 'auto'
        assert config.chunking.chunk_size == 1024
        assert config.embedding.model == 'text-embedding-3-small'
        assert config.pinecone.index_name == 'my-index'
    
    def test_to_flat_dict(self):
        """Test converting ProcessingConfig to flat dict."""
        config = ProcessingConfig(
            parsing=ParsingConfig(parsing_mode='fast'),
            chunking=ChunkingConfig(chunk_size=512),
            embedding=EmbeddingConfig(model='text-embedding-3-small', api_key='sk-test'),
            pinecone=PineconeConfig(api_key='pc-test', index_name='test-index'),
            google=GoogleConfig(credentials={'type':'service_account','project_id':'test','private_key':'test','client_email':'test@test.com'})
        )
        
        d = config.to_dict()
        
        assert d['parsing_mode'] == 'fast'
        assert d['chunk_size'] == 512
        assert d['embedding_model'] == 'text-embedding-3-small'
        assert d['index_name'] == 'test-index'
    
    def test_default_factory(self):
        """Test that default factories create new instances."""
        config1 = ProcessingConfig()
        config2 = ProcessingConfig()
        
        # Should be different objects
        assert config1.parsing is not config2.parsing
        assert config1.chunking is not config2.chunking


if __name__ == '__main__':
    pytest.main([__file__, '-v'])

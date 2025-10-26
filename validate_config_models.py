"""
Simple validation script for config models (no pytest required).
"""

from config.models import (
    ParsingConfig, ChunkingConfig, EmbeddingConfig, TaggingConfig,
    PineconeConfig, GoogleConfig, DeduplicationConfig, ScheduleConfig,
    ProcessingConfig
)


def test_parsing_config():
    """Test ParsingConfig."""
    print("Testing ParsingConfig...")
    
    # Valid config
    config = ParsingConfig(parsing_mode='auto', result_type='markdown')
    assert config.parsing_mode == 'auto'
    
    # Invalid mode should raise
    try:
        ParsingConfig(parsing_mode='invalid')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "parsing_mode must be one of" in str(e)
    
    # from_dict compatibility
    data = {'parsing_mode': 'fast', 'result_type': 'text'}
    config = ParsingConfig.from_dict(data)
    assert config.parsing_mode == 'fast'
    
    # to_dict
    d = config.to_dict()
    assert d['parsing_mode'] == 'fast'
    
    print("✅ ParsingConfig passed")


def test_chunking_config():
    """Test ChunkingConfig."""
    print("Testing ChunkingConfig...")
    
    # Valid config
    config = ChunkingConfig(strategy='Token-based', chunk_size=512)
    assert config.chunk_size == 512
    
    # Invalid chunk size
    try:
        ChunkingConfig(chunk_size=50)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "chunk_size must be >= 100" in str(e)
    
    # Overlap too large
    try:
        ChunkingConfig(chunk_size=100, chunk_overlap=100)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "chunk_overlap" in str(e) and "must be <" in str(e)
    
    # Legacy keys
    data = {'chunking_strategy': 'Sentence-based', 'default_chunk_size': 2048}
    config = ChunkingConfig.from_dict(data)
    assert config.strategy == 'Sentence-based'
    assert config.chunk_size == 2048
    
    # to_dict includes legacy keys
    d = config.to_dict()
    assert d['chunking_strategy'] == 'Sentence-based'
    assert d['default_chunk_size'] == 2048
    
    print("✅ ChunkingConfig passed")


def test_embedding_config():
    """Test EmbeddingConfig."""
    print("Testing EmbeddingConfig...")
    
    # Valid config
    config = EmbeddingConfig(model='text-embedding-3-small', api_key='sk-test')
    assert config.model == 'text-embedding-3-small'
    
    # Empty API key is allowed for default construction (validation happens at usage time)
    config = EmbeddingConfig(model='text-embedding-3-small', api_key='')
    assert config.api_key == ''
    
    # Custom dimension
    config = EmbeddingConfig(
        model='text-embedding-3-large',
        dimension=2048,
        api_key='sk-test'
    )
    assert config.dimension == 2048
    
    # Invalid dimension
    try:
        EmbeddingConfig(model='text-embedding-3-small', dimension=0, api_key='sk-test')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "dimension must be > 0" in str(e)
    
    # Legacy keys
    data = {
        'embedding_model': 'text-embedding-3-small',
        'openai_api_key': 'sk-test',
        'embedding_dimension': 1536
    }
    config = EmbeddingConfig.from_dict(data)
    assert config.model == 'text-embedding-3-small'
    assert config.api_key == 'sk-test'
    assert config.dimension == 1536
    
    print("✅ EmbeddingConfig passed")


def test_tagging_config():
    """Test TaggingConfig."""
    print("Testing TaggingConfig...")
    
    # Disabled config doesn't require validation
    config = TaggingConfig(enabled=False)
    assert config.enabled is False
    
    # Enabled requires API key
    try:
        TaggingConfig(enabled=True, api_key='')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "api_key is required when tagging is enabled" in str(e)
    
    # Valid enabled config
    config = TaggingConfig(enabled=True, model='gpt-4o', api_key='sk-test', max_tags=15)
    assert config.enabled is True
    assert config.model == 'gpt-4o'
    
    # Invalid max_tags
    try:
        TaggingConfig(enabled=True, max_tags=0, api_key='sk-test')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "max_tags must be >= 1" in str(e)
    
    print("✅ TaggingConfig passed")


def test_pinecone_config():
    """Test PineconeConfig."""
    print("Testing PineconeConfig...")
    
    # Valid config
    config = PineconeConfig(api_key='pc-test', index_name='my-index')
    assert config.api_key == 'pc-test'
    assert config.index_name == 'my-index'
    
    # Empty API key and index allowed for default construction
    config = PineconeConfig(api_key='', index_name='')
    assert config.api_key == ''
    assert config.index_name == ''
    
    # Legacy keys
    data = {
        'pinecone_api_key': 'pc-test',
        'pinecone_index': 'my-index',
        'pinecone_environment': 'us-west-1'
    }
    config = PineconeConfig.from_dict(data)
    assert config.api_key == 'pc-test'
    assert config.index_name == 'my-index'
    assert config.environment == 'us-west-1'
    
    print("✅ PineconeConfig passed")


def test_google_config():
    """Test GoogleConfig."""
    print("Testing GoogleConfig...")
    
    # Valid config from dict
    creds = {
        'type': 'service_account',
        'project_id': 'test-project',
        'private_key': '-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n',
        'client_email': 'test@test.iam.gserviceaccount.com'
    }
    config = GoogleConfig(credentials=creds)
    assert config.credentials['project_id'] == 'test-project'
    
    # Valid config from JSON string
    creds_json = '{"type":"service_account","project_id":"test","private_key":"test","client_email":"test@test.com"}'
    config = GoogleConfig(credentials=creds_json)
    assert config.credentials['project_id'] == 'test'
    
    # Empty credentials allowed for default construction
    config = GoogleConfig(credentials='')
    assert config.credentials == ''
    
    # Invalid JSON
    try:
        GoogleConfig(credentials='not-valid-json')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "credentials must be valid JSON" in str(e)
    
    # Missing required keys
    try:
        GoogleConfig(credentials={'type': 'service_account'})
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "credentials missing required keys" in str(e)
    
    print("✅ GoogleConfig passed")


def test_deduplication_config():
    """Test DeduplicationConfig."""
    print("Testing DeduplicationConfig...")
    
    # Valid config
    config = DeduplicationConfig(enabled=True, check_layer1=True)
    assert config.enabled is True
    
    # Invalid threshold
    try:
        DeduplicationConfig(similarity_threshold=1.5)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "similarity_threshold must be 0.0-1.0" in str(e)
    
    # Layer3 with low threshold
    try:
        DeduplicationConfig(check_layer3=True, similarity_threshold=0.5)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "similarity_threshold should be >= 0.8" in str(e)
    
    # Legacy keys
    data = {
        'dedup_layer1': True,
        'dedup_layer2': False,
        'dedup_layer3': True,
        'similarity_threshold': 0.9
    }
    config = DeduplicationConfig.from_dict(data)
    assert config.check_layer1 is True
    assert config.check_layer2 is False
    
    print("✅ DeduplicationConfig passed")


def test_schedule_config():
    """Test ScheduleConfig."""
    print("Testing ScheduleConfig...")
    
    # Valid config
    config = ScheduleConfig(frequency='weekly', max_papers_per_run=50)
    assert config.frequency == 'weekly'
    assert config.max_papers_per_run == 50
    
    # Invalid frequency
    try:
        ScheduleConfig(frequency='hourly')
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "frequency must be one of" in str(e)
    
    # Invalid max_papers
    try:
        ScheduleConfig(max_papers_per_run=0)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "max_papers_per_run must be >= 1" in str(e)
    
    print("✅ ScheduleConfig passed")


def test_processing_config():
    """Test ProcessingConfig master config."""
    print("Testing ProcessingConfig...")
    
    # From flat dict
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
    
    # To flat dict
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
    
    # Default factories create new instances
    config1 = ProcessingConfig()
    config2 = ProcessingConfig()
    assert config1.parsing is not config2.parsing
    
    print("✅ ProcessingConfig passed")


def main():
    """Run all validation tests."""
    print("\n" + "="*60)
    print("VALIDATING TYPE-SAFE CONFIG MODELS")
    print("="*60 + "\n")
    
    try:
        test_parsing_config()
        test_chunking_config()
        test_embedding_config()
        test_tagging_config()
        test_pinecone_config()
        test_google_config()
        test_deduplication_config()
        test_schedule_config()
        test_processing_config()
        
        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED!")
        print("="*60)
        print("\nConfig models are working correctly:")
        print("  - All 9 dataclasses validated")
        print("  - Type checking works")
        print("  - Validation catches errors")
        print("  - Backward compatibility with legacy dicts")
        print("  - from_dict() / to_dict() conversion works")
        print("\n")
        
        return 0
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())

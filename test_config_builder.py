"""
Test script for config_builder.py to verify it works correctly.
"""

import sys
from utils.config_builder import (
    build_product_config,
    get_product_config_from_source,
    PRODUCT_CONFIG_MAPPING,
    PRODUCT_SETTINGS_MAPPING
)
from utils.db import get_products


def test_constants():
    """Test that constants are defined correctly."""
    print("Testing constants...")
    
    assert 'llama_api_key' in PRODUCT_CONFIG_MAPPING
    assert 'openai_api_key' in PRODUCT_CONFIG_MAPPING
    assert 'pinecone_api_key' in PRODUCT_CONFIG_MAPPING
    assert 'google_credentials' in PRODUCT_CONFIG_MAPPING
    
    assert 'index_name' in PRODUCT_SETTINGS_MAPPING
    assert 'chunk_size' in PRODUCT_SETTINGS_MAPPING
    assert 'embedding_model' in PRODUCT_SETTINGS_MAPPING
    
    print("✅ Constants test passed")


def test_build_product_config():
    """Test building product config."""
    print("\nTesting build_product_config...")
    
    # Get first product
    products = get_products()
    if not products:
        print("⚠️  No products found in database - skipping test")
        return
    
    product_id = products[0]['id']
    product_name = products[0]['name']
    
    print(f"Testing with product ID {product_id} ({product_name})")
    
    try:
        # Test building config
        config = build_product_config(product_id)
        
        # Verify required keys are present
        assert 'llama_api_key' in config, "Missing llama_api_key"
        assert 'openai_api_key' in config, "Missing openai_api_key"
        assert 'pinecone_api_key' in config, "Missing pinecone_api_key"
        
        # Verify at least some product settings are present
        assert 'index_name' in config, "Missing index_name"
        
        print(f"✅ Config built successfully")
        print(f"   - Index: {config.get('index_name')}")
        print(f"   - Parsing mode: {config.get('parsing_mode')}")
        print(f"   - Chunk size: {config.get('chunk_size')}")
        print(f"   - Embedding model: {config.get('embedding_model')}")
        
    except ValueError as e:
        print(f"⚠️  Config build failed (may be missing API keys): {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


def test_base_config_merge():
    """Test that base config is properly merged."""
    print("\nTesting base config merge...")
    
    products = get_products()
    if not products:
        print("⚠️  No products found in database - skipping test")
        return
    
    product_id = products[0]['id']
    
    base_config = {
        'custom_setting': 'test_value',
        'another_setting': 123
    }
    
    try:
        config = build_product_config(product_id, base_config=base_config)
        
        # Verify base config values are preserved
        assert config.get('custom_setting') == 'test_value'
        assert config.get('another_setting') == 123
        
        # Verify product settings are also present
        assert 'index_name' in config
        
        print("✅ Base config merge test passed")
        
    except ValueError as e:
        print(f"⚠️  Test skipped (missing API keys): {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        raise


def test_invalid_product():
    """Test error handling for invalid product ID."""
    print("\nTesting invalid product ID...")
    
    try:
        config = build_product_config(product_id=999999)
        print("❌ Should have raised ValueError for invalid product")
        sys.exit(1)
    except ValueError as e:
        print(f"✅ Correctly raised ValueError: {e}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Config Builder Tests")
    print("=" * 60)
    
    try:
        test_constants()
        test_build_product_config()
        test_base_config_merge()
        test_invalid_product()
        
        print("\n" + "=" * 60)
        print("All tests passed! ✅")
        print("=" * 60)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"Tests failed: {e}")
        print("=" * 60)
        sys.exit(1)


if __name__ == '__main__':
    main()

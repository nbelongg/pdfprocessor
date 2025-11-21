"""
Unit tests for utils/db/products.py module.

Tests product operations:
- Product CRUD operations
- API key retrieval via environment variables
- Product configuration management
- Active/inactive product filtering
"""

import pytest
from unittest.mock import patch, MagicMock
from psycopg2.extras import Json

from utils.db.products import (
    get_products,
    get_product,
    create_product,
    update_product,
    delete_product,
    get_product_api_keys
)


@pytest.mark.unit
class TestProductCRUD:
    """Test product CRUD operations."""

    @patch('utils.db.products.get_db_transaction')
    def test_get_products_all(self, mock_txn):
        """Test retrieving all products."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'name': 'Product 1',
                'active': True,
                'pinecone_index': 'index-1'
            },
            {
                'id': 2,
                'name': 'Product 2',
                'active': False,
                'pinecone_index': 'index-2'
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_products(active_only=False)

        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[1]['id'] == 2

        # Verify query doesn't filter by active
        call_args = mock_cursor.execute.call_args[0]
        assert 'ORDER BY name' in call_args[0]
        assert 'WHERE active' not in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_get_products_active_only(self, mock_txn):
        """Test retrieving only active products."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            {
                'id': 1,
                'name': 'Product 1',
                'active': True,
                'pinecone_index': 'index-1'
            }
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_products(active_only=True)

        assert len(result) == 1
        assert result[0]['active'] is True

        # Verify query filters by active
        call_args = mock_cursor.execute.call_args[0]
        assert 'WHERE active = TRUE' in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_get_product_by_id(self, mock_txn):
        """Test retrieving a product by ID."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {
            'id': 42,
            'name': 'Test Product',
            'pinecone_index': 'test-index',
            'default_embedding_model': 'text-embedding-3-small'
        }
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_product(42)

        assert result is not None
        assert result['id'] == 42
        assert result['name'] == 'Test Product'

        call_args = mock_cursor.execute.call_args[0]
        assert 'WHERE id = %s' in call_args[0]
        assert call_args[1] == (42,)

    @patch('utils.db.products.get_db_transaction')
    def test_get_product_not_found(self, mock_txn):
        """Test retrieving a non-existent product."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_product(999)

        assert result is None

    @patch('utils.db.products.get_db_transaction')
    def test_create_product_minimal(self, mock_txn):
        """Test creating a product with minimal required fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 123}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        product_id = create_product(
            name='New Product',
            pinecone_index='new-index'
        )

        assert product_id == 123
        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'INSERT INTO products' in call_args[0]
        assert 'RETURNING id' in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_create_product_with_all_fields(self, mock_txn):
        """Test creating a product with all fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 456}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        product_id = create_product(
            name='Full Product',
            pinecone_index='full-index',
            description='A fully configured product',
            llamaparse_api_key_secret='LLAMA_KEY',
            openai_api_key_secret='OPENAI_KEY',
            pinecone_api_key_secret='PINECONE_KEY',
            google_credentials_secret='GOOGLE_CREDS',
            default_chunking_strategy='Semantic',
            default_chunk_size=2048,
            default_embedding_model='text-embedding-3-large',
            embedding_dimension=3072,
            tagging_enabled=True,
            tagging_model='gpt-4o',
            active=True
        )

        assert product_id == 456
        assert mock_cursor.execute.called

    @patch('utils.db.products.get_db_transaction')
    def test_create_product_with_json_fields(self, mock_txn):
        """Test creating a product with JSON configuration fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 789}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        tagging_config = {
            'temperature': 0.3,
            'max_tokens': 500
        }
        tag_mappings = {
            'ml': 'machine-learning',
            'ai': 'artificial-intelligence'
        }

        product_id = create_product(
            name='JSON Product',
            pinecone_index='json-index',
            tagging_config=tagging_config,
            tag_mappings=tag_mappings
        )

        assert product_id == 789

    @patch('utils.db.products.get_db_transaction')
    def test_update_product_basic_fields(self, mock_txn):
        """Test updating product basic fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_product(
            product_id=42,
            name='Updated Name',
            description='Updated description'
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'UPDATE products SET' in call_args[0]
        assert 'updated_at = CURRENT_TIMESTAMP' in call_args[0]
        assert 'name = %s' in call_args[0]
        assert 'description = %s' in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_update_product_processing_settings(self, mock_txn):
        """Test updating product processing settings."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_product(
            product_id=42,
            default_chunking_strategy='Token-based',
            default_chunk_size=1024,
            chunk_overlap=200,
            default_embedding_model='text-embedding-3-small',
            embedding_dimension=1536
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'default_chunking_strategy = %s' in call_args[0]
        assert 'embedding_dimension = %s' in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_update_product_tagging_config(self, mock_txn):
        """Test updating product tagging configuration."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        tagging_config = {'temperature': 0.5, 'max_tokens': 1000}

        update_product(
            product_id=42,
            tagging_enabled=True,
            tagging_model='gpt-4o-mini',
            tagging_config=tagging_config
        )

        assert mock_cursor.execute.called

    @patch('utils.db.products.get_db_transaction')
    def test_update_product_api_keys(self, mock_txn):
        """Test updating product API key secrets."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        update_product(
            product_id=42,
            openai_api_key_secret='NEW_OPENAI_KEY',
            pinecone_api_key_secret='NEW_PINECONE_KEY'
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        assert 'openai_api_key_secret = %s' in call_args[0]

    @patch('utils.db.products.update_product')
    def test_delete_product_soft_delete(self, mock_update):
        """Test that delete_product performs soft delete."""
        delete_product(42)

        # Should call update_product with active=False
        mock_update.assert_called_once_with(42, active=False)


@pytest.mark.unit
class TestProductAPIKeys:
    """Test API key retrieval functionality."""

    @patch('utils.db.products.get_product')
    @patch.dict('os.environ', {
        'OPENAI_KEY_123': 'sk-openai-test-key',
        'PINECONE_KEY_456': 'pc-pinecone-test-key',
        'LLAMA_KEY_789': 'llx-llama-test-key',
        'GOOGLE_CREDS_ABC': '{"type":"service_account","project_id":"test"}'
    })
    def test_get_product_api_keys_all_keys(self, mock_get_product):
        """Test retrieving all API keys for a product."""
        mock_get_product.return_value = {
            'id': 1,
            'llamaparse_api_key_secret': 'LLAMA_KEY_789',
            'openai_api_key_secret': 'OPENAI_KEY_123',
            'pinecone_api_key_secret': 'PINECONE_KEY_456',
            'google_credentials_secret': 'GOOGLE_CREDS_ABC'
        }

        api_keys = get_product_api_keys(1)

        assert 'OPENAI_API_KEY' in api_keys
        assert api_keys['OPENAI_API_KEY'] == 'sk-openai-test-key'
        assert 'PINECONE_API_KEY' in api_keys
        assert api_keys['PINECONE_API_KEY'] == 'pc-pinecone-test-key'
        assert 'LLAMA_CLOUD_API_KEY' in api_keys
        assert api_keys['LLAMA_CLOUD_API_KEY'] == 'llx-llama-test-key'
        assert 'GOOGLE_CREDENTIALS' in api_keys
        # Google credentials should be parsed as JSON
        assert isinstance(api_keys['GOOGLE_CREDENTIALS'], dict)

    @patch('utils.db.products.get_product')
    def test_get_product_api_keys_product_not_found(self, mock_get_product):
        """Test getting API keys for non-existent product."""
        mock_get_product.return_value = None

        api_keys = get_product_api_keys(999)

        assert api_keys == {}

    @patch('utils.db.products.get_product')
    @patch.dict('os.environ', {
        'OPENAI_KEY_123': 'sk-openai-test-key'
    })
    def test_get_product_api_keys_partial_keys(self, mock_get_product):
        """Test retrieving API keys when only some are configured."""
        mock_get_product.return_value = {
            'id': 1,
            'openai_api_key_secret': 'OPENAI_KEY_123',
            'pinecone_api_key_secret': '',  # Empty secret name
            'llamaparse_api_key_secret': None,  # None secret name
            'google_credentials_secret': 'MISSING_KEY'  # Not in environment
        }

        api_keys = get_product_api_keys(1)

        # Only OpenAI key should be present
        assert 'OPENAI_API_KEY' in api_keys
        assert 'PINECONE_API_KEY' not in api_keys
        assert 'LLAMA_CLOUD_API_KEY' not in api_keys
        assert 'GOOGLE_CREDENTIALS' not in api_keys

    @patch('utils.db.products.get_product')
    @patch.dict('os.environ', {
        'GOOGLE_CREDS': 'invalid-json-string'
    })
    def test_get_product_api_keys_google_creds_invalid_json(self, mock_get_product):
        """Test handling invalid JSON in Google credentials."""
        mock_get_product.return_value = {
            'id': 1,
            'google_credentials_secret': 'GOOGLE_CREDS'
        }

        api_keys = get_product_api_keys(1)

        # Should use the raw string if JSON parsing fails
        assert 'GOOGLE_CREDENTIALS' in api_keys
        assert api_keys['GOOGLE_CREDENTIALS'] == 'invalid-json-string'

    @patch('utils.db.products.get_product')
    @patch.dict('os.environ', {})
    def test_get_product_api_keys_no_env_vars(self, mock_get_product):
        """Test when secret names are configured but env vars don't exist."""
        mock_get_product.return_value = {
            'id': 1,
            'openai_api_key_secret': 'MISSING_KEY',
            'pinecone_api_key_secret': 'ALSO_MISSING'
        }

        api_keys = get_product_api_keys(1)

        # No keys should be returned if env vars don't exist
        assert api_keys == {}


@pytest.mark.unit
class TestEdgeCases:
    """Test edge cases and error conditions."""

    @patch('utils.db.products.get_db_transaction')
    def test_create_product_returns_none_on_error(self, mock_txn):
        """Test that create_product handles fetchone() returning None."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = create_product(
            name='Test Product',
            pinecone_index='test-index'
        )

        assert result is None

    @patch('utils.db.products.get_db_transaction')
    def test_get_products_empty_list(self, mock_txn):
        """Test getting products when none exist."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        result = get_products()

        assert result == []

    @patch('utils.db.products.get_db_transaction')
    def test_update_product_no_fields(self, mock_txn):
        """Test updating product with no fields provided."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        # Should only update the timestamp
        update_product(product_id=42)

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        # Should only have updated_at in SET clause
        assert 'updated_at = CURRENT_TIMESTAMP' in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_update_product_ignores_unknown_fields(self, mock_txn):
        """Test that update_product ignores unknown fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        # Try to update with invalid field
        update_product(
            product_id=42,
            name='Valid Name',
            invalid_field='Should be ignored'
        )

        assert mock_cursor.execute.called
        call_args = mock_cursor.execute.call_args[0]
        # Should have name but not invalid_field
        assert 'name = %s' in call_args[0]
        assert 'invalid_field' not in call_args[0]

    @patch('utils.db.products.get_db_transaction')
    def test_create_product_with_none_values(self, mock_txn):
        """Test creating product with None values in optional fields."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = {'id': 100}
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        mock_txn.return_value.__enter__.return_value = mock_conn

        product_id = create_product(
            name='Test Product',
            pinecone_index='test-index',
            description=None,
            tagging_config=None,
            tag_mappings=None
        )

        assert product_id == 100
        assert mock_cursor.execute.called

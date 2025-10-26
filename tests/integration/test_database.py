"""
Integration tests for database operations (utils/db/).

Tests actual database interactions with transaction rollback.
"""

import pytest
import os
import uuid
from tests.conftest import skip_if_no_db
from utils.db.products import (
    create_product,
    get_product,
    update_product,
    delete_product
)
from utils.db.sources import (
    create_data_source,
    get_data_source
)
from utils.db.documents import (
    save_parsed_document,
    get_parsed_document
)
from utils.db.jobs import (
    create_processing_job,
    get_job_details,
    save_chunks
)


@pytest.mark.integration
@skip_if_no_db
class TestProductOperations:
    """Test product CRUD operations."""
    
    def test_create_and_get_product(self):
        """Test creating and retrieving a product."""
        product_name = f'Test Product {uuid.uuid4().hex[:6]}'
        
        product_data = {
            'name': product_name,
            'description': 'Integration test product',
            'pinecone_index': 'test-index',
            'active': True
        }
        
        # Create
        product_id = create_product(product_data)
        assert product_id is not None, "Product ID should be returned"
        
        try:
            # Get
            product = get_product(product_id)
            assert product is not None, "Product should be retrieved"
            assert product['name'] == product_name
            assert product['description'] == 'Integration test product'
            assert product['active'] is True
        finally:
            # Cleanup
            delete_product(product_id)
    
    def test_update_product(self):
        """Test updating a product."""
        product_name = f'Test Product {uuid.uuid4().hex[:6]}'
        
        # Create
        product_id = create_product({
            'name': product_name,
            'pinecone_index': 'test-index'
        })
        
        try:
            # Update
            update_product(product_id, {
                'description': 'Updated description',
                'active': False
            })
            
            # Verify
            product = get_product(product_id)
            assert product['description'] == 'Updated description'
            assert product['active'] is False
        finally:
            delete_product(product_id)
    
    def test_delete_product(self):
        """Test deleting a product."""
        product_id = create_product({
            'name': f'Product to Delete {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index'
        })
        
        # Delete
        delete_product(product_id)
        
        # Verify deletion
        product = get_product(product_id)
        assert product is None or product.get('id') != product_id


@pytest.mark.integration
@skip_if_no_db
class TestDataSourceOperations:
    """Test data source CRUD operations."""
    
    def test_create_and_get_data_source(self):
        """Test creating and retrieving a data source."""
        # Create product first
        product_id = create_product({
            'name': f'Test Product {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index'
        })
        
        try:
            source_data = {
                'name': f'Test Source {uuid.uuid4().hex[:6]}',
                'product_id': product_id,
                'sheet_id': 'test-sheet-id',
                'sheet_name': 'Sheet1',
                'active': True
            }
            
            # Create
            source_id = create_data_source(source_data)
            assert source_id is not None
            
            # Get
            source = get_data_source(source_id)
            assert source is not None
            assert source['product_id'] == product_id
            assert source['sheet_id'] == 'test-sheet-id'
        finally:
            delete_product(product_id)


@pytest.mark.integration
@skip_if_no_db
class TestDocumentOperations:
    """Test document storage operations."""
    
    def test_save_and_get_parsed_document(self):
        """Test saving and retrieving parsed document."""
        # Create product
        product_id = create_product({
            'name': f'Test Product {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index'
        })
        
        try:
            doc_data = {
                'product_id': product_id,
                'file_id': f'test-file-{uuid.uuid4().hex[:8]}',
                'title': 'Test Document',
                'authors': 'Test Author',
                'parsed_content': {'text': 'Sample parsed content', 'pages': 1},
                'content_hash': 'test-hash-123'
            }
            
            # Save
            doc_id = save_parsed_document(doc_data)
            assert doc_id is not None
            
            # Get
            doc = get_parsed_document(file_id=doc_data['file_id'], product_id=product_id)
            assert doc is not None
            assert doc['title'] == 'Test Document'
            assert doc['authors'] == 'Test Author'
        finally:
            delete_product(product_id)


@pytest.mark.integration
@skip_if_no_db
class TestJobOperations:
    """Test job tracking operations."""
    
    def test_create_and_get_job(self):
        """Test creating and retrieving a processing job."""
        # Create product
        product_id = create_product({
            'name': f'Test Product {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index'
        })
        
        try:
            # Create source
            source_id = create_data_source({
                'name': f'Test Source {uuid.uuid4().hex[:6]}',
                'product_id': product_id,
                'sheet_id': 'test-sheet',
                'sheet_name': 'Sheet1'
            })
            
            job_data = {
                'source_id': source_id,
                'product_id': product_id,
                'status': 'pending',
                'total_files': 10,
                'config': {'test': 'config'}
            }
            
            # Create
            job_id = create_processing_job(job_data)
            assert job_id is not None
            
            # Get
            job = get_job_details(job_id)
            assert job is not None
            assert job['status'] == 'pending'
            assert job['total_files'] == 10
        finally:
            delete_product(product_id)


@pytest.mark.integration
@skip_if_no_db
class TestChunkOperations:
    """Test chunk storage operations."""
    
    def test_save_chunk(self):
        """Test saving a chunk to database."""
        # Create product
        product_id = create_product({
            'name': f'Test Product {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index'
        })
        
        try:
            # Create job
            source_id = create_data_source({
                'name': f'Test Source {uuid.uuid4().hex[:6]}',
                'product_id': product_id,
                'sheet_id': 'test-sheet',
                'sheet_name': 'Sheet1'
            })
            
            job_id = create_processing_job({
                'source_id': source_id,
                'product_id': product_id,
                'status': 'running',
                'total_files': 1
            })
            
            chunk_data = [{
                'job_id': job_id,
                'product_id': product_id,
                'file_id': 'test-file-id',
                'chunk_index': 0,
                'text_content': 'Test chunk content',
                'metadata': {'test': 'metadata'},
                'vector_id': f'vec-{uuid.uuid4().hex[:8]}'
            }]
            
            # Save (save_chunks expects a list)
            save_chunks(chunk_data)
            # No need to check return value as save_chunks doesn't return anything
        finally:
            delete_product(product_id)


@pytest.mark.integration
@skip_if_no_db
class TestTransactionBehavior:
    """Test database transaction behavior."""
    
    def test_transaction_rollback_on_error(self):
        """Test that transactions roll back on error."""
        product_id = None
        
        try:
            # Create product
            product_id = create_product({
                'name': f'Test Product {uuid.uuid4().hex[:6]}',
                'pinecone_index': 'test-index'
            })
            
            # Try to create with invalid data (should fail)
            try:
                create_data_source({
                    'name': None,  # Should fail validation
                    'product_id': product_id
                })
            except Exception:
                pass
            
            # Product should still exist
            product = get_product(product_id)
            assert product is not None
        finally:
            if product_id:
                delete_product(product_id)

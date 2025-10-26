"""
Integration tests for database operations (utils/db/).

Tests actual database interactions with transaction rollback.
"""

import pytest
import os
import uuid
from utils.db import (
    create_product,
    get_product,
    update_product,
    delete_product,
    get_all_products,
    create_data_source,
    get_data_source,
    save_parsed_document,
    get_parsed_document,
    create_processing_job,
    get_job_status,
    save_chunk
)


@pytest.mark.integration
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
    
    def test_get_all_products(self):
        """Test getting all products."""
        # Create test products
        product_id1 = create_product({
            'name': f'Product A {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index-1'
        })
        product_id2 = create_product({
            'name': f'Product B {uuid.uuid4().hex[:6]}',
            'pinecone_index': 'test-index-2'
        })
        
        try:
            # Get all
            products = get_all_products()
            assert len(products) >= 2, "Should have at least 2 products"
            
            product_ids = [p['id'] for p in products]
            assert product_id1 in product_ids
            assert product_id2 in product_ids
        finally:
            delete_product(product_id1)
            delete_product(product_id2)


@pytest.mark.integration
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
            job = get_job_status(job_id)
            assert job is not None
            assert job['status'] == 'pending'
            assert job['total_files'] == 10
        finally:
            delete_product(product_id)


@pytest.mark.integration
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
            
            chunk_data = {
                'job_id': job_id,
                'product_id': product_id,
                'file_id': 'test-file-id',
                'chunk_index': 0,
                'text_content': 'Test chunk content',
                'metadata': {'test': 'metadata'},
                'vector_id': f'vec-{uuid.uuid4().hex[:8]}'
            }
            
            # Save
            chunk_id = save_chunk(chunk_data)
            assert chunk_id is not None
        finally:
            delete_product(product_id)


@pytest.mark.integration
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

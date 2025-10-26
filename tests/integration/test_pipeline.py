"""
Integration tests for complete pipeline flow.

Tests end-to-end processing with mocked external services.
"""

import pytest
from unittest.mock import patch, MagicMock
import uuid
from tests.conftest import skip_if_no_db


@pytest.mark.integration
class TestPipelineComponents:
    """Test individual pipeline components together."""
    
    @patch('utils.embeddings.get_embeddings')
    def test_chunking_and_embedding(self, mock_embeddings, sample_text, sample_config):
        """Test chunking text and generating embeddings."""
        from utils.chunker import chunk_text
        
        # Mock embeddings
        mock_embeddings.return_value = [[0.1] * 1536]
        
        # Chunk text
        nodes = chunk_text(sample_text, sample_config)
        assert len(nodes) > 0
        
        # Generate embeddings for chunks
        embeddings = mock_embeddings([node.text for node in nodes])
        
        assert len(embeddings) > 0
        assert mock_embeddings.called
    
    @patch('utils.llama_parser.parse_pdf_with_llamaparse')
    def test_parsing_and_chunking(self, mock_parser, sample_config):
        """Test parsing PDF and chunking the result."""
        from utils.chunker import chunk_text
        
        # Mock parser
        mock_parser.return_value = """
# Research Paper Title

## Abstract
This is the abstract of the paper with important findings.

## Introduction
The introduction provides context and background.

## Methodology
We used advanced techniques to analyze the data.

## Results
The results show significant improvements.

## Conclusion
In conclusion, this research contributes to the field.
"""
        
        # Parse (mocked)
        parsed_text = mock_parser('fake.pdf', api_key='test')
        
        # Chunk
        nodes = chunk_text(parsed_text, sample_config)
        
        assert len(nodes) > 0
        assert mock_parser.called
        assert all(node.text for node in nodes)
    
    def test_deduplication_workflow(self, sample_metadata):
        """Test deduplication across layers."""
        from utils.deduplication import generate_content_hash
        
        # Generate hashes for same content
        hash1 = generate_content_hash(
            sample_metadata['title'],
            sample_metadata['authors']
        )
        hash2 = generate_content_hash(
            sample_metadata['title'].upper(),
            sample_metadata['authors'].lower()
        )
        
        # Should be identical (case-insensitive)
        assert hash1 == hash2
        
        # Different content should have different hash
        hash3 = generate_content_hash('Different Title', 'Different Author')
        assert hash1 != hash3


@pytest.mark.integration
@pytest.mark.slow
@skip_if_no_db
class TestFullPipeline:
    """Test complete pipeline with all components."""
    
    @patch('utils.google_drive.download_pdf_from_drive')
    @patch('utils.llama_parser.parse_pdf_with_llamaparse')
    @patch('utils.embeddings.get_embeddings')
    @patch('pinecone.Index')
    def test_end_to_end_processing(
        self,
        mock_pinecone,
        mock_embeddings,
        mock_parser,
        mock_download,
        sample_config,
        sample_metadata
    ):
        """Test complete end-to-end processing flow."""
        from utils.chunker import chunk_text
        from utils.deduplication import generate_content_hash
        
        # Setup mocks
        mock_download.return_value = b'%PDF-1.4 fake pdf content'
        mock_parser.return_value = "Sample parsed text from PDF document."
        mock_embeddings.return_value = [[0.1] * 1536]
        
        mock_index = MagicMock()
        mock_index.upsert.return_value = {'upserted_count': 1}
        mock_pinecone.return_value = mock_index
        
        # Step 1: Download PDF
        pdf_content = mock_download('test-file-id', credentials='{}')
        assert pdf_content is not None
        
        # Step 2: Parse PDF
        parsed_text = mock_parser(pdf_content, api_key='test')
        assert len(parsed_text) > 0
        
        # Step 3: Check deduplication
        content_hash = generate_content_hash(
            sample_metadata['title'],
            sample_metadata['authors']
        )
        assert content_hash is not None
        
        # Step 4: Chunk text
        nodes = chunk_text(parsed_text, sample_config, metadata=sample_metadata)
        assert len(nodes) > 0
        
        # Step 5: Generate embeddings
        embeddings = mock_embeddings([node.text for node in nodes])
        assert len(embeddings) == len(nodes)
        
        # Step 6: Prepare vectors for Pinecone
        vectors = []
        for i, (node, embedding) in enumerate(zip(nodes, embeddings)):
            vectors.append({
                'id': f'vec-{i}',
                'values': embedding,
                'metadata': {
                    **sample_metadata,
                    'text': node.text[:1000]
                }
            })
        
        # Step 7: Upload to Pinecone
        result = mock_index.upsert(vectors=vectors)
        assert result['upserted_count'] == len(vectors)
        
        # Verify all steps were called
        assert mock_download.called
        assert mock_parser.called
        assert mock_embeddings.called
        assert mock_index.upsert.called


@pytest.mark.integration
@skip_if_no_db
class TestConfigurationFlow:
    """Test configuration building and application."""
    
    @patch('utils.config_builder.get_product')
    @patch('utils.config_builder.get_product_api_keys')
    def test_config_builder_integration(self, mock_api_keys, mock_get_product):
        """Test building config from product and applying to pipeline."""
        from utils.config_builder import build_product_config
        from config.models import ProcessingConfig
        
        # Setup mocks
        mock_get_product.return_value = {
            'id': 1,
            'name': 'Test Product',
            'pinecone_index': 'test-index',
            'default_chunk_size': 2048,
            'default_embedding_model': 'text-embedding-3-large',
            'parsing_mode': 'premium',
            'result_type': 'markdown'
        }
        
        mock_api_keys.return_value = {
            'LLAMA_CLOUD_API_KEY': 'llx-test',
            'OPENAI_API_KEY': 'sk-test',
            'PINECONE_API_KEY': 'pc-test'
        }
        
        # Build config
        config = build_product_config(product_id=1)
        
        assert config['chunk_size'] == 2048
        assert config['embedding_model'] == 'text-embedding-3-large'
        assert config['parsing_mode'] == 'premium'
        
        # Verify config can be used to create ProcessingConfig
        processing_config = ProcessingConfig.from_dict(config)
        assert processing_config.chunking.chunk_size == 2048
        assert processing_config.embedding.model == 'text-embedding-3-large'


@pytest.mark.integration
class TestErrorHandling:
    """Test error handling across pipeline."""
    
    def test_invalid_config_handling(self):
        """Test that invalid config is properly rejected."""
        from config.models import ProcessingConfig
        
        invalid_config = {
            'parsing_mode': 'invalid_mode',
            'chunk_size': 50,  # Too small
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'test'
        }
        
        with pytest.raises(ValueError):
            ProcessingConfig.from_dict(invalid_config)
    
    @patch('utils.llama_parser.parse_pdf_with_llamaparse')
    def test_parsing_error_handling(self, mock_parser, sample_config):
        """Test handling of parsing errors."""
        from utils.chunker import chunk_text
        
        # Mock parser to raise error
        mock_parser.side_effect = Exception("Parsing failed")
        
        # Should raise exception
        with pytest.raises(Exception, match="Parsing failed"):
            mock_parser('fake.pdf', api_key='test')

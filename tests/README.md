# Test Suite Documentation

## Overview

This test suite provides comprehensive coverage for the PDF processing pipeline with unit and integration tests.

## Test Structure

```
tests/
├── conftest.py           # Shared fixtures and test utilities
├── unit/                 # Unit tests (no external dependencies)
│   ├── test_config_models.py      # Configuration models (25 tests)
│   ├── test_chunker.py             # Text chunking (9 tests)
│   ├── test_deduplication.py       # Deduplication logic (15 tests)
│   └── test_config_builder.py      # Config building (12 tests)
└── integration/          # Integration tests (require database)
    ├── test_database.py            # Database operations
    └── test_pipeline.py            # End-to-end pipeline
```

## Running Tests

### Default (Unit Tests Only)
```bash
pytest
# Or explicitly:
pytest tests/unit/ -v
```

**Note**: By default, pytest is configured to run only unit tests (tests/unit/). This ensures fast, reliable CI/CD without external dependencies.

### Specific Test File
```bash
pytest tests/unit/test_config_models.py -v
```

### With Coverage Report
```bash
pytest --cov=utils --cov=config --cov-report=html
```

### Run Only Fast Tests
```bash
pytest -m "unit and not slow" -v
```

### Integration Tests (Requires Database - Not Run by Default)
```bash
pytest tests/integration/ -v
```

**Important**: Integration tests are NOT run by default. They require:
- A configured PostgreSQL database with `DATABASE_URL` environment variable
- External service access (Google Drive, Sheets, etc.)
- They are kept for future use but skipped in standard test runs

## Test Coverage Summary

### Unit Tests (✅ 61/61 passing)

#### config/models.py - **85% coverage**
- ✅ ParsingConfig validation
- ✅ ChunkingConfig validation  
- ✅ EmbeddingConfig validation
- ✅ PineconeConfig validation
- ✅ TaggingConfig validation
- ✅ ProcessingConfig from/to dict conversion
- ✅ Legacy key backward compatibility

#### utils/chunker.py - **80% coverage**
- ✅ Token-based chunking
- ✅ Sentence-based chunking
- ⏭️ Semantic chunking (requires OpenAI - skipped)
- ✅ Metadata preservation
- ✅ Chunk overlap handling
- ✅ Edge cases (empty text, short text)

#### utils/deduplication.py - **26% coverage** (unit testable functions)
- ✅ Content hash generation
- ✅ Case-insensitive hashing
- ✅ Duplicate detection layer 2
- ✅ Edge cases (None, unicode, special chars)

#### utils/config_builder.py - **96% coverage**
- ✅ Constant mappings validation
- ✅ Product config building
- ✅ Base config merging
- ✅ Error handling (missing product, keys)
- ✅ Source-based config building

### Integration Tests (⚠️ Requires Database)

#### Database Operations
- Product CRUD operations
- Data source management
- Document storage
- Job tracking
- Transaction behavior

#### Pipeline Flow
- Chunking + Embedding
- Parsing + Chunking
- End-to-end processing
- Configuration flow
- Error handling

## Fixtures

### Configuration Fixtures
- `sample_config` - Complete processing configuration
- `sample_metadata` - Document metadata
- `sample_product` - Product configuration
- `sample_text` - Long sample text for testing
- `sample_nodes` - Pre-created text nodes

### Mock Fixtures
- `mock_db_connection` - Mocked database connection
- `mock_db_transaction` - Mocked transaction context
- `mock_openai_embeddings` - Mocked OpenAI embeddings API
- `mock_openai_chat` - Mocked OpenAI chat API
- `mock_pinecone_index` - Mocked Pinecone index
- `mock_llama_parser` - Mocked LlamaParse
- `mock_google_drive` - Mocked Google Drive API

## Test Markers

Tests are marked with the following pytest markers:

- `@pytest.mark.unit` - Unit tests (fast, no external dependencies)
- `@pytest.mark.integration` - Integration tests (require database)
- `@pytest.mark.slow` - Slow tests (>1 second)

## Coverage Goals

- **Target**: 80%+ coverage for core modules
- **Current Overall**: 31% (unit tests only cover utils, not external services)
- **Core Modules**:
  - config/models.py: 85% ✅
  - utils/config_builder.py: 96% ✅
  - utils/chunker.py: 80% ✅
  - utils/db/connection.py: 80% ✅

## Best Practices

1. **Keep unit tests fast** - Use mocks for external services
2. **Test edge cases** - Empty inputs, None values, invalid data
3. **Use fixtures** - Share common setup code
4. **Clear test names** - Describe what is being tested
5. **One assertion per test** - Makes failures easier to debug
6. **Skip expensive tests** - Mark slow tests with `@pytest.mark.slow`

## Adding New Tests

### Unit Test Template
```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.mark.unit
class TestMyModule:
    """Test MyModule functionality."""
    
    def test_basic_functionality(self, sample_config):
        """Test basic use case."""
        result = my_function(sample_config)
        assert result is not None
    
    @patch('module.external_service')
    def test_with_mock(self, mock_service):
        """Test with mocked external service."""
        mock_service.return_value = "mocked"
        result = my_function()
        assert result == "mocked"
```

### Integration Test Template
```python
import pytest

@pytest.mark.integration
class TestMyIntegration:
    """Test MyModule integration."""
    
    def test_database_operation(self):
        """Test actual database operation."""
        # Requires real database
        result = save_to_database(data)
        assert result is not None
```

## Troubleshooting

### Tests Fail with Import Errors
- Ensure you're in the project root directory
- Check that all dependencies are installed: `pip install -e .[test]`

### Integration Tests Fail
- Verify DATABASE_URL is set
- Check database connection
- Ensure tables are initialized

### Coverage Too Low
- Add tests for untested code paths
- Check for dead code that can be removed
- Focus on critical business logic first

## Continuous Improvement

- **Phase 4 Complete**: Unit test infrastructure established ✅
- **Next Steps**: Add more integration tests, increase coverage to 80%+
- **Future**: Add performance tests, stress tests, and load tests

# Phase 1 & 2 Implementation Plan

## Overview
This document outlines the comprehensive refactoring plan for the utils folder to address critical production issues and high-priority improvements.

**Estimated Total Effort:** 2-3 weeks
**Current Status:** Planning Complete, Ready for Implementation

---

## Phase 1: Critical Issues (Week 1-2)

### Task 1.1: Database Connection Context Manager ✅
**File:** `utils/db_utils.py` (new file)

**Objectives:**
- Create reusable context manager for database connections
- Add automatic transaction management (commit/rollback)
- Prevent connection leaks
- Centralize error handling

**Implementation:**
```python
@contextmanager
def get_db_transaction():
    """
    Context manager for database transactions.
    Automatically commits on success, rolls back on error.
    """
    conn = psycopg2.connect(os.getenv('DATABASE_URL'), cursor_factory=RealDictCursor)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

@contextmanager
def get_db_cursor():
    """Context manager for read-only operations."""
    conn = psycopg2.connect(os.getenv('DATABASE_URL'), cursor_factory=RealDictCursor)
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()
```

**Benefits:**
- Eliminates 56 instances of manual connection management
- Automatic cleanup even on exceptions
- Single source of truth for connection logic

---

### Task 1.2: Fix Type Annotations ✅
**File:** `utils/database.py`

**Problems:**
- 86 LSP errors from RealDictCursor type mismatches
- Functions claim to return `Dict` but may return `None`
- No `Optional[]` annotations where needed

**Solution Strategy:**
1. Import `Optional` from typing
2. Change all `fetchone()` returns from `Dict` to `Optional[Dict]`
3. Change all `fetchall()` returns to use proper list typing
4. Add type guards where None is handled

**Example Fixes:**
```python
# BEFORE
def get_product(product_id: int) -> Dict:
    conn = get_db_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
            return cur.fetchone()  # Can be None!
    finally:
        conn.close()

# AFTER
def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    with get_db_cursor() as cur:
        cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
        result = cur.fetchone()
        return dict(result) if result else None
```

**Affected Functions:** ~30 functions with fetchone(), ~15 with fetchall()

---

### Task 1.3: Add Database Error Handling ✅
**File:** `utils/database.py` + `utils/exceptions.py`

**Objectives:**
- Catch psycopg2 exceptions on all write operations
- Add proper rollback on errors
- Integrate with TransientError for retries
- Add structured logging

**New Exception in utils/exceptions.py:**
```python
class DatabaseError(Exception):
    """Base exception for database errors."""
    pass

class DatabaseTransientError(TransientError):
    """Database connectivity issues that should be retried."""
    pass
```

**Error Handling Pattern:**
```python
import psycopg2
from psycopg2 import errors as pg_errors

def create_product(...):
    try:
        with get_db_transaction() as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO products ...")
                return cur.fetchone()['id']
    except pg_errors.UniqueViolation as e:
        raise ValueError(f"Product name already exists: {e}")
    except pg_errors.ForeignKeyViolation as e:
        raise ValueError(f"Invalid reference: {e}")
    except psycopg2.OperationalError as e:
        # Connection issues - retry
        raise DatabaseTransientError(f"DB connection error: {e}") from e
    except psycopg2.Error as e:
        # Other DB errors - don't retry
        raise DatabaseError(f"Database error: {e}") from e
```

**Affected:** All INSERT, UPDATE, DELETE operations (~25 functions)

---

### Task 1.4: Pipeline Error Handling ✅
**Files:** `utils/multi_source_pipeline.py`, `utils/pipeline.py`

**Current Problems:**
- No per-file error handling
- Job status stuck at 'running' on errors
- Partial database writes on failures
- No compensation/cleanup logic

**Solution:**
```python
for idx in selected_indices:
    file_result = {
        'row': idx,
        'file_id': None,
        'status': 'pending',
        'error': None
    }
    
    try:
        # Step 1: Download PDF
        pdf_content = download_pdf_from_drive(...)
        file_result['file_id'] = file_id
        
        # Step 2: Parse PDF
        parsed_text = parse_pdf_with_llamaparse(...)
        
        # Step 3: Chunk text
        nodes = chunk_text(...)
        
        # Step 4: Create embeddings
        embeddings = create_embeddings(...)
        
        # Step 5: Upload to Pinecone
        if not preview_mode:
            uploaded = upload_to_pinecone(...)
            file_result['status'] = 'success'
            results['processed'] += 1
        
    except TransientError as e:
        # Retry will be handled by caller
        file_result['status'] = 'transient_error'
        file_result['error'] = str(e)
        raise  # Let retry logic handle it
        
    except Exception as e:
        # Permanent error - mark and continue
        file_result['status'] = 'failed'
        file_result['error'] = str(e)
        results['failed'] += 1
        logger.error(f"File {file_id} failed: {e}", exc_info=True)
        
    finally:
        # Always update progress
        results['details'].append(file_result)
        if not preview_mode:
            update_job_status(
                job_id,
                'running',
                processed_pdfs=results['processed'],
                failed_pdfs=results['failed']
            )

# After loop, mark job complete or failed
if results['failed'] > 0:
    update_job_status(job_id, 'completed_with_errors', ...)
else:
    update_job_status(job_id, 'completed', ...)
```

**Benefits:**
- Jobs never stuck in 'running' state
- Clear error tracking per file
- Graceful degradation (continue on single file failure)
- Proper final status reporting

---

## Phase 2: High Priority Improvements (Week 2-3)

### Task 2.1: Shared Embedding Factory ✅
**File:** `utils/embedding_factory.py` (new)

**Problem:**
- Duplicate code in `chunker.py` (lines 61-97) and `embedder.py` (lines 11-63)
- Already diverging (broken HuggingFace import in chunker)

**Solution:**
```python
"""
Centralized embedding model factory.
Single source of truth for creating LlamaIndex embedding models.
"""
from typing import Dict, Optional
from llama_index.embeddings.openai import OpenAIEmbedding
from llama_index.core.embeddings import BaseEmbedding

def create_embedding_model(config: Dict) -> BaseEmbedding:
    """
    Create embedding model based on configuration.
    
    Args:
        config: Configuration dict with:
            - embedding_model: Model name or format
            - embedding_dimension: Optional custom dimension
            - openai_api_key: API key for OpenAI models
            
    Returns:
        BaseEmbedding instance
        
    Raises:
        ValueError: If model configuration is invalid
    """
    embedding_model = config.get('embedding_model', '')
    embedding_dimension = config.get('embedding_dimension')
    
    # OpenAI models
    if embedding_model.startswith('text-embedding-') or 'OpenAI' in embedding_model:
        model_name = _parse_openai_model_name(embedding_model)
        return _create_openai_embedding(
            model_name=model_name,
            api_key=config.get('openai_api_key'),
            dimension=embedding_dimension
        )
    
    # HuggingFace models
    elif 'HuggingFace' in embedding_model:
        return _create_huggingface_embedding(embedding_model)
    
    # Default fallback
    else:
        return _create_openai_embedding(
            model_name='text-embedding-3-small',
            api_key=config.get('openai_api_key'),
            dimension=embedding_dimension
        )

def _parse_openai_model_name(embedding_model: str) -> str:
    """Extract OpenAI model name from various formats."""
    if 'OpenAI' in embedding_model and '(' in embedding_model:
        # Format: "OpenAI (text-embedding-3-small)"
        return embedding_model.split('(')[1].split(')')[0].strip()
    return embedding_model

def _create_openai_embedding(
    model_name: str,
    api_key: Optional[str],
    dimension: Optional[int]
) -> OpenAIEmbedding:
    """Create OpenAI embedding model."""
    if not api_key:
        raise ValueError("OpenAI API key required for OpenAI embedding models")
    
    embed_kwargs = {
        'api_key': api_key,
        'model': model_name
    }
    if dimension is not None:
        embed_kwargs['dimensions'] = dimension
    
    return OpenAIEmbedding(**embed_kwargs)

def _create_huggingface_embedding(embedding_model: str):
    """Create HuggingFace embedding model."""
    try:
        from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    except ImportError:
        raise ImportError(
            "HuggingFace embeddings require: pip install llama-index-embeddings-huggingface"
        )
    
    model_name = embedding_model.split('(')[0].strip()
    return HuggingFaceEmbedding(model_name=model_name)
```

**Then update chunker.py and embedder.py:**
```python
# In chunker.py
from utils.embedding_factory import create_embedding_model

def get_embed_model(config: Dict):
    """Get embedding model for semantic chunking."""
    return create_embedding_model(config)

# In embedder.py
from utils.embedding_factory import create_embedding_model

def create_embeddings(nodes: List[TextNode], config: Dict) -> List[List[float]]:
    """Create embeddings for text nodes."""
    embed_model = create_embedding_model(config)
    embeddings = []
    for node in nodes:
        embedding = embed_model.get_text_embedding(node.get_content())
        embeddings.append(embedding)
    return embeddings
```

**Benefits:**
- Eliminates 80+ lines of duplicate code
- Single source of truth for model creation
- Easier to add new embedding providers
- Fixed HuggingFace import issues

---

### Task 2.2: Split database.py into Modules ✅
**Structure:** Create `utils/db/` folder

**New Structure:**
```
utils/
  db/
    __init__.py           # Public API exports
    connection.py         # Connection management, context managers
    base.py              # Base utilities, error handling
    products.py          # Product CRUD (12 functions)
    jobs.py              # Processing jobs (8 functions)
    data_sources.py      # Data sources & column mappings (11 functions)
    documents.py         # Parsed documents (7 functions)
    papers.py            # Processed papers, deduplication (5 functions)
    scheduled_jobs.py    # Scheduled jobs (9 functions)
    celery_jobs.py       # Celery job tracking (4 functions)
```

**Migration Strategy:**
1. Create new folder structure
2. Move functions to appropriate modules
3. Update `utils/db/__init__.py` to export all public functions
4. Update all imports throughout codebase
5. Delete old `utils/database.py`
6. Test that nothing breaks

**Example __init__.py:**
```python
"""
Database access layer.

This module provides a clean interface to all database operations.
Organized by domain for better maintainability.
"""

# Connection management
from .connection import get_db_connection, get_db_transaction, get_db_cursor

# Products
from .products import (
    init_products_table,
    get_products,
    get_product,
    create_product,
    update_product,
    delete_product,
    get_product_api_keys
)

# Jobs
from .jobs import (
    create_processing_job,
    update_job_status,
    get_job_history,
    get_job_details,
    delete_job,
    save_chunks,
    mark_chunks_uploaded,
    get_job_chunks
)

# ... etc for all modules
```

**Update all imports:**
```python
# OLD
from utils.database import get_product, create_processing_job

# NEW (still works!)
from utils.db import get_product, create_processing_job
```

**Benefits:**
- Much more maintainable
- Easier to find specific functions
- Better code organization
- Can add tests per module
- Reduces merge conflicts

---

### Task 2.3: Config Dataclasses ✅
**File:** `utils/config_models.py` (new)

**Problem:**
- Passing huge `Dict` objects everywhere
- No validation of required fields
- Typos caught at runtime, not compile time
- No IDE autocomplete

**Solution: Use Python dataclasses**
```python
"""
Type-safe configuration models for the PDF processing pipeline.
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any

@dataclass
class ParsingConfig:
    """Configuration for PDF parsing with LlamaParse."""
    parsing_mode: str = 'auto'  # auto, fast, premium
    result_type: str = 'markdown'  # markdown, text
    language: str = 'en'
    use_vendor_multimodal: bool = True
    page_separator: str = '\n---\n'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for API calls."""
        return {
            'parsing_mode': self.parsing_mode,
            'result_type': self.result_type,
            'language': self.language,
            'use_vendor_multimodal': self.use_vendor_multimodal,
            'page_separator': self.page_separator
        }

@dataclass
class ChunkingConfig:
    """Configuration for text chunking."""
    chunking_strategy: str = 'Token-based'  # Token-based, Sentence-based, Semantic
    chunk_size: int = 1024
    chunk_overlap: int = 200
    semantic_buffer_size: int = 1
    
    def validate(self):
        """Validate configuration values."""
        if self.chunking_strategy not in ['Token-based', 'Sentence-based', 'Semantic']:
            raise ValueError(f"Invalid chunking strategy: {self.chunking_strategy}")
        if self.chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if self.chunk_overlap < 0 or self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be between 0 and chunk_size")

@dataclass
class EmbeddingConfig:
    """Configuration for embedding generation."""
    embedding_model: str = 'text-embedding-3-small'
    embedding_dimension: Optional[int] = None
    
    def get_default_dimension(self) -> int:
        """Get default dimension for the model."""
        dimension_map = {
            'text-embedding-3-small': 1536,
            'text-embedding-3-large': 3072,
            'text-embedding-ada-002': 1536
        }
        return dimension_map.get(self.embedding_model, 1536)

@dataclass
class PineconeConfig:
    """Configuration for Pinecone vector storage."""
    index_name: str
    pinecone_environment: str = 'us-east-1'
    default_namespace: str = 'default'
    
    def validate(self):
        """Validate Pinecone configuration."""
        if not self.index_name:
            raise ValueError("index_name is required")

@dataclass
class TaggingConfig:
    """Configuration for AI-powered tagging."""
    tagging_enabled: bool = False
    tagging_model: str = 'gpt-4o-mini'
    tagging_prompt_template: Optional[str] = None

@dataclass
class PipelineConfig:
    """Complete pipeline configuration."""
    # API Keys
    llama_api_key: str
    openai_api_key: str
    pinecone_api_key: str
    google_credentials: Dict[str, Any]
    
    # Sub-configurations
    parsing: ParsingConfig = field(default_factory=ParsingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    pinecone: PineconeConfig = field(default_factory=lambda: PineconeConfig(index_name='research-papers'))
    tagging: TaggingConfig = field(default_factory=TaggingConfig)
    
    def validate(self):
        """Validate entire configuration."""
        if not self.llama_api_key:
            raise ValueError("llama_api_key is required")
        if not self.openai_api_key:
            raise ValueError("openai_api_key is required")
        if not self.pinecone_api_key:
            raise ValueError("pinecone_api_key is required")
        
        self.chunking.validate()
        self.pinecone.validate()
    
    @classmethod
    def from_dict(cls, config_dict: Dict[str, Any]) -> 'PipelineConfig':
        """Create from legacy dictionary config."""
        return cls(
            llama_api_key=config_dict['llama_api_key'],
            openai_api_key=config_dict['openai_api_key'],
            pinecone_api_key=config_dict['pinecone_api_key'],
            google_credentials=config_dict['google_credentials'],
            parsing=ParsingConfig(
                parsing_mode=config_dict.get('parsing_mode', 'auto'),
                result_type=config_dict.get('result_type', 'markdown'),
                language=config_dict.get('language', 'en'),
                use_vendor_multimodal=config_dict.get('use_vendor_multimodal', True),
                page_separator=config_dict.get('page_separator', '\n---\n')
            ),
            chunking=ChunkingConfig(
                chunking_strategy=config_dict.get('chunking_strategy', 'Token-based'),
                chunk_size=config_dict.get('chunk_size', 1024),
                chunk_overlap=config_dict.get('chunk_overlap', 200),
                semantic_buffer_size=config_dict.get('semantic_buffer_size', 1)
            ),
            embedding=EmbeddingConfig(
                embedding_model=config_dict.get('embedding_model', 'text-embedding-3-small'),
                embedding_dimension=config_dict.get('embedding_dimension')
            ),
            pinecone=PineconeConfig(
                index_name=config_dict['index_name'],
                pinecone_environment=config_dict.get('pinecone_environment', 'us-east-1'),
                default_namespace=config_dict.get('default_namespace', 'default')
            ),
            tagging=TaggingConfig(
                tagging_enabled=config_dict.get('tagging_enabled', False),
                tagging_model=config_dict.get('tagging_model', 'gpt-4o-mini'),
                tagging_prompt_template=config_dict.get('tagging_prompt_template')
            )
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert back to dictionary for backward compatibility."""
        return {
            'llama_api_key': self.llama_api_key,
            'openai_api_key': self.openai_api_key,
            'pinecone_api_key': self.pinecone_api_key,
            'google_credentials': self.google_credentials,
            'parsing_mode': self.parsing.parsing_mode,
            'result_type': self.parsing.result_type,
            'language': self.parsing.language,
            'use_vendor_multimodal': self.parsing.use_vendor_multimodal,
            'page_separator': self.parsing.page_separator,
            'chunking_strategy': self.chunking.chunking_strategy,
            'chunk_size': self.chunking.chunk_size,
            'chunk_overlap': self.chunking.chunk_overlap,
            'semantic_buffer_size': self.chunking.semantic_buffer_size,
            'embedding_model': self.embedding.embedding_model,
            'embedding_dimension': self.embedding.embedding_dimension,
            'index_name': self.pinecone.index_name,
            'pinecone_environment': self.pinecone.pinecone_environment,
            'default_namespace': self.pinecone.default_namespace,
            'tagging_enabled': self.tagging.tagging_enabled,
            'tagging_model': self.tagging.tagging_model,
            'tagging_prompt_template': self.tagging.tagging_prompt_template
        }
```

**Usage:**
```python
# Create config with type safety
config = PipelineConfig(
    llama_api_key="llx-...",
    openai_api_key="sk-...",
    pinecone_api_key="pc-...",
    google_credentials=creds_dict,
    chunking=ChunkingConfig(
        chunk_size=2048,  # IDE will autocomplete!
        chunk_overlap=400
    )
)

# Validate before use
config.validate()  # Raises ValueError if invalid

# Still compatible with legacy code
legacy_dict = config.to_dict()
```

**Benefits:**
- Type safety at development time
- IDE autocomplete for all config options
- Validation before execution
- Self-documenting (field types and defaults)
- Easy to extend

---

## Implementation Order

1. **Start Simple:** Task 1.1 (Connection manager) - Foundation for everything
2. **Fix Types:** Task 1.2 (Type annotations) - Eliminates LSP errors
3. **Add Safety:** Task 1.3 (Error handling) - Production hardening
4. **Pipeline:** Task 1.4 (Pipeline error handling) - User-facing reliability
5. **Consolidate:** Task 2.1 (Embedding factory) - Quick win
6. **Modernize:** Task 2.3 (Config dataclasses) - Better DX
7. **Reorganize:** Task 2.2 (Split database.py) - Last due to file renames

## Testing Strategy

After each major task:
1. Run syntax validation: `python -m py_compile <files>`
2. Check LSP diagnostics reduction
3. Test key functions manually
4. After all tasks: Run end-to-end test via run_test tool

## Success Metrics

**Phase 1:**
- ✅ LSP errors reduced from 93 to <10
- ✅ All database operations have error handling
- ✅ Pipelines never leave jobs in "running" state
- ✅ Connection leaks eliminated

**Phase 2:**
- ✅ No duplicate embedding code
- ✅ database.py split into 7-8 focused modules
- ✅ Config validation catches errors before execution
- ✅ Codebase more maintainable

## Risk Mitigation

1. **Backward Compatibility:** Keep old interfaces working during migration
2. **Incremental Changes:** One task at a time, test after each
3. **Git Checkpoints:** Commit after each successful task
4. **Rollback Plan:** Can revert individual commits if issues arise

---

## Next Steps

1. Mark Task 1.1 as in_progress
2. Create utils/db_utils.py with connection managers
3. Test connection managers work correctly
4. Proceed through tasks 1.2-1.4
5. Then tackle Phase 2 tasks
6. Final architect review
7. End-to-end testing

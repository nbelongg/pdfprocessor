# Code Quality Enhancement Plan
**Project:** PDF Chunking & Embedding Pipeline  
**Created:** October 26, 2025  
**Status:** Ready for Implementation

---

## 📊 Executive Summary

This plan outlines a systematic approach to elevate code quality from 7.5/10 to 9.0-9.5/10 through type safety, modularization, and testing. The plan is divided into 5 phases with clear deliverables and backward compatibility guarantees.

**Total Estimated Time:** 34-38 hours  
**Core Phases (1-3):** 12-16 hours  
**Expected Quality Gain:** +1.5-2.0 points

---

## 🎯 Current State Analysis

### Strengths
- ✅ Recently completed database error handling refactoring (7 functions, 3/3 tests passing)
- ✅ Clean modular Streamlit architecture (app.py: 152 lines)
- ✅ Solid utilities: centralized embedding factory, good separation of concerns
- ✅ Production features: multi-product support, AI tagging, Celery queue, 3-layer deduplication

### Pain Points
1. **Config Type Safety Crisis** - 73 dictionary accesses, no validation, prone to typos
2. **Database Module Size** - 1,212 lines, 57 functions, hard to navigate
3. **Config Building Duplication** - Same logic in tasks.py, scheduler.py, multi_source_pipeline.py
4. **Code Quality Gaps** - 2 print statements, LSP errors, incomplete docstrings
5. **Incomplete Page Modules** - 4 stub pages at 12 lines each

---

# PHASE 1: Foundation - Code Quality & Type Safety

**Duration:** 6-8 hours  
**Impact:** ⭐⭐⭐⭐⭐ Critical  
**Dependencies:** None

## Phase 1.1: Quick Wins (1-2 hours)

### Task 1.1.1: Remove Print Statements
**File:** `utils/deduplication.py`  
**Line:** 58  
**Current:**
```python
print(f"Warning: Layer 3 similarity check failed: {e}")
```
**Change to:**
```python
logger.warning(f"Layer 3 similarity check failed: {e}")
```

**File:** `utils/multi_source_pipeline.py`  
**Line:** 178  
**Current:**
```python
print(f"Warning: Tagging failed for {file_metadata.get('name', '')}: {str(e)}")
```
**Change to:**
```python
logger.warning(f"Tagging failed for {file_metadata.get('name', '')}: {str(e)}")
```

**Verification:**
```bash
grep -r "print(" utils/ --include="*.py"  # Should return 0 results
```

---

### Task 1.1.2: Fix LSP Errors

#### Fix 1: `utils/chunker.py` line 13
**Current:**
```python
def chunk_text(text: str, config: Dict, metadata: Dict = None) -> List[BaseNode]:
```
**Issue:** `None` cannot be assigned to `Dict` type

**Fix:**
```python
from typing import List, Dict, Optional

def chunk_text(text: str, config: Dict, metadata: Optional[Dict] = None) -> List[BaseNode]:
    """
    Chunk text using specified strategy.
    
    Args:
        text: Text content to chunk
        config: Configuration dictionary with chunking settings
        metadata: Optional metadata to attach to chunks
        
    Returns:
        List of BaseNode objects
    """
```

#### Fix 2: `tasks.py` LSP Error
**Action:** Review error details and fix type hint issues

**Verification:**
```bash
python -m py_compile utils/chunker.py utils/deduplication.py utils/multi_source_pipeline.py tasks.py
```

---

### Task 1.1.3: Complete Docstrings

#### Module-Level Docstrings
Add comprehensive module docstrings to:

**`utils/deduplication.py`:**
```python
"""
Three-layer deduplication system for PDF processing.

This module implements a multi-tiered approach to prevent duplicate processing:
- Layer 1: Google Drive file ID lookup (fastest)
- Layer 2: Content hash comparison (title + authors)
- Layer 3: Embedding similarity search (most thorough)

Usage:
    from utils.deduplication import check_all_layers
    
    is_duplicate, existing_data = check_all_layers(
        drive_file_id='abc123',
        paper_title='Sample Paper',
        authors='John Doe',
        embedding=[0.1, 0.2, ...],
        namespace='research',
        pinecone_index=index
    )
"""
```

**`utils/multi_source_pipeline.py`:** (Already has module docstring, enhance if needed)

**`utils/chunker.py`:**
```python
"""
Text chunking utilities for PDF processing pipeline.

This module provides multiple chunking strategies:
- Token-based: Fixed token count chunks with overlap
- Sentence-based: Semantic sentence boundary splitting
- Semantic: AI-powered semantic similarity clustering

All strategies use LlamaIndex node parsers for consistency.

Usage:
    from utils.chunker import chunk_text
    
    config = {'chunking_strategy': 'Token-based', 'chunk_size': 1024}
    nodes = chunk_text(parsed_text, config, metadata={'source': 'paper.pdf'})
"""
```

**`utils/embedder.py`:**
```python
"""
Embedding generation for text chunks.

This module creates vector embeddings from text nodes using the
centralized embedding factory. Supports OpenAI models with custom dimensions.

Usage:
    from utils.embedder import create_embeddings
    
    config = {'embedding_model': 'text-embedding-3-small', 'openai_api_key': '...'}
    embeddings = create_embeddings(nodes, config)
"""
```

#### Function Docstrings
Ensure all public functions have complete Args/Returns/Raises sections.

**Example template:**
```python
def function_name(arg1: Type1, arg2: Type2) -> ReturnType:
    """
    Brief description of what the function does.
    
    Detailed explanation if needed.
    
    Args:
        arg1: Description of arg1
        arg2: Description of arg2
        
    Returns:
        Description of return value
        
    Raises:
        ValueError: When input is invalid
        TransientError: When network fails (retryable)
        
    Examples:
        >>> result = function_name('value', 123)
        >>> print(result)
        'output'
    """
```

---

## Phase 1.2: Type-Safe Configuration System (4-6 hours)

### Overview
Replace dictionary-based configuration with type-safe dataclasses. This prevents configuration bugs, provides IDE autocomplete, and validates settings at creation time.

### Implementation Steps

#### Step 1: Create `config/models.py`

**File structure:**
```python
"""
Type-safe configuration models for PDF processing pipeline.

This module provides dataclasses for all configuration types, replacing
error-prone dictionaries with validated, typed objects.

Benefits:
- IDE autocomplete for all config options
- Runtime validation prevents invalid states
- Self-documenting code
- Backward compatible via from_dict() / to_dict()
- Type checking catches errors before runtime

Usage:
    # New way (type-safe)
    from config.models import ProcessingConfig, ParsingConfig
    
    config = ProcessingConfig(
        parsing=ParsingConfig(parsing_mode='auto'),
        chunking=ChunkingConfig(chunk_size=1024)
    )
    
    # Legacy compatibility
    old_dict = {'parsing_mode': 'auto', 'chunk_size': 1024}
    config = ProcessingConfig.from_dict(old_dict)
"""

from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional, Any
import json
```

#### Step 2: Define Configuration Classes

**2.1 ParsingConfig**
```python
@dataclass
class ParsingConfig:
    """
    LlamaParse PDF parsing configuration.
    
    Attributes:
        parsing_mode: Parsing strategy ('auto', 'fast', 'premium')
        result_type: Output format ('markdown', 'text')
        language: Document language code (e.g., 'en', 'es')
        use_vendor_multimodal: Enable multimodal processing
        vendor_multimodal_model_name: Model for multimodal (default: 'anthropic-sonnet-4')
        page_separator: String to separate pages in output
        parsing_instruction: Optional custom instructions
    """
    parsing_mode: str = 'auto'
    result_type: str = 'markdown'
    language: str = 'en'
    use_vendor_multimodal: bool = True
    vendor_multimodal_model_name: str = 'anthropic-sonnet-4'
    page_separator: str = '\n---\n'
    parsing_instruction: str = ''
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        valid_modes = ['auto', 'fast', 'premium']
        if self.parsing_mode not in valid_modes:
            raise ValueError(f"parsing_mode must be one of {valid_modes}, got '{self.parsing_mode}'")
        
        valid_types = ['markdown', 'text']
        if self.result_type not in valid_types:
            raise ValueError(f"result_type must be one of {valid_types}, got '{self.result_type}'")
        
        if len(self.language) != 2:
            raise ValueError(f"language must be 2-letter code, got '{self.language}'")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ParsingConfig':
        """Create from dictionary (backward compatibility)."""
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (legacy compatibility)."""
        return asdict(self)
```

**2.2 ChunkingConfig**
```python
@dataclass
class ChunkingConfig:
    """
    Text chunking configuration.
    
    Attributes:
        strategy: Chunking method ('Token-based', 'Sentence-based', 'Semantic')
        chunk_size: Target chunk size in tokens
        chunk_overlap: Overlap between chunks in tokens
        semantic_buffer_size: Buffer size for semantic chunking
    """
    strategy: str = 'Token-based'
    chunk_size: int = 1024
    chunk_overlap: int = 200
    semantic_buffer_size: int = 1
    
    def __post_init__(self):
        """Validate configuration."""
        valid_strategies = ['Token-based', 'Sentence-based', 'Semantic']
        if self.strategy not in valid_strategies:
            raise ValueError(f"strategy must be one of {valid_strategies}")
        
        if self.chunk_size < 100:
            raise ValueError(f"chunk_size must be >= 100, got {self.chunk_size}")
        
        if self.chunk_size > 8192:
            raise ValueError(f"chunk_size must be <= 8192, got {self.chunk_size}")
        
        if self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {self.chunk_overlap}")
        
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"chunk_overlap must be < chunk_size")
        
        if self.semantic_buffer_size < 1:
            raise ValueError(f"semantic_buffer_size must be >= 1")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkingConfig':
        """Create from dictionary."""
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
```

**2.3 EmbeddingConfig**
```python
@dataclass
class EmbeddingConfig:
    """
    Embedding model configuration.
    
    Attributes:
        model: Embedding model name (e.g., 'text-embedding-3-small')
        dimension: Optional custom dimension (None = use model default)
        api_key: OpenAI API key
    """
    model: str = 'text-embedding-3-small'
    dimension: Optional[int] = None
    api_key: str = ''
    
    def __post_init__(self):
        """Validate configuration."""
        valid_models = [
            'text-embedding-3-small',
            'text-embedding-3-large',
            'text-embedding-ada-002'
        ]
        
        if not any(valid in self.model for valid in valid_models):
            raise ValueError(f"model must contain one of {valid_models}")
        
        if self.dimension is not None:
            if self.dimension < 1:
                raise ValueError(f"dimension must be > 0, got {self.dimension}")
            if self.dimension > 3072:
                raise ValueError(f"dimension must be <= 3072, got {self.dimension}")
        
        if not self.api_key:
            raise ValueError("api_key is required")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmbeddingConfig':
        """Create from dictionary."""
        # Handle legacy 'embedding_model' key
        if 'embedding_model' in data and 'model' not in data:
            data['model'] = data['embedding_model']
        
        # Handle legacy 'openai_api_key' key
        if 'openai_api_key' in data and 'api_key' not in data:
            data['api_key'] = data['openai_api_key']
        
        # Handle legacy 'embedding_dimension' key
        if 'embedding_dimension' in data and 'dimension' not in data:
            data['dimension'] = data['embedding_dimension']
        
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with legacy keys."""
        d = asdict(self)
        # Add legacy keys for backward compatibility
        d['embedding_model'] = d['model']
        d['openai_api_key'] = d['api_key']
        if d['dimension'] is not None:
            d['embedding_dimension'] = d['dimension']
        return d
```

**2.4 TaggingConfig**
```python
@dataclass
class TaggingConfig:
    """
    AI-powered document tagging configuration.
    
    Attributes:
        enabled: Whether to enable AI tagging
        model: OpenAI model for tagging ('gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo')
        prompt_template: Template for tagging prompt (supports {text}, {filename}, etc.)
        max_tags: Maximum number of tags to generate
        api_key: OpenAI API key
    """
    enabled: bool = False
    model: str = 'gpt-4o-mini'
    prompt_template: str = 'Generate 5-10 relevant tags for this document:\n\n{text}'
    max_tags: int = 10
    api_key: str = ''
    
    def __post_init__(self):
        """Validate configuration."""
        if self.enabled:
            valid_models = ['gpt-4o', 'gpt-4o-mini', 'gpt-3.5-turbo']
            if self.model not in valid_models:
                raise ValueError(f"model must be one of {valid_models}")
            
            if not self.api_key:
                raise ValueError("api_key is required when tagging is enabled")
            
            if self.max_tags < 1:
                raise ValueError(f"max_tags must be >= 1, got {self.max_tags}")
            
            if self.max_tags > 50:
                raise ValueError(f"max_tags must be <= 50, got {self.max_tags}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaggingConfig':
        """Create from dictionary."""
        # Handle legacy keys
        if 'tagging_enabled' in data and 'enabled' not in data:
            data['enabled'] = data['tagging_enabled']
        if 'tagging_model' in data and 'model' not in data:
            data['model'] = data['tagging_model']
        if 'tagging_prompt_template' in data and 'prompt_template' not in data:
            data['prompt_template'] = data['tagging_prompt_template']
        if 'openai_api_key' in data and 'api_key' not in data:
            data['api_key'] = data['openai_api_key']
        
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with legacy keys."""
        d = asdict(self)
        d['tagging_enabled'] = d['enabled']
        d['tagging_model'] = d['model']
        d['tagging_prompt_template'] = d['prompt_template']
        return d
```

**2.5 PineconeConfig**
```python
@dataclass
class PineconeConfig:
    """
    Pinecone vector database configuration.
    
    Attributes:
        api_key: Pinecone API key
        index_name: Name of the Pinecone index
        environment: Pinecone environment (e.g., 'us-east-1')
        namespace: Default namespace for vectors
        dimension: Vector dimension (must match embedding model)
    """
    api_key: str = ''
    index_name: str = ''
    environment: str = 'us-east-1'
    namespace: str = 'default'
    dimension: int = 1536
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.api_key:
            raise ValueError("api_key is required")
        
        if not self.index_name:
            raise ValueError("index_name is required")
        
        if self.dimension < 1:
            raise ValueError(f"dimension must be > 0, got {self.dimension}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PineconeConfig':
        """Create from dictionary."""
        # Handle legacy keys
        if 'pinecone_api_key' in data and 'api_key' not in data:
            data['api_key'] = data['pinecone_api_key']
        if 'pinecone_environment' in data and 'environment' not in data:
            data['environment'] = data['pinecone_environment']
        if 'default_namespace' in data and 'namespace' not in data:
            data['namespace'] = data['default_namespace']
        
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with legacy keys."""
        d = asdict(self)
        d['pinecone_api_key'] = d['api_key']
        d['pinecone_environment'] = d['environment']
        d['default_namespace'] = d['namespace']
        return d
```

**2.6 GoogleConfig**
```python
@dataclass
class GoogleConfig:
    """
    Google Cloud Platform configuration.
    
    Attributes:
        credentials: Service account JSON as string or dict
        project_id: Optional GCP project ID
    """
    credentials: Any = ''  # Can be string or dict
    project_id: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.credentials:
            raise ValueError("credentials is required")
        
        # Parse JSON string to dict if needed
        if isinstance(self.credentials, str):
            try:
                self.credentials = json.loads(self.credentials)
            except json.JSONDecodeError as e:
                raise ValueError(f"credentials must be valid JSON: {e}")
        
        # Validate it's a dict with required keys
        if not isinstance(self.credentials, dict):
            raise ValueError("credentials must be a dict or JSON string")
        
        required_keys = ['type', 'project_id', 'private_key', 'client_email']
        missing = [k for k in required_keys if k not in self.credentials]
        if missing:
            raise ValueError(f"credentials missing required keys: {missing}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GoogleConfig':
        """Create from dictionary."""
        # Handle legacy key
        if 'google_credentials' in data and 'credentials' not in data:
            data['credentials'] = data['google_credentials']
        
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'google_credentials': self.credentials,
            'project_id': self.project_id
        }
```

**2.7 DeduplicationConfig**
```python
@dataclass
class DeduplicationConfig:
    """
    Three-layer deduplication configuration.
    
    Attributes:
        enabled: Whether to enable deduplication
        check_layer1: Check by Drive file ID
        check_layer2: Check by content hash
        check_layer3: Check by embedding similarity
        similarity_threshold: Threshold for layer 3 (0.0-1.0)
    """
    enabled: bool = True
    check_layer1: bool = True
    check_layer2: bool = True
    check_layer3: bool = False
    similarity_threshold: float = 0.95
    
    def __post_init__(self):
        """Validate configuration."""
        if self.similarity_threshold < 0.0 or self.similarity_threshold > 1.0:
            raise ValueError(f"similarity_threshold must be 0.0-1.0, got {self.similarity_threshold}")
        
        if self.check_layer3 and self.similarity_threshold < 0.8:
            raise ValueError("similarity_threshold should be >= 0.8 for meaningful results")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DeduplicationConfig':
        """Create from dictionary."""
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
```

**2.8 ScheduleConfig**
```python
@dataclass
class ScheduleConfig:
    """
    Scheduled job configuration.
    
    Attributes:
        frequency: Frequency ('daily', 'weekly', 'monthly')
        max_papers_per_run: Maximum papers to process per run
        enabled: Whether schedule is active
    """
    frequency: str = 'daily'
    max_papers_per_run: int = 100
    enabled: bool = False
    
    def __post_init__(self):
        """Validate configuration."""
        valid_frequencies = ['daily', 'weekly', 'monthly']
        if self.frequency not in valid_frequencies:
            raise ValueError(f"frequency must be one of {valid_frequencies}")
        
        if self.max_papers_per_run < 1:
            raise ValueError(f"max_papers_per_run must be >= 1")
        
        if self.max_papers_per_run > 1000:
            raise ValueError(f"max_papers_per_run must be <= 1000")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduleConfig':
        """Create from dictionary."""
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
```

**2.9 ProcessingConfig (Master)**
```python
@dataclass
class ProcessingConfig:
    """
    Complete processing configuration combining all sub-configs.
    
    This is the master configuration object that includes all settings
    for the entire PDF processing pipeline.
    
    Attributes:
        parsing: PDF parsing settings
        chunking: Text chunking settings
        embedding: Embedding generation settings
        tagging: AI tagging settings
        pinecone: Vector storage settings
        google: Google Cloud settings
        deduplication: Deduplication settings
        schedule: Scheduled job settings
    """
    parsing: ParsingConfig = field(default_factory=ParsingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    tagging: TaggingConfig = field(default_factory=TaggingConfig)
    pinecone: PineconeConfig = field(default_factory=PineconeConfig)
    google: GoogleConfig = field(default_factory=GoogleConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    schedule: ScheduleConfig = field(default_factory=ScheduleConfig)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ProcessingConfig':
        """
        Create from flat dictionary (backward compatibility).
        
        Automatically groups keys into appropriate sub-configs.
        """
        # Create sub-configs from flat dict
        parsing = ParsingConfig.from_dict(data)
        chunking = ChunkingConfig.from_dict(data)
        embedding = EmbeddingConfig.from_dict(data)
        tagging = TaggingConfig.from_dict(data)
        pinecone = PineconeConfig.from_dict(data)
        google = GoogleConfig.from_dict(data)
        deduplication = DeduplicationConfig.from_dict(data)
        schedule = ScheduleConfig.from_dict(data)
        
        return cls(
            parsing=parsing,
            chunking=chunking,
            embedding=embedding,
            tagging=tagging,
            pinecone=pinecone,
            google=google,
            deduplication=deduplication,
            schedule=schedule
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to flat dictionary (legacy compatibility).
        
        Merges all sub-config dictionaries into one flat dict.
        """
        result = {}
        result.update(self.parsing.to_dict())
        result.update(self.chunking.to_dict())
        result.update(self.embedding.to_dict())
        result.update(self.tagging.to_dict())
        result.update(self.pinecone.to_dict())
        result.update(self.google.to_dict())
        result.update(self.deduplication.to_dict())
        result.update(self.schedule.to_dict())
        return result
```

#### Step 3: Testing Config Models

Create `tests/test_config_models.py`:

```python
"""
Unit tests for type-safe configuration models.
"""

import pytest
from config.models import (
    ParsingConfig, ChunkingConfig, EmbeddingConfig, TaggingConfig,
    PineconeConfig, GoogleConfig, DeduplicationConfig, ScheduleConfig,
    ProcessingConfig
)


class TestParsingConfig:
    def test_valid_config(self):
        """Test creating valid parsing config"""
        config = ParsingConfig(parsing_mode='auto', result_type='markdown')
        assert config.parsing_mode == 'auto'
        assert config.result_type == 'markdown'
    
    def test_invalid_parsing_mode(self):
        """Test that invalid parsing mode raises error"""
        with pytest.raises(ValueError, match="parsing_mode must be one of"):
            ParsingConfig(parsing_mode='invalid')
    
    def test_invalid_result_type(self):
        """Test that invalid result type raises error"""
        with pytest.raises(ValueError, match="result_type must be one of"):
            ParsingConfig(result_type='invalid')
    
    def test_from_dict(self):
        """Test backward compatibility from dict"""
        data = {'parsing_mode': 'fast', 'result_type': 'text', 'extra_key': 'ignored'}
        config = ParsingConfig.from_dict(data)
        assert config.parsing_mode == 'fast'
        assert config.result_type == 'text'
    
    def test_to_dict(self):
        """Test conversion to dict"""
        config = ParsingConfig(parsing_mode='premium')
        d = config.to_dict()
        assert d['parsing_mode'] == 'premium'


class TestChunkingConfig:
    def test_valid_config(self):
        """Test creating valid chunking config"""
        config = ChunkingConfig(strategy='Token-based', chunk_size=512)
        assert config.strategy == 'Token-based'
        assert config.chunk_size == 512
    
    def test_invalid_strategy(self):
        """Test that invalid strategy raises error"""
        with pytest.raises(ValueError, match="strategy must be one of"):
            ChunkingConfig(strategy='invalid')
    
    def test_chunk_size_too_small(self):
        """Test that chunk_size < 100 raises error"""
        with pytest.raises(ValueError, match="chunk_size must be >= 100"):
            ChunkingConfig(chunk_size=50)
    
    def test_overlap_too_large(self):
        """Test that overlap >= chunk_size raises error"""
        with pytest.raises(ValueError, match="chunk_overlap must be < chunk_size"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)


class TestEmbeddingConfig:
    def test_valid_config(self):
        """Test creating valid embedding config"""
        config = EmbeddingConfig(
            model='text-embedding-3-small',
            api_key='sk-test'
        )
        assert config.model == 'text-embedding-3-small'
    
    def test_missing_api_key(self):
        """Test that missing API key raises error"""
        with pytest.raises(ValueError, match="api_key is required"):
            EmbeddingConfig(model='text-embedding-3-small', api_key='')
    
    def test_custom_dimension(self):
        """Test custom dimension validation"""
        config = EmbeddingConfig(
            model='text-embedding-3-large',
            dimension=2048,
            api_key='sk-test'
        )
        assert config.dimension == 2048
    
    def test_invalid_dimension(self):
        """Test that invalid dimension raises error"""
        with pytest.raises(ValueError, match="dimension must be > 0"):
            EmbeddingConfig(
                model='text-embedding-3-small',
                dimension=0,
                api_key='sk-test'
            )
    
    def test_legacy_keys(self):
        """Test backward compatibility with legacy keys"""
        data = {
            'embedding_model': 'text-embedding-3-small',
            'openai_api_key': 'sk-test',
            'embedding_dimension': 1536
        }
        config = EmbeddingConfig.from_dict(data)
        assert config.model == 'text-embedding-3-small'
        assert config.api_key == 'sk-test'
        assert config.dimension == 1536


class TestProcessingConfig:
    def test_from_flat_dict(self):
        """Test creating ProcessingConfig from flat dict"""
        data = {
            'parsing_mode': 'auto',
            'chunk_size': 1024,
            'embedding_model': 'text-embedding-3-small',
            'openai_api_key': 'sk-test',
            'pinecone_api_key': 'pc-test',
            'index_name': 'my-index',
            'google_credentials': '{"type":"service_account","project_id":"test"}',
        }
        
        config = ProcessingConfig.from_dict(data)
        
        assert config.parsing.parsing_mode == 'auto'
        assert config.chunking.chunk_size == 1024
        assert config.embedding.model == 'text-embedding-3-small'
        assert config.pinecone.index_name == 'my-index'
    
    def test_to_flat_dict(self):
        """Test converting ProcessingConfig to flat dict"""
        config = ProcessingConfig(
            parsing=ParsingConfig(parsing_mode='fast'),
            chunking=ChunkingConfig(chunk_size=512)
        )
        
        d = config.to_dict()
        
        assert d['parsing_mode'] == 'fast'
        assert d['chunk_size'] == 512
```

#### Step 4: Usage Examples

**Example 1: New Code (Type-Safe)**
```python
from config.models import ProcessingConfig, ParsingConfig, ChunkingConfig

# Create with validation
config = ProcessingConfig(
    parsing=ParsingConfig(parsing_mode='auto', result_type='markdown'),
    chunking=ChunkingConfig(chunk_size=1024, strategy='Token-based')
)

# IDE autocomplete works!
print(config.parsing.parsing_mode)  # ✅ Autocomplete suggests 'parsing_mode'

# Validation catches errors at creation
try:
    bad_config = ParsingConfig(parsing_mode='invalid')  # ❌ Raises ValueError immediately
except ValueError as e:
    print(f"Configuration error: {e}")
```

**Example 2: Legacy Code (Backward Compatible)**
```python
from config.models import ProcessingConfig

# Old dictionary-based config still works
legacy_dict = {
    'parsing_mode': 'auto',
    'chunk_size': 1024,
    'embedding_model': 'text-embedding-3-small',
    'openai_api_key': 'sk-...',
    # ... 20 more keys
}

# Convert to type-safe config
config = ProcessingConfig.from_dict(legacy_dict)

# Use in new code
validated_settings = config.parsing.to_dict()
```

**Example 3: Product Configuration Loading**
```python
from config.models import ProcessingConfig
from utils.database import get_product

def load_product_config(product_id: int) -> ProcessingConfig:
    """Load and validate product configuration from database."""
    product = get_product(product_id)
    
    # Database returns dict
    product_dict = {
        'parsing_mode': product['parsing_mode'],
        'chunk_size': product['default_chunk_size'],
        # ... all product settings
    }
    
    # Convert to type-safe config with validation
    try:
        config = ProcessingConfig.from_dict(product_dict)
        return config
    except ValueError as e:
        raise ValueError(f"Invalid product {product_id} configuration: {e}")
```

### Migration Strategy

**Phase 1: Co-existence (Immediate)**
- Config models exist alongside dict-based config
- New code can use type-safe config
- Old code continues using dicts
- No breaking changes

**Phase 2: Gradual Adoption (Optional)**
- Use `from_dict()` to convert legacy dicts
- New features use config models exclusively
- Old features migrate opportunistically

**Phase 3: Full Migration (Future)**
- All code uses config models
- Remove `from_dict()` / `to_dict()` compatibility layer
- Pure type-safe codebase

### Validation Benefits

**Before (Dict-based):**
```python
config = {'parsing_mode': 'autoo'}  # Typo! Won't catch until LlamaParse call
result = parse_pdf(pdf, config)  # ❌ Fails after expensive download
```

**After (Type-safe):**
```python
try:
    config = ParsingConfig(parsing_mode='autoo')  # ✅ Fails immediately
except ValueError as e:
    print(f"Config error: {e}")  # Caught before any work done
```

---

# PHASE 2: Database Modularization

**Duration:** 5-6 hours  
**Impact:** ⭐⭐⭐⭐ High  
**Dependencies:** None (can run parallel to Phase 1)

## Overview

Split `utils/database.py` (1,212 lines, 57 functions) into focused modules organized by domain.

## Critical Constraint

**MUST PRESERVE** recent error handling migration:
- 7 functions use `@with_db_error_handling` decorator
- All use `get_db_transaction()` context manager
- Zero manual commits remaining

## Implementation Steps

### Step 1: Create Module Structure

```bash
mkdir -p utils/db
touch utils/db/__init__.py
```

### Step 2: Module Organization

**Domain-Based Split:**

```
utils/db/
├── __init__.py              # Export all (backward compatibility)
├── connection.py            # ✅ Already exists (39 lines)
├── products.py              # Product management (~300 lines, 7 functions)
├── jobs.py                  # Processing jobs & chunks (~400 lines, 14 functions)
├── documents.py             # Parsed docs & deduplication (~350 lines, 12 functions)
├── sources.py               # Data sources & mappings (~350 lines, 15 functions)
└── scheduling.py            # Scheduled jobs (~250 lines, 9 functions)
```

### Step 3: Create `utils/db/products.py`

**Functions to move (preserve decorators!):**
```python
"""
Product management database operations.

This module handles all database operations for products:
- CRUD operations
- API key retrieval
- Configuration management
"""

import logging
from typing import Dict, List, Optional, Any
import psycopg2
from psycopg2.extras import RealDictCursor, Json

from utils.exceptions import DatabaseError, DatabaseTransientError
from utils.db_utils import get_db_transaction, with_db_error_handling

logger = logging.getLogger(__name__)


# ===== COPIED FROM database.py WITH DECORATORS PRESERVED =====

@with_db_error_handling  # ✅ PRESERVE THIS
def init_products_table():
    """Initialize products table."""
    with get_db_transaction() as conn:  # ✅ PRESERVE THIS
        # ... rest of function EXACTLY as is
        pass


def get_products() -> List[Dict[str, Any]]:
    """Get all active products."""
    # ... copy function exactly


def get_product(product_id: int) -> Optional[Dict[str, Any]]:
    """Get product by ID."""
    # ... copy function exactly


# ... Copy all 7 product-related functions
```

### Step 4: Create `utils/db/jobs.py`

**Functions to move:**
- `create_processing_job()` ✅ Has decorator
- `update_job_status()` ✅ Has decorator
- `save_chunks()` ✅ Has decorator
- `mark_chunks_uploaded()` ✅ Has decorator
- `get_job_history()`
- `get_job_details()`
- `get_job_chunks()`
- ... (14 total)

### Step 5: Create `utils/db/documents.py`

**Functions to move:**
- `save_parsed_document()` ✅ Has decorator
- `update_document_tags()` ✅ Has decorator
- `get_parsed_document()`
- `get_document_tags()`
- `check_paper_processed()`
- ... (12 total)

### Step 6: Create `utils/db/sources.py`

**Functions to move:**
- `create_data_source()`
- `get_data_source()`
- `update_data_source()`
- `delete_data_source()`
- `get_column_mapping_dict()`
- ... (15 total)

### Step 7: Create `utils/db/scheduling.py`

**Functions to move:**
- `create_scheduled_job()`
- `get_all_scheduled_jobs()`
- `update_scheduled_job_run_time()`
- ... (9 total)

### Step 8: Create Backward-Compatible `__init__.py`

```python
"""
Database operations package.

This package organizes database operations by domain for better maintainability.
All functions are re-exported for backward compatibility.

Usage:
    # New way (recommended)
    from utils.db.products import get_products
    from utils.db import get_products  # Also works
    
    # Old way (still works)
    from utils.database import get_products
"""

# Re-export everything for backward compatibility
from .connection import *
from .products import *
from .jobs import *
from .documents import *
from .sources import *
from .scheduling import *

__all__ = [
    # Products
    'init_products_table',
    'get_products',
    'get_product',
    'create_product',
    'update_product',
    'delete_product',
    'get_product_api_keys',
    
    # Jobs
    'create_processing_job',
    'update_job_status',
    'save_chunks',
    'mark_chunks_uploaded',
    'get_job_history',
    'get_job_details',
    'get_job_chunks',
    # ... list all 57 functions
]
```

### Step 9: Create Compatibility Shim (Optional)

**Option A:** Rename old file
```bash
mv utils/database.py utils/database_old.py
```

**Option B:** Create shim that imports from new modules
```python
# utils/database.py
"""
Backward compatibility shim.

This file re-exports all database functions from the new modular structure.
Deprecated: Use `from utils.db import ...` instead.
"""

import warnings

# Warn on first import
warnings.warn(
    "Importing from utils.database is deprecated. "
    "Use 'from utils.db import ...' instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export everything
from utils.db import *
```

### Step 10: Verification

**Test imports work:**
```python
# Test old imports still work
from utils.database import get_products, create_processing_job
print("✅ Old imports work")

# Test new imports work
from utils.db import get_products, create_processing_job
from utils.db.products import get_products
from utils.db.jobs import create_processing_job
print("✅ New imports work")
```

**Re-run integration tests:**
```bash
python test_error_handling.py
# Should still show 3/3 passing
```

### Step 11: Update Imports (Optional, can be done gradually)

**High-traffic files to update:**
- `tasks.py`
- `scheduler.py`
- `multi_source_pipeline.py`
- `page_modules/products.py`
- `page_modules/data_sources.py`

**Before:**
```python
from utils.database import get_products, get_data_source
```

**After:**
```python
from utils.db import get_products, get_data_source
# or
from utils.db.products import get_products
from utils.db.sources import get_data_source
```

## Benefits

- ✅ 73% reduction in largest file (1,212 → 423 lines max)
- ✅ Clear domain separation
- ✅ All error handling preserved
- ✅ 100% backward compatible
- ✅ Easier code navigation
- ✅ Better organization for team collaboration

---

# PHASE 3: Extract Shared Logic

**Duration:** 3-4 hours  
**Impact:** ⭐⭐⭐ Medium-High  
**Dependencies:** None

## Overview

Eliminate config building duplication across `tasks.py`, `scheduler.py`, and `multi_source_pipeline.py`.

## Current Duplication

**`PRODUCT_CONFIG_MAPPING` defined in:**
- `tasks.py` lines 76-81
- `scheduler.py` lines 68-73

**Config building logic in:**
- `tasks.py` `apply_product_config()` function
- `scheduler.py` inline config building
- Potentially `multi_source_pipeline.py`

## Implementation

### Step 1: Create `utils/config_builder.py`

```python
"""
Centralized product configuration builder.

This module provides a single source of truth for building product
configurations from database records, eliminating duplication across
tasks.py, scheduler.py, and pipeline modules.

Usage:
    from utils.config_builder import build_product_config
    
    # Build config for a product
    config = build_product_config(product_id=1)
    
    # Build config with base settings
    config = build_product_config(
        product_id=1,
        base_config={'extra_setting': 'value'}
    )
"""

import logging
from typing import Dict, Any, Optional
import json
import os

from utils.database import get_product, get_product_api_keys
from utils.exceptions import DatabaseError

logger = logging.getLogger(__name__)


# ============================================
# CONSTANTS - Single Source of Truth
# ============================================

PRODUCT_CONFIG_MAPPING = {
    'llama_api_key': 'LLAMA_CLOUD_API_KEY',
    'openai_api_key': 'OPENAI_API_KEY',
    'pinecone_api_key': 'PINECONE_API_KEY',
    'google_credentials': 'GOOGLE_CREDENTIALS'
}

PRODUCT_SETTINGS_MAPPING = {
    'index_name': 'pinecone_index',
    'pinecone_environment': 'pinecone_environment',
    'default_namespace': 'default_namespace',
    'parsing_mode': 'parsing_mode',
    'result_type': 'result_type',
    'language': 'language',
    'use_vendor_multimodal': 'use_vendor_multimodal',
    'page_separator': 'page_separator',
    'chunking_strategy': 'default_chunking_strategy',
    'chunk_size': 'default_chunk_size',
    'chunk_overlap': 'chunk_overlap',
    'semantic_buffer_size': 'semantic_buffer_size',
    'embedding_model': 'default_embedding_model',
    'embedding_dimension': 'embedding_dimension',
    'tagging_enabled': 'tagging_enabled',
    'tagging_model': 'tagging_model',
    'tagging_prompt_template': 'tagging_prompt_template'
}


# ============================================
# CONFIG BUILDER
# ============================================

def build_product_config(
    product_id: int,
    base_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build complete product configuration from database.
    
    This function:
    1. Loads product info from database
    2. Retrieves API keys from environment (via product secrets)
    3. Merges product settings with base config
    4. Returns complete configuration dict
    
    Args:
        product_id: Product ID to load config for
        base_config: Optional base configuration to extend
        
    Returns:
        Complete configuration dictionary ready for processing
        
    Raises:
        DatabaseError: If product not found or database error
        ValueError: If required API keys are missing
        
    Examples:
        >>> config = build_product_config(product_id=1)
        >>> print(config['parsing_mode'])
        'auto'
        
        >>> config = build_product_config(
        ...     product_id=1,
        ...     base_config={'custom_setting': 'value'}
        ... )
    """
    # Start with base config or empty dict
    config = base_config.copy() if base_config else {}
    
    # Load product info
    product = get_product(product_id)
    if not product:
        raise ValueError(f"Product {product_id} not found")
    
    logger.info(f"Building config for product: {product.get('name')}")
    
    # Get API keys from environment (using secret names)
    api_keys = get_product_api_keys(product_id)
    
    # Apply API keys using mapping dict
    for config_key, api_key_name in PRODUCT_CONFIG_MAPPING.items():
        value = api_keys.get(api_key_name)
        if value:
            config[config_key] = value
            logger.debug(f"Set {config_key} from {api_key_name}")
        else:
            logger.warning(f"Missing API key: {api_key_name}")
    
    # Apply product settings using mapping dict
    for config_key, product_key in PRODUCT_SETTINGS_MAPPING.items():
        value = product.get(product_key)
        if value is not None:
            config[config_key] = value
            logger.debug(f"Set {config_key} = {value}")
    
    # Validate required keys
    required_keys = ['llama_api_key', 'openai_api_key', 'pinecone_api_key']
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        raise ValueError(f"Missing required API keys for product {product_id}: {missing}")
    
    logger.info(f"Successfully built config for product {product_id}")
    return config


def get_product_config_from_source(source_id: int) -> Dict[str, Any]:
    """
    Build product config from data source ID.
    
    Convenience function that looks up the product ID from a data source
    and builds the config.
    
    Args:
        source_id: Data source ID
        
    Returns:
        Complete product configuration
    """
    from utils.database import get_data_source
    
    source = get_data_source(source_id)
    if not source:
        raise ValueError(f"Data source {source_id} not found")
    
    product_id = source.get('product_id')
    if not product_id:
        raise ValueError(f"Data source {source_id} has no product assigned")
    
    return build_product_config(product_id)
```

### Step 2: Update `tasks.py`

**Remove duplicates:**
```python
# DELETE these lines (76-103)
# PRODUCT_CONFIG_MAPPING = { ... }
# PRODUCT_SETTINGS_MAPPING = { ... }

# DELETE the apply_product_config() function (174-203)
```

**Add import:**
```python
from utils.config_builder import build_product_config
```

**Update usage:**
```python
# OLD (lines 430-440):
# product_info = get_product(product_id)
# api_keys = get_product_api_keys(product_id)
# apply_product_config(config, product_info)

# NEW:
from utils.config_builder import build_product_config

config = build_product_config(product_id, base_config=config)
```

### Step 3: Update `scheduler.py`

**Remove duplicates:**
```python
# DELETE lines 67-73
# PRODUCT_CONFIG_MAPPING = { ... }
```

**Add import:**
```python
from utils.config_builder import build_product_config
```

**Update usage in `process_scheduled_job()` function:**
```python
# OLD (lines 430-445):
# product_info = get_product(product_id)
# api_keys = get_product_api_keys(product_id)
# for config_key, api_key in PRODUCT_CONFIG_MAPPING.items():
#     if api_keys.get(api_key):
#         config[config_key] = api_keys[api_key]

# NEW:
config = build_product_config(product_id)
```

### Step 4: Review `multi_source_pipeline.py`

Check if it has similar config building logic. If yes, replace with `build_product_config()`.

### Step 5: Verification

**Test config builder:**
```python
from utils.config_builder import build_product_config

# Test with existing product
config = build_product_config(product_id=1)
assert 'llama_api_key' in config
assert 'parsing_mode' in config
print("✅ Config builder works")
```

**Run integration tests:**
```bash
python test_error_handling.py
```

## Benefits

- ✅ DRY principle - single source of truth
- ✅ Easier maintenance - change logic in one place
- ✅ Consistency - all modules use same logic
- ✅ Better testability - centralized unit tests

---

# PHASE 4: Testing Infrastructure (Optional)

**Duration:** 8-10 hours  
**Impact:** ⭐⭐⭐⭐ High (Defensive)  
**Dependencies:** Phase 1.2 (config models make testing easier)

## Overview

Create comprehensive test suite with pytest for unit and integration tests.

## Implementation

### Step 1: Setup Pytest

**Install pytest:**
```bash
pip install pytest pytest-cov pytest-mock
```

**Create `pytest.ini`:**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = 
    -v
    --tb=short
    --strict-markers
    --cov=utils
    --cov=config
    --cov-report=term-missing
    --cov-report=html
markers =
    unit: Unit tests
    integration: Integration tests
    slow: Slow tests
```

### Step 2: Create Test Structure

```bash
mkdir -p tests/{unit,integration,fixtures}
touch tests/__init__.py
touch tests/conftest.py
```

### Step 3: Create Fixtures (`tests/conftest.py`)

```python
"""
Pytest fixtures for testing.
"""

import pytest
import os
from unittest.mock import Mock, MagicMock
from typing import Dict, Any


@pytest.fixture
def mock_db_connection():
    """Mock database connection."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    return conn, cursor


@pytest.fixture
def sample_config() -> Dict[str, Any]:
    """Sample processing configuration."""
    return {
        'parsing_mode': 'auto',
        'result_type': 'markdown',
        'chunk_size': 1024,
        'chunk_overlap': 200,
        'chunking_strategy': 'Token-based',
        'embedding_model': 'text-embedding-3-small',
        'openai_api_key': 'sk-test',
        'pinecone_api_key': 'pc-test',
        'llama_api_key': 'llx-test',
        'index_name': 'test-index',
        'pinecone_environment': 'us-east-1',
        'default_namespace': 'test'
    }


@pytest.fixture
def sample_metadata() -> Dict[str, Any]:
    """Sample document metadata."""
    return {
        'title': 'Sample Paper',
        'authors': 'John Doe, Jane Smith',
        'year': '2024',
        'source': 'test.pdf'
    }


@pytest.fixture
def mock_openai():
    """Mock OpenAI API."""
    with patch('openai.Embedding.create') as mock:
        mock.return_value = {
            'data': [{'embedding': [0.1] * 1536}]
        }
        yield mock


@pytest.fixture
def mock_pinecone():
    """Mock Pinecone index."""
    index = MagicMock()
    index.upsert.return_value = {'upserted_count': 10}
    index.query.return_value = {'matches': []}
    return index
```

### Step 4: Unit Tests

**`tests/unit/test_chunker.py`:**
```python
"""Unit tests for chunker module."""

import pytest
from utils.chunker import chunk_text


class TestChunker:
    def test_token_based_chunking(self, sample_config):
        """Test token-based chunking."""
        text = "This is a test. " * 200  # Long text
        config = {**sample_config, 'chunking_strategy': 'Token-based', 'chunk_size': 100}
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 0
        assert all(node.text for node in nodes)
    
    def test_sentence_based_chunking(self, sample_config):
        """Test sentence-based chunking."""
        text = "First sentence. Second sentence. Third sentence."
        config = {**sample_config, 'chunking_strategy': 'Sentence-based'}
        
        nodes = chunk_text(text, config)
        
        assert len(nodes) > 0
    
    def test_metadata_preserved(self, sample_config, sample_metadata):
        """Test that metadata is preserved in chunks."""
        text = "Test text"
        
        nodes = chunk_text(text, sample_config, metadata=sample_metadata)
        
        assert all(node.metadata.get('title') == 'Sample Paper' for node in nodes)
```

**`tests/unit/test_config_models.py`:**
```python
"""Unit tests for configuration models."""

import pytest
from config.models import (
    ParsingConfig, ChunkingConfig, EmbeddingConfig,
    ProcessingConfig
)


class TestParsingConfig:
    def test_valid_config(self):
        config = ParsingConfig(parsing_mode='auto')
        assert config.parsing_mode == 'auto'
    
    def test_invalid_parsing_mode(self):
        with pytest.raises(ValueError, match="parsing_mode"):
            ParsingConfig(parsing_mode='invalid')
    
    def test_from_dict(self):
        data = {'parsing_mode': 'fast', 'result_type': 'text'}
        config = ParsingConfig.from_dict(data)
        assert config.parsing_mode == 'fast'


class TestChunkingConfig:
    def test_chunk_size_validation(self):
        with pytest.raises(ValueError, match="chunk_size"):
            ChunkingConfig(chunk_size=50)  # Too small
    
    def test_overlap_validation(self):
        with pytest.raises(ValueError, match="chunk_overlap"):
            ChunkingConfig(chunk_size=100, chunk_overlap=100)  # Too large
```

**`tests/unit/test_deduplication.py`:**
```python
"""Unit tests for deduplication."""

import pytest
from utils.deduplication import generate_content_hash, check_duplicate_layer2


class TestDeduplication:
    def test_content_hash_generation(self):
        """Test content hash is consistent."""
        hash1 = generate_content_hash("Paper Title", "Author Name")
        hash2 = generate_content_hash("Paper Title", "Author Name")
        
        assert hash1 == hash2
    
    def test_content_hash_case_insensitive(self):
        """Test content hash is case-insensitive."""
        hash1 = generate_content_hash("Paper Title", "Author Name")
        hash2 = generate_content_hash("PAPER TITLE", "AUTHOR NAME")
        
        assert hash1 == hash2
    
    def test_different_content_different_hash(self):
        """Test different content produces different hash."""
        hash1 = generate_content_hash("Paper 1", "Author 1")
        hash2 = generate_content_hash("Paper 2", "Author 2")
        
        assert hash1 != hash2
```

### Step 5: Integration Tests

**`tests/integration/test_pipeline.py`:**
```python
"""Integration tests for PDF processing pipeline."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.integration
class TestPipeline:
    @patch('utils.google_drive.download_pdf_from_drive')
    @patch('utils.llama_parser.parse_pdf_with_llamaparse')
    @patch('utils.pinecone_uploader.upload_to_pinecone')
    def test_full_pipeline(
        self,
        mock_upload,
        mock_parse,
        mock_download,
        sample_config
    ):
        """Test complete pipeline with mocked external services."""
        from utils.multi_source_pipeline import process_multi_source_pipeline
        
        # Setup mocks
        mock_download.return_value = b'fake pdf content'
        mock_parse.return_value = "Parsed text from PDF"
        mock_upload.return_value = {'upserted_count': 5}
        
        # Run pipeline
        result = process_multi_source_pipeline(
            source_configs=[...],
            config=sample_config,
            preview_mode=False
        )
        
        # Verify
        assert result['status'] == 'completed'
        assert result['vectors_stored'] > 0
```

**`tests/integration/test_database.py`:**
```python
"""Integration tests for database operations."""

import pytest
import os


@pytest.mark.integration
class TestDatabaseOperations:
    def test_create_and_get_product(self):
        """Test product CRUD operations."""
        from utils.db.products import create_product, get_product, delete_product
        
        # Create
        product_id = create_product({
            'name': f'Test Product {os.urandom(4).hex()}',
            'pinecone_index': 'test-index'
        })
        
        assert product_id is not None
        
        # Get
        product = get_product(product_id)
        assert product['name'].startswith('Test Product')
        
        # Cleanup
        delete_product(product_id)
```

### Step 6: Run Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=utils --cov=config --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration
```

### Step 7: CI Integration (Future)

Create `.github/workflows/tests.yml` for automated testing on push.

## Benefits

- ✅ Prevents regressions
- ✅ Enables confident refactoring
- ✅ Documents expected behavior
- ✅ Catches edge cases early

---

# PHASE 5: Complete UI (Lower Priority)

**Duration:** 10-12 hours  
**Impact:** ⭐⭐⭐ Medium  
**Dependencies:** None

## Overview

Implement the 4 stub page modules if needed for complete feature set.

## Current State

**Stub pages (12 lines each):**
- `page_modules/select_files.py`
- `page_modules/preview.py`
- `page_modules/process.py`
- `page_modules/job_queue.py`

**Fully implemented pages:**
- `page_modules/products.py` (381 lines)
- `page_modules/data_sources.py` (132 lines)
- `page_modules/home.py` (86 lines)
- `page_modules/search.py` (118 lines)
- `page_modules/history.py` (67 lines)
- `page_modules/status.py` (40 lines)

## Implementation (Only if Needed)

### Task 5.1: `select_files.py`

**Purpose:** File selection UI for batch processing

**Features:**
- Connect to Google Sheets
- Display available files
- Multi-select files for processing
- Preview metadata
- Submit for processing

**Estimated:** 3 hours

### Task 5.2: `preview.py`

**Purpose:** Preview chunks before uploading

**Features:**
- Show parsed text
- Display chunk boundaries
- Preview embeddings
- Metadata inspection
- Confirm/cancel upload

**Estimated:** 3 hours

### Task 5.3: `process.py`

**Purpose:** Processing UI with real-time progress

**Features:**
- Progress bars for each file
- Live status updates
- Error display
- Pause/resume controls
- Success/failure summary

**Estimated:** 3-4 hours

### Task 5.4: `job_queue.py`

**Purpose:** Celery task monitoring

**Features:**
- Active tasks list
- Queue depth
- Task status (pending/running/failed/success)
- Retry controls
- Task details view

**Estimated:** 2-3 hours

## Decision Point

**Before implementing, ask:**
1. Are these features actually needed?
2. Does current workflow work without them?
3. Is there user demand for these UIs?

If no, keep as stubs and skip this phase.

---

# 📊 IMPLEMENTATION ROADMAP

## Week-by-Week Plan

### Week 1: Foundation & Type Safety
**Goal:** Eliminate quick wins, add config models

**Monday-Tuesday (Phase 1.1):**
- Remove print statements (30 min)
- Fix LSP errors (1 hour)
- Complete docstrings (30 min)

**Wednesday-Friday (Phase 1.2):**
- Create config/models.py (3 hours)
- Write config model tests (2 hours)
- Document usage patterns (1 hour)

**Deliverables:**
- ✅ Zero print statements
- ✅ Zero LSP errors
- ✅ Complete docstrings
- ✅ Type-safe config models
- ✅ Config model unit tests

**Expected Quality:** 8.5/10 (+1.0)

---

### Week 2: Structure & DRY

**Monday-Wednesday (Phase 3):**
- Create utils/config_builder.py (2 hours)
- Update tasks.py (1 hour)
- Update scheduler.py (30 min)
- Test config builder (30 min)

**Thursday-Friday (Phase 2):**
- Create utils/db/ modules (4 hours)
- Create __init__.py exports (1 hour)
- Verify imports & tests (1 hour)

**Deliverables:**
- ✅ Centralized config builder
- ✅ Modular database structure
- ✅ Backward compatibility maintained
- ✅ All tests passing

**Expected Quality:** 9.0/10 (+0.5)

---

### Week 3+: Testing & Polish (Optional)

**Phase 4: Testing Infrastructure**
- Setup pytest (1 hour)
- Create fixtures (2 hours)
- Write unit tests (4 hours)
- Write integration tests (3 hours)

**Deliverables:**
- ✅ 70%+ code coverage
- ✅ Comprehensive test suite

**Expected Quality:** 9.3/10 (+0.3)

---

## Success Metrics

### Code Quality Improvements

| Metric | Before | After Phase 1 | After Phase 2 | After Phase 3 | Final |
|--------|--------|---------------|---------------|---------------|-------|
| **Overall Rating** | 7.5/10 | 8.5/10 | 8.8/10 | 9.0/10 | 9.3/10 |
| **Print Statements** | 2 | 0 | 0 | 0 | 0 |
| **LSP Errors** | 2 | 0 | 0 | 0 | 0 |
| **Largest File** | 1,212 lines | 1,212 lines | 423 lines | 423 lines | 423 lines |
| **Config Type Safety** | 0% | 100% | 100% | 100% | 100% |
| **Code Duplication** | High | High | High | Low | Low |
| **Test Coverage** | 5% | 10% | 10% | 10% | 70%+ |
| **Docstring Coverage** | 70% | 95% | 95% | 95% | 95% |

### Time Investment vs. Value

| Phase | Hours | Quality Gain | ROI |
|-------|-------|--------------|-----|
| Phase 1.1 | 2 | +0.3 | ⭐⭐⭐⭐⭐ Excellent |
| Phase 1.2 | 6 | +0.7 | ⭐⭐⭐⭐⭐ Excellent |
| Phase 3 | 4 | +0.2 | ⭐⭐⭐⭐ High |
| Phase 2 | 6 | +0.3 | ⭐⭐⭐⭐ High |
| Phase 4 | 10 | +0.3 | ⭐⭐⭐ Medium (defensive) |
| Phase 5 | 12 | +0.0 | ⭐ Low (only if needed) |

---

## Risk Mitigation

### Phase 2 Risk: Breaking Error Handling

**Risk:** Database split might break recent error handling work

**Mitigation:**
1. Copy functions exactly as-is with decorators
2. Test after each module created
3. Keep old file until 100% verified
4. Re-run integration tests frequently

### Backward Compatibility Risk

**Risk:** Imports might break existing code

**Mitigation:**
1. Re-export all functions in __init__.py
2. Create compatibility shims
3. Test both old and new import paths
4. Gradual migration, not big-bang

### Config Model Adoption Risk

**Risk:** Team might not adopt new config models

**Mitigation:**
1. Provide `from_dict()` / `to_dict()` for compatibility
2. Document benefits clearly
3. Use in new code only (optional for old code)
4. Show examples of validation catching bugs

---

## Verification Checklist

### After Each Phase

- [ ] All existing tests pass
- [ ] No new LSP errors introduced
- [ ] Workflows (Server, Worker) still running
- [ ] No print statements added
- [ ] Documentation updated
- [ ] Git commit with clear message

### Final Verification

- [ ] 3/3 integration tests passing
- [ ] Zero LSP errors
- [ ] Zero print statements
- [ ] All imports work (old and new)
- [ ] Workflows running without errors
- [ ] replit.md updated with changes

---

## Maintenance Plan

### Post-Implementation

**Monthly:**
- Review test coverage
- Update config models as features added
- Refactor newly identified duplications

**Quarterly:**
- Review database module organization
- Consider migrating read-only functions to new pattern
- Evaluate config model adoption

**Yearly:**
- Full code quality audit
- Consider Phase 5 (UI completion) if needed
- Plan next enhancement cycle

---

## Conclusion

This enhancement plan provides a systematic approach to elevating code quality from 7.5/10 to 9.0-9.5/10 through:

1. **Type Safety** - Config models prevent bugs before runtime
2. **Modularization** - Smaller, focused modules easier to maintain
3. **DRY Principle** - Eliminate duplication for consistency
4. **Testing** - Prevent regressions and enable refactoring
5. **Documentation** - Clear, comprehensive docs

**Total Investment:** 12-38 hours depending on phases chosen  
**Expected Return:** +1.5-2.0 quality points, fewer bugs, easier maintenance

**Recommended Start:** Phase 1 (Quick Wins + Config Models) for immediate impact with manageable effort.

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
            raise ValueError(f"strategy must be one of {valid_strategies}, got '{self.strategy}'")
        
        if self.chunk_size < 100:
            raise ValueError(f"chunk_size must be >= 100, got {self.chunk_size}")
        
        if self.chunk_size > 8192:
            raise ValueError(f"chunk_size must be <= 8192, got {self.chunk_size}")
        
        if self.chunk_overlap < 0:
            raise ValueError(f"chunk_overlap must be >= 0, got {self.chunk_overlap}")
        
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(f"chunk_overlap ({self.chunk_overlap}) must be < chunk_size ({self.chunk_size})")
        
        if self.semantic_buffer_size < 1:
            raise ValueError(f"semantic_buffer_size must be >= 1, got {self.semantic_buffer_size}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ChunkingConfig':
        """Create from dictionary."""
        # Handle legacy keys
        if 'chunking_strategy' in data and 'strategy' not in data:
            data['strategy'] = data['chunking_strategy']
        if 'default_chunking_strategy' in data and 'strategy' not in data:
            data['strategy'] = data['default_chunking_strategy']
        if 'default_chunk_size' in data and 'chunk_size' not in data:
            data['chunk_size'] = data['default_chunk_size']
        
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with legacy keys."""
        d = asdict(self)
        # Add legacy keys for backward compatibility
        d['chunking_strategy'] = d['strategy']
        d['default_chunking_strategy'] = d['strategy']
        d['default_chunk_size'] = d['chunk_size']
        return d


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
            raise ValueError(f"model must contain one of {valid_models}, got '{self.model}'")
        
        if self.dimension is not None:
            if self.dimension < 1:
                raise ValueError(f"dimension must be > 0, got {self.dimension}")
            if self.dimension > 3072:
                raise ValueError(f"dimension must be <= 3072, got {self.dimension}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmbeddingConfig':
        """Create from dictionary."""
        # Handle legacy 'embedding_model' key
        if 'embedding_model' in data and 'model' not in data:
            data['model'] = data['embedding_model']
        if 'default_embedding_model' in data and 'model' not in data:
            data['model'] = data['default_embedding_model']
        
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
        d['default_embedding_model'] = d['model']
        d['openai_api_key'] = d['api_key']
        if d['dimension'] is not None:
            d['embedding_dimension'] = d['dimension']
        return d


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
                raise ValueError(f"model must be one of {valid_models}, got '{self.model}'")
            
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
        if self.dimension < 1:
            raise ValueError(f"dimension must be > 0, got {self.dimension}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PineconeConfig':
        """Create from dictionary."""
        # Handle legacy keys
        if 'pinecone_api_key' in data and 'api_key' not in data:
            data['api_key'] = data['pinecone_api_key']
        if 'pinecone_index' in data and 'index_name' not in data:
            data['index_name'] = data['pinecone_index']
        if 'index_name' not in data and 'pinecone_index' not in data:
            data['index_name'] = data.get('index_name', '')
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
        d['pinecone_index'] = d['index_name']
        d['pinecone_environment'] = d['environment']
        d['default_namespace'] = d['namespace']
        return d


@dataclass
class GoogleConfig:
    """
    Google Cloud Platform configuration.
    
    Attributes:
        credentials: Service account JSON as string or dict
        project_id: Optional GCP project ID
    """
    credentials: Any = ''
    project_id: Optional[str] = None
    
    def __post_init__(self):
        """Validate configuration."""
        if not self.credentials:
            # Allow empty credentials for default construction
            return
        
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
        # Handle legacy keys
        if 'dedup_layer1' in data and 'check_layer1' not in data:
            data['check_layer1'] = data['dedup_layer1']
        if 'dedup_layer2' in data and 'check_layer2' not in data:
            data['check_layer2'] = data['dedup_layer2']
        if 'dedup_layer3' in data and 'check_layer3' not in data:
            data['check_layer3'] = data['dedup_layer3']
        
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary with legacy keys."""
        d = asdict(self)
        d['dedup_layer1'] = d['check_layer1']
        d['dedup_layer2'] = d['check_layer2']
        d['dedup_layer3'] = d['check_layer3']
        return d


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
            raise ValueError(f"frequency must be one of {valid_frequencies}, got '{self.frequency}'")
        
        if self.max_papers_per_run < 1:
            raise ValueError(f"max_papers_per_run must be >= 1, got {self.max_papers_per_run}")
        
        if self.max_papers_per_run > 1000:
            raise ValueError(f"max_papers_per_run must be <= 1000, got {self.max_papers_per_run}")
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ScheduleConfig':
        """Create from dictionary."""
        valid_keys = cls.__annotations__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


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

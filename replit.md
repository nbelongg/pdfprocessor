# PDF Chunking & Embedding Pipeline

## Overview

This is a Streamlit-based web application that processes PDF documents from Google Drive through a complete data pipeline: parsing PDFs using LlamaParse, chunking the extracted text using various strategies, generating embeddings with multiple model options, and storing the resulting vectors in Pinecone for semantic search and retrieval. The system is designed for batch processing of research papers, documents, or any PDF collection, with metadata enrichment from Google Sheets.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
- **Frontend**: Streamlit-based web interface for user interaction and configuration
- **Authentication**: Password-based access control using environment variables
- **State Management**: Streamlit session state for maintaining processing state and user configuration

### PDF Processing Pipeline
The application follows a multi-stage pipeline architecture:

1. **Input Layer**: Google Sheets integration for batch configuration
   - Reads PDF links and metadata from Google Sheets
   - Supports flexible metadata mapping from arbitrary sheet columns
   - Allows namespace specification per document for organized storage

2. **PDF Acquisition**: Google Drive integration
   - Downloads PDFs using Google Drive API with service account credentials
   - Extracts file IDs from various Google Drive URL formats
   - Retrieves file metadata for enrichment

3. **Parsing Layer**: LlamaParse integration
   - Converts PDFs to structured text (markdown or text format)
   - Configurable parsing modes (fast, premium, auto)
   - Support for multimodal parsing with vendor models (Anthropic Sonnet)
   - Custom parsing instructions and language specification

4. **Chunking Layer**: Multiple text splitting strategies
   - **Token-based**: Fixed-size chunks with configurable overlap using TokenTextSplitter
   - **Sentence-based**: Semantic sentence boundaries with SentenceSplitter
   - **Semantic**: Context-aware splitting using embeddings with SemanticSplitterNodeParser
   - Returns LlamaIndex BaseNode objects with attached metadata

5. **Embedding Layer**: Dual model support
   - **OpenAI**: text-embedding-3-small (1536d), text-embedding-3-large (3072d)
   - **HuggingFace**: Custom model specification support
   - Generates vector representations for each text chunk

6. **Storage Layer**: Pinecone vector database
   - Serverless deployment on AWS (us-east-1)
   - Cosine similarity metric for semantic search
   - Automatic index creation with configurable dimensions
   - Namespace support for logical data organization
   - Batch upsert operations with metadata preservation

### Configuration Management
- Environment-based secrets for API keys (LlamaParse, Pinecone, OpenAI)
- Service account JSON for Google Cloud authentication
- Session-based configuration during runtime
- Default values with user override capability

### Data Flow
```
Google Sheets → Drive Links → PDF Download → LlamaParse → Text → Chunking → Nodes → Embeddings → Pinecone
     ↓                                                                                           ↑
  Metadata ----------------------------------------------------------------→ Attached to vectors
```

## External Dependencies

### Third-Party APIs & Services

1. **LlamaParse** (cloud.llamaindex.ai)
   - Purpose: High-quality PDF parsing with multimodal support
   - Authentication: API key via LLAMA_CLOUD_API_KEY
   - Features: Markdown/text output, custom instructions, vendor model integration

2. **Pinecone** (app.pinecone.io)
   - Purpose: Vector database for embedding storage and similarity search
   - Authentication: API key via PINECONE_API_KEY
   - Configuration: Serverless deployment, AWS us-east-1, cosine metric
   - Features: Namespaces for organization, automatic index management

3. **OpenAI** (platform.openai.com) - Optional
   - Purpose: Embedding generation when using OpenAI models
   - Authentication: API key via OPENAI_API_KEY
   - Models: text-embedding-3-small, text-embedding-3-large

4. **Google Cloud Platform**
   - **Google Drive API**: PDF file access and download
   - **Google Sheets API**: Metadata and configuration retrieval
   - Authentication: Service account JSON credentials
   - Required Scopes:
     - `https://www.googleapis.com/auth/drive.readonly`
     - `https://spreadsheets.google.com/feeds`
     - `https://www.googleapis.com/auth/drive`

### Core Libraries

1. **LlamaIndex**: Document processing, node parsing, embedding generation
   - Components: SentenceSplitter, SemanticSplitterNodeParser, TokenTextSplitter
   - Embedding integrations: OpenAIEmbedding, HuggingFaceEmbedding

2. **Streamlit**: Web application framework and UI components

3. **Google API Clients**:
   - `google-api-python-client`: Drive and Sheets access
   - `oauth2client`: Service account authentication
   - `gspread`: Simplified Sheets operations

4. **HuggingFace**: Alternative embedding model provider (transformers, sentence-transformers)

### Data Storage
- **Pinecone**: Primary vector storage (cloud-hosted, serverless)
- **PostgreSQL**: Processing history, job tracking, and chunk storage (local development database)
- **Session State**: Temporary configuration and processing state (in-memory)

### Database Schema
1. **data_sources**: Stores Google Sheet data source configurations
   - Source ID, name, description, sheet URL, tab name
   - Sheet type (single or multi-tab), status (active/inactive)
   - Last processed timestamp, total rows, processing statistics
   - Created and updated timestamps

2. **column_mappings**: Maps source columns to metadata roles
   - Links to data source via source_id
   - Column name and role (drive_link, paper_title, authors, tags, namespace, etc.)
   - Custom mappings for flexible metadata extraction

3. **processing_jobs**: Tracks all processing jobs
   - job_id, status, configuration, metrics (PDFs, chunks, embeddings)
   - Timestamps for created, updated, and completed
   
4. **processing_chunks**: Stores individual chunks for preview and validation
   - Links to job via job_id
   - Contains chunk text, metadata, namespace
   - Tracks whether embedding has been uploaded to Pinecone

5. **metadata_transformations**: Stores custom metadata transformation rules
   - Reusable transformations for metadata processing

### Authentication Flow
- Application: Password-based entry (APP_PASSWORD environment variable)
- Google Services: Service account credentials (JSON file upload - required)
- External APIs: API key-based authentication (environment variables or user input)

## Recent Changes

### Phase 1: Multi-Source Data Management (COMPLETED - Oct 2025)

**Goal**: Enable management and processing of papers from multiple Google Sheet sources, each with unique column mappings and metadata configurations.

**Implementation**:
1. **Database Layer**:
   - Created `data_sources` table to store Google Sheet configurations
   - Created `column_mappings` table for flexible metadata extraction per source
   - Support for single-tab and multi-tab sheets
   - Tracking of processing statistics per source

2. **Data Sources UI** (Tab 1):
   - Add/edit/delete data sources with descriptive names
   - Automatic sheet column detection when adding sources
   - Role-based column mapping interface (Drive Link, Paper Title, Authors, Tags, Namespace, etc.)
   - Support for custom metadata columns beyond predefined roles
   - Active/inactive status toggle for each source

3. **Multi-Source Pipeline** (`utils/multi_source_pipeline.py`):
   - Processes papers from multiple sources simultaneously
   - Applies per-source column mappings and metadata
   - Merges results while preserving source identity
   - Supports both preview and full processing modes

4. **Updated Tabs**:
   - **Select Files** (Tab 4): Multi-select data sources, view papers from each source, select individual papers
   - **Preview Chunks** (Tab 5): Preview papers from multiple sources before uploading
   - **Process & Upload** (Tab 6): Batch process all selected papers from all sources

**Benefits**:
- Organize papers by topic/category using different sheets
- Each source can have unique metadata structure
- Process thousands of papers across multiple sources in one batch
- Maintain clear source tracking for all processed papers

### Phase 2: Deduplication System (COMPLETED - Oct 2025)

**Goal**: Prevent duplicate papers from being processed and uploaded to Pinecone using a 3-layer deduplication approach.

**Implementation**:
1. **Database Layer**:
   - Created `processed_papers` table to track all processed papers
   - Created `source_paper_mapping` table to link papers to their source(s)
   - Stores Drive file ID, content hash (SHA-256 of title + authors), metadata
   - Tracks processing count and timestamps for each paper

2. **Deduplication Module** (`utils/deduplication.py`):
   - **Layer 1**: Drive file ID check (exact match on Google Drive file ID)
   - **Layer 2**: Content hash check (SHA-256 hash of normalized title + authors)
   - **Layer 3**: Embedding similarity check (cosine similarity threshold, optional)
   - Configurable layers - can enable/disable each independently
   - Returns duplicate status, which layer detected it, and existing paper data

3. **Pipeline Integration** (`utils/multi_source_pipeline.py`):
   - Checks deduplication before downloading PDF (saves time and API calls)
   - Records/updates paper in database after successful processing
   - Tracks which sources have seen each paper
   - Skips duplicate papers and logs them in processing report

4. **Tracking & Statistics**:
   - Get deduplication stats: unique papers, duplicate attempts, papers seen multiple times
   - Source-paper mapping enables cross-source duplicate detection
   - Processing history shows which papers were skipped as duplicates

**Benefits**:
- Saves time and API costs by not re-processing duplicates
- Prevents duplicate vectors in Pinecone
- Handles papers that appear in multiple Google Sheets
- Flexible 3-layer approach catches duplicates at different levels
- Tracks duplicate attempts for analytics

### Phase 2 (Previous): Processing History & Tracking
- All processing jobs are now persisted in PostgreSQL database
- Unique job IDs generated for each processing run
- Job status tracking: pending, running, completed, preview, error
- Detailed metrics: PDFs processed, chunks created, embeddings generated, vectors stored

### Preview Mode
- **Preview Chunks Tab**: Generate previews without uploading to Pinecone
- Parse and chunk PDFs to inspect results before final processing
- View individual chunks with text content and metadata
- Validate chunking strategy effectiveness before committing

### Processing History Viewer
- **History Tab**: Browse all past processing jobs
- View job details, status, and metrics
- Inspect chunks generated for each job
- Track which chunks have been uploaded to Pinecone

### Vector Search Testing
- **Search Test Tab**: Query Pinecone index directly from the app
- Test semantic search with custom queries
- View search results with relevance scores
- Inspect returned chunks and metadata
- Validate that embeddings are working correctly

### Metadata Transformation Rules (app_transformations.py)
- Separate interface for creating reusable metadata transformation rules
- Transformation types:
  - Map Values: Transform specific values to new values
  - Combine Columns: Merge multiple columns into one
  - Extract Pattern: Use regex to extract data
  - Conditional Transform: Apply transformations based on conditions
- Save, manage, and export transformation rules as JSON

## Application Pages
1. **app.py**: Main PDF processing pipeline with 8 tabs
2. **app_transformations.py**: Metadata transformation rule manager
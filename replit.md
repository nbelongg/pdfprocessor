# PDF Chunking & Embedding Pipeline

## Overview
This project is a Streamlit-based web application for processing PDF documents from Google Drive. It provides a data pipeline for parsing PDFs using LlamaParse, chunking extracted text, generating embeddings with OpenAI models, and storing vectors in Pinecone for semantic search. The system supports batch processing, metadata enrichment from Google Sheets, deduplication, scheduled processing, and multi-product/multi-startup support, aiming to efficiently manage and make searchable document collections.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
- **Frontend**: Streamlit for the user interface.
- **Authentication**: Password-based via environment variables.
- **State Management**: Streamlit session state.
- **Background Processing**: Celery with Redis as the message broker for scalable job queuing.

### Code Architecture
The application features a modular architecture:
- **`app.py`**: Main router for authentication, navigation, and page routing.
- **`config/constants.py`**: Centralized configuration, UI messages, and help text.
- **`config/models.py`**: Type-safe configuration dataclasses with validation (Phase 1).
- **`components/common.py`**: Reusable UI components.
- **`page_modules/`**: Modular page implementations for configuration, product management, data sources, PDF processing workflow, job monitoring, status display, history, and search.
- **`utils/`**: Backend utilities for database, embeddings, parsing, etc.
  - **`utils/db/`**: Modular database operations organized by domain (Phase 2).
  - **`utils/config_builder.py`**: Centralized product configuration builder (Phase 3).

### PDF Processing Pipeline
1.  **Input Layer**: Google Sheets for batch configuration and metadata.
2.  **PDF Acquisition**: Google Drive API for downloading PDFs.
3.  **Parsing Layer**: LlamaParse for structured text extraction with advanced features:
    - **Parsing Modes**: 6 modes (auto, fast, premium, balanced, llm, lvm) for quality/cost tradeoffs
    - **Result Types**: 4 formats (markdown, text, json, structured) for different use cases
    - **Parallel Processing**: 1-9 workers for batch speed optimization (default: 4)
    - **Error Tolerance**: Configurable page error tolerance (default: 5% failure allowed)
    - Raw output stored as JSON in PostgreSQL for re-processing without re-parsing
4.  **AI Tagging Layer** (Optional): OpenAI-powered automatic tag generation with product-specific models and customizable prompts. Tags stored in the database and propagated to chunks.
5.  **Chunking Layer**: Multiple strategies (token-based, sentence-based, semantic) with tag inclusion in metadata.
6.  **Embedding Layer**: OpenAI embeddings (text-embedding-3-small, text-embedding-3-large).
7.  **Storage Layer**: Pinecone vector database (serverless) for vector storage, supporting namespaces and batch upsert, with tags included in vector metadata.

### Background Job Queue System (Celery)
-   **Message Broker**: Redis (Upstash) for task queue and result backend.
-   **Workers**: Concurrent Celery workers with exponential backoff retry logic.
-   **Job Tracking**: PostgreSQL tables (`celery_jobs`) for status, progress, and results.
-   **Monitoring**: Real-time job queue UI.

### Configuration & Data Flow
-   Environment variables for API keys and Google Cloud service account JSON.
-   Data flow: `Google Sheets → Drive Links → PDF Download → LlamaParse → Parsed JSON (stored) → AI Tagging (optional) → Chunking (with tags) → Nodes → Embeddings → Pinecone (with tags in metadata)`

### Key Features
-   **Multi-Source Data Management**: Process PDFs from various Google Sheet sources with unique configurations.
-   **Deduplication System**: Three-layer deduplication (Drive file ID, content hash, optional embedding similarity).
-   **Scheduled/Periodic Processing**: Automatic processing of new documents via configurable scheduled jobs.
-   **Processing History & Tracking**: Persistence of job details in PostgreSQL.
-   **Preview Mode**: Preview parsed and chunked PDFs before Pinecone upload.
-   **Vector Search Testing**: In-app tool for querying the Pinecone index.
-   **Metadata Transformation Rules**: Reusable rules for metadata manipulation.
-   **Multi-Product/Multi-Startup Support**: Management of multiple products with isolated Pinecone indexes, API keys, and processing settings.
-   **Parsed Content Persistence**: Raw LlamaParse output stored in PostgreSQL as JSON for re-chunking/re-embedding without re-parsing.
-   **Job Management & Monitoring**: Real-time Celery job monitoring, on-demand processing triggers, job history with filtering, manual retry/cancel controls.

### UI/UX Decisions
-   **Navigation**: Left sidebar with radio buttons for page selection.
-   **Processing Settings**: Moved to product-specific configuration.
-   **Products Tab**: Collapsible sections for organized product creation/editing.
-   **Job Management Page**: Comprehensive job control with 3 tabs:
    - **Monitor Jobs**: Real-time Celery task status, progress bars, error details, cancel controls
    - **Trigger Processing**: On-demand processing from data sources (bypasses scheduler)
    - **Job History**: Filtering by status, detailed job information and results

### Database Write Operations Pattern
-   All database write operations utilize a standardized pattern with `get_db_transaction` and `with_db_error_handling` for automatic transaction management and consistent error handling (permanent `DatabaseError` or transient `DatabaseTransientError`).
-   **Database Modularization (Phase 2)**: Database operations are organized into domain-specific modules in `utils/db/`:
  - `products.py`: Product CRUD & API key management (7 functions)
  - `jobs.py`: Processing jobs, chunks, Celery tracking (16 functions)
  - `documents.py`: Parsed docs, AI tagging, deduplication (12 functions)
  - `sources.py`: Data sources & column mappings (10 functions)
  - `scheduling.py`: Scheduled jobs & job runs (9 functions)
  - `connection.py`: Core database connection utilities
  - All 30 functions with `@with_db_error_handling` decorator preserved exactly.

### Product Management & Multi-Tenant Support
-   **Isolation**: Complete isolation for multiple products/startups via separate Pinecone indexes, API keys, and Google service account credentials.
-   **Configuration**: Each product stores its name, description, Pinecone configuration, API key secret names (referencing Replit secrets), and complete processing settings (parsing, tagging, chunking, embedding).
-   **Advanced Parsing Configuration** (per product):
    - Parsing mode selection (auto/fast/premium/balanced/llm/lvm) for quality vs cost optimization
    - Result type (markdown/text/json/structured) for different downstream needs
    - Parallel workers (1-9) for batch processing speed control
    - Page error tolerance (0-1) for handling partially corrupted documents
-   **Secret Management**: Uses a secret reference system where products store secret names (e.g., `llamaparse_api_key_secret = "STARTUP_A_LLAMAPARSE_KEY"`) instead of actual credentials, which are retrieved from Replit secrets.
-   **Centralized Config Builder (Phase 3)**: `utils/config_builder.py` provides single source of truth for product configuration building:
  - `build_product_config()`: Builds complete product config from database with API key retrieval and validation
  - `PRODUCT_CONFIG_MAPPING` and `PRODUCT_SETTINGS_MAPPING`: Centralized constant definitions
  - Used by `tasks.py`, `scheduler.py`, and `utils/multi_source_pipeline.py`
  - Eliminates ~100 lines of duplicate config building logic across modules.

## External Dependencies

### Third-Party APIs & Services
1.  **LlamaParse**: PDF parsing.
2.  **Pinecone**: Vector database.
3.  **OpenAI**: Embedding generation and AI Tagging.
4.  **Google Cloud Platform**:
    -   **Google Drive API**: PDF file access.
    -   **Google Sheets API**: Metadata and configuration.

### Core Libraries
1.  **LlamaIndex**: Document processing, node parsing, embedding generation.
2.  **Streamlit**: Web application framework.
3.  **Google API Clients** (`google-api-python-client`, `oauth2client`, `gspread`): Google Drive and Sheets access.
4.  **Celery**: Distributed task queue.
5.  **Redis**: Celery message broker.

### Data Storage
-   **Pinecone**: Primary vector storage.
-   **PostgreSQL**: Processing history, job tracking, chunk storage, raw parsed text, configuration for data sources, column mappings, jobs, chunks, metadata transformations, processed papers, scheduled jobs, and products. The `parsed_documents` table stores raw parsed content, AI-generated tags, and tagging metadata.
-   **Session State**: Temporary configuration and processing state.
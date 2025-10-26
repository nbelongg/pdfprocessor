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
- **`components/common.py`**: Reusable UI components.
- **`page_modules/`**: Modular page implementations for configuration, product management, data sources, PDF processing workflow, job monitoring, status display, history, and search.
- **`utils/`**: Backend utilities for database, embeddings, parsing, etc.

### PDF Processing Pipeline
1.  **Input Layer**: Google Sheets for batch configuration and metadata.
2.  **PDF Acquisition**: Google Drive API for downloading PDFs.
3.  **Parsing Layer**: LlamaParse for structured text extraction (markdown/text), with raw output stored as JSON in PostgreSQL.
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

### UI/UX Decisions
-   **Navigation**: Left sidebar with radio buttons for page selection.
-   **Processing Settings**: Moved to product-specific configuration.
-   **Products Tab**: Collapsible sections for organized product creation/editing.

### Database Write Operations Pattern
-   All database write operations utilize a standardized pattern with `get_db_transaction` and `with_db_error_handling` for automatic transaction management and consistent error handling (permanent `DatabaseError` or transient `DatabaseTransientError`).

### Product Management & Multi-Tenant Support
-   **Isolation**: Complete isolation for multiple products/startups via separate Pinecone indexes, API keys, and Google service account credentials.
-   **Configuration**: Each product stores its name, description, Pinecone configuration, API key secret names (referencing Replit secrets), and complete processing settings (parsing, tagging, chunking, embedding).
-   **Secret Management**: Uses a secret reference system where products store secret names (e.g., `llamaparse_api_key_secret = "STARTUP_A_LLAMAPARSE_KEY"`) instead of actual credentials, which are retrieved from Replit secrets.
-   **Integration**: When processing, the pipeline loads complete product-specific configurations including API keys, Google Drive credentials, Pinecone settings, and all processing parameters.

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
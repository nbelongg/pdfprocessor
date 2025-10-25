# PDF Chunking & Embedding Pipeline

## Overview
This project is a Streamlit-based web application designed to process PDF documents from Google Drive. It provides a comprehensive data pipeline for parsing PDFs using LlamaParse, chunking the extracted text with various strategies, generating embeddings using multiple model options (OpenAI, HuggingFace), and storing these vectors in Pinecone for semantic search and retrieval. The system supports batch processing, metadata enrichment from Google Sheets, and includes features for deduplication, scheduled processing, and multi-product/multi-startup support. Its purpose is to efficiently manage and make searchable collections of documents like research papers or business reports.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
- **Frontend**: Streamlit for interactive user interface.
- **Authentication**: Password-based via environment variables.
- **State Management**: Streamlit session state.

### PDF Processing Pipeline
1.  **Input Layer**: Google Sheets integration for batch configuration and metadata.
2.  **PDF Acquisition**: Google Drive API for downloading PDFs.
3.  **Parsing Layer**: LlamaParse for converting PDFs to structured text (markdown/text), with configurable modes and custom instructions.
4.  **Chunking Layer**: Multiple strategies including token-based (`TokenTextSplitter`), sentence-based (`SentenceSplitter`), and semantic (`SemanticSplitterNodeParser`).
5.  **Embedding Layer**: Supports OpenAI (text-embedding-3-small, text-embedding-3-large) and HuggingFace models.
6.  **Storage Layer**: Pinecone vector database (serverless, AWS us-east-1, cosine similarity) for vector storage, with namespace support and batch upsert.

### Configuration & Data Flow
-   Environment variables for API keys and service account JSON for Google Cloud.
-   Data flow: `Google Sheets → Drive Links → PDF Download → LlamaParse → Text → Chunking → Nodes → Embeddings → Pinecone` with metadata attached to vectors.

### Key Features
-   **Multi-Source Data Management**: Process PDFs from multiple Google Sheet sources, each with unique column mappings and metadata configurations.
-   **Deduplication System**: Three-layer deduplication (Drive file ID, content hash, optional embedding similarity) to prevent reprocessing and duplicate vectors.
-   **Scheduled/Periodic Processing**: Automatic processing of new papers from data sources via scheduled jobs (cron-based, configurable per source).
-   **Processing History & Tracking**: Persistence of all processing jobs, statuses, and metrics in a PostgreSQL database.
-   **Preview Mode**: Allows users to preview parsed and chunked PDFs before uploading to Pinecone.
-   **Vector Search Testing**: In-app tool to query the Pinecone index and test semantic search.
-   **Metadata Transformation Rules**: Reusable rules for transforming metadata (map values, combine columns, extract patterns, conditional transforms).
-   **Multi-Product/Multi-Startup Support**: Management of multiple products/startups with separate Pinecone indexes, API keys (via Replit secrets), and processing settings.

### UI/UX Decisions
-   Application structured with multiple tabs (`app.py`, `app_transformations.py`) for different functionalities like data source management, processing, preview, and history.

## External Dependencies

### Third-Party APIs & Services
1.  **LlamaParse**: High-quality PDF parsing.
2.  **Pinecone**: Vector database for embedding storage and similarity search.
3.  **OpenAI**: Embedding generation (optional).
4.  **Google Cloud Platform**:
    -   **Google Drive API**: PDF file access.
    -   **Google Sheets API**: Metadata and configuration retrieval.

### Core Libraries
1.  **LlamaIndex**: Document processing, node parsing, embedding generation.
2.  **Streamlit**: Web application framework.
3.  **Google API Clients** (`google-api-python-client`, `oauth2client`, `gspread`): Google Drive and Sheets access.
4.  **HuggingFace**: Alternative embedding model provider.

### Data Storage
-   **Pinecone**: Primary vector storage.
-   **PostgreSQL**: Processing history, job tracking, chunk storage, and configuration for data sources, column mappings, processing jobs, chunks, metadata transformations, processed papers, scheduled jobs, and products.
-   **Session State**: Temporary configuration and processing state.
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
5.  **Embedding Layer**: OpenAI embeddings only (text-embedding-3-small, text-embedding-3-large). HuggingFace removed for deployment optimization.
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
-   **Navigation**: Left sidebar with radio buttons for page selection (Configuration, Products, Data Sources, Select Files, Preview Chunks, Process & Upload, Status, History, Search Test)
-   **Processing Settings**: All processing settings moved to product-specific configuration (no global Processing Settings page)
-   **Products Tab**: Organized into collapsible sections (Parsing, Chunking, Embedding, Pinecone Settings) for better UX when creating/editing products

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

### Data Storage
-   **Pinecone**: Primary vector storage.
-   **PostgreSQL**: Processing history, job tracking, chunk storage, and configuration for data sources, column mappings, processing jobs, chunks, metadata transformations, processed papers, scheduled jobs, and products.
-   **Session State**: Temporary configuration and processing state.

## Product Management & Multi-Tenant Support

### Overview
The application supports managing multiple products/startups with complete isolation through separate Pinecone indexes, API keys, and Google service account credentials. Each product can have its own default processing settings.

### Product Configuration
Each product in the database stores:
- **Name & Description**: Product identifier and description
- **Pinecone Configuration**: Dedicated index name, environment (serverless region), and default namespace
- **API Key Secret Names**: References to Replit secrets containing:
  - LlamaParse API key
  - OpenAI API key (if using OpenAI embeddings)
  - Pinecone API key
  - Google service account JSON credentials
- **Complete Processing Settings** (all settings are product-specific):
  - **Parsing Settings**: Mode (auto/fast/premium), result type (markdown/text), language, multimodal support, page separator
  - **Chunking Settings**: Strategy (token/sentence/semantic), chunk size, chunk overlap, semantic buffer size
  - **Embedding Settings**: Model (OpenAI text-embedding-3-small/large)
- **Status**: Active/inactive flag

### Secret Management
Products use a **secret reference system** for security:

**API Keys**: Product stores the secret name, not the actual key
- Example: Product "Startup A" has `llamaparse_api_key_secret = "STARTUP_A_LLAMAPARSE_KEY"`
- In Replit Secrets, you set: `STARTUP_A_LLAMAPARSE_KEY = "llx-actual-api-key-here"`
- App reads: `os.getenv("STARTUP_A_LLAMAPARSE_KEY")`

**Google Credentials**: Product stores secret name for JSON string
- Example: Product has `google_credentials_secret = "STARTUP_A_GOOGLE_CREDS"`
- In Replit Secrets, set the entire JSON as a string:
  ```
  STARTUP_A_GOOGLE_CREDS = '{"type": "service_account", "project_id": "...", ...}'
  ```
- App parses: `json.loads(os.getenv("STARTUP_A_GOOGLE_CREDS"))`

### Integration with Pipeline
When processing PDFs:
1. Data source specifies which product it belongs to
2. Pipeline loads complete product configuration including:
   - **All API keys** from product-specific Replit secrets
   - **Google Drive credentials** from product secret (enables per-product Drive access)
   - **Pinecone configuration**: Index name, environment, default namespace
   - **All parsing settings**: Mode, result type, language, multimodal, page separator
   - **All chunking settings**: Strategy, size, overlap, semantic buffer
   - **Embedding model**: OpenAI model selection
3. Product settings take precedence over any global/base configuration
4. Pipeline functions (PDF download, parsing, chunking, embedding) all use product-specific config
5. Vectors stored in product-specific Pinecone index with product settings

### Integration with Scheduler
Scheduled jobs automatically use product settings:
- Inherit product from data source
- Load product-specific API keys and credentials
- Route to correct Pinecone index
- Log which product settings are being used

### Benefits
- **Complete Isolation**: Each product has separate vector storage
- **Billing Separation**: Different API keys for different products
- **Flexible Settings**: Each product can use different processing strategies
- **Secure Credentials**: Each product can access different Google Drive accounts
- **Scalability**: Easy to add new products without changing code
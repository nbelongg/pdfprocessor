# PDF Chunking & Embedding Pipeline

## Overview
This project is a Streamlit-based web application designed to process PDF documents from Google Drive. It establishes a data pipeline for parsing PDFs, chunking extracted text, generating OpenAI embeddings, and storing vectors in Pinecone for semantic search. The system supports batch processing, metadata enrichment from Google Sheets, deduplication, scheduled processing, multi-product/multi-startup capabilities, and efficient metadata-only updates for existing documents. Its primary goal is to provide an efficient and searchable document management system.

## User Preferences
Preferred communication style: Simple, everyday language.

## System Architecture

### Application Framework
-   **Frontend**: Streamlit.
-   **Authentication**: Password-based.
-   **Background Processing**: Celery with Redis as the message broker.

### Code Architecture
-   **Modular Design**: `app.py` for routing, `config/` for constants and models, `components/` for UI, `page_modules/` for page implementations, and `utils/` for backend logic (database, embeddings, parsing, config building, row identification).

### PDF Processing Pipeline
1.  **Input**: Google Sheets for configuration and metadata.
2.  **PDF Acquisition**: Google Drive API.
3.  **Parsing**: LlamaParse for structured text extraction, supporting multiple modes, result types, parallel processing, and error tolerance. Raw output is stored in PostgreSQL.
4.  **AI Tagging (Optional)**: OpenAI-powered tag generation, stored in DB and propagated to chunks.
5.  **Chunking**: Multiple strategies with tag inclusion.
6.  **Embedding**: OpenAI embeddings (text-embedding-3-small, text-embedding-3-large).
7.  **Storage**: Pinecone vector database with namespaces and batch upsert.

### Background Job Queue System (Celery)
-   **Async Architecture**: Redis message broker, concurrent workers with retry logic, and PostgreSQL for unified job tracking (`celery_jobs` table).
-   **Automatic Status Tracking**: Celery signal handlers ensure robust status updates (pending, running, failed, success) even if tasks crash.
-   **Database Maintenance**: Utility script for cleaning up orphaned, stuck, or old job records.

### Configuration & Data Flow
-   Environment variables for API keys.
-   Data Flow: `Google Sheets → Drive Links → PDF Download → LlamaParse → Parsed JSON (stored) → AI Tagging (optional) → Chunking (with tags) → Nodes → Embeddings → Pinecone (with tags in metadata)`

### Key Features
-   **Multi-Source Data Management**: Process PDFs from various Google Sheet sources.
-   **Robust Deduplication System**: Two-layer system (Drive file ID, content hash) with 4-state self-healing logic and product isolation. Same paper can be processed into multiple products with different embedding dimensions while preventing duplicates within each product. System automatically recovers from timeouts and database-Pinecone inconsistencies.
-   **Admin Maintenance Tools**: Production-accessible pages for backfilling deduplication records and enriching metadata.
-   **Metadata-Only Updates**: Efficiently update metadata without re-parsing PDFs or regenerating embeddings, using metadata fingerprints for change detection.
-   **Hash-Based Paper Detection**: Position-independent detection of new papers in Google Sheets using Drive File ID or content hash.
-   **Scheduled Processing**: Automatic processing of new documents.
-   **Processing History & Tracking**: Persistent job details in PostgreSQL with deduplication metrics (new papers processed vs duplicates skipped).
-   **Preview Mode**: Visualize parsed and chunked PDFs.
-   **Vector Search Testing**: In-app tool for querying Pinecone.
-   **Multi-Product/Multi-Startup Support**: Isolated configurations, Pinecone indexes, and API keys.
-   **Parsed Content Persistence**: Raw LlamaParse output stored in PostgreSQL for reprocessing.
-   **Job Management & Monitoring**: Real-time Celery job monitoring with deduplication statistics, on-demand triggers, and detailed history.

### UI/UX Decisions
-   **Navigation**: Left sidebar.
-   **Product Configuration**: Collapsible sections for organized management.
-   **Job Management Page**: Comprehensive control with tabs for monitoring, triggering, and history.

### Database Write Operations Pattern
-   Standardized pattern with `get_db_transaction` and `with_db_error_handling` for transaction management and error handling.
-   **Modularization**: Database operations are organized into domain-specific modules (`products.py`, `jobs.py`, `documents.py`, etc.) within `utils/db/`.

### Product Management & Multi-Tenant Support
-   **Isolation**: Separate Pinecone indexes, namespaces, API keys, and credentials per product.
-   **Configuration**: Each product stores its specific processing settings (parsing modes, result types, parallel workers, error tolerance) and secret names (referencing Replit secrets).
-   **Centralized Config Builder**: `utils/config_builder.py` provides a single source of truth for building product configurations from the database.
-   **Product-Scoped Deduplication**: The `processed_papers` table uses dual partial unique indexes to allow the same paper (Drive File ID) to be processed into multiple products while preventing duplicates within each product:
    -   `processed_papers_drive_file_id_null_idx`: UNIQUE (drive_file_id) WHERE product_id IS NULL (legacy/global scope)
    -   `processed_papers_drive_file_id_product_id_idx`: UNIQUE (drive_file_id, product_id) WHERE product_id IS NOT NULL (product-scoped)
    -   Example: Paper XYZ can be processed into Product 1 (1536-dim embeddings, namespace: product-1) and Product 7 (384-dim embeddings, namespace: product-7) simultaneously, with deduplication enforced separately for each product.

### Robust Deduplication System (November 2025)
-   **Design Principle**: "Check First, Process Never" - Duplicates are detected BEFORE any expensive processing (parsing, chunking, embedding).
-   **Two-Layer Detection**:
    -   **Layer 1 (Primary)**: Drive File ID lookup in `processed_papers` table (fast, product-scoped)
    -   **Layer 2 (Fallback)**: Content hash comparison (title + authors) for same paper with different Drive links
    -   **Removed**: Layer 3 embedding similarity (too slow, complex, not needed)
-   **4-State Self-Healing Logic**:
    -   **State 1**: In `processed_papers` + has uploaded chunks → **SKIP** (already complete)
    -   **State 2**: In `processed_papers` but NO uploaded chunks → **REPROCESS** (previous upload failed, clean up first)
    -   **State 3**: NOT in `processed_papers` but HAS uploaded chunks → **SKIP + backfill** (timeout recovery)
    -   **State 4**: NOT in `processed_papers` and NO uploaded chunks → **PROCESS** (truly new)
-   **Atomic Pinecone Upload Tracking**: Papers are ONLY marked in `processed_papers` AFTER confirming successful Pinecone upload (vectors_uploaded > 0).
-   **Product Scoping**: Chunk existence checks filter by both `drive_file_id` AND `namespace` to prevent cross-product false positives.
-   **Self-Healing**: System automatically backfills missing records (State 3) and cleans up incomplete records (State 2) to maintain database-Pinecone synchronization.
-   **Transparent Logging**: All duplicate decisions include state, reason, and layer for debugging and monitoring.

## External Dependencies

### Third-Party APIs & Services
1.  **LlamaParse**: PDF parsing.
2.  **Pinecone**: Vector database.
3.  **OpenAI**: Embedding generation and AI Tagging.
4.  **Google Cloud Platform**: Google Drive API, Google Sheets API.

### Core Libraries
1.  **LlamaIndex**: Document processing.
2.  **Streamlit**: Web application framework.
3.  **Google API Clients**: For Google Drive and Sheets access.
4.  **Celery**: Distributed task queue.
5.  **Redis**: Celery message broker.

### Data Storage
-   **Pinecone**: Vector storage.
-   **PostgreSQL**: Processing history, job tracking, chunk storage, raw parsed text, configuration data, and `parsed_documents` table which stores raw parsed content, AI tags, and complete Google Sheets metadata.
-   **Session State**: Temporary configuration.
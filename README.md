# PDF Chunking & Embedding Pipeline

A comprehensive Streamlit application for processing PDFs from Google Drive using LlamaParse, creating embeddings with LlamaIndex, and storing vectors in Pinecone.

## Features

- **Password Protection**: Simple password-based access control
- **LlamaParse Integration**: High-quality PDF parsing with configurable parameters
- **Flexible Chunking**: Multiple strategies (Token-based, Sentence-based, Semantic)
- **Multiple Embedding Models**: Support for OpenAI and HuggingFace models
- **Metadata Enrichment**: Automatic metadata mapping from Google Sheets
- **Pinecone Storage**: Organized storage with projects, indices, and namespaces
- **Batch Processing**: Process multiple PDFs from a single Google Sheets configuration

## Setup

### 1. API Keys Required

You'll need API keys for the following services:

- **LlamaParse**: Get from [cloud.llamaindex.ai](https://cloud.llamaindex.ai)
- **Pinecone**: Get from [app.pinecone.io](https://app.pinecone.io)
- **OpenAI** (optional): For OpenAI embeddings from [platform.openai.com](https://platform.openai.com)
- **Google Cloud**: Service account JSON for Drive & Sheets access

### 2. Google Cloud Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable Google Drive API and Google Sheets API
3. Create a Service Account
4. Download the JSON credentials file
5. Share your Google Drive folders and Sheets with the service account email

### 3. Environment Variables

Configure the following in Replit Secrets or create a `.env` file:

```
APP_PASSWORD=your_password
LLAMA_CLOUD_API_KEY=your_key
PINECONE_API_KEY=your_key
OPENAI_API_KEY=your_key
```

### 4. Google Sheets Format

Your Google Sheet should have:
- A column with Google Drive PDF links
- Columns for metadata/tags you want to attach to chunks
- Optional: A column to specify Pinecone namespaces

## Usage

1. **Configure API Keys**: Enter your API keys in the Configuration tab
2. **Upload Google Credentials**: Upload your service account JSON file
3. **Load Sheet Data**: Enter your Google Sheets URL and load the data
4. **Select PDFs**: Choose which PDFs to process
5. **Configure Processing**: Set LlamaParse, chunking, and embedding options
6. **Process**: Start the pipeline and monitor progress
7. **Review Status**: Check processing results and statistics

## Chunking Strategies

- **Token-based**: Fixed token size with overlap
- **Sentence-based**: Splits on sentence boundaries
- **Semantic**: AI-powered semantic boundary detection

## Embedding Models

- **OpenAI**: text-embedding-3-small, text-embedding-3-large, ada-002
- **HuggingFace**: BAAI/bge models, sentence-transformers

## LlamaParse Parameters

- Parsing mode (auto, fast, premium)
- Result type (markdown, text)
- Language settings
- Multimodal model support
- Custom page separators

## Architecture

```
PDF (Google Drive)
    ↓
LlamaParse (parsing)
    ↓
LlamaIndex (chunking)
    ↓
Embedding Models (vectorization)
    ↓
Metadata Enrichment (from Google Sheets)
    ↓
Pinecone (storage)
```

## Security

- Password-protected access
- API keys stored securely in environment variables
- Service account credentials handled securely
- No credentials stored in code

## Support

For issues or questions, check the documentation for:
- [LlamaParse](https://docs.llamaindex.ai/en/stable/llama_cloud/llama_parse/)
- [LlamaIndex](https://docs.llamaindex.ai/)
- [Pinecone](https://docs.pinecone.io/)

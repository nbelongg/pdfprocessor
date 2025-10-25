# Quick Start Guide

## Getting Started

Your PDF Chunking & Embedding Pipeline is now running! Here's how to use it:

### Step 1: Prepare Your Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create or select a project
3. Enable these APIs:
   - Google Drive API
   - Google Sheets API
4. Create a Service Account:
   - Go to IAM & Admin → Service Accounts
   - Click "Create Service Account"
   - Give it a name (e.g., "pdf-processor")
   - Grant it "Viewer" role (or Editor if needed)
   - Click "Create Key" → JSON
   - Download the JSON file (keep it secure!)
5. Copy the service account email (looks like `name@project.iam.gserviceaccount.com`)
6. Share your Google Drive PDFs and Sheets with this email address

### Step 2: Set Up Your Google Sheet

Your Google Sheet should have:
- **One column** with Google Drive links to your PDFs
- **Other columns** with metadata, tags, or any information you want attached to chunks
- **Optional:** A column to specify which Pinecone namespace to use

Example structure:
| Drive Link | Title | Author | Year | Topic | Namespace |
|------------|-------|--------|------|-------|-----------|
| https://drive.google.com/file/d/ABC123... | Paper 1 | Smith | 2023 | AI | research |
| https://drive.google.com/file/d/DEF456... | Paper 2 | Jones | 2024 | ML | papers |

### Step 3: Get Your API Keys

- **LlamaParse**: Sign up at [cloud.llamaindex.ai](https://cloud.llamaindex.ai)
- **Pinecone**: Create account at [app.pinecone.io](https://app.pinecone.io)
- **OpenAI** (if using OpenAI embeddings): Get from [platform.openai.com](https://platform.openai.com)

### Step 4: Using the Application

#### Configuration Tab
1. Enter your LlamaParse API key
2. Enter your Pinecone API key
3. Enter your OpenAI API key (if using OpenAI embeddings)
4. Upload your Google Service Account JSON file
5. Wait for "All required API keys configured!" message

#### Select Files Tab
1. Enter your Google Sheets URL
2. Enter the tab name (e.g., "Sheet1")
3. Enter the column name that has Drive links (e.g., "Drive Link")
4. Click "Load Sheet Data"
5. Preview your data
6. Select which PDFs to process (or check "Select All")

#### Processing Settings Tab

**LlamaParse Settings:**
- **Parsing Mode**: Choose quality level (auto, fast, premium)
- **Result Type**: markdown or text
- **Language**: Document language (default: en)
- **Multimodal Model**: Enable for better image/table handling

**Chunking Strategy:**
- **Token-based**: Fixed token chunks (good for most cases)
  - Set chunk size (128-2048 tokens)
  - Set overlap (0-512 tokens)
- **Sentence-based**: Respects sentence boundaries
  - Set chunk size in characters
  - Set overlap
- **Semantic**: AI-powered natural breakpoints
  - Set buffer size

**Embedding Settings:**
- Choose your model:
  - OpenAI: text-embedding-3-small (faster, cheaper)
  - OpenAI: text-embedding-3-large (better quality)
  - HuggingFace: Free, runs locally
- Embedding dimension is auto-detected

**Pinecone Settings:**
- Enter your Pinecone environment (e.g., "gcp-starter")
- Enter index name (will be created if doesn't exist)
- Enter default namespace
- Select which metadata columns to include
- Optionally select a column for dynamic namespaces

#### Process & Upload Tab
1. Review your settings
2. Click "Start Processing Pipeline"
3. Watch the progress bar
4. Check results in Status tab

### Step 5: Monitor Progress

The Status tab shows:
- Number of PDFs processed
- Total chunks created
- Embeddings generated
- Vectors stored in Pinecone

### Common Issues

**"Google credentials required"**
- Make sure you've uploaded the service account JSON file

**"Could not access file"**
- Check that you've shared the Drive files with your service account email
- Verify the Drive links in your sheet are correct

**"Sheet not found"**
- Double-check the sheet tab name (case-sensitive)
- Make sure you've shared the sheet with your service account

**"Pinecone index creation failed"**
- Check your Pinecone API key
- Verify you're on the correct Pinecone plan

### Best Practices

1. **Start small**: Test with 1-2 PDFs first
2. **Check chunks**: Start with token-based chunking (512 tokens, 50 overlap)
3. **Monitor costs**: 
   - LlamaParse charges per page
   - OpenAI charges per token
   - Pinecone has storage limits
4. **Use namespaces**: Organize vectors by project, topic, or date
5. **Tag everything**: More metadata = better searchability later

### Security Notes

- Never share your service account JSON file
- Store API keys in Replit Secrets
- Use read-only permissions when possible
- Regularly rotate your API keys

## Need Help?

Check the documentation:
- [LlamaParse Docs](https://docs.llamaindex.ai/en/stable/llama_cloud/llama_parse/)
- [LlamaIndex Docs](https://docs.llamaindex.ai/)
- [Pinecone Docs](https://docs.pinecone.io/)

Happy processing! 🚀

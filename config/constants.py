"""
Configuration constants for the PDF Processing Pipeline application.
Centralizes all configuration values, page definitions, and default settings.
"""
import os

# ============================================
# APPLICATION CONFIG
# ============================================
APP_TITLE = "PDF Processing Pipeline"
APP_ICON = "📄"

# Security - Password loaded from environment only
APP_PASSWORD = os.getenv("APP_PASSWORD", "admin123")

# ============================================
# PAGE DEFINITIONS
# ============================================
class Page:
    """Page definition with icon and name."""
    def __init__(self, icon: str, name: str, key: str):
        self.icon = icon
        self.name = name
        self.key = key
        self.display_name = f"{icon} {name}"

# Define all pages
PAGES = {
    "home": Page("🔑", "Configuration", "home"),
    "products": Page("🏢", "Products", "products"),
    "data_sources": Page("📚", "Data Sources", "data_sources"),
    "job_queue": Page("⚙️", "Job Management", "job_queue"),
    "monitoring": Page("📊", "Monitoring & Costs", "monitoring"),
    "metadata_management": Page("🔄", "Metadata Management", "metadata_management"),
    "status": Page("📈", "Status", "status"),
    "history": Page("📜", "History", "history"),
    "search": Page("🔍", "Search Test", "search"),
    "diagnostics": Page("🔬", "Diagnostics", "diagnostics"),
}

# Page order for navigation
PAGE_ORDER = [
    "home", "products", "data_sources", "job_queue", "monitoring", "metadata_management", "status", "history", "search", "diagnostics"
]

# ============================================
# DEFAULT VALUES
# ============================================

# Parsing defaults
DEFAULT_PARSING_MODE = "auto"
DEFAULT_RESULT_TYPE = "markdown"
DEFAULT_LANGUAGE = "en"
DEFAULT_PAGE_SEPARATOR = "\n---\n"
DEFAULT_USE_MULTIMODAL = True

# Chunking defaults
DEFAULT_CHUNK_STRATEGY = "Token-based"
DEFAULT_CHUNK_SIZE = 1024
DEFAULT_CHUNK_OVERLAP = 200
DEFAULT_SEMANTIC_BUFFER = 1

# Embedding defaults
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_MODELS = [
    "text-embedding-3-small",
    "text-embedding-3-large"
]

# Embedding dimensions
EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072
}

# Tagging defaults
DEFAULT_TAGGING_ENABLED = False
DEFAULT_TAGGING_MODEL = "gpt-4o-mini"
TAGGING_MODELS = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]

# Pinecone defaults
DEFAULT_PINECONE_ENV = "us-east-1"
DEFAULT_NAMESPACE = "default"

# Chunking strategies
CHUNKING_STRATEGIES = ["Token-based", "Sentence-based", "Semantic"]

# Parsing modes
PARSING_MODES = ["auto", "fast", "premium", "balanced", "llm", "lvm"]
RESULT_TYPES = ["markdown", "text", "json", "structured"]

# ============================================
# UI TEXT & MESSAGES
# ============================================

# Success messages
MSG_PRODUCT_CREATED = "✅ Created product: {}"
MSG_PRODUCT_UPDATED = "✅ Updated product: {}"
MSG_PRODUCT_DELETED = "Deleted product: {}"
MSG_SOURCE_CREATED = "✅ Created data source: {}"
MSG_SOURCE_UPDATED = "Updated {}"
MSG_SOURCE_DELETED = "Deleted {}"

# Error messages
MSG_INVALID_PASSWORD = "❌ Invalid password"
MSG_MISSING_REQUIRED = "Product name and Pinecone index are required"
MSG_SOURCE_NOT_FOUND = "Source not found"
MSG_NO_FILES_SELECTED = "No files selected. Please select files in the Select Files page."
MSG_NO_SHEETS_CONFIGURED = "No Google Sheets configured. Please add data sources first."

# Info messages
MSG_NO_PRODUCTS = "No products configured yet. Create one in the 'Add/Edit Product' tab."
MSG_NO_SOURCES = "No data sources configured yet. Add one in the 'Add/Edit Source' tab."
MSG_LOADING = "Loading data..."

# Help text
HELP_SECRET_NAME = "Name of the Replit secret containing the {} API key"
HELP_GOOGLE_CREDS = "Name of the Replit secret containing the Google service account JSON (as a string)"
HELP_CHUNK_SIZE = "Maximum size of each chunk (tokens or characters)"
HELP_CHUNK_OVERLAP = "Number of tokens/characters to overlap between chunks"
HELP_EMBEDDING_DIMENSION = "Number of dimensions (max {} for {}). Lower = faster & cheaper, but may reduce quality."
HELP_TAGGING_PROMPT = "Customize the prompt for tag generation. Use {{text}}, {{filename}}, and metadata field names as variables."

# ============================================
# UI COMPONENTS
# ============================================

# Column ratios
COL_RATIO_2 = [1, 1]
COL_RATIO_3 = [1, 1, 1]

# Button labels
BTN_REFRESH = "🔄 Refresh"
BTN_SAVE = "💾 Save Product"
BTN_CANCEL = "Cancel"
BTN_EDIT = "✏️ Edit"
BTN_DELETE = "🗑️ Delete"
BTN_UPLOAD = "⬆️ Upload to Pinecone"
BTN_PROCESS = "🚀 Start Processing"

# ============================================
# FILE SIZE LIMITS
# ============================================
MAX_FILE_SIZE_MB = 50
MAX_BATCH_SIZE = 100

# ============================================
# CHUNK LIMITS
# ============================================
MIN_CHUNK_SIZE = 128
MAX_CHUNK_SIZE = 4096
MIN_CHUNK_OVERLAP = 0
MAX_CHUNK_OVERLAP = 512
MIN_SEMANTIC_BUFFER = 1
MAX_SEMANTIC_BUFFER = 5
MIN_EMBEDDING_DIMENSION = 256

# ============================================
# SECRETS EXAMPLE
# ============================================
SECRETS_EXAMPLE_TEMPLATE = """
# Example for "{product_name}" product

Replit Secrets to configure:
┌─────────────────────────────────────────────────────────────────┐
│ Secret Name: {product_name_upper}_LLAMAPARSE_KEY                          │
│ Secret Value: llx-abc123xyz...                                 │
├─────────────────────────────────────────────────────────────────┤
│ Secret Name: {product_name_upper}_OPENAI_KEY                              │
│ Secret Value: sk-proj-def456...                                │
├─────────────────────────────────────────────────────────────────┤
│ Secret Name: {product_name_upper}_PINECONE_KEY                            │
│ Secret Value: pcsk-ghi789...                                   │
├─────────────────────────────────────────────────────────────────┤
│ Secret Name: {product_name_upper}_GOOGLE_CREDS                            │
│ Secret Value: {{"type": "service_account", "project_id": ...}}   │
└─────────────────────────────────────────────────────────────────┘

Then in the Products tab:
- LlamaParse Secret Name: {product_name_upper}_LLAMAPARSE_KEY
- OpenAI Secret Name: {product_name_upper}_OPENAI_KEY
- Pinecone Secret Name: {product_name_upper}_PINECONE_KEY
- Google Credentials Secret Name: {product_name_upper}_GOOGLE_CREDS
"""

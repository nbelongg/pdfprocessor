import streamlit as st
import os
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict, Optional
import io
import json

load_dotenv()

st.set_page_config(
    page_title="PDF Chunking & Embedding Pipeline",
    page_icon="📄",
    layout="wide"
)

def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == os.getenv("APP_PASSWORD", "admin123"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.info("💡 Default password is 'admin123'. Set APP_PASSWORD in Secrets to change it.")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title("📄 PDF Chunking & Embedding Pipeline")
st.markdown("Process PDFs from Google Drive using LlamaParse, chunk them, create embeddings, and store in Pinecone")

if 'processing_state' not in st.session_state:
    st.session_state.processing_state = None

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🔑 Configuration", 
    "📁 Select Files", 
    "⚙️ Processing Settings", 
    "🚀 Process & Upload",
    "📊 Status"
])

with tab1:
    st.header("API Configuration")
    st.markdown("Configure your API keys and credentials for the pipeline")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("LlamaParse API")
        llama_api_key = st.text_input(
            "LlamaParse API Key",
            type="password",
            value=st.session_state.get('llama_api_key', os.getenv('LLAMA_CLOUD_API_KEY', '')),
            help="Get your API key from cloud.llamaindex.ai"
        )
        if llama_api_key:
            st.session_state.llama_api_key = llama_api_key
        
        st.subheader("Pinecone API")
        pinecone_api_key = st.text_input(
            "Pinecone API Key",
            type="password",
            value=st.session_state.get('pinecone_api_key', os.getenv('PINECONE_API_KEY', '')),
            help="Get your API key from app.pinecone.io"
        )
        if pinecone_api_key:
            st.session_state.pinecone_api_key = pinecone_api_key
        
        st.subheader("Embedding Model API")
        embedding_provider = st.selectbox(
            "Embedding Provider",
            ["OpenAI", "HuggingFace"],
            key="embedding_provider_select"
        )
        
        if embedding_provider == "OpenAI":
            openai_api_key = st.text_input(
                "OpenAI API Key",
                type="password",
                value=st.session_state.get('openai_api_key', os.getenv('OPENAI_API_KEY', '')),
                help="Required for OpenAI embeddings"
            )
            if openai_api_key:
                st.session_state.openai_api_key = openai_api_key
    
    with col2:
        st.subheader("Google Drive & Sheets")
        st.markdown("Upload your Google Service Account JSON credentials")
        
        uploaded_file = st.file_uploader(
            "Service Account JSON",
            type=['json'],
            help="Download from Google Cloud Console"
        )
        
        if uploaded_file is not None:
            credentials_data = json.load(uploaded_file)
            st.session_state.google_credentials = credentials_data
            st.success("✅ Google credentials loaded")
        elif 'google_credentials' in st.session_state:
            st.success("✅ Google credentials already loaded")
        else:
            st.info("📤 Upload your service account JSON file")
        
        st.markdown("---")
        st.markdown("**Alternative: Use API Keys**")
        google_api_key = st.text_input(
            "Google API Key (Optional)",
            type="password",
            value=st.session_state.get('google_api_key', os.getenv('GOOGLE_API_KEY', '')),
            help="Alternative to service account"
        )
        if google_api_key:
            st.session_state.google_api_key = google_api_key

    st.markdown("---")
    
    required_keys = []
    if not st.session_state.get('llama_api_key'):
        required_keys.append("LlamaParse API Key")
    if not st.session_state.get('pinecone_api_key'):
        required_keys.append("Pinecone API Key")
    if embedding_provider == "OpenAI" and not st.session_state.get('openai_api_key'):
        required_keys.append("OpenAI API Key")
    if not st.session_state.get('google_credentials') and not st.session_state.get('google_api_key'):
        required_keys.append("Google Credentials")
    
    if required_keys:
        st.warning(f"⚠️ Missing: {', '.join(required_keys)}")
    else:
        st.success("✅ All required API keys configured!")

with tab2:
    st.header("Select Files from Google Drive")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Google Sheets Configuration")
        sheet_url = st.text_input(
            "Google Sheets URL",
            value=st.session_state.get('sheet_url', ''),
            help="Full URL of your Google Sheet with metadata"
        )
        if sheet_url:
            st.session_state.sheet_url = sheet_url
        
        sheet_tab = st.text_input(
            "Sheet Tab Name",
            value=st.session_state.get('sheet_tab', 'Sheet1'),
            help="Name of the tab containing your data"
        )
        if sheet_tab:
            st.session_state.sheet_tab = sheet_tab
        
        drive_link_column = st.text_input(
            "Google Drive Link Column",
            value=st.session_state.get('drive_link_column', 'Drive Link'),
            help="Column name containing Google Drive PDF links"
        )
        if drive_link_column:
            st.session_state.drive_link_column = drive_link_column
        
        if st.button("📥 Load Sheet Data"):
            if st.session_state.get('google_credentials') or st.session_state.get('google_api_key'):
                with st.spinner("Loading Google Sheets data..."):
                    try:
                        from utils.google_sheets import load_sheet_data
                        df = load_sheet_data(
                            sheet_url,
                            sheet_tab,
                            st.session_state.get('google_credentials')
                        )
                        st.session_state.sheet_data = df
                        st.success(f"✅ Loaded {len(df)} rows from Google Sheets")
                    except Exception as e:
                        st.error(f"❌ Error loading sheet: {str(e)}")
            else:
                st.error("❌ Please configure Google credentials first")
    
    with col2:
        st.subheader("Data Preview")
        if 'sheet_data' in st.session_state:
            st.dataframe(st.session_state.sheet_data.head(), use_container_width=True)
            st.caption(f"Showing first 5 of {len(st.session_state.sheet_data)} rows")
        else:
            st.info("Load sheet data to preview")
    
    st.markdown("---")
    
    if 'sheet_data' in st.session_state:
        st.subheader("Select PDFs to Process")
        
        df = st.session_state.sheet_data
        
        if drive_link_column in df.columns:
            pdf_rows = df[df[drive_link_column].notna()]
            
            select_all = st.checkbox("Select All PDFs", value=False)
            
            if select_all:
                selected_indices = list(range(len(pdf_rows)))
            else:
                selected_indices = st.multiselect(
                    "Choose PDFs to process",
                    options=list(range(len(pdf_rows))),
                    format_func=lambda x: f"Row {x+1}: {pdf_rows.iloc[x].get('Title', pdf_rows.iloc[x][drive_link_column][:50])}",
                    default=[]
                )
            
            st.session_state.selected_pdf_indices = selected_indices
            st.info(f"📌 Selected {len(selected_indices)} PDF(s) for processing")
        else:
            st.warning(f"⚠️ Column '{drive_link_column}' not found in sheet")

with tab3:
    st.header("Processing Settings")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔍 LlamaParse Settings")
        
        parsing_mode = st.selectbox(
            "Parsing Mode",
            ["auto", "fast", "premium"],
            help="auto: Automatic selection, fast: Quick parsing, premium: High quality"
        )
        st.session_state.parsing_mode = parsing_mode
        
        result_type = st.selectbox(
            "Result Type",
            ["markdown", "text"],
            help="Output format from LlamaParse"
        )
        st.session_state.result_type = result_type
        
        language = st.text_input(
            "Language",
            value="en",
            help="Language code (e.g., en, es, fr)"
        )
        st.session_state.language = language
        
        use_vendor_multimodal = st.checkbox(
            "Use Vendor Multimodal Model",
            value=True,
            help="Enable for better handling of images and tables"
        )
        st.session_state.use_vendor_multimodal = use_vendor_multimodal
        
        page_separator = st.text_input(
            "Page Separator",
            value="\\n---\\n",
            help="Separator between pages in output"
        )
        st.session_state.page_separator = page_separator
        
        st.subheader("🔪 Chunking Strategy")
        
        chunking_strategy = st.selectbox(
            "Strategy",
            ["Token-based", "Sentence-based", "Semantic"],
            help="How to split documents into chunks"
        )
        st.session_state.chunking_strategy = chunking_strategy
        
        if chunking_strategy == "Token-based":
            chunk_size = st.slider(
                "Chunk Size (tokens)",
                min_value=128,
                max_value=2048,
                value=512,
                step=128
            )
            chunk_overlap = st.slider(
                "Chunk Overlap (tokens)",
                min_value=0,
                max_value=512,
                value=50,
                step=10
            )
            st.session_state.chunk_size = chunk_size
            st.session_state.chunk_overlap = chunk_overlap
        
        elif chunking_strategy == "Sentence-based":
            sentences_per_chunk = st.slider(
                "Sentences per Chunk",
                min_value=1,
                max_value=20,
                value=5,
                step=1
            )
            st.session_state.sentences_per_chunk = sentences_per_chunk
        
        elif chunking_strategy == "Semantic":
            st.info("Semantic chunking uses AI to identify natural breakpoints")
            buffer_size = st.slider(
                "Buffer Size",
                min_value=1,
                max_value=5,
                value=1,
                step=1,
                help="Number of sentences to consider for semantic boundaries"
            )
            st.session_state.semantic_buffer_size = buffer_size
    
    with col2:
        st.subheader("🧠 Embedding Settings")
        
        embedding_model_choice = st.selectbox(
            "Embedding Model",
            [
                "text-embedding-3-small (OpenAI)",
                "text-embedding-3-large (OpenAI)",
                "text-embedding-ada-002 (OpenAI)",
                "BAAI/bge-small-en-v1.5 (HuggingFace)",
                "BAAI/bge-base-en-v1.5 (HuggingFace)",
                "sentence-transformers/all-MiniLM-L6-v2 (HuggingFace)"
            ],
            help="Choose your embedding model"
        )
        st.session_state.embedding_model = embedding_model_choice
        
        embedding_dimension = st.number_input(
            "Embedding Dimension",
            min_value=128,
            max_value=3072,
            value=1536 if "OpenAI" in embedding_model_choice else 384,
            help="Dimension of embedding vectors (auto-detected)"
        )
        st.session_state.embedding_dimension = embedding_dimension
        
        st.subheader("📍 Pinecone Settings")
        
        pinecone_environment = st.text_input(
            "Pinecone Environment",
            value=st.session_state.get('pinecone_environment', 'gcp-starter'),
            help="Your Pinecone environment (e.g., gcp-starter, us-east-1-aws)"
        )
        st.session_state.pinecone_environment = pinecone_environment
        
        index_name = st.text_input(
            "Index Name",
            value=st.session_state.get('index_name', 'research-papers'),
            help="Pinecone index name"
        )
        st.session_state.index_name = index_name
        
        default_namespace = st.text_input(
            "Default Namespace",
            value=st.session_state.get('default_namespace', 'default'),
            help="Default namespace (can be overridden by sheet metadata)"
        )
        st.session_state.default_namespace = default_namespace
        
        st.subheader("🏷️ Metadata Mapping")
        
        st.markdown("**Columns to include as metadata:**")
        
        if 'sheet_data' in st.session_state:
            available_columns = [col for col in st.session_state.sheet_data.columns 
                               if col != st.session_state.get('drive_link_column', '')]
            
            metadata_columns = st.multiselect(
                "Select metadata columns",
                options=available_columns,
                default=available_columns[:5] if len(available_columns) >= 5 else available_columns,
                help="Choose which columns to attach as metadata to chunks"
            )
            st.session_state.metadata_columns = metadata_columns
            
            namespace_column = st.selectbox(
                "Namespace Column (optional)",
                options=["None"] + available_columns,
                help="Column to use for Pinecone namespace (overrides default)"
            )
            st.session_state.namespace_column = None if namespace_column == "None" else namespace_column
        else:
            st.info("Load sheet data first to configure metadata mapping")

with tab4:
    st.header("Process & Upload to Pinecone")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("PDFs Selected", len(st.session_state.get('selected_pdf_indices', [])))
    with col2:
        st.metric("Total Rows in Sheet", len(st.session_state.get('sheet_data', [])))
    with col3:
        st.metric("Metadata Columns", len(st.session_state.get('metadata_columns', [])))
    
    st.markdown("---")
    
    if st.button("🚀 Start Processing Pipeline", type="primary", use_container_width=True):
        selected_indices = st.session_state.get('selected_pdf_indices', [])
        
        if not selected_indices:
            st.error("❌ Please select at least one PDF to process")
        elif not st.session_state.get('llama_api_key'):
            st.error("❌ LlamaParse API key required")
        elif not st.session_state.get('pinecone_api_key'):
            st.error("❌ Pinecone API key required")
        elif not st.session_state.get('sheet_data') is not None:
            st.error("❌ Please load sheet data first")
        else:
            st.session_state.processing_state = "running"
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                from utils.pipeline import process_pipeline
                
                results = process_pipeline(
                    sheet_data=st.session_state.sheet_data,
                    selected_indices=selected_indices,
                    config={
                        'llama_api_key': st.session_state.llama_api_key,
                        'pinecone_api_key': st.session_state.pinecone_api_key,
                        'openai_api_key': st.session_state.get('openai_api_key'),
                        'google_credentials': st.session_state.get('google_credentials'),
                        'parsing_mode': st.session_state.get('parsing_mode', 'auto'),
                        'result_type': st.session_state.get('result_type', 'markdown'),
                        'language': st.session_state.get('language', 'en'),
                        'use_vendor_multimodal': st.session_state.get('use_vendor_multimodal', True),
                        'page_separator': st.session_state.get('page_separator', '\\n---\\n'),
                        'chunking_strategy': st.session_state.get('chunking_strategy', 'Token-based'),
                        'chunk_size': st.session_state.get('chunk_size', 512),
                        'chunk_overlap': st.session_state.get('chunk_overlap', 50),
                        'sentences_per_chunk': st.session_state.get('sentences_per_chunk', 5),
                        'semantic_buffer_size': st.session_state.get('semantic_buffer_size', 1),
                        'embedding_model': st.session_state.get('embedding_model'),
                        'embedding_dimension': st.session_state.get('embedding_dimension', 1536),
                        'pinecone_environment': st.session_state.get('pinecone_environment'),
                        'index_name': st.session_state.get('index_name'),
                        'default_namespace': st.session_state.get('default_namespace', 'default'),
                        'metadata_columns': st.session_state.get('metadata_columns', []),
                        'namespace_column': st.session_state.get('namespace_column'),
                        'drive_link_column': st.session_state.get('drive_link_column', 'Drive Link')
                    },
                    progress_callback=lambda pct, msg: (progress_bar.progress(pct), status_text.text(msg))
                )
                
                st.session_state.processing_results = results
                st.session_state.processing_state = "completed"
                
                st.success("✅ Processing completed successfully!")
                st.balloons()
                
            except Exception as e:
                st.session_state.processing_state = "error"
                st.error(f"❌ Error during processing: {str(e)}")
                st.exception(e)

with tab5:
    st.header("Processing Status & Logs")
    
    if st.session_state.processing_state == "running":
        st.info("🔄 Processing in progress...")
    elif st.session_state.processing_state == "completed":
        st.success("✅ Processing completed!")
        
        if 'processing_results' in st.session_state:
            results = st.session_state.processing_results
            
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("PDFs Processed", results.get('total_pdfs', 0))
            with col2:
                st.metric("Total Chunks", results.get('total_chunks', 0))
            with col3:
                st.metric("Embeddings Created", results.get('total_embeddings', 0))
            with col4:
                st.metric("Vectors Stored", results.get('vectors_stored', 0))
            
            st.subheader("Processing Details")
            if 'details' in results:
                st.json(results['details'])
    
    elif st.session_state.processing_state == "error":
        st.error("❌ Processing encountered an error")
    else:
        st.info("👆 Configure settings and start processing to see status here")

st.markdown("---")
st.caption("PDF Chunking & Embedding Pipeline v1.0 | Powered by LlamaParse, LlamaIndex, and Pinecone")

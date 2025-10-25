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

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9 = st.tabs([
    "🔑 Configuration",
    "📚 Data Sources",
    "📁 Select Files", 
    "⚙️ Processing Settings", 
    "👁️ Preview Chunks",
    "🚀 Process & Upload",
    "📊 Status",
    "📜 History",
    "🔍 Search Test"
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
    
    required_keys = []
    if not st.session_state.get('llama_api_key'):
        required_keys.append("LlamaParse API Key")
    if not st.session_state.get('pinecone_api_key'):
        required_keys.append("Pinecone API Key")
    if embedding_provider == "OpenAI" and not st.session_state.get('openai_api_key'):
        required_keys.append("OpenAI API Key")
    if not st.session_state.get('google_credentials'):
        required_keys.append("Google Service Account JSON")
    
    if required_keys:
        st.warning(f"⚠️ Missing: {', '.join(required_keys)}")
    else:
        st.success("✅ All required API keys configured!")

with tab2:
    st.header("Data Sources Management")
    st.markdown("Manage Google Sheet data sources for different paper topics")
    
    from utils.database import (
        get_data_sources, create_data_source, update_data_source, 
        delete_data_source, get_column_mappings, save_column_mapping,
        delete_column_mapping
    )
    from utils.google_sheets import load_sheet_data
    
    subtab1, subtab2 = st.tabs(["📋 View Sources", "➕ Add/Edit Source"])
    
    with subtab1:
        st.subheader("Existing Data Sources")
        
        if st.button("🔄 Refresh Sources"):
            st.session_state.data_sources = get_data_sources()
        
        if 'data_sources' not in st.session_state:
            st.session_state.data_sources = get_data_sources()
        
        sources = st.session_state.data_sources
        
        if sources:
            for source in sources:
                status_icon = "✅" if source['active'] else "❌"
                with st.expander(f"{status_icon} {source['name']} - {source.get('topic', 'No topic')}"):
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.markdown(f"**Sheet URL:** {source['sheet_url'][:50]}...")
                        st.markdown(f"**Tab:** {source['sheet_tab']}")
                    with col2:
                        st.markdown(f"**Namespace:** {source['default_namespace']}")
                        st.markdown(f"**Active:** {'Yes' if source['active'] else 'No'}")
                    with col3:
                        st.markdown(f"**Last Processed:** {source.get('last_processed_at', 'Never')}")
                        st.markdown(f"**Last Row:** {source.get('last_processed_row', 0)}")
                    
                    st.markdown("**Column Mappings:**")
                    mappings = get_column_mappings(source['id'])
                    if mappings:
                        mapping_df = pd.DataFrame([{
                            'Role': m['column_role'],
                            'Column': m['column_name'],
                            'Required': '✓' if m['is_required'] else ''
                        } for m in mappings])
                        st.dataframe(mapping_df, use_container_width=True)
                    else:
                        st.info("No column mappings configured")
                    
                    col_a, col_b, col_c = st.columns(3)
                    
                    with col_a:
                        if st.button(f"Edit", key=f"edit_{source['id']}"):
                            st.session_state.edit_source_id = source['id']
                            st.session_state.active_subtab = "Add/Edit Source"
                            st.rerun()
                    
                    with col_b:
                        active_toggle = st.checkbox(
                            "Active",
                            value=source['active'],
                            key=f"active_{source['id']}"
                        )
                        if active_toggle != source['active']:
                            update_data_source(source['id'], active=active_toggle)
                            st.success(f"Updated {source['name']}")
                            st.rerun()
                    
                    with col_c:
                        if st.button(f"Delete", key=f"del_{source['id']}"):
                            delete_data_source(source['id'])
                            st.success(f"Deleted {source['name']}")
                            st.rerun()
        else:
            st.info("No data sources configured yet. Add one in the 'Add/Edit Source' tab.")
    
    with subtab2:
        st.subheader("Add or Edit Data Source")
        
        edit_mode = 'edit_source_id' in st.session_state
        editing_source = None
        
        if edit_mode:
            from utils.database import get_data_source
            editing_source = get_data_source(st.session_state.edit_source_id)
            if editing_source:
                st.info(f"Editing: {editing_source['name']}")
            else:
                st.error("Source not found")
                del st.session_state.edit_source_id
                edit_mode = False
        
        col1, col2 = st.columns(2)
        
        with col1:
            source_name = st.text_input(
                "Source Name",
                value=editing_source['name'] if (edit_mode and editing_source) else "",
                help="Unique identifier for this data source"
            )
            
            source_url = st.text_input(
                "Google Sheet URL",
                value=editing_source['sheet_url'] if (edit_mode and editing_source) else "",
                help="Full URL of the Google Sheet"
            )
            
            source_tab = st.text_input(
                "Sheet Tab Name",
                value=editing_source['sheet_tab'] if (edit_mode and editing_source) else "Sheet1",
                help="Which tab/worksheet to use"
            )
        
        with col2:
            source_topic = st.text_input(
                "Topic/Category",
                value=editing_source.get('topic', '') if (edit_mode and editing_source) else "",
                help="Optional topic or category for organization"
            )
            
            source_namespace = st.text_input(
                "Default Namespace",
                value=editing_source['default_namespace'] if (edit_mode and editing_source) else "default",
                help="Pinecone namespace for this source"
            )
        
        st.markdown("---")
        st.subheader("Column Mappings")
        st.markdown("Map your sheet columns to predefined roles")
        
        if source_url and st.button("🔍 Auto-Detect Columns"):
            with st.spinner("Loading sheet columns..."):
                try:
                    temp_data = load_sheet_data(source_url, source_tab, st.session_state.get('google_credentials'))
                    st.session_state.detected_columns = list(temp_data.columns) if temp_data is not None else []
                    st.success(f"Found {len(st.session_state.detected_columns)} columns")
                except Exception as e:
                    st.error(f"Error loading sheet: {str(e)}")
        
        available_columns = st.session_state.get('detected_columns', [])
        
        if available_columns:
            st.info(f"Available columns: {', '.join(available_columns)}")
        
        COLUMN_ROLES = {
            'drive_link': 'Drive Link (required)',
            'paper_title': 'Paper Title',
            'authors': 'Authors',
            'publication_year': 'Publication Year',
            'journal': 'Journal/Conference',
            'abstract': 'Abstract',
            'tags': 'Tags/Keywords',
            'namespace': 'Namespace (overrides default)',
            'custom_1': 'Custom Field 1',
            'custom_2': 'Custom Field 2',
            'custom_3': 'Custom Field 3'
        }
        
        if edit_mode:
            current_mappings = {m['column_role']: m['column_name'] for m in get_column_mappings(st.session_state.edit_source_id)}
        else:
            current_mappings = {}
        
        st.session_state.column_mappings_temp = {}
        
        for role_key, role_label in COLUMN_ROLES.items():
            col_map_a, col_map_b = st.columns([2, 1])
            
            with col_map_a:
                column_options = ["None"] + available_columns
                default_value = current_mappings.get(role_key, "None")
                
                if default_value not in column_options and default_value != "None":
                    column_options.insert(1, default_value)
                
                selected = st.selectbox(
                    role_label,
                    options=column_options,
                    index=column_options.index(default_value) if default_value in column_options else 0,
                    key=f"map_{role_key}"
                )
                
                if selected != "None":
                    st.session_state.column_mappings_temp[role_key] = selected
            
            with col_map_b:
                if role_key == 'drive_link':
                    st.checkbox("Required", value=True, disabled=True, key=f"req_{role_key}")
                else:
                    st.checkbox("Required", value=False, key=f"req_{role_key}")
        
        st.markdown("---")
        
        col_save, col_cancel = st.columns(2)
        
        with col_save:
            if st.button("💾 Save Data Source", type="primary", use_container_width=True):
                if not source_name:
                    st.error("Please provide a source name")
                elif not source_url:
                    st.error("Please provide a Google Sheet URL")
                elif 'drive_link' not in st.session_state.column_mappings_temp:
                    st.error("Drive Link column mapping is required")
                else:
                    try:
                        if edit_mode:
                            update_data_source(
                                st.session_state.edit_source_id,
                                name=source_name,
                                sheet_url=source_url,
                                sheet_tab=source_tab,
                                topic=source_topic,
                                default_namespace=source_namespace
                            )
                            source_id = st.session_state.edit_source_id
                        else:
                            source_id = create_data_source(
                                source_name, source_url, source_tab,
                                source_topic, source_namespace
                            )
                        
                        for role, column in st.session_state.column_mappings_temp.items():
                            is_req = role == 'drive_link'
                            save_column_mapping(source_id, role, column, is_req)
                        
                        st.success(f"✅ {'Updated' if edit_mode else 'Created'} data source: {source_name}")
                        
                        if 'edit_source_id' in st.session_state:
                            del st.session_state.edit_source_id
                        if 'detected_columns' in st.session_state:
                            del st.session_state.detected_columns
                        if 'column_mappings_temp' in st.session_state:
                            del st.session_state.column_mappings_temp
                        
                        st.session_state.data_sources = get_data_sources()
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error saving data source: {str(e)}")
        
        with col_cancel:
            if st.button("Cancel", use_container_width=True):
                if 'edit_source_id' in st.session_state:
                    del st.session_state.edit_source_id
                if 'detected_columns' in st.session_state:
                    del st.session_state.detected_columns
                st.rerun()

with tab3:
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
            if st.session_state.get('google_credentials'):
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
                st.error("❌ Please upload Google Service Account JSON file first")
    
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
            chunk_size = st.slider(
                "Chunk Size (characters)",
                min_value=256,
                max_value=4096,
                value=1024,
                step=128,
                help="Maximum size of each chunk"
            )
            chunk_overlap = st.slider(
                "Chunk Overlap (characters)",
                min_value=0,
                max_value=512,
                value=200,
                step=50,
                help="Overlap between consecutive chunks"
            )
            st.session_state.chunk_size = chunk_size
            st.session_state.chunk_overlap = chunk_overlap
        
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
    st.header("Preview Chunks")
    st.markdown("Preview how your PDFs will be chunked before uploading to Pinecone")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Preview Settings")
        
        preview_limit = st.number_input(
            "Number of PDFs to Preview",
            min_value=1,
            max_value=10,
            value=1,
            help="How many PDFs to parse and chunk for preview"
        )
        
        if st.button("🔍 Generate Preview", use_container_width=True):
            selected_indices = st.session_state.get('selected_pdf_indices', [])[:preview_limit]
            
            if not selected_indices:
                st.error("❌ Please select at least one PDF")
            elif not st.session_state.get('llama_api_key'):
                st.error("❌ LlamaParse API key required")
            elif not st.session_state.get('sheet_data') is not None:
                st.error("❌ Please load sheet data first")
            else:
                with st.spinner("Generating preview..."):
                    try:
                        from utils.pipeline import process_pipeline
                        
                        results = process_pipeline(
                            sheet_data=st.session_state.sheet_data,
                            selected_indices=selected_indices,
                            config={
                                'llama_api_key': st.session_state.llama_api_key,
                                'google_credentials': st.session_state.get('google_credentials'),
                                'parsing_mode': st.session_state.get('parsing_mode', 'auto'),
                                'result_type': st.session_state.get('result_type', 'markdown'),
                                'language': st.session_state.get('language', 'en'),
                                'use_vendor_multimodal': st.session_state.get('use_vendor_multimodal', True),
                                'page_separator': st.session_state.get('page_separator', '\\n---\\n'),
                                'chunking_strategy': st.session_state.get('chunking_strategy', 'Token-based'),
                                'chunk_size': st.session_state.get('chunk_size', 512),
                                'chunk_overlap': st.session_state.get('chunk_overlap', 50),
                                'semantic_buffer_size': st.session_state.get('semantic_buffer_size', 1),
                                'embedding_model': st.session_state.get('embedding_model'),
                                'metadata_columns': st.session_state.get('metadata_columns', []),
                                'namespace_column': st.session_state.get('namespace_column'),
                                'drive_link_column': st.session_state.get('drive_link_column', 'Drive Link'),
                                'default_namespace': st.session_state.get('default_namespace', 'default'),
                                'sheet_url': st.session_state.get('sheet_url', ''),
                                'sheet_tab': st.session_state.get('sheet_tab', 'Sheet1')
                            },
                            preview_mode=True
                        )
                        
                        st.session_state.preview_results = results
                        st.success(f"✅ Preview generated for {results['total_pdfs']} PDF(s)")
                        
                    except Exception as e:
                        st.error(f"❌ Error generating preview: {str(e)}")
                        st.exception(e)
    
    with col2:
        st.subheader("Chunk Preview")
        
        if 'preview_results' in st.session_state:
            results = st.session_state.preview_results
            chunks = results.get('preview_chunks', [])
            
            if chunks:
                st.info(f"📊 Generated {len(chunks)} chunks from {results['total_pdfs']} PDF(s)")
                
                chunk_idx = st.number_input(
                    "Chunk to view",
                    min_value=0,
                    max_value=len(chunks)-1,
                    value=0
                )
                
                chunk = chunks[chunk_idx]
                
                st.markdown(f"**Chunk {chunk_idx + 1} of {len(chunks)}**")
                st.markdown(f"**Namespace:** `{chunk['namespace']}`")
                
                with st.expander("📝 Chunk Text", expanded=True):
                    st.text_area(
                        "Content",
                        chunk['text'],
                        height=300,
                        key=f"chunk_{chunk_idx}"
                    )
                
                with st.expander("🏷️ Metadata", expanded=False):
                    st.json(chunk['metadata'])
            else:
                st.warning("No chunks generated")
        else:
            st.info("Click 'Generate Preview' to see chunks")

with tab5:
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
                        'semantic_buffer_size': st.session_state.get('semantic_buffer_size', 1),
                        'embedding_model': st.session_state.get('embedding_model'),
                        'embedding_dimension': st.session_state.get('embedding_dimension', 1536),
                        'pinecone_environment': st.session_state.get('pinecone_environment'),
                        'index_name': st.session_state.get('index_name'),
                        'default_namespace': st.session_state.get('default_namespace', 'default'),
                        'metadata_columns': st.session_state.get('metadata_columns', []),
                        'namespace_column': st.session_state.get('namespace_column'),
                        'drive_link_column': st.session_state.get('drive_link_column', 'Drive Link'),
                        'sheet_url': st.session_state.get('sheet_url', ''),
                        'sheet_tab': st.session_state.get('sheet_tab', 'Sheet1')
                    },
                    progress_callback=lambda pct, msg: (progress_bar.progress(pct), status_text.text(msg)),
                    preview_mode=False
                )
                
                st.session_state.processing_results = results
                st.session_state.processing_state = "completed"
                
                st.success("✅ Processing completed successfully!")
                st.balloons()
                
            except Exception as e:
                st.session_state.processing_state = "error"
                st.error(f"❌ Error during processing: {str(e)}")
                st.exception(e)

with tab6:
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
            
            st.subheader("Job ID")
            st.code(results.get('job_id', 'N/A'))
            
            st.subheader("Processing Details")
            if 'details' in results:
                st.json(results['details'])
    
    elif st.session_state.processing_state == "error":
        st.error("❌ Processing encountered an error")
    else:
        st.info("👆 Configure settings and start processing to see status here")

with tab7:
    st.header("Processing History")
    st.markdown("View past processing jobs and their results")
    
    if st.button("🔄 Refresh History"):
        from utils.database import get_job_history
        st.session_state.job_history = get_job_history(50)
    
    if 'job_history' not in st.session_state:
        from utils.database import get_job_history
        st.session_state.job_history = get_job_history(50)
    
    history = st.session_state.job_history
    
    if history:
        for job in history:
            with st.expander(f"Job {job['job_id'][:8]}... - {job['status']} - {job.get('created_at', 'N/A')}"):
                col1, col2, col3, col4, col5 = st.columns(5)
                
                with col1:
                    st.metric("Status", job['status'])
                with col2:
                    st.metric("PDFs", job.get('total_pdfs', 0))
                with col3:
                    st.metric("Chunks", job.get('total_chunks', 0))
                with col4:
                    st.metric("Embeddings", job.get('total_embeddings', 0))
                with col5:
                    st.metric("Stored", job.get('vectors_stored', 0))
                
                st.markdown(f"**Sheet:** {job.get('sheet_url', 'N/A')}")
                st.markdown(f"**Tab:** {job.get('sheet_tab', 'N/A')}")
                
                if st.button(f"View Details", key=f"view_{job['job_id']}"):
                    from utils.database import get_job_details, get_job_chunks
                    
                    details = get_job_details(job['job_id'])
                    chunks = get_job_chunks(job['job_id'])
                    
                    st.session_state[f"job_details_{job['job_id']}"] = details
                    st.session_state[f"job_chunks_{job['job_id']}"] = chunks
                
                if f"job_chunks_{job['job_id']}" in st.session_state:
                    chunks = st.session_state[f"job_chunks_{job['job_id']}"]
                    st.info(f"📊 {len(chunks)} chunks stored for this job")
                    
                    if chunks:
                        chunk_df = pd.DataFrame([{
                            'file_id': c['file_id'],
                            'filename': c['filename'],
                            'chunk_index': c['chunk_index'],
                            'namespace': c['namespace'],
                            'uploaded': c['embedding_stored']
                        } for c in chunks])
                        st.dataframe(chunk_df, use_container_width=True)
    else:
        st.info("No processing history found")

with tab8:
    st.header("Vector Search Testing")
    st.markdown("Query your Pinecone index to test stored embeddings")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("Search Configuration")
        
        search_query = st.text_area(
            "Search Query",
            height=100,
            help="Enter your search query text"
        )
        
        search_namespace = st.text_input(
            "Namespace",
            value=st.session_state.get('default_namespace', 'default'),
            help="Pinecone namespace to search in"
        )
        
        top_k = st.slider(
            "Number of Results",
            min_value=1,
            max_value=20,
            value=5,
            help="How many results to return"
        )
        
        if st.button("🔍 Search", use_container_width=True):
            if not search_query:
                st.error("Please enter a search query")
            elif not st.session_state.get('pinecone_api_key'):
                st.error("Pinecone API key required")
            else:
                with st.spinner("Searching..."):
                    try:
                        from utils.embedder import create_embeddings, get_embedding_dimension
                        from utils.pinecone_uploader import initialize_pinecone
                        from llama_index.core.schema import TextNode
                        
                        config = {
                            'pinecone_api_key': st.session_state.pinecone_api_key,
                            'openai_api_key': st.session_state.get('openai_api_key'),
                            'embedding_model': st.session_state.get('embedding_model'),
                            'embedding_dimension': st.session_state.get('embedding_dimension', 1536),
                            'index_name': st.session_state.get('index_name')
                        }
                        
                        index = initialize_pinecone(config)
                        
                        query_node = TextNode(text=search_query)
                        query_embedding = create_embeddings([query_node], config)[0]
                        
                        results = index.query(
                            vector=query_embedding,
                            top_k=top_k,
                            namespace=search_namespace,
                            include_metadata=True
                        )
                        
                        st.session_state.search_results = results
                        st.success(f"Found {len(results.matches)} results")
                        
                    except Exception as e:
                        st.error(f"Search error: {str(e)}")
                        st.exception(e)
    
    with col2:
        st.subheader("Search Results")
        
        if 'search_results' in st.session_state:
            results = st.session_state.search_results
            
            if results.matches:
                for idx, match in enumerate(results.matches):
                    with st.expander(f"Result {idx + 1} - Score: {match.score:.4f}", expanded=(idx==0)):
                        st.markdown(f"**ID:** `{match.id}`")
                        st.markdown(f"**Score:** {match.score:.4f}")
                        
                        if match.metadata:
                            st.markdown("**Text:**")
                            st.text_area(
                                "Chunk content",
                                match.metadata.get('text', 'No text available'),
                                height=200,
                                key=f"result_{idx}"
                            )
                            
                            st.markdown("**Metadata:**")
                            metadata_display = {k: v for k, v in match.metadata.items() if k != 'text'}
                            st.json(metadata_display)
            else:
                st.warning("No results found")
        else:
            st.info("Enter a query and click Search to see results")

st.markdown("---")
st.caption("PDF Chunking & Embedding Pipeline v1.0 | Powered by LlamaParse, LlamaIndex, and Pinecone")

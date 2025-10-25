import streamlit as st
import os
from dotenv import load_dotenv
import pandas as pd
from typing import List, Dict, Optional
import io
import json

load_dotenv()

os.environ['HF_HOME'] = '/tmp/.huggingface'
os.environ['TRANSFORMERS_CACHE'] = '/tmp/.huggingface/transformers'
os.environ['SENTENCE_TRANSFORMERS_HOME'] = '/tmp/.huggingface/sentence-transformers'

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

# Initialize database tables
from utils.database import init_products_table

try:
    init_products_table()
except Exception as e:
    st.error(f"Products table initialization: {str(e)}")

# Sidebar Navigation
st.sidebar.title("📑 Navigation")
selected_page = st.sidebar.radio(
    "Select a page:",
    [
        "🔑 Configuration",
        "🏢 Products",
        "📚 Data Sources",
        "📁 Select Files", 
        "👁️ Preview Chunks",
        "🚀 Process & Upload",
        "📊 Status",
        "📜 History",
        "🔍 Search Test"
    ],
    label_visibility="collapsed"
)

st.sidebar.markdown("---")
st.sidebar.markdown("### 📊 Quick Stats")
from utils.database import get_products, get_data_sources
products = get_products(active_only=True)
data_sources = get_data_sources()
st.sidebar.metric("Active Products", len(products))
st.sidebar.metric("Data Sources", len(data_sources))

# Page Content
if selected_page == "🔑 Configuration":
    st.header("🏢 Product-Based Configuration")
    
    st.info("""
    **This application uses product-specific credentials for complete isolation between your startups.**
    
    All API keys and credentials are managed through the **Products** tab (next tab).
    """)
    
    st.markdown("### How It Works")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**1️⃣ Create Products**")
        st.markdown("Go to the **Products** tab to create entries for each of your startups/products.")
        
        st.markdown("**2️⃣ Set API Keys in Replit Secrets**")
        st.markdown("""
        For each product, configure secrets in Replit:
        - LlamaParse API key
        - OpenAI API key (if using OpenAI embeddings)
        - Pinecone API key
        - Google Service Account JSON (as a string)
        """)
    
    with col2:
        st.markdown("**3️⃣ Assign Products to Data Sources**")
        st.markdown("When creating a data source, select which product it belongs to.")
        
        st.markdown("**4️⃣ Automatic Routing**")
        st.markdown("""
        The pipeline automatically uses the correct credentials:
        - Product-specific API keys
        - Product-specific Pinecone index
        - Product-specific Google credentials
        """)
    
    st.markdown("---")
    
    st.markdown("### 📋 Quick Setup Checklist")
    
    from utils.database import get_products
    products = get_products(active_only=True)
    
    if not products:
        st.warning("⚠️ No products configured yet. Go to the **Products** tab to create your first product.")
    else:
        st.success(f"✅ {len(products)} active product(s) configured")
        
        st.markdown("**Your Products:**")
        for product in products:
            st.markdown(f"- **{product['name']}** → Index: `{product['pinecone_index']}`")
    
    st.markdown("---")
    
    st.markdown("### 🔐 Secret Management Example")
    
    with st.expander("Click to see example setup"):
        st.code("""
# Example for "Startup A" product

Replit Secrets to configure:
┌─────────────────────────────────────────────────────────────────┐
│ Secret Name: STARTUP_A_LLAMAPARSE_KEY                          │
│ Secret Value: llx-abc123xyz...                                 │
├─────────────────────────────────────────────────────────────────┤
│ Secret Name: STARTUP_A_OPENAI_KEY                              │
│ Secret Value: sk-proj-def456...                                │
├─────────────────────────────────────────────────────────────────┤
│ Secret Name: STARTUP_A_PINECONE_KEY                            │
│ Secret Value: pcsk-ghi789...                                   │
├─────────────────────────────────────────────────────────────────┤
│ Secret Name: STARTUP_A_GOOGLE_CREDS                            │
│ Secret Value: {"type": "service_account", "project_id": ...}   │
└─────────────────────────────────────────────────────────────────┘

Then in the Products tab:
- LlamaParse Secret Name: STARTUP_A_LLAMAPARSE_KEY
- OpenAI Secret Name: STARTUP_A_OPENAI_KEY
- Pinecone Secret Name: STARTUP_A_PINECONE_KEY
- Google Credentials Secret Name: STARTUP_A_GOOGLE_CREDS
        """, language="text")

elif selected_page == "🏢 Products":
    st.header("Product Management")
    st.markdown("Manage products/startups with separate Pinecone indexes and API keys")
    
    from utils.database import (
        get_products, create_product, update_product, delete_product, get_product
    )
    
    subtab1, subtab2 = st.tabs(["📋 View Products", "➕ Add/Edit Product"])
    
    with subtab1:
        st.subheader("Existing Products")
        
        if st.button("🔄 Refresh Products"):
            st.session_state.products = get_products()
        
        if 'products' not in st.session_state:
            st.session_state.products = get_products()
        
        products = st.session_state.products
        
        if products:
            for product in products:
                status_icon = "✅" if product['active'] else "❌"
                with st.expander(f"{status_icon} {product['name']}"):
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.markdown(f"**Description:** {product.get('description', 'N/A')}")
                        st.markdown(f"**Pinecone Index:** `{product['pinecone_index']}`")
                        st.markdown(f"**Status:** {'Active' if product['active'] else 'Inactive'}")
                    
                    with col2:
                        st.markdown(f"**LlamaParse Secret:** `{product.get('llamaparse_api_key_secret', 'Not set')}`")
                        st.markdown(f"**OpenAI Secret:** `{product.get('openai_api_key_secret', 'Not set')}`")
                        st.markdown(f"**Pinecone Secret:** `{product.get('pinecone_api_key_secret', 'Not set')}`")
                        st.markdown(f"**Google Credentials Secret:** `{product.get('google_credentials_secret', 'Not set')}`")
                    
                    st.markdown("**Processing Settings:**")
                    
                    settings_col1, settings_col2 = st.columns(2)
                    with settings_col1:
                        st.markdown("*Parsing:*")
                        st.markdown(f"- Mode: {product.get('parsing_mode', 'auto')}")
                        st.markdown(f"- Result Type: {product.get('result_type', 'markdown')}")
                        st.markdown(f"- Language: {product.get('language', 'en')}")
                        st.markdown(f"- Multimodal: {product.get('use_vendor_multimodal', True)}")
                        
                        st.markdown("*Chunking:*")
                        st.markdown(f"- Strategy: {product.get('default_chunking_strategy', 'N/A')}")
                        st.markdown(f"- Size: {product.get('default_chunk_size', 'N/A')}")
                        st.markdown(f"- Overlap: {product.get('chunk_overlap', 200)}")
                        st.markdown(f"- Semantic Buffer: {product.get('semantic_buffer_size', 1)}")
                    
                    with settings_col2:
                        st.markdown("*Embedding:*")
                        st.markdown(f"- Model: {product.get('default_embedding_model', 'N/A')}")
                        
                        st.markdown("*Pinecone:*")
                        st.markdown(f"- Environment: {product.get('pinecone_environment', 'us-east-1')}")
                        st.markdown(f"- Namespace: {product.get('default_namespace', 'default')}")
                    
                    col_edit, col_delete, col_toggle = st.columns(3)
                    with col_edit:
                        if st.button(f"✏️ Edit", key=f"edit_product_{product['id']}"):
                            st.session_state.edit_product_id = product['id']
                            st.rerun()
                    with col_delete:
                        if st.button(f"🗑️ Delete", key=f"delete_product_{product['id']}"):
                            delete_product(product['id'])
                            st.session_state.products = get_products()
                            st.success(f"Deleted product: {product['name']}")
                            st.rerun()
                    with col_toggle:
                        new_status = not product['active']
                        if st.button(f"{'Activate' if not product['active'] else 'Deactivate'}", key=f"toggle_product_{product['id']}"):
                            update_product(product['id'], active=new_status)
                            st.session_state.products = get_products()
                            st.rerun()
        else:
            st.info("No products configured yet. Create one in the 'Add/Edit Product' tab.")
    
    with subtab2:
        st.subheader("Add or Edit Product")
        
        edit_mode = 'edit_product_id' in st.session_state
        product_to_edit = None
        
        if edit_mode:
            product_to_edit = get_product(st.session_state.edit_product_id)
            if product_to_edit:
                st.info(f"Editing: {product_to_edit['name']}")
        
        product_name = st.text_input(
            "Product/Startup Name",
            value=product_to_edit['name'] if edit_mode else "",
            help="e.g., 'Startup A', 'Research Project B'"
        )
        
        product_description = st.text_area(
            "Description",
            value=product_to_edit.get('description', '') if edit_mode else "",
            help="Brief description of this product/startup"
        )
        
        st.markdown("### Pinecone Configuration")
        pinecone_index = st.text_input(
            "Pinecone Index Name",
            value=product_to_edit['pinecone_index'] if edit_mode else "",
            help="The Pinecone index where vectors for this product will be stored"
        )
        
        st.markdown("### API Key Secrets")
        st.info("💡 Set these secret names in Replit Secrets. The app will read the actual keys from environment variables.")
        
        llamaparse_secret = st.text_input(
            "LlamaParse API Key Secret Name",
            value=product_to_edit.get('llamaparse_api_key_secret', '') if edit_mode else "",
            placeholder="e.g., PRODUCT_A_LLAMAPARSE_KEY",
            help="Name of the Replit secret containing the LlamaParse API key"
        )
        
        openai_secret = st.text_input(
            "OpenAI API Key Secret Name",
            value=product_to_edit.get('openai_api_key_secret', '') if edit_mode else "",
            placeholder="e.g., PRODUCT_A_OPENAI_KEY",
            help="Name of the Replit secret containing the OpenAI API key (if using OpenAI embeddings)"
        )
        
        pinecone_secret = st.text_input(
            "Pinecone API Key Secret Name",
            value=product_to_edit.get('pinecone_api_key_secret', '') if edit_mode else "",
            placeholder="e.g., PRODUCT_A_PINECONE_KEY",
            help="Name of the Replit secret containing the Pinecone API key"
        )
        
        google_credentials_secret = st.text_input(
            "Google Service Account JSON Secret Name",
            value=product_to_edit.get('google_credentials_secret', '') if edit_mode else "",
            placeholder="e.g., PRODUCT_A_GOOGLE_CREDS_JSON",
            help="Name of the Replit secret containing the Google service account JSON (as a string)"
        )
        
        st.markdown("### Processing Settings")
        st.info("💡 These settings control how PDFs are parsed, chunked, and embedded for this product")
        
        with st.expander("🔍 Parsing Settings", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                parsing_mode = st.selectbox(
                    "Parsing Mode",
                    ["auto", "fast", "premium"],
                    index=["auto", "fast", "premium"].index(product_to_edit.get('parsing_mode', 'auto')) if edit_mode else 0,
                    help="LlamaParse parsing quality mode"
                )
                
                result_type = st.selectbox(
                    "Result Type",
                    ["markdown", "text"],
                    index=["markdown", "text"].index(product_to_edit.get('result_type', 'markdown')) if edit_mode else 0,
                    help="Output format from LlamaParse"
                )
            
            with col2:
                language = st.text_input(
                    "Language Code",
                    value=product_to_edit.get('language', 'en') if edit_mode else 'en',
                    help="ISO language code (e.g., 'en', 'es', 'fr')"
                )
                
                use_vendor_multimodal = st.checkbox(
                    "Use Vendor Multimodal",
                    value=product_to_edit.get('use_vendor_multimodal', True) if edit_mode else True,
                    help="Enable multimodal parsing for images/tables"
                )
            
            page_separator = st.text_input(
                "Page Separator",
                value=product_to_edit.get('page_separator', '\n---\n') if edit_mode else '\n---\n',
                help="String used to separate pages in parsed output"
            )
        
        with st.expander("✂️ Chunking Settings", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                chunking_strategy = st.selectbox(
                    "Chunking Strategy",
                    ["Token-based", "Sentence-based", "Semantic"],
                    index=["Token-based", "Sentence-based", "Semantic"].index(product_to_edit.get('default_chunking_strategy', 'Token-based')) if edit_mode else 0,
                    help="How to split text into chunks"
                )
                
                chunk_size = st.number_input(
                    "Chunk Size",
                    min_value=128,
                    max_value=4096,
                    value=product_to_edit.get('default_chunk_size', 1024) if edit_mode else 1024,
                    step=128,
                    help="Maximum size of each chunk (tokens or characters)"
                )
            
            with col2:
                chunk_overlap = st.number_input(
                    "Chunk Overlap",
                    min_value=0,
                    max_value=512,
                    value=product_to_edit.get('chunk_overlap', 200) if edit_mode else 200,
                    step=50,
                    help="Number of tokens/characters to overlap between chunks"
                )
                
                semantic_buffer_size = st.number_input(
                    "Semantic Buffer Size",
                    min_value=1,
                    max_value=5,
                    value=product_to_edit.get('semantic_buffer_size', 1) if edit_mode else 1,
                    help="Buffer size for semantic chunking (only used if strategy is Semantic)"
                )
        
        with st.expander("🧮 Embedding Settings", expanded=True):
            embedding_model = st.selectbox(
                "Embedding Model",
                ["text-embedding-3-small", "text-embedding-3-large"],
                index=["text-embedding-3-small", "text-embedding-3-large"].index(product_to_edit.get('default_embedding_model', 'text-embedding-3-small')) if edit_mode and product_to_edit.get('default_embedding_model') in ["text-embedding-3-small", "text-embedding-3-large"] else 0,
                help="OpenAI embedding model to use"
            )
        
        with st.expander("📍 Pinecone Settings", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                pinecone_environment = st.text_input(
                    "Pinecone Environment",
                    value=product_to_edit.get('pinecone_environment', 'us-east-1') if edit_mode else 'us-east-1',
                    help="Pinecone serverless region (e.g., 'us-east-1')"
                )
            
            with col2:
                default_namespace = st.text_input(
                    "Default Namespace",
                    value=product_to_edit.get('default_namespace', 'default') if edit_mode else 'default',
                    help="Default namespace for vectors in Pinecone"
                )
        
        col_save, col_cancel = st.columns(2)
        
        with col_save:
            if st.button("💾 Save Product", type="primary", use_container_width=True):
                try:
                    if not product_name or not pinecone_index:
                        st.error("Product name and Pinecone index are required")
                    else:
                        if edit_mode:
                            update_product(
                                st.session_state.edit_product_id,
                                name=product_name,
                                description=product_description,
                                pinecone_index=pinecone_index,
                                llamaparse_secret=llamaparse_secret,
                                openai_secret=openai_secret,
                                pinecone_secret=pinecone_secret,
                                google_credentials_secret=google_credentials_secret,
                                chunking_strategy=chunking_strategy,
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                                embedding_model=embedding_model,
                                parsing_mode=parsing_mode,
                                result_type=result_type,
                                language=language,
                                use_vendor_multimodal=use_vendor_multimodal,
                                page_separator=page_separator,
                                semantic_buffer_size=semantic_buffer_size,
                                pinecone_environment=pinecone_environment,
                                default_namespace=default_namespace
                            )
                        else:
                            create_product(
                                name=product_name,
                                description=product_description,
                                pinecone_index=pinecone_index,
                                llamaparse_secret=llamaparse_secret,
                                openai_secret=openai_secret,
                                pinecone_secret=pinecone_secret,
                                google_credentials_secret=google_credentials_secret,
                                chunking_strategy=chunking_strategy,
                                chunk_size=chunk_size,
                                chunk_overlap=chunk_overlap,
                                embedding_model=embedding_model,
                                parsing_mode=parsing_mode,
                                result_type=result_type,
                                language=language,
                                use_vendor_multimodal=use_vendor_multimodal,
                                page_separator=page_separator,
                                semantic_buffer_size=semantic_buffer_size,
                                pinecone_environment=pinecone_environment,
                                default_namespace=default_namespace
                            )
                        
                        st.success(f"✅ {'Updated' if edit_mode else 'Created'} product: {product_name}")
                        
                        if 'edit_product_id' in st.session_state:
                            del st.session_state.edit_product_id
                        
                        st.session_state.products = get_products()
                        st.rerun()
                        
                except Exception as e:
                    st.error(f"Error saving product: {str(e)}")
        
        with col_cancel:
            if st.button("Cancel", use_container_width=True):
                if 'edit_product_id' in st.session_state:
                    del st.session_state.edit_product_id
                st.rerun()

elif selected_page == "📚 Data Sources":
    st.header("Data Sources Management")
    st.markdown("Manage Google Sheet data sources for different paper topics")
    
    from utils.database import (
        get_data_sources, create_data_source, update_data_source, 
        delete_data_source, get_column_mappings, save_column_mapping,
        delete_column_mapping, get_all_scheduled_jobs, create_scheduled_job,
        update_scheduled_job_status, delete_scheduled_job, get_scheduled_job_runs
    )
    from utils.google_sheets import load_sheet_data
    from datetime import datetime, timedelta
    
    subtab1, subtab2, subtab3 = st.tabs(["📋 View Sources", "➕ Add/Edit Source", "⏰ Scheduling"])
    
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
        
        # Product selection
        products = get_products(active_only=True)
        if not products:
            st.warning("⚠️ No active products found. Please create a product first in the Products tab.")
            st.stop()
        
        selected_product_id = st.selectbox(
            "Select Product",
            options=[p['id'] for p in products],
            format_func=lambda x: next((p['name'] for p in products if p['id'] == x), str(x)),
            index=next((i for i, p in enumerate(products) if p['id'] == editing_source.get('product_id')), 0) if (edit_mode and editing_source) else 0,
            help="Which product/startup this data source belongs to"
        )
        
        st.markdown("---")
        
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
                                default_namespace=source_namespace,
                                product_id=selected_product_id
                            )
                            source_id = st.session_state.edit_source_id
                        else:
                            source_id = create_data_source(
                                source_name, source_url, source_tab,
                                source_topic, source_namespace,
                                product_id=selected_product_id
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
    
    with subtab3:
        st.subheader("Scheduled Processing")
        st.markdown("Configure automatic periodic processing for each data source")
        
        if 'data_sources' not in st.session_state:
            st.session_state.data_sources = get_data_sources()
        
        sources = st.session_state.data_sources
        
        if not sources:
            st.info("No data sources available. Create a data source first.")
        else:
            source_selector = st.selectbox(
                "Select Data Source to Schedule",
                options=[s['id'] for s in sources],
                format_func=lambda x: next((f"{s['name']} - {s.get('topic', 'No topic')}" for s in sources if s['id'] == x), str(x))
            )
            
            if source_selector:
                selected_source = next((s for s in sources if s['id'] == source_selector), None)
                existing_schedule = get_scheduled_job(source_selector)
                
                st.markdown("---")
                
                col1, col2 = st.columns([2, 1])
                
                with col1:
                    st.markdown(f"**Scheduling for:** {selected_source['name']}")
                    
                    schedule_enabled = st.checkbox(
                        "Enable Scheduled Processing",
                        value=existing_schedule['enabled'] if existing_schedule else False,
                        key=f"schedule_enabled_{source_selector}"
                    )
                    
                    job_name = st.text_input(
                        "Job Name",
                        value=existing_schedule['job_name'] if existing_schedule else f"Auto-process {selected_source['name']}",
                        help="Descriptive name for this scheduled job"
                    )
                    
                    schedule_type = st.selectbox(
                        "Schedule Type",
                        ["hourly", "daily", "weekly", "interval"],
                        index=["hourly", "daily", "weekly", "interval"].index(existing_schedule['schedule_type']) if existing_schedule else 1
                    )
                    
                    schedule_config = existing_schedule.get('schedule_config', {}) if existing_schedule else {}
                    
                    if schedule_type == "daily":
                        hour = st.number_input(
                            "Hour (0-23)",
                            min_value=0,
                            max_value=23,
                            value=schedule_config.get('hour', 0)
                        )
                        schedule_config['hour'] = hour
                    
                    elif schedule_type == "weekly":
                        day_of_week = st.selectbox(
                            "Day of Week",
                            options=[0, 1, 2, 3, 4, 5, 6],
                            format_func=lambda x: ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][x],
                            index=schedule_config.get('day_of_week', 0)
                        )
                        hour = st.number_input(
                            "Hour (0-23)",
                            min_value=0,
                            max_value=23,
                            value=schedule_config.get('hour', 0)
                        )
                        schedule_config['day_of_week'] = day_of_week
                        schedule_config['hour'] = hour
                    
                    elif schedule_type == "interval":
                        interval_hours = st.number_input(
                            "Interval (hours)",
                            min_value=1,
                            max_value=168,
                            value=schedule_config.get('interval_hours', 24)
                        )
                        schedule_config['interval_hours'] = interval_hours
                    
                    max_papers = st.number_input(
                        "Max Papers per Run",
                        min_value=1,
                        max_value=500,
                        value=schedule_config.get('max_papers_per_run', 100),
                        help="Maximum number of new papers to process in each scheduled run"
                    )
                    schedule_config['max_papers_per_run'] = max_papers
                    
                    if st.button("💾 Save Schedule Configuration", type="primary"):
                        try:
                            schedule_config['chunking_strategy'] = 'Token-based'
                            schedule_config['chunk_size'] = 512
                            schedule_config['embedding_model'] = 'text-embedding-3-small'
                            schedule_config['index_name'] = 'pdf-embeddings'
                            
                            job_id = create_scheduled_job(
                                source_id=source_selector,
                                job_name=job_name,
                                schedule_type=schedule_type,
                                schedule_config=schedule_config
                            )
                            
                            from scheduler import calculate_next_run
                            next_run = calculate_next_run(schedule_type, schedule_config, datetime.now())
                            
                            from utils.database import update_scheduled_job_run_time
                            update_scheduled_job_run_time(job_id, next_run)
                            
                            if existing_schedule and existing_schedule['enabled'] != schedule_enabled:
                                update_scheduled_job_status(job_id, schedule_enabled)
                            
                            st.success(f"✅ Schedule saved! Next run: {next_run}")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error saving schedule: {str(e)}")
                
                with col2:
                    if existing_schedule:
                        st.markdown("**Schedule Status**")
                        st.info(f"**Enabled:** {'Yes' if existing_schedule['enabled'] else 'No'}")
                        st.info(f"**Type:** {existing_schedule['schedule_type']}")
                        st.info(f"**Last Run:** {existing_schedule.get('last_run_at', 'Never')}")
                        st.info(f"**Next Run:** {existing_schedule.get('next_run_at', 'Not scheduled')}")
                        st.info(f"**Total Runs:** {existing_schedule.get('total_runs', 0)}")
                        st.info(f"**Successful:** {existing_schedule.get('successful_runs', 0)}")
                        st.info(f"**Failed:** {existing_schedule.get('failed_runs', 0)}")
                        
                        if st.button("🗑️ Delete Schedule"):
                            delete_scheduled_job(existing_schedule['id'])
                            st.success("Schedule deleted")
                            st.rerun()
                    else:
                        st.info("No schedule configured for this source")
                
                if existing_schedule:
                    st.markdown("---")
                    st.subheader("Run History")
                    
                    runs = get_scheduled_job_runs(existing_schedule['id'], limit=10)
                    
                    if runs:
                        runs_df = pd.DataFrame([{
                            'Started': r['run_started_at'],
                            'Status': r['status'],
                            'Found': r['papers_found'],
                            'Processed': r['papers_processed'],
                            'Duplicates': r['papers_skipped_duplicate'],
                            'Failed': r['papers_failed']
                        } for r in runs])
                        st.dataframe(runs_df, use_container_width=True)
                    else:
                        st.info("No runs yet")

elif selected_page == "📁 Select Files":
    st.header("Select Files to Process")
    st.markdown("Choose which data sources and papers to process")
    
    from utils.database import get_data_sources, get_column_mapping_dict
    from utils.google_sheets import load_sheet_data
    
    if 'data_sources' not in st.session_state:
        st.session_state.data_sources = get_data_sources(active_only=True)
    
    active_sources = [s for s in st.session_state.data_sources if s.get('active', False)]
    
    if not active_sources:
        st.warning("⚠️ No active data sources found. Please add and activate data sources in the 'Data Sources' tab.")
    else:
        st.subheader("Select Data Sources")
        
        source_selection_mode = st.radio(
            "Selection Mode",
            ["Select Specific Sources", "Process All Active Sources"],
            horizontal=True
        )
        
        if source_selection_mode == "Select Specific Sources":
            selected_source_ids = st.multiselect(
                "Choose data sources to process",
                options=[s['id'] for s in active_sources],
                format_func=lambda x: next((s['name'] for s in active_sources if s['id'] == x), str(x)),
                default=[]
            )
        else:
            selected_source_ids = [s['id'] for s in active_sources]
            st.info(f"Will process all {len(selected_source_ids)} active source(s)")
        
        st.session_state.selected_source_ids = selected_source_ids
        
        if selected_source_ids:
            st.markdown("---")
            st.subheader("Load and Preview Papers")
            
            for source_id in selected_source_ids:
                source = next((s for s in active_sources if s['id'] == source_id), None)
                if not source:
                    continue
                
                with st.expander(f"📚 {source['name']} - {source.get('topic', 'No topic')}", expanded=True):
                    col1, col2 = st.columns([3, 1])
                    
                    with col1:
                        st.markdown(f"**Sheet:** {source['sheet_url'][:60]}...")
                        st.markdown(f"**Tab:** {source['sheet_tab']}")
                        st.markdown(f"**Namespace:** {source['default_namespace']}")
                    
                    with col2:
                        if st.button(f"📥 Load", key=f"load_{source_id}"):
                            if st.session_state.get('google_credentials'):
                                with st.spinner(f"Loading {source['name']}..."):
                                    try:
                                        df = load_sheet_data(
                                            source['sheet_url'],
                                            source['sheet_tab'],
                                            st.session_state.get('google_credentials')
                                        )
                                        
                                        if f'source_data_{source_id}' not in st.session_state:
                                            st.session_state[f'source_data_{source_id}'] = {}
                                        
                                        st.session_state[f'source_data_{source_id}']['data'] = df
                                        st.session_state[f'source_data_{source_id}']['mappings'] = get_column_mapping_dict(source_id)
                                        st.success(f"✅ Loaded {len(df)} rows")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Error: {str(e)}")
                            else:
                                st.error("Upload Google credentials first")
                    
                    source_data_key = f'source_data_{source_id}'
                    if source_data_key in st.session_state:
                        data_info = st.session_state[source_data_key]
                        df = data_info['data']
                        mappings = data_info['mappings']
                        
                        st.dataframe(df.head(3), use_container_width=True)
                        st.caption(f"Showing 3 of {len(df)} rows")
                        
                        drive_link_col = mappings.get('drive_link', 'Drive Link')
                        
                        if drive_link_col in df.columns:
                            pdf_rows = df[df[drive_link_col].notna()]
                            
                            selection_mode = st.radio(
                                "Paper Selection",
                                ["Select Specific Papers", "Process All Papers", "Process New Only"],
                                key=f"mode_{source_id}",
                                horizontal=True
                            )
                            
                            if selection_mode == "Select Specific Papers":
                                title_col = mappings.get('paper_title', 'Title')
                                
                                selected_indices = st.multiselect(
                                    "Choose papers",
                                    options=list(range(len(pdf_rows))),
                                    format_func=lambda x: f"Row {x+1}: {pdf_rows.iloc[x].get(title_col, pdf_rows.iloc[x][drive_link_col][:40]) if title_col in pdf_rows.columns else pdf_rows.iloc[x][drive_link_col][:40]}",
                                    default=[],
                                    key=f"papers_{source_id}"
                                )
                                st.session_state[f'selected_indices_{source_id}'] = selected_indices
                                
                            elif selection_mode == "Process All Papers":
                                st.session_state[f'selected_indices_{source_id}'] = list(range(len(pdf_rows)))
                                st.info(f"Will process all {len(pdf_rows)} papers")
                                
                            elif selection_mode == "Process New Only":
                                last_processed = source.get('last_processed_row', 0)
                                new_indices = list(range(last_processed, len(pdf_rows)))
                                st.session_state[f'selected_indices_{source_id}'] = new_indices
                                st.info(f"Will process {len(new_indices)} new papers (rows {last_processed + 1} onwards)")
                            
                            selected = st.session_state.get(f'selected_indices_{source_id}', [])
                            st.success(f"📌 Selected {len(selected)} paper(s) from this source")
                        else:
                            st.error(f"Drive link column '{drive_link_col}' not found")
                    else:
                        st.info("Click 'Load' to fetch papers from this source")

elif selected_page == "👁️ Preview Chunks":
    st.header("Preview Chunks")
    st.markdown("Preview how your papers will be chunked before uploading to Pinecone")
    
    selected_source_ids = st.session_state.get('selected_source_ids', [])
    
    if not selected_source_ids:
        st.warning("⚠️ Please select data sources in the 'Select Files' tab first")
    else:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Preview Settings")
            
            preview_limit = st.number_input(
                "Papers per Source",
                min_value=1,
                max_value=5,
                value=1,
                help="How many papers to preview from each selected source"
            )
            
            if st.button("🔍 Generate Preview", use_container_width=True):
                from utils.multi_source_pipeline import process_multi_source_pipeline
                
                source_configs = []
                for source_id in selected_source_ids:
                    source_data_key = f'source_data_{source_id}'
                    if source_data_key in st.session_state:
                        data_info = st.session_state[source_data_key]
                        selected_indices_key = f'selected_indices_{source_id}'
                        indices = st.session_state.get(selected_indices_key, [])[:preview_limit]
                        
                        if indices:
                            source_configs.append({
                                'source_id': source_id,
                                'data': data_info['data'],
                                'selected_indices': indices
                            })
                
                if not source_configs:
                    st.error("❌ No papers selected for preview")
                elif not st.session_state.get('llama_api_key'):
                    st.error("❌ LlamaParse API key required")
                else:
                    with st.spinner("Generating preview..."):
                        try:
                            results = process_multi_source_pipeline(
                                source_configs=source_configs,
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
                                    'embedding_model': st.session_state.get('embedding_model')
                                },
                                preview_mode=True
                            )
                            
                            st.session_state.preview_results = results
                            st.success(f"✅ Preview: {results['total_pdfs']} papers, {results['total_chunks']} chunks")
                            
                        except Exception as e:
                            st.error(f"❌ Error: {str(e)}")
                            st.exception(e)
        
        with col2:
            st.subheader("Chunk Preview")
            
            if 'preview_results' in st.session_state:
                results = st.session_state.preview_results
                chunks = results.get('preview_chunks', [])
                
                if chunks:
                    st.info(f"📊 {len(chunks)} chunks from {results['total_pdfs']} papers")
                    
                    chunk_idx = st.number_input(
                        "Chunk to view",
                        min_value=0,
                        max_value=len(chunks)-1,
                        value=0,
                        key="preview_chunk_idx"
                    )
                    
                    chunk = chunks[chunk_idx]
                    
                    st.markdown(f"**Chunk {chunk_idx + 1} of {len(chunks)}**")
                    st.markdown(f"**Source:** {chunk['metadata'].get('source', 'Unknown')}")
                    st.markdown(f"**Namespace:** `{chunk['namespace']}`")
                    
                    with st.expander("📝 Chunk Text", expanded=True):
                        st.text_area(
                            "Content",
                            chunk['text'],
                            height=300,
                            key=f"preview_chunk_{chunk_idx}"
                        )
                    
                    with st.expander("🏷️ Metadata", expanded=False):
                        st.json(chunk['metadata'])
                else:
                    st.warning("No chunks generated")
            else:
                st.info("Click 'Generate Preview' to see chunks")

elif selected_page == "🚀 Process & Upload":
    st.header("Process & Upload to Pinecone")
    
    selected_source_ids = st.session_state.get('selected_source_ids', [])
    
    total_selected = 0
    total_sources = len(selected_source_ids)
    
    for source_id in selected_source_ids:
        indices = st.session_state.get(f'selected_indices_{source_id}', [])
        total_selected += len(indices)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Data Sources", total_sources)
    with col2:
        st.metric("Papers Selected", total_selected)
    with col3:
        st.metric("Ready to Process", "✅" if total_selected > 0 else "❌")
    
    st.markdown("---")
    
    if st.button("🚀 Start Processing Pipeline", type="primary", use_container_width=True):
        from utils.multi_source_pipeline import process_multi_source_pipeline
        
        source_configs = []
        for source_id in selected_source_ids:
            source_data_key = f'source_data_{source_id}'
            if source_data_key in st.session_state:
                data_info = st.session_state[source_data_key]
                selected_indices = st.session_state.get(f'selected_indices_{source_id}', [])
                
                if selected_indices:
                    source_configs.append({
                        'source_id': source_id,
                        'data': data_info['data'],
                        'selected_indices': selected_indices
                    })
        
        if not source_configs:
            st.error("❌ Please select papers to process")
        elif not st.session_state.get('llama_api_key'):
            st.error("❌ LlamaParse API key required")
        elif not st.session_state.get('pinecone_api_key'):
            st.error("❌ Pinecone API key required")
        else:
            st.session_state.processing_state = "running"
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                results = process_multi_source_pipeline(
                    source_configs=source_configs,
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
                        'index_name': st.session_state.get('index_name')
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

elif selected_page == "📊 Status":
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

elif selected_page == "📜 History":
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

elif selected_page == "🔍 Search Test":
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

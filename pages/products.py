"""
Products page - Manage products/startups with separate Pinecone indexes and API keys.
"""
import streamlit as st
from components.common import page_header, refresh_button, success_message, error_message, info_box
from utils.database import get_products, create_product, update_product, delete_product, get_product
from utils.tagger import DEFAULT_TAGGING_PROMPT
from config.constants import (
    PARSING_MODES, RESULT_TYPES, CHUNKING_STRATEGIES, EMBEDDING_MODELS,
    TAGGING_MODELS, DEFAULT_PARSING_MODE, DEFAULT_RESULT_TYPE, DEFAULT_LANGUAGE,
    DEFAULT_PAGE_SEPARATOR, DEFAULT_USE_MULTIMODAL, DEFAULT_CHUNK_STRATEGY,
    DEFAULT_CHUNK_SIZE, DEFAULT_CHUNK_OVERLAP, DEFAULT_SEMANTIC_BUFFER,
    DEFAULT_PINECONE_ENV, DEFAULT_NAMESPACE, DEFAULT_TAGGING_MODEL,
    EMBEDDING_DIMENSIONS, MIN_CHUNK_SIZE, MAX_CHUNK_SIZE, MIN_CHUNK_OVERLAP,
    MAX_CHUNK_OVERLAP, MIN_SEMANTIC_BUFFER, MAX_SEMANTIC_BUFFER, MIN_EMBEDDING_DIMENSION,
    MSG_PRODUCT_CREATED, MSG_PRODUCT_UPDATED, MSG_PRODUCT_DELETED, MSG_MISSING_REQUIRED,
    MSG_NO_PRODUCTS
)


def render():
    """Render the Products page."""
    page_header("Product Management", "Manage products/startups with separate Pinecone indexes and API keys")
    
    subtab1, subtab2 = st.tabs(["📋 View Products", "➕ Add/Edit Product"])
    
    with subtab1:
        _render_view_products()
    
    with subtab2:
        _render_add_edit_product()


def _render_view_products():
    """Render the view products tab."""
    st.subheader("Existing Products")
    
    if refresh_button("refresh_products"):
        st.session_state.products = get_products()
    
    if 'products' not in st.session_state:
        st.session_state.products = get_products()
    
    products = st.session_state.products
    
    if products:
        for product in products:
            _render_product_card(product)
    else:
        st.info(MSG_NO_PRODUCTS)


def _render_product_card(product: dict):
    """Render a single product card with all details."""
    status_icon = "✅" if product['active'] else "❌"
    
    with st.expander(f"{status_icon} {product['name']}"):
        # Basic info
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
        
        # Processing settings
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
        
        # Action buttons
        col_edit, col_delete, col_toggle = st.columns(3)
        with col_edit:
            if st.button(f"✏️ Edit", key=f"edit_product_{product['id']}"):
                st.session_state.edit_product_id = product['id']
                st.rerun()
        with col_delete:
            if st.button(f"🗑️ Delete", key=f"delete_product_{product['id']}"):
                delete_product(product['id'])
                st.session_state.products = get_products()
                if 'edit_product_id' in st.session_state:
                    del st.session_state.edit_product_id
                success_message(MSG_PRODUCT_DELETED.format(product['name']))
                st.rerun()
        with col_toggle:
            new_status = not product['active']
            if st.button(f"{'Activate' if not product['active'] else 'Deactivate'}", key=f"toggle_product_{product['id']}"):
                update_product(product['id'], active=new_status)
                st.session_state.products = get_products()
                st.rerun()


def _render_add_edit_product():
    """Render the add/edit product form."""
    st.subheader("Add or Edit Product")
    
    edit_mode = 'edit_product_id' in st.session_state
    product_to_edit = None
    
    if edit_mode:
        product_to_edit = get_product(st.session_state.edit_product_id)
        if product_to_edit:
            info_box(f"Editing: {product_to_edit['name']}")
        else:
            error_message("Product not found. It may have been deleted.")
            del st.session_state.edit_product_id
            edit_mode = False
    
    # Basic info
    product_name = st.text_input(
        "Product/Startup Name",
        value=product_to_edit['name'] if (edit_mode and product_to_edit) else "",
        help="e.g., 'Startup A', 'Research Project B'"
    )
    
    product_description = st.text_area(
        "Description",
        value=product_to_edit.get('description', '') if product_to_edit else "",
        help="Brief description of this product/startup"
    )
    
    # Pinecone config
    st.markdown("### Pinecone Configuration")
    pinecone_index = st.text_input(
        "Pinecone Index Name",
        value=product_to_edit['pinecone_index'] if product_to_edit else "",
        help="The Pinecone index where vectors for this product will be stored"
    )
    
    # API key secrets
    st.markdown("### API Key Secrets")
    info_box("Set these secret names in Replit Secrets. The app will read the actual keys from environment variables.")
    
    llamaparse_secret = st.text_input(
        "LlamaParse API Key Secret Name",
        value=product_to_edit.get('llamaparse_api_key_secret', '') if product_to_edit else "",
        placeholder="e.g., PRODUCT_A_LLAMAPARSE_KEY"
    )
    
    openai_secret = st.text_input(
        "OpenAI API Key Secret Name",
        value=product_to_edit.get('openai_api_key_secret', '') if product_to_edit else "",
        placeholder="e.g., PRODUCT_A_OPENAI_KEY"
    )
    
    pinecone_secret = st.text_input(
        "Pinecone API Key Secret Name",
        value=product_to_edit.get('pinecone_api_key_secret', '') if product_to_edit else "",
        placeholder="e.g., PRODUCT_A_PINECONE_KEY"
    )
    
    google_credentials_secret = st.text_input(
        "Google Service Account JSON Secret Name",
        value=product_to_edit.get('google_credentials_secret', '') if product_to_edit else "",
        placeholder="e.g., PRODUCT_A_GOOGLE_CREDS_JSON"
    )
    
    # Processing settings
    st.markdown("### Processing Settings")
    info_box("These settings control how PDFs are parsed, chunked, and embedded for this product")
    
    # Parsing settings
    with st.expander("🔍 Parsing Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            parsing_mode = st.selectbox(
                "Parsing Mode",
                PARSING_MODES,
                index=PARSING_MODES.index(product_to_edit.get('parsing_mode', DEFAULT_PARSING_MODE)) if product_to_edit else 0
            )
            
            result_type = st.selectbox(
                "Result Type",
                RESULT_TYPES,
                index=RESULT_TYPES.index(product_to_edit.get('result_type', DEFAULT_RESULT_TYPE)) if product_to_edit else 0
            )
        
        with col2:
            language = st.text_input(
                "Language Code",
                value=product_to_edit.get('language', DEFAULT_LANGUAGE) if product_to_edit else DEFAULT_LANGUAGE
            )
            
            use_vendor_multimodal = st.checkbox(
                "Use Vendor Multimodal",
                value=product_to_edit.get('use_vendor_multimodal', DEFAULT_USE_MULTIMODAL) if product_to_edit else DEFAULT_USE_MULTIMODAL
            )
        
        page_separator = st.text_input(
            "Page Separator",
            value=product_to_edit.get('page_separator', DEFAULT_PAGE_SEPARATOR) if product_to_edit else DEFAULT_PAGE_SEPARATOR
        )
    
    # Chunking settings
    with st.expander("✂️ Chunking Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            chunking_strategy = st.selectbox(
                "Chunking Strategy",
                CHUNKING_STRATEGIES,
                index=CHUNKING_STRATEGIES.index(product_to_edit.get('default_chunking_strategy', DEFAULT_CHUNK_STRATEGY)) if product_to_edit else 0
            )
            
            chunk_size = st.number_input(
                "Chunk Size",
                min_value=MIN_CHUNK_SIZE,
                max_value=MAX_CHUNK_SIZE,
                value=product_to_edit.get('default_chunk_size', DEFAULT_CHUNK_SIZE) if product_to_edit else DEFAULT_CHUNK_SIZE,
                step=128
            )
        
        with col2:
            chunk_overlap = st.number_input(
                "Chunk Overlap",
                min_value=MIN_CHUNK_OVERLAP,
                max_value=MAX_CHUNK_OVERLAP,
                value=product_to_edit.get('chunk_overlap', DEFAULT_CHUNK_OVERLAP) if product_to_edit else DEFAULT_CHUNK_OVERLAP,
                step=50
            )
            
            semantic_buffer_size = st.number_input(
                "Semantic Buffer Size",
                min_value=MIN_SEMANTIC_BUFFER,
                max_value=MAX_SEMANTIC_BUFFER,
                value=product_to_edit.get('semantic_buffer_size', DEFAULT_SEMANTIC_BUFFER) if product_to_edit else DEFAULT_SEMANTIC_BUFFER
            )
    
    # Embedding settings
    with st.expander("🧮 Embedding Settings", expanded=True):
        embedding_model = st.selectbox(
            "Embedding Model",
            EMBEDDING_MODELS,
            index=EMBEDDING_MODELS.index(product_to_edit.get('default_embedding_model', EMBEDDING_MODELS[0])) if product_to_edit and product_to_edit.get('default_embedding_model') in EMBEDDING_MODELS else 0
        )
        
        max_dimension = EMBEDDING_DIMENSIONS[embedding_model]
        current_dimension = product_to_edit.get('embedding_dimension') if product_to_edit else None
        
        use_custom_dimension = st.checkbox(
            "Use Custom Dimension",
            value=current_dimension is not None
        )
        
        embedding_dimension = None
        if use_custom_dimension:
            embedding_dimension = st.number_input(
                "Embedding Dimension",
                min_value=MIN_EMBEDDING_DIMENSION,
                max_value=max_dimension,
                value=current_dimension if current_dimension else max_dimension,
                step=64
            )
            info_box(f"Default: {max_dimension} dims. Reducing dimensions can significantly lower costs while maintaining good quality for many use cases.")
    
    # Pinecone settings
    with st.expander("📍 Pinecone Settings", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            pinecone_environment = st.text_input(
                "Pinecone Environment",
                value=product_to_edit.get('pinecone_environment', DEFAULT_PINECONE_ENV) if product_to_edit else DEFAULT_PINECONE_ENV
            )
        
        with col2:
            default_namespace = st.text_input(
                "Default Namespace",
                value=product_to_edit.get('default_namespace', DEFAULT_NAMESPACE) if product_to_edit else DEFAULT_NAMESPACE
            )
    
    # Tagging settings
    with st.expander("🏷️ AI Tagging Settings", expanded=False):
        info_box("Automatically generate relevant tags for each document using OpenAI LLM")
        
        tagging_enabled = st.checkbox(
            "Enable AI Tagging",
            value=product_to_edit.get('tagging_enabled', False) if product_to_edit else False
        )
        
        if tagging_enabled:
            tagging_model = st.selectbox(
                "Tagging Model",
                TAGGING_MODELS,
                index=TAGGING_MODELS.index(product_to_edit.get('tagging_model', DEFAULT_TAGGING_MODEL)) if (product_to_edit and product_to_edit.get('tagging_model') in TAGGING_MODELS) else 0
            )
            
            tagging_prompt = st.text_area(
                "Tagging Prompt Template",
                value=product_to_edit.get('tagging_prompt_template', '') if product_to_edit else DEFAULT_TAGGING_PROMPT,
                height=300
            )
            
            st.markdown("**Available Variables:**")
            st.markdown("- `{text}` - Parsed document text (truncated to first 8000 chars)")
            st.markdown("- `{filename}` - PDF filename")
            st.markdown("- Any metadata column names from your Google Sheets")
        else:
            tagging_model = DEFAULT_TAGGING_MODEL
            tagging_prompt = None
    
    # Save/Cancel buttons
    col_save, col_cancel = st.columns(2)
    
    with col_save:
        if st.button("💾 Save Product", type="primary", use_container_width=True):
            try:
                if not product_name or not pinecone_index:
                    error_message(MSG_MISSING_REQUIRED)
                else:
                    product_data = {
                        "name": product_name,
                        "description": product_description,
                        "pinecone_index": pinecone_index,
                        "llamaparse_secret": llamaparse_secret,
                        "openai_secret": openai_secret,
                        "pinecone_secret": pinecone_secret,
                        "google_credentials_secret": google_credentials_secret,
                        "chunking_strategy": chunking_strategy,
                        "chunk_size": chunk_size,
                        "chunk_overlap": chunk_overlap,
                        "embedding_model": embedding_model,
                        "embedding_dimension": embedding_dimension,
                        "parsing_mode": parsing_mode,
                        "result_type": result_type,
                        "language": language,
                        "use_vendor_multimodal": use_vendor_multimodal,
                        "page_separator": page_separator,
                        "semantic_buffer_size": semantic_buffer_size,
                        "pinecone_environment": pinecone_environment,
                        "default_namespace": default_namespace,
                        "tagging_enabled": tagging_enabled,
                        "tagging_model": tagging_model,
                        "tagging_prompt_template": tagging_prompt
                    }
                    
                    if edit_mode:
                        update_product(st.session_state.edit_product_id, **product_data)
                        success_message(MSG_PRODUCT_UPDATED.format(product_name))
                    else:
                        create_product(**product_data)
                        success_message(MSG_PRODUCT_CREATED.format(product_name))
                    
                    if 'edit_product_id' in st.session_state:
                        del st.session_state.edit_product_id
                    
                    st.session_state.products = get_products()
                    st.rerun()
                    
            except Exception as e:
                error_message(f"Error saving product: {str(e)}")
    
    with col_cancel:
        if st.button("Cancel", use_container_width=True):
            if 'edit_product_id' in st.session_state:
                del st.session_state.edit_product_id
            st.rerun()

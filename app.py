"""
PDF Processing Pipeline - Main Application
Streamlined refactored version with modular page architecture.
"""
import os
import streamlit as st

# Initialize Sentry for error tracking
from utils.sentry_config import init_sentry
init_sentry()

# Import configuration
from config.constants import (
    APP_TITLE, APP_ICON, APP_PASSWORD, PAGES, PAGE_ORDER
)

# Import page modules
from page_modules import home, products, data_sources, select_files, preview
from page_modules import process, job_queue, monitoring, status, history, search, metadata_management, diagnostics, admin_backfill, admin_metadata_enrichment, admin_coverage_analysis

# Import database utilities for sidebar stats and initialization
from utils.database import get_products, get_data_sources
from utils.db.products import init_products_table
from utils.db.jobs import init_celery_tables


# ============================================
# PAGE CONFIGURATION
# ============================================

st.set_page_config(
    page_title=APP_TITLE,
    page_icon=APP_ICON,
    layout="wide",
    initial_sidebar_state="expanded"
)


# ============================================
# SESSION STATE INITIALIZATION
# ============================================

def init_session_state():
    """Initialize session state variables."""
    defaults = {
        'logged_in': False,
        'processing_state': 'idle',
        'pinecone_api_key': os.getenv("ABCD_DA_PINECONE_KEY", ""),
        'openai_api_key': os.getenv("ABCD_DA_OPENAI_KEY", ""),
        'llama_api_key': os.getenv("ABCD_DA_LLAMAPARSE_KEY", ""),
        'default_namespace': 'default',
        'index_name': ''
    }
    
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()


# ============================================
# DATABASE INITIALIZATION
# ============================================

# Initialize database tables on startup
try:
    init_products_table()
    init_celery_tables()
except Exception as e:
    st.error(f"Database initialization error: {str(e)}")


# ============================================
# AUTHENTICATION
# ============================================

if not st.session_state.logged_in:
    st.title(f"{APP_ICON} {APP_TITLE}")
    st.subheader("🔐 Please log in")
    
    password = st.text_input("Enter password", type="password")
    
    if st.button("Login"):
        if password == APP_PASSWORD:
            st.session_state.logged_in = True
            st.rerun()
        else:
            st.error("Invalid password")
    
    st.stop()


# ============================================
# SIDEBAR NAVIGATION
# ============================================

st.sidebar.title(f"{APP_ICON} {APP_TITLE}")

# Logout button
if st.sidebar.button("🚪 Logout"):
    st.session_state.logged_in = False
    st.rerun()

st.sidebar.markdown("---")

# Page selection
page_labels = [PAGES[key].display_name for key in PAGE_ORDER]
selected_label = st.sidebar.radio(
    "Select a page:",
    page_labels,
    label_visibility="collapsed"
)

# Find the selected page key
selected_page_key = None
for key in PAGE_ORDER:
    if PAGES[key].display_name == selected_label:
        selected_page_key = key
        break

st.sidebar.markdown("---")

# Quick stats
st.sidebar.markdown("### 📊 Quick Stats")
try:
    product_list = get_products(active_only=True)
    source_list = get_data_sources()
    st.sidebar.metric("Active Products", len(product_list))
    st.sidebar.metric("Data Sources", len(source_list))
except Exception as e:
    st.sidebar.error(f"Error loading stats: {str(e)}")


# ============================================
# PAGE ROUTING
# ============================================

# Map page keys to their render functions
PAGE_RENDERERS = {
    "home": home.render,
    "products": products.render,
    "data_sources": data_sources.render,
    "select_files": select_files.render,
    "preview": preview.render,
    "process": process.render,
    "job_queue": job_queue.render,
    "monitoring": monitoring.render_monitoring_page,
    "metadata_management": metadata_management.render,
    "status": status.render,
    "history": history.render,
    "search": search.render,
    "diagnostics": diagnostics.render,
    "admin_backfill": admin_backfill.render,
    "admin_metadata_enrichment": admin_metadata_enrichment.render,
    "admin_coverage_analysis": admin_coverage_analysis.show
}

# Render the selected page
if selected_page_key and selected_page_key in PAGE_RENDERERS:
    try:
        PAGE_RENDERERS[selected_page_key]()
    except Exception as e:
        st.error(f"Error rendering page: {str(e)}")
        st.exception(e)
else:
    st.error(f"Page not found: {selected_page_key}")


# ============================================
# FOOTER
# ============================================

st.markdown("---")
st.caption("PDF Chunking & Embedding Pipeline v2.0 (Refactored) | Powered by LlamaParse, LlamaIndex, and Pinecone")

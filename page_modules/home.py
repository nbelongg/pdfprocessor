"""
Home/Configuration page - Explains the product-based configuration system.
"""
import streamlit as st
from components.common import page_header, info_box
from utils.database import get_products
from config.constants import SECRETS_EXAMPLE_TEMPLATE


def render():
    """Render the Home/Configuration page."""
    page_header(
        "Product-Based Configuration",
        icon="🏢"
    )
    
    info_box(
        "This application uses product-specific credentials for complete isolation between your startups. "
        "All API keys and credentials are managed through the **Products** tab (next tab)."
    )
    
    st.markdown("### How It Works")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**1️⃣ Create Products**")
        st.markdown("Go to the **Products** tab to create entries for each of your startups/products.")
        
        st.markdown("**2️⃣ Set API Keys in Replit Secrets**")
        st.markdown("""
        For each product, configure secrets in Replit:
        - LlamaParse API key
        - OpenAI API key (for embeddings and tagging)
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
    
    _render_setup_checklist()
    
    st.markdown("---")
    
    _render_secrets_example()


def _render_setup_checklist():
    """Render the setup checklist section."""
    st.markdown("### 📋 Quick Setup Checklist")
    
    products = get_products(active_only=True)
    
    if not products:
        st.warning("⚠️ No products configured yet. Go to the **Products** tab to create your first product.")
    else:
        st.success(f"✅ {len(products)} active product(s) configured")
        
        st.markdown("**Your Products:**")
        for product in products:
            st.markdown(f"- **{product['name']}** → Index: `{product['pinecone_index']}`")


def _render_secrets_example():
    """Render the secrets management example."""
    st.markdown("### 🔐 Secret Management Example")
    
    with st.expander("Click to see example setup"):
        example_name = "Startup A"
        example_text = SECRETS_EXAMPLE_TEMPLATE.format(
            product_name=example_name,
            product_name_upper=example_name.upper().replace(" ", "_")
        )
        st.code(example_text, language="text")

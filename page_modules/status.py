"""
Status page - Shows processing status and logs.
"""
import streamlit as st
from components.common import page_header


def render():
    """Render the Status page."""
    page_header("Processing Status & Logs")
    
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

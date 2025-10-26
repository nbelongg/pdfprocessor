"""
History page - View past processing jobs and their results.
"""
import streamlit as st
import pandas as pd
from components.common import page_header, refresh_button
from utils.database import get_job_history, get_job_details, get_job_chunks


def render():
    """Render the History page."""
    page_header("Processing History", "View past processing jobs and their results")
    
    if refresh_button("refresh_history"):
        st.session_state.job_history = get_job_history(50)
    
    if 'job_history' not in st.session_state:
        st.session_state.job_history = get_job_history(50)
    
    history = st.session_state.job_history
    
    if history:
        for job in history:
            _render_job_card(job)
    else:
        st.info("No processing history found")


def _render_job_card(job: dict):
    """Render a single job history card."""
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

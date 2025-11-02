"""
Metadata Management Page - Manual metadata update triggers and change detection.
"""
import streamlit as st
import pandas as pd
from utils.database import get_data_sources, get_column_mapping_dict, get_product
from utils.google_sheets import load_sheet_data
from scheduler import get_papers_with_metadata_changes
from utils.config_builder import build_product_config
from tasks_metadata import update_metadata_batch_task
from utils.db.metadata_updates import create_metadata_update_job
import json
import os


def render():
    """Render the Metadata Management page."""
    st.title("🔄 Metadata Management")
    st.markdown("Update metadata for existing papers without re-parsing PDFs.")
    
    st.info(
        "💡 **How it works**: When metadata changes in Google Sheets (tags, year, topic, etc.), "
        "you can update existing papers without re-parsing PDFs. This is 40-80x faster and costs $0."
    )
    
    # Select data source
    st.subheader("1️⃣ Select Data Source")
    
    try:
        sources = get_data_sources()
        if not sources:
            st.warning("No data sources configured. Please add a data source first.")
            return
        
        source_options = {f"{s['name']} (ID: {s['id']})": s['id'] for s in sources}
        selected_source_label = st.selectbox(
            "Choose a data source to check for metadata changes:",
            options=list(source_options.keys())
        )
        
        source_id = source_options[selected_source_label]
        source_info = next((s for s in sources if s['id'] == source_id), None)
        
        if not source_info:
            st.error("Source not found")
            return
        
        # Show source details
        with st.expander("📋 Source Details", expanded=False):
            st.json({
                'Name': source_info.get('name'),
                'Sheet URL': source_info.get('sheet_url'),
                'Tab Name': source_info.get('sheet_tab_name'),
                'Product ID': source_info.get('product_id')
            })
        
        # Check for changes button
        st.subheader("2️⃣ Detect Metadata Changes")
        
        if st.button("🔍 Check for Metadata Changes", type="primary"):
            with st.spinner("Loading sheet data and comparing with database..."):
                try:
                    # Load Google credentials
                    google_creds_secret = source_info.get('google_service_account_secret', 'ABCD_DA_GOOGLE_CREDS')
                    google_creds_json = os.getenv(google_creds_secret, '')
                    
                    if not google_creds_json:
                        st.error(f"Google credentials not found in secret: {google_creds_secret}")
                        return
                    
                    google_credentials = json.loads(google_creds_json)
                    
                    # Load sheet data
                    sheet_data = load_sheet_data(
                        source_info['sheet_url'],
                        source_info['sheet_tab_name'],
                        google_credentials
                    )
                    
                    # Get column mappings
                    column_mappings = get_column_mapping_dict(source_id)
                    
                    # Detect changes
                    papers_with_changes = get_papers_with_metadata_changes(
                        source_id=source_id,
                        sheet_data=sheet_data,
                        column_mappings=column_mappings,
                        max_papers_per_run=100  # UI can handle more
                    )
                    
                    if not papers_with_changes:
                        st.success("✅ No metadata changes detected. All papers are up to date!")
                        return
                    
                    # Display changes
                    st.success(f"Found {len(papers_with_changes)} papers with metadata changes")
                    
                    # Show papers with changes
                    st.subheader("3️⃣ Papers with Metadata Changes")
                    
                    # Prepare data for display
                    changes_df = pd.DataFrame([
                        {
                            'File ID': p['file_id'][:16] + '...',
                            'Tags': ', '.join(p['new_metadata'].get('tags', [])) if p['new_metadata'].get('tags') else 'None',
                            'Year': p['new_metadata'].get('year', 'N/A'),
                            'Topic': p['new_metadata'].get('topic', 'N/A')
                        }
                        for p in papers_with_changes
                    ])
                    
                    st.dataframe(changes_df, use_container_width=True)
                    
                    # Trigger update button
                    st.subheader("4️⃣ Update Metadata")
                    
                    st.warning(
                        f"⚠️ This will update metadata for {len(papers_with_changes)} papers. "
                        "Embeddings will NOT be regenerated (cost: $0)."
                    )
                    
                    if st.button(f"🚀 Update Metadata for {len(papers_with_changes)} Papers", type="primary"):
                        with st.spinner("Queueing metadata update job..."):
                            try:
                                # Create metadata update job
                                job_id = create_metadata_update_job(
                                    source_id=source_id,
                                    product_id=source_info.get('product_id'),
                                    total_papers=len(papers_with_changes)
                                )
                                
                                # Build product config
                                product_config = build_product_config(source_info.get('product_id'))
                                
                                # Queue batch update task
                                update_metadata_batch_task.apply_async(
                                    args=(job_id, papers_with_changes, product_config),
                                    queue='metadata_updates'
                                )
                                
                                st.success(
                                    f"✅ Metadata update job queued successfully!\n\n"
                                    f"**Job ID**: `{job_id}`\n\n"
                                    f"**Papers**: {len(papers_with_changes)}\n\n"
                                    f"Monitor progress in the **Job Management** page."
                                )
                                
                            except Exception as e:
                                st.error(f"Failed to queue metadata update job: {str(e)}")
                    
                except Exception as e:
                    st.error(f"Error detecting metadata changes: {str(e)}")
                    import traceback
                    with st.expander("Error Details"):
                        st.code(traceback.format_exc())
    
    except Exception as e:
        st.error(f"Error loading data sources: {str(e)}")
        import traceback
        with st.expander("Error Details"):
            st.code(traceback.format_exc())

"""
Admin Coverage Analysis Page

Analyzes which Google Sheet rows have/haven't been processed.
Compares Google Sheets data against database records to identify gaps.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Set, Tuple
import logging

from utils.google_sheets import load_sheet_data
from utils.row_identifier import extract_row_identifier
from utils.db.sources import get_data_sources
from utils.db.documents import get_processed_identifiers_for_source
from utils.config_builder import build_product_config

logger = logging.getLogger(__name__)


def show():
    """Display coverage analysis page."""
    st.header("📊 Coverage Analysis")
    st.markdown("Analyze which Google Sheet rows have been processed vs. not processed")
    
    st.divider()
    
    # Get all data sources
    sources = get_data_sources(active_only=False)
    
    if not sources:
        st.warning("No data sources configured. Please add a data source first.")
        return
    
    # Source selection
    source_options = {f"{s['name']} (ID: {s['id']})": s for s in sources}
    selected_source_key = st.selectbox(
        "Select Data Source to Analyze",
        options=list(source_options.keys())
    )
    
    if not selected_source_key:
        return
    
    source = source_options[selected_source_key]
    source_id = source['id']
    
    st.divider()
    
    # Analysis button
    if st.button("🔍 Run Coverage Analysis", type="primary", use_container_width=True):
        analyze_coverage(source)


def analyze_coverage(source: Dict):
    """
    Analyze coverage for a specific data source.
    
    Compares Google Sheets rows against database records.
    """
    source_id = source['id']
    source_name = source['name']
    
    with st.spinner(f"Analyzing coverage for '{source_name}'..."):
        try:
            # Step 1: Get product configuration
            product_id = source.get('product_id')
            if not product_id:
                st.error(f"Source '{source_name}' has no product assigned.")
                return
            
            product_config = build_product_config(product_id)
            if not product_config:
                st.error(f"Product configuration not found for product_id={product_id}")
                return
            
            google_credentials = product_config.get('google_credentials')
            if not google_credentials:
                st.error("No Google credentials configured for this product.")
                return
            
            st.info(f"📄 Fetching Google Sheet data from '{source_name}'...")
            
            # Step 2: Fetch Google Sheet data
            sheet_data = load_sheet_data(
                source['sheet_url'],
                source['sheet_tab'],
                google_credentials
            )
            
            if sheet_data is None or sheet_data.empty:
                st.warning("No data found in Google Sheet.")
                return
            
            total_rows = len(sheet_data)
            st.success(f"✅ Found {total_rows} rows in Google Sheet")
            
            # Step 3: Get column mappings from product config
            column_mappings = product_config.get('column_mappings', {})
            
            if not column_mappings:
                st.error("No column mappings configured for this product.")
                return
            
            # Step 4: Extract identifiers from each sheet row
            st.info("🔍 Extracting identifiers from Google Sheet rows...")
            
            sheet_identifiers = {}  # {identifier: row_index}
            rows_without_identifiers = []
            
            for idx, row in sheet_data.iterrows():
                identifier = extract_row_identifier(
                    row=row,
                    column_mappings=column_mappings,
                    verbose=False
                )
                
                if identifier:
                    sheet_identifiers[identifier] = idx
                else:
                    rows_without_identifiers.append(idx)
            
            st.success(f"✅ Extracted {len(sheet_identifiers)} identifiers from sheet")
            
            # Step 5: Get processed identifiers from database
            st.info("💾 Fetching processed identifiers from database...")
            
            processed_identifiers = get_processed_identifiers_for_source(source_id)
            
            st.success(f"✅ Found {len(processed_identifiers)} processed identifiers in database")
            
            # Step 6: Compare and identify gaps
            st.info("📊 Comparing sheet vs database...")
            
            # Not processed = identifiers in sheet but not in database
            not_processed = set(sheet_identifiers.keys()) - processed_identifiers
            
            # Already processed = identifiers in both sheet and database
            already_processed = set(sheet_identifiers.keys()) & processed_identifiers
            
            # Step 7: Display results
            st.divider()
            st.subheader("📈 Coverage Summary")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Total Rows", total_rows)
            
            with col2:
                st.metric("Already Processed", len(already_processed))
            
            with col3:
                st.metric("Not Yet Processed", len(not_processed))
            
            with col4:
                st.metric("No Identifier", len(rows_without_identifiers))
            
            # Coverage percentage
            identifiable_rows = len(sheet_identifiers)
            if identifiable_rows > 0:
                coverage_pct = (len(already_processed) / identifiable_rows) * 100
                st.progress(coverage_pct / 100)
                st.caption(f"Coverage: {coverage_pct:.1f}% of identifiable rows")
            
            # Step 8: Show detailed breakdowns
            st.divider()
            
            # Tab view for different categories
            tab1, tab2, tab3 = st.tabs([
                "❌ Not Yet Processed",
                "✅ Already Processed",
                "⚠️ No Identifier"
            ])
            
            with tab1:
                if not_processed:
                    st.markdown(f"**{len(not_processed)} rows** not yet processed:")
                    
                    # Build dataframe with details
                    not_processed_rows = []
                    for identifier in not_processed:
                        row_idx = sheet_identifiers[identifier]
                        row = sheet_data.iloc[row_idx]
                        
                        # Extract key fields
                        title_col = column_mappings.get('title')
                        authors_col = column_mappings.get('authors')
                        drive_link_col = column_mappings.get('drive_link')
                        
                        not_processed_rows.append({
                            'Row #': row_idx + 2,  # +2 because Excel/Sheets start at 1 and has header
                            'Identifier': identifier[:20] + '...' if len(identifier) > 20 else identifier,
                            'Title': row.get(title_col, 'N/A')[:50] if title_col else 'N/A',
                            'Authors': row.get(authors_col, 'N/A')[:30] if authors_col else 'N/A',
                            'Drive Link': row.get(drive_link_col, 'N/A')[:50] if drive_link_col else 'N/A'
                        })
                    
                    df_not_processed = pd.DataFrame(not_processed_rows)
                    st.dataframe(df_not_processed, use_container_width=True, height=400)
                    
                    # Export option
                    csv = df_not_processed.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Not Processed (CSV)",
                        data=csv,
                        file_name=f"not_processed_{source_name}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.success("🎉 All identifiable rows have been processed!")
            
            with tab2:
                if already_processed:
                    st.markdown(f"**{len(already_processed)} rows** already processed:")
                    
                    # Build dataframe
                    processed_rows = []
                    for identifier in list(already_processed)[:1000]:  # Limit to first 1000 for display
                        row_idx = sheet_identifiers[identifier]
                        row = sheet_data.iloc[row_idx]
                        
                        title_col = column_mappings.get('title')
                        authors_col = column_mappings.get('authors')
                        
                        processed_rows.append({
                            'Row #': row_idx + 2,
                            'Identifier': identifier[:20] + '...' if len(identifier) > 20 else identifier,
                            'Title': row.get(title_col, 'N/A')[:50] if title_col else 'N/A',
                            'Authors': row.get(authors_col, 'N/A')[:30] if authors_col else 'N/A'
                        })
                    
                    df_processed = pd.DataFrame(processed_rows)
                    st.dataframe(df_processed, use_container_width=True, height=400)
                    
                    if len(already_processed) > 1000:
                        st.info(f"Showing first 1,000 of {len(already_processed)} processed rows")
                else:
                    st.warning("No rows have been processed yet")
            
            with tab3:
                if rows_without_identifiers:
                    st.markdown(f"**{len(rows_without_identifiers)} rows** without identifiable information:")
                    st.caption("These rows lack both a Drive File ID and sufficient metadata (title/authors) to generate an identifier")
                    
                    # Build dataframe
                    no_id_rows = []
                    for row_idx in rows_without_identifiers:
                        row = sheet_data.iloc[row_idx]
                        
                        # Show all columns to help debug
                        no_id_rows.append({
                            'Row #': row_idx + 2,
                            'Preview': str(row.to_dict())[:100] + '...'
                        })
                    
                    df_no_id = pd.DataFrame(no_id_rows)
                    st.dataframe(df_no_id, use_container_width=True, height=400)
                    
                    st.warning("⚠️ These rows cannot be processed until they have either a Drive link or title/authors")
                else:
                    st.success("All rows have identifiers")
            
            st.divider()
            st.success(f"✅ Analysis complete for '{source_name}'")
            
        except Exception as e:
            logger.error(f"Coverage analysis failed: {e}", exc_info=True)
            st.error(f"Analysis failed: {str(e)}")
            st.exception(e)


if __name__ == "__main__":
    show()

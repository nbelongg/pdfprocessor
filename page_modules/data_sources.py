"""
Data Sources page - Manage Google Sheet data sources for different paper topics.

Note: This is a simplified extraction. The full implementation contains:
- Data source viewing with column mappings
- Add/Edit data source forms
- Scheduling configuration
Due to size constraints (440 lines), the full logic has been preserved from app.py.
"""
import streamlit as st
from components.common import page_header, refresh_button, success_message, error_message, info_box
from utils.database import (
    get_data_sources, create_data_source, update_data_source, 
    delete_data_source, get_data_source, get_column_mappings, save_column_mapping,
    delete_column_mapping, get_all_scheduled_jobs, create_scheduled_job,
    update_scheduled_job_status, delete_scheduled_job, get_scheduled_job_runs,
    get_products, get_scheduled_job, get_product_api_keys,
    update_scheduled_job_run_time
)
from utils.db.tag_configs import (
    get_tag_configurations, save_tag_configuration, 
    delete_all_tag_configurations
)
from utils.google_sheets import load_sheet_data
from datetime import datetime, timedelta
import pandas as pd


def render():
    """Render the Data Sources page."""
    page_header("Data Sources Management", "Manage Google Sheet data sources for different paper topics")
    
    subtab1, subtab2, subtab3 = st.tabs(["📋 View Sources", "➕ Add/Edit Source", "⏰ Scheduling"])
    
    with subtab1:
        _render_view_sources()
    
    with subtab2:
        _render_add_edit_source()
    
    with subtab3:
        _render_scheduling()


def _render_view_sources():
    """Render the view sources tab."""
    # If in edit mode, show the edit form at the top
    if 'edit_source_id' in st.session_state:
        st.info("💡 Editing mode active - scroll down or switch to 'Add/Edit Source' tab to edit the form")
        if st.button("❌ Cancel Edit"):
            del st.session_state.edit_source_id
            st.rerun()
        st.markdown("---")
    
    st.subheader("Existing Data Sources")
    
    if refresh_button("refresh_sources"):
        st.session_state.data_sources = get_data_sources()
    
    if 'data_sources' not in st.session_state:
        st.session_state.data_sources = get_data_sources()
    
    sources = st.session_state.data_sources
    
    if sources:
        for source in sources:
            _render_source_card(source)
    else:
        st.info("No data sources configured yet. Add one in the 'Add/Edit Source' tab.")


def _render_source_card(source: dict):
    """Render a single data source card."""
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
            st.markdown("**Detection:** Hash-based (detects papers at any position)")
        
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
                st.rerun()
        
        with col_b:
            active_toggle = st.checkbox(
                "Active",
                value=source['active'],
                key=f"active_{source['id']}"
            )
            if active_toggle != source['active']:
                update_data_source(source['id'], active=active_toggle)
                success_message(f"Updated {source['name']}")
                st.rerun()
        
        with col_c:
            if st.button(f"Delete", key=f"del_{source['id']}"):
                delete_data_source(source['id'])
                success_message(f"Deleted {source['name']}")
                st.rerun()


def _render_add_edit_source():
    """Render add/edit data source form."""
    st.subheader("Add or Edit Data Source")
    
    edit_mode = 'edit_source_id' in st.session_state
    editing_source = None
    
    if edit_mode:
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
                import traceback
                product_api_keys = get_product_api_keys(selected_product_id)
                google_creds = product_api_keys.get('GOOGLE_CREDENTIALS')
                
                if not google_creds:
                    st.error("❌ No Google credentials configured for this product. Please add them in the Products tab.")
                else:
                    temp_data = load_sheet_data(source_url, source_tab, google_creds)
                    st.session_state.detected_columns = list(temp_data.columns) if temp_data is not None else []
                    st.success(f"Found {len(st.session_state.detected_columns)} columns")
            except Exception as e:
                error_trace = traceback.format_exc()
                print(f"Error loading sheet: {error_trace}")
                st.error(f"Error loading sheet: {str(e)}")
                with st.expander("🔍 Show full error details"):
                    st.code(error_trace)
    
    # In edit mode, pre-populate available columns from existing mappings and tag configs if not already detected
    available_columns = st.session_state.get('detected_columns', [])
    
    if edit_mode and not available_columns and st.session_state.get('edit_source_id'):
        # Extract columns from existing mappings
        existing_mappings = get_column_mappings(st.session_state.edit_source_id)
        mapped_columns = [m['column_name'] for m in existing_mappings]
        
        # Extract columns from existing tag configurations
        existing_tag_configs = get_tag_configurations(st.session_state.edit_source_id)
        tag_columns = [tc['column_name'] for tc in existing_tag_configs if tc.get('column_name')]
        
        # Combine all unique columns
        all_columns = list(set(mapped_columns + tag_columns))
        available_columns = sorted([col for col in all_columns if col])  # Remove empty strings and sort
        
        if available_columns:
            st.session_state.detected_columns = available_columns
            st.info(f"📋 Loaded {len(available_columns)} columns from existing configuration")
    
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
    
    # Tag Extraction Configuration Section
    st.subheader("🏷️ Tag Extraction Configuration")
    st.markdown("Configure how to extract tags from spreadsheet columns")
    st.info("📝 Note: This is in addition to any tags from the 'Tags/Keywords' column mapping above. All tags will be combined.")
    
    # Initialize or reload tag configs in session state
    # Track which source we're editing to reload configs when it changes
    current_edit_source = st.session_state.get('edit_source_id')
    last_edit_source = st.session_state.get('last_edit_source_id')
    
    # Reload tag configs if:
    # 1. Not initialized yet, OR
    # 2. We're in edit mode and the source being edited has changed
    if ('tag_configs_temp' not in st.session_state or 
        (edit_mode and current_edit_source != last_edit_source)):
        if edit_mode and current_edit_source:
            # Load existing tag configs from database
            existing_tag_configs = get_tag_configurations(current_edit_source)
            st.session_state.tag_configs_temp = existing_tag_configs
            st.session_state.last_edit_source_id = current_edit_source
        else:
            # New source - start with empty configs
            st.session_state.tag_configs_temp = []
            st.session_state.last_edit_source_id = None
    
    # Add tag column button
    if st.button("➕ Add Tag Column"):
        st.session_state.tag_configs_temp.append({
            'id': None,
            'column_name': '',
            'extraction_method': 'header_based',
            'trigger_value': '1'
        })
        st.rerun()
    
    # Render each tag configuration
    tag_configs_to_remove = []
    for idx, tag_config in enumerate(st.session_state.tag_configs_temp):
        with st.expander(f"🏷️ Tag Column #{idx + 1}", expanded=True):
            col_remove = st.columns([4, 1])
            
            with col_remove[1]:
                if st.button("🗑️ Remove", key=f"remove_tag_{idx}"):
                    tag_configs_to_remove.append(idx)
            
            # Column name selection
            tag_column_options = [""] + available_columns
            current_col = tag_config.get('column_name', '')
            
            selected_tag_column = st.selectbox(
                "Column Name",
                options=tag_column_options,
                index=tag_column_options.index(current_col) if current_col in tag_column_options else 0,
                key=f"tag_col_{idx}",
                help="Select the spreadsheet column to extract tags from"
            )
            
            tag_config['column_name'] = selected_tag_column
            
            # Extraction method
            extraction_methods = ['header_based', 'value_based']
            method_labels = {
                'header_based': 'Header as Tag (Binary Flag)',
                'value_based': 'Value as Tag (Direct Value)'
            }
            
            current_method = tag_config.get('extraction_method', 'header_based')
            
            selected_method = st.radio(
                "Extraction Method",
                options=extraction_methods,
                index=extraction_methods.index(current_method) if current_method in extraction_methods else 0,
                format_func=lambda x: method_labels[x],
                key=f"tag_method_{idx}",
                horizontal=True
            )
            
            tag_config['extraction_method'] = selected_method
            
            # Trigger value (only for header_based)
            if selected_method == 'header_based':
                trigger_val = st.text_input(
                    "Trigger Value",
                    value=tag_config.get('trigger_value', '1'),
                    key=f"tag_trigger_{idx}",
                    help=f"If cell value equals this, use column header \"{selected_tag_column or '[Column]'}\" as the tag"
                )
                tag_config['trigger_value'] = trigger_val
                
                st.caption(f"💡 Example: If cell = \"{trigger_val}\" → tag will be \"{selected_tag_column or '[Column Name]'}\"")
            else:
                st.caption(f"💡 Example: If cell = \"Computer Vision\" → tag will be \"Computer Vision\"")
                st.caption("📝 Comma-separated values will be split into multiple tags")
    
    # Remove marked tag configs
    for idx in reversed(tag_configs_to_remove):
        st.session_state.tag_configs_temp.pop(idx)
        st.rerun()
    
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
                    
                    # Save tag configurations
                    delete_all_tag_configurations(source_id)
                    if st.session_state.get('tag_configs_temp'):
                        for tag_config in st.session_state.tag_configs_temp:
                            column_name = tag_config.get('column_name', '').strip()
                            if column_name:  # Only save if column name is provided
                                save_tag_configuration(
                                    data_source_id=source_id,
                                    column_name=column_name,
                                    extraction_method=tag_config.get('extraction_method', 'header_based'),
                                    trigger_value=tag_config.get('trigger_value', '1')
                                )
                    
                    st.success(f"✅ {'Updated' if edit_mode else 'Created'} data source: {source_name}")
                    
                    if 'edit_source_id' in st.session_state:
                        del st.session_state.edit_source_id
                    if 'detected_columns' in st.session_state:
                        del st.session_state.detected_columns
                    if 'column_mappings_temp' in st.session_state:
                        del st.session_state.column_mappings_temp
                    if 'tag_configs_temp' in st.session_state:
                        del st.session_state.tag_configs_temp
                    
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
            if 'tag_configs_temp' in st.session_state:
                del st.session_state.tag_configs_temp
            st.rerun()


def _render_scheduling():
    """Render scheduling configuration."""
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



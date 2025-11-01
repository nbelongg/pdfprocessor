"""
Job Management page - Monitor Celery jobs, trigger on-demand processing, view history.

This page provides comprehensive job management capabilities:
- Real-time monitoring of active Celery tasks
- On-demand processing triggers for data sources
- Job history with filtering and detailed error views
"""
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import time
import logging
from components.common import page_header, refresh_button, success_message, error_message
from utils.db.jobs import (
    get_all_celery_jobs, get_celery_job,
    update_celery_job_status, cancel_celery_job
)
from utils.db.sources import get_data_sources, get_data_source
from utils.db.products import get_products, get_product_api_keys
from utils.db.scheduling import get_all_scheduled_jobs, get_scheduled_job_runs
from utils.google_sheets import load_sheet_data
from utils.config_builder import get_product_config_from_source
import os

logger = logging.getLogger(__name__)


def render():
    """Render the Job Management page."""
    page_header("Job Management", "Monitor, trigger, and manage background processing jobs")
    
    # Initialize session state
    if 'job_auto_refresh' not in st.session_state:
        st.session_state.job_auto_refresh = False
    if 'job_page_monitor' not in st.session_state:
        st.session_state.job_page_monitor = 1
    if 'job_page_history' not in st.session_state:
        st.session_state.job_page_history = 1
    if 'job_last_refresh_time' not in st.session_state:
        st.session_state.job_last_refresh_time = time.time()
    if 'monitor_last_filter' not in st.session_state:
        st.session_state.monitor_last_filter = "All"
    if 'monitor_last_page_size' not in st.session_state:
        st.session_state.monitor_last_page_size = 50
    if 'history_last_filter' not in st.session_state:
        st.session_state.history_last_filter = "All"
    if 'history_last_page_size' not in st.session_state:
        st.session_state.history_last_page_size = 25
    
    # Tabs for different functionality
    tab1, tab2, tab3 = st.tabs([
        "⚙️ Monitor Jobs",
        "🚀 Trigger Processing",
        "📜 Job History"
    ])
    
    with tab1:
        _render_monitor_jobs()
    
    with tab2:
        _render_trigger_processing()
    
    with tab3:
        _render_job_history()


# ============================================
# TAB 1: MONITOR JOBS
# ============================================

def _render_monitor_jobs():
    """Render the real-time job monitoring tab."""
    st.subheader("Real-Time Job Monitoring")
    
    # Controls row
    col1, col2, col3, col4 = st.columns([2, 2, 2, 4])
    
    with col1:
        if st.button("🔄 Refresh Now", use_container_width=True):
            st.session_state.job_last_refresh_time = time.time()
            st.rerun()
    
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (10s)", value=st.session_state.job_auto_refresh)
        if auto_refresh != st.session_state.job_auto_refresh:
            st.session_state.job_auto_refresh = auto_refresh
            st.session_state.job_last_refresh_time = time.time()
            st.rerun()
    
    with col3:
        jobs_per_page = st.selectbox(
            "Jobs per page:",
            [10, 25, 50, 100],
            index=2,
            key="monitor_jobs_per_page"
        )
        
        # Reset page if page size changed
        if jobs_per_page != st.session_state.monitor_last_page_size:
            st.session_state.job_page_monitor = 1
            st.session_state.monitor_last_page_size = jobs_per_page
    
    # Auto-refresh (non-blocking, checks elapsed time and reruns after 10s)
    if st.session_state.job_auto_refresh:
        elapsed = time.time() - st.session_state.job_last_refresh_time
        
        # Display countdown info (approximate - updates on user interaction or after 10s)
        remaining = max(0, 10 - int(elapsed))
        st.info(f"⏱️ Auto-refresh enabled (next refresh in ~{remaining}s)")
        
        # Trigger refresh if 10 seconds have elapsed (non-blocking check)
        if elapsed >= 10:
            st.session_state.job_last_refresh_time = time.time()
            st.rerun()
    
    # Get all jobs with pagination support
    try:
        all_jobs = get_all_celery_jobs(limit=1000)  # Fetch more for pagination
    except Exception as e:
        st.error(f"Error loading jobs: {str(e)}")
        return
    
    if not all_jobs:
        st.info("No jobs found. Trigger processing in the 'Trigger Processing' tab.")
        return
    
    # Filter by status
    status_counts = _calculate_status_counts(all_jobs)
    
    # Display metrics
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("🔵 Pending", status_counts.get('pending', 0))
    with col2:
        st.metric("🟡 Running", status_counts.get('running', 0) + status_counts.get('started', 0))
    with col3:
        st.metric("✅ Completed", status_counts.get('completed', 0) + status_counts.get('success', 0))
    with col4:
        st.metric("❌ Failed", status_counts.get('failed', 0))
    with col5:
        st.metric("🚫 Cancelled", status_counts.get('cancelled', 0))
    
    st.markdown("---")
    
    # Filter selector
    status_filter = st.selectbox(
        "Filter by status:",
        ["All", "Pending", "Running", "Completed", "Failed", "Cancelled"],
        key="monitor_status_filter"
    )
    
    # Reset page if filter changed
    if status_filter != st.session_state.monitor_last_filter:
        st.session_state.job_page_monitor = 1
        st.session_state.monitor_last_filter = status_filter
    
    # Filter jobs
    filtered_jobs = _filter_jobs_by_status(all_jobs, status_filter)
    
    # Pagination
    total_jobs = len(filtered_jobs)
    total_pages = max(1, (total_jobs + jobs_per_page - 1) // jobs_per_page)
    
    # Clamp page number to valid range
    if st.session_state.job_page_monitor > total_pages:
        st.session_state.job_page_monitor = max(1, total_pages)
    
    if total_pages > 1:
        col1, col2, col3 = st.columns([2, 6, 2])
        with col1:
            if st.button("⬅️ Previous", disabled=st.session_state.job_page_monitor <= 1):
                st.session_state.job_page_monitor -= 1
                st.rerun()
        with col2:
            st.markdown(f"**Page {st.session_state.job_page_monitor} of {total_pages}** (Total: {total_jobs} jobs)")
        with col3:
            if st.button("Next ➡️", disabled=st.session_state.job_page_monitor >= total_pages):
                st.session_state.job_page_monitor += 1
                st.rerun()
    else:
        st.markdown(f"**Showing {total_jobs} jobs**")
    
    # Calculate pagination slice
    start_idx = (st.session_state.job_page_monitor - 1) * jobs_per_page
    end_idx = min(start_idx + jobs_per_page, total_jobs)
    page_jobs = filtered_jobs[start_idx:end_idx]
    
    # Display jobs
    for job in page_jobs:
        _render_job_card(job)


def _calculate_status_counts(jobs: List[Dict]) -> Dict[str, int]:
    """Calculate count of jobs by status."""
    counts = {}
    for job in jobs:
        status = job.get('status', 'unknown').lower()
        counts[status] = counts.get(status, 0) + 1
    return counts


def _filter_jobs_by_status(jobs: List[Dict], status_filter: str) -> List[Dict]:
    """Filter jobs by status."""
    if status_filter == "All":
        return jobs
    
    status_map = {
        "Pending": ['pending'],
        "Running": ['running', 'started', 'progress'],
        "Completed": ['completed', 'success'],
        "Failed": ['failed'],
        "Cancelled": ['cancelled']
    }
    
    valid_statuses = status_map.get(status_filter, [])
    return [j for j in jobs if j.get('status', '').lower() in valid_statuses]


def _render_job_card(job: Dict):
    """Render a single job monitoring card."""
    status = job.get('status', 'unknown')
    task_name = job.get('task_name', 'Unknown Task')
    task_id = job.get('task_id', '')
    created_at = job.get('created_at', '')
    
    # Status icon
    status_icons = {
        'pending': '🔵',
        'running': '🟡',
        'started': '🟡',
        'progress': '🟡',
        'completed': '✅',
        'success': '✅',
        'failed': '❌',
        'cancelled': '🚫'
    }
    icon = status_icons.get(status.lower(), '❓')
    
    with st.expander(f"{icon} {task_name} - {status.upper()} ({created_at})"):
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.markdown(f"**Task ID:** `{task_id[:16]}...`")
            st.markdown(f"**Status:** {status}")
            st.markdown(f"**Created:** {created_at}")
            
            # Progress bar
            progress_current = job.get('progress_current', 0)
            progress_total = job.get('progress_total', 0)
            progress_message = job.get('progress_message', '')
            
            if progress_total > 0:
                progress_pct = int((progress_current / progress_total) * 100)
                st.progress(progress_current / progress_total, text=f"{progress_pct}% - {progress_message}")
            elif progress_message:
                st.info(progress_message)
            
            # Error message
            if job.get('error_message'):
                st.error(f"**Error:** {job['error_message']}")
            
            # Result
            if job.get('result'):
                with st.expander("📊 View Result"):
                    st.json(job['result'])
        
        with col2:
            # Action buttons
            if status.lower() in ['pending', 'running', 'started', 'progress']:
                if st.button("🚫 Cancel", key=f"cancel_{task_id}", use_container_width=True):
                    try:
                        cancel_celery_job(task_id)
                        success_message(f"Cancelled job {task_id[:8]}")
                        st.rerun()
                    except Exception as e:
                        error_message(f"Error cancelling job: {str(e)}")
            
            if status.lower() in ['failed', 'cancelled']:
                if st.button("🔄 Retry", key=f"retry_{task_id}", use_container_width=True):
                    _retry_failed_job(job)


def _retry_failed_job(job: Dict):
    """Retry a failed job by re-triggering processing for its source."""
    retry_job_id = None  # Initialize for error handling
    try:
        source_id = job.get('source_id')
        
        if not source_id:
            st.warning("⚠️ Cannot retry: No data source associated with this job. Please trigger a new job manually.")
            return
        
        # Get source info
        source = get_data_source(source_id)
        if not source:
            error_message(f"❌ Data source {source_id} not found. It may have been deleted.")
            return
        
        if not source.get('active'):
            st.warning(f"⚠️ Data source '{source['name']}' is inactive. Please activate it first.")
            return
        
        # Get product-based credentials
        product_id = source.get('product_id')
        if not product_id:
            error_message('No product associated with this data source')
            return
        
        product_api_keys = get_product_api_keys(product_id)
        google_credentials = product_api_keys.get('GOOGLE_CREDENTIALS')
        
        if not google_credentials:
            error_message('Google credentials not configured for this product. Please add them in the Products tab.')
            return
        
        # Load sheet data
        sheet_data = load_sheet_data(
            source['sheet_url'],
            source['sheet_tab'],
            google_credentials
        )
        
        # Use hash-based detection to find unprocessed papers
        from utils.db.documents import get_processed_identifiers_for_source
        from utils.row_identifier import get_unprocessed_row_indices
        from utils.database import get_column_mapping_dict
        
        column_mappings = get_column_mapping_dict(source_id)
        processed_ids = get_processed_identifiers_for_source(source_id)
        
        rows_to_process = get_unprocessed_row_indices(
            sheet_data=sheet_data,
            column_mappings=column_mappings,
            processed_identifiers=processed_ids,
            max_papers=50  # Limit to 50 papers for retry
        )
        
        if not rows_to_process:
            st.info("ℹ️ No new papers to process. All papers have been processed.")
            return
        
        # Build configuration
        config = get_product_config_from_source(source_id)
        config['google_credentials'] = google_credentials
        
        # Prepare for pipeline
        source_configs = [{
            'source_id': source_id,
            'data': sheet_data,
            'selected_indices': rows_to_process
        }]
        
        # Import and trigger pipeline
        from utils.multi_source_pipeline import process_multi_source_pipeline
        import uuid
        
        retry_job_id = str(uuid.uuid4())
        
        # Create Celery job record
        from utils.db.jobs import create_celery_job
        create_celery_job(
            task_id=retry_job_id,
            task_name=f"Retry: {source['name']}",
            source_id=source_id,
            submitted_by='retry'
        )
        
        # Process synchronously
        with st.spinner(f"Processing {len(rows_to_process)} papers..."):
            results = process_multi_source_pipeline(
                source_configs=source_configs,
                config=config,
                progress_callback=None,
                preview_mode=False
            )
        
        # Update job status
        from utils.db.jobs import update_celery_job_status
        update_celery_job_status(
            retry_job_id,
            'completed',
            result=results
        )
        
        success_message(f"✅ Retry successful! Processed {results.get('total_pdfs', 0)} papers.")
        st.rerun()
        
    except Exception as e:
        # Update job status to failed if job was created
        if retry_job_id is not None:
            try:
                from utils.db.jobs import update_celery_job_status
                update_celery_job_status(
                    retry_job_id,
                    'failed',
                    error=str(e)
                )
            except:
                pass  # Don't fail the error response if we can't update status
        
        logger.exception(f"Error retrying job: {e}")
        error_message(f"❌ Error retrying job: {str(e)}")
        st.exception(e)


# ============================================
# TAB 2: TRIGGER PROCESSING
# ============================================

def _render_trigger_processing():
    """Render the on-demand processing trigger tab."""
    st.subheader("Trigger On-Demand Processing")
    
    st.info("💡 Bypass the scheduler and process papers immediately from your configured data sources.")
    
    # Get data sources
    try:
        sources = get_data_sources()
    except Exception as e:
        st.error(f"Error loading data sources: {str(e)}")
        return
    
    if not sources:
        st.warning("No data sources configured. Please add data sources first.")
        return
    
    # Active sources only
    active_sources = [s for s in sources if s.get('active')]
    
    if not active_sources:
        st.warning("No active data sources found.")
        return
    
    # Source selection
    source_options = {f"{s['name']} ({s.get('topic', 'No topic')})": s['id'] for s in active_sources}
    selected_source_label = st.selectbox(
        "Select Data Source:",
        list(source_options.keys())
    )
    
    selected_source_id = source_options[selected_source_label]
    selected_source = next((s for s in active_sources if s['id'] == selected_source_id), None)
    
    if not selected_source:
        return
    
    # Display source info
    st.markdown("---")
    st.markdown("### Selected Source Details")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(f"**Sheet URL:** {selected_source['sheet_url'][:50]}...")
        st.markdown(f"**Tab:** {selected_source['sheet_tab']}")
    with col2:
        st.markdown(f"**Namespace:** {selected_source.get('default_namespace', 'default')}")
        st.markdown("**Detection:** Hash-based (all positions)")
    with col3:
        product_id = selected_source.get('product_id')
        if product_id:
            st.markdown(f"**Product ID:** {product_id}")
    
    st.markdown("---")
    
    # Processing options
    st.markdown("### Processing Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        process_mode = st.radio(
            "Processing Mode:",
            ["New Papers Only", "Specific Rows", "All Papers (Re-process)"]
        )
    
    with col2:
        max_papers = st.number_input(
            "Max Papers to Process:",
            min_value=1,
            max_value=1000,
            value=50,
            help="Limit the number of papers to process in this run"
        )
    
    # Row selection for "Specific Rows" mode
    selected_rows = None
    if process_mode == "Specific Rows":
        rows_input = st.text_input(
            "Enter row numbers (comma-separated):",
            placeholder="e.g., 10,15,20-25,30"
        )
        if rows_input:
            selected_rows = _parse_row_input(rows_input)
            st.info(f"Will process {len(selected_rows)} rows: {selected_rows[:10]}{'...' if len(selected_rows) > 10 else ''}")
    
    # Trigger button
    st.markdown("---")
    
    if st.button("🚀 Trigger Processing Now", type="primary", use_container_width=True):
        with st.spinner("Triggering processing job..."):
            try:
                result = _trigger_processing_job(
                    selected_source,
                    process_mode,
                    max_papers,
                    selected_rows
                )
                
                if result.get('success'):
                    success_message(f"✅ Processing job triggered! Job ID: {result.get('job_id', 'N/A')}")
                    success_message(f"Processing {result.get('paper_count', 0)} papers.")
                    st.info("Switch to 'Monitor Jobs' tab to view progress.")
                else:
                    error_message(f"Failed to trigger processing: {result.get('error', 'Unknown error')}")
            except Exception as e:
                error_message(f"Error triggering processing: {str(e)}")
                st.exception(e)


def _parse_row_input(rows_input: str) -> List[int]:
    """Parse comma-separated row numbers with range support."""
    rows = []
    parts = rows_input.split(',')
    
    for part in parts:
        part = part.strip()
        if '-' in part:
            # Range like "20-25"
            try:
                start, end = part.split('-')
                rows.extend(range(int(start), int(end) + 1))
            except (ValueError, IndexError) as e:
                logger.warning(f"Invalid range format '{part}': {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing range '{part}': {e}")
                continue
        else:
            # Single number
            try:
                rows.append(int(part))
            except ValueError as e:
                logger.warning(f"Invalid row number '{part}': {e}")
                continue
            except Exception as e:
                logger.error(f"Unexpected error parsing row number '{part}': {e}")
                continue
    
    return sorted(list(set(rows)))  # Remove duplicates and sort


def _trigger_processing_job(
    source: Dict,
    process_mode: str,
    max_papers: int,
    selected_rows: Optional[List[int]] = None
) -> Dict:
    """Trigger an on-demand processing job."""
    job_id = None  # Initialize for error handling
    try:
        # Get product-based credentials
        product_id = source.get('product_id')
        if not product_id:
            return {'success': False, 'error': 'No product associated with this data source'}
        
        product_api_keys = get_product_api_keys(product_id)
        google_credentials = product_api_keys.get('GOOGLE_CREDENTIALS')
        
        if not google_credentials:
            return {'success': False, 'error': 'Google credentials not configured for this product. Please add them in the Products tab.'}
        
        # Load sheet data
        sheet_data = load_sheet_data(
            source['sheet_url'],
            source['sheet_tab'],
            google_credentials
        )
        
        total_rows = len(sheet_data)
        
        # Determine which rows to process
        if process_mode == "New Papers Only":
            # Use hash-based detection to find unprocessed papers
            from utils.db.documents import get_processed_identifiers_for_source
            from utils.row_identifier import get_unprocessed_row_indices
            from utils.database import get_column_mapping_dict
            
            column_mappings = get_column_mapping_dict(source['id'])
            processed_ids = get_processed_identifiers_for_source(source['id'])
            
            rows_to_process = get_unprocessed_row_indices(
                sheet_data=sheet_data,
                column_mappings=column_mappings,
                processed_identifiers=processed_ids,
                max_papers=max_papers
            )
        elif process_mode == "Specific Rows":
            if not selected_rows:
                return {'success': False, 'error': 'No rows specified'}
            rows_to_process = [r for r in selected_rows if r < total_rows][:max_papers]
        else:  # All Papers
            rows_to_process = list(range(0, min(max_papers, total_rows)))
        
        if not rows_to_process:
            return {'success': False, 'error': 'No papers to process'}
        
        # Build configuration
        config = get_product_config_from_source(source['id'])
        config['google_credentials'] = google_credentials
        
        # Prepare for pipeline
        source_configs = [{
            'source_id': source['id'],
            'data': sheet_data,
            'selected_indices': rows_to_process
        }]
        
        # Import and trigger pipeline
        from utils.multi_source_pipeline import process_multi_source_pipeline
        
        # Trigger async processing
        import uuid
        job_id = str(uuid.uuid4())
        
        # Create Celery job record
        from utils.db.jobs import create_celery_job
        create_celery_job(
            task_id=job_id,
            task_name=f"On-Demand: {source['name']}",
            source_id=source['id'],
            submitted_by='manual'
        )
        
        # For now, process synchronously (could be made async with Celery later)
        results = process_multi_source_pipeline(
            source_configs=source_configs,
            config=config,
            progress_callback=None,
            preview_mode=False
        )
        
        # Update job status
        from utils.db.jobs import update_celery_job_status
        update_celery_job_status(
            job_id,
            'completed',
            result=results
        )
        
        return {
            'success': True,
            'job_id': job_id,
            'paper_count': len(rows_to_process)
        }
        
    except Exception as e:
        # Update job status to failed if job was created
        if job_id is not None:
            try:
                from utils.db.jobs import update_celery_job_status
                update_celery_job_status(
                    job_id,
                    'failed',
                    error=str(e)
                )
            except:
                pass  # Don't fail the error response if we can't update status
        
        logger.exception(f"Error triggering processing job: {e}")
        return {'success': False, 'error': str(e)}


# ============================================
# TAB 3: JOB HISTORY
# ============================================

def _render_job_history():
    """Render the job history tab."""
    st.subheader("Job History & Re-Processing")
    
    # Filters
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        status_filter_hist = st.selectbox(
            "Status:",
            ["All", "Completed", "Failed", "Cancelled"],
            key="history_status_filter"
        )
        
        # Reset page if filter changed
        if status_filter_hist != st.session_state.history_last_filter:
            st.session_state.job_page_history = 1
            st.session_state.history_last_filter = status_filter_hist
    
    with col2:
        limit = st.number_input("Total jobs to load:", min_value=10, max_value=2000, value=100)
    
    with col3:
        jobs_per_page_hist = st.selectbox(
            "Jobs per page:",
            [10, 25, 50, 100],
            index=1,
            key="history_jobs_per_page"
        )
        
        # Reset page if page size changed
        if jobs_per_page_hist != st.session_state.history_last_page_size:
            st.session_state.job_page_history = 1
            st.session_state.history_last_page_size = jobs_per_page_hist
    
    with col4:
        if st.button("🔄 Refresh History"):
            st.session_state.job_page_history = 1
            st.rerun()
    
    # Get jobs
    try:
        if status_filter_hist == "All":
            jobs = get_all_celery_jobs(limit=limit)
        else:
            jobs = get_all_celery_jobs(limit=limit, status_filter=status_filter_hist.lower())
    except Exception as e:
        st.error(f"Error loading job history: {str(e)}")
        return
    
    if not jobs:
        st.info("No job history found.")
        return
    
    # Pagination for history
    total_jobs = len(jobs)
    total_pages = max(1, (total_jobs + jobs_per_page_hist - 1) // jobs_per_page_hist)
    
    # Clamp page number to valid range
    if st.session_state.job_page_history > total_pages:
        st.session_state.job_page_history = max(1, total_pages)
    
    if total_pages > 1:
        col1, col2, col3 = st.columns([2, 6, 2])
        with col1:
            if st.button("⬅️ Prev", disabled=st.session_state.job_page_history <= 1, key="hist_prev"):
                st.session_state.job_page_history -= 1
                st.rerun()
        with col2:
            st.markdown(f"**Page {st.session_state.job_page_history} of {total_pages}** (Total: {total_jobs} jobs)")
        with col3:
            if st.button("Next ➡️", disabled=st.session_state.job_page_history >= total_pages, key="hist_next"):
                st.session_state.job_page_history += 1
                st.rerun()
    else:
        st.markdown(f"**Showing {total_jobs} jobs**")
    
    st.markdown("---")
    
    # Calculate pagination slice
    start_idx = (st.session_state.job_page_history - 1) * jobs_per_page_hist
    end_idx = min(start_idx + jobs_per_page_hist, total_jobs)
    page_jobs = jobs[start_idx:end_idx]
    
    # Display jobs as table
    job_data = []
    for job in page_jobs:
        job_data.append({
            'Task ID': job.get('task_id', '')[:12] + '...',
            'Task Name': job.get('task_name', ''),
            'Status': job.get('status', ''),
            'Created': job.get('created_at', ''),
            'Completed': job.get('completed_at', '') or '-',
            'Submitted By': job.get('submitted_by', 'system')
        })
    
    if job_data:
        df = pd.DataFrame(job_data)
        st.dataframe(df, use_container_width=True)
    
    # Detailed view selector (guard against empty page_jobs)
    if page_jobs:
        st.markdown("---")
        st.markdown("### Job Details")
        
        job_ids = [j.get('task_id', '') for j in page_jobs]
        job_labels = [f"{j.get('task_name', 'Unknown')} - {j.get('task_id', '')[:12]}..." for j in page_jobs]
        
        selected_job_label = st.selectbox("Select job for details:", job_labels)
        selected_job_idx = job_labels.index(selected_job_label)
        selected_job = page_jobs[selected_job_idx]
        
        # Display selected job details
        _render_job_details(selected_job)
    else:
        st.info("No jobs on this page. Try adjusting your filters or page number.")


def _render_job_details(job: Dict):
    """Render detailed view of a single job."""
    st.markdown("#### Job Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"**Task ID:** `{job.get('task_id', '')}`")
        st.markdown(f"**Task Name:** {job.get('task_name', '')}")
        st.markdown(f"**Status:** {job.get('status', '').upper()}")
        st.markdown(f"**Submitted By:** {job.get('submitted_by', 'system')}")
    
    with col2:
        st.markdown(f"**Created:** {job.get('created_at', '')}")
        st.markdown(f"**Updated:** {job.get('updated_at', '')}")
        st.markdown(f"**Completed:** {job.get('completed_at', '') or 'Not completed'}")
        
        # Duration
        if job.get('created_at') and job.get('completed_at'):
            try:
                created = pd.to_datetime(job['created_at'])
                completed = pd.to_datetime(job['completed_at'])
                duration = completed - created
                st.markdown(f"**Duration:** {duration}")
            except (ValueError, KeyError, TypeError) as e:
                logger.warning(f"Could not calculate duration for job {job.get('task_id')}: {e}")
                st.markdown("**Duration:** N/A")
            except Exception as e:
                logger.error(f"Unexpected error calculating duration: {e}")
                st.markdown("**Duration:** N/A")
    
    # Progress
    if job.get('progress_total', 0) > 0:
        st.markdown("#### Progress")
        progress_pct = int((job.get('progress_current', 0) / job['progress_total']) * 100)
        st.progress(job.get('progress_current', 0) / job['progress_total'], text=f"{progress_pct}%")
        if job.get('progress_message'):
            st.info(job['progress_message'])
    
    # Error message
    if job.get('error_message'):
        st.markdown("#### Error")
        st.error(job['error_message'])
    
    # Result
    if job.get('result'):
        st.markdown("#### Result")
        st.json(job['result'])
    
    # Retry button for failed/cancelled jobs
    if job.get('status', '').lower() in ['failed', 'cancelled']:
        st.markdown("---")
        if st.button("🔄 Retry This Job", key=f"retry_detail_{job.get('task_id')}", type="primary"):
            _retry_failed_job(job)

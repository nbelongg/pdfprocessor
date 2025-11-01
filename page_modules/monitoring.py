"""
Monitoring page module for cost tracking and system health.

This module provides:
- API cost summary (LlamaParse, OpenAI, Pinecone)
- Daily cost breakdown charts
- Queue depth monitoring with alerts
- Failed task queue viewer
- System health metrics
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any

from utils.monitoring import (
    get_cost_summary, get_daily_costs, get_queue_depth, get_failed_tasks
)
from components.common import info_box, error_message


def render_monitoring_page():
    """Render the monitoring dashboard page."""
    st.title("📊 System Monitoring & Costs")
    
    # Create tabs for different monitoring views
    tab1, tab2, tab3, tab4 = st.tabs([
        "💰 Cost Summary",
        "📈 Daily Costs",
        "📋 Queue Status",
        "❌ Failed Tasks"
    ])
    
    with tab1:
        render_cost_summary()
    
    with tab2:
        render_daily_costs()
    
    with tab3:
        render_queue_status()
    
    with tab4:
        render_failed_tasks()


def render_cost_summary():
    """Render the cost summary section."""
    st.subheader("💰 API Cost Summary")
    
    # Date range selector
    col1, col2 = st.columns([1, 3])
    with col1:
        days = st.selectbox(
            "Time Period",
            options=[7, 30, 60, 90],
            index=1,
            format_func=lambda x: f"Last {x} days"
        )
    
    with col2:
        if st.button("🔄 Refresh Data"):
            st.rerun()
    
    # Get cost summary
    try:
        summary = get_cost_summary(days)
        
        if summary['total_cost'] == 0:
            info_box("ℹ️ No API costs recorded in the selected period.")
            return
        
        # Display total cost
        st.metric(
            label="Total API Costs",
            value=f"${summary['total_cost']:.2f}",
            delta=f"{days} days"
        )
        
        st.markdown("---")
        
        # Service breakdown
        st.subheader("📊 Cost Breakdown by Service")
        
        services = summary.get('services', {})
        
        if not services:
            info_box("No service costs recorded yet.")
            return
        
        # Create metrics columns
        cols = st.columns(min(len(services), 3))
        
        for idx, (service_name, service_data) in enumerate(services.items()):
            col_idx = idx % 3
            with cols[col_idx]:
                # Format service name nicely
                display_name = service_name.replace('_', ' ').title()
                
                st.metric(
                    label=display_name,
                    value=f"${service_data['total_cost']:.4f}",
                    delta=f"{service_data['num_calls']} calls"
                )
                
                # Additional details in expander
                with st.expander("Details"):
                    st.write(f"**Total Units:** {service_data['total_units']:,.0f}")
                    st.write(f"**API Calls:** {service_data['num_calls']:,}")
                    if service_data['first_call']:
                        st.write(f"**First Call:** {service_data['first_call'].strftime('%Y-%m-%d %H:%M')}")
                    if service_data['last_call']:
                        st.write(f"**Last Call:** {service_data['last_call'].strftime('%Y-%m-%d %H:%M')}")
        
        st.markdown("---")
        
        # Cost projections
        st.subheader("📈 Monthly Projection")
        
        avg_daily_cost = summary['total_cost'] / days
        monthly_projection = avg_daily_cost * 30
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric(
                label="Average Daily Cost",
                value=f"${avg_daily_cost:.2f}"
            )
        
        with col2:
            st.metric(
                label="Projected Monthly Cost",
                value=f"${monthly_projection:.2f}"
            )
        
        with col3:
            # Annual projection
            annual_projection = monthly_projection * 12
            st.metric(
                label="Projected Annual Cost",
                value=f"${annual_projection:.2f}"
            )
        
        # Cost breakdown pie chart
        if len(services) > 0:
            st.markdown("---")
            st.subheader("🍕 Cost Distribution")
            
            df_pie = pd.DataFrame([
                {'Service': name.replace('_', ' ').title(), 'Cost': data['total_cost']}
                for name, data in services.items()
            ])
            
            # Display as bar chart (Streamlit native)
            st.bar_chart(df_pie.set_index('Service'))
        
    except Exception as e:
        error_message(f"Error loading cost summary: {str(e)}")


def render_daily_costs():
    """Render daily cost breakdown."""
    st.subheader("📈 Daily Cost Breakdown")
    
    # Date range selector
    days = st.slider("Days to Display", min_value=7, max_value=90, value=30)
    
    try:
        daily_costs = get_daily_costs(days)
        
        if not daily_costs:
            info_box("No daily cost data available.")
            return
        
        # Convert to DataFrame
        df = pd.DataFrame(daily_costs)
        
        # Pivot for chart
        df_pivot = df.pivot_table(
            index='date',
            columns='service',
            values='total_cost',
            fill_value=0
        )
        
        # Rename columns for display
        df_pivot.columns = [col.replace('_', ' ').title() for col in df_pivot.columns]
        
        # Sort by date
        df_pivot = df_pivot.sort_index(ascending=True)
        
        # Display area chart
        st.area_chart(df_pivot)
        
        st.markdown("---")
        
        # Show detailed table
        with st.expander("📋 View Detailed Data"):
            # Format the table
            df_display = df.copy()
            df_display['service'] = df_display['service'].str.replace('_', ' ').str.title()
            df_display['total_cost'] = df_display['total_cost'].apply(lambda x: f"${x:.4f}")
            df_display['total_units'] = df_display['total_units'].apply(lambda x: f"{x:,.0f}")
            
            st.dataframe(
                df_display[['date', 'service', 'total_units', 'total_cost']],
                use_container_width=True
            )
        
    except Exception as e:
        error_message(f"Error loading daily costs: {str(e)}")


def render_queue_status():
    """Render Celery queue status and monitoring."""
    st.subheader("📋 Celery Queue Status")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Refresh Queue"):
            st.rerun()
    
    try:
        queue_stats = get_queue_depth()
        
        if 'error' in queue_stats:
            error_message(f"Cannot connect to Celery: {queue_stats['error']}")
            st.info("💡 Make sure Celery workers are running.")
            return
        
        # Display metrics
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Active Tasks",
                value=queue_stats['active']
            )
        
        with col2:
            st.metric(
                label="Scheduled Tasks",
                value=queue_stats['scheduled']
            )
        
        with col3:
            st.metric(
                label="Reserved Tasks",
                value=queue_stats['reserved']
            )
        
        with col4:
            total = queue_stats['total_pending']
            st.metric(
                label="Total Pending",
                value=total,
                delta="⚠️ HIGH" if total > 100 else "✅ Normal"
            )
        
        # Alert if queue is backing up
        if total > 100:
            st.warning(
                f"⚠️ **Queue Depth Alert:** {total} tasks pending. "
                f"Consider adding more workers or investigating slow processing."
            )
        elif total > 50:
            st.info(
                f"ℹ️ Queue depth is moderate ({total} tasks). Monitoring recommended."
            )
        else:
            st.success("✅ Queue depth is normal. System processing smoothly.")
        
        # Processing capacity info
        st.markdown("---")
        st.subheader("⚙️ Processing Capacity")
        
        st.info(
            """
            **Current Configuration:**
            - 3 Celery workers (concurrency=3)
            - Daily processing limit: 300 papers/day
            - Average processing time: 3-7 minutes per paper
            - Theoretical capacity: ~12 papers/hour (4 per worker)
            """
        )
        
    except Exception as e:
        error_message(f"Error checking queue status: {str(e)}")


def render_failed_tasks():
    """Render failed tasks queue viewer."""
    st.subheader("❌ Failed Tasks (Dead Letter Queue)")
    
    st.write(
        "Tasks that failed after all retry attempts are logged here for manual review."
    )
    
    # Limit selector
    limit = st.slider("Number of recent failures to show", min_value=10, max_value=200, value=50)
    
    try:
        failed_tasks = get_failed_tasks(limit)
        
        if not failed_tasks:
            st.success("✅ No failed tasks! All processing successful.")
            return
        
        # Display count
        st.warning(f"⚠️ Found {len(failed_tasks)} failed tasks")
        
        # Convert to DataFrame for display
        df = pd.DataFrame(failed_tasks)
        
        # Display summary metrics
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Total Failures", len(failed_tasks))
        
        with col2:
            unique_errors = df['error_type'].nunique()
            st.metric("Unique Error Types", unique_errors)
        
        with col3:
            total_retries = df['retry_count'].sum()
            st.metric("Total Retry Attempts", total_retries)
        
        st.markdown("---")
        
        # Group by error type
        st.subheader("Error Type Breakdown")
        error_counts = df['error_type'].value_counts()
        st.bar_chart(error_counts)
        
        st.markdown("---")
        
        # Display detailed table
        st.subheader("Detailed Failure Log")
        
        for idx, task in enumerate(failed_tasks):
            with st.expander(
                f"🔴 {task['task_name']} - {task['error_type']} "
                f"({task['created_at'].strftime('%Y-%m-%d %H:%M')})"
            ):
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write(f"**Task ID:** `{task['task_id']}`")
                    st.write(f"**Job ID:** `{task['job_id']}`")
                    st.write(f"**Retry Count:** {task['retry_count']}")
                
                with col2:
                    st.write(f"**Error Type:** {task['error_type']}")
                    st.write(f"**Failed At:** {task['created_at']}")
                    if task['last_retry_at']:
                        st.write(f"**Last Retry:** {task['last_retry_at']}")
                
                st.markdown("**Task Arguments:**")
                st.json(task['task_args'])
                
                st.markdown("**Error Message:**")
                st.code(task['error_message'], language='python')
        
    except Exception as e:
        error_message(f"Error loading failed tasks: {str(e)}")

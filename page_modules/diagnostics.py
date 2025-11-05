"""
Diagnostics page - Environment, Redis, Database connection information.

This page helps debug production vs dev environment issues by showing
comprehensive system configuration and connection status.
"""
import streamlit as st
import os
from datetime import datetime
import logging
from components.common import page_header

logger = logging.getLogger(__name__)


def render():
    """Render the Diagnostics page."""
    page_header("System Diagnostics", "Environment detection, Redis config, and database status")
    
    st.markdown("""
    This page helps diagnose production vs development environment issues by showing:
    - Environment detection results
    - Redis configuration and key prefixing
    - Database connection status
    - Celery worker information
    """)
    
    # Environment Detection
    st.markdown("---")
    st.subheader("🌍 Environment Detection")
    
    replit_deployment = os.getenv('REPLIT_DEPLOYMENT', 'not set')
    repl_slug = os.getenv('REPL_SLUG', 'not set')
    replit_domains = os.getenv('REPLIT_DOMAINS', 'not set')
    
    # Determine environment
    is_production = (
        replit_deployment == '1' or
        repl_slug.endswith('.replit.app') or
        'replit.app' in replit_domains
    )
    
    env_name = 'PRODUCTION' if is_production else 'DEVELOPMENT'
    redis_prefix = 'prod' if is_production else 'dev'
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Detection Variables")
        st.code(f"""
REPLIT_DEPLOYMENT: {replit_deployment}
REPL_SLUG: {repl_slug[:50]}{'...' if len(repl_slug) > 50 else ''}
REPLIT_DOMAINS: {replit_domains[:50]}{'...' if len(replit_domains) > 50 else ''}
        """)
    
    with col2:
        st.markdown("### Detection Result")
        if is_production:
            st.success(f"**Environment:** {env_name} ✅")
        else:
            st.info(f"**Environment:** {env_name}")
        
        st.code(f"""
Redis Key Prefix: {redis_prefix}_
Example Key: {redis_prefix}_celery-task-meta-abc123
        """)
    
    # Redis Configuration
    st.markdown("---")
    st.subheader("📦 Redis Configuration")
    
    redis_host = os.getenv('REDIS_HOST', 'not set')
    redis_port = os.getenv('REDIS_PORT', 'not set')
    redis_use_tls = os.getenv('REDIS_USE_TLS', 'not set')
    redis_password_set = 'SET' if os.getenv('REDIS_PASSWORD') else 'NOT SET'
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Connection Info")
        st.code(f"""
Host: {redis_host[:60]}{'...' if len(redis_host) > 60 else ''}
Port: {redis_port}
TLS: {redis_use_tls}
Password: {redis_password_set}
Database: 0 (Upstash limitation)
        """)
    
    with col2:
        st.markdown("### Expected Behavior")
        st.code(f"""
UI Task Submission:
  → Creates job in DB
  → Enqueues to: {redis_prefix}_*
  → Worker listens: {redis_prefix}_*

Worker Environment: {env_name}
Worker consumes: {redis_prefix}_* tasks
        """)
    
    # Database Configuration
    st.markdown("---")
    st.subheader("💾 Database Configuration")
    
    database_url_set = 'SET' if os.getenv('DATABASE_URL') else 'NOT SET'
    pgdatabase = os.getenv('PGDATABASE', 'not set')
    pghost = os.getenv('PGHOST', 'not set')
    pgport = os.getenv('PGPORT', 'not set')
    pguser = os.getenv('PGUSER', 'not set')
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("### Database Credentials")
        st.code(f"""
DATABASE_URL: {database_url_set}
PGDATABASE: {pgdatabase}
PGHOST: {pghost}
PGPORT: {pgport}
PGUSER: {pguser}
        """)
    
    with col2:
        st.markdown("### Connection Test")
        try:
            # Test database connection
            from utils.db.jobs import get_all_celery_jobs
            jobs = get_all_celery_jobs(limit=1)
            st.success("✅ Database connection: **WORKING**")
            st.info(f"Can query celery_jobs table")
        except Exception as e:
            st.error(f"❌ Database connection: **FAILED**")
            st.error(f"Error: {str(e)}")
    
    # Celery Configuration
    st.markdown("---")
    st.subheader("⚙️ Celery Configuration")
    
    try:
        from celeryconfig import env_prefix, celery_app
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("### Celery Settings")
            st.code(f"""
Environment Prefix: {env_prefix}_
Broker: Redis (TLS: {redis_use_tls})
Result Backend: Redis
Queues:
  - batch_processing
  - pdf_processing
  - metadata_updates
            """)
        
        with col2:
            st.markdown("### Key Prefixing")
            broker_opts = celery_app.conf.get('broker_transport_options', {})
            result_opts = celery_app.conf.get('result_backend_transport_options', {})
            
            st.code(f"""
Broker Key Prefix: {broker_opts.get('global_keyprefix', 'not set')}
Result Key Prefix: {result_opts.get('global_keyprefix', 'not set')}

This ensures production and dev
use different Redis key spaces!
            """)
    
    except Exception as e:
        st.error(f"Error loading Celery config: {str(e)}")
    
    # Diagnostic Summary
    st.markdown("---")
    st.subheader("📊 Diagnostic Summary")
    
    if is_production:
        st.info(f"""
        **Production Environment Detected**
        
        ✅ UI submits tasks to Redis with `prod_` prefix
        ✅ Production worker should consume `prod_*` tasks
        ⚠️ Verify production worker is running (not just dev worker)
        ⚠️ Check worker logs show "Environment: PRODUCTION"
        """)
    else:
        st.info(f"""
        **Development Environment Detected**
        
        ✅ UI submits tasks to Redis with `dev_` prefix
        ✅ Development worker should consume `dev_*` tasks
        ⚠️ Production tasks use `prod_` prefix (won't be picked up here)
        """)
    
    # Timestamp
    st.markdown("---")
    st.caption(f"Diagnostic generated at: {datetime.utcnow().isoformat()} UTC")

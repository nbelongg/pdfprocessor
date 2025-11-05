"""
Admin page for running database backfill operations.
This page allows running the processed_papers backfill script from the UI.
"""

import streamlit as st
import sys
from io import StringIO
from datetime import datetime
import psycopg2.extras
from utils.db.connection import get_db_connection
from utils.deduplication import generate_content_hash
from utils.metadata_fingerprint import calculate_metadata_fingerprint
from typing import Dict, Set


def get_database_stats():
    """Get current database statistics."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        cur.execute("""
            SELECT 
                (SELECT COUNT(*) FROM parsed_documents) as parsed_docs,
                (SELECT COUNT(*) FROM processed_papers) as processed_papers,
                (SELECT COUNT(DISTINCT file_id) FROM processing_chunks) as docs_with_chunks,
                (SELECT COUNT(*) FROM processing_chunks) as total_chunks
        """)
        
        stats = cur.fetchone()
        return {
            'parsed_documents': stats['parsed_docs'],
            'processed_papers': stats['processed_papers'],
            'docs_with_chunks': stats['docs_with_chunks'],
            'total_chunks': stats['total_chunks']
        }
    finally:
        cur.close()
        conn.close()


def get_missing_count():
    """Calculate how many records need to be backfilled."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get file_ids with chunks
        cur.execute("""
            SELECT DISTINCT file_id 
            FROM processing_chunks
            WHERE file_id IS NOT NULL
        """)
        with_chunks = {row['file_id'] for row in cur.fetchall()}
        
        # Get existing processed_papers
        cur.execute("""
            SELECT DISTINCT drive_file_id 
            FROM processed_papers
            WHERE drive_file_id IS NOT NULL
        """)
        existing = {row['drive_file_id'] for row in cur.fetchall()}
        
        missing = with_chunks - existing
        return len(missing), list(missing)
        
    finally:
        cur.close()
        conn.close()


def run_backfill(dry_run=True, progress_container=None):
    """
    Run the backfill operation.
    
    Args:
        dry_run: If True, only preview changes
        progress_container: Streamlit container for progress updates
    """
    results = {
        'total': 0,
        'success': 0,
        'skipped': 0,
        'errors': 0,
        'details': []
    }
    
    # Get missing file_ids
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get file_ids with chunks
        cur.execute("""
            SELECT DISTINCT file_id 
            FROM processing_chunks
            WHERE file_id IS NOT NULL
        """)
        with_chunks = {row['file_id'] for row in cur.fetchall()}
        
        # Get existing processed_papers
        cur.execute("""
            SELECT DISTINCT drive_file_id 
            FROM processed_papers
            WHERE drive_file_id IS NOT NULL
        """)
        existing = {row['drive_file_id'] for row in cur.fetchall()}
        
        missing_ids = sorted(with_chunks - existing)
        results['total'] = len(missing_ids)
        
        if not missing_ids:
            return results
        
        # Process each missing record
        for idx, file_id in enumerate(missing_ids, 1):
            if progress_container:
                progress_container.progress(
                    idx / len(missing_ids),
                    text=f"Processing {idx}/{len(missing_ids)}: {file_id[:20]}..."
                )
            
            try:
                # Get metadata from parsed_documents
                cur.execute("""
                    SELECT file_id, filename, file_metadata, created_at
                    FROM parsed_documents
                    WHERE file_id = %s
                """, (file_id,))
                
                parsed_row = cur.fetchone()
                if not parsed_row:
                    results['skipped'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'status': 'skipped',
                        'reason': 'No parsed_document found'
                    })
                    continue
                
                # Get chunk info
                cur.execute("""
                    SELECT namespace, metadata, created_at
                    FROM processing_chunks
                    WHERE file_id = %s
                    LIMIT 1
                """, (file_id,))
                
                chunk_row = cur.fetchone()
                if not chunk_row:
                    results['skipped'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'status': 'skipped',
                        'reason': 'No chunks found'
                    })
                    continue
                
                # Extract metadata
                file_metadata = parsed_row['file_metadata'] or {}
                chunk_metadata = chunk_row['metadata'] or {}
                
                paper_title = (
                    file_metadata.get('paper_title') or 
                    chunk_metadata.get('paper_title') or 
                    parsed_row['filename'] or
                    'Unknown'
                )
                
                authors = (
                    file_metadata.get('authors') or 
                    chunk_metadata.get('authors') or 
                    ''
                )
                
                source_id = chunk_metadata.get('source_id')
                source_name = chunk_metadata.get('source', 'Unknown')
                
                # Generate content hash
                content_hash = generate_content_hash(paper_title, authors)
                
                # Get namespace
                namespace = chunk_row['namespace'] or 'default'
                
                # Build complete metadata
                complete_metadata = {
                    'paper_title': paper_title,
                    'authors': authors,
                    'publication_year': file_metadata.get('publication_year') or chunk_metadata.get('publication_year'),
                    'topic': file_metadata.get('topic') or chunk_metadata.get('topic'),
                    'source': source_name,
                    'source_id': source_id,
                }
                
                # Calculate fingerprint
                metadata_fingerprint = calculate_metadata_fingerprint(complete_metadata)
                
                # Use earliest timestamp
                created_at = chunk_row['created_at'] or parsed_row['created_at']
                
                if dry_run:
                    results['success'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'status': 'would_create',
                        'title': paper_title[:60],
                        'authors': authors[:60],
                        'source': source_name
                    })
                else:
                    # Actually create the record
                    cur.execute("""
                        INSERT INTO processed_papers (
                            drive_file_id,
                            content_hash,
                            paper_title,
                            authors,
                            metadata,
                            pinecone_namespace,
                            processed_at,
                            metadata_fingerprint
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (drive_file_id) DO NOTHING
                        RETURNING id
                    """, (
                        file_id,
                        content_hash,
                        paper_title,
                        authors,
                        complete_metadata,
                        namespace,
                        created_at,
                        metadata_fingerprint
                    ))
                    
                    result = cur.fetchone()
                    if result:
                        paper_id = result['id']
                        
                        # Create source_paper_mapping if we have source_id
                        if source_id:
                            cur.execute("""
                                INSERT INTO source_paper_mapping (
                                    source_id,
                                    paper_id,
                                    row_number,
                                    created_at
                                ) VALUES (%s, %s, %s, %s)
                                ON CONFLICT (source_id, paper_id) DO NOTHING
                            """, (source_id, paper_id, 0, created_at))
                        
                        conn.commit()
                        results['success'] += 1
                        results['details'].append({
                            'file_id': file_id,
                            'status': 'created',
                            'paper_id': paper_id,
                            'title': paper_title[:60],
                            'source': source_name
                        })
                    else:
                        results['skipped'] += 1
                        results['details'].append({
                            'file_id': file_id,
                            'status': 'already_exists',
                            'title': paper_title[:60]
                        })
                        
            except Exception as e:
                conn.rollback()
                results['errors'] += 1
                results['details'].append({
                    'file_id': file_id,
                    'status': 'error',
                    'error': str(e)
                })
        
        return results
        
    finally:
        cur.close()
        conn.close()


def render():
    """Render the admin backfill page."""
    st.title("🔧 Admin: Database Backfill")
    
    st.markdown("""
    This page allows you to backfill missing `processed_papers` records for PDFs that 
    completed processing but didn't get deduplication records due to Celery timeouts.
    """)
    
    # Show database statistics
    st.subheader("📊 Current Database Statistics")
    
    with st.spinner("Loading database statistics..."):
        stats = get_database_stats()
        missing_count, missing_ids = get_missing_count()
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Parsed Documents", stats['parsed_documents'])
    
    with col2:
        st.metric("Processed Papers", stats['processed_papers'])
    
    with col3:
        st.metric("Docs with Chunks", stats['docs_with_chunks'])
    
    with col4:
        st.metric("Missing Records", missing_count, 
                  delta=None if missing_count == 0 else f"-{missing_count}",
                  delta_color="inverse")
    
    st.markdown("---")
    
    # Show analysis
    if missing_count == 0:
        st.success("✅ All processed PDFs have deduplication records! Nothing to backfill.")
        return
    
    # Show missing records
    st.warning(f"⚠️ Found {missing_count} PDFs with chunks but missing deduplication records")
    
    with st.expander(f"View {missing_count} missing file IDs"):
        for file_id in missing_ids[:50]:  # Show first 50
            st.code(file_id, language=None)
        if len(missing_ids) > 50:
            st.info(f"... and {len(missing_ids) - 50} more")
    
    st.markdown("---")
    
    # Dry-run section
    st.subheader("🔍 Step 1: Preview Changes (Dry-Run)")
    
    st.markdown("""
    First, run a dry-run to see what would be backfilled **without making any changes** to the database.
    """)
    
    if st.button("🔍 Run Dry-Run (Safe Preview)", type="secondary", use_container_width=True):
        st.info("Running dry-run preview...")
        progress_bar = st.progress(0, text="Starting...")
        
        with st.spinner("Analyzing missing records..."):
            results = run_backfill(dry_run=True, progress_container=progress_bar)
        
        progress_bar.empty()
        
        st.success(f"✅ Dry-run complete!")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Would Create", results['success'])
        with col2:
            st.metric("Would Skip", results['skipped'])
        with col3:
            st.metric("Errors", results['errors'])
        
        # Show details
        with st.expander(f"📋 View {len(results['details'])} Preview Details"):
            for detail in results['details'][:20]:  # Show first 20
                if detail['status'] == 'would_create':
                    st.success(f"✅ Would create: {detail['title']} (Source: {detail['source']})")
                elif detail['status'] == 'skipped':
                    st.warning(f"⚠️ Would skip: {detail['file_id'][:20]}... - {detail['reason']}")
        
        st.info("💡 No changes were made. Use 'Execute Backfill' below to apply these changes.")
    
    st.markdown("---")
    
    # Execute section
    st.subheader("⚡ Step 2: Execute Backfill")
    
    st.markdown("""
    **⚠️ This will modify your database.** Make sure you've reviewed the dry-run results first.
    
    This will create missing `processed_papers` and `source_paper_mapping` records.
    """)
    
    # Confirmation checkbox
    confirm = st.checkbox("I have reviewed the dry-run and want to proceed with the backfill")
    
    if st.button("⚡ Execute Backfill", type="primary", disabled=not confirm, use_container_width=True):
        st.warning("🚀 Executing backfill... Please wait, do not close this page!")
        progress_bar = st.progress(0, text="Starting backfill...")
        
        with st.spinner("Creating missing records..."):
            results = run_backfill(dry_run=False, progress_container=progress_bar)
        
        progress_bar.empty()
        
        st.success(f"🎉 Backfill complete!")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Created", results['success'], delta=f"+{results['success']}")
        with col2:
            st.metric("Skipped", results['skipped'])
        with col3:
            st.metric("Errors", results['errors'])
        
        # Show success details
        if results['success'] > 0:
            st.success(f"✅ Successfully created {results['success']} processed_papers records!")
            
            with st.expander(f"📋 View {len(results['details'])} Details"):
                for detail in results['details']:
                    if detail['status'] == 'created':
                        st.success(f"✅ Created ID {detail['paper_id']}: {detail['title']}")
                    elif detail['status'] == 'error':
                        st.error(f"❌ Error: {detail['file_id'][:20]}... - {detail['error']}")
        
        # Refresh stats
        st.markdown("---")
        st.subheader("📊 Updated Statistics")
        with st.spinner("Refreshing..."):
            new_stats = get_database_stats()
            new_missing_count, _ = get_missing_count()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Parsed Documents", new_stats['parsed_documents'])
        with col2:
            st.metric("Processed Papers", new_stats['processed_papers'], 
                      delta=f"+{new_stats['processed_papers'] - stats['processed_papers']}")
        with col3:
            st.metric("Docs with Chunks", new_stats['docs_with_chunks'])
        with col4:
            st.metric("Missing Records", new_missing_count,
                      delta=f"{new_missing_count - missing_count}")
        
        if new_missing_count == 0:
            st.balloons()
            st.success("🎉 All processed PDFs now have deduplication records! Your database is fully synchronized.")

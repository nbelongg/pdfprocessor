"""
Admin page for running database backfill operations.
This page allows running the processed_papers backfill script from the UI.
"""

import streamlit as st
import sys
import json
from io import StringIO
from datetime import datetime
import psycopg2
import psycopg2.extras
from utils.db.connection import get_db_connection
from utils.deduplication import generate_content_hash
from typing import Dict, Set

# Try to import metadata_fingerprint, fallback to None if not available
try:
    from utils.metadata_fingerprint import calculate_metadata_fingerprint
except ImportError:
    calculate_metadata_fingerprint = None


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


def get_table_columns(cur, table_name):
    """Get list of columns for a table."""
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (table_name,))
    return [row['column_name'] for row in cur.fetchall()]


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
    
    # Detect which columns exist in processed_papers table
    available_columns = get_table_columns(cur, 'processed_papers')
    has_metadata_fingerprint = 'metadata_fingerprint' in available_columns
    has_processed_at = 'processed_at' in available_columns
    
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
                
                # Extract metadata - try multiple possible field names
                file_metadata = parsed_row['file_metadata'] or {}
                chunk_metadata = chunk_row['metadata'] or {}
                
                # Try multiple possible keys for paper title
                paper_title = (
                    file_metadata.get('paper_title') or 
                    file_metadata.get('title') or
                    chunk_metadata.get('paper_title') or 
                    chunk_metadata.get('title') or
                    parsed_row['filename'] or
                    f"PDF {file_id[:8]}..."
                )
                
                # Try multiple possible keys for authors
                authors = (
                    file_metadata.get('authors') or 
                    chunk_metadata.get('authors') or 
                    chunk_metadata.get('author') or
                    ''
                )
                
                # Try multiple possible keys for source
                source_id = (
                    chunk_metadata.get('source_id') or
                    file_metadata.get('source_id')
                )
                # Ensure source_id is an integer or None
                if source_id and not isinstance(source_id, int):
                    try:
                        source_id = int(source_id)
                    except (ValueError, TypeError):
                        source_id = None
                
                source_name = (
                    chunk_metadata.get('source') or 
                    file_metadata.get('source') or
                    chunk_metadata.get('source_name') or
                    f"Source {source_id}" if source_id else "Unknown"
                )
                
                # Generate content hash
                content_hash = generate_content_hash(paper_title, authors)
                
                # Get namespace
                namespace = chunk_row['namespace'] or 'default'
                
                # Build complete metadata - ensure all values are JSON serializable
                complete_metadata = {
                    'paper_title': str(paper_title) if paper_title else '',
                    'authors': str(authors) if authors else '',
                    'publication_year': file_metadata.get('publication_year') or chunk_metadata.get('publication_year'),
                    'topic': file_metadata.get('topic') or chunk_metadata.get('topic'),
                    'source': str(source_name) if source_name else 'Unknown',
                    'source_id': source_id if source_id else None,
                }
                
                # Calculate fingerprint (if available)
                metadata_fingerprint = None
                if calculate_metadata_fingerprint:
                    try:
                        metadata_fingerprint = calculate_metadata_fingerprint(complete_metadata)
                    except Exception as e:
                        # Fingerprint calculation failed, continue without it
                        pass
                
                # Use earliest timestamp, fallback to now if both are None
                created_at = chunk_row['created_at'] or parsed_row['created_at']
                if not created_at:
                    created_at = datetime.now()
                
                if dry_run:
                    results['success'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'status': 'would_create',
                        'title': paper_title[:80] if paper_title else f"File {file_id[:12]}...",
                        'authors': authors[:60] if authors else '',
                        'source': source_name,
                        'file_id_short': file_id[:12]
                    })
                else:
                    # Actually create the record
                    # Convert metadata dict to JSON string for PostgreSQL JSONB
                    metadata_json = json.dumps(complete_metadata)
                    
                    # Build INSERT query based on available columns
                    if has_metadata_fingerprint and has_processed_at:
                        # Full schema with both columns
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
                            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s, %s)
                            ON CONFLICT (drive_file_id) DO NOTHING
                            RETURNING id
                        """, (
                            file_id,
                            content_hash,
                            paper_title,
                            authors,
                            metadata_json,
                            namespace,
                            created_at,
                            metadata_fingerprint
                        ))
                    elif has_processed_at:
                        # Has processed_at but not metadata_fingerprint
                        cur.execute("""
                            INSERT INTO processed_papers (
                                drive_file_id,
                                content_hash,
                                paper_title,
                                authors,
                                metadata,
                                pinecone_namespace,
                                processed_at
                            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                            ON CONFLICT (drive_file_id) DO NOTHING
                            RETURNING id
                        """, (
                            file_id,
                            content_hash,
                            paper_title,
                            authors,
                            metadata_json,
                            namespace,
                            created_at
                        ))
                    elif has_metadata_fingerprint:
                        # Has metadata_fingerprint but not processed_at
                        cur.execute("""
                            INSERT INTO processed_papers (
                                drive_file_id,
                                content_hash,
                                paper_title,
                                authors,
                                metadata,
                                pinecone_namespace,
                                metadata_fingerprint
                            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s)
                            ON CONFLICT (drive_file_id) DO NOTHING
                            RETURNING id
                        """, (
                            file_id,
                            content_hash,
                            paper_title,
                            authors,
                            metadata_json,
                            namespace,
                            metadata_fingerprint
                        ))
                    else:
                        # Minimal schema - neither column
                        cur.execute("""
                            INSERT INTO processed_papers (
                                drive_file_id,
                                content_hash,
                                paper_title,
                                authors,
                                metadata,
                                pinecone_namespace
                            ) VALUES (%s, %s, %s, %s, %s::jsonb, %s)
                            ON CONFLICT (drive_file_id) DO NOTHING
                            RETURNING id
                        """, (
                            file_id,
                            content_hash,
                            paper_title,
                            authors,
                            metadata_json,
                            namespace
                        ))
                    
                    result = cur.fetchone()
                    if result:
                        paper_id = result['id']
                        
                        # Create source_paper_mapping if we have valid source_id
                        if source_id and isinstance(source_id, int):
                            try:
                                cur.execute("""
                                    INSERT INTO source_paper_mapping (
                                        source_id,
                                        paper_id,
                                        row_number,
                                        created_at
                                    ) VALUES (%s, %s, %s, %s)
                                    ON CONFLICT (source_id, paper_id) DO NOTHING
                                """, (source_id, paper_id, 0, created_at))
                            except Exception as mapping_err:
                                # Log error but don't fail the whole operation
                                # The processed_papers record is already created
                                pass
                        
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
                        # Record was not inserted (conflict), this means it already exists
                        conn.commit()  # Commit the transaction
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
                    title_text = detail.get('title', 'Unknown')
                    source_text = detail.get('source', 'Unknown')
                    file_id_text = detail.get('file_id_short', detail.get('file_id', '')[:12])
                    st.success(f"✅ {title_text}\n   📂 File ID: `{file_id_text}...` | Source: {source_text}")
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
                        title_text = detail.get('title', 'Unknown')
                        st.success(f"✅ Created paper ID {detail['paper_id']}: {title_text}")
                    elif detail['status'] == 'error':
                        st.error(f"❌ Error: {detail['file_id'][:20]}... - {detail['error']}")
        
        # Show error details prominently
        if results['errors'] > 0:
            st.error(f"❌ {results['errors']} records failed to create!")
            
            with st.expander(f"⚠️ View {results['errors']} Error Details", expanded=True):
                error_count = 0
                for detail in results['details']:
                    if detail['status'] == 'error':
                        error_count += 1
                        st.error(f"**Error #{error_count}:** File ID: `{detail.get('file_id', 'unknown')[:20]}...`")
                        st.code(detail.get('error', 'Unknown error'), language=None)
                        if error_count >= 10:
                            st.warning(f"... and {results['errors'] - 10} more errors (showing first 10)")
        
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

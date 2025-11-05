"""
Admin page for running metadata enrichment migration on production database.

This migration backfills parsed_documents.file_metadata with complete Google Sheets
metadata from processed_papers table, making parsed_documents a single source of truth.
"""

import streamlit as st
import psycopg2
import psycopg2.extras
import json
from datetime import datetime
from typing import Dict, Any, List
from psycopg2.extras import Json

from utils.database import get_db_connection


def get_parsed_documents_stats():
    """Get statistics about parsed documents and enrichment status."""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Total parsed documents
        cur.execute("SELECT COUNT(*) as total FROM parsed_documents")
        total = cur.fetchone()['total']
        
        # Documents with paper_title and authors (enriched)
        cur.execute("""
            SELECT COUNT(*) as enriched
            FROM parsed_documents
            WHERE file_metadata->>'paper_title' IS NOT NULL
              AND file_metadata->>'authors' IS NOT NULL
        """)
        enriched = cur.fetchone()['enriched']
        
        # Documents without enrichment
        cur.execute("""
            SELECT COUNT(*) as missing
            FROM parsed_documents
            WHERE file_metadata->>'paper_title' IS NULL
               OR file_metadata->>'authors' IS NULL
        """)
        missing = cur.fetchone()['missing']
        
        return {
            'total': total,
            'enriched': enriched,
            'missing': missing
        }
    finally:
        cur.close()
        conn.close()


def get_processed_paper_metadata(cur, file_id: str) -> Dict[str, Any]:
    """
    Get Google Sheets metadata for a file from processed_papers table.
    Uses existing cursor instead of creating new connection.
    Returns enriched metadata dict or None if not found.
    """
    cur.execute("""
        SELECT 
            paper_title,
            authors,
            metadata,
            pinecone_namespace,
            first_processed_at,
            processing_count
        FROM processed_papers
        WHERE drive_file_id = %s
        LIMIT 1
    """, (file_id,))
    
    row = cur.fetchone()
    if not row:
        return None
    
    # Extract metadata from the row
    enrichment = {}
    
    # Add structured fields
    if row['paper_title']:
        enrichment['paper_title'] = row['paper_title']
    if row['authors']:
        enrichment['authors'] = row['authors']
    
    # Merge the full metadata JSONB
    if row['metadata']:
        enrichment.update(row['metadata'])
    
    # Add processing info
    enrichment['pinecone_namespace'] = row['pinecone_namespace']
    if row['first_processed_at']:
        enrichment['first_processed_at'] = row['first_processed_at'].isoformat()
    enrichment['processing_count'] = row['processing_count']
    
    # Ensure drive_url is present
    enrichment['drive_url'] = enrichment.get('drive_link') or f"https://drive.google.com/file/d/{file_id}/view"
    
    return enrichment


def merge_metadata(base: Dict, enrichment: Dict) -> Dict:
    """
    Merge enrichment metadata into base metadata.
    Google Sheets metadata takes precedence over Google Drive metadata.
    """
    merged = base.copy()
    merged.update(enrichment)
    return merged


def run_enrichment_migration(dry_run=True, progress_container=None):
    """
    Run the metadata enrichment migration.
    
    Args:
        dry_run: If True, only preview changes
        progress_container: Streamlit container for progress updates
    """
    results = {
        'total': 0,
        'enriched': 0,
        'already_rich': 0,
        'not_found': 0,
        'errors': 0,
        'details': []
    }
    
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    try:
        # Get all parsed documents
        cur.execute("""
            SELECT 
                file_id,
                filename,
                file_metadata
            FROM parsed_documents
            ORDER BY created_at
        """)
        
        parsed_docs = cur.fetchall()
        results['total'] = len(parsed_docs)
        
        if not parsed_docs:
            return results
        
        # Process each document
        for idx, doc in enumerate(parsed_docs, 1):
            if progress_container:
                progress_container.progress(
                    idx / len(parsed_docs),
                    text=f"Processing {idx}/{len(parsed_docs)}: {doc['filename'][:30]}..."
                )
            
            file_id = doc['file_id']
            filename = doc['filename']
            current_metadata = doc['file_metadata'] or {}
            
            try:
                # Check if already has Google Sheets metadata
                has_paper_title = 'paper_title' in current_metadata
                has_authors = 'authors' in current_metadata
                
                if has_paper_title and has_authors:
                    results['already_rich'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'filename': filename,
                        'status': 'already_enriched',
                        'title': current_metadata.get('paper_title', '')[:60]
                    })
                    continue
                
                # Get enrichment from processed_papers (reusing cursor)
                enrichment = get_processed_paper_metadata(cur, file_id)
                
                if not enrichment:
                    results['not_found'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'filename': filename,
                        'status': 'not_found',
                        'reason': 'No match in processed_papers table'
                    })
                    continue
                
                # Merge metadata
                merged = merge_metadata(current_metadata, enrichment)
                
                if dry_run:
                    results['enriched'] += 1
                    results['details'].append({
                        'file_id': file_id,
                        'filename': filename,
                        'status': 'would_enrich',
                        'title': merged.get('paper_title', '')[:60],
                        'authors': merged.get('authors', '')[:60],
                        'year': merged.get('publication_year', ''),
                        'topic': merged.get('topic', ''),
                        'fields_added': len(enrichment)
                    })
                else:
                    # Actually update the record
                    metadata_json = json.dumps(merged)
                    
                    cur.execute("""
                        UPDATE parsed_documents
                        SET file_metadata = %s::jsonb,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE file_id = %s
                    """, (metadata_json, file_id))
                    
                    if cur.rowcount > 0:
                        # Commit immediately to preserve this success
                        conn.commit()
                        results['enriched'] += 1
                        results['details'].append({
                            'file_id': file_id,
                            'filename': filename,
                            'status': 'enriched',
                            'title': merged.get('paper_title', '')[:60],
                            'authors': merged.get('authors', '')[:60],
                            'year': merged.get('publication_year', ''),
                            'fields_added': len(enrichment)
                        })
                    else:
                        results['errors'] += 1
                        results['details'].append({
                            'file_id': file_id,
                            'filename': filename,
                            'status': 'error',
                            'reason': 'No rows updated'
                        })
                        
            except Exception as e:
                # Roll back only this record's failed transaction
                conn.rollback()
                results['errors'] += 1
                results['details'].append({
                    'file_id': file_id,
                    'filename': filename,
                    'status': 'error',
                    'reason': str(e)
                })
        
        return results
        
    except Exception as e:
        # Roll back entire transaction on fatal error
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def render():
    """Render the metadata enrichment migration admin page."""
    st.title("🔧 Admin: Metadata Enrichment Migration")
    
    st.markdown("""
    This tool enriches your `parsed_documents` table with complete Google Sheets metadata 
    from the `processed_papers` table, making it a **single source of truth** for both 
    parsed content AND metadata.
    """)
    
    # Show current status
    st.subheader("📊 Current Status")
    
    with st.spinner("Checking database..."):
        stats = get_parsed_documents_stats()
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Documents", stats['total'])
    with col2:
        st.metric("Already Enriched", stats['enriched'], 
                  delta=f"{stats['enriched']/max(stats['total'], 1)*100:.1f}%")
    with col3:
        st.metric("Missing Metadata", stats['missing'], 
                  delta=f"{stats['missing']/max(stats['total'], 1)*100:.1f}%",
                  delta_color="inverse")
    
    st.markdown("---")
    
    # Benefits section
    with st.expander("✨ What This Migration Does", expanded=True):
        st.markdown("""
        **Enriches `parsed_documents.file_metadata` with:**
        - 📄 Paper title
        - 👥 Authors
        - 📅 Publication year
        - 🏷️ Topic/category
        - 🔗 Drive URL
        - 📊 Source information
        - ⚙️ Processing metadata
        
        **Benefits:**
        - ✅ **Single source of truth** - Everything in one table
        - ✅ **Re-chunking support** - Can re-chunk without re-parsing
        - ✅ **Easy queries** - Find papers by author, year, topic
        - ✅ **Saves money** - No need to re-parse PDFs ($2000+ saved)
        - ✅ **Future-proof** - Can upgrade to dedicated columns later
        
        **Safety:**
        - ✅ Idempotent (safe to run multiple times)
        - ✅ Non-destructive (only adds data, never deletes)
        - ✅ Dry-run preview available
        - ✅ Preserves all existing metadata
        """)
    
    st.markdown("---")
    
    # Migration controls
    st.subheader("🚀 Run Migration")
    
    if stats['missing'] == 0:
        st.success("✅ All documents are already enriched! No migration needed.")
        return
    
    st.warning(f"⚠️ {stats['missing']} documents need metadata enrichment")
    
    # Dry run button
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("🔍 Preview Migration (Dry Run)", type="secondary", use_container_width=True):
            st.session_state.run_enrichment_preview = True
    
    with col2:
        if st.button("⚡ Execute Migration", type="primary", use_container_width=True):
            st.session_state.run_enrichment_execute = True
    
    # Run dry run preview
    if st.session_state.get('run_enrichment_preview'):
        st.markdown("---")
        st.subheader("🔍 Migration Preview (Dry Run)")
        st.info("This is a preview. No changes will be made to the database.")
        
        progress_placeholder = st.empty()
        
        with st.spinner("Analyzing documents..."):
            results = run_enrichment_migration(dry_run=True, progress_container=progress_placeholder)
        
        progress_placeholder.empty()
        
        # Show summary
        st.markdown("### 📊 Preview Summary")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total", results['total'])
        with col2:
            st.metric("Would Enrich", results['enriched'], delta=f"+{results['enriched']}")
        with col3:
            st.metric("Already Enriched", results['already_rich'])
        with col4:
            st.metric("Not Found", results['not_found'])
        
        # Show sample details
        if results['enriched'] > 0:
            with st.expander(f"📋 View {min(10, results['enriched'])} Sample Enrichments"):
                enrichment_samples = [d for d in results['details'] if d['status'] == 'would_enrich'][:10]
                for detail in enrichment_samples:
                    st.markdown(f"""
                    **{detail['filename']}**
                    - Title: {detail.get('title', 'N/A')}
                    - Authors: {detail.get('authors', 'N/A')}
                    - Year: {detail.get('year', 'N/A')}
                    - Fields to add: {detail.get('fields_added', 0)}
                    """)
        
        if results['not_found'] > 0:
            with st.expander(f"⚠️ View {results['not_found']} Documents Not Found"):
                not_found = [d for d in results['details'] if d['status'] == 'not_found']
                for detail in not_found:
                    st.markdown(f"- **{detail['filename']}**: {detail.get('reason', 'Unknown')}")
        
        st.session_state.run_enrichment_preview = False
    
    # Run actual migration
    if st.session_state.get('run_enrichment_execute'):
        st.markdown("---")
        st.subheader("⚡ Executing Migration")
        st.warning("⚠️ Executing migration... Please wait, do not close this page!")
        
        progress_placeholder = st.empty()
        
        with st.spinner("Enriching documents..."):
            results = run_enrichment_migration(dry_run=False, progress_container=progress_placeholder)
        
        progress_placeholder.empty()
        
        # Show results
        st.markdown("### 🎉 Migration Complete!")
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Total", results['total'])
        with col2:
            st.metric("Enriched", results['enriched'], delta=f"+{results['enriched']}")
        with col3:
            st.metric("Already Enriched", results['already_rich'])
        with col4:
            st.metric("Errors", results['errors'])
        
        if results['errors'] > 0:
            st.error(f"❌ {results['errors']} documents failed to enrich!")
            with st.expander(f"⚠️ View {results['errors']} Error Details"):
                errors = [d for d in results['details'] if d['status'] == 'error']
                for i, detail in enumerate(errors, 1):
                    st.markdown(f"""
                    **Error #{i}: File: {detail['filename']}**
                    
                    ```
                    {detail.get('reason', 'Unknown error')}
                    ```
                    """)
        else:
            st.success(f"✅ Successfully enriched {results['enriched']} documents!")
            
            if results['enriched'] > 0:
                with st.expander(f"📋 View {min(10, results['enriched'])} Sample Enriched Documents"):
                    enriched = [d for d in results['details'] if d['status'] == 'enriched'][:10]
                    for detail in enriched:
                        st.markdown(f"""
                        **{detail['filename']}**
                        - Title: {detail.get('title', 'N/A')}
                        - Authors: {detail.get('authors', 'N/A')}
                        - Year: {detail.get('year', 'N/A')}
                        - Fields added: {detail.get('fields_added', 0)}
                        """)
        
        # Re-check stats
        with st.spinner("Updating statistics..."):
            new_stats = get_parsed_documents_stats()
        
        st.markdown("### 📊 Updated Status")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Documents", new_stats['total'])
        with col2:
            st.metric("Enriched", new_stats['enriched'], 
                      delta=f"+{new_stats['enriched'] - stats['enriched']}")
        with col3:
            st.metric("Missing Metadata", new_stats['missing'], 
                      delta=f"{new_stats['missing'] - stats['missing']}",
                      delta_color="inverse")
        
        if new_stats['missing'] == 0:
            st.balloons()
            st.success("🎉 All documents are now enriched with complete metadata!")
        
        st.session_state.run_enrichment_execute = False

"""
Search Test page - Query Pinecone index to test stored embeddings.
"""
import streamlit as st
from components.common import page_header, error_message, success_message


def render():
    """Render the Search Test page."""
    page_header("Vector Search Testing", "Query your Pinecone index to test stored embeddings")
    
    col1, col2 = st.columns([1, 2])
    
    with col1:
        _render_search_form()
    
    with col2:
        _render_search_results()


def _render_search_form():
    """Render the search configuration form."""
    st.subheader("Search Configuration")
    
    search_query = st.text_area(
        "Search Query",
        height=100,
        help="Enter your search query text"
    )
    
    search_namespace = st.text_input(
        "Namespace",
        value=st.session_state.get('default_namespace', 'default'),
        help="Pinecone namespace to search in"
    )
    
    top_k = st.slider(
        "Number of Results",
        min_value=1,
        max_value=20,
        value=5,
        help="How many results to return"
    )
    
    if st.button("🔍 Search", use_container_width=True):
        if not search_query:
            error_message("Please enter a search query")
        elif not st.session_state.get('pinecone_api_key'):
            error_message("Pinecone API key required")
        else:
            _perform_search(search_query, search_namespace, top_k)


def _perform_search(query: str, namespace: str, top_k: int):
    """Perform the vector search."""
    with st.spinner("Searching..."):
        try:
            from utils.embedder import create_embeddings
            from utils.pinecone_uploader import initialize_pinecone
            from llama_index.core.schema import TextNode
            
            config = {
                'pinecone_api_key': st.session_state.pinecone_api_key,
                'openai_api_key': st.session_state.get('openai_api_key'),
                'embedding_model': st.session_state.get('embedding_model'),
                'embedding_dimension': st.session_state.get('embedding_dimension', 1536),
                'index_name': st.session_state.get('index_name')
            }
            
            index = initialize_pinecone(config)
            
            query_node = TextNode(text=query)
            query_embedding = create_embeddings([query_node], config)[0]
            
            results = index.query(
                vector=query_embedding,
                top_k=top_k,
                namespace=namespace,
                include_metadata=True
            )
            
            st.session_state.search_results = results
            success_message(f"Found {len(results.matches)} results")
            
        except Exception as e:
            error_message(f"Search error: {str(e)}")
            st.exception(e)


def _render_search_results():
    """Render the search results."""
    st.subheader("Search Results")
    
    if 'search_results' in st.session_state:
        results = st.session_state.search_results
        
        if results.matches:
            for idx, match in enumerate(results.matches):
                with st.expander(f"Result {idx + 1} - Score: {match.score:.4f}", expanded=(idx==0)):
                    st.markdown(f"**ID:** `{match.id}`")
                    st.markdown(f"**Score:** {match.score:.4f}")
                    
                    if match.metadata:
                        st.markdown("**Text:**")
                        st.text_area(
                            "Chunk content",
                            match.metadata.get('text', 'No text available'),
                            height=200,
                            key=f"result_{idx}"
                        )
                        
                        st.markdown("**Metadata:**")
                        metadata_display = {k: v for k, v in match.metadata.items() if k != 'text'}
                        st.json(metadata_display)
        else:
            st.warning("No results found")
    else:
        st.info("Enter a query and click Search to see results")

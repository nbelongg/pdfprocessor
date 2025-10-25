import streamlit as st
import os
from dotenv import load_dotenv
import json

load_dotenv()

st.set_page_config(
    page_title="Metadata Transformations",
    page_icon="🔧",
    layout="wide"
)

def check_password():
    """Returns `True` if the user had the correct password."""
    
    def password_entered():
        """Checks whether a password entered by the user is correct."""
        if st.session_state["password"] == os.getenv("APP_PASSWORD", "admin123"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.info("💡 Default password is 'admin123'. Set APP_PASSWORD in Secrets to change it.")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input(
            "Password", type="password", on_change=password_entered, key="password"
        )
        st.error("😕 Password incorrect")
        return False
    else:
        return True

if not check_password():
    st.stop()

st.title("🔧 Metadata Transformation Rules")
st.markdown("Create and manage custom metadata transformation rules for your processing pipeline")

tab1, tab2 = st.tabs(["📝 Create/Edit", "📋 Manage"])

with tab1:
    st.header("Create Transformation Rule")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        rule_name = st.text_input(
            "Rule Name",
            help="Unique identifier for this transformation rule"
        )
        
        description = st.text_area(
            "Description",
            help="What does this transformation do?"
        )
        
        st.subheader("Transformation Rules")
        st.markdown("Define how to transform metadata columns")
        
        transformation_type = st.selectbox(
            "Transformation Type",
            ["Map Values", "Combine Columns", "Extract Pattern", "Conditional Transform"]
        )
        
        if transformation_type == "Map Values":
            st.markdown("**Map specific values to new values**")
            source_column = st.text_input("Source Column")
            target_column = st.text_input("Target Column (leave empty to replace source)")
            
            num_mappings = st.number_input("Number of mappings", min_value=1, max_value=20, value=3)
            
            mappings = {}
            for i in range(num_mappings):
                col_a, col_b = st.columns(2)
                with col_a:
                    from_val = st.text_input(f"From value {i+1}", key=f"from_{i}")
                with col_b:
                    to_val = st.text_input(f"To value {i+1}", key=f"to_{i}")
                
                if from_val:
                    mappings[from_val] = to_val
            
            rules = {
                'type': 'map_values',
                'source_column': source_column,
                'target_column': target_column or source_column,
                'mappings': mappings
            }
        
        elif transformation_type == "Combine Columns":
            st.markdown("**Combine multiple columns into one**")
            columns_to_combine = st.text_input(
                "Columns to combine (comma-separated)",
                help="e.g., Author, Year, Title"
            )
            target_column = st.text_input("Target Column Name")
            separator = st.text_input("Separator", value=" - ")
            
            rules = {
                'type': 'combine_columns',
                'source_columns': [c.strip() for c in columns_to_combine.split(',') if c.strip()],
                'target_column': target_column,
                'separator': separator
            }
        
        elif transformation_type == "Extract Pattern":
            st.markdown("**Extract part of a value using regex**")
            source_column = st.text_input("Source Column")
            target_column = st.text_input("Target Column")
            pattern = st.text_input(
                "Regex Pattern",
                help="e.g., r'(\\d{4})' to extract year"
            )
            
            rules = {
                'type': 'extract_pattern',
                'source_column': source_column,
                'target_column': target_column,
                'pattern': pattern
            }
        
        elif transformation_type == "Conditional Transform":
            st.markdown("**Transform based on conditions**")
            source_column = st.text_input("Source Column")
            target_column = st.text_input("Target Column")
            condition_column = st.text_input("Condition Column")
            condition_value = st.text_input("Condition Value")
            if_true = st.text_input("Value if True")
            if_false = st.text_input("Value if False")
            
            rules = {
                'type': 'conditional',
                'source_column': source_column,
                'target_column': target_column,
                'condition_column': condition_column,
                'condition_value': condition_value,
                'if_true': if_true,
                'if_false': if_false
            }
    
    with col2:
        st.subheader("Preview")
        
        if rule_name:
            st.markdown(f"**Rule:** `{rule_name}`")
        if description:
            st.markdown(f"**Description:** {description}")
        
        st.markdown("**Transformation:**")
        st.json(rules if 'rules' in locals() else {})
        
        if st.button("💾 Save Transformation Rule", type="primary", use_container_width=True):
            if not rule_name:
                st.error("Please provide a rule name")
            else:
                try:
                    from utils.database import save_metadata_transformation
                    
                    save_metadata_transformation(rule_name, description, rules)
                    st.success(f"✅ Transformation rule '{rule_name}' saved!")
                    
                except Exception as e:
                    st.error(f"Error saving rule: {str(e)}")

with tab2:
    st.header("Manage Transformation Rules")
    
    if st.button("🔄 Refresh Rules"):
        from utils.database import get_metadata_transformations
        st.session_state.transformations = get_metadata_transformations()
    
    if 'transformations' not in st.session_state:
        from utils.database import get_metadata_transformations
        st.session_state.transformations = get_metadata_transformations()
    
    transformations = st.session_state.transformations
    
    if transformations:
        for trans in transformations:
            with st.expander(f"📐 {trans['name']}"):
                st.markdown(f"**Description:** {trans.get('description', 'N/A')}")
                st.markdown(f"**Created:** {trans.get('created_at', 'N/A')}")
                st.markdown(f"**Last Updated:** {trans.get('updated_at', 'N/A')}")
                
                st.markdown("**Rules:**")
                st.json(trans.get('rules', {}))
                
                col_a, col_b = st.columns(2)
                
                with col_a:
                    if st.button(f"Delete", key=f"del_{trans['name']}"):
                        from utils.database import delete_metadata_transformation
                        
                        delete_metadata_transformation(trans['name'])
                        st.success(f"Deleted '{trans['name']}'")
                        st.rerun()
                
                with col_b:
                    if st.button(f"Export JSON", key=f"exp_{trans['name']}"):
                        export_data = {
                            'name': trans['name'],
                            'description': trans.get('description', ''),
                            'rules': trans.get('rules', {})
                        }
                        st.download_button(
                            "Download",
                            data=json.dumps(export_data, indent=2),
                            file_name=f"{trans['name']}.json",
                            mime="application/json",
                            key=f"down_{trans['name']}"
                        )
    else:
        st.info("No transformation rules defined yet")

st.markdown("---")
st.caption("Metadata Transformation Rules | PDF Chunking & Embedding Pipeline")

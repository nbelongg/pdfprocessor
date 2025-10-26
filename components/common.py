"""
Reusable UI components for the Streamlit application.
Reduces code duplication and provides consistent UI patterns.
"""
import streamlit as st
from typing import Callable, Optional, Any, List, Dict
from config.constants import BTN_REFRESH


def refresh_button(key: str, callback: Optional[Callable] = None, label: str = BTN_REFRESH) -> bool:
    """
    Standardized refresh button with optional callback.
    
    Args:
        key: Unique key for the button
        callback: Optional function to call when clicked
        label: Button label text
        
    Returns:
        True if button was clicked
    """
    if st.button(label, key=key):
        if callback:
            callback()
        return True
    return False


def page_header(title: str, description: str = None, icon: str = None):
    """
    Standardized page header with optional description.
    
    Args:
        title: Page title
        description: Optional description text
        icon: Optional emoji icon
    """
    if icon:
        st.header(f"{icon} {title}")
    else:
        st.header(title)
    
    if description:
        st.markdown(description)


def info_box(message: str, icon: str = "💡"):
    """
    Standardized info box.
    
    Args:
        message: Info message to display
        icon: Icon to show
    """
    st.info(f"{icon} {message}")


def success_message(message: str):
    """Display success message."""
    st.success(f"✅ {message}")


def error_message(message: str):
    """Display error message."""
    st.error(f"❌ {message}")


def warning_message(message: str):
    """Display warning message."""
    st.warning(f"⚠️ {message}")


def confirm_action(
    label: str,
    key: str,
    action: Callable,
    confirm_text: str = "Are you sure?",
    button_type: str = "secondary"
) -> None:
    """
    Button with confirmation dialog.
    
    Args:
        label: Button label
        key: Unique button key
        action: Function to execute on confirmation
        confirm_text: Confirmation message
        button_type: Streamlit button type
    """
    if st.button(label, key=key, type=button_type):
        st.session_state[f"{key}_confirm"] = True
    
    if st.session_state.get(f"{key}_confirm", False):
        st.warning(confirm_text)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Yes", key=f"{key}_yes"):
                action()
                del st.session_state[f"{key}_confirm"]
                st.rerun()
        with col2:
            if st.button("No", key=f"{key}_no"):
                del st.session_state[f"{key}_confirm"]
                st.rerun()


def status_badge(active: bool, active_label: str = "Active", inactive_label: str = "Inactive") -> str:
    """
    Return status badge icon and text.
    
    Args:
        active: Whether status is active
        active_label: Label for active status
        inactive_label: Label for inactive status
        
    Returns:
        Formatted status string with icon
    """
    if active:
        return f"✅ {active_label}"
    return f"❌ {inactive_label}"


def expandable_section(
    title: str,
    content_func: Callable,
    expanded: bool = False,
    key: Optional[str] = None
):
    """
    Create an expandable section with a title and content function.
    
    Args:
        title: Section title
        content_func: Function that renders the content
        expanded: Whether expanded by default
        key: Optional unique key
    """
    with st.expander(title, expanded=expanded):
        content_func()


def two_column_form(
    fields_left: List[tuple],
    fields_right: List[tuple],
    values: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Create a two-column form with fields.
    
    Args:
        fields_left: List of (label, field_type, kwargs) for left column
        fields_right: List of (label, field_type, kwargs) for right column
        values: Optional default values dict
        
    Returns:
        Dictionary of field values
    """
    col1, col2 = st.columns(2)
    result = {}
    
    with col1:
        for label, field_type, kwargs in fields_left:
            if values and label in values:
                kwargs['value'] = values[label]
            result[label] = field_type(label, **kwargs)
    
    with col2:
        for label, field_type, kwargs in fields_right:
            if values and label in values:
                kwargs['value'] = values[label]
            result[label] = field_type(label, **kwargs)
    
    return result


def data_table(
    data: List[Dict],
    columns: List[str] = None,
    height: int = None
):
    """
    Display a data table with optional column selection.
    
    Args:
        data: List of dictionaries to display
        columns: Optional list of columns to show
        height: Optional table height
    """
    import pandas as pd
    
    if not data:
        st.info("No data to display")
        return
    
    df = pd.DataFrame(data)
    
    if columns:
        df = df[columns]
    
    if height:
        st.dataframe(df, height=height, use_container_width=True)
    else:
        st.dataframe(df, use_container_width=True)


def loading_spinner(message: str = "Loading..."):
    """
    Context manager for loading spinner.
    
    Usage:
        with loading_spinner("Processing..."):
            # do work
    """
    return st.spinner(message)


def metric_card(label: str, value: Any, delta: Any = None, help_text: str = None):
    """
    Display a metric card.
    
    Args:
        label: Metric label
        value: Metric value
        delta: Optional change/delta value
        help_text: Optional help tooltip
    """
    st.metric(label=label, value=value, delta=delta, help=help_text)


def key_value_display(data: Dict[str, Any], markdown: bool = True):
    """
    Display key-value pairs.
    
    Args:
        data: Dictionary of key-value pairs
        markdown: Whether to use markdown formatting
    """
    for key, value in data.items():
        if markdown:
            st.markdown(f"**{key}:** {value}")
        else:
            st.write(f"{key}: {value}")

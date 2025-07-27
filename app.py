import streamlit as st
from auth.auth_manager import AuthManager
from ui.landing_page import show_landing_page, show_user_session_info
from ui.auth_components import show_auth_status, handle_google_auth, show_auth_required_message
from ui.chat_interface import (
    initialize_chat_interface, 
    show_chat_interface, 
    show_chat_controls, 
    show_quick_actions,
    show_workflow_progress
)
from config import settings

def main():
    """Main Streamlit application - No LLM in UI layer"""
    
    # Validate configuration on startup
    try:
        # This will raise an error if NVIDIA_API_KEY is missing
        settings.validate()
    except ValueError as e:
        st.error(f"⚠️ Configuration Error: {str(e)}")
        st.stop()
    
    # Initialize auth manager (no LLM client needed here)
    auth_manager = AuthManager()
    
    # Initialize user session first
    user_id = auth_manager.initialize_user_session()
    
    # Check for OAuth callback (before checking demo_started)
    query_params = st.query_params
    if 'code' in query_params:
        # User is returning from Google OAuth - ensure they stay in main app
        st.session_state['demo_started'] = True
    
    # Check if user has started the demo
    if 'demo_started' not in st.session_state:
        if show_landing_page():
            st.session_state.demo_started = True
            st.rerun()
        return
    
    # Show session info in sidebar
    show_user_session_info()
    
    # Check authentication status
    is_authenticated = auth_manager.is_authenticated(user_id)
    
    # Show auth status in sidebar
    show_auth_status(auth_manager, user_id)
    
    # Show workflow progress if active
    show_workflow_progress()
    
    # Main content area
    st.title("🤖 AI Assistant")
    st.caption("Powered by NVIDIA AI & LangGraph")
    
    if not is_authenticated:
        # Show authentication flow
        st.markdown("## 🔐 Google Account Connection Required")
        handle_google_auth(auth_manager, user_id)
        show_auth_required_message()
    else:
        # Show main chat interface (LLM created internally by agents)
        initialize_chat_interface()
        show_chat_interface(auth_manager, user_id)
        
        # Show sidebar controls
        show_chat_controls()
        show_quick_actions(auth_manager, user_id)

if __name__ == "__main__":
    main()
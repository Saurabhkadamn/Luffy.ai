import streamlit as st
import os
from langchain_nvidia_ai_endpoints import ChatNVIDIA
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

def get_llm_client():
    """Initialize NVIDIA LLM client"""
    try:
        # Get API key from environment or Streamlit secrets
        nvidia_api_key = os.getenv("NVIDIA_API_KEY") or st.secrets.get("NVIDIA_API_KEY")
        
        if not nvidia_api_key:
            st.error("⚠️ NVIDIA API key not found. Please set NVIDIA_API_KEY environment variable.")
            return None
        
        llm = ChatNVIDIA(
            model="moonshotai/kimi-k2-instruct",
            api_key=nvidia_api_key,
            temperature=0.6,
            top_p=0.9,
            max_tokens=4096,
        )
        
        return llm
        
    except Exception as e:
        st.error(f"❌ Failed to initialize NVIDIA LLM: {str(e)}")
        return None

def main():
    """Main Streamlit application with NVIDIA LLM"""
    
    # Initialize auth manager and LLM
    auth_manager = AuthManager()
    llm_client = get_llm_client()
    
    if not llm_client:
        st.stop()  # Stop execution if LLM client failed to initialize
    
    # Check if user has started the demo
    if 'demo_started' not in st.session_state:
        if show_landing_page():
            st.session_state.demo_started = True
            st.rerun()
        return
    
    # Initialize user session
    user_id = auth_manager.initialize_user_session()
    
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
        # Show main chat interface with NVIDIA LLM
        initialize_chat_interface()
        show_chat_interface(auth_manager, llm_client, user_id)
        
        # Show sidebar controls
        show_chat_controls()
        show_quick_actions(auth_manager, user_id)

if __name__ == "__main__":
    main()
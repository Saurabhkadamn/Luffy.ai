import streamlit as st
from typing import Dict, Any

def show_landing_page() -> bool:
    """Show project landing page and handle user ID generation"""
    
    st.set_page_config(
        page_title="AI Assistant - Google Integration",
        page_icon="🤖",
        layout="wide"
    )
    
    # Hero Section
    st.markdown("""
    # 🤖 Intelligent AI Assistant
    ### Powered by LangChain + LangGraph + Google APIs
    
    Your personal AI assistant that can help you with:
    """)
    
    # Feature showcase
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        **📧 Gmail Management**
        - Send emails to anyone
        - Search your inbox intelligently  
        - Read recent messages
        - Handle email threads
        """)
    
    with col2:
        st.markdown("""
        **📅 Calendar & Meetings**
        - Create calendar events
        - Schedule Google Meet calls
        - Check your availability
        - Update existing events
        """)
    
    with col3:
        st.markdown("""
        **📁 Drive Operations**
        - Upload and share files
        - Search your documents
        - Download files locally
        - Manage permissions
        """)
    
    st.markdown("---")
    
    # How it works
    st.markdown("""
    ## 🧠 How It Works
    
    This AI assistant uses **LangGraph** to orchestrate complex multi-step workflows across your Google services:
    
    1. **Natural Language Input**: Just tell the assistant what you want to do
    2. **Intelligent Planning**: The AI breaks down your request into actionable steps  
    3. **Tool Execution**: Seamlessly execute actions across Gmail, Calendar, and Drive
    4. **Smart Coordination**: Each step builds on the previous ones using shared context
    
    **Example**: *"Hey, email my team about tomorrow's meeting, create a calendar event, and attach the project document from my Drive"*
    
    The assistant will:
    - Search your contacts for team members
    - Compose and send the email
    - Create a calendar event with Google Meet
    - Find and attach the relevant document
    - Keep you updated on each step
    """)
    
    st.markdown("---")
    
    # Technology stack
    with st.expander("🔧 Technology Stack"):
        st.markdown("""
        - **LangChain/LangGraph**: AI agent orchestration and workflow management
        - **Google APIs**: Gmail, Calendar, Drive integration via OAuth 2.0
        - **Streamlit**: Interactive web interface with session management
        - **Python**: Backend logic and Google API client libraries
        
        **Architecture Highlights**:
        - Multi-user session isolation for secure demo usage
        - Persistent state management across complex workflows  
        - Automatic token refresh and error recovery
        - Modular tool design for easy extensibility
        """)
    
    st.markdown("---")
    
    # CTA Section
    st.markdown("## 🚀 Ready to try it?")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        if st.button("🎯 Start Demo", type="primary", use_container_width=True):
            return True
    
    st.markdown("""
    <div style='text-align: center; color: #666; margin-top: 20px;'>
    <small>⚠️ Demo purposes only - Your data remains private and secure</small>
    </div>
    """, unsafe_allow_html=True)
    
    return False

def show_user_session_info():
    """Show current user session information"""
    if 'user_id' in st.session_state:
        with st.sidebar:
            st.markdown("### 👤 Session Info")
            st.markdown(f"**Session ID**: `{st.session_state.user_id[-8:]}`")
            
            if st.button("🔄 New Session"):
                # Clear session and restart
                for key in list(st.session_state.keys()):
                    del st.session_state[key]
                st.rerun()
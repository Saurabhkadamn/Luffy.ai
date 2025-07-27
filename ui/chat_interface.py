import streamlit as st
from typing import List, Dict, Any, Optional
from auth.auth_manager import AuthManager

def initialize_chat_interface():
    """Initialize chat interface with session state"""
    if 'messages' not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant", 
                "content": """👋 Hi! I'm your AI assistant powered by LangGraph.

I can help you with:
- 📧 **Gmail**: Send emails, search inbox, read messages
- 📅 **Calendar**: Create events, schedule meetings with Google Meet  
- 📁 **Drive**: Upload files, search documents, share files

Just tell me what you'd like to do in natural language!

*Example: "Send an email to john@company.com about tomorrow's meeting and create a calendar event for 2pm"*"""
            }
        ]

def show_chat_interface(auth_manager: AuthManager, user_id: str):
    """Display main chat interface"""
    
    # Show chat history
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input
    if prompt := st.chat_input("What would you like me to help you with?"):
        # Add user message
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Check authentication before processing
        if not auth_manager.is_authenticated(user_id):
            with st.chat_message("assistant"):
                st.markdown("""
                🔐 I need access to your Google account to help with that request.
                
                Please connect your Google account using the sidebar, then try again.
                """)
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": "Please connect your Google account to continue."
                })
        else:
            # Process with LangGraph agent (placeholder for now)
            with st.chat_message("assistant"):
                with st.spinner("🤔 Processing your request..."):
                    response = process_user_request(prompt, auth_manager, user_id)
                    st.markdown(response)
                    
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": response
                })

def process_user_request(prompt: str, auth_manager: AuthManager, user_id: str) -> str:
    """Process user request with LangGraph agent (placeholder)"""
    # TODO: Integrate with actual LangGraph agent
    
    # For now, return a placeholder response
    return f"""
    ✅ **Request received**: {prompt}
    
    🔧 **Status**: Ready to process with authenticated Google clients:
    - Gmail client: {'✅' if auth_manager.get_authenticated_client('gmail', 'v1', user_id) else '❌'}
    - Calendar client: {'✅' if auth_manager.get_authenticated_client('calendar', 'v3', user_id) else '❌'}
    - Drive client: {'✅' if auth_manager.get_authenticated_client('drive', 'v3', user_id) else '❌'}
    
    🚧 **Note**: LangGraph agent integration coming next!
    """

def show_chat_controls():
    """Show chat control buttons"""
    with st.sidebar:
        st.markdown("### 💬 Chat Controls")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Clear Chat"):
                st.session_state.messages = st.session_state.messages[:1]  # Keep welcome message
                st.rerun()
        
        with col2:
            if st.button("💾 Export Chat"):
                # TODO: Implement chat export
                st.info("Export feature coming soon!")

def show_quick_actions(auth_manager: AuthManager, user_id: str):
    """Show quick action buttons for common tasks"""
    if auth_manager.is_authenticated(user_id):
        with st.sidebar:
            st.markdown("### ⚡ Quick Actions")
            
            if st.button("📧 Check Recent Emails"):
                st.session_state.messages.append({
                    "role": "user", 
                    "content": "Show me my recent emails"
                })
                st.rerun()
            
            if st.button("📅 Today's Calendar"):
                st.session_state.messages.append({
                    "role": "user", 
                    "content": "Show me today's calendar events"
                })
                st.rerun()
            
            if st.button("📁 Recent Files"):
                st.session_state.messages.append({
                    "role": "user", 
                    "content": "Show me my recent Drive files"
                })
                st.rerun()
import streamlit as st
from typing import List, Dict, Any, Optional
from auth.auth_manager import AuthManager
from agents.agent_orchestrator import AgentOrchestrator

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
            # Process with AgentOrchestrator
            with st.chat_message("assistant"):
                response_placeholder = st.empty()
                full_response = ""
                
                try:
                    # Create orchestrator (LLM created internally)
                    orchestrator = AgentOrchestrator(auth_manager)
                    
                    # Process request with streaming updates
                    for update in orchestrator.process_user_request(prompt, user_id):
                        full_response += update + "\n"
                        response_placeholder.markdown(full_response)
                    
                except Exception as e:
                    error_msg = f"❌ **Error processing request**: {str(e)}\n\nPlease try again or rephrase your request."
                    response_placeholder.markdown(error_msg)
                    full_response = error_msg
                
                # Add to message history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": full_response
                })

def show_workflow_progress():
    """Show current workflow progress"""
    if 'user_id' in st.session_state:
        user_id = st.session_state.user_id
        
        # Check if there's an active workflow
        workflow_key = f"workflow_state_{user_id}"
        if workflow_key in st.session_state:
            with st.sidebar:
                st.markdown("### 🔄 Workflow Progress")
                
                # Get progress from session state
                workflow_state = st.session_state[workflow_key]
                
                if hasattr(workflow_state, 'plan') and hasattr(workflow_state, 'step_results'):
                    total_steps = len(workflow_state.plan.steps)
                    completed_steps = len([r for r in workflow_state.step_results.values() if r.status == "completed"])
                    
                    progress = completed_steps / total_steps if total_steps > 0 else 0
                    st.progress(progress)
                    st.caption(f"Step {completed_steps} of {total_steps}")
                    
                    # Show current status
                    if workflow_state.status == "executing":
                        st.info("🚀 Executing workflow...")
                    elif workflow_state.status == "completed":
                        st.success("✅ Workflow completed!")
                    elif workflow_state.status == "failed":
                        st.error("❌ Workflow failed")

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
                # Simple export implementation
                chat_content = "\n\n".join([
                    f"**{msg['role'].title()}**: {msg['content']}" 
                    for msg in st.session_state.messages
                ])
                st.download_button(
                    label="📥 Download",
                    data=chat_content,
                    file_name="chat_history.txt",
                    mime="text/plain"
                )

def show_quick_actions(auth_manager: AuthManager, user_id: str):
    """Show quick action buttons for common tasks"""
    if auth_manager.is_authenticated(user_id):
        with st.sidebar:
            st.markdown("### ⚡ Quick Actions")
            
            # Debug button to test Gmail connection
            if st.button("🔍 Debug Gmail"):
                client = auth_manager.get_authenticated_client('gmail', 'v1', user_id)
                if client:
                    st.success("Gmail client OK")
                    try:
                        results = client.users().messages().list(userId='me', maxResults=1).execute()
                        st.success(f"Gmail API working: {len(results.get('messages', []))} messages")
                    except Exception as e:
                        st.error(f"Gmail API failed: {e}")
                else:
                    st.error("No Gmail client")
            
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
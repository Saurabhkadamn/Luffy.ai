import streamlit as st
from typing import List, Dict, Any, Optional
import logging
import time
from datetime import datetime

# Our new components
from auth.auth_manager import AuthManager
from agents.agent_orchestrator import create_agent_orchestrator
from agents.state_manager import get_user_state_manager

# Configure logging
logger = logging.getLogger(__name__)

def initialize_chat_interface():
    """
    Initialize chat interface with proper multi-user session management.
    
    Each user gets their own isolated chat history and workflow state.
    """
    # Get user ID from session state (set by auth manager)
    user_id = st.session_state.get('user_id')
    
    if not user_id:
        logger.warning("⚠️ No user_id found in session state")
        return
    
    # Initialize user-specific chat history
    chat_key = f'messages_{user_id}'
    
    if chat_key not in st.session_state:
        logger.info(f"💬 Initializing chat for user: {user_id}")
        st.session_state[chat_key] = [
            {
                "role": "assistant", 
                "content": """👋 Hi! I'm your AI assistant powered by LangGraph.

I can help you with:
- 📧 **Gmail**: Send emails, search inbox, read messages
- 📅 **Calendar**: Create events, schedule meetings with Google Meet  
- 📁 **Drive**: Upload files, search documents, share files

Just tell me what you'd like to do in natural language!

*Example: "Send an email to john@company.com about tomorrow's meeting and create a calendar event for 2pm"*""",
                "timestamp": datetime.now().isoformat()
            }
        ]
        logger.info(f"✅ Chat initialized for user: {user_id}")

def show_chat_interface(auth_manager: AuthManager, user_id: str):
    """
    Display main chat interface with multi-user support and real streaming.
    
    Handles authentication, user isolation, and Claude-style progress display.
    """
    logger.info(f"🎨 Showing chat interface for user: {user_id}")
    
    # Get user-specific chat messages
    chat_key = f'messages_{user_id}'
    
    if chat_key not in st.session_state:
        logger.warning(f"⚠️ No chat history found for user: {user_id}")
        initialize_chat_interface()
    
    messages = st.session_state.get(chat_key, [])
    
    # Show chat history with user isolation
    for message in messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    
    # Chat input with user validation
    if prompt := st.chat_input("What would you like me to help you with?"):
        logger.info(f"📝 User {user_id} submitted: {prompt}")
        
        # Add user message to user-specific history
        user_message = {
            "role": "user", 
            "content": prompt,
            "timestamp": datetime.now().isoformat()
        }
        st.session_state[chat_key].append(user_message)
        
        with st.chat_message("user"):
            st.markdown(prompt)
        
        # Verify authentication before processing
        if not _verify_user_authentication(auth_manager, user_id):
            with st.chat_message("assistant"):
                auth_error_msg = """
                🔐 **Authentication Required**
                
                Your Google account connection has expired or is missing.
                Please reconnect your account using the sidebar, then try again.
                """
                st.markdown(auth_error_msg)
                
                # Add to chat history
                st.session_state[chat_key].append({
                    "role": "assistant", 
                    "content": auth_error_msg,
                    "timestamp": datetime.now().isoformat()
                })
            return
        
        # Process request with real streaming and user isolation
        with st.chat_message("assistant"):
            _process_request_with_streaming(prompt, auth_manager, user_id)

def _verify_user_authentication(auth_manager: AuthManager, user_id: str) -> bool:
    """
    Verify user authentication and available services.
    
    Returns True if user is properly authenticated with required services.
    """
    logger.info(f"🔐 Verifying authentication for user: {user_id}")
    
    try:
        # Check if user is authenticated
        if not auth_manager.is_authenticated(user_id):
            logger.warning(f"⚠️ User {user_id} not authenticated")
            return False
        
        # Check available services
        available_services = []
        
        if auth_manager.get_authenticated_client('gmail', 'v1', user_id):
            available_services.append('gmail')
        
        if auth_manager.get_authenticated_client('calendar', 'v3', user_id):
            available_services.append('calendar')
        
        if auth_manager.get_authenticated_client('drive', 'v3', user_id):
            available_services.append('drive')
        
        logger.info(f"✅ User {user_id} has access to: {available_services}")
        
        # Require at least one service
        return len(available_services) > 0
        
    except Exception as e:
        logger.error(f"❌ Error verifying authentication for user {user_id}: {str(e)}")
        return False

def _process_request_with_streaming(prompt: str, auth_manager: AuthManager, user_id: str):
    """
    Process user request with real streaming and Claude-style progress display.
    
    Provides the step-by-step progress updates that users see in real-time.
    """
    logger.info(f"⚡ Processing request with streaming for user: {user_id}")
    
    # Create response placeholder for streaming updates
    response_placeholder = st.empty()
    full_response = ""
    
    try:
        # Create orchestrator for this user (user-isolated)
        logger.info(f"🚀 Creating orchestrator for user: {user_id}")
        orchestrator = create_agent_orchestrator(auth_manager)
        
        # Show initial processing indicator
        with response_placeholder.container():
            st.markdown("🤖 **Processing your request...**")
        
        # Process request with real streaming
        logger.info(f"⚡ Starting streaming execution for user: {user_id}")
        response_lines = []
        
        for update in orchestrator.process_user_request(prompt, user_id):
            # Add each update to the response
            response_lines.append(update)
            
            # Join all lines and display
            full_response = "\n".join(response_lines)
            
            # Update the display in real-time
            with response_placeholder.container():
                st.markdown(full_response)
            
            # Small delay for better UX (optional)
            time.sleep(0.1)
        
        logger.info(f"✅ Streaming completed for user: {user_id}")
        
    except Exception as e:
        logger.error(f"❌ Error processing request for user {user_id}: {str(e)}")
        
        error_msg = f"""
❌ **Error processing request**: {str(e)}

This might be due to:
- Google API connection issues
- Authentication problems
- Service rate limits

Please try again or rephrase your request.
"""
        
        with response_placeholder.container():
            st.markdown(error_msg)
        
        full_response = error_msg
    
    # Add final response to user-specific chat history
    chat_key = f'messages_{user_id}'
    st.session_state[chat_key].append({
        "role": "assistant", 
        "content": full_response,
        "timestamp": datetime.now().isoformat()
    })
    
    logger.info(f"💾 Response saved to chat history for user: {user_id}")

def show_workflow_progress():
    """
    Show current workflow progress in sidebar with user isolation.
    
    Displays progress for the current user's active workflow.
    """
    user_id = st.session_state.get('user_id')
    
    if not user_id:
        return
    
    try:
        # Get user-specific state manager
        state_manager = get_user_state_manager(user_id)
        
        # Check if user has active workflow
        if state_manager.is_workflow_active():
            with st.sidebar:
                st.markdown("### 🔄 Workflow Progress")
                
                # Get progress details
                progress = state_manager.get_workflow_progress()
                
                if progress and progress.get('status') != 'no_workflow':
                    # Show progress bar
                    progress_percent = progress.get('progress_percent', 0) / 100
                    st.progress(progress_percent)
                    
                    # Show step details
                    current_step = progress.get('current_step', 1)
                    total_steps = progress.get('total_steps', 1)
                    st.caption(f"Step {current_step} of {total_steps}")
                    
                    # Show workflow intent
                    intent = progress.get('plan_intent', 'Unknown workflow')
                    st.caption(f"**{intent}**")
                    
                    # Show status
                    status = progress.get('status', 'unknown')
                    if status == "executing":
                        st.info("🚀 Executing workflow...")
                    elif status == "completed":
                        st.success("✅ Workflow completed!")
                    elif status == "failed":
                        st.error("❌ Workflow failed")
                    
                    # Show recent progress messages
                    recent_messages = state_manager.get_recent_messages(3)
                    if recent_messages:
                        st.markdown("**Recent updates:**")
                        for msg in recent_messages[-3:]:  # Last 3 messages
                            st.caption(f"• {msg}")
                    
                    # Cancel button
                    if st.button("🛑 Cancel Workflow", key=f"cancel_{user_id}"):
                        try:
                            state_manager.clear_workflow()
                            st.success("Workflow cancelled")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error cancelling workflow: {e}")
        
    except Exception as e:
        logger.error(f"❌ Error showing workflow progress for user {user_id}: {str(e)}")

def show_chat_controls():
    """
    Show chat control buttons with user isolation.
    
    Provides user-specific chat management without affecting other users.
    """
    user_id = st.session_state.get('user_id')
    
    if not user_id:
        return
    
    with st.sidebar:
        st.markdown("### 💬 Chat Controls")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🗑️ Clear Chat", key=f"clear_chat_{user_id}"):
                # Clear only this user's chat
                chat_key = f'messages_{user_id}'
                if chat_key in st.session_state:
                    # Keep welcome message
                    welcome_msg = st.session_state[chat_key][0] if st.session_state[chat_key] else None
                    st.session_state[chat_key] = [welcome_msg] if welcome_msg else []
                    logger.info(f"🗑️ Chat cleared for user: {user_id}")
                st.rerun()
        
        with col2:
            if st.button("💾 Export Chat", key=f"export_chat_{user_id}"):
                # Export only this user's chat
                chat_key = f'messages_{user_id}'
                messages = st.session_state.get(chat_key, [])
                
                chat_content = f"Chat Export for User: {user_id}\n"
                chat_content += f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                chat_content += "=" * 50 + "\n\n"
                
                for msg in messages:
                    timestamp = msg.get('timestamp', 'Unknown time')
                    role = msg['role'].title()
                    content = msg['content']
                    chat_content += f"[{timestamp}] {role}:\n{content}\n\n"
                
                st.download_button(
                    label="📥 Download",
                    data=chat_content,
                    file_name=f"chat_history_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                    key=f"download_chat_{user_id}"
                )

def show_quick_actions(auth_manager: AuthManager, user_id: str):
    """
    Show quick action buttons with user authentication checks.
    
    Provides convenient shortcuts for common tasks with proper user isolation.
    """
    if not _verify_user_authentication(auth_manager, user_id):
        return
    
    with st.sidebar:
        st.markdown("### ⚡ Quick Actions")
        
        # Debug panel for development
        with st.expander("🔧 Debug Info"):
            st.markdown(f"**User ID**: `{user_id}`")
            
            # Test service connections
            services = []
            if auth_manager.get_authenticated_client('gmail', 'v1', user_id):
                services.append("✅ Gmail")
            else:
                services.append("❌ Gmail")
                
            if auth_manager.get_authenticated_client('calendar', 'v3', user_id):
                services.append("✅ Calendar")
            else:
                services.append("❌ Calendar")
                
            if auth_manager.get_authenticated_client('drive', 'v3', user_id):
                services.append("✅ Drive")
            else:
                services.append("❌ Drive")
            
            st.markdown("**Services:**")
            for service in services:
                st.caption(service)
            
            # Show workflow status
            try:
                state_manager = get_user_state_manager(user_id)
                if state_manager.is_workflow_active():
                    st.caption("🔄 Active workflow")
                else:
                    st.caption("✅ No active workflow")
            except:
                st.caption("❓ Workflow status unknown")
        
        # Quick action buttons
        if st.button("📧 Check Recent Emails", key=f"quick_email_{user_id}"):
            chat_key = f'messages_{user_id}'
            st.session_state[chat_key].append({
                "role": "user", 
                "content": "Show me my recent emails",
                "timestamp": datetime.now().isoformat()
            })
            st.rerun()
        
        if st.button("📅 Today's Calendar", key=f"quick_calendar_{user_id}"):
            chat_key = f'messages_{user_id}'
            st.session_state[chat_key].append({
                "role": "user", 
                "content": "Show me today's calendar events",
                "timestamp": datetime.now().isoformat()
            })
            st.rerun()
        
        if st.button("📁 Recent Files", key=f"quick_files_{user_id}"):
            chat_key = f'messages_{user_id}'
            st.session_state[chat_key].append({
                "role": "user", 
                "content": "Show me my recent Drive files",
                "timestamp": datetime.now().isoformat()
            })
            st.rerun()

def show_user_session_status():
    """
    Show current user session status and statistics in sidebar.
    
    Provides visibility into user-specific session information.
    """
    user_id = st.session_state.get('user_id')
    
    if not user_id:
        return
    
    with st.sidebar:
        st.markdown("### 👤 Session Status")
        
        # Basic session info
        st.caption(f"**User**: `{user_id[-8:]}`")  # Show last 8 chars
        
        # Chat statistics
        chat_key = f'messages_{user_id}'
        messages = st.session_state.get(chat_key, [])
        message_count = len([m for m in messages if m['role'] == 'user'])
        st.caption(f"**Messages sent**: {message_count}")
        
        # Session duration
        if 'auth_initialized' in st.session_state:
            session_start = st.session_state.get('session_start_time', datetime.now())
            if isinstance(session_start, str):
                try:
                    session_start = datetime.fromisoformat(session_start)
                except:
                    session_start = datetime.now()
            
            duration = datetime.now() - session_start
            hours = int(duration.total_seconds() // 3600)
            minutes = int((duration.total_seconds() % 3600) // 60)
            
            if hours > 0:
                st.caption(f"**Session**: {hours}h {minutes}m")
            else:
                st.caption(f"**Session**: {minutes}m")
        
        # Workflow history
        try:
            state_manager = get_user_state_manager(user_id)
            workflow_summary = state_manager.get_workflow_summary()
            
            if workflow_summary:
                completed = workflow_summary.get('completed_steps', 0)
                total = workflow_summary.get('total_steps', 0)
                st.caption(f"**Last workflow**: {completed}/{total} steps")
        except:
            pass  # Silently handle errors

# Utility functions for multi-user management
def cleanup_inactive_users():
    """
    Clean up session data for inactive users.
    
    Removes chat histories and workflow data for users who haven't
    been active recently.
    """
    try:
        current_user = st.session_state.get('user_id')
        cutoff_hours = 24  # Clean up after 24 hours of inactivity
        
        # This would need to be implemented with proper user tracking
        # For now, we rely on Streamlit's session management
        logger.info("🧹 User cleanup would run here in production")
        
    except Exception as e:
        logger.error(f"❌ Error in user cleanup: {str(e)}")

def get_user_stats() -> Dict[str, Any]:
    """
    Get statistics about current user session.
    
    Returns information about user activity and system usage.
    """
    user_id = st.session_state.get('user_id')
    
    if not user_id:
        return {"error": "No active user session"}
    
    try:
        stats = {
            "user_id": user_id,
            "session_active": True,
            "chat_messages": 0,
            "workflow_active": False
        }
        
        # Count chat messages
        chat_key = f'messages_{user_id}'
        messages = st.session_state.get(chat_key, [])
        stats["chat_messages"] = len([m for m in messages if m['role'] == 'user'])
        
        # Check workflow status
        try:
            state_manager = get_user_state_manager(user_id)
            stats["workflow_active"] = state_manager.is_workflow_active()
        except:
            pass
        
        return stats
        
    except Exception as e:
        logger.error(f"❌ Error getting user stats: {str(e)}")
        return {"error": str(e)}

if __name__ == "__main__":
    # Example usage for testing
    print("🎨 Chat Interface Module")
    print("This module provides multi-user chat interface with real streaming")
    print("Run with proper Streamlit app for full functionality")
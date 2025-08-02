import streamlit as st
import logging
from datetime import datetime
import os
from pathlib import Path

# Core components
from auth.auth_manager import AuthManager
from ui.landing_page import show_landing_page, show_user_session_info
from ui.auth_components import show_auth_status, handle_google_auth, show_auth_required_message
from ui.chat_interface import (
    initialize_chat_interface, 
    show_chat_interface, 
    show_chat_controls, 
    show_quick_actions,
    show_workflow_progress,
    show_user_session_status,
    cleanup_inactive_users,
    get_user_stats
)
from config import settings

# Initialize directories first (before logging setup)
def _ensure_directories():
    """Ensure required directories exist before logging setup"""
    try:
        from pathlib import Path
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Create data directory for checkpoints
        data_dir = Path("data/checkpoints")
        data_dir.mkdir(parents=True, exist_ok=True)
        
    except Exception:
        # If we can't create directories, we'll just use console logging
        pass

# Ensure directories exist before configuring logging
_ensure_directories()

# CLEAN LOGGING CONFIGURATION
logging.basicConfig(
    level=logging.ERROR,  # Only show errors by default
    format='%(levelname)s: %(message)s',  # Simple format
    handlers=[logging.StreamHandler()]  # Console only
)

# Enable specific loggers for workflow tracking
logging.getLogger('agents.llm_planner').setLevel(logging.INFO)
logging.getLogger('agents.agent_orchestrator').setLevel(logging.INFO) 
logging.getLogger('agents.graph_builder').setLevel(logging.INFO)
logging.getLogger('__main__').setLevel(logging.WARNING)  # Reduce main app noise

logger = logging.getLogger(__name__)

def configure_streamlit_app():
    """Configure Streamlit app settings for production deployment"""
    st.set_page_config(
        page_title="AI Assistant - Google Integration",
        page_icon="🤖",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            'Get Help': 'https://github.com/your-repo/issues',
            'Report a bug': 'https://github.com/your-repo/issues',
            'About': '''
            # AI Assistant with Google Integration
            
            Powered by LangGraph + LangChain + Google APIs
            
            Features:
            - Multi-user support with session isolation
            - Real-time streaming workflows
            - Gmail, Calendar, and Drive integration
            - Claude-style progress display
            '''
        }
    )

def initialize_logging_and_directories():
    """Initialize logging and directories - called after Streamlit setup"""
    try:
        # Create logs directory if it doesn't exist
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        
        # Create data directory for checkpoints
        data_dir = Path("data/checkpoints")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        logger.debug("Directories initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing directories: {str(e)}")

def validate_environment():
    """Validate environment configuration and dependencies"""
    try:
        logger.debug("Validating environment configuration")
        
        # Validate settings
        settings.validate()
        logger.debug("Settings validation passed")
        
        # Check required directories
        required_dirs = ["logs", "data", "data/checkpoints"]
        for dir_path in required_dirs:
            if not os.path.exists(dir_path):
                os.makedirs(dir_path, exist_ok=True)
                logger.debug(f"Created directory: {dir_path}")
        
        # Check Google credentials file
        if not os.path.exists(settings.GOOGLE_CREDENTIALS_JSON):
            raise FileNotFoundError(f"Google credentials file not found: {settings.GOOGLE_CREDENTIALS_JSON}")
        
        logger.debug("Environment validation completed")
        return True
        
    except Exception as e:
        logger.error(f"Environment validation failed: {str(e)}")
        st.error(f"Configuration Error: {str(e)}")
        st.error("Please check your environment setup and try again.")
        return False

def initialize_user_session(auth_manager: AuthManager) -> str:
    """
    Initialize user session with proper multi-user handling.
    
    Creates unique user ID and sets up session tracking.
    """
    try:
        # Initialize user session through auth manager
        user_id = auth_manager.initialize_user_session()
        
        # Set session start time if not already set
        if 'session_start_time' not in st.session_state:
            st.session_state.session_start_time = datetime.now()
            logger.debug(f"Session started for user: {user_id}")
        
        # Initialize session metadata
        if 'session_metadata' not in st.session_state:
            st.session_state.session_metadata = {
                'user_id': user_id,
                'start_time': datetime.now().isoformat(),
                'requests_processed': 0,
                'last_activity': datetime.now().isoformat()
            }
        
        # Update last activity
        st.session_state.session_metadata['last_activity'] = datetime.now().isoformat()
        
        logger.debug(f"User session initialized: {user_id}")
        return user_id
        
    except Exception as e:
        logger.error(f"Error initializing user session: {str(e)}")
        raise

def handle_oauth_callback():
    """
    Handle OAuth callback with proper error handling and user redirection.
    
    Ensures users stay in the main app after Google authentication.
    """
    try:
        query_params = st.query_params
        
        if 'code' in query_params:
            logger.debug("OAuth callback detected")
            
            # Ensure user stays in main app
            st.session_state['demo_started'] = True
            st.session_state['oauth_callback'] = True
            
            # Mark that we're processing OAuth
            if 'processing_oauth' not in st.session_state:
                st.session_state['processing_oauth'] = True
                logger.debug("Processing OAuth callback...")
            
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error handling OAuth callback: {str(e)}")
        return False

def show_app_header():
    """Show application header with branding and status"""
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col1:
        st.title("🤖 AI Assistant")
        st.caption("Powered by NVIDIA AI & LangGraph")
    
    with col2:
        # Show environment indicator
        if st.session_state.get('user_id'):
            st.success("🟢 Connected")
        else:
            st.warning("🟡 Starting...")
    
    with col3:
        # Show user count (simulated)
        user_id = st.session_state.get('user_id', '')
        if user_id:
            st.metric("User ID", f"...{user_id[-4:]}")

def show_sidebar_info(auth_manager: AuthManager, user_id: str):
    """Show comprehensive sidebar information"""
    with st.sidebar:
        # User session info
        show_user_session_info()
        
        # Authentication status
        show_auth_status(auth_manager, user_id)
        
        # Workflow progress (if active)
        show_workflow_progress()
        
        # Session status
        show_user_session_status()
        
        st.markdown("---")
        
        # Chat controls
        show_chat_controls()
        
        # Quick actions
        show_quick_actions(auth_manager, user_id)
        
        st.markdown("---")
        
        # System info
        with st.expander("ℹ️ System Info"):
            try:
                stats = get_user_stats()
                
                if "error" not in stats:
                    st.json(stats)
                else:
                    st.error(f"Error: {stats['error']}")
            except Exception as e:
                st.error(f"Error getting stats: {e}")
            
            # Show app version
            st.caption("**Version**: 2.0.0-rebuild")
            st.caption("**LangGraph**: Enabled")
            st.caption("**Multi-User**: Active")

def show_authentication_flow(auth_manager: AuthManager, user_id: str):
    """Show authentication flow for non-authenticated users"""
    st.markdown("## 🔐 Google Account Connection Required")
    
    # Show connection benefits
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        **📧 Gmail Integration**
        - Send emails to anyone
        - Search and read messages  
        - Manage email threads
        - Smart contact discovery
        """)
    
    with col2:
        st.markdown("""
        **📅 Calendar & Meetings**
        - Create calendar events
        - Schedule Google Meet calls
        - Check availability
        - Update existing events
        """)
    
    st.markdown("""
    **📁 Drive Operations**
    - Upload and share files
    - Search documents
    - Download files
    - Manage permissions
    """)
    
    st.markdown("---")
    
    # Handle Google authentication
    handle_google_auth(auth_manager, user_id)
    
    # Show additional help
    show_auth_required_message()

def show_main_application(auth_manager: AuthManager, user_id: str):
    """Show main application interface for authenticated users"""
    # Initialize chat interface for this user
    initialize_chat_interface()
    
    # Show main chat interface with real streaming
    show_chat_interface(auth_manager, user_id)

def handle_errors_gracefully():
    """Global error handler for the application"""
    try:
        # Check for common error conditions
        if 'error_state' in st.session_state:
            error = st.session_state['error_state']
            
            st.error(f"Application Error: {error}")
            st.markdown("""
            **Possible solutions:**
            - Refresh the page
            - Check your internet connection
            - Verify Google account permissions
            - Try logging out and back in
            """)
            
            if st.button("🔄 Reset Application"):
                # Clear error state
                for key in list(st.session_state.keys()):
                    if 'error' in key.lower():
                        del st.session_state[key]
                st.rerun()
            
            return True
        
        return False
        
    except Exception as e:
        logger.error(f"Error in error handler: {str(e)}")
        return False

def cleanup_on_exit():
    """Cleanup function called on app termination"""
    try:
        # Clean up inactive users
        cleanup_inactive_users()
        
        # Log session end
        user_id = st.session_state.get('user_id')
        if user_id:
            logger.debug(f"Session ended for user: {user_id}")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {str(e)}")

def main():
    """
    Main Streamlit application with production-ready multi-user support.
    
    Features:
    - Multi-user session isolation
    - Real streaming with LangGraph
    - Comprehensive error handling
    - Production deployment patterns
    """
    try:
        # Configure Streamlit
        configure_streamlit_app()
        
        # Initialize logging and environment
        initialize_logging_and_directories()
        
        # Validate environment
        if not validate_environment():
            st.stop()
        
        # Handle any existing errors
        if handle_errors_gracefully():
            return
        
        # Initialize auth manager
        logger.debug("Initializing AuthManager")
        auth_manager = AuthManager()
        
        # Initialize user session
        user_id = initialize_user_session(auth_manager)
        
        # Handle OAuth callback (before checking demo_started)
        oauth_callback = handle_oauth_callback()
        
        # Check if user has started the demo
        if 'demo_started' not in st.session_state and not oauth_callback:
            logger.debug("Showing landing page")
            if show_landing_page():
                st.session_state.demo_started = True
                st.rerun()
            return
        
        # Show app header
        show_app_header()
        
        # Show sidebar information
        show_sidebar_info(auth_manager, user_id)
        
        # Check authentication status
        is_authenticated = auth_manager.is_authenticated(user_id)
        logger.debug(f"User {user_id} authentication status: {is_authenticated}")
        
        # Main application flow
        if not is_authenticated:
            logger.debug(f"Showing authentication flow for user: {user_id}")
            show_authentication_flow(auth_manager, user_id)
        else:
            logger.debug(f"Showing main application for user: {user_id}")
            show_main_application(auth_manager, user_id)
        
        # Update session metadata
        if 'session_metadata' in st.session_state:
            st.session_state.session_metadata['requests_processed'] += 1
        
        logger.debug(f"App cycle completed for user: {user_id}")
        
    except Exception as e:
        logger.error(f"Critical error in main application: {str(e)}")
        
        # Store error state for graceful handling
        st.session_state['error_state'] = str(e)
        
        # Show error to user
        st.error(f"Critical Error: {str(e)}")
        st.markdown("""
        **This error has been logged. Please try:**
        - Refreshing the page
        - Clearing your browser cache
        - Contacting support if the issue persists
        """)
        
        # Provide restart option
        if st.button("🔄 Restart Application"):
            # Clear all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

# Production deployment helpers
def get_app_health() -> dict:
    """Get application health status for monitoring"""
    try:
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "version": "2.0.0-rebuild",
            "features": {
                "multi_user": True,
                "langgraph": True,
                "streaming": True,
                "checkpointing": True
            }
        }
        
        # Check critical components
        try:
            settings.validate()
            health["config"] = "valid"
        except:
            health["config"] = "invalid"
            health["status"] = "degraded"
        
        # Check directories
        required_dirs = ["logs", "data", "data/checkpoints"]
        missing_dirs = [d for d in required_dirs if not os.path.exists(d)]
        
        if missing_dirs:
            health["directories"] = f"missing: {missing_dirs}"
            health["status"] = "degraded"
        else:
            health["directories"] = "all_present"
        
        return health
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

# Entry point
if __name__ == "__main__":
    try:
        # Register cleanup function
        import atexit
        atexit.register(cleanup_on_exit)
        
        # Run main application
        main()
        
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        print(f"Fatal error: {str(e)}")
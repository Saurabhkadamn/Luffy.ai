import streamlit as st
from typing import Dict, Any, Optional
from auth.auth_manager import AuthManager

def show_auth_status(auth_manager: AuthManager, user_id: str):
    """Display current authentication status"""
    status = auth_manager.get_auth_status(user_id)
    
    if status['authenticated']:
        user_info = status['user_info']
        
        with st.sidebar:
            st.success("✅ Google Connected")
            
            if user_info:
                st.markdown("### 👤 Connected Account")
                
                # Show user avatar and info
                col1, col2 = st.columns([1, 2])
                with col1:
                    if user_info.get('picture'):
                        st.image(user_info['picture'], width=50)
                
                with col2:
                    st.markdown(f"**{user_info.get('name', 'User')}**")
                    st.markdown(f"`{user_info.get('email', '')}`")
            
            # Logout button
            if st.button("🚪 Disconnect Google", type="secondary"):
                auth_manager.logout_user(user_id)
                st.rerun()
    
    else:
        with st.sidebar:
            st.warning("⚠️ Google Not Connected")
            st.markdown("Connect your Google account to use AI features")

def show_auth_required_message():
    """Show message when authentication is required"""
    st.warning("""
    🔐 **Google Authentication Required**
    
    To use Gmail, Calendar, and Drive features, you need to connect your Google account.
    
    This is a secure OAuth 2.0 connection - your credentials are never stored on our servers.
    """)

def handle_google_auth(auth_manager: AuthManager, user_id: str) -> bool:
    """Handle Google OAuth authentication flow"""
    
    # Check if we have auth code in URL params
    query_params = st.experimental_get_query_params()
    
    if 'code' in query_params:
        # Handle OAuth callback
        auth_code = query_params['code'][0]
        
        with st.spinner("🔄 Completing Google authentication..."):
            success = auth_manager.handle_auth_callback(auth_code, user_id)
            
            if success:
                st.success("✅ Google account connected successfully!")
                # Clear URL params and refresh
                st.experimental_set_query_params()
                st.rerun()
            else:
                st.error("❌ Authentication failed. Please try again.")
                return False
    
    # Show authentication button
    auth_url = auth_manager.get_auth_url(user_id)
    
    if auth_url:
        st.markdown("### 🔗 Connect Your Google Account")
        
        st.markdown("""
        Click the button below to securely connect your Google account:
        - ✅ Gmail access for email operations
        - ✅ Calendar access for scheduling  
        - ✅ Drive access for file management
        - ✅ Profile access for personalization
        """)
        
        # Create auth button with custom styling
        st.markdown(f"""
        <div style='text-align: center; margin: 20px 0;'>
            <a href="{auth_url}" target="_self">
                <button style='
                    background: #4285f4;
                    color: white;
                    border: none;
                    padding: 12px 24px;
                    border-radius: 6px;
                    font-size: 16px;
                    cursor: pointer;
                    text-decoration: none;
                '>
                    🔐 Connect with Google
                </button>
            </a>
        </div>
        """, unsafe_allow_html=True)
        
        st.info("""
        **What happens next?**
        1. You'll be redirected to Google's secure login page
        2. Review and approve the requested permissions  
        3. You'll be redirected back here automatically
        4. Start using your AI assistant immediately!
        """)
    
    return False

def show_auth_error(error_message: str):
    """Display authentication error"""
    st.error(f"""
    ❌ **Authentication Error**
    
    {error_message}
    
    Please try connecting your Google account again.
    """)

def show_token_refresh_status():
    """Show token refresh status"""
    if 'token_refreshing' in st.session_state and st.session_state.token_refreshing:
        st.info("🔄 Refreshing authentication token...")
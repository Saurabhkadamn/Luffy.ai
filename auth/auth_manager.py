import streamlit as st
import json
import os
from typing import Dict, Any, Optional
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import secrets
from datetime import datetime, timedelta
from config import settings

class AuthManager:
    """Authentication manager for Google APIs with Streamlit session state"""
    
    def __init__(self):
        self.credentials_file = settings.GOOGLE_CREDENTIALS_JSON
        self.scopes = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.send',
            'https://www.googleapis.com/auth/calendar',
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/userinfo.email',
            'https://www.googleapis.com/auth/userinfo.profile',
            'openid'
        ]
        self.redirect_uri = settings.GOOGLE_REDIRECT_URI
    
    def initialize_user_session(self) -> str:
        """Initialize user session with unique ID"""
        if 'user_id' not in st.session_state:
            # Generate unique user ID
            user_id = f"user_{secrets.token_hex(8)}"
            st.session_state.user_id = user_id
            st.session_state.auth_initialized = True
            
        return st.session_state.user_id
    
    def is_authenticated(self, user_id: Optional[str] = None) -> bool:
        """Check if user is authenticated"""
        if user_id is None:
            user_id = st.session_state.get('user_id')
        
        if not user_id:
            return False
        
        token_key = f"google_tokens_{user_id}"
        
        if token_key not in st.session_state:
            return False
        
        tokens = st.session_state[token_key]
        
        # Check if tokens exist and are valid
        if not tokens or 'access_token' not in tokens:
            return False
        
        # Check if token is expired
        if self._is_token_expired(tokens):
            # Try to refresh
            return self._refresh_token(user_id)
        
        return True
    
    def get_auth_url(self, user_id: str) -> str:
        """Generate Google OAuth authorization URL"""
        try:
            flow = Flow.from_client_secrets_file(
                self.credentials_file,
                scopes=self.scopes,
                redirect_uri=self.redirect_uri
            )
            
            # Store flow in session for later use
            st.session_state[f"oauth_flow_{user_id}"] = flow
            
            # Generate authorization URL
            auth_url, _ = flow.authorization_url(
                prompt='consent',
                state=user_id  # Include user_id in state for security
            )
            
            return auth_url
            
        except Exception as e:
            st.error(f"Failed to generate auth URL: {str(e)}")
            return ""
    
    def handle_auth_callback(self, auth_code: str, user_id: str) -> bool:
        """Handle OAuth callback and store tokens"""
        try:
            flow_key = f"oauth_flow_{user_id}"
            
            if flow_key not in st.session_state:
                # Recreate flow if not found (common in Streamlit)
                flow = Flow.from_client_secrets_file(
                    self.credentials_file,
                    scopes=self.scopes,
                    redirect_uri=self.redirect_uri
                )
                st.session_state[flow_key] = flow
            
            flow = st.session_state[flow_key]
            
            # Exchange authorization code for tokens
            flow.fetch_token(code=auth_code)
            
            # Store tokens in session state
            credentials = flow.credentials
            tokens = {
                'access_token': credentials.token,
                'refresh_token': credentials.refresh_token,
                'expires_at': credentials.expiry.timestamp() if credentials.expiry else None,
                'token_type': 'Bearer',
                'scopes': self.scopes
            }
            
            token_key = f"google_tokens_{user_id}"
            st.session_state[token_key] = tokens
            
            # Clean up flow from session
            if flow_key in st.session_state:
                del st.session_state[flow_key]
            
            # Mark as authenticated
            st.session_state[f"authenticated_{user_id}"] = True
            
            return True
            
        except Exception as e:
            st.error(f"Authentication failed: {str(e)}")
            return False
    
    def get_authenticated_client(self, service_name: str, version: str, 
                               user_id: Optional[str] = None) -> Optional[Any]:
        """Get authenticated Google API client"""
        if user_id is None:
            user_id = st.session_state.get('user_id')
        
        if not self.is_authenticated(user_id):
            return None
        
        try:
            token_key = f"google_tokens_{user_id}"
            tokens = st.session_state[token_key]
            
            # Create credentials object
            credentials = Credentials(
                token=tokens['access_token'],
                refresh_token=tokens['refresh_token'],
                token_uri='https://oauth2.googleapis.com/token',
                client_id=self._get_client_id(),
                client_secret=self._get_client_secret(),
                scopes=self.scopes
            )
            
            # Build and return service
            service = build(service_name, version, credentials=credentials)
            return service
            
        except Exception as e:
            st.error(f"Failed to create authenticated client: {str(e)}")
            return None
    
    def logout_user(self, user_id: Optional[str] = None):
        """Logout user and clear tokens"""
        if user_id is None:
            user_id = st.session_state.get('user_id')
        
        if not user_id:
            return
        
        # Clear tokens and auth status
        token_key = f"google_tokens_{user_id}"
        auth_key = f"authenticated_{user_id}"
        
        if token_key in st.session_state:
            del st.session_state[token_key]
        
        if auth_key in st.session_state:
            del st.session_state[auth_key]
        
        # Optionally clear user_id to force re-initialization
        if 'user_id' in st.session_state:
            del st.session_state.user_id
    
    def get_user_info(self, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get basic user information"""
        client = self.get_authenticated_client('oauth2', 'v2', user_id)
        
        if not client:
            return None
        
        try:
            user_info = client.userinfo().get().execute()
            return {
                'email': user_info.get('email', ''),
                'name': user_info.get('name', ''),
                'picture': user_info.get('picture', '')
            }
        except Exception as e:
            st.error(f"Failed to get user info: {str(e)}")
            return None
    
    def _is_token_expired(self, tokens: Dict[str, Any]) -> bool:
        """Check if access token is expired"""
        if 'expires_at' not in tokens or tokens['expires_at'] is None:
            return False
        
        expiry_time = datetime.fromtimestamp(tokens['expires_at'])
        # Add 5 minute buffer
        return datetime.now() >= (expiry_time - timedelta(minutes=5))
    
    def _refresh_token(self, user_id: str) -> bool:
        """Refresh expired access token"""
        try:
            token_key = f"google_tokens_{user_id}"
            tokens = st.session_state[token_key]
            
            if 'refresh_token' not in tokens:
                return False
            
            # Create credentials and refresh
            credentials = Credentials(
                token=tokens['access_token'],
                refresh_token=tokens['refresh_token'],
                token_uri='https://oauth2.googleapis.com/token',
                client_id=self._get_client_id(),
                client_secret=self._get_client_secret(),
                scopes=self.scopes
            )
            
            # Refresh token
            credentials.refresh(Request())
            
            # Update stored tokens
            tokens['access_token'] = credentials.token
            if credentials.expiry:
                tokens['expires_at'] = credentials.expiry.timestamp()
            
            st.session_state[token_key] = tokens
            
            return True
            
        except Exception as e:
            st.error(f"Token refresh failed: {str(e)}")
            return False
    
    def _get_client_id(self) -> str:
        """Get client ID from credentials file"""
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
                return creds['web']['client_id']
        except Exception:
            st.error("Failed to read client ID from credentials file")
            return ""
    
    def _get_client_secret(self) -> str:
        """Get client secret from credentials file"""
        try:
            with open(self.credentials_file, 'r') as f:
                creds = json.load(f)
                return creds['web']['client_secret']
        except Exception:
            st.error("Failed to read client secret from credentials file")
            return ""
    
    def get_auth_status(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """Get detailed authentication status"""
        if user_id is None:
            user_id = st.session_state.get('user_id')
        
        if not user_id:
            return {
                'authenticated': False,
                'user_id': None,
                'user_info': None,
                'tokens_exist': False,
                'tokens_expired': False
            }
        
        token_key = f"google_tokens_{user_id}"
        tokens_exist = token_key in st.session_state
        tokens_expired = False
        
        if tokens_exist:
            tokens = st.session_state[token_key]
            tokens_expired = self._is_token_expired(tokens)
        
        authenticated = self.is_authenticated(user_id)
        user_info = self.get_user_info(user_id) if authenticated else None
        
        return {
            'authenticated': authenticated,
            'user_id': user_id,
            'user_info': user_info,
            'tokens_exist': tokens_exist,
            'tokens_expired': tokens_expired
        }
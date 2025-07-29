import os
import io
from typing import List, Dict, Any, Optional, Union
import mimetypes
import logging
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload

# LangChain tool imports
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)

# Pydantic models for tool inputs - KEEP YOUR EXISTING SCHEMAS
class UploadFileInput(BaseModel):
    """Input schema for uploading files to Google Drive"""
    file_path: Optional[str] = Field(default=None, description="Local file path to upload")
    filename: Optional[str] = Field(default=None, description="Name for the uploaded file")
    folder_id: Optional[str] = Field(default=None, description="Google Drive folder ID")
    description: Optional[str] = Field(default=None, description="File description")
    make_public: bool = Field(default=False, description="Make file publicly accessible")
    user_id: str = Field(description="User ID for authentication")

class SearchFilesInput(BaseModel):
    """Input schema for searching files in Google Drive"""
    query: Optional[str] = Field(default=None, description="Search query for file names")
    file_type: Optional[str] = Field(default=None, description="File type filter")
    folder_id: Optional[str] = Field(default=None, description="Search within specific folder")
    max_results: int = Field(default=20, description="Maximum number of results")
    include_trashed: bool = Field(default=False, description="Include trashed files")
    user_id: str = Field(description="User ID for authentication")

class ShareFileInput(BaseModel):
    """Input schema for sharing files"""
    file_id: str = Field(description="Google Drive file ID to share")
    email_addresses: Optional[List[str]] = Field(default=None, description="Email addresses to share with")
    role: str = Field(default='reader', description="Permission role: reader, writer, commenter")
    make_public: bool = Field(default=False, description="Make file publicly accessible")
    send_notification: bool = Field(default=True, description="Send email notification")
    user_id: str = Field(description="User ID for authentication")

class DownloadFileInput(BaseModel):
    """Input schema for downloading files"""
    file_id: str = Field(description="Google Drive file ID to download")
    download_path: Optional[str] = Field(default=None, description="Local download path")
    user_id: str = Field(description="User ID for authentication")

class ListFilesInput(BaseModel):
    """Input schema for listing recent files"""
    max_results: int = Field(default=20, description="Maximum number of files")
    file_types: Optional[List[str]] = Field(default=None, description="Filter by file types")
    recent: bool = Field(default=True, description="Sort by recent activity")
    user_id: str = Field(description="User ID for authentication")

class GetFileInfoInput(BaseModel):
    """Input schema for getting file information"""
    file_id: str = Field(description="Google Drive file ID")
    user_id: str = Field(description="User ID for authentication")

# Drive Tool Helper Class - KEEP YOUR EXISTING LOGIC
class DriveToolHelper:
    """Helper class containing Drive API operations"""
    
    @staticmethod
    def _get_file_type(mime_type: str) -> str:
        """Get human-readable file type from MIME type"""
        type_mapping = {
            'application/pdf': 'PDF',
            'application/vnd.google-apps.document': 'Google Doc',
            'application/vnd.google-apps.spreadsheet': 'Google Sheet',
            'application/vnd.google-apps.presentation': 'Google Slides',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word Document',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel Spreadsheet',
            'text/plain': 'Text File',
            'image/jpeg': 'JPEG Image',
            'image/png': 'PNG Image',
            'video/mp4': 'MP4 Video',
            'audio/mp3': 'MP3 Audio'
        }
        
        if mime_type in type_mapping:
            return type_mapping[mime_type]
        elif mime_type.startswith('image/'):
            return 'Image'
        elif mime_type.startswith('video/'):
            return 'Video'
        elif mime_type.startswith('audio/'):
            return 'Audio'
        else:
            return 'File'
    
    @staticmethod
    def _format_file_size(size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
    
    @staticmethod
    def _format_file_summary(file: Dict[str, Any]) -> str:
        """Format file for tool output"""
        name = file.get('name', 'Unknown')
        file_type = DriveToolHelper._get_file_type(file.get('mimeType', ''))
        size = int(file.get('size', 0)) if file.get('size') else 0
        size_readable = DriveToolHelper._format_file_size(size)
        modified = file.get('modifiedTime', 'Unknown')
        
        summary = f"📄 {name}\n"
        summary += f"   📁 Type: {file_type}\n"
        if size > 0:
            summary += f"   📏 Size: {size_readable}\n"
        summary += f"   🕐 Modified: {modified}\n"
        summary += f"   🔗 View: {file.get('webViewLink', 'N/A')}\n"
        
        return summary
    
    @staticmethod
    def _make_file_public(service, file_id: str):
        """Make file publicly accessible"""
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        service.permissions().create(fileId=file_id, body=permission).execute()

# FACTORY FUNCTION - Create Drive tools with auth injection
def create_drive_tools(auth_manager) -> List[BaseTool]:
    """
    Create Drive tools with auth_manager dependency injected.
    
    Auth manager still uses session state internally (perfect for demos!)
    Tools no longer import Streamlit directly.
    """
    logger.info("🔧 Creating Drive tools with auth injection")
    
    @tool
    def upload_file_to_drive_tool(input_data: UploadFileInput) -> str:
        """
        Upload a file to Google Drive.
        
        Uploads a local file to Google Drive with optional folder placement
        and public sharing. Returns file details and share link.
        """
        logger.info(f"📤 Uploading file to Drive: {input_data.filename}")
        
        try:
            # FIXED: Use injected auth_manager instead of session state import
            client = auth_manager.get_authenticated_client('drive', 'v3', input_data.user_id)
            if not client:
                raise Exception("Drive authentication failed")
            
            # Validate file path
            if not input_data.file_path or not os.path.exists(input_data.file_path):
                raise FileNotFoundError(f"File not found: {input_data.file_path}")
            
            filename = input_data.filename or os.path.basename(input_data.file_path)
            mime_type, _ = mimetypes.guess_type(input_data.file_path)
            media = MediaFileUpload(input_data.file_path, mimetype=mime_type)
            
            # File metadata
            file_metadata = {'name': filename}
            
            if input_data.description:
                file_metadata['description'] = input_data.description
            
            if input_data.folder_id:
                file_metadata['parents'] = [input_data.folder_id]
            
            # Upload file
            result = client.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size,mimeType,webViewLink,webContentLink'
            ).execute()
            
            # Make public if requested
            if input_data.make_public:
                DriveToolHelper._make_file_public(client, result['id'])
            
            logger.info(f"✅ File uploaded successfully: {result['id']}")
            
            # Format response
            response = f"File '{filename}' uploaded successfully to Google Drive!\n\n"
            response += DriveToolHelper._format_file_summary(result)
            response += f"   🆔 File ID: {result['id']}\n"
            
            if input_data.make_public:
                response += "   🌍 Public access: Yes\n"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to upload file: {str(e)}")
            return f"Failed to upload file: {str(e)}"
    
    @tool
    def search_files_in_drive_tool(input_data: SearchFilesInput) -> str:
        """
        Search for files in Google Drive using various filters.
        
        Search files by name, type, folder, or content. Supports filtering
        by file types and excluding trashed files.
        """
        logger.info(f"🔍 Searching Drive files: {input_data.query}")
        
        try:
            client = auth_manager.get_authenticated_client('drive', 'v3', input_data.user_id)
            if not client:
                raise Exception("Drive authentication failed")
            
            # Build search query
            search_parts = []
            
            if input_data.query:
                search_parts.append(f"name contains '{input_data.query}'")
            
            if input_data.file_type:
                # Handle common file type shortcuts
                type_mapping = {
                    'pdf': 'application/pdf',
                    'doc': 'application/vnd.google-apps.document',
                    'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                    'sheet': 'application/vnd.google-apps.spreadsheet',
                    'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    'image': 'image/',
                    'video': 'video/',
                    'audio': 'audio/'
                }
                
                mime_type = type_mapping.get(input_data.file_type.lower(), input_data.file_type)
                if mime_type.endswith('/'):
                    search_parts.append(f"mimeType contains '{mime_type}'")
                else:
                    search_parts.append(f"mimeType = '{mime_type}'")
            
            if input_data.folder_id:
                search_parts.append(f"'{input_data.folder_id}' in parents")
            
            if not input_data.include_trashed:
                search_parts.append("trashed = false")
            
            search_query = " and ".join(search_parts) if search_parts else "trashed = false"
            
            # Execute search
            results = client.files().list(
                q=search_query,
                pageSize=input_data.max_results,
                fields="files(id,name,size,mimeType,modifiedTime,webViewLink,parents,shared)"
            ).execute()
            
            files = results.get('files', [])
            
            logger.info(f"✅ Found {len(files)} files")
            
            # Format response
            if files:
                response = f"Found {len(files)} files in Google Drive:\n\n"
                for i, file in enumerate(files, 1):
                    response += f"{i}. {DriveToolHelper._format_file_summary(file)}\n"
                return response
            else:
                return "No files found matching the search criteria."
            
        except Exception as e:
            logger.error(f"❌ Failed to search files: {str(e)}")
            return f"Failed to search files: {str(e)}"
    
    @tool
    def share_drive_file_tool(input_data: ShareFileInput) -> str:
        """
        Share a Google Drive file with users or make it public.
        
        Grants access to specific users via email or makes file publicly
        accessible. Supports different permission levels.
        """
        logger.info(f"🔗 Sharing Drive file: {input_data.file_id}")
        
        try:
            client = auth_manager.get_authenticated_client('drive', 'v3', input_data.user_id)
            if not client:
                raise Exception("Drive authentication failed")
            
            # Get file details
            file_metadata = client.files().get(fileId=input_data.file_id, fields='name,webViewLink').execute()
            filename = file_metadata['name']
            
            permissions_created = []
            
            # Share with specific users
            if input_data.email_addresses:
                for email in input_data.email_addresses:
                    permission = {
                        'type': 'user',
                        'role': input_data.role,
                        'emailAddress': email
                    }
                    
                    result = client.permissions().create(
                        fileId=input_data.file_id,
                        body=permission,
                        sendNotificationEmail=input_data.send_notification
                    ).execute()
                    
                    permissions_created.append({
                        'email': email,
                        'role': input_data.role,
                        'permission_id': result['id']
                    })
            
            # Make public if requested
            if input_data.make_public:
                public_permission = {
                    'type': 'anyone',
                    'role': 'reader'
                }
                
                result = client.permissions().create(
                    fileId=input_data.file_id,
                    body=public_permission
                ).execute()
                
                permissions_created.append({
                    'type': 'public',
                    'role': 'reader',
                    'permission_id': result['id']
                })
            
            logger.info(f"✅ File shared successfully: {input_data.file_id}")
            
            # Format response
            response = f"File '{filename}' shared successfully!\n\n"
            response += f"📄 {filename}\n"
            response += f"🔗 View link: {file_metadata['webViewLink']}\n"
            
            if input_data.email_addresses:
                response += f"📧 Shared with {len(input_data.email_addresses)} user(s):\n"
                for perm in permissions_created:
                    if 'email' in perm:
                        response += f"   • {perm['email']} ({perm['role']})\n"
            
            if input_data.make_public:
                response += "🌍 Public access: Anyone with link can view\n"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to share file: {str(e)}")
            return f"Failed to share file: {str(e)}"
    
    @tool
    def download_drive_file_tool(input_data: DownloadFileInput) -> str:
        """
        Download a file from Google Drive to local storage.
        
        Downloads file content and saves to specified location.
        Returns download confirmation and file details.
        """
        logger.info(f"📥 Downloading Drive file: {input_data.file_id}")
        
        try:
            client = auth_manager.get_authenticated_client('drive', 'v3', input_data.user_id)
            if not client:
                raise Exception("Drive authentication failed")
            
            # Get file metadata
            file_metadata = client.files().get(fileId=input_data.file_id).execute()
            filename = file_metadata['name']
            
            # Determine download path
            if input_data.download_path is None:
                download_path = filename
            elif os.path.isdir(input_data.download_path):
                download_path = os.path.join(input_data.download_path, filename)
            else:
                download_path = input_data.download_path
            
            # Download file
            request = client.files().get_media(fileId=input_data.file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Save to file
            with open(download_path, 'wb') as f:
                f.write(file_io.getvalue())
            
            file_size = os.path.getsize(download_path)
            
            logger.info(f"✅ File downloaded successfully: {download_path}")
            
            response = f"File '{filename}' downloaded successfully!\n\n"
            response += f"📄 {filename}\n"
            response += f"📁 Saved to: {download_path}\n"
            response += f"📏 Size: {DriveToolHelper._format_file_size(file_size)}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to download file: {str(e)}")
            return f"Failed to download file: {str(e)}"
    
    @tool
    def list_recent_drive_files_tool(input_data: ListFilesInput) -> str:
        """
        List recent files from Google Drive.
        
        Shows recently modified files with optional filtering by file types.
        Useful for finding recently worked on documents.
        """
        logger.info(f"📋 Listing {input_data.max_results} recent Drive files")
        
        try:
            client = auth_manager.get_authenticated_client('drive', 'v3', input_data.user_id)
            if not client:
                raise Exception("Drive authentication failed")
            
            # Build query for file types
            query_parts = ["trashed = false"]
            
            if input_data.file_types:
                type_conditions = []
                for file_type in input_data.file_types:
                    # Handle common file type shortcuts
                    type_mapping = {
                        'pdf': 'application/pdf',
                        'doc': 'application/vnd.google-apps.document',
                        'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                        'sheet': 'application/vnd.google-apps.spreadsheet',
                        'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        'image': 'image/',
                        'video': 'video/',
                        'audio': 'audio/'
                    }
                    
                    mime_type = type_mapping.get(file_type.lower(), file_type)
                    if mime_type.endswith('/'):
                        type_conditions.append(f"mimeType contains '{mime_type}'")
                    else:
                        type_conditions.append(f"mimeType = '{mime_type}'")
                
                if type_conditions:
                    query_parts.append(f"({' or '.join(type_conditions)})")
            
            search_query = " and ".join(query_parts)
            
            # Get recent files
            results = client.files().list(
                q=search_query,
                pageSize=input_data.max_results,
                orderBy='modifiedTime desc' if input_data.recent else 'name',
                fields="files(id,name,size,mimeType,modifiedTime,webViewLink,parents,shared,owners)"
            ).execute()
            
            files = results.get('files', [])
            
            logger.info(f"✅ Retrieved {len(files)} recent files")
            
            # Format response
            if files:
                response = f"Recent files from Google Drive ({len(files)} found):\n\n"
                for i, file in enumerate(files, 1):
                    response += f"{i}. {DriveToolHelper._format_file_summary(file)}\n"
                return response
            else:
                return "No recent files found in Google Drive."
            
        except Exception as e:
            logger.error(f"❌ Failed to list recent files: {str(e)}")
            return f"Failed to list recent files: {str(e)}"
    
    @tool
    def get_drive_file_info_tool(input_data: GetFileInfoInput) -> str:
        """
        Get detailed information about a specific Google Drive file.
        
        Retrieves comprehensive file details including permissions,
        sharing status, and metadata.
        """
        logger.info(f"🔍 Getting Drive file info: {input_data.file_id}")
        
        try:
            client = auth_manager.get_authenticated_client('drive', 'v3', input_data.user_id)
            if not client:
                raise Exception("Drive authentication failed")
            
            # Get file details
            file_details = client.files().get(
                fileId=input_data.file_id,
                fields="*"
            ).execute()
            
            # Get permissions
            permissions = client.permissions().list(fileId=input_data.file_id).execute()
            
            logger.info(f"✅ Retrieved file details: {input_data.file_id}")
            
            # Format detailed response
            response = f"Google Drive File Details:\n\n"
            response += DriveToolHelper._format_file_summary(file_details)
            
            # Add description if present
            description = file_details.get('description', '')
            if description:
                response += f"   📝 Description: {description[:200]}{'...' if len(description) > 200 else ''}\n"
            
            # Add sharing information
            perm_list = permissions.get('permissions', [])
            if perm_list:
                response += f"   👥 Shared with {len(perm_list)} user(s):\n"
                for perm in perm_list[:5]:  # Limit to first 5
                    perm_type = perm.get('type', 'unknown')
                    role = perm.get('role', 'unknown')
                    if perm_type == 'anyone':
                        response += f"      • Public access ({role})\n"
                    else:
                        email = perm.get('emailAddress', 'Unknown user')
                        response += f"      • {email} ({role})\n"
                if len(perm_list) > 5:
                    response += f"      ... and {len(perm_list) - 5} more\n"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to get file info: {str(e)}")
            return f"Failed to get file info: {str(e)}"
    
    # Return list of tools
    tools = [
        upload_file_to_drive_tool,
        search_files_in_drive_tool,
        share_drive_file_tool,
        download_drive_file_tool,
        list_recent_drive_files_tool,
        get_drive_file_info_tool
    ]
    
    logger.info(f"✅ Created {len(tools)} Drive tools with auth injection")
    return tools

# Tool metadata for the orchestrator - KEEP YOUR EXISTING METADATA
DRIVE_TOOL_METADATA = {
    "upload_file_to_drive_tool": {
        "description": "Upload files to Google Drive",
        "parameters": ["file_path", "filename", "folder_id", "make_public"],
        "outputs": ["file_id", "share_link", "upload_confirmation"]
    },
    "search_files_in_drive_tool": {
        "description": "Search files in Google Drive",
        "parameters": ["query", "file_type", "folder_id"],
        "outputs": ["file_list", "file_ids", "file_details"]
    },
    "share_drive_file_tool": {
        "description": "Share Drive files with users",
        "parameters": ["file_id", "email_addresses", "role", "make_public"],
        "outputs": ["share_confirmation", "permissions_created"]
    },
    "download_drive_file_tool": {
        "description": "Download files from Google Drive",
        "parameters": ["file_id", "download_path"],
        "outputs": ["download_confirmation", "local_path"]
    },
    "list_recent_drive_files_tool": {
        "description": "List recent Drive files",
        "parameters": ["max_results", "file_types", "recent"],
        "outputs": ["file_list", "recent_files"]
    },
    "get_drive_file_info_tool": {
        "description": "Get detailed file information",
        "parameters": ["file_id"],
        "outputs": ["file_details", "permissions", "sharing_status"]
    }
}
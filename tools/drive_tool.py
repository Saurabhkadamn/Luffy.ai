import os
import io
from typing import List, Dict, Any, Optional, Union
import mimetypes
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload, MediaIoBaseUpload

class DriveTool:
    """Google Drive operations tool for file management"""
    
    def __init__(self):
        self.service_name = 'drive'
        self.version = 'v3'
    
    def upload_file(self, google_client, file_path: Optional[str] = None,
                   file_content: Optional[bytes] = None, filename: Optional[str] = None,
                   folder_id: Optional[str] = None, description: Optional[str] = None,
                   make_public: bool = False) -> Dict[str, Any]:
        """Upload file to Google Drive"""
        try:
            service = google_client
            
            # Determine file details
            if file_path:
                if not os.path.exists(file_path):
                    raise FileNotFoundError(f"File not found: {file_path}")
                
                filename = filename or os.path.basename(file_path)
                mime_type, _ = mimetypes.guess_type(file_path)
                media = MediaFileUpload(file_path, mimetype=mime_type)
                
            elif file_content and filename:
                mime_type, _ = mimetypes.guess_type(filename)
                if mime_type is None:
                    mime_type = 'application/octet-stream'
                
                file_stream = io.BytesIO(file_content)
                media = MediaIoBaseUpload(file_stream, mimetype=mime_type)
                
            else:
                raise ValueError("Either file_path or (file_content + filename) must be provided")
            
            # File metadata
            file_metadata = {
                'name': filename,
            }
            
            if description:
                file_metadata['description'] = description
            
            if folder_id:
                file_metadata['parents'] = [folder_id]
            
            # Upload file
            result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id,name,size,mimeType,webViewLink,webContentLink'
            ).execute()
            
            # Make public if requested
            if make_public:
                self._make_file_public(service, result['id'])
            
            return {
                'success': True,
                'data': {
                    'file_id': result['id'],
                    'filename': result['name'],
                    'size': int(result.get('size', 0)),
                    'mime_type': result['mimeType'],
                    'web_view_link': result['webViewLink'],
                    'download_link': result.get('webContentLink', ''),
                    'is_public': make_public
                },
                'error': None,
                'message': f"File '{filename}' uploaded successfully"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to upload file: {str(e)}"
            }
    
    def search_files(self, google_client, query: Optional[str] = None,
                    file_type: Optional[str] = None, folder_id: Optional[str] = None,
                    max_results: int = 20, include_trashed: bool = False) -> Dict[str, Any]:
        """Search files in Google Drive"""
        try:
            service = google_client
            
            # Build search query
            search_parts = []
            
            if query:
                search_parts.append(f"name contains '{query}'")
            
            if file_type:
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
                    search_parts.append(f"mimeType contains '{mime_type}'")
                else:
                    search_parts.append(f"mimeType = '{mime_type}'")
            
            if folder_id:
                search_parts.append(f"'{folder_id}' in parents")
            
            if not include_trashed:
                search_parts.append("trashed = false")
            
            search_query = " and ".join(search_parts) if search_parts else "trashed = false"
            
            # Execute search
            results = service.files().list(
                q=search_query,
                pageSize=max_results,
                fields="files(id,name,size,mimeType,modifiedTime,webViewLink,parents,shared)"
            ).execute()
            
            files = results.get('files', [])
            formatted_files = []
            
            for file in files:
                formatted_file = self._format_file_details(file)
                formatted_files.append(formatted_file)
            
            return {
                'success': True,
                'data': {
                    'files': formatted_files,
                    'total_count': len(formatted_files),
                    'search_query': search_query
                },
                'error': None,
                'message': f"Found {len(formatted_files)} files"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to search files: {str(e)}"
            }
    
    def download_file(self, google_client, file_id: str, 
                     download_path: Optional[str] = None) -> Dict[str, Any]:
        """Download file from Google Drive"""
        try:
            service = google_client
            
            # Get file metadata
            file_metadata = service.files().get(fileId=file_id).execute()
            filename = file_metadata['name']
            
            # Determine download path
            if download_path is None:
                download_path = filename
            elif os.path.isdir(download_path):
                download_path = os.path.join(download_path, filename)
            
            # Download file
            request = service.files().get_media(fileId=file_id)
            file_io = io.BytesIO()
            downloader = MediaIoBaseDownload(file_io, request)
            
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            
            # Save to file
            with open(download_path, 'wb') as f:
                f.write(file_io.getvalue())
            
            file_size = os.path.getsize(download_path)
            
            return {
                'success': True,
                'data': {
                    'file_id': file_id,
                    'filename': filename,
                    'download_path': download_path,
                    'file_size': file_size
                },
                'error': None,
                'message': f"File '{filename}' downloaded to '{download_path}'"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to download file: {str(e)}"
            }
    
    def share_file(self, google_client, file_id: str, 
                  email_addresses: Optional[List[str]] = None,
                  role: str = 'reader', make_public: bool = False,
                  send_notification: bool = True) -> Dict[str, Any]:
        """Share file with users or make public"""
        try:
            service = google_client
            
            # Get file details
            file_metadata = service.files().get(fileId=file_id, fields='name,webViewLink').execute()
            filename = file_metadata['name']
            
            permissions_created = []
            
            # Share with specific users
            if email_addresses:
                for email in email_addresses:
                    permission = {
                        'type': 'user',
                        'role': role,
                        'emailAddress': email
                    }
                    
                    result = service.permissions().create(
                        fileId=file_id,
                        body=permission,
                        sendNotificationEmail=send_notification
                    ).execute()
                    
                    permissions_created.append({
                        'email': email,
                        'role': role,
                        'permission_id': result['id']
                    })
            
            # Make public if requested
            if make_public:
                public_permission = {
                    'type': 'anyone',
                    'role': 'reader'
                }
                
                result = service.permissions().create(
                    fileId=file_id,
                    body=public_permission
                ).execute()
                
                permissions_created.append({
                    'type': 'public',
                    'role': 'reader',
                    'permission_id': result['id']
                })
            
            return {
                'success': True,
                'data': {
                    'file_id': file_id,
                    'filename': filename,
                    'web_view_link': file_metadata['webViewLink'],
                    'permissions_created': permissions_created,
                    'is_public': make_public,
                    'shared_with_count': len(email_addresses) if email_addresses else 0
                },
                'error': None,
                'message': f"File '{filename}' shared successfully"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to share file: {str(e)}"
            }
    
    def list_recent_files(self, google_client, max_results: int = 20,
                         file_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """List recent files from Google Drive"""
        try:
            service = google_client
            
            # Build query for file types
            query_parts = ["trashed = false"]
            
            if file_types:
                type_conditions = []
                for file_type in file_types:
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
            results = service.files().list(
                q=search_query,
                pageSize=max_results,
                orderBy='modifiedTime desc',
                fields="files(id,name,size,mimeType,modifiedTime,webViewLink,parents,shared,owners)"
            ).execute()
            
            files = results.get('files', [])
            formatted_files = []
            
            for file in files:
                formatted_file = self._format_file_details(file)
                formatted_files.append(formatted_file)
            
            return {
                'success': True,
                'data': {
                    'files': formatted_files,
                    'total_count': len(formatted_files),
                    'file_types_filter': file_types
                },
                'error': None,
                'message': f"Retrieved {len(formatted_files)} recent files"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to list recent files: {str(e)}"
            }
    
    def get_file_info(self, google_client, file_id: str) -> Dict[str, Any]:
        """Get detailed information about a specific file"""
        try:
            service = google_client
            
            # Get file details
            file_details = service.files().get(
                fileId=file_id,
                fields="*"
            ).execute()
            
            # Get permissions
            permissions = service.permissions().list(fileId=file_id).execute()
            
            formatted_file = self._format_file_details(file_details)
            formatted_file['permissions'] = self._format_permissions(permissions.get('permissions', []))
            
            return {
                'success': True,
                'data': {
                    'file_details': formatted_file
                },
                'error': None,
                'message': f"Retrieved details for '{formatted_file['name']}'"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to get file info: {str(e)}"
            }
    
    def _make_file_public(self, service, file_id: str):
        """Make file publicly accessible"""
        permission = {
            'type': 'anyone',
            'role': 'reader'
        }
        service.permissions().create(fileId=file_id, body=permission).execute()
    
    def _format_file_details(self, file: Dict[str, Any]) -> Dict[str, Any]:
        """Format file details for consistent response"""
        return {
            'id': file.get('id', ''),
            'name': file.get('name', ''),
            'size': int(file.get('size', 0)) if file.get('size') else 0,
            'size_readable': self._format_file_size(int(file.get('size', 0)) if file.get('size') else 0),
            'mime_type': file.get('mimeType', ''),
            'file_type': self._get_file_type(file.get('mimeType', '')),
            'modified_time': file.get('modifiedTime', ''),
            'created_time': file.get('createdTime', ''),
            'web_view_link': file.get('webViewLink', ''),
            'download_link': file.get('webContentLink', ''),
            'is_shared': file.get('shared', False),
            'parents': file.get('parents', []),
            'owners': [owner.get('displayName', owner.get('emailAddress', '')) 
                      for owner in file.get('owners', [])]
        }
    
    def _format_permissions(self, permissions: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Format permissions for response"""
        formatted = []
        for perm in permissions:
            formatted.append({
                'id': perm.get('id', ''),
                'type': perm.get('type', ''),
                'role': perm.get('role', ''),
                'email': perm.get('emailAddress', ''),
                'display_name': perm.get('displayName', '')
            })
        return formatted
    
    def _get_file_type(self, mime_type: str) -> str:
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
    
    def _format_file_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format"""
        if size_bytes == 0:
            return "0 B"
        
        size_names = ["B", "KB", "MB", "GB", "TB"]
        i = 0
        while size_bytes >= 1024 and i < len(size_names) - 1:
            size_bytes /= 1024.0
            i += 1
        
        return f"{size_bytes:.1f} {size_names[i]}"
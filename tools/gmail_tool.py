import base64
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import mimetypes

class GmailTool:
    """Gmail operations tool with optional attachment support"""
    
    def __init__(self):
        self.service_name = 'gmail'
        self.version = 'v1'
    
    def _build_message(self, to: Union[str, List[str]], subject: str, body: str, 
                       cc: Optional[Union[str, List[str]]] = None,
                       bcc: Optional[Union[str, List[str]]] = None,
                       attachments: Optional[List[Union[str, Dict]]] = None) -> Dict[str, str]:
        """Build email message with optional attachments"""
        
        # Create message container
        if attachments:
            message = MIMEMultipart()
        else:
            message = MIMEText(body)
            message['to'] = self._format_recipients(to)
            message['subject'] = subject
            if cc:
                message['cc'] = self._format_recipients(cc)
            if bcc:
                message['bcc'] = self._format_recipients(bcc)
            return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
        
        # For messages with attachments
        message['to'] = self._format_recipients(to)
        message['subject'] = subject
        if cc:
            message['cc'] = self._format_recipients(cc)
        if bcc:
            message['bcc'] = self._format_recipients(bcc)
        
        # Add body
        message.attach(MIMEText(body, 'plain'))
        
        # Add attachments
        for attachment in attachments:
            self._add_attachment(message, attachment)
        
        return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
    
    def _format_recipients(self, recipients: Union[str, List[str]]) -> str:
        """Format recipients as comma-separated string"""
        if isinstance(recipients, str):
            return recipients
        return ', '.join(recipients)
    
    def _add_attachment(self, message: MIMEMultipart, attachment: Union[str, Dict]):
        """Add attachment to message"""
        try:
            if isinstance(attachment, str):
                # File path
                if not os.path.exists(attachment):
                    raise FileNotFoundError(f"Attachment file not found: {attachment}")
                
                filename = os.path.basename(attachment)
                with open(attachment, 'rb') as f:
                    content = f.read()
                
                mime_type, _ = mimetypes.guess_type(attachment)
                if mime_type is None:
                    mime_type = 'application/octet-stream'
                
            elif isinstance(attachment, dict):
                # Dict with filename, content, mime_type
                filename = attachment['filename']
                content = attachment['content']
                mime_type = attachment.get('mime_type', 'application/octet-stream')
                
                if isinstance(content, str):
                    content = content.encode()
            
            # Create attachment part
            part = MIMEBase(*mime_type.split('/'))
            part.set_payload(content)
            encoders.encode_base64(part)
            part.add_header(
                'Content-Disposition',
                f'attachment; filename= {filename}'
            )
            message.attach(part)
            
        except Exception as e:
            raise Exception(f"Failed to add attachment {filename}: {str(e)}")
    
    def send_email(self, google_client, to: Union[str, List[str]], subject: str, body: str,
                   cc: Optional[Union[str, List[str]]] = None,
                   bcc: Optional[Union[str, List[str]]] = None,
                   attachments: Optional[List[Union[str, Dict]]] = None) -> Dict[str, Any]:
        """Send email with optional attachments"""
        try:
            service = google_client
            
            # Build message
            message = self._build_message(to, subject, body, cc, bcc, attachments)
            
            # Send message
            result = service.users().messages().send(userId='me', body=message).execute()
            
            attachment_count = len(attachments) if attachments else 0
            success_msg = f"Email sent successfully"
            if attachment_count > 0:
                success_msg += f" with {attachment_count} attachment(s)"
            
            return {
                'success': True,
                'data': {
                    'message_id': result['id'],
                    'thread_id': result['threadId'],
                    'attachment_count': attachment_count
                },
                'error': None,
                'message': success_msg
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to send email: {str(e)}"
            }
    
    def read_recent_emails(self, google_client, max_results: int = 10, 
                          query: Optional[str] = None,
                          include_attachments: bool = False) -> Dict[str, Any]:
        """Read recent emails with optional attachment info"""
        try:
            service = google_client
            
            # Get message list
            search_query = query if query else 'in:inbox'
            results = service.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for msg in messages:
                email_data = self._get_email_details(service, msg['id'], include_attachments)
                if email_data:
                    emails.append(email_data)
            
            return {
                'success': True,
                'data': {
                    'emails': emails,
                    'total_count': len(emails)
                },
                'error': None,
                'message': f"Retrieved {len(emails)} recent emails"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to read emails: {str(e)}"
            }
    
    def search_emails_by_filters(self, google_client,
                                sender: Optional[str] = None,
                                date_range: Optional[tuple] = None,
                                keywords: Optional[Union[str, List[str]]] = None,
                                has_attachment: Optional[bool] = None,
                                include_attachments: bool = False,
                                max_results: int = 20) -> Dict[str, Any]:
        """Search emails by various filters"""
        try:
            service = google_client
            
            # Build search query
            query_parts = []
            
            if sender:
                query_parts.append(f"from:{sender}")
            
            if date_range:
                start_date, end_date = date_range
                if isinstance(start_date, str):
                    query_parts.append(f"after:{start_date}")
                if isinstance(end_date, str):
                    query_parts.append(f"before:{end_date}")
            
            if keywords:
                if isinstance(keywords, str):
                    query_parts.append(f"({keywords})")
                else:
                    keyword_query = " OR ".join(keywords)
                    query_parts.append(f"({keyword_query})")
            
            if has_attachment is not None:
                if has_attachment:
                    query_parts.append("has:attachment")
                else:
                    query_parts.append("-has:attachment")
            
            search_query = " ".join(query_parts) if query_parts else "in:inbox"
            
            # Execute search
            results = service.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for msg in messages:
                email_data = self._get_email_details(service, msg['id'], include_attachments)
                if email_data:
                    emails.append(email_data)
            
            return {
                'success': True,
                'data': {
                    'emails': emails,
                    'search_query': search_query,
                    'total_count': len(emails)
                },
                'error': None,
                'message': f"Found {len(emails)} emails matching filters"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to search emails: {str(e)}"
            }
    
    def get_email_threads(self, google_client,
                         thread_id: Optional[str] = None,
                         query: Optional[str] = None,
                         include_attachments: bool = False) -> Dict[str, Any]:
        """Get email thread conversations"""
        try:
            service = google_client
            
            if thread_id:
                # Get specific thread
                thread = service.users().threads().get(userId='me', id=thread_id).execute()
                threads_data = [self._process_thread(service, thread, include_attachments)]
            
            elif query:
                # Search for threads
                results = service.users().threads().list(
                    userId='me',
                    q=query,
                    maxResults=10
                ).execute()
                
                threads = results.get('threads', [])
                threads_data = []
                
                for thread in threads:
                    thread_details = service.users().threads().get(
                        userId='me', 
                        id=thread['id']
                    ).execute()
                    threads_data.append(self._process_thread(service, thread_details, include_attachments))
            
            else:
                return {
                    'success': False,
                    'data': None,
                    'error': "Either thread_id or query must be provided",
                    'message': "Missing thread identifier"
                }
            
            return {
                'success': True,
                'data': {
                    'threads': threads_data,
                    'total_count': len(threads_data)
                },
                'error': None,
                'message': f"Retrieved {len(threads_data)} thread(s)"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to get threads: {str(e)}"
            }
    
    def _get_email_details(self, service, message_id: str, include_attachments: bool = False) -> Dict[str, Any]:
        """Get detailed email information"""
        try:
            message = service.users().messages().get(userId='me', id=message_id).execute()
            
            headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
            
            # Extract body
            body = self._extract_body(message['payload'])
            
            email_data = {
                'id': message['id'],
                'thread_id': message['threadId'],
                'from': headers.get('From', ''),
                'to': headers.get('To', ''),
                'subject': headers.get('Subject', ''),
                'date': headers.get('Date', ''),
                'body': body,
                'snippet': message.get('snippet', '')
            }
            
            # Add attachment info if requested
            if include_attachments:
                attachments = self._extract_attachments(message['payload'])
                email_data['attachments'] = attachments
                email_data['has_attachments'] = len(attachments) > 0
            
            return email_data
            
        except Exception as e:
            print(f"Error getting email details: {e}")
            return None
    
    def _extract_body(self, payload: Dict) -> str:
        """Extract email body from payload"""
        body = ""
        
        if 'parts' in payload:
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain':
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                        break
                elif part['mimeType'] == 'text/html' and not body:
                    if 'data' in part['body']:
                        body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
        else:
            if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
                body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body
    
    def _extract_attachments(self, payload: Dict) -> List[Dict[str, Any]]:
        """Extract attachment information from payload"""
        attachments = []
        
        def process_parts(parts):
            for part in parts:
                if 'filename' in part and part['filename']:
                    attachment = {
                        'filename': part['filename'],
                        'mime_type': part['mimeType'],
                        'size': part['body'].get('size', 0),
                        'attachment_id': part['body'].get('attachmentId', '')
                    }
                    attachments.append(attachment)
                
                if 'parts' in part:
                    process_parts(part['parts'])
        
        if 'parts' in payload:
            process_parts(payload['parts'])
        
        return attachments
    
    def _process_thread(self, service, thread: Dict, include_attachments: bool = False) -> Dict[str, Any]:
        """Process thread data"""
        messages = []
        
        for message in thread['messages']:
            email_data = self._get_email_details(service, message['id'], include_attachments)
            if email_data:
                messages.append(email_data)
        
        return {
            'thread_id': thread['id'],
            'message_count': len(messages),
            'messages': messages
        }
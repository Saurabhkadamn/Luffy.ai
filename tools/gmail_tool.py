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
import logging

# LangChain tool imports
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)

# Pydantic models - KEEP YOUR EXISTING SCHEMAS
class SendEmailInput(BaseModel):
    """Input schema for sending emails"""
    to: Union[str, List[str]] = Field(description="Email recipient(s)")
    subject: str = Field(description="Email subject line")
    body: str = Field(description="Email body content")
    cc: Optional[Union[str, List[str]]] = Field(default=None, description="CC recipients")
    bcc: Optional[Union[str, List[str]]] = Field(default=None, description="BCC recipients")
    user_id: str = Field(description="User ID for authentication")

class SearchEmailsInput(BaseModel):
    """Input schema for searching emails"""
    sender: Optional[str] = Field(default=None, description="Filter by sender email")
    date_range: Optional[List[str]] = Field(default=None, description="Date range [start, end]")
    keywords: Optional[Union[str, List[str]]] = Field(default=None, description="Keywords to search")
    has_attachment: Optional[bool] = Field(default=None, description="Filter by attachments")
    max_results: int = Field(default=20, description="Maximum results")
    user_id: str = Field(description="User ID for authentication")

class ReadEmailsInput(BaseModel):
    """Input schema for reading recent emails"""
    max_results: int = Field(default=10, description="Maximum emails to read")
    query: Optional[str] = Field(default=None, description="Gmail search query")
    include_attachments: bool = Field(default=False, description="Include attachment info")
    user_id: str = Field(description="User ID for authentication")

class GetThreadsInput(BaseModel):
    """Input schema for getting email threads"""
    thread_id: Optional[str] = Field(default=None, description="Specific thread ID")
    query: Optional[str] = Field(default=None, description="Search query for threads")
    include_attachments: bool = Field(default=False, description="Include attachments")
    user_id: str = Field(description="User ID for authentication")

# Gmail Helper Class - KEEP YOUR EXISTING LOGIC
class GmailToolHelper:
    """Helper class containing Gmail API operations"""
    
    @staticmethod
    def _build_message(to: Union[str, List[str]], subject: str, body: str, 
                       cc: Optional[Union[str, List[str]]] = None,
                       bcc: Optional[Union[str, List[str]]] = None,
                       attachments: Optional[List[Union[str, Dict]]] = None) -> Dict[str, str]:
        """Build email message with optional attachments"""
        
        if attachments:
            message = MIMEMultipart()
        else:
            message = MIMEText(body)
            message['to'] = GmailToolHelper._format_recipients(to)
            message['subject'] = subject
            if cc:
                message['cc'] = GmailToolHelper._format_recipients(cc)
            if bcc:
                message['bcc'] = GmailToolHelper._format_recipients(bcc)
            return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
        
        # For messages with attachments
        message['to'] = GmailToolHelper._format_recipients(to)
        message['subject'] = subject
        if cc:
            message['cc'] = GmailToolHelper._format_recipients(cc)
        if bcc:
            message['bcc'] = GmailToolHelper._format_recipients(bcc)
        
        # Add body
        message.attach(MIMEText(body, 'plain'))
        
        # Add attachments
        for attachment in attachments:
            GmailToolHelper._add_attachment(message, attachment)
        
        return {'raw': base64.urlsafe_b64encode(message.as_bytes()).decode()}
    
    @staticmethod
    def _format_recipients(recipients: Union[str, List[str]]) -> str:
        """Format recipients as comma-separated string"""
        if isinstance(recipients, str):
            return recipients
        return ', '.join(recipients)
    
    @staticmethod
    def _add_attachment(message: MIMEMultipart, attachment: Union[str, Dict]):
        """Add attachment to message"""
        try:
            if isinstance(attachment, str):
                if not os.path.exists(attachment):
                    raise FileNotFoundError(f"Attachment file not found: {attachment}")
                
                filename = os.path.basename(attachment)
                with open(attachment, 'rb') as f:
                    content = f.read()
                
                mime_type, _ = mimetypes.guess_type(attachment)
                if mime_type is None:
                    mime_type = 'application/octet-stream'
                
            elif isinstance(attachment, dict):
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
    
    @staticmethod
    def _get_email_details(service, message_id: str, include_attachments: bool = False) -> Dict[str, Any]:
        """Get detailed email information"""
        try:
            message = service.users().messages().get(userId='me', id=message_id).execute()
            
            headers = {h['name']: h['value'] for h in message['payload'].get('headers', [])}
            
            # Extract body
            body = GmailToolHelper._extract_body(message['payload'])
            
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
            
            if include_attachments:
                attachments = GmailToolHelper._extract_attachments(message['payload'])
                email_data['attachments'] = attachments
                email_data['has_attachments'] = len(attachments) > 0
            
            return email_data
            
        except Exception as e:
            logger.error(f"Error getting email details: {e}")
            return None
    
    @staticmethod
    def _extract_body(payload: Dict) -> str:
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
    
    @staticmethod
    def _extract_attachments(payload: Dict) -> List[Dict[str, Any]]:
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

# FACTORY FUNCTION - This is the key change!
def create_gmail_tools(auth_manager) -> List[BaseTool]:
    """
    Create Gmail tools with auth_manager dependency injected.
    
    This approach:
    - Keeps your session state token storage (perfect for demos)
    - Removes Streamlit coupling from tools  
    - Makes tools testable
    - Clean dependency injection
    """
    logger.info("🔧 Creating Gmail tools with auth injection")
    
    # Create tools that close over auth_manager
    @tool
    def send_email_tool(input_data: SendEmailInput) -> str:
        """
        Send an email via Gmail API.
        
        Sends email to specified recipients with subject and body.
        Supports CC, BCC, and basic formatting.
        """
        logger.info(f"📧 Sending email to: {input_data.to}")
        
        try:
            # FIXED: Use injected auth_manager (which still uses session state internally)
            client = auth_manager.get_authenticated_client('gmail', 'v1', input_data.user_id)
            if not client:
                raise Exception("Gmail authentication failed")
            
            # Build message
            message = GmailToolHelper._build_message(
                input_data.to, 
                input_data.subject, 
                input_data.body, 
                input_data.cc, 
                input_data.bcc
            )
            
            # Send message
            result = client.users().messages().send(userId='me', body=message).execute()
            
            logger.info(f"✅ Email sent successfully: {result['id']}")
            
            return f"Email sent successfully to {input_data.to}. Message ID: {result['id']}"
            
        except Exception as e:
            logger.error(f"❌ Failed to send email: {str(e)}")
            return f"Failed to send email: {str(e)}"
    
    @tool
    def search_emails_tool(input_data: SearchEmailsInput) -> str:
        """
        Search emails using Gmail API with filters.
        
        Search emails by sender, date range, keywords, and attachment status.
        Returns formatted list of matching emails.
        """
        logger.info(f"🔍 Searching emails with filters")
        
        try:
            # Use injected auth_manager
            client = auth_manager.get_authenticated_client('gmail', 'v1', input_data.user_id)
            if not client:
                raise Exception("Gmail authentication failed")
            
            # Build search query
            query_parts = []
            
            if input_data.sender:
                query_parts.append(f"from:{input_data.sender}")
            
            if input_data.date_range:
                start_date, end_date = input_data.date_range
                query_parts.append(f"after:{start_date}")
                query_parts.append(f"before:{end_date}")
            
            if input_data.keywords:
                if isinstance(input_data.keywords, str):
                    query_parts.append(f"({input_data.keywords})")
                else:
                    keyword_query = " OR ".join(input_data.keywords)
                    query_parts.append(f"({keyword_query})")
            
            if input_data.has_attachment is not None:
                if input_data.has_attachment:
                    query_parts.append("has:attachment")
                else:
                    query_parts.append("-has:attachment")
            
            search_query = " ".join(query_parts) if query_parts else "in:inbox"
            
            # Execute search
            results = client.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=input_data.max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for msg in messages[:5]:  # Limit detail for tool output
                email_data = GmailToolHelper._get_email_details(client, msg['id'], False)
                if email_data:
                    emails.append({
                        'from': email_data['from'],
                        'subject': email_data['subject'],
                        'date': email_data['date'],
                        'snippet': email_data['snippet'][:100] + '...' if len(email_data['snippet']) > 100 else email_data['snippet']
                    })
            
            logger.info(f"✅ Found {len(messages)} emails, returning {len(emails)} details")
            
            # Format response
            if emails:
                response = f"Found {len(messages)} emails matching search criteria:\n\n"
                for i, email in enumerate(emails, 1):
                    response += f"{i}. From: {email['from']}\n"
                    response += f"   Subject: {email['subject']}\n"
                    response += f"   Date: {email['date']}\n"
                    response += f"   Preview: {email['snippet']}\n\n"
                return response
            else:
                return "No emails found matching the search criteria."
            
        except Exception as e:
            logger.error(f"❌ Failed to search emails: {str(e)}")
            return f"Failed to search emails: {str(e)}"
    
    @tool
    def read_recent_emails_tool(input_data: ReadEmailsInput) -> str:
        """
        Read recent emails from Gmail inbox.
        
        Retrieves and formats recent emails with sender, subject, and preview.
        Useful for getting overview of recent activity.
        """
        logger.info(f"📬 Reading {input_data.max_results} recent emails")
        
        try:
            client = auth_manager.get_authenticated_client('gmail', 'v1', input_data.user_id)
            if not client:
                raise Exception("Gmail authentication failed")
            
            # Get message list
            search_query = input_data.query if input_data.query else 'in:inbox'
            results = client.users().messages().list(
                userId='me',
                q=search_query,
                maxResults=input_data.max_results
            ).execute()
            
            messages = results.get('messages', [])
            emails = []
            
            for msg in messages:
                email_data = GmailToolHelper._get_email_details(client, msg['id'], input_data.include_attachments)
                if email_data:
                    emails.append(email_data)
            
            logger.info(f"✅ Retrieved {len(emails)} recent emails")
            
            # Format response
            if emails:
                response = f"Recent {len(emails)} emails:\n\n"
                for i, email in enumerate(emails, 1):
                    response += f"{i}. From: {email['from']}\n"
                    response += f"   Subject: {email['subject']}\n"
                    response += f"   Date: {email['date']}\n"
                    response += f"   Preview: {email['snippet'][:100]}...\n"
                    if input_data.include_attachments and email.get('has_attachments'):
                        response += f"   Attachments: {len(email.get('attachments', []))}\n"
                    response += "\n"
                return response
            else:
                return "No recent emails found."
            
        except Exception as e:
            logger.error(f"❌ Failed to read emails: {str(e)}")
            return f"Failed to read emails: {str(e)}"
    
    @tool
    def get_email_threads_tool(input_data: GetThreadsInput) -> str:
        """
        Get email thread conversations.
        
        Retrieves complete email threads for conversation context.
        Can get specific thread by ID or search for threads.
        """
        logger.info(f"🧵 Getting email threads")
        
        try:
            client = auth_manager.get_authenticated_client('gmail', 'v1', input_data.user_id)
            if not client:
                raise Exception("Gmail authentication failed")
            
            if input_data.thread_id:
                # Get specific thread
                thread = client.users().threads().get(userId='me', id=input_data.thread_id).execute()
                threads_data = [GmailToolHelper._process_thread(client, thread, input_data.include_attachments)]
            
            elif input_data.query:
                # Search for threads
                results = client.users().threads().list(
                    userId='me',
                    q=input_data.query,
                    maxResults=5  # Limit for tool output
                ).execute()
                
                threads = results.get('threads', [])
                threads_data = []
                
                for thread in threads:
                    thread_details = client.users().threads().get(
                        userId='me', 
                        id=thread['id']
                    ).execute()
                    
                    processed_thread = GmailToolHelper._process_thread(client, thread_details, input_data.include_attachments)
                    threads_data.append(processed_thread)
            
            else:
                return "Either thread_id or query must be provided"
            
            logger.info(f"✅ Retrieved {len(threads_data)} thread(s)")
            
            # Format response
            if threads_data:
                response = f"Email threads ({len(threads_data)} found):\n\n"
                for i, thread in enumerate(threads_data, 1):
                    response += f"Thread {i} (ID: {thread['thread_id']}):\n"
                    response += f"  Messages: {thread['message_count']}\n"
                    
                    # Show first and last message
                    messages = thread['messages']
                    if messages:
                        response += f"  First: {messages[0]['subject']} from {messages[0]['from']}\n"
                        if len(messages) > 1:
                            response += f"  Latest: {messages[-1]['subject']} from {messages[-1]['from']}\n"
                    response += "\n"
                
                return response
            else:
                return "No threads found."
            
        except Exception as e:
            logger.error(f"❌ Failed to get threads: {str(e)}")
            return f"Failed to get threads: {str(e)}"
    
    # Return list of tools
    tools = [
        send_email_tool,
        search_emails_tool, 
        read_recent_emails_tool,
        get_email_threads_tool
    ]
    
    logger.info(f"✅ Created {len(tools)} Gmail tools with auth injection")
    return tools

# Tool metadata for the orchestrator - KEEP YOUR EXISTING METADATA
GMAIL_TOOL_METADATA = {
    "send_email_tool": {
        "description": "Send emails to recipients",
        "parameters": ["to", "subject", "body", "cc", "bcc"],
        "outputs": ["message_id", "success_status"]
    },
    "search_emails_tool": {
        "description": "Search emails with filters",
        "parameters": ["sender", "date_range", "keywords", "has_attachment"],
        "outputs": ["email_list", "sender_addresses", "subjects"]
    },
    "read_recent_emails_tool": {
        "description": "Read recent emails from inbox",
        "parameters": ["max_results", "query"],
        "outputs": ["email_list", "contacts", "recent_subjects"]
    },
    "get_email_threads_tool": {
        "description": "Get email conversation threads",
        "parameters": ["thread_id", "query"],
        "outputs": ["thread_data", "conversation_history"]
    }
}
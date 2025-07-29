from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import uuid
import logging

# LangChain tool imports
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

# Configure logging
logger = logging.getLogger(__name__)

# Pydantic models for tool inputs - KEEP YOUR EXISTING SCHEMAS
class CreateEventInput(BaseModel):
    """Input schema for creating calendar events"""
    title: str = Field(description="Event title/subject")
    start_time: str = Field(description="Start time in ISO format")
    end_time: str = Field(description="End time in ISO format")
    description: Optional[str] = Field(default=None, description="Event description")
    attendees: Optional[List[str]] = Field(default=None, description="Attendee email addresses")
    location: Optional[str] = Field(default=None, description="Event location")
    include_meet: bool = Field(default=False, description="Include Google Meet link")
    timezone: str = Field(default='UTC', description="Timezone for the event")
    user_id: str = Field(description="User ID for authentication")

class ListEventsInput(BaseModel):
    """Input schema for listing calendar events"""
    start_date: str = Field(description="Start date in YYYY-MM-DD format")
    end_date: Optional[str] = Field(default=None, description="End date in YYYY-MM-DD format")
    max_results: int = Field(default=50, description="Maximum number of events")
    timezone: str = Field(default='UTC', description="Timezone for the query")
    user_id: str = Field(description="User ID for authentication")

class UpdateEventInput(BaseModel):
    """Input schema for updating calendar events"""
    event_id: str = Field(description="ID of the event to update")
    title: Optional[str] = Field(default=None, description="New event title")
    start_time: Optional[str] = Field(default=None, description="New start time in ISO format")
    end_time: Optional[str] = Field(default=None, description="New end time in ISO format")
    description: Optional[str] = Field(default=None, description="New event description")
    attendees: Optional[List[str]] = Field(default=None, description="New attendee list")
    location: Optional[str] = Field(default=None, description="New event location")
    add_meet: bool = Field(default=False, description="Add Google Meet link")
    timezone: str = Field(default='UTC', description="Timezone for the event")
    user_id: str = Field(description="User ID for authentication")

class DeleteEventInput(BaseModel):
    """Input schema for deleting calendar events"""
    event_id: str = Field(description="ID of the event to delete")
    user_id: str = Field(description="User ID for authentication")

class GetEventInput(BaseModel):
    """Input schema for getting event details"""
    event_id: str = Field(description="ID of the event to retrieve")
    user_id: str = Field(description="User ID for authentication")

# Calendar Tool Helper Class - KEEP YOUR EXISTING LOGIC
class CalendarToolHelper:
    """Helper class containing Calendar API operations"""
    
    @staticmethod
    def _build_event_object(title: str, start_time: Union[str, datetime],
                           end_time: Union[str, datetime], description: Optional[str],
                           attendees: Optional[List[str]], location: Optional[str],
                           timezone: str) -> Dict[str, Any]:
        """Build event object for Google Calendar API"""
        event = {
            'summary': title,
            'start': CalendarToolHelper._format_datetime_for_event(start_time, timezone),
            'end': CalendarToolHelper._format_datetime_for_event(end_time, timezone),
        }
        
        if description:
            event['description'] = description
        
        if location:
            event['location'] = location
        
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]
        
        return event
    
    @staticmethod
    def _format_datetime_for_event(dt: Union[str, datetime], timezone: str) -> Dict[str, str]:
        """Format datetime for Google Calendar API"""
        if isinstance(dt, str):
            return {
                'dateTime': dt,
                'timeZone': timezone
            }
        else:
            return {
                'dateTime': dt.isoformat(),
                'timeZone': timezone
            }
    
    @staticmethod
    def _format_datetime(dt: Union[str, datetime], timezone: str) -> str:
        """Format datetime to ISO string"""
        if isinstance(dt, str):
            return dt
        else:
            return dt.isoformat() + 'Z'
    
    @staticmethod
    def _extract_meet_link(event: Dict[str, Any]) -> Optional[str]:
        """Extract Google Meet link from event"""
        conference_data = event.get('conferenceData', {})
        entry_points = conference_data.get('entryPoints', [])
        
        for entry_point in entry_points:
            if entry_point.get('entryPointType') == 'video':
                return entry_point.get('uri')
        
        # Also check hangoutLink (legacy)
        return event.get('hangoutLink')
    
    @staticmethod
    def _format_attendees_response(attendees: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Format attendees for response"""
        formatted = []
        for attendee in attendees:
            formatted.append({
                'email': attendee.get('email', ''),
                'status': attendee.get('responseStatus', 'needsAction'),
                'name': attendee.get('displayName', '')
            })
        return formatted
    
    @staticmethod
    def _format_event_summary(event: Dict[str, Any]) -> str:
        """Format event for tool output"""
        start = event.get('start', {})
        end = event.get('end', {})
        
        title = event.get('summary', 'Untitled Event')
        start_time = start.get('dateTime', start.get('date', 'Unknown time'))
        location = event.get('location', '')
        attendees = event.get('attendees', [])
        
        summary = f"📅 {title}\n"
        summary += f"   🕐 {start_time}\n"
        if location:
            summary += f"   📍 {location}\n"
        if attendees:
            summary += f"   👥 {len(attendees)} attendee(s)\n"
        
        # Check for Meet link
        meet_link = CalendarToolHelper._extract_meet_link(event)
        if meet_link:
            summary += f"   🎥 Meet: {meet_link}\n"
        
        return summary

# FACTORY FUNCTION - Create Calendar tools with auth injection
def create_calendar_tools(auth_manager) -> List[BaseTool]:
    """
    Create Calendar tools with auth_manager dependency injected.
    
    Auth manager still uses session state internally (perfect for demos!)
    Tools no longer import Streamlit directly.
    """
    logger.info("🔧 Creating Calendar tools with auth injection")
    
    @tool
    def create_calendar_event_tool(input_data: CreateEventInput) -> str:
        """
        Create a calendar event with optional Google Meet integration.
        
        Creates a new calendar event with specified details. Can include Google Meet
        link for virtual meetings. Returns event details and Meet link if requested.
        """
        logger.info(f"📅 Creating calendar event: {input_data.title}")
        
        try:
            # FIXED: Use injected auth_manager instead of session state import
            client = auth_manager.get_authenticated_client('calendar', 'v3', input_data.user_id)
            if not client:
                raise Exception("Calendar authentication failed")
            
            # Build event object
            event = CalendarToolHelper._build_event_object(
                input_data.title, 
                input_data.start_time, 
                input_data.end_time,
                input_data.description, 
                input_data.attendees, 
                input_data.location, 
                input_data.timezone
            )
            
            # Add Google Meet conference if requested
            if input_data.include_meet:
                event['conferenceData'] = {
                    'createRequest': {
                        'requestId': str(uuid.uuid4()),
                        'conferenceSolutionKey': {
                            'type': 'hangoutsMeet'
                        }
                    }
                }
            
            # Create event
            result = client.events().insert(
                calendarId='primary', 
                body=event,
                conferenceDataVersion=1 if input_data.include_meet else 0
            ).execute()
            
            logger.info(f"✅ Event created successfully: {result['id']}")
            
            # Format response
            response = f"Calendar event '{input_data.title}' created successfully!\n\n"
            response += CalendarToolHelper._format_event_summary(result)
            response += f"   🆔 Event ID: {result['id']}\n"
            
            # Extract Meet link if present
            meet_link = CalendarToolHelper._extract_meet_link(result)
            if meet_link:
                response += f"   🎥 Google Meet: {meet_link}\n"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to create calendar event: {str(e)}")
            return f"Failed to create calendar event: {str(e)}"
    
    @tool
    def list_calendar_events_tool(input_data: ListEventsInput) -> str:
        """
        List calendar events within a date range.
        
        Retrieves calendar events for specified date range. Useful for checking
        availability, finding conflicts, or getting agenda overview.
        """
        logger.info(f"📋 Listing calendar events from {input_data.start_date}")
        
        try:
            client = auth_manager.get_authenticated_client('calendar', 'v3', input_data.user_id)
            if not client:
                raise Exception("Calendar authentication failed")
            
            # Format dates
            time_min = CalendarToolHelper._format_datetime(input_data.start_date, input_data.timezone)
            time_max = None
            if input_data.end_date:
                time_max = CalendarToolHelper._format_datetime(input_data.end_date, input_data.timezone)
            else:
                # Default to end of day if no end_date provided
                end_dt = datetime.strptime(input_data.start_date, '%Y-%m-%d')
                end_dt = end_dt.replace(hour=23, minute=59, second=59)
                time_max = CalendarToolHelper._format_datetime(end_dt, input_data.timezone)
            
            # Get events
            events_result = client.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=input_data.max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            logger.info(f"✅ Found {len(events)} calendar events")
            
            # Format response
            if events:
                response = f"Calendar events for {input_data.start_date} ({len(events)} found):\n\n"
                for i, event in enumerate(events, 1):
                    response += f"{i}. {CalendarToolHelper._format_event_summary(event)}\n"
                return response
            else:
                return f"No calendar events found for {input_data.start_date}"
            
        except Exception as e:
            logger.error(f"❌ Failed to list calendar events: {str(e)}")
            return f"Failed to list calendar events: {str(e)}"
    
    @tool
    def update_calendar_event_tool(input_data: UpdateEventInput) -> str:
        """
        Update an existing calendar event.
        
        Updates event details like title, time, attendees, or location.
        Can also add Google Meet link to existing events.
        """
        logger.info(f"✏️ Updating calendar event: {input_data.event_id}")
        
        try:
            client = auth_manager.get_authenticated_client('calendar', 'v3', input_data.user_id)
            if not client:
                raise Exception("Calendar authentication failed")
            
            # Get existing event
            existing_event = client.events().get(calendarId='primary', eventId=input_data.event_id).execute()
            original_title = existing_event.get('summary', 'Untitled Event')
            
            # Update fields
            if input_data.title:
                existing_event['summary'] = input_data.title
            if input_data.description:
                existing_event['description'] = input_data.description
            if input_data.location:
                existing_event['location'] = input_data.location
            
            if input_data.start_time:
                existing_event['start'] = CalendarToolHelper._format_datetime_for_event(input_data.start_time, input_data.timezone)
            if input_data.end_time:
                existing_event['end'] = CalendarToolHelper._format_datetime_for_event(input_data.end_time, input_data.timezone)
            
            if input_data.attendees:
                existing_event['attendees'] = [{'email': email} for email in input_data.attendees]
            
            # Add Meet link if requested and not already present
            if input_data.add_meet and 'conferenceData' not in existing_event:
                existing_event['conferenceData'] = {
                    'createRequest': {
                        'requestId': str(uuid.uuid4()),
                        'conferenceSolutionKey': {
                            'type': 'hangoutsMeet'
                        }
                    }
                }
            
            # Update event
            result = client.events().update(
                calendarId='primary',
                eventId=input_data.event_id,
                body=existing_event,
                conferenceDataVersion=1 if input_data.add_meet else 0
            ).execute()
            
            logger.info(f"✅ Event updated successfully: {input_data.event_id}")
            
            # Format response
            response = f"Calendar event '{original_title}' updated successfully!\n\n"
            response += CalendarToolHelper._format_event_summary(result)
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to update calendar event: {str(e)}")
            return f"Failed to update calendar event: {str(e)}"
    
    @tool
    def delete_calendar_event_tool(input_data: DeleteEventInput) -> str:
        """
        Delete a calendar event.
        
        Permanently removes a calendar event. Use with caution as this
        action cannot be undone.
        """
        logger.info(f"🗑️ Deleting calendar event: {input_data.event_id}")
        
        try:
            client = auth_manager.get_authenticated_client('calendar', 'v3', input_data.user_id)
            if not client:
                raise Exception("Calendar authentication failed")
            
            # Get event details before deletion for confirmation
            event = client.events().get(calendarId='primary', eventId=input_data.event_id).execute()
            event_title = event.get('summary', 'Untitled Event')
            
            # Delete event
            client.events().delete(calendarId='primary', eventId=input_data.event_id).execute()
            
            logger.info(f"✅ Event deleted successfully: {input_data.event_id}")
            
            return f"Calendar event '{event_title}' deleted successfully."
            
        except Exception as e:
            logger.error(f"❌ Failed to delete calendar event: {str(e)}")
            return f"Failed to delete calendar event: {str(e)}"
    
    @tool
    def get_calendar_event_tool(input_data: GetEventInput) -> str:
        """
        Get detailed information about a specific calendar event.
        
        Retrieves complete event details including attendees, location,
        description, and Google Meet link if present.
        """
        logger.info(f"🔍 Getting calendar event details: {input_data.event_id}")
        
        try:
            client = auth_manager.get_authenticated_client('calendar', 'v3', input_data.user_id)
            if not client:
                raise Exception("Calendar authentication failed")
            
            # Get event
            event = client.events().get(calendarId='primary', eventId=input_data.event_id).execute()
            
            logger.info(f"✅ Retrieved event details: {input_data.event_id}")
            
            # Format detailed response
            response = f"Calendar Event Details:\n\n"
            response += CalendarToolHelper._format_event_summary(event)
            
            # Add description if present
            description = event.get('description', '')
            if description:
                response += f"   📝 Description: {description[:200]}{'...' if len(description) > 200 else ''}\n"
            
            # Add attendee details
            attendees = event.get('attendees', [])
            if attendees:
                response += f"   👥 Attendees:\n"
                for attendee in attendees[:5]:  # Limit to first 5
                    email = attendee.get('email', 'Unknown')
                    status = attendee.get('responseStatus', 'needsAction')
                    response += f"      • {email} ({status})\n"
                if len(attendees) > 5:
                    response += f"      ... and {len(attendees) - 5} more\n"
            
            return response
            
        except Exception as e:
            logger.error(f"❌ Failed to get calendar event: {str(e)}")
            return f"Failed to get calendar event: {str(e)}"
    
    # Return list of tools
    tools = [
        create_calendar_event_tool,
        list_calendar_events_tool,
        update_calendar_event_tool,
        delete_calendar_event_tool,
        get_calendar_event_tool
    ]
    
    logger.info(f"✅ Created {len(tools)} Calendar tools with auth injection")
    return tools

# Tool metadata for the orchestrator - KEEP YOUR EXISTING METADATA
CALENDAR_TOOL_METADATA = {
    "create_calendar_event_tool": {
        "description": "Create calendar events with optional Google Meet",
        "parameters": ["title", "start_time", "end_time", "attendees", "include_meet"],
        "outputs": ["event_id", "meet_link", "event_details"]
    },
    "list_calendar_events_tool": {
        "description": "List calendar events in date range",
        "parameters": ["start_date", "end_date", "max_results"],
        "outputs": ["event_list", "availability", "conflicts"]
    },
    "update_calendar_event_tool": {
        "description": "Update existing calendar events",
        "parameters": ["event_id", "title", "start_time", "attendees"],
        "outputs": ["updated_event", "confirmation"]
    },
    "delete_calendar_event_tool": {
        "description": "Delete calendar events",
        "parameters": ["event_id"],
        "outputs": ["deletion_confirmation"]
    },
    "get_calendar_event_tool": {
        "description": "Get detailed event information",
        "parameters": ["event_id"],
        "outputs": ["event_details", "attendee_list", "meet_link"]
    }
}
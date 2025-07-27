from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
import uuid

class CalendarTool:
    """Calendar operations tool with Google Meet integration"""
    
    def __init__(self):
        self.service_name = 'calendar'
        self.version = 'v3'
    
    def create_event(self, google_client, title: str, start_time: Union[str, datetime], 
                    end_time: Union[str, datetime], description: Optional[str] = None,
                    attendees: Optional[List[str]] = None, location: Optional[str] = None,
                    timezone: str = 'UTC') -> Dict[str, Any]:
        """Create a calendar event"""
        try:
            service = google_client
            
            # Build event object
            event = self._build_event_object(
                title, start_time, end_time, description, attendees, location, timezone
            )
            
            # Create event
            result = service.events().insert(calendarId='primary', body=event).execute()
            
            return {
                'success': True,
                'data': {
                    'event_id': result['id'],
                    'event_link': result.get('htmlLink', ''),
                    'attendees': self._format_attendees_response(result.get('attendees', [])),
                    'event_details': self._format_event_details(result)
                },
                'error': None,
                'message': f"Event '{title}' created successfully"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to create event: {str(e)}"
            }
    
    def create_meet_event(self, google_client, title: str, start_time: Union[str, datetime],
                         end_time: Union[str, datetime], description: Optional[str] = None,
                         attendees: Optional[List[str]] = None, location: Optional[str] = None,
                         timezone: str = 'UTC') -> Dict[str, Any]:
        """Create a calendar event with Google Meet link"""
        try:
            service = google_client
            
            # Build event object with Meet conference
            event = self._build_event_object(
                title, start_time, end_time, description, attendees, location, timezone
            )
            
            # Add Google Meet conference data
            event['conferenceData'] = {
                'createRequest': {
                    'requestId': str(uuid.uuid4()),
                    'conferenceSolutionKey': {
                        'type': 'hangoutsMeet'
                    }
                }
            }
            
            # Create event with conference
            result = service.events().insert(
                calendarId='primary', 
                body=event,
                conferenceDataVersion=1
            ).execute()
            
            # Extract Meet link
            meet_link = self._extract_meet_link(result)
            
            return {
                'success': True,
                'data': {
                    'event_id': result['id'],
                    'meet_link': meet_link,
                    'event_link': result.get('htmlLink', ''),
                    'attendees': self._format_attendees_response(result.get('attendees', [])),
                    'event_details': self._format_event_details(result)
                },
                'error': None,
                'message': f"Event '{title}' created with Google Meet link"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to create Meet event: {str(e)}"
            }
    
    def list_events(self, google_client, start_date: Union[str, datetime],
                   end_date: Optional[Union[str, datetime]] = None,
                   max_results: int = 50, timezone: str = 'UTC') -> Dict[str, Any]:
        """List calendar events within date range"""
        try:
            service = google_client
            
            # Format dates
            time_min = self._format_datetime(start_date, timezone)
            time_max = None
            if end_date:
                time_max = self._format_datetime(end_date, timezone)
            else:
                # Default to end of day if no end_date provided
                if isinstance(start_date, datetime):
                    end_dt = start_date.replace(hour=23, minute=59, second=59)
                else:
                    end_dt = datetime.strptime(start_date, '%Y-%m-%d')
                    end_dt = end_dt.replace(hour=23, minute=59, second=59)
                time_max = self._format_datetime(end_dt, timezone)
            
            # Get events
            events_result = service.events().list(
                calendarId='primary',
                timeMin=time_min,
                timeMax=time_max,
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            formatted_events = []
            
            for event in events:
                formatted_event = self._format_event_details(event)
                # Check for Meet links
                meet_link = self._extract_meet_link(event)
                if meet_link:
                    formatted_event['meet_link'] = meet_link
                formatted_events.append(formatted_event)
            
            return {
                'success': True,
                'data': {
                    'events': formatted_events,
                    'total_count': len(formatted_events),
                    'date_range': {
                        'start': time_min,
                        'end': time_max
                    }
                },
                'error': None,
                'message': f"Found {len(formatted_events)} events"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to list events: {str(e)}"
            }
    
    def update_event(self, google_client, event_id: str, title: Optional[str] = None,
                    start_time: Optional[Union[str, datetime]] = None,
                    end_time: Optional[Union[str, datetime]] = None,
                    description: Optional[str] = None,
                    attendees: Optional[List[str]] = None,
                    location: Optional[str] = None,
                    add_meet: bool = False, timezone: str = 'UTC') -> Dict[str, Any]:
        """Update an existing calendar event"""
        try:
            service = google_client
            
            # Get existing event
            existing_event = service.events().get(calendarId='primary', eventId=event_id).execute()
            
            # Update fields
            if title:
                existing_event['summary'] = title
            if description:
                existing_event['description'] = description
            if location:
                existing_event['location'] = location
            
            if start_time:
                existing_event['start'] = self._format_datetime_for_event(start_time, timezone)
            if end_time:
                existing_event['end'] = self._format_datetime_for_event(end_time, timezone)
            
            if attendees:
                existing_event['attendees'] = [{'email': email} for email in attendees]
            
            # Add Meet link if requested and not already present
            if add_meet and 'conferenceData' not in existing_event:
                existing_event['conferenceData'] = {
                    'createRequest': {
                        'requestId': str(uuid.uuid4()),
                        'conferenceSolutionKey': {
                            'type': 'hangoutsMeet'
                        }
                    }
                }
            
            # Update event
            result = service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=existing_event,
                conferenceDataVersion=1 if add_meet else 0
            ).execute()
            
            meet_link = self._extract_meet_link(result)
            
            return {
                'success': True,
                'data': {
                    'event_id': result['id'],
                    'meet_link': meet_link,
                    'event_link': result.get('htmlLink', ''),
                    'attendees': self._format_attendees_response(result.get('attendees', [])),
                    'event_details': self._format_event_details(result)
                },
                'error': None,
                'message': f"Event updated successfully"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to update event: {str(e)}"
            }
    
    def delete_event(self, google_client, event_id: str) -> Dict[str, Any]:
        """Delete a calendar event"""
        try:
            service = google_client
            
            # Get event details before deletion for confirmation
            event = service.events().get(calendarId='primary', eventId=event_id).execute()
            event_title = event.get('summary', 'Untitled Event')
            
            # Delete event
            service.events().delete(calendarId='primary', eventId=event_id).execute()
            
            return {
                'success': True,
                'data': {
                    'deleted_event_id': event_id,
                    'deleted_event_title': event_title
                },
                'error': None,
                'message': f"Event '{event_title}' deleted successfully"
            }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to delete event: {str(e)}"
            }
    
    def get_meet_link_from_event(self, google_client, event_id: str) -> Dict[str, Any]:
        """Extract Google Meet link from existing event"""
        try:
            service = google_client
            
            # Get event
            event = service.events().get(calendarId='primary', eventId=event_id).execute()
            
            meet_link = self._extract_meet_link(event)
            event_title = event.get('summary', 'Untitled Event')
            
            if meet_link:
                return {
                    'success': True,
                    'data': {
                        'event_id': event_id,
                        'event_title': event_title,
                        'meet_link': meet_link,
                        'has_meet': True
                    },
                    'error': None,
                    'message': f"Meet link found for '{event_title}'"
                }
            else:
                return {
                    'success': True,
                    'data': {
                        'event_id': event_id,
                        'event_title': event_title,
                        'meet_link': None,
                        'has_meet': False
                    },
                    'error': None,
                    'message': f"No Meet link found for '{event_title}'"
                }
            
        except Exception as e:
            return {
                'success': False,
                'data': None,
                'error': str(e),
                'message': f"Failed to get Meet link: {str(e)}"
            }
    
    def _build_event_object(self, title: str, start_time: Union[str, datetime],
                           end_time: Union[str, datetime], description: Optional[str],
                           attendees: Optional[List[str]], location: Optional[str],
                           timezone: str) -> Dict[str, Any]:
        """Build event object for Google Calendar API"""
        event = {
            'summary': title,
            'start': self._format_datetime_for_event(start_time, timezone),
            'end': self._format_datetime_for_event(end_time, timezone),
        }
        
        if description:
            event['description'] = description
        
        if location:
            event['location'] = location
        
        if attendees:
            event['attendees'] = [{'email': email} for email in attendees]
        
        return event
    
    def _format_datetime_for_event(self, dt: Union[str, datetime], timezone: str) -> Dict[str, str]:
        """Format datetime for Google Calendar API"""
        if isinstance(dt, str):
            # Assume ISO format string
            return {
                'dateTime': dt,
                'timeZone': timezone
            }
        else:
            # datetime object
            return {
                'dateTime': dt.isoformat(),
                'timeZone': timezone
            }
    
    def _format_datetime(self, dt: Union[str, datetime], timezone: str) -> str:
        """Format datetime to ISO string"""
        if isinstance(dt, str):
            return dt
        else:
            return dt.isoformat() + 'Z'
    
    def _extract_meet_link(self, event: Dict[str, Any]) -> Optional[str]:
        """Extract Google Meet link from event"""
        conference_data = event.get('conferenceData', {})
        entry_points = conference_data.get('entryPoints', [])
        
        for entry_point in entry_points:
            if entry_point.get('entryPointType') == 'video':
                return entry_point.get('uri')
        
        # Also check hangoutLink (legacy)
        return event.get('hangoutLink')
    
    def _format_attendees_response(self, attendees: List[Dict[str, Any]]) -> List[Dict[str, str]]:
        """Format attendees for response"""
        formatted = []
        for attendee in attendees:
            formatted.append({
                'email': attendee.get('email', ''),
                'status': attendee.get('responseStatus', 'needsAction'),
                'name': attendee.get('displayName', '')
            })
        return formatted
    
    def _format_event_details(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """Format event details for consistent response"""
        start = event.get('start', {})
        end = event.get('end', {})
        
        return {
            'id': event.get('id', ''),
            'title': event.get('summary', ''),
            'description': event.get('description', ''),
            'location': event.get('location', ''),
            'start_time': start.get('dateTime', start.get('date', '')),
            'end_time': end.get('dateTime', end.get('date', '')),
            'timezone': start.get('timeZone', ''),
            'event_link': event.get('htmlLink', ''),
            'attendees': self._format_attendees_response(event.get('attendees', [])),
            'has_meet': bool(self._extract_meet_link(event)),
            'created': event.get('created', ''),
            'updated': event.get('updated', '')
        }
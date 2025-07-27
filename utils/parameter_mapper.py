import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Union, Optional

logger = logging.getLogger(__name__)

class ParameterMapper:
    """Production-ready parameter mapper for LLM→Tool parameter translation with Gmail date fixes"""
    
    def __init__(self):
        logger.info("🔧 ParameterMapper initialized")
    
    def map_gmail_params(self, llm_params: Dict[str, Any]) -> Dict[str, Any]:
        """Map LLM parameters to Gmail tool parameters"""
        
        logger.info(f"📧 Mapping Gmail parameters: {list(llm_params.keys())}")
        
        try:
            mapped_params = {}
            
            # Handle each parameter
            for key, value in llm_params.items():
                
                # Date-related parameter mapping
                if key == "query" and isinstance(value, str):
                    date_range = self._convert_query_to_date_range(value)
                    if date_range:
                        mapped_params["date_range"] = date_range
                        logger.info(f"📅 Converted query '{value}' → date_range {date_range}")
                    else:
                        # If not a date query, convert to keywords
                        mapped_params["keywords"] = value
                        logger.info(f"🔍 Converted query '{value}' → keywords")
                
                # Thread parameter mapping
                elif key == "thread_ids" and isinstance(value, list) and value:
                    mapped_params["thread_id"] = value[0]  # Take first thread
                    logger.info(f"🧵 Converted thread_ids {value} → thread_id '{value[0]}'")
                
                elif key == "thread_ids" and isinstance(value, str):
                    mapped_params["thread_id"] = value
                    logger.info(f"🧵 Converted thread_ids '{value}' → thread_id")
                
                # Search filters mapping
                elif key == "search_query":
                    mapped_params["keywords"] = value
                    logger.info(f"🔍 Converted search_query → keywords")
                
                elif key == "from_email":
                    mapped_params["sender"] = value
                    logger.info(f"👤 Converted from_email → sender")
                
                # Direct mappings (keep as-is)
                elif key in ["sender", "keywords", "has_attachment", "max_results", 
                            "include_attachments", "date_range", "thread_id"]:
                    mapped_params[key] = value
                    logger.info(f"✅ Direct mapping: {key}")
                
                # Unknown parameter - log warning but include
                else:
                    mapped_params[key] = value
                    logger.warning(f"⚠️ Unknown Gmail parameter '{key}', including as-is")
            
            logger.info(f"✅ Gmail parameters mapped: {list(mapped_params.keys())}")
            return mapped_params
            
        except Exception as e:
            logger.error(f"❌ Error mapping Gmail parameters: {str(e)}")
            return llm_params  # Return original on error
    
    def map_calendar_params(self, llm_params: Dict[str, Any]) -> Dict[str, Any]:
        """Map LLM parameters to Calendar tool parameters"""
        
        logger.info(f"📅 Mapping Calendar parameters: {list(llm_params.keys())}")
        
        try:
            mapped_params = {}
            
            for key, value in llm_params.items():
                
                # Date/time parameter mapping
                if key in ["date", "start_date"] and isinstance(value, str):
                    mapped_params["start_time"] = self._format_calendar_datetime(value)
                    logger.info(f"📅 Converted {key} → start_time")
                
                elif key in ["end_date"] and isinstance(value, str):
                    mapped_params["end_time"] = self._format_calendar_datetime(value)
                    logger.info(f"📅 Converted {key} → end_time")
                
                elif key == "meeting_time" and isinstance(value, str):
                    # Split into start and end time (assume 1 hour duration)
                    start_dt = self._format_calendar_datetime(value)
                    end_dt = self._add_hours_to_datetime(start_dt, 1)
                    mapped_params["start_time"] = start_dt
                    mapped_params["end_time"] = end_dt
                    logger.info(f"🕐 Converted meeting_time → start_time/end_time")
                
                # Attendee parameter mapping
                elif key in ["emails", "attendee_emails", "participants"]:
                    mapped_params["attendees"] = value if isinstance(value, list) else [value]
                    logger.info(f"👥 Converted {key} → attendees")
                
                # Event details mapping
                elif key in ["event_title", "meeting_title", "subject"]:
                    mapped_params["title"] = value
                    logger.info(f"📝 Converted {key} → title")
                
                elif key in ["event_description", "meeting_description", "details"]:
                    mapped_params["description"] = value
                    logger.info(f"📝 Converted {key} → description")
                
                elif key in ["meeting_location", "venue"]:
                    mapped_params["location"] = value
                    logger.info(f"📍 Converted {key} → location")
                
                # Direct mappings
                elif key in ["title", "description", "location", "attendees", "start_time", 
                            "end_time", "timezone", "event_id", "max_results"]:
                    mapped_params[key] = value
                    logger.info(f"✅ Direct mapping: {key}")
                
                else:
                    mapped_params[key] = value
                    logger.warning(f"⚠️ Unknown Calendar parameter '{key}', including as-is")
            
            logger.info(f"✅ Calendar parameters mapped: {list(mapped_params.keys())}")
            return mapped_params
            
        except Exception as e:
            logger.error(f"❌ Error mapping Calendar parameters: {str(e)}")
            return llm_params
    
    def map_drive_params(self, llm_params: Dict[str, Any]) -> Dict[str, Any]:
        """Map LLM parameters to Drive tool parameters"""
        
        logger.info(f"📁 Mapping Drive parameters: {list(llm_params.keys())}")
        
        try:
            mapped_params = {}
            
            for key, value in llm_params.items():
                
                # File search mapping
                if key in ["filename", "file_name", "search_term"]:
                    mapped_params["query"] = value
                    logger.info(f"🔍 Converted {key} → query")
                
                elif key in ["file_type", "type", "extension"]:
                    mapped_params["file_type"] = value
                    logger.info(f"📄 Converted {key} → file_type")
                
                # Sharing parameters
                elif key in ["emails", "share_emails", "recipients"]:
                    mapped_params["email_addresses"] = value if isinstance(value, list) else [value]
                    logger.info(f"📤 Converted {key} → email_addresses")
                
                elif key in ["access_level", "permission"]:
                    mapped_params["role"] = value
                    logger.info(f"🔐 Converted {key} → role")
                
                # File operations
                elif key in ["file_path", "path"]:
                    mapped_params["file_path"] = value
                    logger.info(f"📁 Converted {key} → file_path")
                
                elif key in ["folder", "parent_folder"]:
                    mapped_params["folder_id"] = value
                    logger.info(f"📂 Converted {key} → folder_id")
                
                # Direct mappings
                elif key in ["query", "file_type", "folder_id", "max_results", "file_id",
                            "email_addresses", "role", "make_public", "file_path", "filename"]:
                    mapped_params[key] = value
                    logger.info(f"✅ Direct mapping: {key}")
                
                else:
                    mapped_params[key] = value
                    logger.warning(f"⚠️ Unknown Drive parameter '{key}', including as-is")
            
            logger.info(f"✅ Drive parameters mapped: {list(mapped_params.keys())}")
            return mapped_params
            
        except Exception as e:
            logger.error(f"❌ Error mapping Drive parameters: {str(e)}")
            return llm_params
    
    def _convert_query_to_date_range(self, query: str) -> Optional[tuple]:
        """Convert date queries to actual date ranges with Gmail API format (YYYY/MM/DD)"""
        
        logger.info(f"📅 Converting query '{query}' to date range")
        
        try:
            query_lower = query.lower().strip()
            now = datetime.now()
            
            if query_lower in ["today"]:
                start_date = now.strftime("%Y/%m/%d")         # ✅ GMAIL FORMAT
                end_date = (now + timedelta(days=1)).strftime("%Y/%m/%d")  # ✅ EXCLUSIVE END
                logger.info(f"📅 Today: {start_date} to {end_date}")
                return (start_date, end_date)
            
            elif query_lower in ["yesterday"]:
                yesterday = now - timedelta(days=1)
                start_date = yesterday.strftime("%Y/%m/%d")   # ✅ GMAIL FORMAT  
                end_date = now.strftime("%Y/%m/%d")           # ✅ EXCLUSIVE END
                logger.info(f"📅 Yesterday: {start_date} to {end_date}")
                return (start_date, end_date)
            
            elif query_lower in ["tomorrow"]:
                tomorrow = now + timedelta(days=1)
                start_date = tomorrow.strftime("%Y/%m/%d")    # ✅ GMAIL FORMAT
                end_date = (tomorrow + timedelta(days=1)).strftime("%Y/%m/%d")  # ✅ EXCLUSIVE END
                logger.info(f"📅 Tomorrow: {start_date} to {end_date}")
                return (start_date, end_date)
            
            elif "this week" in query_lower:
                start = (now - timedelta(days=now.weekday())).strftime("%Y/%m/%d")     # ✅ GMAIL FORMAT
                end = (now + timedelta(days=6-now.weekday() + 1)).strftime("%Y/%m/%d") # ✅ EXCLUSIVE END
                logger.info(f"📅 This week: {start} to {end}")
                return (start, end)
            
            elif "last week" in query_lower:
                start = (now - timedelta(days=now.weekday() + 7)).strftime("%Y/%m/%d")     # ✅ GMAIL FORMAT
                end = (now - timedelta(days=now.weekday())).strftime("%Y/%m/%d")           # ✅ EXCLUSIVE END
                logger.info(f"📅 Last week: {start} to {end}")
                return (start, end)
            
            else:
                logger.info(f"📝 Query '{query}' is not a date query")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error converting query to date range: {str(e)}")
            return None
    
    def _format_calendar_datetime(self, date_str: str) -> str:
        """Format datetime for Calendar API"""
        
        try:
            # Try to parse various formats
            for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"]:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.isoformat() + 'Z'
                except ValueError:
                    continue
            
            # If no format matches, assume it's a date and add default time
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            dt = dt.replace(hour=9, minute=0)  # Default to 9 AM
            return dt.isoformat() + 'Z'
            
        except Exception as e:
            logger.error(f"❌ Error formatting datetime '{date_str}': {str(e)}")
            # Return current time as fallback
            return datetime.now().isoformat() + 'Z'
    
    def _add_hours_to_datetime(self, datetime_str: str, hours: int) -> str:
        """Add hours to a datetime string"""
        
        try:
            # Parse the datetime
            if datetime_str.endswith('Z'):
                dt = datetime.fromisoformat(datetime_str[:-1])
            else:
                dt = datetime.fromisoformat(datetime_str)
            
            # Add hours
            dt = dt + timedelta(hours=hours)
            return dt.isoformat() + 'Z'
            
        except Exception as e:
            logger.error(f"❌ Error adding hours to datetime: {str(e)}")
            return datetime_str
    
    def get_current_date_context(self) -> Dict[str, str]:
        """Get current date context for system prompts (keeps YYYY-MM-DD for LLM)"""
        
        logger.info("📅 Getting current date context")
        
        try:
            now = datetime.now()
            
            context = {
                "current_date": now.strftime("%Y-%m-%d"),        # ✅ LLM FORMAT
                "current_time": now.strftime("%H:%M:%S"),
                "current_datetime": now.isoformat(),
                "tomorrow": (now + timedelta(days=1)).strftime("%Y-%m-%d"),        # ✅ LLM FORMAT
                "yesterday": (now - timedelta(days=1)).strftime("%Y-%m-%d"),       # ✅ LLM FORMAT
                "day_of_week": now.strftime("%A"),
                "this_week_start": (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d"),
                "this_week_end": (now + timedelta(days=6-now.weekday())).strftime("%Y-%m-%d")
            }
            
            logger.info(f"✅ Date context generated for {context['current_date']}")
            return context
            
        except Exception as e:
            logger.error(f"❌ Error getting date context: {str(e)}")
            return {"current_date": "2025-07-28", "error": str(e)}
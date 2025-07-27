from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

class ToolType(Enum):
    GMAIL = "gmail_tool"
    CALENDAR = "calendar_tool"
    DRIVE = "drive_tool"

class ActionType(Enum):
    # Gmail actions
    SEND_EMAIL = "send_email"
    READ_RECENT_EMAILS = "read_recent_emails"
    SEARCH_EMAILS = "search_emails_by_filters"
    GET_EMAIL_THREADS = "get_email_threads"
    
    # Calendar actions
    CREATE_EVENT = "create_event"
    CREATE_MEET_EVENT = "create_meet_event"
    LIST_EVENTS = "list_events"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    GET_MEET_LINK = "get_meet_link_from_event"
    
    # Drive actions
    UPLOAD_FILE = "upload_file"
    SEARCH_FILES = "search_files"
    DOWNLOAD_FILE = "download_file"
    SHARE_FILE = "share_file"
    LIST_RECENT_FILES = "list_recent_files"

@dataclass
class ExecutionStep:
    step_index: int
    tool: ToolType
    action: ActionType
    description: str
    parameters: Dict[str, Any]
    dependencies: List[int]
    expected_outputs: List[str]

@dataclass
class ExecutionPlan:
    intent: str
    steps: List[ExecutionStep]
    estimated_duration: str
    requires_confirmation: bool
    
@dataclass
class StepResult:
    step_index: int
    tool: ToolType
    action: ActionType
    status: str  # "completed", "failed", "pending"
    raw_output: Dict[str, Any]
    extracted_data: Dict[str, Any]
    error_message: Optional[str] = None

@dataclass
class WorkflowState:
    plan: ExecutionPlan
    step_results: Dict[int, StepResult]
    shared_context: Dict[str, Any]
    current_step: int
    status: str  # "planning", "executing", "completed", "failed"
    user_id: str
    created_at: str
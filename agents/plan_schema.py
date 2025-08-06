from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
from enum import Enum
import operator

class ToolType(Enum):
    GMAIL = "gmail_tool"
    CALENDAR = "calendar_tool"
    DRIVE = "drive_tool"

class ActionType(Enum):
    # Gmail actions - Simplified
    SEND_EMAIL = "send_email"
    READ_EMAILS = "read_emails"
    SEARCH_EMAILS = "search_emails"
    GET_THREADS = "get_threads"
    
    # Calendar actions - Simplified
    CREATE_EVENT = "create_event"
    LIST_EVENTS = "list_events"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    GET_EVENT = "get_event"
    
    # Drive actions - Simplified
    UPLOAD_FILE = "upload_file"
    SEARCH_FILES = "search_files"
    DOWNLOAD_FILE = "download_file"
    SHARE_FILE = "share_file"
    LIST_FILES = "list_files"

class ExecutionStep(TypedDict):
    step_index: int
    tool: ToolType
    action: ActionType
    description: str
    parameters: Dict[str, Any]
    dependencies: List[int]
    expected_outputs: List[str]

class ExecutionPlan(TypedDict):
    intent: str
    steps: List[ExecutionStep]
    estimated_duration: str
    requires_confirmation: bool

class StepResult(TypedDict):
    step_index: int
    tool: ToolType
    action: ActionType
    status: str  # "completed", "failed", "pending"
    raw_output: Dict[str, Any]
    extracted_data: Dict[str, Any]
    error_message: Optional[str]

# Custom reducer functions for WorkflowState
def merge_step_results(existing: Dict[int, StepResult], new: Dict[int, StepResult]) -> Dict[int, StepResult]:
    """Merge step results without overwriting existing ones"""
    if not existing:
        return new
    if not new:
        return existing
    
    merged = existing.copy()
    merged.update(new)
    return merged

def merge_shared_context(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Intelligently merge shared context"""
    if not existing:
        return new
    if not new:
        return existing
    
    merged = existing.copy()
    
    # Special handling for specific keys
    for key, value in new.items():
        if key in merged:
            # If both are lists, extend instead of replace
            if isinstance(merged[key], list) and isinstance(value, list):
                merged[key] = merged[key] + value
            # If both are dicts, merge them
            elif isinstance(merged[key], dict) and isinstance(value, dict):
                merged[key] = {**merged[key], **value}
            else:
                # For other types, new value overwrites
                merged[key] = value
        else:
            merged[key] = value
    
    return merged

def add_execution_log(existing: List[str], new: List[str]) -> List[str]:
    """Add new log entries to existing log"""
    if not existing:
        return new
    if not new:
        return existing
    return existing + new

# ✅ FIXED: WorkflowState now uses TypedDict with proper reducers
class WorkflowState(TypedDict):
    plan: ExecutionPlan
    step_results: Annotated[Dict[int, StepResult], merge_step_results]
    shared_context: Annotated[Dict[str, Any], merge_shared_context]
    current_step: int
    status: str  # "planning", "executing", "completed", "failed"
    user_id: str
    created_at: str
    # New: Add execution log for better tracking
    execution_log: Annotated[List[str], add_execution_log]
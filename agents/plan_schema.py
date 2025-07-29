from typing import List, Dict, Any, Optional, Annotated
from typing_extensions import TypedDict
from dataclasses import dataclass
from enum import Enum
import operator

# Keep the existing enums - they're fine
class ToolType(Enum):
    GMAIL = "gmail_tool"
    CALENDAR = "calendar_tool"
    DRIVE = "drive_tool"

class ActionType(Enum):
    # Gmail actions
    SEND_EMAIL = "send_email"
    READ_EMAILS = "read_emails"
    SEARCH_EMAILS = "search_emails"
    GET_THREADS = "get_threads"
    
    # Calendar actions
    CREATE_EVENT = "create_event"
    LIST_EVENTS = "list_events"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    GET_EVENT = "get_event"
    
    # Drive actions
    UPLOAD_FILE = "upload_file"
    SEARCH_FILES = "search_files"
    DOWNLOAD_FILE = "download_file"
    SHARE_FILE = "share_file"
    LIST_FILES = "list_files"

# Keep dataclasses for plan structure - they're not state
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

# Custom reducers for state management
def merge_step_results(existing: Dict[int, StepResult], new: Dict[int, StepResult]) -> Dict[int, StepResult]:
    """Reducer to merge step results without overwriting"""
    if existing is None:
        existing = {}
    if new is None:
        return existing
    
    # Merge the dictionaries - new results update existing ones
    merged = existing.copy()
    merged.update(new)
    return merged

def merge_context(existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer to intelligently merge shared context"""
    if existing is None:
        existing = {}
    if new is None:
        return existing
    
    merged = existing.copy()
    
    # Handle special context keys that need list merging
    for key, value in new.items():
        if key in merged and isinstance(merged[key], list) and isinstance(value, list):
            # Merge lists (e.g., attendees, file_ids)
            merged[key] = list(set(merged[key] + value))  # Remove duplicates
        elif key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            # Merge nested dictionaries
            merged[key] = {**merged[key], **value}
        else:
            # Direct replacement for other types
            merged[key] = value
    
    return merged

def append_progress(existing: List[str], new: List[str]) -> List[str]:
    """Reducer to append progress messages"""
    if existing is None:
        existing = []
    if new is None:
        return existing
    return existing + new

# NEW: Proper LangGraph State using TypedDict with reducers
class WorkflowState(TypedDict):
    """
    LangGraph state with proper reducers for automatic state management.
    
    This replaces the old dataclass-based WorkflowState and follows
    LangGraph best practices for state handling.
    """
    # Core workflow data
    plan: ExecutionPlan
    user_id: str
    
    # Accumulating data with custom reducers
    step_results: Annotated[Dict[int, StepResult], merge_step_results]
    shared_context: Annotated[Dict[str, Any], merge_context]
    progress_messages: Annotated[List[str], append_progress]
    
    # Simple fields (direct replacement)
    current_step: int
    status: str  # "planning", "executing", "completed", "failed", "interrupted"
    created_at: str
    
    # Optional workflow control
    error_count: Annotated[int, operator.add]  # Track cumulative errors
    retry_count: Annotated[int, operator.add]  # Track retry attempts

# Helper functions for working with the new state
def create_initial_state(plan: ExecutionPlan, user_id: str) -> WorkflowState:
    """Create initial workflow state with proper defaults"""
    from datetime import datetime
    
    return WorkflowState(
        plan=plan,
        user_id=user_id,
        step_results={},
        shared_context={
            "user_id": user_id,
            "workflow_started": datetime.now().isoformat(),
            "discovered_contacts": [],
            "meeting_details": {},
            "file_references": []
        },
        progress_messages=[],
        current_step=1,
        status="executing",
        created_at=datetime.now().isoformat(),
        error_count=0,
        retry_count=0
    )

def update_step_completion(step_result: StepResult, extracted_data: Dict[str, Any] = None) -> Dict[str, Any]:
    """
    Create state update for step completion.
    Returns the update dict that LangGraph will merge using reducers.
    """
    if extracted_data is None:
        extracted_data = {}
    
    # Build the state update
    update = {
        "step_results": {step_result.step_index: step_result},
        "current_step": step_result.step_index + 1,
        "progress_messages": [f"✅ Step {step_result.step_index} completed: {step_result.tool.value}"]
    }
    
    # Add context updates if step succeeded
    if step_result.status == "completed":
        context_updates = {}
        
        # Add extracted data to shared context
        if "for_future_steps" in extracted_data:
            context_updates.update(extracted_data["for_future_steps"])
        
        # Add any context updates
        if "context_updates" in extracted_data:
            context_updates.update(extracted_data["context_updates"])
        
        if context_updates:
            update["shared_context"] = context_updates
    
    elif step_result.status == "failed":
        update["error_count"] = 1
        update["progress_messages"] = [f"❌ Step {step_result.step_index} failed: {step_result.error_message}"]
    
    return update

def update_workflow_status(status: str, message: str = None) -> Dict[str, Any]:
    """Create state update for workflow status changes"""
    update = {"status": status}
    
    if message:
        update["progress_messages"] = [message]
    
    return update

# Progress message helpers for the UI
def get_progress_summary(state: WorkflowState) -> Dict[str, Any]:
    """Get progress summary for UI display"""
    total_steps = len(state["plan"].steps)
    completed_steps = len([r for r in state["step_results"].values() if r.status == "completed"])
    failed_steps = len([r for r in state["step_results"].values() if r.status == "failed"])
    
    return {
        "status": state["status"],
        "progress_percent": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
        "current_step": state["current_step"],
        "total_steps": total_steps,
        "completed_steps": completed_steps,
        "failed_steps": failed_steps,
        "plan_intent": state["plan"].intent,
        "recent_messages": state["progress_messages"][-5:],  # Last 5 messages
        "error_count": state["error_count"],
        "created_at": state["created_at"]
    }
from typing import Dict, Any
from agents.plan_schema import StepResult, ToolType, ActionType
from tools.gmail_tool import GmailTool
from tools.calendar_tool import CalendarTool
from tools.drive_tool import DriveTool

class ExecutionNode:
    """Base class for tool execution nodes"""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        """Execute tool action and return result"""
        raise NotImplementedError

class GmailNode(ExecutionNode):
    """Gmail tool execution node"""
    
    def __init__(self, auth_manager):
        super().__init__(auth_manager)
        self.tool = GmailTool()
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        
        try:
            # Get authenticated client
            client = self.auth_manager.get_authenticated_client('gmail', 'v1', context['user_id'])
            if not client:
                raise Exception("Gmail authentication failed")
            
            # Prepare parameters
            params = self._prepare_parameters(action, context)
            
            # Execute action
            result = self._call_tool_method(action, client, params)
            
            return StepResult(
                step_index=step_index,
                tool=tool,
                action=action,
                status="completed" if result.get("success") else "failed",
                raw_output=result,
                extracted_data={},
                error_message=result.get("error") if not result.get("success") else None
            )
            
        except Exception as e:
            return StepResult(
                step_index=step_index,
                tool=tool,
                action=action,
                status="failed",
                raw_output={},
                extracted_data={},
                error_message=str(e)
            )
    
    def _prepare_parameters(self, action: ActionType, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for tool method call"""
        
        base_params = context.get("step_parameters", {})
        shared_context = context.get("shared_context", {})
        
        # Smart parameter resolution from context
        if action == ActionType.SEND_EMAIL:
            # If 'to' is not specified, try to get from shared context
            if "to" not in base_params and "meeting_attendees" in shared_context:
                base_params["to"] = shared_context["meeting_attendees"]
            
            # If subject/body reference meeting details
            if "meeting_details" in shared_context:
                meeting = shared_context["meeting_details"]
                if "{{meeting_title}}" in base_params.get("subject", ""):
                    base_params["subject"] = base_params["subject"].replace("{{meeting_title}}", meeting.get("title", "Meeting"))
                if "{{meeting_link}}" in base_params.get("body", ""):
                    base_params["body"] = base_params["body"].replace("{{meeting_link}}", shared_context.get("meeting_link", ""))
        
        return base_params
    
    def _call_tool_method(self, action: ActionType, client, params: Dict[str, Any]):
        """Call appropriate tool method"""
        
        if action == ActionType.SEND_EMAIL:
            return self.tool.send_email(client, **params)
        elif action == ActionType.READ_RECENT_EMAILS:
            return self.tool.read_recent_emails(client, **params)
        elif action == ActionType.SEARCH_EMAILS:
            return self.tool.search_emails_by_filters(client, **params)
        elif action == ActionType.GET_EMAIL_THREADS:
            return self.tool.get_email_threads(client, **params)
        else:
            raise ValueError(f"Unknown Gmail action: {action}")

class CalendarNode(ExecutionNode):
    """Calendar tool execution node"""
    
    def __init__(self, auth_manager):
        super().__init__(auth_manager)
        self.tool = CalendarTool()
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        
        try:
            # Get authenticated client
            client = self.auth_manager.get_authenticated_client('calendar', 'v3', context['user_id'])
            if not client:
                raise Exception("Calendar authentication failed")
            
            # Prepare parameters
            params = self._prepare_parameters(action, context)
            
            # Execute action
            result = self._call_tool_method(action, client, params)
            
            return StepResult(
                step_index=step_index,
                tool=tool,
                action=action,
                status="completed" if result.get("success") else "failed",
                raw_output=result,
                extracted_data={},
                error_message=result.get("error") if not result.get("success") else None
            )
            
        except Exception as e:
            return StepResult(
                step_index=step_index,
                tool=tool,
                action=action,
                status="failed",
                raw_output={},
                extracted_data={},
                error_message=str(e)
            )
    
    def _prepare_parameters(self, action: ActionType, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for calendar tool"""
        
        base_params = context.get("step_parameters", {})
        shared_context = context.get("shared_context", {})
        
        # Smart parameter resolution
        if action in [ActionType.CREATE_EVENT, ActionType.CREATE_MEET_EVENT]:
            # Use attendees from previous steps
            if "attendees" not in base_params and "meeting_attendees" in shared_context:
                base_params["attendees"] = shared_context["meeting_attendees"]
            
            # Use meeting details from context
            if "meeting_details" in shared_context:
                meeting = shared_context["meeting_details"]
                if "title" not in base_params:
                    base_params["title"] = meeting.get("title", "Meeting")
                if "description" not in base_params:
                    base_params["description"] = meeting.get("description", "")
        
        return base_params
    
    def _call_tool_method(self, action: ActionType, client, params: Dict[str, Any]):
        """Call appropriate calendar tool method"""
        
        if action == ActionType.CREATE_EVENT:
            return self.tool.create_event(client, **params)
        elif action == ActionType.CREATE_MEET_EVENT:
            return self.tool.create_meet_event(client, **params)
        elif action == ActionType.LIST_EVENTS:
            return self.tool.list_events(client, **params)
        elif action == ActionType.UPDATE_EVENT:
            return self.tool.update_event(client, **params)
        elif action == ActionType.DELETE_EVENT:
            return self.tool.delete_event(client, **params)
        elif action == ActionType.GET_MEET_LINK:
            return self.tool.get_meet_link_from_event(client, **params)
        else:
            raise ValueError(f"Unknown Calendar action: {action}")

class DriveNode(ExecutionNode):
    """Drive tool execution node"""
    
    def __init__(self, auth_manager):
        super().__init__(auth_manager)
        self.tool = DriveTool()
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        
        try:
            # Get authenticated client
            client = self.auth_manager.get_authenticated_client('drive', 'v3', context['user_id'])
            if not client:
                raise Exception("Drive authentication failed")
            
            # Prepare parameters
            params = self._prepare_parameters(action, context)
            
            # Execute action
            result = self._call_tool_method(action, client, params)
            
            return StepResult(
                step_index=step_index,
                tool=tool,
                action=action,
                status="completed" if result.get("success") else "failed",
                raw_output=result,
                extracted_data={},
                error_message=result.get("error") if not result.get("success") else None
            )
            
        except Exception as e:
            return StepResult(
                step_index=step_index,
                tool=tool,
                action=action,
                status="failed",
                raw_output={},
                extracted_data={},
                error_message=str(e)
            )
    
    def _prepare_parameters(self, action: ActionType, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for drive tool"""
        
        base_params = context.get("step_parameters", {})
        shared_context = context.get("shared_context", {})
        
        # Smart parameter resolution
        if action == ActionType.SHARE_FILE:
            # Use attendees from shared context for sharing
            if "email_addresses" not in base_params and "meeting_attendees" in shared_context:
                base_params["email_addresses"] = shared_context["meeting_attendees"]
        
        return base_params
    
    def _call_tool_method(self, action: ActionType, client, params: Dict[str, Any]):
        """Call appropriate drive tool method"""
        
        if action == ActionType.UPLOAD_FILE:
            return self.tool.upload_file(client, **params)
        elif action == ActionType.SEARCH_FILES:
            return self.tool.search_files(client, **params)
        elif action == ActionType.DOWNLOAD_FILE:
            return self.tool.download_file(client, **params)
        elif action == ActionType.SHARE_FILE:
            return self.tool.share_file(client, **params)
        elif action == ActionType.LIST_RECENT_FILES:
            return self.tool.list_recent_files(client, **params)
        else:
            raise ValueError(f"Unknown Drive action: {action}")

class NodeFactory:
    """Factory for creating execution nodes"""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self._nodes = {
            ToolType.GMAIL: GmailNode(auth_manager),
            ToolType.CALENDAR: CalendarNode(auth_manager),
            ToolType.DRIVE: DriveNode(auth_manager)
        }
    
    def get_node(self, tool_type: ToolType) -> ExecutionNode:
        """Get execution node for tool type"""
        return self._nodes[tool_type]
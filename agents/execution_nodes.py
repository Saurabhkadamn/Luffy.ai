import logging
import traceback
from typing import Dict, Any
from agents.plan_schema import StepResult, ToolType, ActionType
from tools.gmail_tool import GmailTool
from tools.calendar_tool import CalendarTool
from tools.drive_tool import DriveTool
from utils.parameter_mapper import ParameterMapper

# Configure logging
logger = logging.getLogger(__name__)

class ExecutionNode:
    """Base class for tool execution nodes with parameter mapping"""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.parameter_mapper = ParameterMapper()
        logger.info(f"🔧 Initialized {self.__class__.__name__} with ParameterMapper")
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        """Execute tool action and return result as TypedDict"""
        raise NotImplementedError

class GmailNode(ExecutionNode):
    """Gmail tool execution node with enhanced parameter mapping"""
    
    def __init__(self, auth_manager):
        super().__init__(auth_manager)
        logger.info("📧 Creating GmailTool instance")
        self.tool = GmailTool()
        logger.info("✅ GmailNode initialized successfully")
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        
        logger.info(f"📧 Executing Gmail step {step_index}: {action.value}")
        
        try:
            # Get authenticated client
            logger.info(f"🔐 Getting authenticated Gmail client for user: {context.get('user_id', 'unknown')}")
            client = self.auth_manager.get_authenticated_client('gmail', 'v1', context['user_id'])
            
            if not client:
                logger.error("❌ Gmail authentication failed - no client returned")
                raise Exception("Gmail authentication failed")
            
            logger.info("✅ Gmail client authenticated successfully")
            
            # Prepare and map parameters with enhanced error handling
            logger.info("⚙️ Preparing and mapping parameters for Gmail action")
            params = self._prepare_parameters(action, context)
            logger.info(f"✅ Parameters prepared and mapped: {list(params.keys())}")
            
            # Execute action with parameter validation
            logger.info(f"🚀 Executing Gmail action: {action.value}")
            result = self._call_tool_method(action, client, params)
            logger.info(f"✅ Gmail action completed: {result.get('success', False)}")
            
            if result.get('success'):
                logger.info("✅ Gmail step completed successfully")
                if 'data' in result:
                    logger.info(f"📊 Result data keys: {list(result['data'].keys()) if isinstance(result['data'], dict) else 'non-dict data'}")
            else:
                logger.error(f"❌ Gmail step failed: {result.get('error', 'Unknown error')}")
            
            # ✅ FIXED: Return StepResult as TypedDict
            return {
                "step_index": step_index,
                "tool": tool,
                "action": action,
                "status": "completed" if result.get("success") else "failed",
                "raw_output": result,
                "extracted_data": {},
                "error_message": result.get("error") if not result.get("success") else None
            }
            
        except Exception as e:
            logger.error(f"❌ Exception in Gmail step {step_index}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # ✅ FIXED: Return failed StepResult as TypedDict
            return {
                "step_index": step_index,
                "tool": tool,
                "action": action,
                "status": "failed",
                "raw_output": {},
                "extracted_data": {},
                "error_message": str(e)
            }
    
    def _prepare_parameters(self, action: ActionType, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for tool method call with enhanced parameter mapping"""
        
        logger.info(f"⚙️ Preparing Gmail parameters for action: {action.value}")
        
        try:
            base_params = context.get("step_parameters", {})
            shared_context = context.get("shared_context", {})
            
            logger.info(f"📋 Base parameters before mapping: {list(base_params.keys())}")
            logger.info(f"📊 Shared context keys: {list(shared_context.keys())}")
            
            # Apply parameter mapping first
            logger.info("🔄 Applying parameter mapping")
            mapped_params = self.parameter_mapper.map_gmail_params(base_params)
            logger.info(f"✅ Parameters after mapping: {list(mapped_params.keys())}")
            
            # ✅ FIX: Validate parameters for specific actions
            validated_params = self._validate_action_parameters(action, mapped_params)
            logger.info(f"✅ Parameters after validation: {list(validated_params.keys())}")
            
            # Smart parameter resolution from context
            if action == ActionType.SEND_EMAIL:
                logger.info("📧 Processing SEND_EMAIL parameters")
                
                # If 'to' is not specified, try to get from shared context
                if "to" not in validated_params and "meeting_attendees" in shared_context:
                    validated_params["to"] = shared_context["meeting_attendees"]
                    logger.info(f"✅ Added recipients from shared context: {len(validated_params['to']) if isinstance(validated_params['to'], list) else 1}")
                
                # If subject/body reference meeting details
                if "meeting_details" in shared_context:
                    meeting = shared_context["meeting_details"]
                    logger.info("🔄 Processing meeting details templates")
                    
                    if "{{meeting_title}}" in validated_params.get("subject", ""):
                        old_subject = validated_params["subject"]
                        validated_params["subject"] = validated_params["subject"].replace("{{meeting_title}}", meeting.get("title", "Meeting"))
                        logger.info(f"📝 Updated subject template: {old_subject} -> {validated_params['subject']}")
                        
                    if "{{meeting_link}}" in validated_params.get("body", ""):
                        meeting_link = shared_context.get("meeting_link", "")
                        old_body = validated_params["body"]
                        validated_params["body"] = validated_params["body"].replace("{{meeting_link}}", meeting_link)
                        logger.info(f"🔗 Updated body with meeting link: {len(meeting_link)} chars")
            
            logger.info(f"✅ Gmail parameters fully prepared: {list(validated_params.keys())}")
            return validated_params
            
        except Exception as e:
            logger.error(f"❌ Error preparing Gmail parameters: {str(e)}")
            logger.error(traceback.format_exc())
            return context.get("step_parameters", {})
    
    def _validate_action_parameters(self, action: ActionType, params: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters for specific Gmail actions"""
        
        logger.info(f"🔍 Validating parameters for action: {action.value}")
        
        try:
            validated_params = params.copy()
            
            # Define valid parameters for each action
            valid_params = {
                ActionType.SEND_EMAIL: ['to', 'subject', 'body', 'cc', 'bcc', 'attachments'],
                ActionType.READ_EMAILS: ['max_results', 'query', 'include_attachments'],
                ActionType.SEARCH_EMAILS: ['sender', 'date_range', 'keywords', 'has_attachment', 'include_attachments', 'max_results'],
                ActionType.GET_THREADS: ['thread_id', 'query', 'include_attachments']
            }
            
            if action in valid_params:
                allowed_params = valid_params[action]
                
                # Remove invalid parameters
                invalid_params = []
                for param_key in list(validated_params.keys()):
                    if param_key not in allowed_params:
                        invalid_params.append(param_key)
                        validated_params.pop(param_key)
                
                if invalid_params:
                    logger.warning(f"⚠️ Removed invalid parameters for {action.value}: {invalid_params}")
                
                logger.info(f"✅ Validation complete for {action.value}: {list(validated_params.keys())}")
            else:
                logger.warning(f"⚠️ No validation rules for action: {action.value}")
            
            return validated_params
            
        except Exception as e:
            logger.error(f"❌ Error validating parameters: {str(e)}")
            return params
    
    def _call_tool_method(self, action: ActionType, client, params: Dict[str, Any]):
        """Call appropriate tool method with enhanced error handling"""
        
        logger.info(f"🔧 Calling Gmail tool method for action: {action.value}")
        logger.info(f"📋 Final parameters: {list(params.keys())}")
        
        try:
            if action == ActionType.SEND_EMAIL:
                logger.info("📧 Calling send_email method")
                result = self.tool.send_email(client, **params)
            elif action == ActionType.READ_EMAILS:
                logger.info("📬 Calling read_recent_emails method")
                result = self.tool.read_recent_emails(client, **params)
            elif action == ActionType.SEARCH_EMAILS:
                logger.info("🔍 Calling search_emails_by_filters method")
                result = self.tool.search_emails_by_filters(client, **params)
            elif action == ActionType.GET_THREADS:
                logger.info("🧵 Calling get_email_threads method")
                result = self.tool.get_email_threads(client, **params)
            else:
                logger.error(f"❌ Unknown Gmail action: {action}")
                raise ValueError(f"Unknown Gmail action: {action}")
            
            logger.info(f"✅ Gmail tool method completed: {action.value}")
            return result
            
        except TypeError as e:
            if "unexpected keyword argument" in str(e):
                logger.error(f"❌ Parameter mismatch for {action.value}: {str(e)}")
                logger.error(f"📋 Attempted parameters: {list(params.keys())}")
                
                # Try to call with minimal required parameters
                logger.info("🔄 Attempting fallback with minimal parameters")
                try:
                    if action == ActionType.READ_EMAILS:
                        # Only use supported parameters
                        minimal_params = {k: v for k, v in params.items() if k in ['max_results', 'query', 'include_attachments']}
                        logger.info(f"🔄 Fallback parameters: {list(minimal_params.keys())}")
                        result = self.tool.read_recent_emails(client, **minimal_params)
                        logger.info("✅ Fallback successful")
                        return result
                    else:
                        raise e
                except Exception as fallback_error:
                    logger.error(f"❌ Fallback also failed: {str(fallback_error)}")
                    raise e
            else:
                raise e
        except Exception as e:
            logger.error(f"❌ Error calling Gmail tool method: {str(e)}")
            logger.error(traceback.format_exc())
            raise

class CalendarNode(ExecutionNode):
    """Calendar tool execution node with parameter mapping"""
    
    def __init__(self, auth_manager):
        super().__init__(auth_manager)
        logger.info("📅 Creating CalendarTool instance")
        self.tool = CalendarTool()
        logger.info("✅ CalendarNode initialized successfully")
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        
        logger.info(f"📅 Executing Calendar step {step_index}: {action.value}")
        
        try:
            # Get authenticated client
            logger.info(f"🔐 Getting authenticated Calendar client for user: {context.get('user_id', 'unknown')}")
            client = self.auth_manager.get_authenticated_client('calendar', 'v3', context['user_id'])
            
            if not client:
                logger.error("❌ Calendar authentication failed - no client returned")
                raise Exception("Calendar authentication failed")
            
            logger.info("✅ Calendar client authenticated successfully")
            
            # Prepare and map parameters
            logger.info("⚙️ Preparing and mapping parameters for Calendar action")
            params = self._prepare_parameters(action, context)
            logger.info(f"✅ Parameters prepared and mapped: {list(params.keys())}")
            
            # Execute action
            logger.info(f"🚀 Executing Calendar action: {action.value}")
            result = self._call_tool_method(action, client, params)
            logger.info(f"✅ Calendar action completed: {result.get('success', False)}")
            
            if result.get('success'):
                logger.info("✅ Calendar step completed successfully")
                if 'data' in result:
                    logger.info(f"📊 Result data keys: {list(result['data'].keys()) if isinstance(result['data'], dict) else 'non-dict data'}")
            else:
                logger.error(f"❌ Calendar step failed: {result.get('error', 'Unknown error')}")
            
            # ✅ FIXED: Return StepResult as TypedDict
            return {
                "step_index": step_index,
                "tool": tool,
                "action": action,
                "status": "completed" if result.get("success") else "failed",
                "raw_output": result,
                "extracted_data": {},
                "error_message": result.get("error") if not result.get("success") else None
            }
            
        except Exception as e:
            logger.error(f"❌ Exception in Calendar step {step_index}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # ✅ FIXED: Return failed StepResult as TypedDict
            return {
                "step_index": step_index,
                "tool": tool,
                "action": action,
                "status": "failed",
                "raw_output": {},
                "extracted_data": {},
                "error_message": str(e)
            }
    
    def _prepare_parameters(self, action: ActionType, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for calendar tool with parameter mapping"""
        
        logger.info(f"⚙️ Preparing Calendar parameters for action: {action.value}")
        
        try:
            base_params = context.get("step_parameters", {})
            shared_context = context.get("shared_context", {})
            
            logger.info(f"📋 Base parameters before mapping: {list(base_params.keys())}")
            logger.info(f"📊 Shared context keys: {list(shared_context.keys())}")
            
            # Apply parameter mapping first
            logger.info("🔄 Applying parameter mapping")
            mapped_params = self.parameter_mapper.map_calendar_params(base_params)
            logger.info(f"✅ Parameters after mapping: {list(mapped_params.keys())}")
            
            # Smart parameter resolution
            if action == ActionType.CREATE_EVENT:
                logger.info(f"📅 Processing {action.value} parameters")
                
                # Use attendees from previous steps
                if "attendees" not in mapped_params and "meeting_attendees" in shared_context:
                    mapped_params["attendees"] = shared_context["meeting_attendees"]
                    logger.info(f"✅ Added attendees from shared context: {len(mapped_params['attendees']) if isinstance(mapped_params['attendees'], list) else 1}")
                
                # Use meeting details from context
                if "meeting_details" in shared_context:
                    meeting = shared_context["meeting_details"]
                    logger.info("🔄 Processing meeting details")
                    
                    if "title" not in mapped_params:
                        mapped_params["title"] = meeting.get("title", "Meeting")
                        logger.info(f"📝 Added title from context: {mapped_params['title']}")
                        
                    if "description" not in mapped_params:
                        mapped_params["description"] = meeting.get("description", "")
                        logger.info(f"📝 Added description from context: {len(mapped_params['description'])} chars")
                
                # Handle include_meet parameter for Google Meet integration
                if mapped_params.get("include_meet", False):
                    # This will be handled by the calendar tool to decide between create_event or create_meet_event
                    logger.info("🎥 Google Meet requested for event")
            
            logger.info(f"✅ Calendar parameters fully prepared: {list(mapped_params.keys())}")
            return mapped_params
            
        except Exception as e:
            logger.error(f"❌ Error preparing Calendar parameters: {str(e)}")
            logger.error(traceback.format_exc())
            return context.get("step_parameters", {})
    
    def _call_tool_method(self, action: ActionType, client, params: Dict[str, Any]):
        """Call appropriate calendar tool method with logging"""
        
        logger.info(f"🔧 Calling Calendar tool method for action: {action.value}")
        logger.info(f"📋 Final parameters: {list(params.keys())}")
        
        try:
            if action == ActionType.CREATE_EVENT:
                logger.info("📅 Calling create_event method")
                # Check if Google Meet is requested
                if params.get("include_meet", False):
                    # Remove include_meet from params before calling tool
                    params_copy = params.copy()
                    params_copy.pop("include_meet", None)
                    logger.info("🎥 Calling create_meet_event method")
                    result = self.tool.create_meet_event(client, **params_copy)
                else:
                    result = self.tool.create_event(client, **params)
            elif action == ActionType.LIST_EVENTS:
                logger.info("📋 Calling list_events method")
                result = self.tool.list_events(client, **params)
            elif action == ActionType.UPDATE_EVENT:
                logger.info("✏️ Calling update_event method")
                result = self.tool.update_event(client, **params)
            elif action == ActionType.DELETE_EVENT:
                logger.info("🗑️ Calling delete_event method")
                result = self.tool.delete_event(client, **params)
            elif action == ActionType.GET_EVENT:
                logger.info("🔗 Calling get_meet_link_from_event method")
                result = self.tool.get_meet_link_from_event(client, **params)
            else:
                logger.error(f"❌ Unknown Calendar action: {action}")
                raise ValueError(f"Unknown Calendar action: {action}")
            
            logger.info(f"✅ Calendar tool method completed: {action.value}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error calling Calendar tool method: {str(e)}")
            logger.error(traceback.format_exc())
            raise

class DriveNode(ExecutionNode):
    """Drive tool execution node with parameter mapping"""
    
    def __init__(self, auth_manager):
        super().__init__(auth_manager)
        logger.info("📁 Creating DriveTool instance")
        self.tool = DriveTool()
        logger.info("✅ DriveNode initialized successfully")
    
    def execute(self, step_index: int, tool: ToolType, action: ActionType, 
                context: Dict[str, Any]) -> StepResult:
        
        logger.info(f"📁 Executing Drive step {step_index}: {action.value}")
        
        try:
            # Get authenticated client
            logger.info(f"🔐 Getting authenticated Drive client for user: {context.get('user_id', 'unknown')}")
            client = self.auth_manager.get_authenticated_client('drive', 'v3', context['user_id'])
            
            if not client:
                logger.error("❌ Drive authentication failed - no client returned")
                raise Exception("Drive authentication failed")
            
            logger.info("✅ Drive client authenticated successfully")
            
            # Prepare and map parameters
            logger.info("⚙️ Preparing and mapping parameters for Drive action")
            params = self._prepare_parameters(action, context)
            logger.info(f"✅ Parameters prepared and mapped: {list(params.keys())}")
            
            # Execute action
            logger.info(f"🚀 Executing Drive action: {action.value}")
            result = self._call_tool_method(action, client, params)
            logger.info(f"✅ Drive action completed: {result.get('success', False)}")
            
            if result.get('success'):
                logger.info("✅ Drive step completed successfully")
                if 'data' in result:
                    logger.info(f"📊 Result data keys: {list(result['data'].keys()) if isinstance(result['data'], dict) else 'non-dict data'}")
            else:
                logger.error(f"❌ Drive step failed: {result.get('error', 'Unknown error')}")
            
            # ✅ FIXED: Return StepResult as TypedDict
            return {
                "step_index": step_index,
                "tool": tool,
                "action": action,
                "status": "completed" if result.get("success") else "failed",
                "raw_output": result,
                "extracted_data": {},
                "error_message": result.get("error") if not result.get("success") else None
            }
            
        except Exception as e:
            logger.error(f"❌ Exception in Drive step {step_index}: {str(e)}")
            logger.error(traceback.format_exc())
            
            # ✅ FIXED: Return failed StepResult as TypedDict
            return {
                "step_index": step_index,
                "tool": tool,
                "action": action,
                "status": "failed",
                "raw_output": {},
                "extracted_data": {},
                "error_message": str(e)
            }
    
    def _prepare_parameters(self, action: ActionType, context: Dict[str, Any]) -> Dict[str, Any]:
        """Prepare parameters for drive tool with parameter mapping"""
        
        logger.info(f"⚙️ Preparing Drive parameters for action: {action.value}")
        
        try:
            base_params = context.get("step_parameters", {})
            shared_context = context.get("shared_context", {})
            
            logger.info(f"📋 Base parameters before mapping: {list(base_params.keys())}")
            logger.info(f"📊 Shared context keys: {list(shared_context.keys())}")
            
            # Apply parameter mapping first
            logger.info("🔄 Applying parameter mapping")
            mapped_params = self.parameter_mapper.map_drive_params(base_params)
            logger.info(f"✅ Parameters after mapping: {list(mapped_params.keys())}")
            
            # Smart parameter resolution
            if action == ActionType.SHARE_FILE:
                logger.info("📁 Processing SHARE_FILE parameters")
                
                # Use attendees from shared context for sharing
                if "email_addresses" not in mapped_params and "meeting_attendees" in shared_context:
                    mapped_params["email_addresses"] = shared_context["meeting_attendees"]
                    logger.info(f"✅ Added share recipients from shared context: {len(mapped_params['email_addresses']) if isinstance(mapped_params['email_addresses'], list) else 1}")
            
            elif action == ActionType.LIST_FILES:
                logger.info("📁 Processing LIST_FILES parameters")
                
                # Handle recent parameter for backwards compatibility
                if mapped_params.get("recent", True):
                    # This will be used to determine sorting and filtering in the tool
                    logger.info("📅 Recent files requested")
            
            logger.info(f"✅ Drive parameters fully prepared: {list(mapped_params.keys())}")
            return mapped_params
            
        except Exception as e:
            logger.error(f"❌ Error preparing Drive parameters: {str(e)}")
            logger.error(traceback.format_exc())
            return context.get("step_parameters", {})
    
    def _call_tool_method(self, action: ActionType, client, params: Dict[str, Any]):
        """Call appropriate drive tool method with logging"""
        
        logger.info(f"🔧 Calling Drive tool method for action: {action.value}")
        logger.info(f"📋 Final parameters: {list(params.keys())}")
        
        try:
            if action == ActionType.UPLOAD_FILE:
                logger.info("📤 Calling upload_file method")
                result = self.tool.upload_file(client, **params)
            elif action == ActionType.SEARCH_FILES:
                logger.info("🔍 Calling search_files method")
                result = self.tool.search_files(client, **params)
            elif action == ActionType.DOWNLOAD_FILE:
                logger.info("📥 Calling download_file method")
                result = self.tool.download_file(client, **params)
            elif action == ActionType.SHARE_FILE:
                logger.info("🔗 Calling share_file method")
                result = self.tool.share_file(client, **params)
            elif action == ActionType.LIST_FILES:
                logger.info("📋 Calling list_recent_files method")
                result = self.tool.list_recent_files(client, **params)
            else:
                logger.error(f"❌ Unknown Drive action: {action}")
                raise ValueError(f"Unknown Drive action: {action}")
            
            logger.info(f"✅ Drive tool method completed: {action.value}")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error calling Drive tool method: {str(e)}")
            logger.error(traceback.format_exc())
            raise

class NodeFactory:
    """Factory for creating execution nodes with parameter mapping"""
    
    def __init__(self, auth_manager):
        logger.info("🏭 Initializing NodeFactory with parameter mapping")
        
        try:
            self.auth_manager = auth_manager
            logger.info("🔧 Creating execution nodes with parameter mapping")
            
            self._nodes = {
                ToolType.GMAIL: GmailNode(auth_manager),
                ToolType.CALENDAR: CalendarNode(auth_manager),
                ToolType.DRIVE: DriveNode(auth_manager)
            }
            
            logger.info(f"✅ NodeFactory initialized with {len(self._nodes)} nodes: {list(self._nodes.keys())}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize NodeFactory: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def get_node(self, tool_type: ToolType) -> ExecutionNode:
        """Get execution node for tool type with logging"""
        
        logger.info(f"🔧 Getting execution node for tool: {tool_type.value}")
        
        try:
            node = self._nodes[tool_type]
            logger.info(f"✅ Node retrieved: {type(node).__name__}")
            return node
            
        except KeyError:
            logger.error(f"❌ Unknown tool type: {tool_type}")
            raise ValueError(f"Unknown tool type: {tool_type}")
        except Exception as e:
            logger.error(f"❌ Error getting node: {str(e)}")
            logger.error(traceback.format_exc())
            raise
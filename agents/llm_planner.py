import json
import logging
import traceback
from typing import Dict, Any, List
from langchain.schema import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from agents.plan_schema import ExecutionPlan, ExecutionStep, ToolType, ActionType
from config import settings

# Configure logging
logger = logging.getLogger(__name__)

class StreamlinedLLMPlanner:
    """
    FIXED: LLM planner with parameter schemas aligned to tool inputs.
    
    CHANGES:
    - Prompts now generate EXACT parameter names that tools expect
    - No more parameter mapping needed
    - Clean alignment between LLM output and Pydantic tool schemas
    """
    
    def __init__(self):
        logger.info("🤖 Initializing StreamlinedLLMPlanner with aligned schemas")
        
        try:
            # Create LLM instance with optimized config
            logger.info("🔧 Creating ChatNVIDIA instance for planning")
            logger.info(f"🔑 Using API key: {'*' * 20}{settings.NVIDIA_API_KEY[-4:] if settings.NVIDIA_API_KEY else 'MISSING'}")
            
            self.llm = ChatNVIDIA(
                model="moonshotai/kimi-k2-instruct",
                api_key=settings.NVIDIA_API_KEY,
                temperature=0.3,  # Lower temperature for more consistent planning
                top_p=0.9,
                max_tokens=4096,
            )
            logger.info("✅ ChatNVIDIA instance created successfully")
            
            logger.info("📝 Building ALIGNED system prompt")
            self.system_prompt = self._build_aligned_system_prompt()
            logger.info(f"✅ System prompt built (length: {len(self.system_prompt)} chars)")
            
            logger.info("✅ StreamlinedLLMPlanner initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize StreamlinedLLMPlanner: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def create_plan(self, user_request: str, user_context: Dict[str, Any] = None) -> ExecutionPlan:
        """
        Generate execution plan from user request with ALIGNED parameters.
        
        Now generates parameters that exactly match tool Pydantic schemas.
        """
        logger.info(f"📋 Creating plan for request: {user_request}")
        logger.info(f"📊 User context: {user_context}")
        
        try:
            logger.info("✍️ Building planning prompt")
            user_prompt = self._build_planning_prompt(user_request, user_context)
            logger.info(f"✅ Planning prompt built (length: {len(user_prompt)} chars)")
            
            logger.info("💬 Preparing LangChain messages")
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_prompt)
            ]
            logger.info("✅ Messages prepared for LLM")
            
            logger.info("🚀 Invoking LLM for plan generation")
            response = self.llm.invoke(messages)
            logger.info("✅ LLM response received")
            
            # Extract content from LangChain response
            response_content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"📄 Response content length: {len(response_content)} chars")
            logger.info(f"📄 Response preview: {response_content[:200]}...")
            
            # Clean and parse JSON response
            logger.info("🧹 Cleaning and parsing JSON response")
            cleaned_content = self._clean_json_response(response_content)
            plan_data = json.loads(cleaned_content)
            logger.info("✅ JSON parsed successfully")
            logger.info(f"📊 Plan data keys: {list(plan_data.keys())}")
            
            logger.info("🏗️ Converting to ExecutionPlan object")
            execution_plan = self._parse_plan(plan_data)
            logger.info(f"✅ ExecutionPlan created: {execution_plan.intent}")
            logger.info(f"📋 Plan has {len(execution_plan.steps)} steps")
            
            # Validate plan
            validation_issues = self._validate_plan(execution_plan)
            if validation_issues:
                logger.warning(f"⚠️ Plan validation issues: {validation_issues}")
                # Continue anyway - basic validation only
            
            return execution_plan
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing error: {str(e)}")
            logger.error(f"📄 Raw response: {response_content}")
            
            # Try to extract JSON from response
            try:
                logger.info("🔍 Attempting to extract JSON from response")
                json_str = self._extract_json_from_text(response_content)
                
                if json_str:
                    logger.info("🔍 Extracted JSON successfully")
                    plan_data = json.loads(json_str)
                    execution_plan = self._parse_plan(plan_data)
                    logger.info(f"✅ ExecutionPlan created from extracted JSON: {execution_plan.intent}")
                    return execution_plan
                else:
                    logger.error("❌ No valid JSON found in response")
                    return self._create_fallback_plan(user_request, f"JSON parsing error: {str(e)}")
                    
            except Exception as extract_error:
                logger.error(f"❌ JSON extraction also failed: {str(extract_error)}")
                return self._create_fallback_plan(user_request, f"JSON parsing error: {str(e)}")
                
        except Exception as e:
            logger.error(f"❌ General error in create_plan: {str(e)}")
            logger.error(traceback.format_exc())
            return self._create_fallback_plan(user_request, str(e))
    
    def _build_aligned_system_prompt(self) -> str:
        """
        FIXED: Build system prompt with EXACT parameter names that match tool schemas.
        
        This eliminates the need for parameter mapping by ensuring LLM output
        exactly matches what tools expect.
        """
        logger.info("📝 Building ALIGNED system prompt with exact tool schemas")
        
        prompt = """
You are an AI workflow planner for a Google productivity assistant with Gmail, Calendar, and Drive integration.

CRITICAL: Respond with ONLY valid JSON. No explanations, no markdown, no additional text.

IMPORTANT: Use EXACT parameter names that match the tool schemas below. This is critical for execution.

AVAILABLE TOOLS WITH EXACT SCHEMAS:

1. GMAIL TOOLS:
   - send_email_tool:
     Parameters: to, subject, body, cc (optional), bcc (optional), user_id
   - search_emails_tool:
     Parameters: sender (optional), date_range (optional), keywords (optional), has_attachment (optional), max_results, user_id
   - read_recent_emails_tool:
     Parameters: max_results, query (optional), include_attachments, user_id
   - get_email_threads_tool:
     Parameters: thread_id (optional), query (optional), include_attachments, user_id

2. CALENDAR TOOLS:
   - create_calendar_event_tool:
     Parameters: title, start_time, end_time, description (optional), attendees (optional), location (optional), include_meet, timezone, user_id
   - list_calendar_events_tool:
     Parameters: start_date, end_date (optional), max_results, timezone, user_id
   - update_calendar_event_tool:
     Parameters: event_id, title (optional), start_time (optional), end_time (optional), description (optional), attendees (optional), location (optional), add_meet, timezone, user_id
   - delete_calendar_event_tool:
     Parameters: event_id, user_id
   - get_calendar_event_tool:
     Parameters: event_id, user_id

3. DRIVE TOOLS:
   - upload_file_to_drive_tool:
     Parameters: file_path (optional), filename (optional), folder_id (optional), description (optional), make_public, user_id
   - search_files_in_drive_tool:
     Parameters: query (optional), file_type (optional), folder_id (optional), max_results, include_trashed, user_id
   - share_drive_file_tool:
     Parameters: file_id, email_addresses (optional), role, make_public, send_notification, user_id
   - download_drive_file_tool:
     Parameters: file_id, download_path (optional), user_id
   - list_recent_drive_files_tool:
     Parameters: max_results, file_types (optional), recent, user_id
   - get_drive_file_info_tool:
     Parameters: file_id, user_id

PARAMETER GUIDELINES (USE EXACT NAMES):
- Use actual dates from context (never "today", "tomorrow") 
- For Gmail date_range: ["YYYY/MM/DD", "YYYY/MM/DD"] format (Gmail API format)
- For Calendar times: "YYYY-MM-DDTHH:MM:SSZ" format (ISO format)
- For shared data: use template variables like "{{attendee_emails}}" or "{{meeting_link}}"
- For user_id: always use "{{user_id}}" template variable
- Keep parameters simple but use EXACT names from schemas above

MANDATORY JSON RESPONSE FORMAT:
{
  "intent": "Brief description of what user wants to accomplish",
  "steps": [
    {
      "step_index": 1,
      "tool": "gmail_tool",
      "action": "search_emails_tool",
      "description": "Human-readable description of this step",
      "parameters": {
        "sender": "john@company.com",
        "max_results": 10,
        "user_id": "{{user_id}}"
      },
      "dependencies": [],
      "expected_outputs": ["email_addresses", "contact_list"]
    },
    {
      "step_index": 2,
      "tool": "calendar_tool",
      "action": "create_calendar_event_tool", 
      "description": "Create meeting with found contacts",
      "parameters": {
        "title": "Team Meeting",
        "start_time": "2025-01-31T14:00:00Z",
        "end_time": "2025-01-31T15:00:00Z",
        "attendees": "{{contact_list}}",
        "include_meet": true,
        "timezone": "UTC",
        "user_id": "{{user_id}}"
      },
      "dependencies": [1],
      "expected_outputs": ["event_id", "meet_link"]
    }
  ],
  "estimated_duration": "45 seconds",
  "requires_confirmation": false
}

CRITICAL ALIGNMENT RULES:
- Use EXACT parameter names from the schemas above
- Always include user_id: "{{user_id}}" in every tool call
- Use template variables ({{variable_name}}) for data from previous steps
- For Gmail sender parameter: use "sender" not "from_email"
- For Calendar title parameter: use "title" not "subject" 
- For Drive query parameter: use "query" not "search_term"
- Include all required parameters, mark optional ones clearly

RESPOND WITH ONLY THE JSON OBJECT ABOVE.
"""
        logger.info("✅ ALIGNED system prompt built")
        return prompt
    
    def _build_planning_prompt(self, user_request: str, user_context: Dict[str, Any]) -> str:
        """Build user prompt with context"""
        logger.info("✍️ Building planning prompt with context")
        
        # Build context string
        context_str = ""
        if user_context:
            context_items = []
            
            # Add date/time context
            if user_context.get("current_date"):
                context_items.append(f"Current Date: {user_context['current_date']}")
            if user_context.get("tomorrow"):
                context_items.append(f"Tomorrow: {user_context['tomorrow']}")
            if user_context.get("yesterday"):
                context_items.append(f"Yesterday: {user_context['yesterday']}")
            
            # Add user info
            if user_context.get("user_email"):
                context_items.append(f"User Email: {user_context['user_email']}")
            if user_context.get("authenticated_services"):
                context_items.append(f"Available Services: {', '.join(user_context['authenticated_services'])}")
            
            if context_items:
                context_str = f"\n\nCONTEXT:\n" + "\n".join(context_items)
        
        prompt = f"""
USER REQUEST: {user_request}{context_str}

Create a step-by-step execution plan using the available tools.

CRITICAL REQUIREMENTS:
1. Respond with ONLY the JSON object - NO explanatory text
2. Use EXACT parameter names from the tool schemas in the system prompt
3. Use actual dates from context where provided
4. Include user_id: "{{{{user_id}}}}" in every tool call
5. Set up proper dependencies between steps
6. Use template variables for data flow between steps

PARAMETER ALIGNMENT CHECKLIST:
- Gmail: Use "sender" not "from_email"
- Calendar: Use "title" not "subject"
- Drive: Use "query" not "search_term"
- Always include required parameters
- Use template variables for step dependencies

RESPOND WITH ONLY THE JSON OBJECT:
"""
        logger.info("✅ Planning prompt built")
        return prompt
    
    def _clean_json_response(self, content: str) -> str:
        """Clean LLM response to extract pure JSON"""
        # Remove markdown code blocks
        content = content.replace('```json', '').replace('```', '')
        
        # Remove common prefixes and explanatory text
        lines = content.split('\n')
        cleaned_lines = []
        json_started = False
        
        for line in lines:
            stripped = line.strip()
            
            if not json_started:
                if stripped.startswith('{'):
                    json_started = True
                    cleaned_lines.append(line)
                # Skip explanatory lines before JSON
                continue
            else:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def _extract_json_from_text(self, text: str) -> str:
        """Extract JSON object from text"""
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx + 1]
        
        return None
    
    def _parse_plan(self, plan_data: Dict[str, Any]) -> ExecutionPlan:
        """Convert JSON plan to ExecutionPlan object"""
        logger.info("🏗️ Parsing plan data to ExecutionPlan")
        
        try:
            steps = []
            step_data_list = plan_data.get("steps", [])
            logger.info(f"📋 Processing {len(step_data_list)} steps")
            
            for i, step_data in enumerate(step_data_list):
                logger.info(f"🔄 Processing step {i+1}: {step_data.get('description', 'No description')}")
                
                # Map action to our ActionType enum
                action_name = step_data.get("action", "")
                tool_name = step_data.get("tool", "")
                
                # Extract tool type from tool name
                if "gmail" in tool_name:
                    tool_type = ToolType.GMAIL
                elif "calendar" in tool_name:
                    tool_type = ToolType.CALENDAR
                elif "drive" in tool_name:
                    tool_type = ToolType.DRIVE
                else:
                    logger.warning(f"⚠️ Unknown tool type: {tool_name}")
                    tool_type = ToolType.GMAIL  # Default fallback
                
                # Map action name to ActionType
                action_type = self._map_action_name(action_name)
                
                step = ExecutionStep(
                    step_index=step_data.get("step_index", i + 1),
                    tool=tool_type,
                    action=action_type,
                    description=step_data.get("description", f"Execute {action_name}"),
                    parameters=step_data.get("parameters", {}),
                    dependencies=step_data.get("dependencies", []),
                    expected_outputs=step_data.get("expected_outputs", [])
                )
                
                steps.append(step)
                logger.info(f"✅ Step {i+1} parsed: {step.tool.value} - {step.action.value}")
            
            execution_plan = ExecutionPlan(
                intent=plan_data.get("intent", "Execute user request"),
                steps=steps,
                estimated_duration=plan_data.get("estimated_duration", "Unknown"),
                requires_confirmation=plan_data.get("requires_confirmation", False)
            )
            
            logger.info(f"✅ ExecutionPlan created: {execution_plan.intent}")
            return execution_plan
            
        except Exception as e:
            logger.error(f"❌ Error parsing plan: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _map_action_name(self, action_name: str) -> ActionType:
        """Map action name to ActionType enum"""
        # Create mapping from tool names to ActionType
        action_mapping = {
            # Gmail actions
            "send_email_tool": ActionType.SEND_EMAIL,
            "search_emails_tool": ActionType.SEARCH_EMAILS,
            "read_recent_emails_tool": ActionType.READ_EMAILS,
            "get_email_threads_tool": ActionType.GET_THREADS,
            
            # Calendar actions
            "create_calendar_event_tool": ActionType.CREATE_EVENT,
            "list_calendar_events_tool": ActionType.LIST_EVENTS,
            "update_calendar_event_tool": ActionType.UPDATE_EVENT,
            "delete_calendar_event_tool": ActionType.DELETE_EVENT,
            "get_calendar_event_tool": ActionType.GET_EVENT,
            
            # Drive actions
            "upload_file_to_drive_tool": ActionType.UPLOAD_FILE,
            "search_files_in_drive_tool": ActionType.SEARCH_FILES,
            "share_drive_file_tool": ActionType.SHARE_FILE,
            "download_drive_file_tool": ActionType.DOWNLOAD_FILE,
            "list_recent_drive_files_tool": ActionType.LIST_FILES,
            "get_drive_file_info_tool": ActionType.SEARCH_FILES  # Closest match
        }
        
        return action_mapping.get(action_name, ActionType.READ_EMAILS)  # Default fallback
    
    def _validate_plan(self, plan: ExecutionPlan) -> List[str]:
        """Validate execution plan for basic issues"""
        issues = []
        
        try:
            if not plan.steps:
                issues.append("Plan has no steps")
                return issues
            
            # Check step indices
            expected_indices = set(range(1, len(plan.steps) + 1))
            actual_indices = {step.step_index for step in plan.steps}
            
            if expected_indices != actual_indices:
                issues.append(f"Step indices mismatch. Expected: {expected_indices}, Got: {actual_indices}")
            
            # Check dependencies
            for step in plan.steps:
                for dep in step.dependencies:
                    if dep >= step.step_index:
                        issues.append(f"Step {step.step_index} depends on future step {dep}")
                    if dep not in actual_indices:
                        issues.append(f"Step {step.step_index} depends on non-existent step {dep}")
            
            return issues
            
        except Exception as e:
            return [f"Error validating plan: {str(e)}"]
    
    def _create_fallback_plan(self, user_request: str, error: str) -> ExecutionPlan:
        """Create simple fallback plan when planning fails"""
        logger.warning(f"⚠️ Creating fallback plan due to error: {error}")
        
        try:
            fallback_step = ExecutionStep(
                step_index=1,
                tool=ToolType.GMAIL,
                action=ActionType.READ_EMAILS,
                description=f"Fallback: Check recent emails (Planning error: {error[:100]})",
                parameters={"max_results": 5, "query": None, "include_attachments": False, "user_id": "{{user_id}}"},
                dependencies=[],
                expected_outputs=["emails"]
            )
            
            fallback_plan = ExecutionPlan(
                intent=f"Fallback plan for: {user_request[:100]}",
                steps=[fallback_step],
                estimated_duration="10 seconds",
                requires_confirmation=False
            )
            
            logger.info("✅ Fallback plan created")
            return fallback_plan
            
        except Exception as fallback_error:
            logger.error(f"❌ Error creating fallback plan: {str(fallback_error)}")
            raise

# Factory function for easy integration
def create_llm_planner() -> StreamlinedLLMPlanner:
    """
    Factory function to create a StreamlinedLLMPlanner instance.
    
    Returns:
        Configured StreamlinedLLMPlanner instance with aligned schemas
    """
    logger.info("🏭 Creating StreamlinedLLMPlanner instance")
    return StreamlinedLLMPlanner()

# Utility functions
def validate_plan_structure(plan: ExecutionPlan) -> Dict[str, Any]:
    """
    Validate plan structure and return detailed analysis.
    
    Args:
        plan: ExecutionPlan to validate
        
    Returns:
        Validation results with issues and recommendations
    """
    validation = {
        "valid": True,
        "issues": [],
        "warnings": [],
        "recommendations": [],
        "stats": {
            "total_steps": len(plan.steps),
            "gmail_steps": len([s for s in plan.steps if s.tool == ToolType.GMAIL]),
            "calendar_steps": len([s for s in plan.steps if s.tool == ToolType.CALENDAR]),
            "drive_steps": len([s for s in plan.steps if s.tool == ToolType.DRIVE]),
            "dependent_steps": len([s for s in plan.steps if s.dependencies]),
            "parallel_steps": len([s for s in plan.steps if not s.dependencies])
        }
    }
    
    # Basic validation
    if not plan.steps:
        validation["issues"].append("Plan has no steps")
        validation["valid"] = False
    
    if not plan.intent:
        validation["warnings"].append("Plan has no clear intent")
    
    # Check for reasonable step count
    if len(plan.steps) > 10:
        validation["warnings"].append(f"Plan has many steps ({len(plan.steps)}). Consider simplification.")
    
    # Check for complex dependencies
    max_deps = max((len(s.dependencies) for s in plan.steps), default=0)
    if max_deps > 3:
        validation["warnings"].append("Some steps have many dependencies. Consider parallelization.")
    
    return validation

if __name__ == "__main__":
    # Example usage for testing
    print("🤖 StreamlinedLLMPlanner Test")
    print("FIXED: Parameter schemas now aligned with tool inputs")
    print("RESULT: No more parameter mapping needed!")
    
    try:
        planner = create_llm_planner()
        print("✅ Planner created successfully")
    except Exception as e:
        print(f"❌ Planner creation failed: {e}")
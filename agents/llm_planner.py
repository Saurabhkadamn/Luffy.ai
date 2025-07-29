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
    Streamlined LLM planner for generating execution plans.
    
    Simplified to work with LangChain tools and ToolNode execution.
    Removes complex parameter mapping since tools now handle their own validation.
    """
    
    def __init__(self):
        logger.info("🤖 Initializing StreamlinedLLMPlanner")
        
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
            
            logger.info("📝 Building streamlined system prompt")
            self.system_prompt = self._build_system_prompt()
            logger.info(f"✅ System prompt built (length: {len(self.system_prompt)} chars)")
            
            logger.info("✅ StreamlinedLLMPlanner initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize StreamlinedLLMPlanner: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def create_plan(self, user_request: str, user_context: Dict[str, Any] = None) -> ExecutionPlan:
        """
        Generate execution plan from user request.
        
        Simplified planning focused on tool selection and sequencing
        rather than complex parameter mapping.
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
                # Continue anyway - tools will handle parameter validation
            
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
    
    def _build_system_prompt(self) -> str:
        """Build streamlined system prompt focused on tool orchestration"""
        logger.info("📝 Building streamlined system prompt")
        
        prompt = """
You are an AI workflow planner for a Google productivity assistant with Gmail, Calendar, and Drive integration.

CRITICAL: Respond with ONLY valid JSON. No explanations, no markdown, no additional text.

AVAILABLE TOOLS (Simplified):

1. GMAIL TOOLS:
   - send_email_tool: Send emails to recipients
   - search_emails_tool: Search emails with filters (sender, date_range, keywords)
   - read_recent_emails_tool: Read recent emails from inbox
   - get_email_threads_tool: Get email conversation threads

2. CALENDAR TOOLS:
   - create_calendar_event_tool: Create events with optional Google Meet
   - list_calendar_events_tool: List events in date range
   - update_calendar_event_tool: Update existing events
   - delete_calendar_event_tool: Delete events
   - get_calendar_event_tool: Get event details

3. DRIVE TOOLS:
   - upload_file_to_drive_tool: Upload files to Drive
   - search_files_in_drive_tool: Search Drive files
   - share_drive_file_tool: Share files with users
   - download_drive_file_tool: Download files
   - list_recent_drive_files_tool: List recent files
   - get_drive_file_info_tool: Get file details

PLANNING PRINCIPLES:
1. Break complex requests into logical steps
2. Use simple, specific tool names from the list above
3. Include realistic parameter values in JSON format
4. Consider dependencies between steps
5. Focus on workflow orchestration, not parameter details
6. Use template variables for data that flows between steps

PARAMETER GUIDELINES:
- Use actual dates from context (never "today", "tomorrow")
- For Gmail: date_range as ["start_date", "end_date"] in YYYY-MM-DD format
- For Calendar: times in ISO format "YYYY-MM-DDTHH:MM:SSZ"
- For shared data: use template variables like "{{attendee_emails}}" or "{{meeting_link}}"
- Keep parameters simple - tools will handle validation

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
        "max_results": 10
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
        "include_meet": true
      },
      "dependencies": [1],
      "expected_outputs": ["event_id", "meet_link"]
    }
  ],
  "estimated_duration": "45 seconds",
  "requires_confirmation": false
}

IMPORTANT RULES:
- Use EXACT tool names from the list above
- Each step MUST have a clear "description" field
- Use template variables ({{variable_name}}) for data from previous steps
- Keep dependencies simple and logical
- Focus on high-level workflow, not parameter complexity

RESPOND WITH ONLY THE JSON OBJECT ABOVE.
"""
        logger.info("✅ Streamlined system prompt built")
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

REQUIREMENTS:
1. Respond with ONLY the JSON object - NO explanatory text
2. Use EXACT tool names from the system prompt
3. Use actual dates from context where provided
4. Include clear step descriptions
5. Set up proper dependencies between steps
6. Use template variables for data flow between steps

FOCUS ON:
- Breaking the request into logical steps
- Selecting the right tools for each step
- Creating a clear execution sequence
- Using realistic parameter values

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
                parameters={"max_results": 5},
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
        Configured StreamlinedLLMPlanner instance
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
    print("This module handles plan generation for LangGraph workflows")
    
    try:
        planner = create_llm_planner()
        print("✅ Planner created successfully")
    except Exception as e:
        print(f"❌ Planner creation failed: {e}")
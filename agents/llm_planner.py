import json
from typing import Dict, Any, List
from langchain.schema import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from agents.plan_schema import ExecutionPlan, ExecutionStep, ToolType, ActionType
from config import settings

class LLMPlanner:
    """Converts natural language requests into structured execution plans"""
    
    def __init__(self):
        # Create LLM instance with standardized config
        self.llm = ChatNVIDIA(
            model="moonshotai/kimi-k2-instruct",
            api_key=settings.NVIDIA_API_KEY,
            temperature=0.6,
            top_p=0.9,
            max_tokens=4096,
        )
        self.system_prompt = self._build_system_prompt()
    
    def create_plan(self, user_request: str, user_context: Dict[str, Any] = None) -> ExecutionPlan:
        """Generate execution plan from user request"""
        
        user_prompt = self._build_user_prompt(user_request, user_context)
        
        try:
            # Use LangChain message format
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # Extract content from LangChain response
            response_content = response.content if hasattr(response, 'content') else str(response)
            
            plan_data = json.loads(response_content)
            return self._parse_plan(plan_data)
            
        except json.JSONDecodeError as e:
            # Try to extract JSON from response if it's wrapped in other text
            try:
                response_content = response.content if hasattr(response, 'content') else str(response)
                
                # Find JSON in response
                start_idx = response_content.find('{')
                end_idx = response_content.rfind('}') + 1
                
                if start_idx != -1 and end_idx != -1:
                    json_str = response_content[start_idx:end_idx]
                    plan_data = json.loads(json_str)
                    return self._parse_plan(plan_data)
                else:
                    raise e
            except:
                return self._create_fallback_plan(user_request, f"JSON parsing error: {str(e)}")
                
        except Exception as e:
            # Fallback plan for errors
            return self._create_fallback_plan(user_request, str(e))
    
    def _build_system_prompt(self) -> str:
        return """
You are an AI workflow planner for a Google productivity assistant.

AVAILABLE TOOLS AND ACTIONS:
1. GMAIL_TOOL:
   - send_email: Send emails to recipients
   - read_recent_emails: Get recent inbox messages  
   - search_emails_by_filters: Search by sender, date, keywords
   - get_email_threads: Get conversation threads

2. CALENDAR_TOOL:
   - create_event: Create calendar events
   - create_meet_event: Create events with Google Meet links
   - list_events: Get events in date range
   - update_event: Modify existing events
   - delete_event: Remove events
   - get_meet_link_from_event: Extract Meet link from event

3. DRIVE_TOOL:
   - upload_file: Upload files to Drive
   - search_files: Find files by name, type, folder
   - download_file: Download files locally
   - share_file: Share files with users or make public
   - list_recent_files: Get recently modified files

PLANNING RULES:
1. Break complex requests into sequential steps
2. Each step should have clear dependencies
3. Extract required parameters from user request
4. Consider cross-tool workflows (email + calendar, calendar + drive)
5. Steps that can run in parallel should have no dependencies between them
6. Always include realistic parameter values
7. Use template variables like {{meeting_title}} or {{meeting_link}} when data comes from previous steps

RESPONSE FORMAT (JSON ONLY):
{
  "intent": "brief description of user goal",
  "steps": [
    {
      "step_index": 1,
      "tool": "gmail_tool",
      "action": "send_email", 
      "description": "Send email to team about meeting",
      "parameters": {"to": "{{team_emails}}", "subject": "Meeting Tomorrow", "body": "We have a meeting at {{meeting_time}}. Join here: {{meeting_link}}"},
      "dependencies": [],
      "expected_outputs": ["message_id", "recipient_email"]
    }
  ],
  "estimated_duration": "30 seconds",
  "requires_confirmation": false
}

IMPORTANT: Respond with valid JSON only. No additional text before or after the JSON.
"""

    def _build_user_prompt(self, user_request: str, user_context: Dict[str, Any]) -> str:
        context_str = ""
        if user_context:
            # Format user context nicely
            context_items = []
            if user_context.get("user_email"):
                context_items.append(f"User email: {user_context['user_email']}")
            if user_context.get("user_name"):
                context_items.append(f"User name: {user_context['user_name']}")
            if user_context.get("authenticated_services"):
                context_items.append(f"Available services: {', '.join(user_context['authenticated_services'])}")
            
            if context_items:
                context_str = f"\n\nUSER CONTEXT:\n" + "\n".join(context_items)
        
        return f"""
USER REQUEST: {user_request}{context_str}

Create a detailed execution plan to fulfill this request. Consider:
1. What tools and actions are needed?
2. What order should steps execute in?
3. What parameters are required for each step?
4. Which steps depend on outputs from previous steps?
5. Use template variables for data that comes from previous steps

Respond with valid JSON only.
"""

    def _parse_plan(self, plan_data: Dict[str, Any]) -> ExecutionPlan:
        """Convert JSON plan to ExecutionPlan object"""
        
        steps = []
        for step_data in plan_data["steps"]:
            step = ExecutionStep(
                step_index=step_data["step_index"],
                tool=ToolType(step_data["tool"]),
                action=ActionType(step_data["action"]),
                description=step_data["description"],
                parameters=step_data["parameters"],
                dependencies=step_data.get("dependencies", []),
                expected_outputs=step_data.get("expected_outputs", [])
            )
            steps.append(step)
        
        return ExecutionPlan(
            intent=plan_data["intent"],
            steps=steps,
            estimated_duration=plan_data.get("estimated_duration", "Unknown"),
            requires_confirmation=plan_data.get("requires_confirmation", False)
        )
    
    def _create_fallback_plan(self, user_request: str, error: str) -> ExecutionPlan:
        """Create simple fallback plan when LLM planning fails"""
        
        fallback_step = ExecutionStep(
            step_index=1,
            tool=ToolType.GMAIL,
            action=ActionType.READ_RECENT_EMAILS,
            description=f"Fallback: Check recent emails (Planning error: {error})",
            parameters={"max_results": 5},
            dependencies=[],
            expected_outputs=["emails"]
        )
        
        return ExecutionPlan(
            intent=f"Fallback plan for: {user_request}",
            steps=[fallback_step],
            estimated_duration="10 seconds",
            requires_confirmation=False
        )
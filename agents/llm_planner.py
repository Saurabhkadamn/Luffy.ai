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

class LLMPlanner:
    """Converts natural language requests into structured execution plans with date context and strict JSON format"""
    
    def __init__(self):
        logger.info("🤖 Initializing LLMPlanner")
        
        try:
            # Create LLM instance with standardized config
            logger.info("🔧 Creating NVIDIA ChatNVIDIA instance")
            logger.info(f"🔑 Using API key: {'*' * 20}{settings.NVIDIA_API_KEY[-4:] if settings.NVIDIA_API_KEY else 'MISSING'}")
            
            self.llm = ChatNVIDIA(
                model="moonshotai/kimi-k2-instruct",
                api_key=settings.NVIDIA_API_KEY,
                temperature=0.6,
                top_p=0.9,
                max_tokens=4096,
            )
            logger.info("✅ ChatNVIDIA instance created successfully")
            
            logger.info("📝 Building system prompt")
            self.system_prompt = self._build_system_prompt()
            logger.info(f"✅ System prompt built (length: {len(self.system_prompt)} chars)")
            
            logger.info("✅ LLMPlanner initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize LLMPlanner: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def create_plan(self, user_request: str, user_context: Dict[str, Any] = None) -> ExecutionPlan:
        """Generate execution plan from user request with comprehensive logging"""
        
        logger.info(f"📋 Creating plan for request: {user_request}")
        logger.info(f"📊 User context: {user_context}")
        
        try:
            logger.info("✍️ Building user prompt")
            user_prompt = self._build_user_prompt(user_request, user_context)
            logger.info(f"✅ User prompt built (length: {len(user_prompt)} chars)")
            
            logger.info("💬 Preparing LangChain messages")
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_prompt)
            ]
            logger.info(f"✅ Messages prepared (system: {len(self.system_prompt)} chars, user: {len(user_prompt)} chars)")
            
            logger.info("🚀 Invoking LLM")
            response = self.llm.invoke(messages)
            logger.info("✅ LLM response received")
            
            # Extract content from LangChain response
            response_content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"📄 Response content length: {len(response_content)} chars")
            logger.info(f"📄 Response preview: {response_content[:200]}...")
            
            # Clean the response content to extract JSON
            cleaned_content = self._clean_json_response(response_content)
            logger.info(f"🧹 Cleaned content length: {len(cleaned_content)} chars")
            
            logger.info("🔄 Parsing JSON response")
            plan_data = json.loads(cleaned_content)
            logger.info("✅ JSON parsed successfully")
            logger.info(f"📊 Plan data keys: {list(plan_data.keys())}")
            
            logger.info("🏗️ Converting to ExecutionPlan object")
            execution_plan = self._parse_plan(plan_data)
            logger.info(f"✅ ExecutionPlan created: {execution_plan.intent}")
            logger.info(f"📋 Plan has {len(execution_plan.steps)} steps")
            
            return execution_plan
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing error: {str(e)}")
            logger.error(f"📄 Raw response that failed to parse: {response_content}")
            
            # Try to extract JSON from response if it's wrapped in other text
            try:
                logger.info("🔍 Attempting to extract JSON from response")
                json_str = self._extract_json_from_text(response_content)
                
                if json_str:
                    logger.info(f"🔍 Extracted JSON: {json_str[:200]}...")
                    plan_data = json.loads(json_str)
                    logger.info("✅ Extracted JSON parsed successfully")
                    
                    execution_plan = self._parse_plan(plan_data)
                    logger.info(f"✅ ExecutionPlan created from extracted JSON: {execution_plan.intent}")
                    return execution_plan
                else:
                    logger.error("❌ No valid JSON found in response")
                    raise e
                    
            except Exception as extract_error:
                logger.error(f"❌ JSON extraction also failed: {str(extract_error)}")
                return self._create_fallback_plan(user_request, f"JSON parsing error: {str(e)}")
                
        except Exception as e:
            logger.error(f"❌ General error in create_plan: {str(e)}")
            logger.error(traceback.format_exc())
            # Fallback plan for errors
            return self._create_fallback_plan(user_request, str(e))
    
    def _clean_json_response(self, content: str) -> str:
        """Clean LLM response to extract pure JSON"""
        
        # Remove markdown code blocks
        content = content.replace('```json', '').replace('```', '')
        
        # Remove common prefixes
        lines = content.split('\n')
        cleaned_lines = []
        json_started = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip explanation lines before JSON
            if not json_started:
                if stripped.startswith('{'):
                    json_started = True
                    cleaned_lines.append(line)
                elif stripped.startswith('"intent"') or stripped.startswith('"steps"'):
                    # Sometimes JSON starts without opening brace on first line
                    json_started = True
                    cleaned_lines.append('{')
                    cleaned_lines.append(line)
                # Skip lines that look like explanations
                elif any(word in stripped.lower() for word in ['search', 'find', 'using', 'tool', 'july', 'will', 'emails']):
                    continue
            else:
                cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def _extract_json_from_text(self, text: str) -> str:
        """Extract JSON object from text that might contain other content"""
        
        # Find JSON boundaries
        start_idx = text.find('{')
        end_idx = text.rfind('}')
        
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            return text[start_idx:end_idx + 1]
        
        return None
    
    def _build_system_prompt(self) -> str:
        logger.info("📝 Building enhanced system prompt with simplified action names")
        prompt = """
You are an AI workflow planner for a Google productivity assistant.

CRITICAL: You MUST respond with ONLY valid JSON. No explanations, no markdown, no additional text.

AVAILABLE TOOLS AND ACTIONS WITH EXACT SIGNATURES - SIMPLIFIED ACTIONS:

1. GMAIL_TOOL:
   - search_emails: 
     Parameters: sender (str), date_range (tuple), keywords (str/list), has_attachment (bool), max_results (int)
     Example: {"date_range": ["2025-01-28", "2025-01-29"], "max_results": 20}
     NOTE: date_range uses [start_date, end_date] where end_date is EXCLUSIVE
   
   - read_emails: 
     Parameters: max_results (int), query (str), include_attachments (bool)
     Example: {"max_results": 10, "include_attachments": false}
   
   - get_threads:
     Parameters: thread_id (str), query (str), include_attachments (bool)  
     Example: {"thread_id": "abc123"} OR {"query": "subject:meeting"}
   
   - send_email:
     Parameters: to (str/list), subject (str), body (str), cc (str/list), bcc (str/list), attachments (list)
     Example: {"to": ["user@email.com"], "subject": "Meeting", "body": "Hi there"}

2. CALENDAR_TOOL:
   - create_event:
     Parameters: title (str), start_time (str), end_time (str), description (str), attendees (list), location (str), include_meet (bool)
     Example: {"title": "Meeting", "start_time": "2025-01-29T14:00:00Z", "end_time": "2025-01-29T15:00:00Z", "include_meet": true}
   
   - list_events:
     Parameters: start_date (str), end_date (str), max_results (int), timezone (str)
     Example: {"start_date": "2025-01-28", "end_date": "2025-01-28", "max_results": 10}
   
   - update_event:
     Parameters: event_id (str), title (str), start_time (str), end_time (str), attendees (list)
     Example: {"event_id": "event123", "title": "Updated Meeting"}
   
   - delete_event:
     Parameters: event_id (str)
     Example: {"event_id": "event123"}
   
   - get_event:
     Parameters: event_id (str)
     Example: {"event_id": "event123"}

3. DRIVE_TOOL:
   - search_files:
     Parameters: query (str), file_type (str), folder_id (str), max_results (int), include_trashed (bool)
     Example: {"query": "project document", "file_type": "pdf", "max_results": 10}
   
   - upload_file:
     Parameters: file_path (str), filename (str), folder_id (str), description (str), make_public (bool)
     Example: {"filename": "document.pdf", "description": "Project file"}
   
   - share_file:
     Parameters: file_id (str), email_addresses (list), role (str), make_public (bool)
     Example: {"file_id": "file123", "email_addresses": ["user@email.com"], "role": "reader"}
   
   - download_file:
     Parameters: file_id (str), download_path (str)
     Example: {"file_id": "file123", "download_path": "/downloads/"}
   
   - list_files:
     Parameters: max_results (int), file_types (list), recent (bool)
     Example: {"max_results": 20, "file_types": ["pdf", "doc"], "recent": true}

DATE/TIME USAGE RULES:
- For Gmail date_range: Use [start_date, end_date] where end_date is EXCLUSIVE
  * "today's emails": ["2025-07-28", "2025-07-29"] 
  * "yesterday's emails": ["2025-07-27", "2025-07-28"]
- For Calendar times: Use ISO format "2025-01-29T14:00:00Z"
- For Calendar dates: Use "YYYY-MM-DD" format
- Always use actual dates from context, never relative terms like "today", "tomorrow"

CRITICAL GMAIL API REQUIREMENTS:
- Gmail date_range MUST be [start_date, next_day] because end_date is EXCLUSIVE
- Example: For July 27th emails, use ["2025-07-27", "2025-07-28"]
- This ensures the Gmail API searches correctly with after:2025/07/27 before:2025/07/28

PLANNING RULES:
1. Break complex requests into sequential steps
2. Each step MUST have: step_index, tool, action, description, parameters, dependencies, expected_outputs
3. Extract required parameters from user request
4. Use EXACT action names from the simplified list above
5. Include realistic parameter values
6. Use template variables like {{meeting_title}} or {{meeting_link}} when data comes from previous steps
7. Steps that can run in parallel should have no dependencies between them

MANDATORY JSON RESPONSE FORMAT:
{
  "intent": "brief description of user goal",
  "steps": [
    {
      "step_index": 1,
      "tool": "gmail_tool",
      "action": "search_emails", 
      "description": "Search for yesterday's emails",
      "parameters": {"date_range": ["2025-07-27", "2025-07-28"], "max_results": 20},
      "dependencies": [],
      "expected_outputs": ["email_addresses", "message_ids"]
    }
  ],
  "estimated_duration": "30 seconds",
  "requires_confirmation": false
}

ABSOLUTE REQUIREMENTS: 
- Respond with ONLY the JSON object above
- NO explanatory text before or after the JSON
- NO markdown code blocks or formatting
- Each step MUST include "description" field
- Use EXACT action names from the simplified list above
- For Gmail searches, use [start_date, next_day] format for date_range
- Use actual dates from the context, never "today", "tomorrow" etc.
"""
        logger.info("✅ Enhanced system prompt built with simplified action names")
        return prompt

    def _build_user_prompt(self, user_request: str, user_context: Dict[str, Any]) -> str:
        logger.info("✍️ Building user prompt with date context and simplified action requirements")
        
        context_str = ""
        if user_context:
            # Format user context nicely with date information
            context_items = []
            
            # Add current date/time context
            if user_context.get("current_date"):
                context_items.append(f"Current Date: {user_context['current_date']}")
                logger.info(f"📅 Added current date to context: {user_context['current_date']}")
            
            if user_context.get("current_time"):
                context_items.append(f"Current Time: {user_context['current_time']}")
                
            if user_context.get("day_of_week"):
                context_items.append(f"Day of Week: {user_context['day_of_week']}")
                
            if user_context.get("tomorrow"):
                context_items.append(f"Tomorrow: {user_context['tomorrow']}")
                
            if user_context.get("yesterday"):
                context_items.append(f"Yesterday: {user_context['yesterday']}")
                
            if user_context.get("this_week_start") and user_context.get("this_week_end"):
                context_items.append(f"This Week: {user_context['this_week_start']} to {user_context['this_week_end']}")
            
            # Add user info
            if user_context.get("user_email"):
                context_items.append(f"User Email: {user_context['user_email']}")
                logger.info(f"📧 Added user email to context")
            if user_context.get("user_name"):
                context_items.append(f"User Name: {user_context['user_name']}")
                logger.info(f"👤 Added user name to context")
            if user_context.get("authenticated_services"):
                context_items.append(f"Available Services: {', '.join(user_context['authenticated_services'])}")
                logger.info(f"🔧 Added services to context: {user_context['authenticated_services']}")
            
            if context_items:
                context_str = f"\n\nCURRENT CONTEXT:\n" + "\n".join(context_items)
                logger.info(f"✅ Context string built: {len(context_str)} chars")
        
        # Calculate next day for Gmail API exclusive end dates
        current_date = user_context.get('current_date', '2025-07-28')
        yesterday = user_context.get('yesterday', '2025-07-27')
        tomorrow = user_context.get('tomorrow', '2025-07-29')
        
        # For Gmail API, we need the day AFTER for exclusive end dates
        from datetime import datetime, timedelta
        try:
            current_dt = datetime.strptime(current_date, '%Y-%m-%d')
            next_day = (current_dt + timedelta(days=1)).strftime('%Y-%m-%d')
            
            yesterday_dt = datetime.strptime(yesterday, '%Y-%m-%d')
            yesterday_next = (yesterday_dt + timedelta(days=1)).strftime('%Y-%m-%d')
        except:
            next_day = '2025-07-29'
            yesterday_next = '2025-07-28'
        
        prompt = f"""
USER REQUEST: {user_request}{context_str}

Create a detailed execution plan using the EXACT simplified action names provided in the system prompt.

CRITICAL REQUIREMENTS:
1. Respond with ONLY the JSON object - NO explanatory text
2. Use EXACT simplified action names (e.g., "search_emails" not "search_emails_by_filters")
3. Use actual dates from context (e.g., "{current_date}" not "today")
4. For Gmail date_range, use [start_date, next_day] format because end_date is EXCLUSIVE
5. MUST include "description" field in each step
6. Ensure all parameters match the expected tool method signatures
7. Use template variables for data that comes from previous steps

GMAIL DATE EXAMPLES based on current context:
- "today's emails" → {{"date_range": ["{current_date}", "{next_day}"], "max_results": 20}}
- "yesterday's emails" → {{"date_range": ["{yesterday}", "{yesterday_next}"], "max_results": 20}}

CALENDAR DATE EXAMPLES:
- "tomorrow's meeting" → {{"start_time": "{tomorrow}T14:00:00Z", "end_time": "{tomorrow}T15:00:00Z"}}

RESPOND WITH ONLY THE JSON OBJECT:
"""
        logger.info("✅ User prompt built with simplified action requirements")
        return prompt

    def _parse_plan(self, plan_data: Dict[str, Any]) -> ExecutionPlan:
        """Convert JSON plan to ExecutionPlan object with logging"""
        
        logger.info("🏗️ Parsing plan data to ExecutionPlan")
        logger.info(f"📊 Plan data structure: {list(plan_data.keys())}")
        
        try:
            steps = []
            step_data_list = plan_data.get("steps", [])
            logger.info(f"📋 Processing {len(step_data_list)} steps")
            
            for i, step_data in enumerate(step_data_list):
                logger.info(f"🔄 Processing step {i+1}: {step_data.get('description', 'No description')}")
                
                try:
                    # Ensure required fields exist with defaults
                    step = ExecutionStep(
                        step_index=step_data["step_index"],
                        tool=ToolType(step_data["tool"]),
                        action=ActionType(step_data["action"]),
                        description=step_data.get("description", f"Execute {step_data['action']} action"),
                        parameters=step_data.get("parameters", {}),
                        dependencies=step_data.get("dependencies", []),
                        expected_outputs=step_data.get("expected_outputs", [])
                    )
                    steps.append(step)
                    logger.info(f"✅ Step {i+1} parsed successfully: {step.tool.value} - {step.action.value}")
                    logger.info(f"📋 Step {i+1} parameters: {list(step.parameters.keys())}")
                    
                    # Log Gmail date_range specifically for debugging
                    if step.tool.value == "gmail_tool" and "date_range" in step.parameters:
                        logger.info(f"📅 Gmail date_range for step {i+1}: {step.parameters['date_range']}")
                    
                except Exception as step_error:
                    logger.error(f"❌ Error parsing step {i+1}: {str(step_error)}")
                    logger.error(f"📊 Step data: {step_data}")
                    raise
            
            logger.info("🏗️ Creating ExecutionPlan object")
            execution_plan = ExecutionPlan(
                intent=plan_data.get("intent", "Execute user request"),
                steps=steps,
                estimated_duration=plan_data.get("estimated_duration", "Unknown"),
                requires_confirmation=plan_data.get("requires_confirmation", False)
            )
            
            logger.info(f"✅ ExecutionPlan created successfully: {execution_plan.intent}")
            return execution_plan
            
        except Exception as e:
            logger.error(f"❌ Error parsing plan: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_fallback_plan(self, user_request: str, error: str) -> ExecutionPlan:
        """Create simple fallback plan when LLM planning fails with logging"""
        
        logger.warning(f"⚠️ Creating fallback plan due to error: {error}")
        logger.info(f"📋 Original request: {user_request}")
        
        try:
            fallback_step = ExecutionStep(
                step_index=1,
                tool=ToolType.GMAIL,
                action=ActionType.READ_EMAILS,  # Updated to use simplified action
                description=f"Fallback: Check recent emails (Planning error: {error})",
                parameters={"max_results": 5},
                dependencies=[],
                expected_outputs=["emails"]
            )
            
            fallback_plan = ExecutionPlan(
                intent=f"Fallback plan for: {user_request}",
                steps=[fallback_step],
                estimated_duration="10 seconds",
                requires_confirmation=False
            )
            
            logger.info("✅ Fallback plan created successfully")
            return fallback_plan
            
        except Exception as fallback_error:
            logger.error(f"❌ Error creating fallback plan: {str(fallback_error)}")
            logger.error(traceback.format_exc())
            raise
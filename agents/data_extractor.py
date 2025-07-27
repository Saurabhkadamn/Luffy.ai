import json
from typing import Dict, Any, List
from langchain.schema import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from agents.plan_schema import StepResult, ExecutionStep
from config import settings

class DataExtractor:
    """Extracts relevant data from tool outputs using LLM"""
    
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
    
    def extract_data(self, step_result: StepResult, completed_step: ExecutionStep, 
                    remaining_steps: List[ExecutionStep], shared_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract useful data from step result for future steps"""
        
        user_prompt = self._build_extraction_prompt(step_result, completed_step, remaining_steps, shared_context)
        
        try:
            # Use LangChain message format
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_prompt)
            ]
            
            response = self.llm.invoke(messages)
            
            # Extract content from LangChain response
            response_content = response.content if hasattr(response, 'content') else str(response)
            
            return json.loads(response_content)
            
        except json.JSONDecodeError:
            # Try to extract JSON from response
            try:
                start_idx = response_content.find('{')
                end_idx = response_content.rfind('}') + 1
                
                if start_idx != -1 and end_idx != -1:
                    json_str = response_content[start_idx:end_idx]
                    return json.loads(json_str)
                else:
                    return self._fallback_extraction(step_result)
            except:
                return self._fallback_extraction(step_result)
                
        except Exception as e:
            # Fallback extraction
            return self._fallback_extraction(step_result)
    
    def _build_system_prompt(self) -> str:
        return """
You are a data extraction agent for multi-step Google API workflows.

Your job: Extract relevant data from tool outputs that future workflow steps might need.

COMMON DATA PATTERNS:
- Gmail outputs → email addresses, message IDs, subject lines, thread IDs
- Calendar outputs → event IDs, Meet links, attendee lists, time slots
- Drive outputs → file IDs, share links, file names, folder paths

EXTRACTION INTELLIGENCE:
1. Consider what FUTURE steps in the workflow might need
2. Extract identifiers (IDs, emails, links) and key entities (names, dates, topics)
3. If calendar event created → extract meet_link for potential email inclusion
4. If emails found → extract email_addresses for potential meeting invitations
5. If files mentioned → extract file_ids for potential sharing or attachment
6. Look for patterns that suggest user intent (meeting topics, project names, team members)

RESPONSE FORMAT (JSON only):
{
  "extracted_data": {
    "key_identifier_1": "value1",
    "key_identifier_2": "value2",
    "list_of_items": ["item1", "item2"]
  },
  "for_future_steps": {
    "meeting_attendees": ["email1@co.com", "email2@co.com"],
    "files_to_attach": ["file_id_1", "file_id_2"], 
    "meeting_details": {
      "title": "extracted or inferred title",
      "description": "relevant context"
    }
  },
  "context_updates": {
    "user_preferences": "any learned preferences",
    "common_contacts": ["frequently contacted emails"],
    "project_context": "any project or topic context discovered"
  }
}

IMPORTANT: Respond with valid JSON only. No additional text.
"""

    def _build_extraction_prompt(self, step_result: StepResult, completed_step: ExecutionStep,
                                remaining_steps: List[ExecutionStep], shared_context: Dict[str, Any]) -> str:
        
        remaining_summary = []
        for step in remaining_steps:
            remaining_summary.append(f"Step {step.step_index}: {step.tool.value} - {step.action.value}")
        
        return f"""
COMPLETED STEP:
Step {step_result.step_index}: {step_result.tool.value} - {step_result.action.value}
Description: {completed_step.description}

TOOL OUTPUT:
{json.dumps(step_result.raw_output, indent=2)}

REMAINING WORKFLOW STEPS:
{chr(10).join(remaining_summary) if remaining_summary else "None"}

CURRENT SHARED CONTEXT:
{json.dumps(shared_context, indent=2)}

Extract data that will be useful for the remaining workflow steps. 
Focus on identifiers, relationships, and context that future steps might need.

Respond with JSON only.
"""

    def _fallback_extraction(self, step_result: StepResult) -> Dict[str, Any]:
        """Simple fallback extraction when LLM fails"""
        
        extracted = {
            "extracted_data": {},
            "for_future_steps": {},
            "context_updates": {}
        }
        
        # Basic extraction based on tool type
        if step_result.tool.value == "gmail_tool":
            if "data" in step_result.raw_output and "emails" in step_result.raw_output["data"]:
                emails = step_result.raw_output["data"]["emails"]
                if emails:
                    extracted["extracted_data"]["email_addresses"] = [email.get("from", "") for email in emails if email.get("from")]
        
        elif step_result.tool.value == "calendar_tool":
            if "data" in step_result.raw_output:
                data = step_result.raw_output["data"]
                if "meet_link" in data:
                    extracted["extracted_data"]["meeting_link"] = data["meet_link"]
                if "event_id" in data:
                    extracted["extracted_data"]["event_id"] = data["event_id"]
        
        elif step_result.tool.value == "drive_tool":
            if "data" in step_result.raw_output:
                data = step_result.raw_output["data"]
                if "file_id" in data:
                    extracted["extracted_data"]["file_id"] = data["file_id"]
                if "web_view_link" in data:
                    extracted["extracted_data"]["share_link"] = data["web_view_link"]
        
        return extracted
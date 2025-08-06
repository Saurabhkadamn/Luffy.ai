import json
import logging
import traceback
from typing import Dict, Any, List
from langchain.schema import HumanMessage, SystemMessage
from langchain_nvidia_ai_endpoints import ChatNVIDIA
from agents.plan_schema import StepResult, ExecutionStep
from config import settings

# Configure logging
logger = logging.getLogger(__name__)

class DataExtractor:
    """Extracts relevant data from tool outputs using LLM with comprehensive logging"""
    
    def __init__(self):
        logger.info("🤖 Initializing DataExtractor")
        
        try:
            # Create LLM instance with standardized config
            logger.info("🔧 Creating ChatNVIDIA instance for data extraction")
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
            
            logger.info("✅ DataExtractor initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize DataExtractor: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def extract_data(self, step_result: StepResult, completed_step: ExecutionStep, 
                    remaining_steps: List[ExecutionStep], shared_context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract useful data from step result for future steps with comprehensive logging"""
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        logger.info(f"🔍 Starting data extraction for step {step_result['step_index']}")
        logger.info(f"🔧 Tool: {step_result['tool'].value}, Action: {step_result['action'].value}")
        logger.info(f"📊 Step status: {step_result['status']}")
        logger.info(f"📋 Remaining steps count: {len(remaining_steps)}")
        
        try:
            logger.info("✍️ Building extraction prompt")
            user_prompt = self._build_extraction_prompt(step_result, completed_step, remaining_steps, shared_context)
            logger.info(f"✅ Extraction prompt built (length: {len(user_prompt)} chars)")
            
            logger.info("💬 Preparing LangChain messages")
            messages = [
                SystemMessage(content=self.system_prompt),
                HumanMessage(content=user_prompt)
            ]
            logger.info("✅ Messages prepared for LLM")
            
            logger.info("🚀 Invoking LLM for data extraction")
            response = self.llm.invoke(messages)
            logger.info("✅ LLM response received")
            
            # Extract content from LangChain response
            response_content = response.content if hasattr(response, 'content') else str(response)
            logger.info(f"📄 Response content length: {len(response_content)} chars")
            logger.info(f"📄 Response preview: {response_content[:200]}...")
            
            logger.info("🔄 Parsing JSON response")
            extracted_data = json.loads(response_content)
            logger.info("✅ JSON parsed successfully")
            logger.info(f"📊 Extracted data keys: {list(extracted_data.keys())}")
            
            # Log key extracted information
            if 'extracted_data' in extracted_data:
                logger.info(f"🔑 Main extracted data: {list(extracted_data['extracted_data'].keys())}")
            if 'for_future_steps' in extracted_data:
                logger.info(f"🔮 Data for future steps: {list(extracted_data['for_future_steps'].keys())}")
            if 'context_updates' in extracted_data:
                logger.info(f"📝 Context updates: {list(extracted_data['context_updates'].keys())}")
            
            logger.info(f"✅ Data extraction completed successfully for step {step_result['step_index']}")
            return extracted_data
            
        except json.JSONDecodeError as e:
            logger.error(f"❌ JSON parsing error in data extraction: {str(e)}")
            logger.error(f"📄 Raw response that failed to parse: {response_content}")
            
            # Try to extract JSON from response
            try:
                logger.info("🔍 Attempting to extract JSON from response")
                start_idx = response_content.find('{')
                end_idx = response_content.rfind('}') + 1
                
                logger.info(f"🔍 JSON boundaries: start={start_idx}, end={end_idx}")
                
                if start_idx != -1 and end_idx != -1:
                    json_str = response_content[start_idx:end_idx]
                    logger.info(f"🔍 Extracted JSON: {json_str[:200]}...")
                    
                    extracted_data = json.loads(json_str)
                    logger.info("✅ Extracted JSON parsed successfully")
                    return extracted_data
                else:
                    logger.error("❌ No JSON boundaries found in response")
                    return self._fallback_extraction(step_result)
            except Exception as extract_error:
                logger.error(f"❌ JSON extraction also failed: {str(extract_error)}")
                return self._fallback_extraction(step_result)
                
        except Exception as e:
            logger.error(f"❌ General error in data extraction: {str(e)}")
            logger.error(traceback.format_exc())
            # Fallback extraction
            return self._fallback_extraction(step_result)
    
    def _build_system_prompt(self) -> str:
        logger.info("📝 Building data extraction system prompt")
        prompt = """
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
        logger.info("✅ Data extraction system prompt built")
        return prompt

    def _build_extraction_prompt(self, step_result: StepResult, completed_step: ExecutionStep,
                                remaining_steps: List[ExecutionStep], shared_context: Dict[str, Any]) -> str:
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        logger.info(f"✍️ Building extraction prompt for step {step_result['step_index']}")
        
        try:
            remaining_summary = []
            for step in remaining_steps:
                remaining_summary.append(f"Step {step['step_index']}: {step['tool'].value} - {step['action'].value}")
            
            logger.info(f"📋 Built summary of {len(remaining_summary)} remaining steps")
            
            prompt = f"""
COMPLETED STEP:
Step {step_result['step_index']}: {step_result['tool'].value} - {step_result['action'].value}
Description: {completed_step['description']}

TOOL OUTPUT:
{json.dumps(step_result['raw_output'], indent=2)}

REMAINING WORKFLOW STEPS:
{chr(10).join(remaining_summary) if remaining_summary else "None"}

CURRENT SHARED CONTEXT:
{json.dumps(shared_context, indent=2)}

Extract data that will be useful for the remaining workflow steps. 
Focus on identifiers, relationships, and context that future steps might need.

Respond with JSON only.
"""
            logger.info("✅ Extraction prompt built successfully")
            return prompt
            
        except Exception as e:
            logger.error(f"❌ Error building extraction prompt: {str(e)}")
            logger.error(traceback.format_exc())
            raise

    def _fallback_extraction(self, step_result: StepResult) -> Dict[str, Any]:
        """Simple fallback extraction when LLM fails with logging"""
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        logger.warning(f"⚠️ Using fallback extraction for step {step_result['step_index']}")
        logger.info(f"🔧 Tool: {step_result['tool'].value}")
        
        try:
            extracted = {
                "extracted_data": {},
                "for_future_steps": {},
                "context_updates": {}
            }
            
            # Basic extraction based on tool type
            if step_result['tool'].value == "gmail_tool":
                logger.info("📧 Processing Gmail tool fallback extraction")
                if "data" in step_result['raw_output'] and "emails" in step_result['raw_output']["data"]:
                    emails = step_result['raw_output']["data"]["emails"]
                    if emails:
                        email_addresses = [email.get("from", "") for email in emails if email.get("from")]
                        extracted["extracted_data"]["email_addresses"] = email_addresses
                        logger.info(f"📧 Extracted {len(email_addresses)} email addresses")
            
            elif step_result['tool'].value == "calendar_tool":
                logger.info("📅 Processing Calendar tool fallback extraction")
                if "data" in step_result['raw_output']:
                    data = step_result['raw_output']["data"]
                    if "meet_link" in data:
                        extracted["extracted_data"]["meeting_link"] = data["meet_link"]
                        logger.info("🔗 Extracted meeting link")
                    if "event_id" in data:
                        extracted["extracted_data"]["event_id"] = data["event_id"]
                        logger.info("📅 Extracted event ID")
            
            elif step_result['tool'].value == "drive_tool":
                logger.info("📁 Processing Drive tool fallback extraction")
                if "data" in step_result['raw_output']:
                    data = step_result['raw_output']["data"]
                    if "file_id" in data:
                        extracted["extracted_data"]["file_id"] = data["file_id"]
                        logger.info("📁 Extracted file ID")
                    if "web_view_link" in data:
                        extracted["extracted_data"]["share_link"] = data["web_view_link"]
                        logger.info("🔗 Extracted share link")
            
            logger.info(f"✅ Fallback extraction completed for step {step_result['step_index']}")
            logger.info(f"📊 Fallback extracted data: {list(extracted['extracted_data'].keys())}")
            
            return extracted
            
        except Exception as e:
            logger.error(f"❌ Error in fallback extraction: {str(e)}")
            logger.error(traceback.format_exc())
            # Return empty structure if even fallback fails
            return {
                "extracted_data": {},
                "for_future_steps": {},
                "context_updates": {}
            }
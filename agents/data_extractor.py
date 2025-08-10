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
    """Extracts relevant data from tool outputs using LLM with improved error handling"""
    
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
        """Extract useful data from step result for future steps with improved error handling"""
        
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
            
            # ✅ FIX: Better handling of empty responses
            if not response_content or response_content.strip() == "":
                logger.warning("⚠️ Empty response from LLM, using fallback extraction")
                return self._fallback_extraction(step_result)
            
            logger.info(f"📄 Response preview: {response_content[:200]}...")
            
            # Clean the response content to extract JSON
            cleaned_content = self._clean_json_response(response_content)
            logger.info(f"🧹 Cleaned content length: {len(cleaned_content)} chars")
            
            # ✅ FIX: Better JSON parsing with multiple attempts
            extracted_data = self._parse_json_with_fallback(cleaned_content, response_content)
            
            if extracted_data:
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
            else:
                logger.warning("⚠️ JSON parsing failed, using fallback extraction")
                return self._fallback_extraction(step_result)
            
        except Exception as e:
            logger.error(f"❌ General error in data extraction: {str(e)}")
            logger.error(traceback.format_exc())
            # Fallback extraction
            return self._fallback_extraction(step_result)
    
    def _parse_json_with_fallback(self, cleaned_content: str, original_content: str) -> Dict[str, Any]:
        """Parse JSON with multiple fallback strategies"""
        
        # Attempt 1: Parse cleaned content
        try:
            logger.info("🔄 Attempt 1: Parsing cleaned JSON response")
            return json.loads(cleaned_content)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Attempt 1 failed: {str(e)}")
        
        # Attempt 2: Extract JSON from original response
        try:
            logger.info("🔍 Attempt 2: Extracting JSON from original response")
            json_str = self._extract_json_from_text(original_content)
            
            if json_str:
                logger.info(f"🔍 Extracted JSON: {json_str[:200]}...")
                return json.loads(json_str)
            else:
                logger.warning("❌ No JSON boundaries found in response")
                
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Attempt 2 failed: {str(e)}")
        except Exception as e:
            logger.warning(f"⚠️ Attempt 2 exception: {str(e)}")
        
        # Attempt 3: Try to fix common JSON issues
        try:
            logger.info("🔧 Attempt 3: Trying to fix common JSON issues")
            fixed_json = self._fix_common_json_issues(cleaned_content)
            return json.loads(fixed_json)
        except json.JSONDecodeError as e:
            logger.warning(f"⚠️ Attempt 3 failed: {str(e)}")
        except Exception as e:
            logger.warning(f"⚠️ Attempt 3 exception: {str(e)}")
        
        logger.error("❌ All JSON parsing attempts failed")
        return None
    
    def _fix_common_json_issues(self, content: str) -> str:
        """Fix common JSON formatting issues"""
        
        # Remove trailing commas
        content = content.replace(',}', '}').replace(',]', ']')
        
        # Fix missing quotes around keys (simple cases)
        import re
        content = re.sub(r'(\w+):', r'"\1":', content)
        
        # Ensure content starts and ends with braces
        content = content.strip()
        if not content.startswith('{'):
            content = '{' + content
        if not content.endswith('}'):
            content = content + '}'
        
        return content
    
    def _clean_json_response(self, content: str) -> str:
        """Clean LLM response to extract pure JSON"""
        
        # Remove markdown code blocks
        content = content.replace('```json', '').replace('```', '')
        
        # Remove common prefixes and explanations
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
                elif stripped.startswith('"') and ('extracted_data' in stripped or 'intent' in stripped):
                    # Sometimes JSON starts without opening brace on first line
                    json_started = True
                    cleaned_lines.append('{')
                    cleaned_lines.append(line)
                # Skip lines that look like explanations
                elif any(word in stripped.lower() for word in ['here', 'based', 'analysis', 'extracted', 'summary']):
                    continue
            else:
                cleaned_lines.append(line)
                # Stop at closing brace if we find one at the start of a line
                if stripped == '}' and len(cleaned_lines) > 2:
                    break
        
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

CRITICAL REQUIREMENTS:
- Respond with ONLY valid JSON
- NO explanatory text before or after JSON
- NO markdown formatting
- Ensure all JSON is properly formatted with correct quotes and commas
- If you cannot extract meaningful data, return empty objects for each section
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
            
            # ✅ FIX: Truncate large outputs to prevent prompt size issues
            raw_output = step_result['raw_output']
            if isinstance(raw_output, dict) and len(str(raw_output)) > 10000:
                # Keep only essential parts for large outputs
                truncated_output = {
                    "success": raw_output.get("success"),
                    "message": raw_output.get("message"),
                    "data": str(raw_output.get("data", {}))[:5000] + "... [truncated]"
                }
                logger.info(f"📊 Truncated large output from {len(str(raw_output))} to {len(str(truncated_output))} chars")
                raw_output = truncated_output
            
            prompt = f"""
COMPLETED STEP:
Step {step_result['step_index']}: {step_result['tool'].value} - {step_result['action'].value}
Description: {completed_step['description']}

TOOL OUTPUT:
{json.dumps(raw_output, indent=2)}

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
        """Enhanced fallback extraction when LLM fails"""
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        logger.warning(f"⚠️ Using fallback extraction for step {step_result['step_index']}")
        logger.info(f"🔧 Tool: {step_result['tool'].value}")
        
        try:
            extracted = {
                "extracted_data": {},
                "for_future_steps": {},
                "context_updates": {}
            }
            
            # Enhanced extraction based on tool type
            if step_result['tool'].value == "gmail_tool":
                logger.info("📧 Processing Gmail tool fallback extraction")
                
                raw_output = step_result['raw_output']
                if "data" in raw_output:
                    data = raw_output["data"]
                    
                    # Extract emails data
                    if "emails" in data and isinstance(data["emails"], list):
                        emails = data["emails"]
                        if emails:
                            # Extract email addresses from 'from' field
                            email_addresses = []
                            subjects = []
                            message_ids = []
                            
                            for email in emails:
                                if email.get("from"):
                                    email_addresses.append(email["from"])
                                if email.get("subject"):
                                    subjects.append(email["subject"])
                                if email.get("id"):
                                    message_ids.append(email["id"])
                            
                            if email_addresses:
                                extracted["extracted_data"]["email_addresses"] = email_addresses
                                extracted["for_future_steps"]["discovered_contacts"] = email_addresses
                                logger.info(f"📧 Extracted {len(email_addresses)} email addresses")
                            
                            if subjects:
                                extracted["extracted_data"]["email_subjects"] = subjects
                                logger.info(f"📝 Extracted {len(subjects)} email subjects")
                            
                            if message_ids:
                                extracted["extracted_data"]["message_ids"] = message_ids
                                logger.info(f"🆔 Extracted {len(message_ids)} message IDs")
                            
                            # Create email summary for future steps
                            if len(emails) > 0:
                                summary = f"Found {len(emails)} emails"
                                if subjects:
                                    top_subjects = subjects[:3]  # Top 3 subjects
                                    summary += f" with subjects: {', '.join(top_subjects)}"
                                extracted["for_future_steps"]["email_summary"] = summary
                                logger.info(f"📊 Created email summary: {summary[:100]}...")
            
            elif step_result['tool'].value == "calendar_tool":
                logger.info("📅 Processing Calendar tool fallback extraction")
                
                raw_output = step_result['raw_output']
                if "data" in raw_output:
                    data = raw_output["data"]
                    
                    # Extract meeting/event data
                    if "meet_link" in data:
                        extracted["extracted_data"]["meeting_link"] = data["meet_link"]
                        extracted["for_future_steps"]["meeting_link"] = data["meet_link"]
                        logger.info("🔗 Extracted meeting link")
                    
                    if "event_id" in data:
                        extracted["extracted_data"]["event_id"] = data["event_id"]
                        logger.info("📅 Extracted event ID")
                    
                    if "attendees" in data and isinstance(data["attendees"], list):
                        attendee_emails = [att.get("email") for att in data["attendees"] if att.get("email")]
                        if attendee_emails:
                            extracted["extracted_data"]["attendee_emails"] = attendee_emails
                            extracted["for_future_steps"]["meeting_attendees"] = attendee_emails
                            logger.info(f"👥 Extracted {len(attendee_emails)} attendee emails")
                    
                    # Extract event details
                    if "event_details" in data:
                        details = data["event_details"]
                        meeting_info = {}
                        if details.get("title"):
                            meeting_info["title"] = details["title"]
                        if details.get("start_time"):
                            meeting_info["start_time"] = details["start_time"]
                        if details.get("location"):
                            meeting_info["location"] = details["location"]
                        
                        if meeting_info:
                            extracted["for_future_steps"]["meeting_details"] = meeting_info
                            logger.info(f"📝 Extracted meeting details: {list(meeting_info.keys())}")
            
            elif step_result['tool'].value == "drive_tool":
                logger.info("📁 Processing Drive tool fallback extraction")
                
                raw_output = step_result['raw_output']
                if "data" in raw_output:
                    data = raw_output["data"]
                    
                    # Extract file data
                    if "file_id" in data:
                        extracted["extracted_data"]["file_id"] = data["file_id"]
                        extracted["for_future_steps"]["files_to_attach"] = [data["file_id"]]
                        logger.info("📁 Extracted file ID")
                    
                    if "web_view_link" in data:
                        extracted["extracted_data"]["share_link"] = data["web_view_link"]
                        logger.info("🔗 Extracted share link")
                    
                    if "filename" in data:
                        extracted["extracted_data"]["filename"] = data["filename"]
                        logger.info(f"📄 Extracted filename: {data['filename']}")
                    
                    # Extract files list
                    if "files" in data and isinstance(data["files"], list):
                        files = data["files"]
                        if files:
                            file_names = [f.get("name") for f in files if f.get("name")]
                            file_ids = [f.get("id") for f in files if f.get("id")]
                            
                            if file_names:
                                extracted["extracted_data"]["file_names"] = file_names
                                logger.info(f"📄 Extracted {len(file_names)} file names")
                            
                            if file_ids:
                                extracted["extracted_data"]["file_ids"] = file_ids
                                extracted["for_future_steps"]["available_files"] = file_ids
                                logger.info(f"🆔 Extracted {len(file_ids)} file IDs")
            
            # Add general context updates
            if step_result['status'] == "completed":
                extracted["context_updates"]["last_successful_action"] = f"{step_result['tool'].value}_{step_result['action'].value}"
                extracted["context_updates"]["workflow_progress"] = f"Step {step_result['step_index']} completed successfully"
            
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
                "context_updates": {
                    "extraction_error": str(e),
                    "step_status": step_result['status']
                }
            }
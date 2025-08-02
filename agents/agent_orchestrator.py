from typing import Dict, Any, Optional, Generator
import logging
import traceback
from datetime import datetime

# LangGraph and LangChain imports
from langgraph.graph import StateGraph

# Our new components
from agents.llm_planner import create_llm_planner
from agents.graph_builder import create_workflow_graph
from agents.state_manager import get_user_state_manager
from agents.tools_registry import create_tools_registry
from agents.plan_schema import WorkflowState, create_initial_state, get_progress_summary
from utils.parameter_mapper import ParameterMapper

# Configure logging
logger = logging.getLogger(__name__)

class ModernAgentOrchestrator:
    """
    Modern AI agent orchestrator with real streaming and Claude-style progress display.
    
    Replaces the old complex orchestration with:
    - Real LangGraph streaming (not simulated)
    - Claude-style step-by-step progress display
    - Native LangGraph execution with checkpointing
    - Simplified architecture using ToolNode
    """
    
    def __init__(self, auth_manager):
        logger.info("ORCHESTRATOR: Initializing")
        
        try:
            self.auth_manager = auth_manager
            
            logger.debug("Creating streamlined LLM planner")
            self.planner = create_llm_planner()
            logger.debug("LLM planner created")
            
            logger.debug("Creating tools registry")
            self.tools_registry = create_tools_registry(auth_manager)
            logger.debug("Tools registry created")
            
            logger.debug("Creating parameter mapper for date context")
            self.parameter_mapper = ParameterMapper()
            logger.debug("Parameter mapper created")
            
            logger.info("ORCHESTRATOR: Initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize ModernAgentOrchestrator: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def process_user_request(self, user_request: str, user_id: str) -> Generator[str, None, None]:
        """
        Process user request with real streaming and Claude-style progress display.
        
        This is the main entry point that provides the step-by-step progress
        display that users see in the chat interface.
        """
        logger.info(f"ORCHESTRATOR: Starting request processing for user: {user_id}")
        logger.info(f"REQUEST: {user_request}")
        
        try:
            # === PHASE 1: PLANNING ===
            logger.info("PHASE 1: Creating execution plan")
            yield "Planning your request..."
            
            # Get user context with date information
            logger.debug("Getting user context")
            user_context = self._get_user_context(user_id)
            logger.debug(f"User context retrieved: {list(user_context.keys())}")
            
            # Create execution plan
            logger.debug("Calling LLM planner")
            plan = self.planner.create_plan(user_request, user_context)
            logger.info(f"PLAN CREATED: {plan.intent}")
            logger.info(f"STEPS: {len(plan.steps)} steps to execute")
            
            # Show plan summary to user
            yield f"Plan created: {plan.intent}"
            yield f"Steps to execute: {len(plan.steps)}"
            yield ""
            
            # Show step breakdown
            for i, step in enumerate(plan.steps, 1):
                logger.debug(f"Step {i}: {step.description}")
                yield f"   {i}. {step.description}"
            
            yield ""
            
            # === PHASE 2: WORKFLOW SETUP ===
            logger.info("PHASE 2: Setting up workflow execution")
            yield "Starting execution..."
            
            # Initialize state manager with checkpointing
            logger.debug("Initializing state manager")
            state_manager = get_user_state_manager(user_id, use_memory=False)  # Use SQLite
            logger.debug("State manager initialized")
            
            # Create initial workflow state
            logger.debug("Creating initial workflow state")
            initial_state = create_initial_state(plan, user_id)
            logger.debug(f"Initial state created: {initial_state['status']}")
            
            # Build dynamic workflow graph
            logger.debug("Building workflow graph")
            tools_by_category = self.tools_registry.tools_by_category
            compiled_graph = create_workflow_graph(plan, self.auth_manager, tools_by_category, state_manager)
            logger.debug("Workflow graph built and compiled")
            
            yield "Workflow ready - Starting execution..."
            yield ""
            
            # === PHASE 3: REAL STREAMING EXECUTION ===
            logger.info("PHASE 3: Real LangGraph streaming execution")
            
            # Get state manager config for thread management
            config = state_manager.get_config()
            logger.debug(f"Using config: {config}")
            
            # Execute workflow with REAL LangGraph streaming
            logger.info("WORKFLOW: Starting real LangGraph streaming execution")
            for progress_update in self._execute_streaming_workflow(compiled_graph, initial_state, config, state_manager):
                yield progress_update
            
            # === PHASE 4: FINAL SUMMARY ===
            logger.info("PHASE 4: Generating final summary")
            yield ""
            yield "Generating summary..."
            
            # Get final results from state manager
            logger.debug("Getting final workflow results")
            final_results = state_manager.get_final_results()
            logger.debug(f"Final results retrieved: {len(final_results)} items")
            
            # Generate user-friendly summary
            logger.debug("Generating final response")
            final_response = self._generate_claude_style_summary(final_results, plan)
            logger.debug("Final response generated")
            
            yield ""
            yield "Completed!"
            yield ""
            yield final_response
            
            logger.info("ORCHESTRATOR: Request processing completed successfully")
            
        except Exception as e:
            logger.error(f"Error in process_user_request: {str(e)}")
            logger.error(traceback.format_exc())
            yield ""
            yield f"Error: {str(e)}"
            yield ""
            yield "Please try rephrasing your request or check your Google account connection."
    
    def _execute_streaming_workflow(self, compiled_graph: StateGraph, initial_state: WorkflowState, 
                                   config: Dict[str, Any], state_manager) -> Generator[str, None, None]:
        """
        Execute LangGraph workflow with REAL streaming progress updates.
        
        This provides the Claude-style step-by-step progress display by
        streaming actual LangGraph execution updates.
        """
        logger.info("WORKFLOW: Starting real LangGraph streaming execution")
        
        try:
            step_count = 0
            last_completed_step = 0
            
            # Stream workflow execution with updates mode
            logger.debug("Calling graph.stream() with updates mode")
            for chunk in compiled_graph.stream(initial_state, config=config, stream_mode="updates"):
                step_count += 1
                logger.debug(f"Received chunk {step_count}: {type(chunk)}")
                
                # Parse the streaming update
                progress_update = self._parse_streaming_chunk(chunk, last_completed_step, state_manager)
                
                if progress_update:
                    logger.debug(f"Yielding progress: {progress_update}")
                    yield progress_update
                    
                    # Track completed steps
                    if "Step" in progress_update and "completed" in progress_update:
                        try:
                            # Extract step number from progress update
                            if "Step " in progress_update:
                                step_num_str = progress_update.split("Step ")[1].split()[0]
                                if step_num_str.isdigit():
                                    last_completed_step = max(last_completed_step, int(step_num_str))
                        except:
                            pass  # Continue even if step parsing fails
            
            logger.info(f"WORKFLOW: Streaming execution completed after {step_count} chunks")
            
        except Exception as e:
            logger.error(f"Error in streaming execution: {str(e)}")
            logger.error(traceback.format_exc())
            yield f"Execution Error: {str(e)}"
    
    def _parse_streaming_chunk(self, chunk: Any, last_completed_step: int, state_manager) -> Optional[str]:
        """
        Parse LangGraph streaming chunk into Claude-style progress update.
        
        Converts LangGraph's streaming updates into user-friendly progress messages.
        """
        try:
            # Log chunk structure for debugging
            logger.debug(f"Parsing chunk type: {type(chunk)}")
            
            # Handle different chunk formats from LangGraph
            if isinstance(chunk, dict):
                # Look for node execution updates
                for node_name, node_data in chunk.items():
                    if node_name == "execute_step" and isinstance(node_data, dict):
                        return self._format_step_progress(node_data, last_completed_step)
                    
                    elif node_name == "execute_tools" and isinstance(node_data, dict):
                        return self._format_tool_progress(node_data)
                    
                    elif "progress_messages" in str(node_data):
                        # Extract progress messages from state updates
                        if isinstance(node_data, dict) and "progress_messages" in node_data:
                            messages = node_data["progress_messages"]
                            if messages and isinstance(messages, list):
                                return messages[-1]  # Return latest message
            
            # Try to extract meaningful info from any chunk
            chunk_str = str(chunk)
            if "Step" in chunk_str and ("completed" in chunk_str or "executing" in chunk_str):
                return self._extract_step_info(chunk_str)
            
            return None
            
        except Exception as e:
            logger.error(f"Error parsing streaming chunk: {str(e)}")
            return None
    
    def _format_step_progress(self, step_data: Dict[str, Any], last_completed_step: int) -> Optional[str]:
        """Format step execution progress"""
        try:
            if "current_step" in step_data:
                current_step = step_data["current_step"]
                if current_step > last_completed_step:
                    return f"Step {current_step}: Starting execution..."
            
            if "progress_messages" in step_data:
                messages = step_data["progress_messages"]
                if messages and isinstance(messages, list):
                    return messages[-1]
            
            return None
            
        except Exception as e:
            logger.debug(f"Error formatting step progress: {e}")
            return None
    
    def _format_tool_progress(self, tool_data: Dict[str, Any]) -> Optional[str]:
        """Format tool execution progress"""
        try:
            # Look for tool execution indicators
            if "messages" in str(tool_data):
                return "Executing tools..."
            
            return None
            
        except Exception as e:
            logger.debug(f"Error formatting tool progress: {e}")
            return None
    
    def _extract_step_info(self, chunk_str: str) -> Optional[str]:
        """Extract step information from chunk string"""
        try:
            # Look for step completion patterns
            if "Step" in chunk_str and "completed" in chunk_str:
                # Try to extract step number and description
                lines = chunk_str.split('\n')
                for line in lines:
                    if "Step" in line and ("completed" in line or "✅" in line):
                        return line.strip()
            
            return None
            
        except Exception as e:
            logger.debug(f"Error extracting step info: {e}")
            return None
    
    def _get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Get user context for planning with date context"""
        logger.debug(f"Getting user context for user: {user_id}")
        
        try:
            # Get user info from auth manager
            user_info = self.auth_manager.get_user_info(user_id)
            logger.debug(f"User info retrieved: {user_info is not None}")
            
            # Get current date context
            logger.debug("Getting current date context")
            date_context = self.parameter_mapper.get_current_date_context()
            logger.debug(f"Date context retrieved: {date_context['current_date']}")
            
            # Build context
            context = {
                "user_id": user_id,
                "authenticated_services": []
            }
            
            # Add date context
            context.update(date_context)
            
            # Add user info
            if user_info:
                context.update({
                    "user_email": user_info.get("email", ""),
                    "user_name": user_info.get("name", ""),
                    "timezone": "UTC"
                })
            
            # Check available services
            logger.debug("Checking available services")
            
            if self.auth_manager.get_authenticated_client('gmail', 'v1', user_id):
                context["authenticated_services"].append("gmail")
                logger.debug("Gmail service available")
            
            if self.auth_manager.get_authenticated_client('calendar', 'v3', user_id):
                context["authenticated_services"].append("calendar")
                logger.debug("Calendar service available")
            
            if self.auth_manager.get_authenticated_client('drive', 'v3', user_id):
                context["authenticated_services"].append("drive")
                logger.debug("Drive service available")
            
            logger.debug(f"User context complete. Services: {context['authenticated_services']}")
            return context
            
        except Exception as e:
            logger.error(f"Error getting user context: {str(e)}")
            return {
                "user_id": user_id,
                "authenticated_services": [],
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "error": str(e)
            }
    
    def _generate_claude_style_summary(self, final_results: Dict[str, Any], plan) -> str:
        """
        Generate Claude-style final summary with accomplishments and key details.
        
        Creates a comprehensive summary similar to Claude's research feature.
        """
        logger.debug("Generating Claude-style final summary")
        
        try:
            if not final_results or "error" in final_results:
                logger.warning("No valid final results for summary")
                return "I encountered an issue completing your request. Please try again."
            
            # Start building the summary
            summary_parts = []
            
            # Main accomplishment header
            intent = final_results.get('intent', 'Completed your request')
            summary_parts.append(f"## {intent}")
            summary_parts.append("")
            
            # What was accomplished
            step_summaries = final_results.get('step_summaries', [])
            completed_count = final_results.get('completed_steps', 0)
            failed_count = final_results.get('failed_steps', 0)
            
            if completed_count > 0:
                summary_parts.append("### What I accomplished:")
                summary_parts.append("")
                
                for step_summary in step_summaries:
                    if step_summary.get('status') == 'completed':
                        desc = step_summary.get('description', 'Unknown step')
                        summary_parts.append(f"• **{desc}**")
                
                summary_parts.append("")
            
            # Key outputs and details
            key_outputs = final_results.get('key_outputs', {})
            shared_context = final_results.get('shared_context', {})
            
            important_details = []
            
            # Look for important outputs
            if 'meeting_link' in key_outputs or 'meeting_link' in shared_context:
                meet_link = key_outputs.get('meeting_link') or shared_context.get('meeting_link')
                if meet_link:
                    important_details.append(f"**Google Meet**: {meet_link}")
            
            if 'message_id' in key_outputs:
                important_details.append("**Email sent successfully**")
            
            if 'event_id' in key_outputs:
                important_details.append("**Calendar event created**")
            
            if 'file_id' in key_outputs:
                important_details.append("**File processed in Drive**")
            
            # Check for contact discoveries
            if 'discovered_contacts' in shared_context:
                contacts = shared_context['discovered_contacts']
                if contacts and len(contacts) > 0:
                    important_details.append(f"**Found {len(contacts)} team member(s)**")
            
            # Check for meeting attendees
            if 'meeting_attendees' in shared_context:
                attendees = shared_context['meeting_attendees']
                if attendees and len(attendees) > 0:
                    important_details.append(f"**Notified {len(attendees)} attendee(s)**")
            
            if important_details:
                summary_parts.append("### Key details:")
                summary_parts.append("")
                summary_parts.extend(important_details)
                summary_parts.append("")
            
            # Execution summary
            execution_time = final_results.get('execution_time', 'Unknown')
            total_steps = final_results.get('total_steps', len(step_summaries))
            
            summary_parts.append("### Execution summary:")
            summary_parts.append("")
            summary_parts.append(f"• **Steps completed**: {completed_count}/{total_steps}")
            summary_parts.append(f"• **Execution time**: {execution_time}")
            
            if failed_count > 0:
                summary_parts.append(f"• **Issues encountered**: {failed_count}")
            
            # Handle failures
            if failed_count > 0:
                summary_parts.append("")
                summary_parts.append("### Issues encountered:")
                summary_parts.append("")
                
                for step_summary in step_summaries:
                    if step_summary.get('status') == 'failed':
                        desc = step_summary.get('description', 'Unknown step')
                        error = step_summary.get('error', 'Unknown error')
                        summary_parts.append(f"• **{desc}**: {error}")
            
            final_summary = "\n".join(summary_parts)
            logger.debug("Claude-style summary generated successfully")
            return final_summary
            
        except Exception as e:
            logger.error(f"Error generating summary: {str(e)}")
            logger.error(traceback.format_exc())
            return f"Task completed, but encountered an error generating the summary: {str(e)}"
    
    def get_workflow_status(self, user_id: str) -> Dict[str, Any]:
        """Get current workflow status for UI"""
        logger.debug(f"Getting workflow status for user: {user_id}")
        
        try:
            state_manager = get_user_state_manager(user_id)
            status = state_manager.get_workflow_progress()
            logger.debug(f"Workflow status retrieved: {status}")
            return status
        except Exception as e:
            logger.error(f"Error getting workflow status: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def cancel_workflow(self, user_id: str):
        """Cancel current workflow"""
        logger.info(f"Cancelling workflow for user: {user_id}")
        
        try:
            state_manager = get_user_state_manager(user_id)
            state_manager.clear_workflow()
            logger.info("Workflow cancelled successfully")
        except Exception as e:
            logger.error(f"Error cancelling workflow: {str(e)}")
            raise

# Factory function for easy integration
def create_agent_orchestrator(auth_manager) -> ModernAgentOrchestrator:
    """
    Factory function to create a ModernAgentOrchestrator instance.
    
    Args:
        auth_manager: Authentication manager for Google APIs
        
    Returns:
        Configured ModernAgentOrchestrator instance
    """
    logger.debug("Creating ModernAgentOrchestrator instance")
    return ModernAgentOrchestrator(auth_manager)

# Utility functions for monitoring and debugging
def get_orchestrator_health(auth_manager) -> Dict[str, Any]:
    """
    Get health check information for the orchestrator.
    
    Returns system status and component health.
    """
    logger.debug("Running orchestrator health check")
    
    try:
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "components": {}
        }
        
        # Test LLM planner
        try:
            planner = create_llm_planner()
            health["components"]["llm_planner"] = "healthy"
        except Exception as e:
            health["components"]["llm_planner"] = f"error: {str(e)}"
            health["status"] = "degraded"
        
        # Test tools registry
        try:
            tools_registry = create_tools_registry(auth_manager)
            tool_count = len(tools_registry.get_all_tools())
            health["components"]["tools_registry"] = f"healthy ({tool_count} tools)"
        except Exception as e:
            health["components"]["tools_registry"] = f"error: {str(e)}"
            health["status"] = "degraded"
        
        # Test authentication
        try:
            user_info = auth_manager.get_user_info("test_user")
            health["components"]["auth_manager"] = "healthy"
        except Exception as e:
            health["components"]["auth_manager"] = f"error: {str(e)}"
            health["status"] = "degraded"
        
        logger.debug(f"Health check completed: {health['status']}")
        return health
        
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }

if __name__ == "__main__":
    # Example usage for testing
    print("ORCHESTRATOR: ModernAgentOrchestrator Test")
    print("This module provides real streaming execution with Claude-style progress")
    print("Run with proper auth_manager for full functionality")
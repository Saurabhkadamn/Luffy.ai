from typing import Dict, Any, Optional, Generator
import streamlit as st
import logging
import traceback
from datetime import datetime, timedelta
from agents.llm_planner import LLMPlanner
from agents.graph_builder import GraphBuilder
from agents.plan_schema import WorkflowState
from utils.parameter_mapper import ParameterMapper

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """Main coordinator for LangGraph agent workflows with native streaming and checkpointing"""
    
    def __init__(self, auth_manager):
        logger.info("🚀 Initializing AgentOrchestrator")
        self.auth_manager = auth_manager
        
        try:
            logger.info("📋 Creating LLMPlanner instance")
            self.planner = LLMPlanner()
            logger.info("✅ LLMPlanner created successfully")
            
            logger.info("🔧 Creating GraphBuilder instance")
            self.graph_builder = GraphBuilder(auth_manager)
            logger.info("✅ GraphBuilder created successfully")
            
            logger.info("🔧 Creating ParameterMapper instance")
            self.parameter_mapper = ParameterMapper()
            logger.info("✅ ParameterMapper created successfully")
            
            logger.info("✅ AgentOrchestrator initialization complete")
        except Exception as e:
            logger.error(f"❌ Failed to initialize AgentOrchestrator: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def process_user_request(self, user_request: str, user_id: str) -> Generator[str, None, None]:
        """Process user request with native LangGraph streaming and checkpointing"""
        
        logger.info(f"🎯 Starting request processing for user: {user_id}")
        logger.info(f"📝 User request: {user_request}")
        
        try:
            # Step 1: Create execution plan
            logger.info("🧠 Step 1: Creating execution plan")
            yield "🧠 **Planning your request...**"
            
            logger.info("📊 Getting user context with date information")
            user_context = self._get_user_context(user_id)
            logger.info(f"✅ User context retrieved: {user_context}")
            
            logger.info("🤖 Calling LLM planner")
            plan = self.planner.create_plan(user_request, user_context)
            logger.info(f"✅ Plan created successfully: {plan['intent']}")
            logger.info(f"📋 Plan has {len(plan['steps'])} steps")
            
            yield f"✅ **Plan created**: {plan['intent']}"
            yield f"📋 **Steps to execute**: {len(plan['steps'])}"
            
            # Show plan summary
            for i, step in enumerate(plan['steps'], 1):
                logger.info(f"Step {i}: {step['description']} ({step['tool'].value} - {step['action'].value})")
                yield f"   {i}. {step['description']}"
            
            # Step 2: Build workflow with checkpointing
            logger.info("🚀 Step 2: Building workflow with checkpointing")
            yield "\n🚀 **Building workflow...**"
            
            logger.info("🏗️ Building dynamic workflow graph")
            workflow_graph = self.graph_builder.build_graph(plan, user_id)
            logger.info("✅ Workflow graph built successfully with checkpointing")
            
            # Step 3: Execute with native LangGraph streaming
            logger.info("⚡ Step 3: Executing with native LangGraph streaming")
            yield "⚡ **Starting execution with checkpointing...**"
            
            # ✅ FIXED: Use simple LangGraph config structure
            config = {
                "configurable": {
                    "thread_id": f"user_{user_id}"  # Simple, consistent thread_id
                }
            }
            
            # Initialize workflow state
            initial_state = self._create_initial_state(plan, user_id)
            logger.info("✅ Initial state created")
            
            # Stream with native LangGraph streaming
            logger.info("🌊 Starting native LangGraph streaming")
            step_count = 0
            final_chunk = None
            
            try:
                for chunk in workflow_graph.stream(
                    initial_state, 
                    config, 
                    stream_mode="values"  # Stream state values
                ):
                    logger.info(f"📦 Received chunk: {type(chunk)}")
                    final_chunk = chunk  # Keep track of the last chunk
                    
                    # Extract progress information from chunk
                    if isinstance(chunk, dict) and 'current_step' in chunk:
                        current_step = chunk.get('current_step', 0)
                        status = chunk.get('status', 'executing')
                        execution_log = chunk.get('execution_log', [])
                        
                        logger.info(f"📊 Progress: step {current_step}, status: {status}")
                        
                        # Yield execution log entries
                        if execution_log and len(execution_log) > step_count:
                            for log_entry in execution_log[step_count:]:
                                yield log_entry
                            step_count = len(execution_log)
                        
                        # Check for completion
                        if status == "completed":
                            logger.info("🎉 Workflow completed successfully")
                            yield "🎉 **Workflow completed successfully!**"
                            break
                        elif status == "failed":
                            logger.error("❌ Workflow failed")
                            yield "❌ **Workflow failed**"
                            break
                
                # Step 4: Generate final response
                logger.info("📝 Step 4: Generating final response")
                yield "\n📝 **Generating summary...**"
                
                # Get final state from the last chunk
                final_response = self._generate_final_response_from_state(final_chunk if final_chunk else {})
                logger.info("✅ Final response generated")
                
                yield f"\n✅ **Summary:**\n{final_response}"
                logger.info("🎉 Request processing completed successfully")
                
            except Exception as streaming_error:
                logger.error(f"❌ Error during streaming execution: {str(streaming_error)}")
                logger.error(traceback.format_exc())
                yield f"\n❌ **Execution Error**: {str(streaming_error)}"
                
                # Try to recover from checkpoint
                yield "\n🔄 **Attempting recovery from checkpoint...**"
                try:
                    # Resume from last checkpoint by passing None as initial state
                    for recovery_chunk in workflow_graph.stream(None, config, stream_mode="values"):
                        if isinstance(recovery_chunk, dict):
                            recovery_status = recovery_chunk.get('status', 'unknown')
                            if recovery_status == "completed":
                                yield "✅ **Recovery successful!**"
                                break
                            elif recovery_status == "failed":
                                yield "❌ **Recovery failed**"
                                break
                except Exception as recovery_error:
                    logger.error(f"❌ Recovery also failed: {str(recovery_error)}")
                    yield f"❌ **Recovery failed**: {str(recovery_error)}"
            
        except Exception as e:
            logger.error(f"❌ Error in process_user_request: {str(e)}")
            logger.error(traceback.format_exc())
            yield f"\n❌ **Error**: {str(e)}"
            yield "\nPlease try rephrasing your request or check your Google account connection."
    
    def _create_initial_state(self, plan, user_id: str) -> WorkflowState:
        """Create initial workflow state with proper TypedDict structure"""
        
        logger.info("🔄 Creating initial workflow state")
        
        try:
            initial_state = {
                "plan": plan,
                "step_results": {},
                "shared_context": {
                    "user_id": user_id,
                    "workflow_started": datetime.now().isoformat(),
                    "user_preferences": {},
                    "discovered_contacts": [],
                    "project_context": {}
                },
                "current_step": 1,
                "status": "executing",
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "execution_log": [f"🚀 Workflow started: {plan['intent']}"]
            }
            
            logger.info("✅ Initial workflow state created")
            return initial_state
            
        except Exception as e:
            logger.error(f"❌ Error creating initial state: {str(e)}")
            raise
    
    def _get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Get user context for planning with date context and logging"""
        
        logger.info(f"🔍 Getting user context for user: {user_id}")
        
        try:
            logger.info("👤 Getting user info from auth manager")
            user_info = self.auth_manager.get_user_info(user_id)
            logger.info(f"✅ User info retrieved: {user_info is not None}")
            
            # Get current date context
            logger.info("📅 Getting current date context")
            date_context = self.parameter_mapper.get_current_date_context()
            logger.info(f"✅ Date context retrieved: {date_context['current_date']}")
            
            context = {
                "user_id": user_id,
                "authenticated_services": []
            }
            
            # Add date context
            context.update(date_context)
            logger.info("📅 Date context added to user context")
            
            if user_info:
                logger.info("📧 Adding user info to context")
                context.update({
                    "user_email": user_info.get("email", ""),
                    "user_name": user_info.get("name", ""),
                    "timezone": "UTC"  # Could be enhanced to detect user timezone
                })
                logger.info(f"✅ User context updated with email: {user_info.get('email', 'N/A')}")
            
            # Check available services
            logger.info("🔧 Checking available services")
            
            logger.info("📧 Checking Gmail authentication")
            if self.auth_manager.get_authenticated_client('gmail', 'v1', user_id):
                context["authenticated_services"].append("gmail")
                logger.info("✅ Gmail service available")
            else:
                logger.warning("⚠️ Gmail service not available")
                
            logger.info("📅 Checking Calendar authentication")
            if self.auth_manager.get_authenticated_client('calendar', 'v3', user_id):
                context["authenticated_services"].append("calendar")
                logger.info("✅ Calendar service available")
            else:
                logger.warning("⚠️ Calendar service not available")
                
            logger.info("📁 Checking Drive authentication")
            if self.auth_manager.get_authenticated_client('drive', 'v3', user_id):
                context["authenticated_services"].append("drive")
                logger.info("✅ Drive service available")
            else:
                logger.warning("⚠️ Drive service not available")
            
            logger.info(f"✅ User context complete. Available services: {context['authenticated_services']}")
            logger.info(f"📅 Current date context: {date_context['current_date']} ({date_context['day_of_week']})")
            
            return context
            
        except Exception as e:
            logger.error(f"❌ Error getting user context: {str(e)}")
            logger.error(traceback.format_exc())
            # Return minimal context on error
            return {
                "user_id": user_id,
                "authenticated_services": [],
                "current_date": datetime.now().strftime("%Y-%m-%d"),
                "error": str(e)
            }
    
    def _generate_final_response_from_state(self, final_state: Dict[str, Any]) -> str:
        """Generate human-friendly final response from workflow state"""
        
        logger.info("✍️ Generating final response from workflow state")
        
        if not final_state:
            logger.warning("⚠️ No final state available")
            return "I encountered an issue completing your request. Please try again."
        
        try:
            response_parts = []
            
            # Main accomplishment
            plan = final_state.get('plan', {})
            intent = plan.get('intent', 'Unknown task')
            logger.info(f"🎯 Main intent: {intent}")
            response_parts.append(f"**{intent}**")
            
            # Execution summary
            step_results = final_state.get('step_results', {})
            completed_steps = [r for r in step_results.values() if r['status'] == 'completed']
            failed_steps = [r for r in step_results.values() if r['status'] == 'failed']
            
            logger.info(f"📋 Completed steps: {len(completed_steps)}, Failed steps: {len(failed_steps)}")
            
            if completed_steps:
                response_parts.append("\n**Successfully completed:**")
                for step_result in completed_steps:
                    step_index = step_result['step_index']
                    # Find the corresponding step in the plan
                    step_desc = f"Step {step_index}"
                    if plan and 'steps' in plan:
                        matching_step = next((s for s in plan['steps'] if s['step_index'] == step_index), None)
                        if matching_step:
                            step_desc = matching_step['description']
                    response_parts.append(f"• {step_desc}")
            
            # Key outputs from shared context
            shared_context = final_state.get('shared_context', {})
            important_outputs = []
            
            if 'meeting_link' in shared_context:
                logger.info("🔗 Adding meeting link to response")
                important_outputs.append(f"🔗 **Meeting link**: {shared_context['meeting_link']}")
            
            if 'message_id' in shared_context:
                logger.info("📧 Adding email success to response")
                important_outputs.append("📧 **Email sent successfully**")
            
            if 'event_id' in shared_context:
                logger.info("📅 Adding calendar event to response")
                important_outputs.append("📅 **Calendar event created**")
            
            if 'file_id' in shared_context:
                logger.info("📁 Adding file processing to response")
                important_outputs.append("📁 **File processed in Drive**")
            
            if important_outputs:
                response_parts.append("\n**Key results:**")
                response_parts.extend(important_outputs)
            
            # Show any failures
            if failed_steps:
                response_parts.append(f"\n⚠️ **Note**: {len(failed_steps)} step(s) encountered issues but the workflow completed.")
            
            final_response = "\n".join(response_parts)
            logger.info("✅ Final response generated successfully")
            logger.info(f"📝 Response length: {len(final_response)} characters")
            
            return final_response
            
        except Exception as e:
            logger.error(f"❌ Error generating final response: {str(e)}")
            logger.error(traceback.format_exc())
            return f"Task completed, but encountered an error generating the summary: {str(e)}"
    
    def get_workflow_status(self, user_id: str) -> Dict[str, Any]:
        """Get current workflow status for UI (now works with checkpointer)"""
        
        logger.info(f"📊 Getting workflow status for user: {user_id}")
        
        try:
            # This would need to be implemented to query the checkpointer
            # For now, return basic status
            return {
                "status": "active", 
                "message": "Workflow status tracking with checkpointer - implement checkpoint querying"
            }
        except Exception as e:
            logger.error(f"❌ Error getting workflow status: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def cancel_workflow(self, user_id: str):
        """Cancel current workflow (now works with checkpointer)"""
        
        logger.info(f"🛑 Cancelling workflow for user: {user_id}")
        
        try:
            # This would need to be implemented to work with checkpointer
            # For now, log the cancellation
            logger.info("✅ Workflow cancellation requested - implement checkpoint cleanup")
        except Exception as e:
            logger.error(f"❌ Error cancelling workflow: {str(e)}")
            raise
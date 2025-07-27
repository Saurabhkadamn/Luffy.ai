from typing import Dict, Any, Optional, Generator
import streamlit as st
import logging
import traceback
from datetime import datetime, timedelta
from agents.llm_planner import LLMPlanner
from agents.graph_builder import GraphBuilder
from agents.state_manager import StateManager
from agents.plan_schema import WorkflowState
from utils.parameter_mapper import ParameterMapper

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """Main coordinator for LangGraph agent workflows with date context and parameter mapping"""
    
    def __init__(self, auth_manager):
        logger.info("🚀 Initializing AgentOrchestrator")
        self.auth_manager = auth_manager
        
        try:
            logger.info("📋 Creating LLMPlanner instance")
            self.planner = LLMPlanner()  # LLM created internally
            logger.info("✅ LLMPlanner created successfully")
            
            logger.info("🔧 Creating GraphBuilder instance")
            self.graph_builder = GraphBuilder(auth_manager)  # No LLM needed here
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
        """Process user request with streaming updates and comprehensive logging"""
        
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
            logger.info(f"✅ Plan created successfully: {plan.intent}")
            logger.info(f"📋 Plan has {len(plan.steps)} steps")
            
            yield f"✅ **Plan created**: {plan.intent}"
            yield f"📋 **Steps to execute**: {len(plan.steps)}"
            
            # Show plan summary
            for i, step in enumerate(plan.steps, 1):
                logger.info(f"Step {i}: {step.description} ({step.tool.value} - {step.action.value})")
                yield f"   {i}. {step.description}"
            
            # Step 2: Build and execute workflow
            logger.info("🚀 Step 2: Starting workflow execution")
            yield "\n🚀 **Starting execution...**"
            
            logger.info("🗃️ Initializing StateManager")
            state_manager = StateManager(user_id)
            logger.info("✅ StateManager initialized")
            
            logger.info("🔄 Initializing workflow state")
            initial_state = state_manager.initialize_workflow(plan)
            logger.info(f"✅ Initial state created: {initial_state.status}")
            
            # Build dynamic graph
            logger.info("🏗️ Building dynamic workflow graph")
            workflow_graph = self.graph_builder.build_graph(plan, user_id)
            logger.info("✅ Workflow graph built successfully")
            
            # Execute workflow with progress updates
            logger.info("⚡ Starting workflow execution with progress tracking")
            for update in self._execute_workflow_with_progress(workflow_graph, initial_state, state_manager):
                yield update
            
            # Step 3: Generate final response
            logger.info("📝 Step 3: Generating final response")
            yield "\n📝 **Generating summary...**"
            
            logger.info("📊 Getting final results")
            final_results = state_manager.get_final_results()
            logger.info(f"✅ Final results retrieved: {len(final_results)} items")
            
            logger.info("✍️ Generating final response")
            final_response = self._generate_final_response(final_results)
            logger.info("✅ Final response generated")
            
            yield f"\n✅ **Completed!**\n\n{final_response}"
            logger.info("🎉 Request processing completed successfully")
            
        except Exception as e:
            logger.error(f"❌ Error in process_user_request: {str(e)}")
            logger.error(traceback.format_exc())
            yield f"\n❌ **Error**: {str(e)}"
            yield "\nPlease try rephrasing your request or check your Google account connection."
    
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
    
    def _execute_workflow_with_progress(self, workflow_graph, initial_state: WorkflowState, 
                                      state_manager: StateManager) -> Generator[str, None, None]:
        """Execute workflow with real-time progress updates and logging"""
        
        logger.info("🔄 Starting workflow execution with progress tracking")
        
        try:
            logger.info("⚡ Invoking workflow graph")
            logger.info(f"📊 Initial state: {initial_state.status}")
            logger.info(f"📋 Total steps to execute: {len(initial_state.plan.steps)}")
            
            # Execute the workflow
            result = workflow_graph.invoke(initial_state)
            logger.info(f"✅ Workflow graph execution completed: {type(result)}")
            
            # Monitor progress and provide updates
            logger.info("👀 Monitoring workflow progress")
            for step_index in range(1, len(initial_state.plan.steps) + 1):
                logger.info(f"🔍 Checking status of step {step_index}")
                
                current_state = state_manager.get_current_state()
                logger.info(f"📊 Current state status: {current_state.status if current_state else 'None'}")
                
                if current_state and step_index in current_state.step_results:
                    step_result = current_state.step_results[step_index]
                    step = current_state.plan.steps[step_index - 1]
                    
                    logger.info(f"📋 Step {step_index} result: {step_result.status}")
                    
                    if step_result.status == "completed":
                        logger.info(f"✅ Step {step_index} completed successfully")
                        yield f"✅ **Step {step_index}**: {step.description}"
                        
                        # Show key outputs
                        if step_result.extracted_data:
                            key_data = step_result.extracted_data
                            logger.info(f"📊 Step {step_index} extracted data: {key_data}")
                            if len(str(key_data)) < 100:  # Only show short summaries
                                yield f"   📊 Key result: {key_data}"
                    
                    elif step_result.status == "failed":
                        logger.error(f"❌ Step {step_index} failed: {step_result.error_message}")
                        yield f"❌ **Step {step_index} failed**: {step_result.error_message}"
                        break
                else:
                    logger.info(f"⏳ Step {step_index} still in progress")
                    yield f"⏳ **Step {step_index}**: In progress..."
            
            logger.info("✅ Workflow progress monitoring completed")
            
        except Exception as e:
            logger.error(f"❌ Workflow execution failed: {str(e)}")
            logger.error(traceback.format_exc())
            yield f"❌ **Workflow execution failed**: {str(e)}"
    
    def _generate_final_response(self, final_results: Dict[str, Any]) -> str:
        """Generate human-friendly final response with logging"""
        
        logger.info("✍️ Generating final response")
        logger.info(f"📊 Final results keys: {list(final_results.keys()) if final_results else 'None'}")
        
        if not final_results:
            logger.warning("⚠️ No final results available")
            return "I encountered an issue completing your request. Please try again."
        
        response_parts = []
        
        try:
            # Main accomplishment
            intent = final_results.get('intent', 'Unknown task')
            logger.info(f"🎯 Main intent: {intent}")
            response_parts.append(f"**{intent}**")
            
            # Step summaries
            step_summaries = final_results.get('step_summaries', [])
            logger.info(f"📋 Step summaries count: {len(step_summaries)}")
            
            if step_summaries:
                response_parts.append("\n**What I accomplished:**")
                
                for step_summary in step_summaries:
                    if step_summary.get('status') == 'completed':
                        logger.info(f"✅ Adding completed step: {step_summary.get('description', 'Unknown')}")
                        response_parts.append(f"• {step_summary['description']}")
            
            # Key outputs
            key_outputs = final_results.get('key_outputs', {})
            logger.info(f"🔑 Key outputs: {list(key_outputs.keys())}")
            important_outputs = []
            
            if 'meeting_link' in key_outputs:
                logger.info("🔗 Adding meeting link to response")
                important_outputs.append(f"🔗 **Meeting link**: {key_outputs['meeting_link']}")
            
            if 'message_id' in key_outputs:
                logger.info("📧 Adding email success to response")
                important_outputs.append("📧 **Email sent successfully**")
            
            if 'event_id' in key_outputs:
                logger.info("📅 Adding calendar event to response")
                important_outputs.append("📅 **Calendar event created**")
            
            if 'file_id' in key_outputs:
                logger.info("📁 Adding file processing to response")
                important_outputs.append("📁 **File processed in Drive**")
            
            if important_outputs:
                response_parts.append("\n**Key details:**")
                response_parts.extend(important_outputs)
            
            final_response = "\n".join(response_parts)
            logger.info("✅ Final response generated successfully")
            logger.info(f"📝 Response length: {len(final_response)} characters")
            
            return final_response
            
        except Exception as e:
            logger.error(f"❌ Error generating final response: {str(e)}")
            logger.error(traceback.format_exc())
            return f"Task completed, but encountered an error generating the summary: {str(e)}"
    
    def get_workflow_status(self, user_id: str) -> Dict[str, Any]:
        """Get current workflow status for UI with logging"""
        
        logger.info(f"📊 Getting workflow status for user: {user_id}")
        
        try:
            state_manager = StateManager(user_id)
            status = state_manager.get_workflow_progress()
            logger.info(f"✅ Workflow status retrieved: {status}")
            return status
        except Exception as e:
            logger.error(f"❌ Error getting workflow status: {str(e)}")
            return {"status": "error", "error": str(e)}
    
    def cancel_workflow(self, user_id: str):
        """Cancel current workflow with logging"""
        
        logger.info(f"🛑 Cancelling workflow for user: {user_id}")
        
        try:
            state_manager = StateManager(user_id)
            state_manager.clear_workflow()
            logger.info("✅ Workflow cancelled successfully")
        except Exception as e:
            logger.error(f"❌ Error cancelling workflow: {str(e)}")
            raise
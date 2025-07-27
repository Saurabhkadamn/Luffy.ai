from typing import Dict, Any, Optional, Generator
import streamlit as st
from agents.llm_planner import LLMPlanner
from agents.graph_builder import GraphBuilder
from agents.state_manager import StateManager
from agents.plan_schema import WorkflowState

class AgentOrchestrator:
    """Main coordinator for LangGraph agent workflows"""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.planner = LLMPlanner()  # LLM created internally
        self.graph_builder = GraphBuilder(auth_manager)  # No LLM needed here
    
    def process_user_request(self, user_request: str, user_id: str) -> Generator[str, None, None]:
        """Process user request with streaming updates"""
        
        try:
            # Step 1: Create execution plan
            yield "🧠 **Planning your request...**"
            
            user_context = self._get_user_context(user_id)
            plan = self.planner.create_plan(user_request, user_context)
            
            yield f"✅ **Plan created**: {plan.intent}"
            yield f"📋 **Steps to execute**: {len(plan.steps)}"
            
            # Show plan summary
            for i, step in enumerate(plan.steps, 1):
                yield f"   {i}. {step.description}"
            
            # Step 2: Build and execute workflow
            yield "\n🚀 **Starting execution...**"
            
            state_manager = StateManager(user_id)
            initial_state = state_manager.initialize_workflow(plan)
            
            # Build dynamic graph
            workflow_graph = self.graph_builder.build_graph(plan, user_id)
            
            # Execute workflow with progress updates
            for update in self._execute_workflow_with_progress(workflow_graph, initial_state, state_manager):
                yield update
            
            # Step 3: Generate final response
            yield "\n📝 **Generating summary...**"
            
            final_results = state_manager.get_final_results()
            final_response = self._generate_final_response(final_results)
            
            yield f"\n✅ **Completed!**\n\n{final_response}"
            
        except Exception as e:
            yield f"\n❌ **Error**: {str(e)}"
            yield "\nPlease try rephrasing your request or check your Google account connection."
    
    def _get_user_context(self, user_id: str) -> Dict[str, Any]:
        """Get user context for planning"""
        
        user_info = self.auth_manager.get_user_info(user_id)
        
        context = {
            "user_id": user_id,
            "authenticated_services": []
        }
        
        if user_info:
            context.update({
                "user_email": user_info.get("email", ""),
                "user_name": user_info.get("name", ""),
                "timezone": "UTC"  # Could be enhanced to detect user timezone
            })
        
        # Check available services
        if self.auth_manager.get_authenticated_client('gmail', 'v1', user_id):
            context["authenticated_services"].append("gmail")
        if self.auth_manager.get_authenticated_client('calendar', 'v3', user_id):
            context["authenticated_services"].append("calendar")
        if self.auth_manager.get_authenticated_client('drive', 'v3', user_id):
            context["authenticated_services"].append("drive")
        
        return context
    
    def _execute_workflow_with_progress(self, workflow_graph, initial_state: WorkflowState, 
                                      state_manager: StateManager) -> Generator[str, None, None]:
        """Execute workflow with real-time progress updates"""
        
        try:
            # Execute the workflow
            result = workflow_graph.invoke(initial_state)
            
            # Monitor progress and provide updates
            for step_index in range(1, len(initial_state.plan.steps) + 1):
                current_state = state_manager.get_current_state()
                
                if step_index in current_state.step_results:
                    step_result = current_state.step_results[step_index]
                    step = current_state.plan.steps[step_index - 1]
                    
                    if step_result.status == "completed":
                        yield f"✅ **Step {step_index}**: {step.description}"
                        
                        # Show key outputs
                        if step_result.extracted_data:
                            key_data = step_result.extracted_data
                            if len(str(key_data)) < 100:  # Only show short summaries
                                yield f"   📊 Key result: {key_data}"
                    
                    elif step_result.status == "failed":
                        yield f"❌ **Step {step_index} failed**: {step_result.error_message}"
                        break
                else:
                    yield f"⏳ **Step {step_index}**: In progress..."
            
        except Exception as e:
            yield f"❌ **Workflow execution failed**: {str(e)}"
    
    def _generate_final_response(self, final_results: Dict[str, Any]) -> str:
        """Generate human-friendly final response"""
        
        if not final_results:
            return "I encountered an issue completing your request. Please try again."
        
        response_parts = []
        
        # Main accomplishment
        response_parts.append(f"**{final_results['intent']}**")
        
        # Step summaries
        if final_results.get('step_summaries'):
            response_parts.append("\n**What I accomplished:**")
            
            for step_summary in final_results['step_summaries']:
                if step_summary['status'] == 'completed':
                    response_parts.append(f"• {step_summary['description']}")
        
        # Key outputs
        key_outputs = final_results.get('key_outputs', {})
        important_outputs = []
        
        if 'meeting_link' in key_outputs:
            important_outputs.append(f"🔗 **Meeting link**: {key_outputs['meeting_link']}")
        
        if 'message_id' in key_outputs:
            important_outputs.append("📧 **Email sent successfully**")
        
        if 'event_id' in key_outputs:
            important_outputs.append("📅 **Calendar event created**")
        
        if 'file_id' in key_outputs:
            important_outputs.append("📁 **File processed in Drive**")
        
        if important_outputs:
            response_parts.append("\n**Key details:**")
            response_parts.extend(important_outputs)
        
        return "\n".join(response_parts)
    
    def get_workflow_status(self, user_id: str) -> Dict[str, Any]:
        """Get current workflow status for UI"""
        
        state_manager = StateManager(user_id)
        return state_manager.get_workflow_progress()
    
    def cancel_workflow(self, user_id: str):
        """Cancel current workflow"""
        
        state_manager = StateManager(user_id)
        state_manager.clear_workflow()
from typing import Dict, Any, Optional
from datetime import datetime
import streamlit as st
import logging
from agents.plan_schema import WorkflowState, ExecutionPlan, StepResult

# Configure logging
logger = logging.getLogger(__name__)

class StateManager:
    """
    Updated StateManager for TypedDict compatibility and LangGraph integration.
    
    This class now serves two purposes:
    1. UI state tracking in Streamlit (for progress display)
    2. Helper methods for TypedDict WorkflowState manipulation
    
    The actual workflow state is managed by LangGraph checkpointers automatically.
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state_key = f"workflow_ui_state_{user_id}"
        logger.info(f"🗃️ StateManager initialized for user: {user_id}")
        logger.info("✅ StateManager now compatible with TypedDict WorkflowState")
    
    # ========================================
    # UI TRACKING METHODS (For Streamlit Display)
    # ========================================
    
    def track_workflow_for_ui(self, workflow_intent: str, total_steps: int) -> None:
        """Track workflow progress for UI display only"""
        
        logger.info(f"📱 Tracking workflow for UI: {workflow_intent}")
        
        try:
            ui_state = {
                "workflow_intent": workflow_intent,
                "total_steps": total_steps,
                "current_step": 1,
                "status": "executing",
                "started_at": datetime.now().isoformat(),
                "progress_log": [f"🚀 Started: {workflow_intent}"]
            }
            
            # Store in Streamlit session state for UI
            st.session_state[self.state_key] = ui_state
            logger.info("✅ UI workflow tracking initialized")
            
        except Exception as e:
            logger.error(f"❌ Error tracking workflow for UI: {str(e)}")
    
    def update_ui_progress(self, step: int, message: str) -> None:
        """Update UI progress tracking"""
        
        logger.info(f"📱 Updating UI progress: step {step}")
        
        try:
            if self.state_key in st.session_state:
                ui_state = st.session_state[self.state_key]
                ui_state["current_step"] = step
                ui_state["progress_log"].append(message)
                st.session_state[self.state_key] = ui_state
                logger.info("✅ UI progress updated")
            
        except Exception as e:
            logger.error(f"❌ Error updating UI progress: {str(e)}")
    
    def get_ui_progress(self) -> Dict[str, Any]:
        """Get UI progress for display"""
        
        try:
            if self.state_key in st.session_state:
                ui_state = st.session_state[self.state_key]
                progress = (ui_state["current_step"] / ui_state["total_steps"]) * 100
                
                return {
                    "status": ui_state["status"],
                    "progress": progress,
                    "current_step": ui_state["current_step"],
                    "total_steps": ui_state["total_steps"],
                    "workflow_intent": ui_state["workflow_intent"],
                    "progress_log": ui_state["progress_log"]
                }
            else:
                return {"status": "no_workflow", "progress": 0}
                
        except Exception as e:
            logger.error(f"❌ Error getting UI progress: {str(e)}")
            return {"status": "error", "progress": 0, "error": str(e)}
    
    def clear_ui_tracking(self):
        """Clear UI workflow tracking"""
        
        logger.info(f"🗑️ Clearing UI workflow tracking for user: {self.user_id}")
        
        try:
            if self.state_key in st.session_state:
                del st.session_state[self.state_key]
                logger.info("✅ UI workflow tracking cleared")
            else:
                logger.warning("⚠️ No UI workflow tracking found to clear")
                
        except Exception as e:
            logger.error(f"❌ Error clearing UI workflow tracking: {str(e)}")
    
    # ========================================
    # WORKFLOW STATE HELPER METHODS (TypedDict Compatible)
    # ========================================
    
    def create_initial_state(self, plan: ExecutionPlan, user_id: str) -> WorkflowState:
        """Create initial WorkflowState as TypedDict"""
        
        logger.info(f"🔄 Creating initial WorkflowState for plan: {plan['intent']}")
        
        try:
            # ✅ FIXED: Create WorkflowState as TypedDict
            initial_state: WorkflowState = {
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
            
            logger.info("✅ Initial WorkflowState created as TypedDict")
            return initial_state
            
        except Exception as e:
            logger.error(f"❌ Error creating initial WorkflowState: {str(e)}")
            raise
    
    def update_workflow_state(self, current_state: WorkflowState, step_result: StepResult, 
                             extracted_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create state updates for LangGraph (returns updates, not full state)
        This method helps create proper state updates that will be merged by reducers
        """
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        logger.info(f"📝 Creating state updates for step {step_result['step_index']}")
        
        try:
            # Create state updates (not full state) - LangGraph reducers will merge these
            updates = {}
            
            # Update step results
            if step_result:
                # Add extracted data to step result
                step_result['extracted_data'] = extracted_data.get("extracted_data", {})
                updates["step_results"] = {step_result['step_index']: step_result}
                logger.info(f"✅ Added step result for step {step_result['step_index']}")
            
            # Update shared context
            context_updates = {}
            
            # Add context updates from extracted data
            if "context_updates" in extracted_data:
                context_updates.update(extracted_data["context_updates"])
                logger.info(f"📊 Added context updates: {list(extracted_data['context_updates'].keys())}")
            
            # Add data for future steps
            if "for_future_steps" in extracted_data:
                context_updates.update(extracted_data["for_future_steps"])
                logger.info(f"🔮 Added future step data: {list(extracted_data['for_future_steps'].keys())}")
            
            if context_updates:
                updates["shared_context"] = context_updates
            
            # Update current step and status
            next_step = current_state['current_step'] + 1
            total_steps = len(current_state['plan']['steps'])
            
            updates["current_step"] = next_step
            
            # Determine status
            if step_result['status'] == "failed":
                updates["status"] = "failed"
                updates["execution_log"] = [f"❌ Step {step_result['step_index']} failed: {step_result.get('error_message', 'Unknown error')}"]
            elif next_step > total_steps:
                updates["status"] = "completed" 
                updates["execution_log"] = [f"✅ Step {step_result['step_index']} completed", "🎉 Workflow completed successfully!"]
            else:
                updates["status"] = "executing"
                updates["execution_log"] = [f"✅ Step {step_result['step_index']} completed"]
            
            logger.info(f"✅ State updates created: {list(updates.keys())}")
            return updates
            
        except Exception as e:
            logger.error(f"❌ Error creating state updates: {str(e)}")
            return {
                "status": "failed",
                "execution_log": [f"❌ Error updating state: {str(e)}"]
            }
    
    def extract_progress_from_state(self, state: WorkflowState) -> Dict[str, Any]:
        """Extract progress information from WorkflowState for UI display"""
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        try:
            total_steps = len(state['plan']['steps'])
            completed_steps = len([r for r in state['step_results'].values() if r['status'] == 'completed'])
            failed_steps = len([r for r in state['step_results'].values() if r['status'] == 'failed'])
            
            progress = (completed_steps / total_steps) * 100 if total_steps > 0 else 0
            
            return {
                "status": state['status'],
                "progress": progress,
                "current_step": state['current_step'],
                "total_steps": total_steps,
                "completed_steps": completed_steps,
                "failed_steps": failed_steps,
                "plan_intent": state['plan']['intent'],
                "execution_log": state.get('execution_log', []),
                "created_at": state['created_at']
            }
            
        except Exception as e:
            logger.error(f"❌ Error extracting progress from state: {str(e)}")
            return {
                "status": "error",
                "progress": 0,
                "error": str(e)
            }
    
    def get_context_for_step(self, state: WorkflowState, step_index: int) -> Dict[str, Any]:
        """Get execution context from WorkflowState for a specific step"""
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        logger.info(f"📊 Getting context from WorkflowState for step {step_index}")
        
        try:
            step = state['plan']['steps'][step_index - 1]  # Convert to 0-based index
            context = {
                "shared_context": state['shared_context'],
                "step_parameters": step['parameters'],
                "user_id": state['user_id']
            }
            
            # Add data from dependent steps
            for dep_step_index in step['dependencies']:
                if dep_step_index in state['step_results']:
                    dep_result = state['step_results'][dep_step_index]
                    context[f"step_{dep_step_index}_data"] = dep_result['extracted_data']
                    context[f"step_{dep_step_index}_raw"] = dep_result['raw_output']
                    logger.info(f"📋 Added dependency data from step {dep_step_index}")
            
            logger.info(f"✅ Context prepared for step {step_index}")
            return context
            
        except Exception as e:
            logger.error(f"❌ Error getting context from WorkflowState: {str(e)}")
            return {
                "shared_context": state.get('shared_context', {}),
                "step_parameters": {},
                "user_id": state.get('user_id', self.user_id)
            }
    
    def create_failed_step_result(self, step_index: int, step: Dict[str, Any], error_message: str) -> StepResult:
        """Create a failed StepResult as TypedDict"""
        
        logger.info(f"❌ Creating failed step result for step {step_index}")
        
        try:
            # ✅ FIXED: Create StepResult as TypedDict
            failed_result: StepResult = {
                "step_index": step_index,
                "tool": step['tool'],
                "action": step['action'],
                "status": "failed",
                "raw_output": {},
                "extracted_data": {},
                "error_message": error_message
            }
            
            logger.info(f"✅ Failed step result created for step {step_index}")
            return failed_result
            
        except Exception as e:
            logger.error(f"❌ Error creating failed step result: {str(e)}")
            # Return minimal failed result
            return {
                "step_index": step_index,
                "tool": step.get('tool', 'unknown'),
                "action": step.get('action', 'unknown'), 
                "status": "failed",
                "raw_output": {},
                "extracted_data": {},
                "error_message": f"Error creating failed result: {str(e)}"
            }
    
    # ========================================
    # BACKWARD COMPATIBILITY METHODS
    # ========================================
    
    def get_workflow_progress(self) -> Dict[str, Any]:
        """Get workflow progress - returns UI progress for backward compatibility"""
        logger.info("📊 Getting workflow progress (UI-only for backward compatibility)")
        return self.get_ui_progress()
    
    def clear_workflow(self):
        """Clear workflow - clears UI tracking for backward compatibility"""
        logger.info("🗑️ Clearing workflow (UI-only for backward compatibility)")
        self.clear_ui_tracking()
    
    # ========================================
    # DEPRECATED METHODS - Maintained for compatibility
    # ========================================
    
    def initialize_workflow(self, plan: ExecutionPlan) -> WorkflowState:
        """DEPRECATED: Use create_initial_state() instead"""
        logger.warning("⚠️ DEPRECATED: initialize_workflow() - Use create_initial_state() instead")
        return self.create_initial_state(plan, self.user_id)
    
    def get_current_state(self) -> Optional[WorkflowState]:
        """DEPRECATED: LangGraph checkpointers manage state automatically"""
        logger.warning("⚠️ DEPRECATED: get_current_state() - Query LangGraph checkpointer instead")
        return None
    
    def update_step_result(self, step_result: StepResult, extracted_data: Dict[str, Any]):
        """DEPRECATED: LangGraph handles this automatically with reducers"""
        logger.warning("⚠️ DEPRECATED: update_step_result() - LangGraph handles state updates automatically")
    
    def mark_step_failed(self, step_index: int, error_message: str):
        """DEPRECATED: LangGraph handles failures automatically"""
        logger.warning("⚠️ DEPRECATED: mark_step_failed() - LangGraph handles failures automatically")
    
    def get_final_results(self) -> Dict[str, Any]:
        """DEPRECATED: Get results from LangGraph final state instead"""
        logger.warning("⚠️ DEPRECATED: get_final_results() - Get results from LangGraph final state")
        return {"error": "Use LangGraph final state instead", "status": "deprecated"}
    
    def save_state(self, state: WorkflowState):
        """DEPRECATED: LangGraph checkpointers handle saving automatically"""
        logger.warning("⚠️ DEPRECATED: save_state() - LangGraph checkpointers save automatically")
    
    # ========================================
    # UTILITY METHODS
    # ========================================
    
    def format_execution_time(self, state: WorkflowState) -> str:
        """Calculate and format execution time from WorkflowState"""
        
        # ✅ FIXED: Access TypedDict fields with bracket notation
        try:
            if state.get('created_at'):
                start_time = datetime.fromisoformat(state['created_at'])
                end_time = datetime.now()
                duration = end_time - start_time
                
                total_seconds = int(duration.total_seconds())
                if total_seconds < 60:
                    return f"{total_seconds} seconds"
                else:
                    minutes = total_seconds // 60
                    seconds = total_seconds % 60
                    return f"{minutes}m {seconds}s"
            else:
                return "Unknown"
                
        except Exception as e:
            logger.error(f"❌ Error calculating execution time: {str(e)}")
            return "Unknown"
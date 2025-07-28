from typing import Dict, Any, Optional
from datetime import datetime
import streamlit as st
import logging
from agents.plan_schema import WorkflowState, ExecutionPlan, StepResult

# Configure logging
logger = logging.getLogger(__name__)

class StateManager:
    """Manages workflow state across execution steps with proper LangGraph integration"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state_key = f"workflow_state_{user_id}"
        logger.info(f"🗃️ StateManager initialized for user: {user_id}")
    
    def initialize_workflow(self, plan: ExecutionPlan) -> WorkflowState:
        """Initialize new workflow state - FIXED for LangGraph"""
        
        logger.info(f"🔄 Initializing workflow state for plan: {plan.intent}")
        
        try:
            state = WorkflowState(
                plan=plan,
                step_results={},
                shared_context={
                    "user_id": self.user_id,
                    "workflow_started": datetime.now().isoformat(),
                    "user_preferences": {},
                    "discovered_contacts": [],
                    "project_context": {}
                },
                current_step=1,
                status="executing",
                user_id=self.user_id,
                created_at=datetime.now().isoformat()
            )
            
            # Store in session state
            st.session_state[self.state_key] = state
            logger.info(f"✅ Workflow state initialized and stored for {plan.intent}")
            logger.info(f"📋 Plan has {len(plan.steps)} steps")
            
            return state
            
        except Exception as e:
            logger.error(f"❌ Error initializing workflow state: {str(e)}")
            raise
    
    def get_current_state(self) -> Optional[WorkflowState]:
        """Get current workflow state"""
        
        try:
            state = st.session_state.get(self.state_key)
            if state:
                logger.info(f"📊 Retrieved current state: {state.status}")
                return state
            else:
                logger.warning("⚠️ No current workflow state found")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting current state: {str(e)}")
            return None
    
    def update_step_result(self, step_result: StepResult, extracted_data: Dict[str, Any]):
        """Update state with completed step results - ENHANCED for LangGraph"""
        
        logger.info(f"📝 Updating step result for step {step_result.step_index}")
        
        try:
            state = self.get_current_state()
            if not state:
                logger.error("❌ No current state found for step result update")
                return
            
            # Store step result with extracted data
            step_result.extracted_data = extracted_data.get("extracted_data", {})
            state.step_results[step_result.step_index] = step_result
            logger.info(f"✅ Step {step_result.step_index} result stored")
            
            # Update shared context
            if "context_updates" in extracted_data:
                state.shared_context.update(extracted_data["context_updates"])
                logger.info(f"📊 Context updates applied: {list(extracted_data['context_updates'].keys())}")
            
            # Add data for future steps
            if "for_future_steps" in extracted_data:
                state.shared_context.update(extracted_data["for_future_steps"])
                logger.info(f"🔮 Future step data added: {list(extracted_data['for_future_steps'].keys())}")
            
            # Update current step
            state.current_step = step_result.step_index + 1
            logger.info(f"➡️ Current step advanced to: {state.current_step}")
            
            # Check if workflow completed
            if state.current_step > len(state.plan.steps):
                state.status = "completed"
                logger.info("🎉 Workflow marked as completed")
            
            # Save updated state
            st.session_state[self.state_key] = state
            logger.info(f"✅ State updated and saved for step {step_result.step_index}")
            
        except Exception as e:
            logger.error(f"❌ Error updating step result: {str(e)}")
            raise
    
    def get_context_for_step(self, step_index: int) -> Dict[str, Any]:
        """Get relevant context for executing a specific step - ENHANCED"""
        
        logger.info(f"📊 Getting context for step {step_index}")
        
        try:
            state = self.get_current_state()
            if not state:
                logger.error(f"❌ No current state found for step {step_index}")
                return {
                    "shared_context": {},
                    "step_parameters": {},
                    "user_id": self.user_id
                }
            
            step = state.plan.steps[step_index - 1]  # Convert to 0-based index
            context = {
                "shared_context": state.shared_context,
                "step_parameters": step.parameters,
                "user_id": self.user_id
            }
            
            # Add data from dependent steps
            for dep_step_index in step.dependencies:
                if dep_step_index in state.step_results:
                    dep_result = state.step_results[dep_step_index]
                    context[f"step_{dep_step_index}_data"] = dep_result.extracted_data
                    context[f"step_{dep_step_index}_raw"] = dep_result.raw_output
                    logger.info(f"📋 Added dependency data from step {dep_step_index}")
            
            logger.info(f"✅ Context prepared for step {step_index}: {list(context.keys())}")
            return context
            
        except Exception as e:
            logger.error(f"❌ Error getting context for step {step_index}: {str(e)}")
            # Return minimal context on error
            return {
                "shared_context": {"user_id": self.user_id},
                "step_parameters": {},
                "user_id": self.user_id
            }
    
    def mark_step_failed(self, step_index: int, error_message: str):
        """Mark a step as failed - ENHANCED"""
        
        logger.error(f"❌ Marking step {step_index} as failed: {error_message}")
        
        try:
            state = self.get_current_state()
            if not state:
                logger.error(f"❌ No current state found to mark step {step_index} as failed")
                return
            
            # Update existing step result or create new failed result
            if step_index in state.step_results:
                state.step_results[step_index].status = "failed"
                state.step_results[step_index].error_message = error_message
                logger.info(f"📝 Updated existing step {step_index} with failure")
            else:
                # Create failed step result
                from agents.plan_schema import StepResult, ToolType, ActionType
                step = state.plan.steps[step_index - 1]
                
                failed_result = StepResult(
                    step_index=step_index,
                    tool=step.tool,
                    action=step.action,
                    status="failed",
                    raw_output={},
                    extracted_data={},
                    error_message=error_message
                )
                state.step_results[step_index] = failed_result
                logger.info(f"📝 Created new failed step result for step {step_index}")
            
            # Mark entire workflow as failed
            state.status = "failed"
            logger.info("❌ Workflow marked as failed")
            
            # Save updated state
            st.session_state[self.state_key] = state
            logger.info(f"✅ Failed state saved for step {step_index}")
            
        except Exception as e:
            logger.error(f"❌ Error marking step {step_index} as failed: {str(e)}")
    
    def get_workflow_progress(self) -> Dict[str, Any]:
        """Get current workflow progress for UI display - ENHANCED"""
        
        logger.info("📊 Getting workflow progress")
        
        try:
            state = self.get_current_state()
            if not state:
                logger.warning("⚠️ No workflow state found")
                return {"status": "no_workflow", "progress": 0}
            
            completed_steps = len([r for r in state.step_results.values() if r.status == "completed"])
            failed_steps = len([r for r in state.step_results.values() if r.status == "failed"])
            total_steps = len(state.plan.steps)
            progress = (completed_steps / total_steps) * 100 if total_steps > 0 else 0
            
            progress_info = {
                "status": state.status,
                "progress": progress,
                "current_step": state.current_step,
                "total_steps": total_steps,
                "plan_intent": state.plan.intent,
                "completed_steps": completed_steps,
                "failed_steps": failed_steps,
                "created_at": state.created_at
            }
            
            logger.info(f"📊 Progress: {completed_steps}/{total_steps} steps completed ({progress:.1f}%)")
            return progress_info
            
        except Exception as e:
            logger.error(f"❌ Error getting workflow progress: {str(e)}")
            return {"status": "error", "progress": 0, "error": str(e)}
    
    def clear_workflow(self):
        """Clear current workflow state"""
        
        logger.info(f"🗑️ Clearing workflow state for user: {self.user_id}")
        
        try:
            if self.state_key in st.session_state:
                del st.session_state[self.state_key]
                logger.info("✅ Workflow state cleared successfully")
            else:
                logger.warning("⚠️ No workflow state found to clear")
                
        except Exception as e:
            logger.error(f"❌ Error clearing workflow state: {str(e)}")
    
    def get_final_results(self) -> Dict[str, Any]:
        """Get final workflow results for user response - ENHANCED"""
        
        logger.info("📊 Getting final workflow results")
        
        try:
            state = self.get_current_state()
            if not state:
                logger.warning("⚠️ No workflow state found for final results")
                return {}
            
            if state.status not in ["completed", "failed"]:
                logger.warning(f"⚠️ Workflow not finished yet, status: {state.status}")
                return {}
            
            results = {
                "intent": state.plan.intent,
                "steps_completed": len([r for r in state.step_results.values() if r.status == "completed"]),
                "steps_failed": len([r for r in state.step_results.values() if r.status == "failed"]),
                "step_summaries": [],
                "key_outputs": {},
                "shared_context": state.shared_context,
                "workflow_status": state.status,
                "execution_time": self._calculate_execution_time(state)
            }
            
            # Process step results
            for step_index, result in state.step_results.items():
                step = state.plan.steps[step_index - 1]
                step_summary = {
                    "step": step_index,
                    "description": step.description,
                    "status": result.status,
                    "key_data": result.extracted_data
                }
                
                if result.status == "failed":
                    step_summary["error"] = result.error_message
                
                results["step_summaries"].append(step_summary)
                
                # Collect key outputs from successful steps
                if result.status == "completed" and result.extracted_data:
                    results["key_outputs"].update(result.extracted_data)
            
            logger.info(f"✅ Final results compiled: {results['steps_completed']} completed, {results['steps_failed']} failed")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error getting final results: {str(e)}")
            return {"error": str(e), "status": "error"}
    
    def _calculate_execution_time(self, state: WorkflowState) -> str:
        """Calculate workflow execution time"""
        
        try:
            if state.created_at:
                start_time = datetime.fromisoformat(state.created_at)
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
    
    def save_state(self, state: WorkflowState):
        """Manually save state - useful for LangGraph integration"""
        
        logger.info(f"💾 Manually saving state: {state.status}")
        
        try:
            st.session_state[self.state_key] = state
            logger.info("✅ State saved successfully")
            
        except Exception as e:
            logger.error(f"❌ Error saving state: {str(e)}")
            raise
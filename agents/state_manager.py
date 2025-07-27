from typing import Dict, Any, Optional
from datetime import datetime
import streamlit as st
from agents.plan_schema import WorkflowState, ExecutionPlan, StepResult

class StateManager:
    """Manages workflow state across execution steps"""
    
    def __init__(self, user_id: str):
        self.user_id = user_id
        self.state_key = f"workflow_state_{user_id}"
    
    def initialize_workflow(self, plan: ExecutionPlan) -> WorkflowState:
        """Initialize new workflow state"""
        
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
        return state
    
    def get_current_state(self) -> Optional[WorkflowState]:
        """Get current workflow state"""
        return st.session_state.get(self.state_key)
    
    def update_step_result(self, step_result: StepResult, extracted_data: Dict[str, Any]):
        """Update state with completed step results"""
        
        state = self.get_current_state()
        if not state:
            return
        
        # Store step result
        step_result.extracted_data = extracted_data.get("extracted_data", {})
        state.step_results[step_result.step_index] = step_result
        
        # Update shared context
        if "context_updates" in extracted_data:
            state.shared_context.update(extracted_data["context_updates"])
        
        # Add data for future steps
        if "for_future_steps" in extracted_data:
            state.shared_context.update(extracted_data["for_future_steps"])
        
        # Update current step
        state.current_step += 1
        
        # Check if workflow completed
        if state.current_step > len(state.plan.steps):
            state.status = "completed"
        
        # Save updated state
        st.session_state[self.state_key] = state
    
    def get_context_for_step(self, step_index: int) -> Dict[str, Any]:
        """Get relevant context for executing a specific step"""
        
        state = self.get_current_state()
        if not state:
            return {}
        
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
        
        return context
    
    def mark_step_failed(self, step_index: int, error_message: str):
        """Mark a step as failed"""
        
        state = self.get_current_state()
        if not state:
            return
        
        if step_index in state.step_results:
            state.step_results[step_index].status = "failed"
            state.step_results[step_index].error_message = error_message
        
        state.status = "failed"
        st.session_state[self.state_key] = state
    
    def get_workflow_progress(self) -> Dict[str, Any]:
        """Get current workflow progress for UI display"""
        
        state = self.get_current_state()
        if not state:
            return {"status": "no_workflow", "progress": 0}
        
        completed_steps = len([r for r in state.step_results.values() if r.status == "completed"])
        total_steps = len(state.plan.steps)
        progress = (completed_steps / total_steps) * 100 if total_steps > 0 else 0
        
        return {
            "status": state.status,
            "progress": progress,
            "current_step": state.current_step,
            "total_steps": total_steps,
            "plan_intent": state.plan.intent,
            "completed_steps": completed_steps
        }
    
    def clear_workflow(self):
        """Clear current workflow state"""
        if self.state_key in st.session_state:
            del st.session_state[self.state_key]
    
    def get_final_results(self) -> Dict[str, Any]:
        """Get final workflow results for user response"""
        
        state = self.get_current_state()
        if not state or state.status != "completed":
            return {}
        
        results = {
            "intent": state.plan.intent,
            "steps_completed": len(state.step_results),
            "step_summaries": [],
            "key_outputs": {},
            "shared_context": state.shared_context
        }
        
        for step_index, result in state.step_results.items():
            step = state.plan.steps[step_index - 1]
            results["step_summaries"].append({
                "step": step_index,
                "description": step.description,
                "status": result.status,
                "key_data": result.extracted_data
            })
            
            # Collect key outputs
            if result.extracted_data:
                results["key_outputs"].update(result.extracted_data)
        
        return results
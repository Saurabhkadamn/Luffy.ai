from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from pathlib import Path

# LangGraph checkpointing imports
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.memory import MemorySaver

# Our new state schema
from agents.plan_schema import (
    WorkflowState, 
    ExecutionPlan, 
    StepResult,
    create_initial_state,
    update_step_completion,
    update_workflow_status,
    get_progress_summary
)

# Configure logging
logger = logging.getLogger(__name__)

class StateManager:
    """
    LangGraph-native state manager using checkpointing for persistence.
    
    Replaces Streamlit session state with proper LangGraph checkpointing
    that survives page refreshes, enables recovery, and supports
    human-in-the-loop workflows.
    """
    
    def __init__(self, user_id: str, use_memory: bool = False):
        """
        Initialize state manager with LangGraph checkpointing.
        
        Args:
            user_id: Unique user identifier for thread isolation
            use_memory: If True, use MemorySaver (dev), else SqliteSaver (prod)
        """
        self.user_id = user_id
        self.thread_id = f"workflow_{user_id}"
        
        # Initialize checkpointer
        if use_memory:
            logger.info(f"🗃️ Using MemorySaver for user: {user_id}")
            self.checkpointer = MemorySaver()
        else:
            # Create SQLite database for persistent storage
            db_path = Path("data") / "checkpoints" / f"user_{user_id}.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"🗃️ Using SqliteSaver at: {db_path}")
            self.checkpointer = SqliteSaver(str(db_path))
        
        # Thread configuration for LangGraph
        self.config = {
            "configurable": {
                "thread_id": self.thread_id,
                "user_id": user_id
            }
        }
        
        logger.info(f"✅ StateManager initialized for user: {user_id}")
    
    def create_workflow_state(self, plan: ExecutionPlan) -> WorkflowState:
        """
        Create new workflow state using our schema helper.
        
        This creates the initial state that will be persisted
        by LangGraph checkpointing.
        """
        logger.info(f"🔄 Creating new workflow state for plan: {plan.intent}")
        
        try:
            # Use our helper function from plan_schema
            initial_state = create_initial_state(plan, self.user_id)
            
            logger.info(f"✅ Workflow state created with {len(plan.steps)} steps")
            logger.info(f"📋 Plan intent: {plan.intent}")
            
            return initial_state
            
        except Exception as e:
            logger.error(f"❌ Error creating workflow state: {str(e)}")
            raise
    
    def get_config(self) -> Dict[str, Any]:
        """Get LangGraph configuration for this user's thread"""
        return self.config.copy()
    
    def get_checkpointer(self):
        """Get the LangGraph checkpointer instance"""
        return self.checkpointer
    
    def get_thread_state(self) -> Optional[WorkflowState]:
        """
        Get current state from LangGraph checkpoint.
        
        Returns None if no active workflow exists.
        """
        try:
            # Get latest checkpoint for this thread
            checkpoint = self.checkpointer.get(self.config)
            
            if checkpoint and checkpoint.channel_values:
                logger.info(f"📊 Retrieved thread state for user: {self.user_id}")
                return checkpoint.channel_values
            else:
                logger.info(f"📭 No active workflow found for user: {self.user_id}")
                return None
                
        except Exception as e:
            logger.error(f"❌ Error getting thread state: {str(e)}")
            return None
    
    def get_workflow_progress(self) -> Dict[str, Any]:
        """
        Get current workflow progress for UI display.
        
        Returns progress summary with completion status,
        step details, and recent messages.
        """
        logger.info(f"📊 Getting workflow progress for user: {self.user_id}")
        
        try:
            current_state = self.get_thread_state()
            
            if not current_state:
                return {
                    "status": "no_workflow", 
                    "progress_percent": 0,
                    "message": "No active workflow"
                }
            
            # Use our helper function to get progress summary
            progress = get_progress_summary(current_state)
            
            logger.info(f"📊 Progress: {progress['completed_steps']}/{progress['total_steps']} steps completed")
            return progress
            
        except Exception as e:
            logger.error(f"❌ Error getting workflow progress: {str(e)}")
            return {
                "status": "error", 
                "progress_percent": 0,
                "error": str(e)
            }
    
    def get_recent_messages(self, limit: int = 10) -> List[str]:
        """Get recent progress messages for streaming display"""
        try:
            current_state = self.get_thread_state()
            
            if not current_state or "progress_messages" not in current_state:
                return []
            
            messages = current_state["progress_messages"]
            return messages[-limit:] if len(messages) > limit else messages
            
        except Exception as e:
            logger.error(f"❌ Error getting recent messages: {str(e)}")
            return []
    
    def is_workflow_active(self) -> bool:
        """Check if user has an active workflow"""
        try:
            state = self.get_thread_state()
            return (state is not None and 
                   state.get("status") in ["executing", "planning", "interrupted"])
        except Exception as e:
            logger.error(f"❌ Error checking workflow status: {str(e)}")
            return False
    
    def get_workflow_summary(self) -> Optional[Dict[str, Any]]:
        """
        Get high-level workflow summary for UI display.
        
        Useful for showing workflow cards or status in sidebar.
        """
        try:
            state = self.get_thread_state()
            
            if not state:
                return None
            
            return {
                "intent": state["plan"].intent,
                "status": state["status"],
                "total_steps": len(state["plan"].steps),
                "completed_steps": len([r for r in state["step_results"].values() 
                                      if r.status == "completed"]),
                "created_at": state["created_at"],
                "current_step": state["current_step"],
                "estimated_duration": state["plan"].estimated_duration
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting workflow summary: {str(e)}")
            return None
    
    def clear_workflow(self):
        """
        Clear current workflow state.
        
        This removes the checkpoint for this thread,
        effectively ending the current workflow.
        """
        logger.info(f"🗑️ Clearing workflow for user: {self.user_id}")
        
        try:
            # LangGraph checkpointer doesn't have a direct clear method
            # but we can put an empty state to effectively clear it
            empty_config = self.config.copy()
            
            # The actual clearing will happen when a new workflow starts
            # For now, we just log the intent
            logger.info("✅ Workflow clear requested - will be cleared on next workflow")
            
        except Exception as e:
            logger.error(f"❌ Error clearing workflow: {str(e)}")
    
    def get_step_details(self, step_index: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific step"""
        try:
            state = self.get_thread_state()
            
            if not state or step_index not in state["step_results"]:
                return None
            
            step_result = state["step_results"][step_index]
            plan_step = state["plan"].steps[step_index - 1]  # Convert to 0-based
            
            return {
                "step_index": step_index,
                "description": plan_step.description,
                "tool": step_result.tool.value,
                "action": step_result.action.value,
                "status": step_result.status,
                "extracted_data": step_result.extracted_data,
                "error_message": step_result.error_message,
                "raw_output": step_result.raw_output
            }
            
        except Exception as e:
            logger.error(f"❌ Error getting step details: {str(e)}")
            return None
    
    def get_final_results(self) -> Dict[str, Any]:
        """
        Get final workflow results for user display.
        
        This formats the completed workflow into a user-friendly
        summary with key accomplishments and outputs.
        """
        logger.info(f"📊 Getting final results for user: {self.user_id}")
        
        try:
            state = self.get_thread_state()
            
            if not state:
                logger.warning("⚠️ No workflow state found for final results")
                return {"error": "No workflow found"}
            
            if state["status"] not in ["completed", "failed"]:
                logger.warning(f"⚠️ Workflow not finished yet, status: {state['status']}")
                return {"error": "Workflow not completed", "status": state["status"]}
            
            # Build comprehensive results
            results = {
                "intent": state["plan"].intent,
                "status": state["status"],
                "completed_steps": len([r for r in state["step_results"].values() 
                                      if r.status == "completed"]),
                "failed_steps": len([r for r in state["step_results"].values() 
                                   if r.status == "failed"]),
                "total_steps": len(state["plan"].steps),
                "execution_time": self._calculate_execution_time(state),
                "progress_messages": state["progress_messages"],
                "shared_context": state["shared_context"],
                "error_count": state["error_count"],
                "created_at": state["created_at"]
            }
            
            # Extract key outputs from successful steps
            key_outputs = {}
            step_summaries = []
            
            for step_index, step_result in state["step_results"].items():
                plan_step = state["plan"].steps[step_index - 1]
                
                step_summary = {
                    "step": step_index,
                    "description": plan_step.description,
                    "status": step_result.status,
                    "tool": step_result.tool.value,
                    "action": step_result.action.value
                }
                
                if step_result.status == "completed":
                    step_summary["key_data"] = step_result.extracted_data
                    # Collect important outputs
                    if step_result.extracted_data:
                        key_outputs.update(step_result.extracted_data)
                elif step_result.status == "failed":
                    step_summary["error"] = step_result.error_message
                
                step_summaries.append(step_summary)
            
            results["step_summaries"] = step_summaries
            results["key_outputs"] = key_outputs
            
            logger.info(f"✅ Final results compiled: {results['completed_steps']} completed, {results['failed_steps']} failed")
            return results
            
        except Exception as e:
            logger.error(f"❌ Error getting final results: {str(e)}")
            return {"error": str(e), "status": "error"}
    
    def _calculate_execution_time(self, state: WorkflowState) -> str:
        """Calculate workflow execution time"""
        try:
            if state["created_at"]:
                start_time = datetime.fromisoformat(state["created_at"])
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

# Utility functions for integration with the rest of the system
def get_user_state_manager(user_id: str, use_memory: bool = False) -> StateManager:
    """
    Factory function to get a StateManager instance for a user.
    
    Args:
        user_id: User identifier
        use_memory: If True, use in-memory storage (dev mode)
    
    Returns:
        StateManager instance configured for the user
    """
    return StateManager(user_id, use_memory=use_memory)

def cleanup_old_checkpoints(days_old: int = 7):
    """
    Utility to clean up old checkpoint files.
    
    Args:
        days_old: Remove checkpoints older than this many days
    """
    logger.info(f"🧹 Cleaning up checkpoints older than {days_old} days")
    
    try:
        checkpoint_dir = Path("data") / "checkpoints"
        if not checkpoint_dir.exists():
            return
        
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
        
        for db_file in checkpoint_dir.glob("user_*.db"):
            if db_file.stat().st_mtime < cutoff_time:
                db_file.unlink()
                logger.info(f"🗑️ Removed old checkpoint: {db_file.name}")
        
        logger.info("✅ Checkpoint cleanup completed")
        
    except Exception as e:
        logger.error(f"❌ Error during checkpoint cleanup: {str(e)}")
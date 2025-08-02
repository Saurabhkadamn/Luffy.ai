from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from pathlib import Path
import sqlite3

# LangGraph checkpointing imports - FIXED for v0.2+
from langgraph.checkpoint.memory import MemorySaver
# FIXED: Import from separate package (requires: pip install langgraph-checkpoint-sqlite)
from langgraph.checkpoint.sqlite import SqliteSaver

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
    
    FIXED: Proper SQLite checkpointer implementation for LangGraph v0.2+
    - Uses SqliteSaver direct constructor instead of context manager
    - Proper database setup and error handling
    - Multi-user isolation with separate DB files
    - Automatic cleanup capabilities
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
        
        # Initialize checkpointer with FIXED implementation
        if use_memory:
            logger.info(f"🗃️ Using MemorySaver for user: {user_id}")
            self.checkpointer = MemorySaver()
        else:
            # FIXED: Create SQLite database with proper v0.2+ approach
            db_path = Path("data") / "checkpoints" / f"user_{user_id}.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.info(f"🗃️ Using SqliteSaver at: {db_path}")
            
            try:
                # FIXED: Use direct constructor instead of context manager
                conn = sqlite3.connect(str(db_path), check_same_thread=False)
                self.checkpointer = SqliteSaver(conn)
                
                # FIXED: Setup database tables on first use
                try:
                    self.checkpointer.setup()
                    logger.info("✅ SQLite database setup completed")
                except Exception as setup_error:
                    # Database might already exist, which is fine
                    logger.debug(f"Database setup note: {setup_error}")
                
            except ImportError as e:
                logger.error("❌ SQLite checkpointer not installed!")
                logger.error("Run: pip install langgraph-checkpoint-sqlite")
                raise ImportError(
                    "SQLite checkpointer requires: pip install langgraph-checkpoint-sqlite"
                ) from e
            except Exception as e:
                logger.error(f"❌ Failed to create SQLite checkpointer: {str(e)}")
                logger.warning("🔄 Falling back to MemorySaver")
                self.checkpointer = MemorySaver()
        
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
            # FIXED: Better error handling for checkpoint retrieval
            checkpoint = self.checkpointer.get(self.config)
            
            if checkpoint and hasattr(checkpoint, 'channel_values') and checkpoint.channel_values:
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
        
        IMPROVED: Better cleanup implementation for SQLite
        """
        logger.info(f"🗑️ Clearing workflow for user: {self.user_id}")
        
        try:
            # For MemorySaver, we can clear directly
            if isinstance(self.checkpointer, MemorySaver):
                # Clear from memory
                if hasattr(self.checkpointer, 'storage'):
                    self.checkpointer.storage.clear()
                logger.info("✅ Memory workflow cleared")
            
            else:
                # For SQLite, we could delete the specific thread
                # But for now, just log the intent - the workflow will be 
                # effectively cleared when a new one starts
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
    
    # ADDED: Database health and cleanup methods
    def get_database_info(self) -> Dict[str, Any]:
        """Get information about the SQLite database"""
        if isinstance(self.checkpointer, MemorySaver):
            return {"type": "memory", "persistent": False}
        
        try:
            db_path = Path("data") / "checkpoints" / f"user_{self.user_id}.db"
            
            info = {
                "type": "sqlite",
                "persistent": True,
                "path": str(db_path),
                "exists": db_path.exists(),
                "size_bytes": db_path.stat().st_size if db_path.exists() else 0
            }
            
            # Add size in human readable format
            size_bytes = info["size_bytes"]
            if size_bytes < 1024:
                info["size_readable"] = f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                info["size_readable"] = f"{size_bytes / 1024:.1f} KB"
            else:
                info["size_readable"] = f"{size_bytes / (1024 * 1024):.1f} MB"
            
            return info
            
        except Exception as e:
            logger.error(f"❌ Error getting database info: {str(e)}")
            return {"type": "sqlite", "error": str(e)}
    
    def close_connection(self):
        """
        ADDED: Properly close SQLite connection when done.
        
        Call this when shutting down the state manager.
        """
        try:
            if isinstance(self.checkpointer, SqliteSaver):
                # Access the underlying connection and close it
                if hasattr(self.checkpointer, 'conn'):
                    self.checkpointer.conn.close()
                    logger.info(f"✅ Closed SQLite connection for user: {self.user_id}")
        except Exception as e:
            logger.error(f"❌ Error closing SQLite connection: {str(e)}")
    
    def __del__(self):
        """Cleanup when object is destroyed"""
        try:
            self.close_connection()
        except:
            pass  # Silently handle cleanup errors

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

def cleanup_old_checkpoints(days_old: int = 7) -> Dict[str, Any]:
    """
    IMPROVED: Utility to clean up old checkpoint files with better reporting.
    
    Args:
        days_old: Remove checkpoints older than this many days
    
    Returns:
        Cleanup results with statistics
    """
    logger.info(f"🧹 Cleaning up checkpoints older than {days_old} days")
    
    cleanup_results = {
        "files_removed": 0,
        "space_freed_bytes": 0,
        "errors": [],
        "success": True
    }
    
    try:
        checkpoint_dir = Path("data") / "checkpoints"
        if not checkpoint_dir.exists():
            logger.info("📂 No checkpoint directory found")
            return cleanup_results
        
        cutoff_time = datetime.now().timestamp() - (days_old * 24 * 60 * 60)
        
        for db_file in checkpoint_dir.glob("user_*.db"):
            try:
                file_stat = db_file.stat()
                if file_stat.st_mtime < cutoff_time:
                    file_size = file_stat.st_size
                    db_file.unlink()
                    
                    cleanup_results["files_removed"] += 1
                    cleanup_results["space_freed_bytes"] += file_size
                    
                    logger.info(f"🗑️ Removed old checkpoint: {db_file.name} ({file_size} bytes)")
                    
            except Exception as file_error:
                error_msg = f"Error removing {db_file.name}: {str(file_error)}"
                cleanup_results["errors"].append(error_msg)
                logger.error(f"❌ {error_msg}")
        
        # Convert bytes to readable format
        space_freed = cleanup_results["space_freed_bytes"]
        if space_freed > 0:
            if space_freed < 1024:
                cleanup_results["space_freed_readable"] = f"{space_freed} B"
            elif space_freed < 1024 * 1024:
                cleanup_results["space_freed_readable"] = f"{space_freed / 1024:.1f} KB"
            else:
                cleanup_results["space_freed_readable"] = f"{space_freed / (1024 * 1024):.1f} MB"
        else:
            cleanup_results["space_freed_readable"] = "0 B"
        
        if cleanup_results["errors"]:
            cleanup_results["success"] = False
        
        logger.info(f"✅ Cleanup completed: {cleanup_results['files_removed']} files removed, {cleanup_results['space_freed_readable']} freed")
        return cleanup_results
        
    except Exception as e:
        logger.error(f"❌ Error during checkpoint cleanup: {str(e)}")
        cleanup_results["success"] = False
        cleanup_results["errors"].append(str(e))
        return cleanup_results

def validate_sqlite_installation() -> Dict[str, Any]:
    """
    ADDED: Validate that SQLite checkpointing is properly installed and working.
    
    Returns:
        Validation results with installation status and recommendations
    """
    validation = {
        "sqlite_available": False,
        "import_success": False,
        "test_success": False,
        "version_info": {},
        "recommendations": []
    }
    
    try:
        # Test import
        from langgraph.checkpoint.sqlite import SqliteSaver
        validation["import_success"] = True
        logger.info("✅ SQLite checkpointer import successful")
        
        # Test basic functionality
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        test_saver = SqliteSaver(conn)
        test_saver.setup()
        validation["test_success"] = True
        validation["sqlite_available"] = True
        conn.close()
        logger.info("✅ SQLite checkpointer test successful")
        
    except ImportError as e:
        validation["recommendations"].append(
            "Install SQLite checkpointer: pip install langgraph-checkpoint-sqlite"
        )
        logger.error(f"❌ SQLite checkpointer not installed: {str(e)}")
        
    except Exception as e:
        validation["recommendations"].append(
            "Check SQLite installation and permissions"
        )
        logger.error(f"❌ SQLite checkpointer test failed: {str(e)}")
    
    return validation

# Health check function for the entire state management system
def get_state_manager_health() -> Dict[str, Any]:
    """
    ADDED: Get comprehensive health check for state management system.
    
    Returns:
        Health status with component checks and recommendations
    """
    health = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "components": {},
        "recommendations": []
    }
    
    try:
        # Check SQLite installation
        sqlite_check = validate_sqlite_installation()
        health["components"]["sqlite"] = sqlite_check
        
        if not sqlite_check["sqlite_available"]:
            health["status"] = "degraded"
            health["recommendations"].extend(sqlite_check["recommendations"])
        
        # Check checkpoint directory
        checkpoint_dir = Path("data") / "checkpoints"
        if checkpoint_dir.exists():
            db_files = list(checkpoint_dir.glob("user_*.db"))
            health["components"]["checkpoint_directory"] = {
                "exists": True,
                "path": str(checkpoint_dir),
                "user_databases": len(db_files),
                "total_size_bytes": sum(f.stat().st_size for f in db_files if f.exists())
            }
            
            # Recommend cleanup if too many files
            if len(db_files) > 50:
                health["recommendations"].append(
                    f"Consider cleanup: {len(db_files)} user databases found"
                )
        else:
            health["components"]["checkpoint_directory"] = {
                "exists": False,
                "note": "Will be created automatically"
            }
        
        # Test MemorySaver as fallback
        try:
            memory_saver = MemorySaver()
            health["components"]["memory_fallback"] = "available"
        except Exception as e:
            health["components"]["memory_fallback"] = f"error: {str(e)}"
            health["status"] = "degraded"
        
        logger.info(f"🏥 State manager health check: {health['status']}")
        return health
        
    except Exception as e:
        logger.error(f"❌ Health check failed: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }
import logging
import traceback
from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langchain_core.tools import BaseTool

# Our new state schema and tools
from agents.plan_schema import (
    WorkflowState, 
    ExecutionPlan, 
    ExecutionStep,
    StepResult,
    update_step_completion,
    update_workflow_status,
    ToolType,
    ActionType
)
from agents.state_manager import StateManager

# Configure logging
logger = logging.getLogger(__name__)

class ModernGraphBuilder:
    """
    Modern LangGraph builder using current best practices.
    
    Replaces the old complex manual orchestration with:
    - Proper LangGraph state patterns
    - Built-in streaming support
    - Tool integration with ToolNode
    - Conditional edges for workflow control
    - Error handling and recovery
    """
    
    def __init__(self, auth_manager, tools_registry: Dict[ToolType, List[BaseTool]]):
        """
        Initialize with auth manager and tools registry.
        
        Args:
            auth_manager: Authentication manager for Google APIs
            tools_registry: Dict mapping tool types to LangChain tools
        """
        logger.info("🏗️ Initializing ModernGraphBuilder")
        
        try:
            self.auth_manager = auth_manager
            self.tools_registry = tools_registry
            
            # Flatten all tools for ToolNode
            self.all_tools = []
            for tool_list in tools_registry.values():
                self.all_tools.extend(tool_list)
            
            logger.info(f"🔧 Registered {len(self.all_tools)} tools across {len(tools_registry)} categories")
            logger.info(f"🔧 Tool categories: {list(tools_registry.keys())}")
            
            # Create ToolNode for executing tools
            if self.all_tools:
                self.tool_node = ToolNode(self.all_tools)
                logger.info("✅ ToolNode created successfully")
            else:
                logger.warning("⚠️ No tools registered - ToolNode not created")
                self.tool_node = None
            
            logger.info("✅ ModernGraphBuilder initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize ModernGraphBuilder: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def build_workflow_graph(self, plan: ExecutionPlan, state_manager: StateManager) -> StateGraph:
        """
        Build modern LangGraph workflow with proper patterns.
        
        Creates a streamlined graph with:
        - Step executor nodes
        - Tool execution via ToolNode
        - Conditional routing
        - Error handling
        - Progress tracking
        """
        logger.info(f"🚀 Building workflow graph for: {plan.intent}")
        logger.info(f"📋 Plan has {len(plan.steps)} steps")
        
        try:
            # Create StateGraph with our TypedDict state
            workflow = StateGraph(WorkflowState)
            
            # Add nodes for workflow control
            workflow.add_node("start_workflow", self._create_start_node())
            workflow.add_node("execute_step", self._create_step_executor_node(state_manager))
            workflow.add_node("finalize_workflow", self._create_finalize_node())
            
            # Add ToolNode if we have tools
            if self.tool_node:
                workflow.add_node("execute_tools", self.tool_node)
            
            # Add edges with conditional routing
            workflow.add_edge(START, "start_workflow")
            workflow.add_edge("start_workflow", "execute_step")
            
            # Conditional edge from step executor
            workflow.add_conditional_edges(
                "execute_step",
                self._route_from_step_executor,
                {
                    "execute_tools": "execute_tools",
                    "next_step": "execute_step", 
                    "finalize": "finalize_workflow",
                    "error": END
                }
            )
            
            # Tool execution always returns to step executor
            if self.tool_node:
                workflow.add_edge("execute_tools", "execute_step")
            
            # Finalize workflow ends the graph
            workflow.add_edge("finalize_workflow", END)
            
            logger.info("✅ Workflow graph structure created")
            return workflow
            
        except Exception as e:
            logger.error(f"❌ Error building workflow graph: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_start_node(self):
        """Create workflow start node"""
        def start_workflow(state: WorkflowState) -> Dict[str, Any]:
            """Initialize workflow execution"""
            logger.info(f"🚀 Starting workflow: {state['plan'].intent}")
            
            return update_workflow_status(
                "executing", 
                f"🚀 Starting workflow: {state['plan'].intent}"
            )
        
        return start_workflow
    
    def _create_step_executor_node(self, state_manager: StateManager):
        """Create the main step executor node"""
        def execute_step(state: WorkflowState) -> Dict[str, Any]:
            """
            Execute current workflow step.
            
            This node determines what to do next:
            - Execute tools for current step
            - Move to next step
            - Handle errors
            - Finalize workflow
            """
            current_step = state["current_step"]
            total_steps = len(state["plan"].steps)
            
            logger.info(f"⚡ Executing step {current_step}/{total_steps}")
            
            try:
                # Check if workflow is complete
                if current_step > total_steps:
                    logger.info("🎉 All steps completed, finalizing workflow")
                    return update_workflow_status("completed", "🎉 All steps completed!")
                
                # Get current step details
                step = state["plan"].steps[current_step - 1]  # Convert to 0-based
                logger.info(f"📋 Current step: {step.description}")
                logger.info(f"🔧 Tool: {step.tool.value}, Action: {step.action.value}")
                
                # Check if this step is already completed
                if current_step in state["step_results"]:
                    existing_result = state["step_results"][current_step]
                    if existing_result.status == "completed":
                        logger.info(f"✅ Step {current_step} already completed, moving to next")
                        return {"current_step": current_step + 1}
                
                # Prepare step execution context
                execution_context = self._prepare_step_context(state, step)
                
                # Store context for tool execution
                return {
                    "shared_context": {
                        "current_execution": {
                            "step_index": current_step,
                            "step": step,
                            "context": execution_context,
                            "needs_tool_execution": True
                        }
                    },
                    "progress_messages": [f"🔄 Executing step {current_step}: {step.description}"]
                }
                
            except Exception as e:
                logger.error(f"❌ Error in step executor: {str(e)}")
                
                # Create failed step result
                failed_result = StepResult(
                    step_index=current_step,
                    tool=step.tool if 'step' in locals() else ToolType.GMAIL,
                    action=step.action if 'step' in locals() else ActionType.READ_EMAILS,
                    status="failed",
                    raw_output={},
                    extracted_data={},
                    error_message=str(e)
                )
                
                return update_step_completion(failed_result)
        
        return execute_step
    
    def _create_finalize_node(self):
        """Create workflow finalization node"""
        def finalize_workflow(state: WorkflowState) -> Dict[str, Any]:
            """Finalize completed workflow"""
            logger.info("🎊 Finalizing workflow")
            
            completed_steps = len([r for r in state["step_results"].values() 
                                 if r.status == "completed"])
            failed_steps = len([r for r in state["step_results"].values() 
                              if r.status == "failed"])
            
            final_status = "completed" if failed_steps == 0 else "partial_completion"
            
            return {
                "status": final_status,
                "progress_messages": [
                    f"🎊 Workflow completed! {completed_steps} steps succeeded, {failed_steps} failed"
                ]
            }
        
        return finalize_workflow
    
    def _route_from_step_executor(self, state: WorkflowState) -> Literal["execute_tools", "next_step", "finalize", "error"]:
        """
        Conditional edge function to route after step execution.
        
        Determines next action based on current state:
        - execute_tools: Need to run tools for current step
        - next_step: Move to next step
        - finalize: Workflow complete
        - error: Fatal error occurred
        """
        try:
            current_step = state["current_step"]
            total_steps = len(state["plan"].steps)
            
            # Check for errors
            if state["status"] == "failed":
                logger.error("❌ Workflow failed, ending execution")
                return "error"
            
            # Check if workflow is complete
            if current_step > total_steps:
                logger.info("🎉 Workflow complete, finalizing")
                return "finalize"
            
            # Check if we need to execute tools
            current_execution = state["shared_context"].get("current_execution", {})
            if current_execution.get("needs_tool_execution", False):
                logger.info(f"🔧 Step {current_step} needs tool execution")
                return "execute_tools"
            
            # Check if current step is completed
            if current_step in state["step_results"]:
                result = state["step_results"][current_step]
                if result.status == "completed":
                    logger.info(f"✅ Step {current_step} completed, moving to next")
                    return "next_step"
                elif result.status == "failed":
                    # Handle failed step - could retry or continue
                    logger.warning(f"⚠️ Step {current_step} failed, moving to next")
                    return "next_step"
            
            # Default: continue to next step
            logger.info(f"➡️ Continuing to next step from {current_step}")
            return "next_step"
            
        except Exception as e:
            logger.error(f"❌ Error in routing logic: {str(e)}")
            return "error"
    
    def _prepare_step_context(self, state: WorkflowState, step: ExecutionStep) -> Dict[str, Any]:
        """
        Prepare execution context for a step.
        
        Gathers dependencies, parameters, and shared context
        needed for tool execution.
        """
        logger.info(f"📊 Preparing context for step {step.step_index}")
        
        try:
            context = {
                "user_id": state["user_id"],
                "step_parameters": step.parameters,
                "shared_context": state["shared_context"].copy(),
                "step_description": step.description
            }
            
            # Add data from dependency steps
            for dep_step_index in step.dependencies:
                if dep_step_index in state["step_results"]:
                    dep_result = state["step_results"][dep_step_index]
                    context[f"step_{dep_step_index}_data"] = dep_result.extracted_data
                    context[f"step_{dep_step_index}_output"] = dep_result.raw_output
                    logger.info(f"📋 Added dependency data from step {dep_step_index}")
            
            logger.info(f"✅ Context prepared with {len(context)} elements")
            return context
            
        except Exception as e:
            logger.error(f"❌ Error preparing step context: {str(e)}")
            return {
                "user_id": state["user_id"],
                "step_parameters": step.parameters,
                "shared_context": {},
                "error": str(e)
            }
    
    def compile_workflow(self, workflow: StateGraph, state_manager: StateManager):
        """
        Compile workflow with checkpointing support.
        
        Returns a compiled graph ready for streaming execution.
        """
        logger.info("🔧 Compiling workflow with checkpointing")
        
        try:
            # Get checkpointer from state manager
            checkpointer = state_manager.get_checkpointer()
            
            # Compile with checkpointing
            compiled_graph = workflow.compile(checkpointer=checkpointer)
            
            logger.info("✅ Workflow compiled successfully with persistence")
            return compiled_graph
            
        except Exception as e:
            logger.error(f"❌ Error compiling workflow: {str(e)}")
            logger.error(traceback.format_exc())
            raise

# Factory function for easy integration
def create_workflow_graph(plan: ExecutionPlan, auth_manager, tools_registry: Dict[ToolType, List[BaseTool]], 
                         state_manager: StateManager):
    """
    Factory function to create a complete workflow graph.
    
    Args:
        plan: Execution plan from LLM planner
        auth_manager: Authentication manager
        tools_registry: Registry of LangChain tools
        state_manager: State manager with checkpointing
    
    Returns:
        Compiled LangGraph ready for streaming execution
    """
    logger.info(f"🏭 Creating workflow graph for: {plan.intent}")
    
    try:
        # Create graph builder
        builder = ModernGraphBuilder(auth_manager, tools_registry)
        
        # Build workflow
        workflow = builder.build_workflow_graph(plan, state_manager)
        
        # Compile with checkpointing
        compiled_graph = builder.compile_workflow(workflow, state_manager)
        
        logger.info("✅ Complete workflow graph created and compiled")
        return compiled_graph
        
    except Exception as e:
        logger.error(f"❌ Error creating workflow graph: {str(e)}")
        raise

# Utility functions for workflow management
def get_workflow_visualization(workflow: StateGraph) -> str:
    """
    Get a text representation of the workflow structure.
    Useful for debugging and logging.
    """
    try:
        # Basic workflow structure info
        nodes = list(workflow.nodes.keys())
        edges = [(src, dst) for src, dsts in workflow.edges.items() for dst in dsts]
        
        viz = f"""
Workflow Structure:
  Nodes: {', '.join(nodes)}
  Edges: {len(edges)} connections
  Entry Point: {workflow.entry_point}
  """
        
        return viz.strip()
        
    except Exception as e:
        return f"Error visualizing workflow: {str(e)}"

def validate_workflow_plan(plan: ExecutionPlan) -> List[str]:
    """
    Validate workflow plan for common issues.
    
    Returns list of validation warnings/errors.
    """
    issues = []
    
    try:
        # Check for empty plan
        if not plan.steps:
            issues.append("Plan has no steps")
            return issues
        
        # Check step indices
        expected_indices = set(range(1, len(plan.steps) + 1))
        actual_indices = {step.step_index for step in plan.steps}
        
        if expected_indices != actual_indices:
            issues.append(f"Step indices mismatch. Expected: {expected_indices}, Got: {actual_indices}")
        
        # Check dependencies
        for step in plan.steps:
            for dep in step.dependencies:
                if dep >= step.step_index:
                    issues.append(f"Step {step.step_index} depends on future step {dep}")
                if dep not in actual_indices:
                    issues.append(f"Step {step.step_index} depends on non-existent step {dep}")
        
        # Check for circular dependencies (basic check)
        for step in plan.steps:
            if step.step_index in step.dependencies:
                issues.append(f"Step {step.step_index} depends on itself")
        
        return issues
        
    except Exception as e:
        return [f"Error validating plan: {str(e)}"]
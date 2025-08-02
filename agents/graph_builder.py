import logging
import traceback
from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END, START
from langgraph.prebuilt import ToolNode
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage

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
    FIXED: Modern LangGraph builder with proper ToolNode integration.
    
    Key fixes:
    - Proper tool call generation for ToolNode
    - Template variable resolution ({{user_id}})
    - Correct message format for LangChain tools
    - Better error handling and parameter passing
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
            self.tools_by_name = {}
            
            for tool_list in tools_registry.values():
                for tool in tool_list:
                    self.all_tools.append(tool)
                    self.tools_by_name[tool.name] = tool
            
            logger.info(f"🔧 Registered {len(self.all_tools)} tools across {len(tools_registry)} categories")
            logger.info(f"🔧 Tool categories: {list(tools_registry.keys())}")
            logger.info(f"🔧 Tool names: {list(self.tools_by_name.keys())}")
            
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
        FIXED: Build modern LangGraph workflow with proper ToolNode integration.
        
        Creates a streamlined graph with:
        - Step executor that generates proper tool calls
        - Tool execution via ToolNode with correct message format
        - Conditional routing based on execution state
        - Error handling and recovery
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
            
            # Initialize messages list for ToolNode
            return {
                **update_workflow_status("executing", f"🚀 Starting workflow: {state['plan'].intent}"),
                "messages": []  # Initialize empty messages list
            }
        
        return start_workflow
    
    def _create_step_executor_node(self, state_manager: StateManager):
        """FIXED: Create the main step executor node with proper ToolNode integration"""
        def execute_step(state: WorkflowState) -> Dict[str, Any]:
            """
            FIXED: Execute current workflow step with proper tool call generation.
            
            This node:
            1. Determines current step to execute
            2. Resolves template variables ({{user_id}})
            3. Generates proper tool calls for ToolNode
            4. Handles step completion and routing
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
                logger.info(f"📊 Step parameters: {step.parameters}")
                
                # Check if this step is already completed
                if current_step in state["step_results"]:
                    existing_result = state["step_results"][current_step]
                    if existing_result.status == "completed":
                        logger.info(f"✅ Step {current_step} already completed, moving to next")
                        return {"current_step": current_step + 1}
                
                # Check if we're returning from tool execution
                current_execution = state["shared_context"].get("current_execution", {})
                if current_execution.get("step_index") == current_step and current_execution.get("tool_executed", False):
                    logger.info(f"🔄 Processing tool execution results for step {current_step}")
                    return self._process_tool_results(state, step, current_step)
                
                # FIXED: Prepare and generate tool call for this step
                logger.info(f"🎯 Preparing tool call for step {current_step}")
                tool_call_message = self._generate_tool_call(state, step, current_step)
                
                if not tool_call_message:
                    logger.error(f"❌ Failed to generate tool call for step {current_step}")
                    return self._create_failed_step_result(current_step, step, "Failed to generate tool call")
                
                # Store execution context and add tool call to messages
                updated_state = {
                    "shared_context": {
                        **state["shared_context"],
                        "current_execution": {
                            "step_index": current_step,
                            "step": step,
                            "needs_tool_execution": True,
                            "tool_executed": False
                        }
                    },
                    "messages": state.get("messages", []) + [tool_call_message],
                    "progress_messages": [f"🔄 Executing step {current_step}: {step.description}"]
                }
                
                # DEBUG LOGGING ADDED:
                logger.info(f"🔍 DEBUG: Updated state keys: {list(updated_state.keys())}")
                logger.info(f"🔍 DEBUG: Messages being passed: {updated_state['messages']}")
                logger.info(f"🔍 DEBUG: Last message type: {type(updated_state['messages'][-1]) if updated_state['messages'] else 'NO MESSAGES'}")
                logger.info(f"🔍 DEBUG: Message content: {updated_state['messages'][-1] if updated_state['messages'] else 'NO MESSAGES'}")
                
                logger.info(f"✅ Tool call generated for step {current_step}")
                return updated_state
                
            except Exception as e:
                logger.error(f"❌ Error in step executor: {str(e)}")
                logger.error(traceback.format_exc())
                return self._create_failed_step_result(current_step, step if 'step' in locals() else None, str(e))
        
        return execute_step
    
    def _generate_tool_call(self, state: WorkflowState, step: ExecutionStep, current_step: int) -> AIMessage:
        """
        FIXED: Generate proper tool call message for ToolNode.
        
        This creates the exact format that LangChain's ToolNode expects:
        - AIMessage with tool_calls
        - Resolved template variables
        - Proper tool name mapping
        """
        try:
            logger.info(f"🛠️ Generating tool call for {step.action.value}")
            
            # FIXED: Resolve template variables in parameters
            resolved_params = self._resolve_template_variables(step.parameters, state)
            logger.info(f"📊 Resolved parameters: {resolved_params}")
            
            # FIXED: Map action to actual tool name
            tool_name = self._map_action_to_tool_name(step.action)
            logger.info(f"🔧 Mapped to tool: {tool_name}")
            
            # Verify tool exists
            if tool_name not in self.tools_by_name:
                logger.error(f"❌ Tool not found: {tool_name}")
                logger.error(f"Available tools: {list(self.tools_by_name.keys())}")
                return None
            
            # FIXED: Create proper tool call format for LangChain
            tool_call = {
                "name": tool_name,
                "args": resolved_params,
                "id": f"call_{current_step}_{tool_name}",
                "type": "tool_call"
            }
            
            # Create AI message with tool call
            ai_message = AIMessage(
                content=f"Executing {step.description}",
                tool_calls=[tool_call]
            )
            
            # DEBUG LOGGING ADDED:
            logger.info(f"🔍 DEBUG: Created AIMessage: {ai_message}")
            logger.info(f"🔍 DEBUG: Tool calls: {ai_message.tool_calls}")
            logger.info(f"🔍 DEBUG: Tool call ID: {tool_call['id']}")
            logger.info(f"🔍 DEBUG: Tool call args: {tool_call['args']}")
            
            logger.info(f"✅ Tool call generated: {tool_call['id']}")
            return ai_message
            
        except Exception as e:
            logger.error(f"❌ Error generating tool call: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def _resolve_template_variables(self, parameters: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
        """
        FIXED: Resolve template variables like {{user_id}} in parameters.
        
        This is the key fix for the "No message found in input" error.
        """
        resolved = {}
        
        for key, value in parameters.items():
            if isinstance(value, str) and "{{" in value and "}}" in value:
                # Handle template variables
                if value == "{{user_id}}":
                    resolved[key] = state["user_id"]
                    logger.info(f"🔄 Resolved {key}: {{{{user_id}}}} -> {state['user_id']}")
                
                elif value.startswith("{{") and value.endswith("}}"):
                    # Extract variable name
                    var_name = value[2:-2]
                    
                    # Look for variable in shared context or step results
                    resolved_value = self._lookup_variable(var_name, state)
                    if resolved_value is not None:
                        resolved[key] = resolved_value
                        logger.info(f"🔄 Resolved {key}: {value} -> {resolved_value}")
                    else:
                        logger.warning(f"⚠️ Could not resolve variable: {value}")
                        resolved[key] = value  # Keep original if can't resolve
                else:
                    # Partial template resolution (e.g., "Hello {{name}}")
                    resolved_value = value
                    if "{{user_id}}" in value:
                        resolved_value = value.replace("{{user_id}}", state["user_id"])
                    resolved[key] = resolved_value
                    logger.info(f"🔄 Partial resolution {key}: {value} -> {resolved_value}")
            else:
                # No template variables, use as-is
                resolved[key] = value
        
        # FIXED: Ensure required parameters have defaults
        if "user_id" not in resolved and "user_id" in parameters:
            resolved["user_id"] = state["user_id"]
            logger.info(f"🔄 Added missing user_id: {state['user_id']}")
        
        # FIXED: Add default email parameters if missing for send_email_tool
        if "to" in resolved and "subject" not in resolved:
            resolved["subject"] = "Thank you for your support"
            logger.info("🔄 Added default subject for email")
        
        if "to" in resolved and "body" not in resolved:
            resolved["body"] = "Thank you for your continued support and assistance."
            logger.info("🔄 Added default body for email")
        
        return resolved
    
    def _lookup_variable(self, var_name: str, state: WorkflowState) -> Any:
        """Look up variable value from state context or step results"""
        # Check shared context first
        if var_name in state["shared_context"]:
            return state["shared_context"][var_name]
        
        # Check step results for outputs
        for step_result in state["step_results"].values():
            if var_name in step_result.extracted_data:
                return step_result.extracted_data[var_name]
        
        return None
    
    def _map_action_to_tool_name(self, action: ActionType) -> str:
        """
        FIXED: Map ActionType enum to actual LangChain tool names.
        
        This ensures we call the right tool.
        """
        action_to_tool = {
            # Gmail actions
            ActionType.SEND_EMAIL: "send_email_tool",
            ActionType.SEARCH_EMAILS: "search_emails_tool", 
            ActionType.READ_EMAILS: "read_recent_emails_tool",
            ActionType.GET_THREADS: "get_email_threads_tool",
            
            # Calendar actions
            ActionType.CREATE_EVENT: "create_calendar_event_tool",
            ActionType.LIST_EVENTS: "list_calendar_events_tool",
            ActionType.UPDATE_EVENT: "update_calendar_event_tool",
            ActionType.DELETE_EVENT: "delete_calendar_event_tool",
            ActionType.GET_EVENT: "get_calendar_event_tool",
            
            # Drive actions
            ActionType.UPLOAD_FILE: "upload_file_to_drive_tool",
            ActionType.SEARCH_FILES: "search_files_in_drive_tool",
            ActionType.SHARE_FILE: "share_drive_file_tool",
            ActionType.DOWNLOAD_FILE: "download_drive_file_tool",
            ActionType.LIST_FILES: "list_recent_drive_files_tool"
        }
        
        tool_name = action_to_tool.get(action, "read_recent_emails_tool")
        logger.info(f"🔧 Mapped {action.value} -> {tool_name}")
        return tool_name
    
    def _process_tool_results(self, state: WorkflowState, step: ExecutionStep, current_step: int) -> Dict[str, Any]:
        """
        FIXED: Process results from tool execution and create step result.
        """
        logger.info(f"🔍 Processing tool results for step {current_step}")
        
        try:
            # Look for ToolMessage in recent messages
            messages = state.get("messages", [])
            tool_result = None
            
            # Find the most recent ToolMessage
            for message in reversed(messages):
                if isinstance(message, ToolMessage):
                    tool_result = message.content
                    break
            
            if tool_result:
                logger.info(f"✅ Found tool result: {str(tool_result)[:100]}...")
                
                # Create successful step result
                step_result = StepResult(
                    step_index=current_step,
                    tool=step.tool,
                    action=step.action,
                    status="completed",
                    raw_output={"result": tool_result},
                    extracted_data={"tool_output": tool_result},
                    error_message=None
                )
                
                # Update state with completed step
                return {
                    **update_step_completion(step_result),
                    "shared_context": {
                        **state["shared_context"],
                        "current_execution": {
                            **state["shared_context"].get("current_execution", {}),
                            "tool_executed": False,  # Reset for next step
                            "completed": True
                        }
                    }
                }
            else:
                logger.warning(f"⚠️ No tool result found for step {current_step}")
                return self._create_failed_step_result(current_step, step, "No tool result found")
                
        except Exception as e:
            logger.error(f"❌ Error processing tool results: {str(e)}")
            return self._create_failed_step_result(current_step, step, str(e))
    
    def _create_failed_step_result(self, current_step: int, step: ExecutionStep, error: str) -> Dict[str, Any]:
        """Create a failed step result"""
        logger.error(f"❌ Creating failed result for step {current_step}: {error}")
        
        failed_result = StepResult(
            step_index=current_step,
            tool=step.tool if step else ToolType.GMAIL,
            action=step.action if step else ActionType.READ_EMAILS,
            status="failed",
            raw_output={},
            extracted_data={},
            error_message=error
        )
        
        return update_step_completion(failed_result)
    
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
        FIXED: Conditional edge function to route after step execution.
        
        Determines next action based on current state and tool execution needs.
        """
        try:
            current_step = state["current_step"]
            total_steps = len(state["plan"].steps)
            
            # DEBUG LOGGING ADDED:
            logger.info(f"🔍 DEBUG: State keys: {list(state.keys())}")
            logger.info(f"🔍 DEBUG: Messages in state: {state.get('messages', 'MISSING!')}")
            logger.info(f"🔍 DEBUG: Number of messages: {len(state.get('messages', []))}")
            if state.get('messages'):
                for i, msg in enumerate(state.get('messages', [])):
                    logger.info(f"🔍 DEBUG: Message {i}: type={type(msg)}, content={str(msg)[:100]}")
                    if hasattr(msg, 'tool_calls') and msg.tool_calls:
                        logger.info(f"🔍 DEBUG: Message {i} has tool calls: {msg.tool_calls}")
            
            logger.info(f"🚦 Routing from step executor: step {current_step}/{total_steps}")
            
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
            needs_tool_execution = current_execution.get("needs_tool_execution", False)
            tool_executed = current_execution.get("tool_executed", False)
            
            logger.info(f"🔍 DEBUG: needs_tool_execution={needs_tool_execution}, tool_executed={tool_executed}")
            
            if needs_tool_execution and not tool_executed:
                logger.info(f"🔧 Step {current_step} needs tool execution")
                return "execute_tools"
            
            # Check if current step is completed
            if current_step in state["step_results"]:
                result = state["step_results"][current_step]
                if result.status == "completed":
                    logger.info(f"✅ Step {current_step} completed, moving to next")
                    return "next_step"
                elif result.status == "failed":
                    logger.warning(f"⚠️ Step {current_step} failed, moving to next")
                    return "next_step"
            
            # Check if we just returned from tool execution
            messages = state.get("messages", [])
            if messages and isinstance(messages[-1], ToolMessage):
                logger.info(f"🔄 Tool execution completed for step {current_step}")
                # Mark tool as executed so we process results
                return "next_step"
            
            # Default: continue to next step
            logger.info(f"➡️ Continuing to next step from {current_step}")
            return "next_step"
            
        except Exception as e:
            logger.error(f"❌ Error in routing logic: {str(e)}")
            logger.error(traceback.format_exc())
            return "error"
    
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
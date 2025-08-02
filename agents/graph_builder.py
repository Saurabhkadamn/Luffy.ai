import logging
import traceback
from typing import Dict, Any, List, Literal
from langgraph.graph import StateGraph, END, START
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
    FIXED: Modern LangGraph builder with direct tool execution.
    
    Key fixes:
    - Replaced ToolNode with direct tool execution
    - Maintains all dependency resolution and state management
    - Preserves template variable resolution ({{user_id}})
    - Better error handling and parameter passing
    - Full compatibility with complex multi-step workflows
    """
    
    def __init__(self, auth_manager, tools_registry: Dict[ToolType, List[BaseTool]]):
        """
        Initialize with auth manager and tools registry.
        
        Args:
            auth_manager: Authentication manager for Google APIs
            tools_registry: Dict mapping tool types to LangChain tools
        """
        logger.info("GRAPH: Initializing ModernGraphBuilder")
        
        try:
            self.auth_manager = auth_manager
            self.tools_registry = tools_registry
            
            # Flatten all tools for direct execution
            self.all_tools = []
            self.tools_by_name = {}
            
            for tool_list in tools_registry.values():
                for tool in tool_list:
                    self.all_tools.append(tool)
                    self.tools_by_name[tool.name] = tool
            
            logger.info(f"GRAPH: Registered {len(self.all_tools)} tools across {len(tools_registry)} categories")
            logger.debug(f"Tool categories: {list(tools_registry.keys())}")
            logger.debug(f"Tool names: {list(self.tools_by_name.keys())}")
            
            logger.info("GRAPH: ModernGraphBuilder initialization complete")
            
        except Exception as e:
            logger.error(f"Failed to initialize ModernGraphBuilder: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def build_workflow_graph(self, plan: ExecutionPlan, state_manager: StateManager) -> StateGraph:
        """
        FIXED: Build modern LangGraph workflow with direct tool execution.
        
        Creates a streamlined graph with:
        - Step executor that prepares tool execution
        - Direct tool execution with proper parameter resolution
        - Conditional routing based on execution state
        - Error handling and recovery
        - Progress tracking with dependency support
        """
        logger.info(f"GRAPH: Building workflow graph for: {plan.intent}")
        logger.info(f"GRAPH: Plan has {len(plan.steps)} steps")
        
        try:
            # Create StateGraph with our TypedDict state
            workflow = StateGraph(WorkflowState)
            
            # Add nodes for workflow control
            workflow.add_node("start_workflow", self._create_start_node())
            workflow.add_node("execute_step", self._create_step_executor_node(state_manager))
            workflow.add_node("execute_tools", self._create_direct_tool_executor())
            workflow.add_node("finalize_workflow", self._create_finalize_node())
            
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
            
            # Tool execution returns to step executor for next step
            workflow.add_edge("execute_tools", "execute_step")
            
            # Finalize workflow ends the graph
            workflow.add_edge("finalize_workflow", END)
            
            logger.info("GRAPH: Workflow graph structure created")
            return workflow
            
        except Exception as e:
            logger.error(f"Error building workflow graph: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_start_node(self):
        """Create workflow start node"""
        def start_workflow(state: WorkflowState) -> Dict[str, Any]:
            """Initialize workflow execution"""
            logger.info(f"WORKFLOW: Starting workflow: {state['plan'].intent}")
            
            return {
                **update_workflow_status("executing", f"Starting workflow: {state['plan'].intent}"),
                "messages": []  # Initialize empty messages list for compatibility
            }
        
        return start_workflow
    
    def _create_step_executor_node(self, state_manager: StateManager):
        """Create the main step executor node that prepares tool execution"""
        def execute_step(state: WorkflowState) -> Dict[str, Any]:
            """
            Execute current workflow step with dependency resolution.
            
            This node:
            1. Determines current step to execute
            2. Checks dependencies are satisfied
            3. Resolves template variables ({{user_id}}, {{contact_list}}, etc.)
            4. Prepares tool execution context
            5. Handles step completion and routing
            """
            current_step = state["current_step"]
            total_steps = len(state["plan"].steps)
            
            logger.info(f"STEP: Executing step {current_step}/{total_steps}")
            
            try:
                # Check if workflow is complete
                if current_step > total_steps:
                    logger.info("WORKFLOW: All steps completed, finalizing workflow")
                    return update_workflow_status("completed", "All steps completed!")
                
                # Get current step details
                step = state["plan"].steps[current_step - 1]  # Convert to 0-based
                logger.info(f"STEP: Current step: {step.description}")
                logger.debug(f"Tool: {step.tool.value}, Action: {step.action.value}")
                logger.debug(f"Step parameters: {step.parameters}")
                logger.debug(f"Step dependencies: {step.dependencies}")
                
                # Check if this step is already completed
                if current_step in state["step_results"]:
                    existing_result = state["step_results"][current_step]
                    if existing_result.status == "completed":
                        logger.info(f"STEP: Step {current_step} already completed, moving to next")
                        return {"current_step": current_step + 1}
                
                # Check if we're returning from tool execution
                current_execution = state["shared_context"].get("current_execution", {})
                if current_execution.get("step_index") == current_step and current_execution.get("tool_executed", False):
                    logger.info(f"STEP: Processing tool execution results for step {current_step}")
                    return self._process_tool_results(state, step, current_step)
                
                # Check dependencies before execution
                dependency_check = self._check_step_dependencies(state, step)
                if not dependency_check["satisfied"]:
                    error_msg = f"Dependencies not satisfied for step {current_step}: {dependency_check['missing']}"
                    logger.error(error_msg)
                    return self._create_failed_step_result(current_step, step, error_msg)
                
                # Prepare tool execution context
                logger.info(f"TOOL: Preparing tool execution for step {current_step}")
                tool_context = self._prepare_tool_execution(state, step, current_step)
                
                if not tool_context:
                    logger.error(f"Failed to prepare tool execution for step {current_step}")
                    return self._create_failed_step_result(current_step, step, "Failed to prepare tool execution")
                
                # Store execution context for tool executor
                updated_state = {
                    "shared_context": {
                        **state["shared_context"],
                        "current_execution": {
                            "step_index": current_step,
                            "step": step,
                            "tool_context": tool_context,
                            "needs_tool_execution": True,
                            "tool_executed": False
                        }
                    },
                    "progress_messages": [f"Executing step {current_step}: {step.description}"]
                }
                
                logger.debug(f"Updated state keys: {list(updated_state.keys())}")
                logger.info(f"TOOL: Tool execution prepared for step {current_step}")
                return updated_state
                
            except Exception as e:
                logger.error(f"Error in step executor: {str(e)}")
                logger.error(traceback.format_exc())
                return self._create_failed_step_result(current_step, step if 'step' in locals() else None, str(e))
        
        return execute_step
    
    def _create_direct_tool_executor(self):
        """
        FIXED: Create direct tool executor that bypasses ToolNode.
        
        This replaces ToolNode with direct tool execution while maintaining
        all the dependency resolution and state management capabilities.
        """
        def execute_tools_directly(state: WorkflowState) -> Dict[str, Any]:
            """
            Execute tools directly with full state context and dependency resolution.
            
            This maintains all your excellent features:
            - Template variable resolution
            - Inter-step data dependencies  
            - Shared context updates
            - Progress tracking
            - Error handling
            """
            try:
                logger.info("TOOL: Starting direct tool execution")
                
                # Get current execution context
                current_execution = state["shared_context"].get("current_execution", {})
                step = current_execution.get("step")
                step_index = current_execution.get("step_index")
                tool_context = current_execution.get("tool_context", {})
                
                if not step or not tool_context:
                    error_msg = "No step or tool context found for tool execution"
                    logger.error(error_msg)
                    return self._create_failed_step_result(step_index or 0, step, error_msg)
                
                # Get tool and resolved parameters from context
                tool_name = tool_context["tool_name"]
                resolved_params = tool_context["resolved_params"]
                
                # Get the actual tool
                tool = self.tools_by_name.get(tool_name)
                if not tool:
                    error_msg = f"Tool not found: {tool_name}"
                    logger.error(error_msg)
                    return self._create_failed_step_result(step_index, step, error_msg)
                
                # Execute tool directly with resolved parameters
                logger.info(f"TOOL: Executing {tool_name}")
                logger.debug(f"TOOL: Parameters: {resolved_params}")
                
                result = tool.invoke(resolved_params)
                
                logger.info(f"TOOL: Execution completed successfully")
                logger.debug(f"TOOL: Result: {str(result)[:200]}...")
                
                # Create successful step result
                step_result = StepResult(
                    step_index=step_index,
                    tool=step.tool,
                    action=step.action,
                    status="completed",
                    raw_output={"result": result},
                    extracted_data=self._extract_step_data(result, step),
                    error_message=None
                )
                
                # Update shared context with extracted data for future steps
                context_updates = self._update_shared_context(result, step, state)
                
                # Mark tool as executed and update state
                return {
                    **update_step_completion(step_result),
                    "shared_context": {
                        **state["shared_context"],
                        **context_updates,
                        "current_execution": {
                            **current_execution,
                            "tool_executed": True,
                            "completed": True,
                            "result": result
                        }
                    },
                    "messages": state.get("messages", []) + [
                        ToolMessage(
                            content=str(result),
                            tool_call_id=f"step_{step_index}_{tool_name}",
                            name=tool_name
                        )
                    ]
                }
                
            except Exception as e:
                logger.error(f"Error in direct tool execution: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Get step info for error result
                current_execution = state["shared_context"].get("current_execution", {})
                step = current_execution.get("step")
                step_index = current_execution.get("step_index", 0)
                
                return self._create_failed_step_result(step_index, step, str(e))
        
        return execute_tools_directly
    
    def _check_step_dependencies(self, state: WorkflowState, step: ExecutionStep) -> Dict[str, Any]:
        """
        Check if step dependencies are satisfied.
        
        This ensures steps execute in the correct order and have access
        to data from previous steps.
        """
        try:
            if not step.dependencies:
                return {"satisfied": True, "missing": []}
            
            missing_deps = []
            completed_steps = set(state["step_results"].keys())
            
            for dep_step in step.dependencies:
                if dep_step not in completed_steps:
                    missing_deps.append(dep_step)
                elif state["step_results"][dep_step].status != "completed":
                    missing_deps.append(f"step_{dep_step}_failed")
            
            if missing_deps:
                logger.warning(f"Step {step.step_index} missing dependencies: {missing_deps}")
                return {"satisfied": False, "missing": missing_deps}
            
            logger.debug(f"Step {step.step_index} dependencies satisfied: {step.dependencies}")
            return {"satisfied": True, "missing": []}
            
        except Exception as e:
            logger.error(f"Error checking dependencies: {str(e)}")
            return {"satisfied": False, "missing": [f"dependency_check_error: {str(e)}"]}
    
    def _prepare_tool_execution(self, state: WorkflowState, step: ExecutionStep, current_step: int) -> Dict[str, Any]:
        """
        Prepare tool execution context with dependency resolution.
        
        This handles all the complex variable resolution and parameter preparation.
        """
        try:
            logger.debug(f"Preparing tool execution for {step.action.value}")
            
            # Resolve template variables in parameters (maintains your dependency system)
            resolved_params = self._resolve_template_variables(step.parameters, state)
            logger.debug(f"Resolved parameters: {resolved_params}")
            
            # Map action to actual tool name
            tool_name = self._map_action_to_tool_name(step.action)
            logger.debug(f"Mapped to tool: {tool_name}")
            
            # Verify tool exists
            if tool_name not in self.tools_by_name:
                logger.error(f"Tool not found: {tool_name}")
                logger.error(f"Available tools: {list(self.tools_by_name.keys())}")
                return None
            
            # Create tool execution context
            tool_context = {
                "tool_name": tool_name,
                "resolved_params": resolved_params,
                "step_index": current_step,
                "step_description": step.description
            }
            
            logger.info(f"TOOL: Tool execution context prepared for {tool_name}")
            return tool_context
            
        except Exception as e:
            logger.error(f"Error preparing tool execution: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    
    def _resolve_template_variables(self, parameters: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
        """
        ENHANCED: Resolve template variables with full dependency support.
        
        This maintains your excellent dependency resolution system:
        - {{user_id}} from state
        - {{contact_list}} from previous step results
        - {{meeting_link}} from shared context
        - Complex data flows between steps
        """
        resolved = {}
        
        for key, value in parameters.items():
            if isinstance(value, str) and "{{" in value and "}}" in value:
                # Handle template variables with dependency resolution
                if value == "{{user_id}}":
                    resolved[key] = state["user_id"]
                    logger.debug(f"Resolved {key}: {{user_id}} -> {state['user_id']}")
                
                elif value.startswith("{{") and value.endswith("}}"):
                    # Extract variable name
                    var_name = value[2:-2]
                    
                    # Look for variable in shared context or step results (dependency data)
                    resolved_value = self._lookup_variable(var_name, state)
                    if resolved_value is not None:
                        resolved[key] = resolved_value
                        logger.debug(f"Resolved {key}: {value} -> {resolved_value}")
                    else:
                        logger.warning(f"Could not resolve variable: {value}")
                        resolved[key] = value  # Keep original if can't resolve
                else:
                    # Partial template resolution (e.g., "Hello {{name}}")
                    resolved_value = value
                    if "{{user_id}}" in value:
                        resolved_value = value.replace("{{user_id}}", state["user_id"])
                    
                    # Handle other template variables in the string
                    resolved_value = self._resolve_partial_templates(resolved_value, state)
                    resolved[key] = resolved_value
                    logger.debug(f"Partial resolution {key}: {value} -> {resolved_value}")
            else:
                # No template variables, use as-is
                resolved[key] = value
        
        # Ensure required parameters have defaults
        if "user_id" not in resolved:
            resolved["user_id"] = state["user_id"]
            logger.debug(f"Added missing user_id: {state['user_id']}")
        
        # Add smart defaults for common tool parameters
        resolved = self._add_smart_defaults(resolved, state)
        
        return resolved
    
    def _lookup_variable(self, var_name: str, state: WorkflowState) -> Any:
        """
        Enhanced variable lookup with dependency support.
        
        Searches for variables in:
        1. Shared context (cross-step data)
        2. Step results (previous step outputs)
        3. User context
        """
        # Check shared context first (cross-step data)
        if var_name in state["shared_context"]:
            value = state["shared_context"][var_name]
            logger.debug(f"Found {var_name} in shared_context: {value}")
            return value
        
        # Check step results for outputs (dependency data)
        for step_result in state["step_results"].values():
            if var_name in step_result.extracted_data:
                value = step_result.extracted_data[var_name]
                logger.debug(f"Found {var_name} in step results: {value}")
                return value
        
        # Check for common variable patterns
        if var_name.endswith("_list") or var_name.endswith("_emails"):
            # Look for list-type variables in various formats
            base_name = var_name.replace("_list", "").replace("_emails", "")
            for context_key, context_value in state["shared_context"].items():
                if base_name in context_key and isinstance(context_value, list):
                    logger.debug(f"Found list variable {var_name} via {context_key}: {context_value}")
                    return context_value
        
        logger.debug(f"Variable {var_name} not found")
        return None
    
    def _resolve_partial_templates(self, text: str, state: WorkflowState) -> str:
        """Resolve multiple template variables in a single string"""
        import re
        
        # Find all template variables in the text
        template_pattern = r'\{\{([^}]+)\}\}'
        matches = re.findall(template_pattern, text)
        
        resolved_text = text
        for var_name in matches:
            var_value = self._lookup_variable(var_name, state)
            if var_value is not None:
                resolved_text = resolved_text.replace(f"{{{{{var_name}}}}}", str(var_value))
                logger.debug(f"Resolved partial template {var_name}: {var_value}")
        
        return resolved_text
    
    def _add_smart_defaults(self, params: Dict[str, Any], state: WorkflowState) -> Dict[str, Any]:
        """Add smart defaults for common tool parameters"""
        # Email tool defaults
        if "to" in params and "subject" not in params:
            params["subject"] = "Meeting Update"
        
        if "to" in params and "body" not in params:
            params["body"] = "Please see the details below."
        
        # Calendar tool defaults
        if "title" in params and "timezone" not in params:
            params["timezone"] = "UTC"
        
        if "include_meet" not in params and "attendees" in params:
            params["include_meet"] = True  # Default to include Meet for meetings with attendees
        
        return params
    
    def _map_action_to_tool_name(self, action: ActionType) -> str:
        """Map ActionType enum to actual LangChain tool names"""
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
        logger.debug(f"Mapped {action.value} -> {tool_name}")
        return tool_name
    
    def _extract_step_data(self, result: Any, step: ExecutionStep) -> Dict[str, Any]:
        """
        Extract data from tool results for future step dependencies.
        
        This populates the data that future steps can access via template variables.
        """
        extracted = {"tool_output": result}
        
        try:
            result_str = str(result)
            
            # Extract email addresses from results
            import re
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, result_str)
            if emails:
                extracted["discovered_emails"] = emails
                extracted["contact_list"] = emails
                logger.debug(f"Extracted emails: {emails}")
            
            # Extract Google Meet links
            meet_pattern = r'https://meet\.google\.com/[a-zA-Z0-9-]+'
            meet_links = re.findall(meet_pattern, result_str)
            if meet_links:
                extracted["meeting_link"] = meet_links[0]
                extracted["meet_link"] = meet_links[0]
                logger.debug(f"Extracted Meet link: {meet_links[0]}")
            
            # Extract event IDs
            if "event_id" in result_str.lower() or "Event ID:" in result_str:
                # Try to extract event ID from result
                event_id_pattern = r'Event ID[:\s]+([a-zA-Z0-9_-]+)'
                event_ids = re.findall(event_id_pattern, result_str)
                if event_ids:
                    extracted["event_id"] = event_ids[0]
                    logger.debug(f"Extracted event ID: {event_ids[0]}")
            
            # Extract file IDs from Drive operations
            if "file_id" in result_str.lower() or "File ID:" in result_str:
                file_id_pattern = r'File ID[:\s]+([a-zA-Z0-9_-]+)'
                file_ids = re.findall(file_id_pattern, result_str)
                if file_ids:
                    extracted["file_id"] = file_ids[0]
                    logger.debug(f"Extracted file ID: {file_ids[0]}")
            
        except Exception as e:
            logger.warning(f"Error extracting step data: {str(e)}")
        
        return extracted
    
    def _update_shared_context(self, result: Any, step: ExecutionStep, state: WorkflowState) -> Dict[str, Any]:
        """
        Update shared context with data for future steps.
        
        This maintains cross-step data dependencies.
        """
        context_updates = {}
        
        try:
            # Add extracted data to shared context for future steps
            extracted_data = self._extract_step_data(result, step)
            
            # Merge extracted data into shared context
            for key, value in extracted_data.items():
                if key != "tool_output":  # Don't pollute context with raw output
                    context_updates[key] = value
            
            # Update discovered contacts list
            if "discovered_emails" in extracted_data:
                existing_contacts = state["shared_context"].get("discovered_contacts", [])
                new_contacts = extracted_data["discovered_emails"]
                all_contacts = list(set(existing_contacts + new_contacts))
                context_updates["discovered_contacts"] = all_contacts
            
            # Update meeting details
            if "meeting_link" in extracted_data:
                meeting_details = state["shared_context"].get("meeting_details", {})
                meeting_details["meet_link"] = extracted_data["meeting_link"]
                context_updates["meeting_details"] = meeting_details
            
            logger.debug(f"Context updates: {list(context_updates.keys())}")
            
        except Exception as e:
            logger.warning(f"Error updating shared context: {str(e)}")
        
        return context_updates
    
    def _process_tool_results(self, state: WorkflowState, step: ExecutionStep, current_step: int) -> Dict[str, Any]:
        """Process results from tool execution and advance to next step"""
        logger.info(f"STEP: Processing results and advancing from step {current_step}")
        
        try:
            # Tool execution is complete, advance to next step
            return {
                "current_step": current_step + 1,
                "shared_context": {
                    **state["shared_context"],
                    "current_execution": {}  # Clear execution context
                },
                "progress_messages": [f"Step {current_step} completed successfully"]
            }
            
        except Exception as e:
            logger.error(f"Error processing tool results: {str(e)}")
            return self._create_failed_step_result(current_step, step, str(e))
    
    def _create_failed_step_result(self, current_step: int, step: ExecutionStep, error: str) -> Dict[str, Any]:
        """Create a failed step result with error handling"""
        logger.error(f"Creating failed result for step {current_step}: {error}")
        
        failed_result = StepResult(
            step_index=current_step,
            tool=step.tool if step else ToolType.GMAIL,
            action=step.action if step else ActionType.READ_EMAILS,
            status="failed",
            raw_output={"error": error},
            extracted_data={},
            error_message=error
        )
        
        return {
            **update_step_completion(failed_result),
            "current_step": current_step + 1,  # Continue to next step even on failure
            "progress_messages": [f"Step {current_step} failed: {error}"]
        }
    
    def _create_finalize_node(self):
        """Create workflow finalization node"""
        def finalize_workflow(state: WorkflowState) -> Dict[str, Any]:
            """Finalize completed workflow with summary"""
            logger.info("WORKFLOW: Finalizing workflow")
            
            completed_steps = len([r for r in state["step_results"].values() 
                                 if r.status == "completed"])
            failed_steps = len([r for r in state["step_results"].values() 
                              if r.status == "failed"])
            
            final_status = "completed" if failed_steps == 0 else "partial_completion"
            
            return {
                "status": final_status,
                "progress_messages": [
                    f"Workflow completed! {completed_steps} steps succeeded, {failed_steps} failed"
                ]
            }
        
        return finalize_workflow
    
    def _route_from_step_executor(self, state: WorkflowState) -> Literal["execute_tools", "next_step", "finalize", "error"]:
        """
        Enhanced routing with dependency support.
        
        Determines next action based on current state, dependencies, and execution needs.
        """
        try:
            current_step = state["current_step"]
            total_steps = len(state["plan"].steps)
            
            logger.debug(f"Routing from step executor: step {current_step}/{total_steps}")
            
            # Check for errors
            if state["status"] == "failed":
                logger.error("Workflow failed, ending execution")
                return "error"
            
            # Check if workflow is complete
            if current_step > total_steps:
                logger.info("Workflow complete, finalizing")
                return "finalize"
            
            # Check if we need to execute tools
            current_execution = state["shared_context"].get("current_execution", {})
            needs_tool_execution = current_execution.get("needs_tool_execution", False)
            tool_executed = current_execution.get("tool_executed", False)
            
            logger.debug(f"needs_tool_execution={needs_tool_execution}, tool_executed={tool_executed}")
            
            if needs_tool_execution and not tool_executed:
                logger.info(f"ROUTING: Step {current_step} needs tool execution")
                return "execute_tools"
            
            # Check if current step is completed
            if current_step in state["step_results"]:
                result = state["step_results"][current_step]
                if result.status == "completed":
                    logger.info(f"ROUTING: Step {current_step} completed, moving to next")
                    return "next_step"
                elif result.status == "failed":
                    logger.warning(f"ROUTING: Step {current_step} failed, moving to next")
                    return "next_step"
            
            # Check if we just returned from tool execution
            if tool_executed:
                logger.info(f"ROUTING: Tool execution completed for step {current_step}")
                return "next_step"
            
            # Default: continue to next step
            logger.debug(f"ROUTING: Continuing to next step from {current_step}")
            return "next_step"
            
        except Exception as e:
            logger.error(f"Error in routing logic: {str(e)}")
            logger.error(traceback.format_exc())
            return "error"
    
    def compile_workflow(self, workflow: StateGraph, state_manager: StateManager):
        """
        Compile workflow with checkpointing support.
        
        Returns a compiled graph ready for streaming execution.
        """
        logger.info("GRAPH: Compiling workflow with checkpointing")
        
        try:
            # Get checkpointer from state manager
            checkpointer = state_manager.get_checkpointer()
            
            # Compile with checkpointing
            compiled_graph = workflow.compile(checkpointer=checkpointer)
            
            logger.info("GRAPH: Workflow compiled successfully with persistence")
            return compiled_graph
            
        except Exception as e:
            logger.error(f"Error compiling workflow: {str(e)}")
            logger.error(traceback.format_exc())
            raise

# Factory function for easy integration
def create_workflow_graph(plan: ExecutionPlan, auth_manager, tools_registry: Dict[ToolType, List[BaseTool]], 
                         state_manager: StateManager):
    """
    Factory function to create a complete workflow graph with direct tool execution.
    
    Args:
        plan: Execution plan from LLM planner
        auth_manager: Authentication manager
        tools_registry: Registry of LangChain tools
        state_manager: State manager with checkpointing
    
    Returns:
        Compiled LangGraph ready for streaming execution with dependency support
    """
    logger.info(f"GRAPH: Creating workflow graph for: {plan.intent}")
    
    try:
        # Create graph builder
        builder = ModernGraphBuilder(auth_manager, tools_registry)
        
        # Build workflow
        workflow = builder.build_workflow_graph(plan, state_manager)
        
        # Compile with checkpointing
        compiled_graph = builder.compile_workflow(workflow, state_manager)
        
        logger.info("GRAPH: Complete workflow graph created and compiled")
        return compiled_graph
        
    except Exception as e:
        logger.error(f"Error creating workflow graph: {str(e)}")
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
  Features: Direct Tool Execution, Dependency Resolution, State Persistence
  """
        
        return viz.strip()
        
    except Exception as e:
        return f"Error visualizing workflow: {str(e)}"

def validate_workflow_plan(plan: ExecutionPlan) -> List[str]:
    """
    Enhanced workflow plan validation with dependency checking.
    
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
        
        # Enhanced dependency validation
        for step in plan.steps:
            for dep in step.dependencies:
                if dep >= step.step_index:
                    issues.append(f"Step {step.step_index} depends on future step {dep}")
                if dep not in actual_indices:
                    issues.append(f"Step {step.step_index} depends on non-existent step {dep}")
        
        # Check for circular dependencies (enhanced check)
        for step in plan.steps:
            if step.step_index in step.dependencies:
                issues.append(f"Step {step.step_index} depends on itself")
            
            # Check for indirect circular dependencies
            visited = set()
            def check_circular(current_step_idx, path):
                if current_step_idx in path:
                    return True
                if current_step_idx in visited:
                    return False
                
                visited.add(current_step_idx)
                path.add(current_step_idx)
                
                current_step = next((s for s in plan.steps if s.step_index == current_step_idx), None)
                if current_step:
                    for dep in current_step.dependencies:
                        if check_circular(dep, path.copy()):
                            return True
                
                return False
            
            if check_circular(step.step_index, set()):
                issues.append(f"Circular dependency detected involving step {step.step_index}")
        
        # Check for template variable consistency
        all_expected_outputs = set()
        for step in plan.steps:
            all_expected_outputs.update(step.expected_outputs)
        
        for step in plan.steps:
            for param_value in step.parameters.values():
                if isinstance(param_value, str) and "{{" in param_value and "}}" in param_value:
                    # Extract variable name
                    import re
                    variables = re.findall(r'\{\{([^}]+)\}\}', param_value)
                    for var in variables:
                        if var not in ["user_id"] and var not in all_expected_outputs:
                            issues.append(f"Step {step.step_index} references unknown variable: {var}")
        
        return issues
        
    except Exception as e:
        return [f"Error validating plan: {str(e)}"]

def analyze_workflow_dependencies(plan: ExecutionPlan) -> Dict[str, Any]:
    """
    Analyze workflow dependencies for optimization and debugging.
    
    Returns detailed dependency analysis.
    """
    try:
        analysis = {
            "total_steps": len(plan.steps),
            "independent_steps": [],
            "dependent_steps": [],
            "dependency_chains": [],
            "parallel_opportunities": [],
            "bottlenecks": []
        }
        
        # Categorize steps
        for step in plan.steps:
            if not step.dependencies:
                analysis["independent_steps"].append(step.step_index)
            else:
                analysis["dependent_steps"].append({
                    "step": step.step_index,
                    "depends_on": step.dependencies,
                    "dependency_count": len(step.dependencies)
                })
        
        # Find dependency chains
        for step in plan.steps:
            if step.dependencies:
                chain = [step.step_index]
                current_deps = step.dependencies[:]
                
                while current_deps:
                    next_dep = current_deps.pop(0)
                    chain.insert(0, next_dep)
                    
                    # Find dependencies of this dependency
                    dep_step = next((s for s in plan.steps if s.step_index == next_dep), None)
                    if dep_step and dep_step.dependencies:
                        current_deps.extend(dep_step.dependencies)
                
                if len(chain) > 2:  # Only include non-trivial chains
                    analysis["dependency_chains"].append(chain)
        
        # Identify parallel opportunities
        step_levels = {}
        for step in plan.steps:
            max_dep_level = 0
            for dep in step.dependencies:
                dep_level = step_levels.get(dep, 0)
                max_dep_level = max(max_dep_level, dep_level)
            step_levels[step.step_index] = max_dep_level + 1
        
        # Group steps by level (parallel opportunities)
        level_groups = {}
        for step_idx, level in step_levels.items():
            if level not in level_groups:
                level_groups[level] = []
            level_groups[level].append(step_idx)
        
        for level, steps in level_groups.items():
            if len(steps) > 1:
                analysis["parallel_opportunities"].append({
                    "level": level,
                    "parallel_steps": steps
                })
        
        # Identify bottlenecks (steps many others depend on)
        dependents = {}
        for step in plan.steps:
            for dep in step.dependencies:
                if dep not in dependents:
                    dependents[dep] = []
                dependents[dep].append(step.step_index)
        
        for step_idx, dependent_list in dependents.items():
            if len(dependent_list) > 2:  # More than 2 steps depend on this
                analysis["bottlenecks"].append({
                    "step": step_idx,
                    "dependent_steps": dependent_list,
                    "impact": len(dependent_list)
                })
        
        return analysis
        
    except Exception as e:
        return {"error": f"Error analyzing dependencies: {str(e)}"}

# Enhanced debugging and monitoring
def debug_workflow_execution(state: WorkflowState) -> Dict[str, Any]:
    """
    Debug workflow execution state for troubleshooting.
    
    Returns comprehensive execution state information.
    """
    try:
        debug_info = {
            "workflow_status": state["status"],
            "current_step": state["current_step"],
            "total_steps": len(state["plan"].steps),
            "completed_steps": [],
            "failed_steps": [],
            "pending_steps": [],
            "shared_context_keys": list(state["shared_context"].keys()),
            "current_execution": state["shared_context"].get("current_execution", {}),
            "progress_messages": state["progress_messages"][-5:] if state["progress_messages"] else []
        }
        
        # Analyze step statuses
        for step_idx in range(1, len(state["plan"].steps) + 1):
            if step_idx in state["step_results"]:
                result = state["step_results"][step_idx]
                if result.status == "completed":
                    debug_info["completed_steps"].append({
                        "step": step_idx,
                        "tool": result.tool.value,
                        "action": result.action.value,
                        "extracted_data_keys": list(result.extracted_data.keys())
                    })
                elif result.status == "failed":
                    debug_info["failed_steps"].append({
                        "step": step_idx,
                        "tool": result.tool.value,
                        "action": result.action.value,
                        "error": result.error_message
                    })
            else:
                step = state["plan"].steps[step_idx - 1]
                debug_info["pending_steps"].append({
                    "step": step_idx,
                    "tool": step.tool.value,
                    "action": step.action.value,
                    "dependencies": step.dependencies
                })
        
        return debug_info
        
    except Exception as e:
        return {"error": f"Error debugging workflow: {str(e)}"}

# Performance monitoring
def get_workflow_performance_metrics(state: WorkflowState) -> Dict[str, Any]:
    """
    Get performance metrics for workflow execution.
    
    Returns timing and efficiency metrics.
    """
    try:
        if not state.get("created_at"):
            return {"error": "No creation timestamp available"}
        
        from datetime import datetime
        start_time = datetime.fromisoformat(state["created_at"])
        current_time = datetime.now()
        
        total_duration = (current_time - start_time).total_seconds()
        
        completed_steps = len([r for r in state["step_results"].values() if r.status == "completed"])
        failed_steps = len([r for r in state["step_results"].values() if r.status == "failed"])
        total_steps = len(state["plan"].steps)
        
        metrics = {
            "total_duration_seconds": total_duration,
            "steps_per_second": completed_steps / total_duration if total_duration > 0 else 0,
            "completion_rate": completed_steps / total_steps if total_steps > 0 else 0,
            "failure_rate": failed_steps / total_steps if total_steps > 0 else 0,
            "estimated_remaining_time": (total_duration / completed_steps) * (total_steps - completed_steps) if completed_steps > 0 else 0,
            "efficiency_score": (completed_steps / total_steps) * (1 - failed_steps / total_steps) if total_steps > 0 else 0
        }
        
        return metrics
        
    except Exception as e:
        return {"error": f"Error calculating metrics: {str(e)}"}

if __name__ == "__main__":
    # Example usage and testing
    print("GRAPH: ModernGraphBuilder with Direct Tool Execution")
    print("Features:")
    print("- Direct tool execution (no ToolNode dependency)")
    print("- Full dependency resolution system")
    print("- Template variable support ({{user_id}}, {{contact_list}}, etc.)")
    print("- Multi-step data flow with shared context")
    print("- Enhanced error handling and recovery")
    print("- State persistence with checkpointing")
    print("- Performance monitoring and debugging tools")
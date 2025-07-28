import logging
import traceback
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END, START
from agents.plan_schema import ExecutionPlan, WorkflowState
from agents.execution_nodes import NodeFactory
from agents.state_manager import StateManager
from agents.data_extractor import DataExtractor

# Configure logging
logger = logging.getLogger(__name__)

class GraphBuilder:
    """Builds dynamic LangGraph workflows from execution plans with proper edge configuration"""
    
    def __init__(self, auth_manager):
        logger.info("🏗️ Initializing GraphBuilder")
        
        try:
            self.auth_manager = auth_manager
            logger.info("🔧 Creating NodeFactory")
            self.node_factory = NodeFactory(auth_manager)
            logger.info("✅ NodeFactory created successfully")
            
            logger.info("🤖 Creating DataExtractor")
            self.data_extractor = DataExtractor()  # LLM created internally
            logger.info("✅ DataExtractor created successfully")
            
            logger.info("✅ GraphBuilder initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize GraphBuilder: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def build_graph(self, plan: ExecutionPlan, user_id: str) -> StateGraph:
        """Build executable LangGraph from execution plan with proper LangGraph patterns"""
        
        logger.info(f"🚀 Building graph for plan: {plan.intent}")
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"📋 Plan has {len(plan.steps)} steps")
        
        try:
            # Initialize state manager for this workflow
            logger.info("🗃️ Initializing StateManager")
            state_manager = StateManager(user_id)
            logger.info("✅ StateManager initialized")
            
            # Create graph with WorkflowState
            logger.info("📊 Creating StateGraph with WorkflowState")
            workflow = StateGraph(WorkflowState)
            logger.info("✅ StateGraph created")
            
            # Add nodes for each step
            logger.info("🔗 Adding nodes for each step")
            for step in plan.steps:
                node_name = f"step_{step.step_index}"
                logger.info(f"➕ Adding node: {node_name} ({step.tool.value} - {step.action.value})")
                
                # Create node function that returns WorkflowState
                node_func = self._create_step_node(step, state_manager)
                workflow.add_node(node_name, node_func)
                logger.info(f"✅ Node {node_name} added successfully")
            
            # Add edges based on dependencies - FIXED LOGIC
            logger.info("🔗 Setting up workflow edges with proper dependency handling")
            self._add_workflow_edges(workflow, plan)
            
            logger.info("🔧 Compiling workflow graph")
            compiled_graph = workflow.compile()
            logger.info("✅ Workflow graph compiled successfully")
            
            return compiled_graph
            
        except Exception as e:
            logger.error(f"❌ Error building graph: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _add_workflow_edges(self, workflow: StateGraph, plan: ExecutionPlan):
        """Add edges based on step dependencies - FIXED IMPLEMENTATION"""
        
        logger.info("🔗 Adding edges based on step dependencies")
        
        try:
            # Track which steps have dependencies satisfied
            steps_with_dependencies = set()
            
            # Add edges FROM dependencies TO dependent steps
            for step in plan.steps:
                current_node = f"step_{step.step_index}"
                logger.info(f"🔍 Processing edges for {current_node}")
                
                if step.dependencies:
                    logger.info(f"📋 Step {step.step_index} has dependencies: {step.dependencies}")
                    steps_with_dependencies.add(step.step_index)
                    
                    # Add edge FROM each dependency TO current step
                    for dep_step_index in step.dependencies:
                        dep_node = f"step_{dep_step_index}"
                        logger.info(f"➡️ Adding edge: {dep_node} -> {current_node}")
                        workflow.add_edge(dep_node, current_node)
                else:
                    logger.info(f"🚀 Step {step.step_index} has no dependencies")
            
            # Connect steps with no dependencies to START
            for step in plan.steps:
                if not step.dependencies:
                    current_node = f"step_{step.step_index}"
                    logger.info(f"🚀 Connecting {current_node} to START")
                    workflow.add_edge(START, current_node)
            
            # Connect steps with no dependents to END
            logger.info("🏁 Adding edges to END for terminal steps")
            for step in plan.steps:
                current_node = f"step_{step.step_index}"
                
                # Check if any other step depends on this one
                has_dependents = any(
                    step.step_index in other_step.dependencies 
                    for other_step in plan.steps
                )
                
                if not has_dependents:
                    logger.info(f"🏁 Adding edge to END: {current_node} -> END")
                    workflow.add_edge(current_node, END)
            
            logger.info("✅ All workflow edges configured successfully")
            
        except Exception as e:
            logger.error(f"❌ Error adding workflow edges: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_step_node(self, step, state_manager):
        """Create node function for execution step that returns WorkflowState"""
        
        logger.info(f"🔧 Creating step node for step {step.step_index}: {step.description}")
        
        def step_node(state: WorkflowState) -> WorkflowState:
            """Execute single step and return updated WorkflowState - FIXED"""
            
            logger.info(f"⚡ Executing step {step.step_index}: {step.description}")
            logger.info(f"🔧 Tool: {step.tool.value}, Action: {step.action.value}")
            
            try:
                # Get execution context from current state
                logger.info(f"📊 Getting context for step {step.step_index}")
                context = self._get_context_from_state(state, step.step_index)
                logger.info(f"✅ Context retrieved for step {step.step_index}")
                logger.info(f"📋 Context keys: {list(context.keys())}")
                
                # Get appropriate execution node
                logger.info(f"🔧 Getting execution node for tool: {step.tool.value}")
                execution_node = self.node_factory.get_node(step.tool)
                logger.info(f"✅ Execution node retrieved: {type(execution_node).__name__}")
                
                # Execute step
                logger.info(f"🚀 Executing step {step.step_index}")
                step_result = execution_node.execute(
                    step.step_index, 
                    step.tool, 
                    step.action, 
                    context
                )
                logger.info(f"✅ Step {step.step_index} execution completed with status: {step_result.status}")
                
                if step_result.status == "completed":
                    logger.info(f"✅ Step {step.step_index} completed successfully")
                    
                    # Extract data for future steps
                    logger.info(f"🔄 Extracting data for future steps from step {step.step_index}")
                    remaining_steps = [s for s in state.plan.steps if s.step_index > step.step_index]
                    logger.info(f"📋 Found {len(remaining_steps)} remaining steps")
                    
                    logger.info(f"🤖 Calling DataExtractor for step {step.step_index}")
                    extracted_data = self.data_extractor.extract_data(
                        step_result, step, remaining_steps, state.shared_context
                    )
                    logger.info(f"✅ Data extraction completed for step {step.step_index}")
                    logger.info(f"📊 Extracted data keys: {list(extracted_data.keys())}")
                    
                    # Update step result with extracted data
                    step_result.extracted_data = extracted_data.get("extracted_data", {})
                    
                    # Update state - CRITICAL FIX
                    logger.info(f"📝 Updating state with step {step.step_index} results")
                    
                    # Store step result
                    state.step_results[step_result.step_index] = step_result
                    
                    # Update shared context with extracted data
                    if "context_updates" in extracted_data:
                        state.shared_context.update(extracted_data["context_updates"])
                    
                    # Add data for future steps
                    if "for_future_steps" in extracted_data:
                        state.shared_context.update(extracted_data["for_future_steps"])
                    
                    # Update current step
                    state.current_step = step.step_index + 1
                    
                    # Check if workflow completed
                    if state.current_step > len(state.plan.steps):
                        state.status = "completed"
                        logger.info(f"🎉 Workflow completed after step {step.step_index}")
                    
                    logger.info(f"✅ State updated for step {step.step_index}")
                else:
                    # Handle failure
                    logger.error(f"❌ Step {step.step_index} failed: {step_result.error_message}")
                    
                    # Store failed step result
                    state.step_results[step_result.step_index] = step_result
                    state.status = "failed"
                
                # Return updated state - CRITICAL FOR LANGGRAPH
                logger.info(f"📊 Returning updated state after step {step.step_index}")
                return state
                
            except Exception as e:
                # Handle unexpected errors
                logger.error(f"❌ Unexpected error in step {step.step_index}: {str(e)}")
                logger.error(traceback.format_exc())
                
                logger.info(f"🚨 Marking step {step.step_index} as failed due to exception")
                
                # Create failed step result
                from agents.plan_schema import StepResult
                failed_result = StepResult(
                    step_index=step.step_index,
                    tool=step.tool,
                    action=step.action,
                    status="failed",
                    raw_output={},
                    extracted_data={},
                    error_message=str(e)
                )
                
                # Update state with failure
                state.step_results[step.step_index] = failed_result
                state.status = "failed"
                
                return state
        
        logger.info(f"✅ Step node created for step {step.step_index}")
        return step_node
    
    def _get_context_from_state(self, state: WorkflowState, step_index: int) -> Dict[str, Any]:
        """Get execution context from current state - FIXED"""
        
        logger.info(f"📊 Getting context from state for step {step_index}")
        
        try:
            step = state.plan.steps[step_index - 1]  # Convert to 0-based index
            context = {
                "shared_context": state.shared_context,
                "step_parameters": step.parameters,
                "user_id": state.user_id
            }
            
            # Add data from dependent steps
            for dep_step_index in step.dependencies:
                if dep_step_index in state.step_results:
                    dep_result = state.step_results[dep_step_index]
                    context[f"step_{dep_step_index}_data"] = dep_result.extracted_data
                    context[f"step_{dep_step_index}_raw"] = dep_result.raw_output
                    logger.info(f"📋 Added dependency data from step {dep_step_index}")
            
            logger.info(f"✅ Context prepared for step {step_index}")
            return context
            
        except Exception as e:
            logger.error(f"❌ Error getting context from state: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "shared_context": state.shared_context,
                "step_parameters": {},
                "user_id": state.user_id
            }
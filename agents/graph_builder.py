import logging
import traceback
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from agents.plan_schema import ExecutionPlan, WorkflowState
from agents.execution_nodes import NodeFactory
from agents.state_manager import StateManager
from agents.data_extractor import DataExtractor

# Configure logging
logger = logging.getLogger(__name__)

class GraphBuilder:
    """Builds dynamic LangGraph workflows from execution plans with comprehensive logging"""
    
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
        """Build executable LangGraph from execution plan with comprehensive logging"""
        
        logger.info(f"🚀 Building graph for plan: {plan.intent}")
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"📋 Plan has {len(plan.steps)} steps")
        
        try:
            # Initialize state manager
            logger.info("🗃️ Initializing StateManager")
            state_manager = StateManager(user_id)
            logger.info("✅ StateManager initialized")
            
            # Create graph
            logger.info("📊 Creating StateGraph")
            workflow = StateGraph(WorkflowState)
            logger.info("✅ StateGraph created")
            
            # Add nodes for each step
            logger.info("🔗 Adding nodes for each step")
            for step in plan.steps:
                node_name = f"step_{step.step_index}"
                logger.info(f"➕ Adding node: {node_name} ({step.tool.value} - {step.action.value})")
                
                # Create node function
                node_func = self._create_step_node(step, state_manager)
                workflow.add_node(node_name, node_func)
                logger.info(f"✅ Node {node_name} added successfully")
            
            # Add edges based on dependencies
            logger.info("🔗 Setting up workflow edges")
            workflow.set_entry_point("step_1")
            logger.info("✅ Entry point set to step_1")
            
            for step in plan.steps:
                current_node = f"step_{step.step_index}"
                logger.info(f"🔍 Processing edges for {current_node}")
                
                if step.dependencies:
                    logger.info(f"📋 Step {step.step_index} has dependencies: {step.dependencies}")
                    # This step depends on others - edges handled by dependencies
                    pass
                else:
                    # Independent step or first step
                    if step.step_index == 1:
                        logger.info(f"🚀 Step {step.step_index} is entry point")
                        # Entry point already set
                        pass
                    else:
                        logger.info(f"🔗 Step {step.step_index} is independent")
                
                # Add edges to dependent steps
                dependent_steps = [s for s in plan.steps if step.step_index in s.dependencies]
                logger.info(f"🔗 Step {step.step_index} has {len(dependent_steps)} dependent steps")
                
                if dependent_steps:
                    for dep_step in dependent_steps:
                        next_node = f"step_{dep_step.step_index}"
                        logger.info(f"➡️ Adding edge: {current_node} -> {next_node}")
                        workflow.add_edge(current_node, next_node)
                else:
                    # Last step or no dependents
                    if step.step_index == len(plan.steps):
                        logger.info(f"🏁 Adding edge to END: {current_node} -> END")
                        workflow.add_edge(current_node, END)
            
            logger.info("🔧 Compiling workflow graph")
            compiled_graph = workflow.compile()
            logger.info("✅ Workflow graph compiled successfully")
            
            return compiled_graph
            
        except Exception as e:
            logger.error(f"❌ Error building graph: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_step_node(self, step, state_manager):
        """Create node function for execution step with comprehensive logging"""
        
        logger.info(f"🔧 Creating step node for step {step.step_index}: {step.description}")
        
        def step_node(state: WorkflowState) -> WorkflowState:
            """Execute single step and update state with logging"""
            
            logger.info(f"⚡ Executing step {step.step_index}: {step.description}")
            logger.info(f"🔧 Tool: {step.tool.value}, Action: {step.action.value}")
            
            try:
                # Get execution context
                logger.info(f"📊 Getting context for step {step.step_index}")
                context = state_manager.get_context_for_step(step.step_index)
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
                    
                    # Update state
                    logger.info(f"📝 Updating state with step {step.step_index} results")
                    state_manager.update_step_result(step_result, extracted_data)
                    logger.info(f"✅ State updated for step {step.step_index}")
                else:
                    # Handle failure
                    logger.error(f"❌ Step {step.step_index} failed: {step_result.error_message}")
                    state_manager.mark_step_failed(step.step_index, step_result.error_message)
                
                # Return updated state
                logger.info(f"📊 Getting updated state after step {step.step_index}")
                updated_state = state_manager.get_current_state()
                logger.info(f"✅ Updated state retrieved for step {step.step_index}")
                
                return updated_state
                
            except Exception as e:
                # Handle unexpected errors
                logger.error(f"❌ Unexpected error in step {step.step_index}: {str(e)}")
                logger.error(traceback.format_exc())
                
                logger.info(f"🚨 Marking step {step.step_index} as failed due to exception")
                state_manager.mark_step_failed(step.step_index, str(e))
                
                return state_manager.get_current_state()
        
        logger.info(f"✅ Step node created for step {step.step_index}")
        return step_node
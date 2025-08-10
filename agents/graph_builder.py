import logging
import traceback
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END, START
from langgraph.checkpoint.memory import MemorySaver
from agents.plan_schema import ExecutionPlan, WorkflowState
from agents.execution_nodes import NodeFactory
from agents.data_extractor import DataExtractor

# Configure logging
logger = logging.getLogger(__name__)

class GraphBuilder:
    """Builds dynamic LangGraph workflows with proper checkpointing and persistence"""
    
    def __init__(self, auth_manager):
        logger.info("🏗️ Initializing GraphBuilder with checkpointing support")
        
        try:
            self.auth_manager = auth_manager
            logger.info("🔧 Creating NodeFactory")
            self.node_factory = NodeFactory(auth_manager)
            logger.info("✅ NodeFactory created successfully")
            
            logger.info("🤖 Creating DataExtractor")
            self.data_extractor = DataExtractor()
            logger.info("✅ DataExtractor created successfully")
            
            logger.info("✅ GraphBuilder initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize GraphBuilder: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _get_checkpointer(self):
        """Get in-memory checkpointer (no database required)"""
        logger.info("💾 Using in-memory checkpointer (no database)")
        return MemorySaver()
    
    def build_graph(self, plan: ExecutionPlan, user_id: str) -> StateGraph:
        """Build executable LangGraph with proper checkpointing and persistence"""
        
        logger.info(f"🚀 Building graph for plan: {plan['intent']}")
        logger.info(f"👤 User ID: {user_id}")
        logger.info(f"📋 Plan has {len(plan['steps'])} steps")
        
        try:
            # ✅ FIXED: Create graph with WorkflowState (now TypedDict)
            logger.info("📊 Creating StateGraph with WorkflowState TypedDict")
            workflow = StateGraph(WorkflowState)
            logger.info("✅ StateGraph created")
            
            # Add nodes for each step
            logger.info("🔗 Adding nodes for each step")
            for step in plan['steps']:
                node_name = f"step_{step['step_index']}"
                logger.info(f"➕ Adding node: {node_name} ({step['tool'].value} - {step['action'].value})")
                
                # Create node function that returns proper state updates
                node_func = self._create_step_node(step)
                workflow.add_node(node_name, node_func)
                logger.info(f"✅ Node {node_name} added successfully")
            
            # Add edges based on dependencies
            logger.info("🔗 Setting up workflow edges with proper dependency handling")
            self._add_workflow_edges(workflow, plan)
            
            # ✅ FIXED: Compile with checkpointer for persistence and recovery
            logger.info("🔧 Compiling workflow graph with checkpointer")
            checkpointer = self._get_checkpointer()
            compiled_graph = workflow.compile(checkpointer=checkpointer)
            logger.info("✅ Workflow graph compiled successfully with persistence")
            
            return compiled_graph
            
        except Exception as e:
            logger.error(f"❌ Error building graph: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _add_workflow_edges(self, workflow: StateGraph, plan: ExecutionPlan):
        """Add edges based on step dependencies"""
        
        logger.info("🔗 Adding edges based on step dependencies")
        
        try:
            # Connect steps with no dependencies to START
            for step in plan['steps']:
                if not step['dependencies']:
                    current_node = f"step_{step['step_index']}"
                    logger.info(f"🚀 Connecting {current_node} to START")
                    workflow.add_edge(START, current_node)
            
            # Add edges FROM dependencies TO dependent steps
            for step in plan['steps']:
                current_node = f"step_{step['step_index']}"
                
                if step['dependencies']:
                    logger.info(f"📋 Step {step['step_index']} has dependencies: {step['dependencies']}")
                    
                    for dep_step_index in step['dependencies']:
                        dep_node = f"step_{dep_step_index}"
                        logger.info(f"➡️ Adding edge: {dep_node} -> {current_node}")
                        workflow.add_edge(dep_node, current_node)
            
            # Connect steps with no dependents to END
            logger.info("🏁 Adding edges to END for terminal steps")
            for step in plan['steps']:
                current_node = f"step_{step['step_index']}"
                
                # Check if any other step depends on this one
                has_dependents = any(
                    step['step_index'] in other_step['dependencies'] 
                    for other_step in plan['steps']
                )
                
                if not has_dependents:
                    logger.info(f"🏁 Adding edge to END: {current_node} -> END")
                    workflow.add_edge(current_node, END)
            
            logger.info("✅ All workflow edges configured successfully")
            
        except Exception as e:
            logger.error(f"❌ Error adding workflow edges: {str(e)}")
            logger.error(traceback.format_exc())
            raise
    
    def _create_step_node(self, step):
        """✅ FIXED: Create node function that returns proper state updates (not full state)"""
        
        logger.info(f"🔧 Creating step node for step {step['step_index']}: {step['description']}")
        
        def step_node(state: WorkflowState) -> Dict[str, Any]:
            """Execute single step and return state updates only"""
            
            logger.info(f"⚡ Executing step {step['step_index']}: {step['description']}")
            logger.info(f"🔧 Tool: {step['tool'].value}, Action: {step['action'].value}")
            
            try:
                # Get execution context from current state
                logger.info(f"📊 Getting context for step {step['step_index']}")
                context = self._get_context_from_state(state, step['step_index'])
                logger.info(f"✅ Context retrieved for step {step['step_index']}")
                
                # Get appropriate execution node
                logger.info(f"🔧 Getting execution node for tool: {step['tool'].value}")
                execution_node = self.node_factory.get_node(step['tool'])
                logger.info(f"✅ Execution node retrieved: {type(execution_node).__name__}")
                
                # Execute step
                logger.info(f"🚀 Executing step {step['step_index']}")
                step_result = execution_node.execute(
                    step['step_index'], 
                    step['tool'], 
                    step['action'], 
                    context
                )
                logger.info(f"✅ Step {step['step_index']} execution completed with status: {step_result['status']}")
                
                # ✅ FIXED: Return only state updates, not full state - LangGraph will merge these
                if step_result['status'] == "completed":
                    logger.info(f"✅ Step {step['step_index']} completed successfully")
                    
                    # Extract data for future steps
                    logger.info(f"🔄 Extracting data for future steps from step {step['step_index']}")
                    remaining_steps = [s for s in state['plan']['steps'] if s['step_index'] > step['step_index']]
                    
                    extracted_data = self.data_extractor.extract_data(
                        step_result, step, remaining_steps, state['shared_context']
                    )
                    logger.info(f"✅ Data extraction completed for step {step['step_index']}")
                    
                    # Update extracted data in step result
                    step_result['extracted_data'] = extracted_data.get("extracted_data", {})
                    
                    # Calculate next step and status
                    next_step = state['current_step'] + 1
                    total_steps = len(state['plan']['steps'])
                    new_status = "completed" if next_step > total_steps else "executing"
                    
                    # ✅ RETURN STATE UPDATES ONLY - LangGraph reducers will merge these automatically
                    return {
                        "step_results": {step_result['step_index']: step_result},
                        "shared_context": {
                            **extracted_data.get("context_updates", {}),
                            **extracted_data.get("for_future_steps", {})
                        },
                        "current_step": next_step,
                        "status": new_status,
                        "execution_log": [f"✅ Step {step['step_index']} completed: {step['description']}"]
                    }
                else:
                    # Handle failure
                    logger.error(f"❌ Step {step['step_index']} failed: {step_result.get('error_message')}")
                    
                    return {
                        "step_results": {step_result['step_index']: step_result},
                        "status": "failed",
                        "execution_log": [f"❌ Step {step['step_index']} failed: {step_result.get('error_message')}"]
                    }
                
            except Exception as e:
                # Handle unexpected errors
                logger.error(f"❌ Unexpected error in step {step['step_index']}: {str(e)}")
                logger.error(traceback.format_exc())
                
                # Create failed step result
                failed_result = {
                    'step_index': step['step_index'],
                    'tool': step['tool'],
                    'action': step['action'],
                    'status': "failed",
                    'raw_output': {},
                    'extracted_data': {},
                    'error_message': str(e)
                }
                
                return {
                    "step_results": {step['step_index']: failed_result},
                    "status": "failed",
                    "execution_log": [f"❌ Step {step['step_index']} exception: {str(e)}"]
                }
        
        logger.info(f"✅ Step node created for step {step['step_index']}")
        return step_node
    
    def _get_context_from_state(self, state: WorkflowState, step_index: int) -> Dict[str, Any]:
        """Get execution context from current state"""
        
        logger.info(f"📊 Getting context from state for step {step_index}")
        
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
            logger.error(f"❌ Error getting context from state: {str(e)}")
            logger.error(traceback.format_exc())
            return {
                "shared_context": state['shared_context'],
                "step_parameters": {},
                "user_id": state['user_id']
            }
from typing import Dict, Any, List
from langgraph.graph import StateGraph, END
from agents.plan_schema import ExecutionPlan, WorkflowState
from agents.execution_nodes import NodeFactory
from agents.state_manager import StateManager
from agents.data_extractor import DataExtractor

class GraphBuilder:
    """Builds dynamic LangGraph workflows from execution plans"""
    
    def __init__(self, auth_manager):
        self.auth_manager = auth_manager
        self.node_factory = NodeFactory(auth_manager)
        self.data_extractor = DataExtractor()  # LLM created internally
    
    def build_graph(self, plan: ExecutionPlan, user_id: str) -> StateGraph:
        """Build executable LangGraph from execution plan"""
        
        # Initialize state manager
        state_manager = StateManager(user_id)
        
        # Create graph
        workflow = StateGraph(WorkflowState)
        
        # Add nodes for each step
        for step in plan.steps:
            node_name = f"step_{step.step_index}"
            
            # Create node function
            node_func = self._create_step_node(step, state_manager)
            workflow.add_node(node_name, node_func)
        
        # Add edges based on dependencies
        workflow.set_entry_point("step_1")
        
        for step in plan.steps:
            current_node = f"step_{step.step_index}"
            
            if step.dependencies:
                # This step depends on others - edges handled by dependencies
                pass
            else:
                # Independent step or first step
                if step.step_index == 1:
                    # Entry point already set
                    pass
            
            # Add edges to dependent steps
            dependent_steps = [s for s in plan.steps if step.step_index in s.dependencies]
            
            if dependent_steps:
                for dep_step in dependent_steps:
                    next_node = f"step_{dep_step.step_index}"
                    workflow.add_edge(current_node, next_node)
            else:
                # Last step or no dependents
                if step.step_index == len(plan.steps):
                    workflow.add_edge(current_node, END)
        
        return workflow.compile()
    
    def _create_step_node(self, step, state_manager):
        """Create node function for execution step"""
        
        def step_node(state: WorkflowState) -> WorkflowState:
            """Execute single step and update state"""
            
            try:
                # Get execution context
                context = state_manager.get_context_for_step(step.step_index)
                
                # Get appropriate execution node
                execution_node = self.node_factory.get_node(step.tool)
                
                # Execute step
                step_result = execution_node.execute(
                    step.step_index, 
                    step.tool, 
                    step.action, 
                    context
                )
                
                if step_result.status == "completed":
                    # Extract data for future steps
                    remaining_steps = [s for s in state.plan.steps if s.step_index > step.step_index]
                    extracted_data = self.data_extractor.extract_data(
                        step_result, step, remaining_steps, state.shared_context
                    )
                    
                    # Update state
                    state_manager.update_step_result(step_result, extracted_data)
                else:
                    # Handle failure
                    state_manager.mark_step_failed(step.step_index, step_result.error_message)
                
                # Return updated state
                return state_manager.get_current_state()
                
            except Exception as e:
                # Handle unexpected errors
                state_manager.mark_step_failed(step.step_index, str(e))
                return state_manager.get_current_state()
        
        return step_node
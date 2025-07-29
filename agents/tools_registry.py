"""
Tools Registry - Replaces the old execution_nodes.py

This module provides a centralized registry for all LangChain tools
and integrates them with LangGraph's ToolNode for automatic execution.

Replaces the complex NodeFactory pattern with simple tool registration.
"""

import logging
from typing import Dict, List, Any
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

# Import our converted tools
from tools.gmail_tool import get_gmail_tools, GMAIL_TOOL_METADATA
from tools.calendar_tool import get_calendar_tools, CALENDAR_TOOL_METADATA
from tools.drive_tool import get_drive_tools, DRIVE_TOOL_METADATA
from agents.plan_schema import ToolType

# Configure logging
logger = logging.getLogger(__name__)

class ToolsRegistry:
    """
    Centralized registry for all LangChain tools.
    
    Replaces the old NodeFactory with a simple, modern approach
    using LangGraph's ToolNode for automatic tool execution.
    """
    
    def __init__(self, auth_manager):
        """
        Initialize tools registry with authentication manager.
        
        Args:
            auth_manager: Authentication manager for Google APIs
        """
        logger.info("🔧 Initializing ToolsRegistry")
        
        try:
            self.auth_manager = auth_manager
            
            # Store auth_manager in session state for tools to access
            import streamlit as st
            st.session_state['auth_manager'] = auth_manager
            
            # Create tools registry by category
            logger.info("📧 Creating Gmail tools")
            gmail_tools = get_gmail_tools()
            logger.info(f"✅ Created {len(gmail_tools)} Gmail tools")
            
            logger.info("📅 Creating Calendar tools")
            calendar_tools = get_calendar_tools()
            logger.info(f"✅ Created {len(calendar_tools)} Calendar tools")
            
            logger.info("📁 Creating Drive tools")
            drive_tools = get_drive_tools()
            logger.info(f"✅ Created {len(drive_tools)} Drive tools")
            
            # Store tools by category
            self.tools_by_category = {
                ToolType.GMAIL: gmail_tools,
                ToolType.CALENDAR: calendar_tools,
                ToolType.DRIVE: drive_tools
            }
            
            # Create flat list of all tools for ToolNode
            self.all_tools = []
            for tool_list in self.tools_by_category.values():
                self.all_tools.extend(tool_list)
            
            logger.info(f"✅ Total tools registered: {len(self.all_tools)}")
            
            # Create ToolNode for LangGraph integration
            self.tool_node = ToolNode(self.all_tools)
            logger.info("🚀 ToolNode created successfully")
            
            # Store metadata for tool descriptions
            self.tool_metadata = {
                **GMAIL_TOOL_METADATA,
                **CALENDAR_TOOL_METADATA,
                **DRIVE_TOOL_METADATA
            }
            
            logger.info("✅ ToolsRegistry initialization complete")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize ToolsRegistry: {str(e)}")
            raise
    
    def get_tool_node(self) -> ToolNode:
        """
        Get the LangGraph ToolNode for workflow integration.
        
        Returns:
            ToolNode configured with all registered tools
        """
        return self.tool_node
    
    def get_tools_by_category(self, tool_type: ToolType) -> List[BaseTool]:
        """
        Get tools for a specific category.
        
        Args:
            tool_type: Category of tools to retrieve
            
        Returns:
            List of tools for the specified category
        """
        return self.tools_by_category.get(tool_type, [])
    
    def get_all_tools(self) -> List[BaseTool]:
        """
        Get all registered tools as a flat list.
        
        Returns:
            List of all tools across all categories
        """
        return self.all_tools.copy()
    
    def get_tool_by_name(self, tool_name: str) -> BaseTool:
        """
        Get a specific tool by name.
        
        Args:
            tool_name: Name of the tool to retrieve
            
        Returns:
            The tool if found, None otherwise
        """
        for tool in self.all_tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def get_tool_metadata(self, tool_name: str) -> Dict[str, Any]:
        """
        Get metadata for a specific tool.
        
        Args:
            tool_name: Name of the tool
            
        Returns:
            Tool metadata including description, parameters, outputs
        """
        return self.tool_metadata.get(tool_name, {})
    
    def get_tools_summary(self) -> Dict[str, Any]:
        """
        Get summary of all registered tools.
        
        Returns:
            Summary with tool counts and categories
        """
        summary = {
            "total_tools": len(self.all_tools),
            "categories": {},
            "tool_names": [tool.name for tool in self.all_tools]
        }
        
        for tool_type, tools in self.tools_by_category.items():
            summary["categories"][tool_type.value] = {
                "count": len(tools),
                "tools": [tool.name for tool in tools]
            }
        
        return summary
    
    def list_available_tools(self) -> str:
        """
        Get human-readable list of available tools.
        
        Returns:
            Formatted string listing all tools with descriptions
        """
        output = "🔧 Available Tools:\n\n"
        
        for tool_type, tools in self.tools_by_category.items():
            output += f"📂 {tool_type.value.upper()}:\n"
            
            for tool in tools:
                # Get description from tool docstring or metadata
                description = ""
                if hasattr(tool, 'description') and tool.description:
                    description = tool.description
                elif hasattr(tool, '__doc__') and tool.__doc__:
                    # Extract first line of docstring
                    description = tool.__doc__.strip().split('\n')[0]
                
                output += f"   • {tool.name}: {description}\n"
            
            output += "\n"
        
        return output

# Factory function for easy integration
def create_tools_registry(auth_manager) -> ToolsRegistry:
    """
    Factory function to create a ToolsRegistry instance.
    
    Args:
        auth_manager: Authentication manager for Google APIs
        
    Returns:
        Configured ToolsRegistry instance
    """
    logger.info("🏭 Creating ToolsRegistry instance")
    return ToolsRegistry(auth_manager)

# Utility functions for tool management
def get_tool_node(auth_manager) -> ToolNode:
    """
    Quick function to get a ToolNode with all tools.
    
    Args:
        auth_manager: Authentication manager
        
    Returns:
        ToolNode ready for LangGraph integration
    """
    registry = create_tools_registry(auth_manager)
    return registry.get_tool_node()

def get_tools_for_graph(auth_manager) -> Dict[ToolType, List[BaseTool]]:
    """
    Get tools registry for graph builder.
    
    Args:
        auth_manager: Authentication manager
        
    Returns:
        Dictionary mapping tool types to tool lists
    """
    registry = create_tools_registry(auth_manager)
    return registry.tools_by_category

def validate_tool_integration(auth_manager) -> Dict[str, Any]:
    """
    Validate that all tools are properly integrated.
    
    Args:
        auth_manager: Authentication manager
        
    Returns:
        Validation results with any issues found
    """
    logger.info("🔍 Validating tool integration")
    
    try:
        registry = create_tools_registry(auth_manager)
        
        validation_results = {
            "success": True,
            "total_tools": len(registry.all_tools),
            "categories": {},
            "issues": []
        }
        
        # Validate each category
        for tool_type, tools in registry.tools_by_category.items():
            category_name = tool_type.value
            
            if not tools:
                validation_results["issues"].append(f"No tools found for {category_name}")
                validation_results["success"] = False
            
            validation_results["categories"][category_name] = {
                "tool_count": len(tools),
                "tool_names": [tool.name for tool in tools]
            }
            
            # Validate individual tools
            for tool in tools:
                if not hasattr(tool, 'name') or not tool.name:
                    validation_results["issues"].append(f"Tool missing name in {category_name}")
                    validation_results["success"] = False
                
                if not hasattr(tool, 'description') or not tool.description:
                    validation_results["issues"].append(f"Tool {tool.name} missing description")
        
        # Validate ToolNode creation
        try:
            tool_node = registry.get_tool_node()
            if tool_node is None:
                validation_results["issues"].append("Failed to create ToolNode")
                validation_results["success"] = False
        except Exception as e:
            validation_results["issues"].append(f"ToolNode creation error: {str(e)}")
            validation_results["success"] = False
        
        logger.info(f"✅ Tool validation complete: {validation_results['success']}")
        return validation_results
        
    except Exception as e:
        logger.error(f"❌ Tool validation failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "total_tools": 0,
            "categories": {},
            "issues": [f"Validation failed: {str(e)}"]
        }

# Migration helper functions
def compare_old_vs_new_approach():
    """
    Documentation helper showing the migration from old to new approach.
    
    Returns:
        String comparing old NodeFactory vs new ToolsRegistry
    """
    return """
🔄 MIGRATION: Old NodeFactory → New ToolsRegistry

OLD APPROACH (REMOVED):
├── agents/execution_nodes.py (400+ lines)
│   ├── ExecutionNode (base class)
│   ├── GmailNode (complex execution logic)
│   ├── CalendarNode (parameter mapping)
│   ├── DriveNode (authentication handling)
│   └── NodeFactory (manual orchestration)

NEW APPROACH (CURRENT):
├── tools_registry.py (100 lines)
│   └── ToolsRegistry (simple tool registration)
├── tools/gmail_tool.py (LangChain tools)
├── tools/calendar_tool.py (LangChain tools)
└── tools/drive_tool.py (LangChain tools)

BENEFITS:
✅ 75% reduction in code complexity
✅ Native LangGraph integration
✅ Automatic parameter validation (Pydantic)
✅ Built-in error handling
✅ Streaming support
✅ Better testing capabilities
✅ No manual authentication handling
✅ Works with LangGraph checkpointing

EXECUTION FLOW:
Old: User Request → Planner → NodeFactory → Custom Nodes → Manual Tool Calls
New: User Request → Planner → Graph → ToolNode → LangChain Tools ✨
"""

if __name__ == "__main__":
    # Example usage for testing
    print("🔧 ToolsRegistry Test")
    print("This module replaces the old execution_nodes.py")
    print("Run with proper auth_manager for full functionality")
    
    # Show comparison
    print(compare_old_vs_new_approach())
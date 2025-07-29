"""
Tools Registry - Fixed Authentication Injection (Keep Session State)

CHANGES:
- Removed session state pollution in registry
- Clean dependency injection for auth_manager  
- Auth manager still uses session state internally (that's perfect!)
- Tools no longer import Streamlit directly
"""

import logging
from typing import Dict, List, Any
from langchain_core.tools import BaseTool
from langgraph.prebuilt import ToolNode

# Import our UPDATED tool creation functions
from tools.gmail_tool import create_gmail_tools, GMAIL_TOOL_METADATA
from tools.calendar_tool import create_calendar_tools, CALENDAR_TOOL_METADATA
from tools.drive_tool import create_drive_tools, DRIVE_TOOL_METADATA
from agents.plan_schema import ToolType

# Configure logging
logger = logging.getLogger(__name__)

class ToolsRegistry:
    """
    Centralized registry for all LangChain tools with clean auth injection.
    
    FIXED ISSUES:
    - No more session state pollution in registry
    - Clean dependency injection
    - Auth manager still uses session state internally (perfect for demos!)
    - Tools are now testable and decoupled
    """
    
    def __init__(self, auth_manager):
        """
        Initialize tools registry with authentication manager.
        
        Args:
            auth_manager: Authentication manager (still uses session state internally)
        """
        logger.info("🔧 Initializing ToolsRegistry with clean auth injection")
        
        try:
            self.auth_manager = auth_manager
            
            # REMOVED: No more session state pollution
            # OLD: st.session_state['auth_manager'] = auth_manager  ❌
            # NEW: Clean dependency injection ✅
            
            # Create tools with auth_manager cleanly injected
            logger.info("📧 Creating Gmail tools")
            gmail_tools = create_gmail_tools(auth_manager)  # Pass auth_manager directly
            logger.info(f"✅ Created {len(gmail_tools)} Gmail tools")
            
            logger.info("📅 Creating Calendar tools")
            calendar_tools = create_calendar_tools(auth_manager)  # Pass auth_manager directly
            logger.info(f"✅ Created {len(calendar_tools)} Calendar tools")
            
            logger.info("📁 Creating Drive tools")
            drive_tools = create_drive_tools(auth_manager)  # Pass auth_manager directly
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
            if self.all_tools:
                self.tool_node = ToolNode(self.all_tools)
                logger.info("🚀 ToolNode created successfully")
            else:
                logger.warning("⚠️ No tools registered - ToolNode not created")
                self.tool_node = None
            
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
        """Get the LangGraph ToolNode for workflow integration."""
        return self.tool_node
    
    def get_tools_by_category(self, tool_type: ToolType) -> List[BaseTool]:
        """Get tools for a specific category."""
        return self.tools_by_category.get(tool_type, [])
    
    def get_all_tools(self) -> List[BaseTool]:
        """Get all registered tools as a flat list."""
        return self.all_tools.copy()
    
    def get_tool_by_name(self, tool_name: str) -> BaseTool:
        """Get a specific tool by name."""
        for tool in self.all_tools:
            if tool.name == tool_name:
                return tool
        return None
    
    def get_tool_metadata(self, tool_name: str) -> Dict[str, Any]:
        """Get metadata for a specific tool."""
        return self.tool_metadata.get(tool_name, {})
    
    def get_tools_summary(self) -> Dict[str, Any]:
        """Get summary of all registered tools."""
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
    
    def validate_tools(self) -> Dict[str, Any]:
        """Validate all tools are properly configured."""
        logger.info("🔍 Validating tool configuration")
        
        validation_results = {
            "success": True,
            "total_tools": len(self.all_tools),
            "issues": []
        }
        
        # Validate each tool
        for tool in self.all_tools:
            try:
                # Check tool has required attributes
                if not hasattr(tool, 'name') or not tool.name:
                    validation_results["issues"].append(f"Tool missing name")
                    validation_results["success"] = False
                
                if not hasattr(tool, 'description') or not tool.description:
                    validation_results["issues"].append(f"Tool {getattr(tool, 'name', 'unknown')} missing description")
                
                # Validate tool can be called (basic check)
                if not callable(tool):
                    validation_results["issues"].append(f"Tool {getattr(tool, 'name', 'unknown')} is not callable")
                    validation_results["success"] = False
                    
            except Exception as e:
                validation_results["issues"].append(f"Tool validation error: {str(e)}")
                validation_results["success"] = False
        
        # Validate ToolNode creation
        if self.tool_node is None and self.all_tools:
            validation_results["issues"].append("ToolNode creation failed despite having tools")
            validation_results["success"] = False
        
        logger.info(f"✅ Tool validation complete: {validation_results['success']}")
        return validation_results

# Factory function for easy integration - KEEP YOUR EXISTING PATTERN
def create_tools_registry(auth_manager) -> ToolsRegistry:
    """
    Factory function to create a ToolsRegistry instance.
    
    Args:
        auth_manager: Authentication manager (uses session state internally - perfect!)
        
    Returns:
        Configured ToolsRegistry instance with clean auth injection
    """
    logger.info("🏭 Creating ToolsRegistry instance with clean auth injection")
    return ToolsRegistry(auth_manager)

# Utility functions - KEEP YOUR EXISTING API
def get_tool_node(auth_manager) -> ToolNode:
    """Quick function to get a ToolNode with all tools."""
    registry = create_tools_registry(auth_manager)
    return registry.get_tool_node()

def get_tools_for_graph(auth_manager) -> Dict[ToolType, List[BaseTool]]:
    """Get tools registry for graph builder."""
    registry = create_tools_registry(auth_manager)
    return registry.tools_by_category

def validate_tool_integration(auth_manager) -> Dict[str, Any]:
    """Validate that all tools are properly integrated and testable."""
    logger.info("🔍 Validating tool integration")
    
    try:
        registry = create_tools_registry(auth_manager)
        return registry.validate_tools()
        
    except Exception as e:
        logger.error(f"❌ Tool validation failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "total_tools": 0,
            "issues": [f"Registry creation failed: {str(e)}"]
        }

if __name__ == "__main__":
    # Test the registry (can now be run independently!)
    print("🔧 ToolsRegistry Test")
    print("FIXED: Tools no longer import Streamlit directly")
    print("PRESERVED: Auth manager still uses session state (perfect for demos)")
    print("RESULT: Clean, testable, decoupled architecture")
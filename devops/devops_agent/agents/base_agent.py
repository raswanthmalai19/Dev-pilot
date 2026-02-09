"""
Base Agent class for DevOps Automation.
All specialized agents inherit from this base.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pathlib import Path

from ..core.gemini_client import GeminiClient
from ..core.executor import CommandExecutor
from ..core.file_manager import FileManager
from ..core.logger import AgentLogger
from ..config import get_config


class BaseAgent(ABC):
    """
    Abstract base class for all DevOps agents.
    Provides common utilities and interface.
    """
    
    def __init__(
        self, 
        name: str,
        working_dir: Path = None,
        gemini_client: GeminiClient = None,
    ):
        self.name = name
        self.config = get_config()
        self.working_dir = working_dir or self.config.workspace_dir
        
        # Initialize utilities
        self.logger = AgentLogger(name)
        self.executor = CommandExecutor(working_dir=self.working_dir, logger=self.logger)
        self.file_manager = FileManager(base_dir=self.working_dir, logger=self.logger)
        
        # Gemini client (shared or create new)
        self.gemini = gemini_client or self._create_gemini_client()
        
        # Register agent-specific tools with Gemini
        self._register_tools()
    
    def _create_gemini_client(self) -> GeminiClient:
        """Create a Gemini client with agent-specific instructions."""
        system_instruction = self._get_system_instruction()
        return GeminiClient(system_instruction=system_instruction)
    
    @abstractmethod
    def _get_system_instruction(self) -> str:
        """Return the system instruction for this agent."""
        pass
    
    def _register_tools(self) -> None:
        """Register tools with Gemini. Override in subclasses."""
        pass
    
    @abstractmethod
    async def run(self, *args, **kwargs) -> Any:
        """Execute the agent's main task."""
        pass
    
    async def check_prerequisites(self) -> Dict[str, bool]:
        """Check required tools and dependencies."""
        return {}
    
    def log_step(self, message: str, step: int = None) -> None:
        """Log a step in the agent's workflow."""
        self.logger.step(message, step)
    
    def log_success(self, message: str) -> None:
        """Log a success."""
        self.logger.success(message)
    
    def log_error(self, message: str, exc: Exception = None) -> None:
        """Log an error."""
        self.logger.error(message, exc)

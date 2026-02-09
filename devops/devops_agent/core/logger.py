"""
Structured logging for DevOps Automation Agent.
Uses structlog for rich, contextual logging.
"""

import sys
import structlog
from rich.console import Console
from rich.theme import Theme
from typing import Any

# Custom theme for rich output
custom_theme = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "step": "bold magenta",
})

console = Console(theme=custom_theme)


def setup_logging(verbose: bool = False) -> None:
    """Configure structured logging."""
    
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    
    if verbose:
        processors.append(structlog.dev.ConsoleRenderer(colors=True))
    else:
        processors.append(structlog.processors.JSONRenderer())
    
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(0),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.BoundLogger:
    """Get a logger instance with the given name."""
    return structlog.get_logger(name)


class AgentLogger:
    """High-level logger for agent operations with rich output."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.logger = get_logger(agent_name)
    
    def step(self, message: str, step_num: int = None) -> None:
        """Log a step in the pipeline."""
        prefix = f"[Step {step_num}]" if step_num else "[→]"
        console.print(f"[step]{prefix}[/step] [{self.agent_name}] {message}")
        self.logger.info(message, step=step_num)
    
    def success(self, message: str) -> None:
        """Log a success message."""
        console.print(f"[success]✓[/success] [{self.agent_name}] {message}")
        self.logger.info(message, status="success")
    
    def warning(self, message: str) -> None:
        """Log a warning message."""
        console.print(f"[warning]⚠[/warning] [{self.agent_name}] {message}")
        self.logger.warning(message)
    
    def error(self, message: str, exc: Exception = None) -> None:
        """Log an error message."""
        console.print(f"[error]✗[/error] [{self.agent_name}] {message}")
        self.logger.error(message, exc_info=exc)
    
    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info message."""
        console.print(f"[info]ℹ[/info] [{self.agent_name}] {message}")
        self.logger.info(message, **kwargs)
    
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message."""
        self.logger.debug(message, **kwargs)

"""
Build configuration models for DevOps Automation Agent.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


class BuildStatus(Enum):
    """Status of a build operation."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class BuildConfig:
    """Configuration for building a project."""
    # Build commands
    install_command: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    
    # Environment
    env_vars: Dict[str, str] = field(default_factory=dict)
    build_args: Dict[str, str] = field(default_factory=dict)
    
    # Paths
    working_dir: Optional[str] = None
    output_dir: Optional[str] = None
    
    # Options
    skip_tests: bool = False
    parallel: bool = True
    cache_enabled: bool = True
    
    # Timeouts
    install_timeout: int = 300
    build_timeout: int = 600
    test_timeout: int = 300


@dataclass
class BuildResult:
    """Result of a build operation."""
    status: BuildStatus
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Outputs
    artifacts: List[str] = field(default_factory=list)
    logs: List[str] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Stats
    install_success: bool = True
    build_success: bool = True
    test_success: bool = True
    test_count: int = 0
    test_passed: int = 0
    test_failed: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "build_success": self.build_success,
            "test_success": self.test_success,
            "errors": self.errors,
            "warnings": self.warnings,
        }

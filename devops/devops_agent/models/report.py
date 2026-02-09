"""
Pipeline report models for DevOps Automation Agent.
Final output that summarizes the entire pipeline execution.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


class PipelineStatus(Enum):
    """Overall pipeline status."""
    SUCCESS = "success"
    PARTIAL = "partial"  # Some stages failed but deployment succeeded
    FAILED = "failed"


class Stage(Enum):
    """Pipeline stages."""
    ANALYSIS = "analysis"
    BUILD = "build"
    CONTAINERIZE = "containerize"
    CICD = "cicd"
    INFRASTRUCTURE = "infrastructure"
    DEPLOY = "deploy"


@dataclass
class StageResult:
    """Result of a single pipeline stage."""
    stage: Stage
    success: bool
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Details
    message: str = ""
    outputs: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    # Generated artifacts
    files_generated: List[str] = field(default_factory=list)


@dataclass
class PipelineReport:
    """
    Complete pipeline execution report.
    This is the final output of the DevOps Automation Agent.
    """
    # Identification
    pipeline_id: str
    project_name: str
    
    # Status
    status: PipelineStatus
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Stage results
    stages: Dict[Stage, StageResult] = field(default_factory=dict)
    
    # Key outputs
    project_type: Optional[str] = None
    framework: Optional[str] = None
    deployment_url: Optional[str] = None
    container_image: Optional[str] = None
    cicd_pipeline_url: Optional[str] = None
    
    # Generated files
    generated_files: Dict[str, str] = field(default_factory=dict)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    
    # Integration with other agents
    security_scan_passed: Optional[bool] = None
    test_results_passed: Optional[bool] = None
    
    def add_stage_result(self, result: StageResult) -> None:
        """Add a stage result to the report."""
        self.stages[result.stage] = result
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the pipeline execution."""
        return {
            "pipeline_id": self.pipeline_id,
            "project_name": self.project_name,
            "status": self.status.value,
            "duration_seconds": self.duration_seconds,
            "project_type": self.project_type,
            "framework": self.framework,
            "deployment_url": self.deployment_url,
            "container_image": self.container_image,
            "stages": {
                stage.value: {
                    "success": result.success,
                    "duration": result.duration_seconds,
                    "errors": len(result.errors),
                }
                for stage, result in self.stages.items()
            },
            "recommendations": self.recommendations,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to full dictionary."""
        return {
            "pipeline_id": self.pipeline_id,
            "project_name": self.project_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "project_type": self.project_type,
            "framework": self.framework,
            "deployment_url": self.deployment_url,
            "container_image": self.container_image,
            "cicd_pipeline_url": self.cicd_pipeline_url,
            "stages": {
                stage.value: {
                    "success": result.success,
                    "message": result.message,
                    "duration_seconds": result.duration_seconds,
                    "errors": result.errors,
                    "warnings": result.warnings,
                    "files_generated": result.files_generated,
                }
                for stage, result in self.stages.items()
            },
            "generated_files": list(self.generated_files.keys()),
            "recommendations": self.recommendations,
            "security_scan_passed": self.security_scan_passed,
            "test_results_passed": self.test_results_passed,
        }
    
    def to_markdown(self) -> str:
        """Generate a markdown report."""
        lines = [
            f"# Pipeline Report: {self.project_name}",
            "",
            f"**Pipeline ID:** `{self.pipeline_id}`",
            f"**Status:** {self.status.value.upper()}",
            f"**Duration:** {self.duration_seconds:.2f} seconds",
            "",
            "## Project Details",
            f"- **Type:** {self.project_type}",
            f"- **Framework:** {self.framework}",
            "",
        ]
        
        if self.deployment_url:
            lines.extend([
                "## Deployment",
                f"🚀 **Live URL:** [{self.deployment_url}]({self.deployment_url})",
                "",
            ])
        
        if self.container_image:
            lines.extend([
                "## Container",
                f"📦 **Image:** `{self.container_image}`",
                "",
            ])
        
        lines.extend([
            "## Stages",
            "",
        ])
        
        for stage, result in self.stages.items():
            icon = "✅" if result.success else "❌"
            lines.append(f"### {icon} {stage.value.title()}")
            lines.append(f"- Duration: {result.duration_seconds:.2f}s")
            if result.message:
                lines.append(f"- {result.message}")
            if result.errors:
                lines.append("- Errors:")
                for error in result.errors:
                    lines.append(f"  - {error}")
            lines.append("")
        
        if self.recommendations:
            lines.extend([
                "## Recommendations",
                "",
            ])
            for rec in self.recommendations:
                lines.append(f"- {rec}")
        
        return "\n".join(lines)

"""
Dev Pilot Orchestrator - Main pipeline coordinator.

Orchestrates the entire deployment pipeline:
1. Validate preconditions (Security/QA status)
2. Clone & analyze repository
3. Generate missing configs
4. Build with Cloud Build
5. Deploy to Cloud Run
6. Health check
7. Rollback if unhealthy

All operations are logged and versioned.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from ..core.logger import get_logger
from ..core.cloud_logging_client import PipelineLogger
from ..integrations.github_client import GitHubClient
from ..config import get_config

from .base_agent import BaseAgent
from .precondition_validator import (
    PreconditionValidator,
    PipelineInput,
    ValidationResult,
)
from .project_analyzer import ProjectAnalyzer
from .config_generator import ConfigGenerator, ConfigGeneratorResult
from .cloud_build_agent import CloudBuildAgent, CloudBuildAgentResult
from .cloud_run_deploy_agent import (
    CloudRunDeployAgent,
    CloudRunDeployResult,
    DeploymentConfig,
)
from .health_check_agent import HealthCheckAgent, HealthCheckAgentResult
from .rollback_agent import RollbackAgent, RollbackResult


class PipelineStep(Enum):
    """Pipeline execution steps."""
    VALIDATE_PRECONDITIONS = "validate_preconditions"
    CLONE_REPO = "clone_repo"
    ANALYZE_PROJECT = "analyze_project"
    GENERATE_CONFIGS = "generate_configs"
    BUILD_IMAGE = "build_image"
    DEPLOY_SERVICE = "deploy_service"
    HEALTH_CHECK = "health_check"
    ROLLBACK = "rollback"
    COMPLETE = "complete"


class PipelineStatus(Enum):
    """Overall pipeline status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class StepResult:
    """Result of a pipeline step."""
    step: PipelineStep
    success: bool
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "step": self.step.value,
            "success": self.success,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class PipelineReport:
    """Complete pipeline execution report."""
    deployment_id: str
    status: PipelineStatus
    started_at: datetime
    finished_at: Optional[datetime] = None
    total_duration_seconds: float = 0
    
    # Input
    repo_url: Optional[str] = None
    branch: str = "devpilot-tested"
    commit_hash: Optional[str] = None
    
    # Output
    service_url: Optional[str] = None
    image_url: Optional[str] = None
    revision_name: Optional[str] = None
    
    # Steps
    steps: List[StepResult] = field(default_factory=list)
    
    # Errors
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "deployment_id": self.deployment_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "total_duration_seconds": self.total_duration_seconds,
            "repo_url": self.repo_url,
            "branch": self.branch,
            "commit_hash": self.commit_hash,
            "service_url": self.service_url,
            "image_url": self.image_url,
            "revision_name": self.revision_name,
            "steps": [s.to_dict() for s in self.steps],
            "errors": self.errors,
        }


@dataclass
class DevPilotConfig:
    """Configuration for Dev Pilot pipeline."""
    # GCP settings
    project_id: Optional[str] = None
    region: str = "us-central1"
    
    # Deployment settings
    service_name: Optional[str] = None
    image_name: Optional[str] = None
    
    # Cloud Run settings
    port: int = 8080
    cpu: str = "1"
    memory: str = "512Mi"
    min_instances: int = 0
    max_instances: int = 10
    
    # Environment
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    # Pipeline settings
    auto_rollback: bool = True
    strict_validation: bool = True
    
    # Working directory
    work_dir: Optional[Path] = None


class DevPilotOrchestrator(BaseAgent):
    """
    Dev Pilot Orchestrator - Main pipeline coordinator.
    
    This is the entry point for the autonomous DevOps pipeline.
    It coordinates all agents to take a GitHub repository from
    code to production on GCP Cloud Run.
    
    Usage:
        orchestrator = DevPilotOrchestrator(
            config=DevPilotConfig(
                project_id="my-project",
                region="us-central1",
            )
        )
        
        report = await orchestrator.run(
            repo_url="https://github.com/user/repo",
            branch="devpilot-tested",
            security_status="PASS",
            qa_status="PASS",
        )
        
        if report.status == PipelineStatus.SUCCESS:
            print(f"Deployed: {report.service_url}")
    """
    
    def __init__(
        self,
        working_dir: Path = None,
        gemini_client=None,
        config: DevPilotConfig = None,
    ):
        """
        Initialize the Dev Pilot Orchestrator.
        
        Args:
            working_dir: Working directory
            gemini_client: Gemini client for AI reasoning
            config: Pipeline configuration
        """
        super().__init__(working_dir, gemini_client)
        self.config = config or DevPilotConfig()
        self.app_config = get_config()
        
        # Apply config defaults from environment
        if not self.config.project_id:
            self.config.project_id = self.app_config.gcp.project_id
        if not self.config.region:
            self.config.region = self.app_config.gcp.region
            
        self.logger = get_logger("DevPilotOrchestrator")
        
        # Initialize agents
        self._init_agents()
        
    def _init_agents(self):
        """Initialize all pipeline agents."""
        self.validator = PreconditionValidator(
            strict_mode=self.config.strict_validation,
        )
        
        self.analyzer = ProjectAnalyzer(
            gemini_client=self.gemini,
        )
        
        self.config_generator = ConfigGenerator(
            gemini_client=self.gemini,
            write_files=True,
        )
        
        self.build_agent = CloudBuildAgent(
            gemini_client=self.gemini,
            project_id=self.config.project_id,
            region=self.config.region,
        )
        
        self.deploy_agent = CloudRunDeployAgent(
            gemini_client=self.gemini,
            project_id=self.config.project_id,
            region=self.config.region,
        )
        
        self.health_agent = HealthCheckAgent()
        
        self.rollback_agent = RollbackAgent(
            project_id=self.config.project_id,
            region=self.config.region,
        )
        
    def _get_system_instruction(self) -> str:
        """Get system instruction."""
        return """You are the Dev Pilot orchestrator, an autonomous DevOps agent.

Your job is to take a GitHub repository and deploy it to production on GCP Cloud Run.
You coordinate multiple agents to validate, build, deploy, and verify the deployment.

RULES:
1. NEVER deploy if Security or QA status is not PASS
2. Always validate preconditions first
3. Generate missing configs automatically
4. Retry build once on failure
5. Retry deploy once on failure
6. Run health check after deployment
7. Rollback automatically if unhealthy
8. Log every step
9. Version every deployment"""
    
    async def run(
        self,
        repo_url: str,
        branch: str = "devpilot-tested",
        security_status: str = "PASS",
        qa_status: str = "PASS",
        commit_hash: str = None,
        on_step: Callable[[StepResult], None] = None,
    ) -> PipelineReport:
        """
        Execute the complete deployment pipeline.
        
        Args:
            repo_url: GitHub repository URL
            branch: Branch to deploy (default: devpilot-tested)
            security_status: Security stage status
            qa_status: QA stage status
            commit_hash: Optional commit hash
            on_step: Callback for step completion
            
        Returns:
            PipelineReport with deployment results
        """
        # Generate deployment ID
        deployment_id = f"dp-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        
        # Initialize report
        report = PipelineReport(
            deployment_id=deployment_id,
            status=PipelineStatus.RUNNING,
            started_at=datetime.now(),
            repo_url=repo_url,
            branch=branch,
            commit_hash=commit_hash,
        )
        
        # Initialize cloud logging
        pipeline_logger = PipelineLogger(
            deployment_id=deployment_id,
            project_id=self.config.project_id,
        )
        
        self.logger.info("=" * 70)
        self.logger.info("DEV PILOT - AUTONOMOUS DEPLOYMENT PIPELINE")
        self.logger.info("=" * 70)
        self.logger.info(f"Deployment ID: {deployment_id}")
        self.logger.info(f"Repository: {repo_url}")
        self.logger.info(f"Branch: {branch}")
        self.logger.info("=" * 70)
        
        # Track current project info and results
        project_info = None
        build_result = None
        deploy_result = None
        
        try:
            # ═══════════════════════════════════════════════════════════
            # STEP 1: VALIDATE PRECONDITIONS
            # ═══════════════════════════════════════════════════════════
            step_result = await self._run_step(
                PipelineStep.VALIDATE_PRECONDITIONS,
                pipeline_logger,
                lambda: self._validate_preconditions(
                    repo_url, branch, security_status, qa_status
                ),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                report.status = PipelineStatus.FAILED
                report.errors.append(f"Precondition validation failed: {step_result.error}")
                return await self._finalize_report(report, pipeline_logger)
                
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # STEP 2: CLONE REPOSITORY
            # ═══════════════════════════════════════════════════════════
            step_result = await self._run_step(
                PipelineStep.CLONE_REPO,
                pipeline_logger,
                lambda: self._clone_repository(repo_url, branch),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                report.status = PipelineStatus.FAILED
                report.errors.append(f"Clone failed: {step_result.error}")
                return await self._finalize_report(report, pipeline_logger)
                
            project_path = Path(step_result.data.get("path"))
            
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # STEP 3: ANALYZE PROJECT
            # ═══════════════════════════════════════════════════════════
            step_result = await self._run_step(
                PipelineStep.ANALYZE_PROJECT,
                pipeline_logger,
                lambda: self._analyze_project(project_path),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                report.status = PipelineStatus.FAILED
                report.errors.append(f"Analysis failed: {step_result.error}")
                return await self._finalize_report(report, pipeline_logger)
                
            project_info = step_result.data.get("project_info")
            
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # STEP 4: GENERATE CONFIGS
            # ═══════════════════════════════════════════════════════════
            step_result = await self._run_step(
                PipelineStep.GENERATE_CONFIGS,
                pipeline_logger,
                lambda: self._generate_configs(project_info),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                report.status = PipelineStatus.FAILED
                report.errors.append(f"Config generation failed: {step_result.error}")
                return await self._finalize_report(report, pipeline_logger)
                
            runtime_config = step_result.data.get("runtime_config")
            
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # STEP 5: BUILD IMAGE
            # ═══════════════════════════════════════════════════════════
            image_name = self.config.image_name or project_info.name.lower().replace(" ", "-")
            
            step_result = await self._run_step(
                PipelineStep.BUILD_IMAGE,
                pipeline_logger,
                lambda: self._build_image(project_info, image_name, commit_hash),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                report.status = PipelineStatus.FAILED
                report.errors.append(f"Build failed: {step_result.error}")
                return await self._finalize_report(report, pipeline_logger)
                
            build_result = step_result.data.get("build_result")
            report.image_url = build_result.image_url
            
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # STEP 6: DEPLOY SERVICE
            # ═══════════════════════════════════════════════════════════
            service_name = self.config.service_name or image_name
            
            step_result = await self._run_step(
                PipelineStep.DEPLOY_SERVICE,
                pipeline_logger,
                lambda: self._deploy_service(
                    service_name,
                    build_result.image_url,
                    runtime_config,
                ),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                report.status = PipelineStatus.FAILED
                report.errors.append(f"Deployment failed: {step_result.error}")
                return await self._finalize_report(report, pipeline_logger)
                
            deploy_result = step_result.data.get("deploy_result")
            report.service_url = deploy_result.service_url
            report.revision_name = deploy_result.revision_name
            
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # STEP 7: HEALTH CHECK
            # ═══════════════════════════════════════════════════════════
            health_endpoint = runtime_config.get("health_check_path", "/health") if runtime_config else "/health"
            
            step_result = await self._run_step(
                PipelineStep.HEALTH_CHECK,
                pipeline_logger,
                lambda: self._health_check(deploy_result.service_url, health_endpoint),
            )
            report.steps.append(step_result)
            
            if not step_result.success:
                # HEALTH CHECK FAILED - ROLLBACK
                self.logger.error("Health check failed - initiating rollback")
                
                if self.config.auto_rollback and deploy_result.previous_revision:
                    rollback_step = await self._run_step(
                        PipelineStep.ROLLBACK,
                        pipeline_logger,
                        lambda: self._rollback(
                            service_name,
                            deploy_result.revision_name,
                            deploy_result.previous_revision,
                        ),
                    )
                    report.steps.append(rollback_step)
                    
                    if rollback_step.success:
                        report.status = PipelineStatus.ROLLED_BACK
                        report.errors.append("Deployment was unhealthy, rolled back to previous version")
                    else:
                        report.status = PipelineStatus.FAILED
                        report.errors.append("Deployment unhealthy and rollback failed")
                else:
                    report.status = PipelineStatus.FAILED
                    report.errors.append("Deployment unhealthy, no previous revision for rollback")
                    
                return await self._finalize_report(report, pipeline_logger)
                
            if on_step:
                on_step(step_result)
                
            # ═══════════════════════════════════════════════════════════
            # SUCCESS!
            # ═══════════════════════════════════════════════════════════
            report.status = PipelineStatus.SUCCESS
            
        except Exception as e:
            report.status = PipelineStatus.FAILED
            report.errors.append(f"Pipeline exception: {str(e)}")
            self.logger.error(f"Pipeline exception: {e}")
            import traceback
            traceback.print_exc()
            
        return await self._finalize_report(report, pipeline_logger)
    
    async def _run_step(
        self,
        step: PipelineStep,
        pipeline_logger: PipelineLogger,
        action: Callable,
    ) -> StepResult:
        """Run a pipeline step with logging."""
        result = StepResult(
            step=step,
            success=False,
            started_at=datetime.now(),
        )
        
        self.logger.info("")
        self.logger.info(f"▶ STEP: {step.value.upper()}")
        self.logger.info("-" * 50)
        
        await pipeline_logger.start_step(step.value)
        
        try:
            step_data = await action()
            
            result.success = step_data.get("success", False)
            result.message = step_data.get("message", "")
            result.data = step_data
            result.error = step_data.get("error")
            
        except Exception as e:
            result.error = str(e)
            result.message = f"Step failed: {e}"
            self.logger.error(f"Step {step.value} failed: {e}")
            
        result.finished_at = datetime.now()
        result.duration_seconds = (result.finished_at - result.started_at).total_seconds()
        
        await pipeline_logger.end_step(
            step.value,
            success=result.success,
            message=result.message,
            metadata={"duration": result.duration_seconds},
        )
        
        if result.success:
            self.logger.info(f"✅ {step.value} completed in {result.duration_seconds:.1f}s")
        else:
            self.logger.error(f"❌ {step.value} failed: {result.error}")
            
        return result
    
    async def _validate_preconditions(
        self,
        repo_url: str,
        branch: str,
        security_status: str,
        qa_status: str,
    ) -> Dict[str, Any]:
        """Validate preconditions."""
        input_data = PipelineInput(
            repo_url=repo_url,
            branch=branch,
            security_status=security_status,
            qa_status=qa_status,
        )
        
        result = await self.validator.validate(input_data)
        
        return {
            "success": result.passed,
            "message": result.summary,
            "error": None if result.passed else result.summary,
            "validation_result": result.to_dict(),
        }
    
    async def _clone_repository(
        self,
        repo_url: str,
        branch: str,
    ) -> Dict[str, Any]:
        """Clone the repository."""
        import tempfile
        import subprocess
        
        # Create temp directory
        work_dir = self.config.work_dir or Path(tempfile.mkdtemp(prefix="devpilot-"))
        
        self.logger.info(f"Cloning {repo_url} ({branch}) to {work_dir}")
        
        try:
            # Clone repository
            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(work_dir)],
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if result.returncode != 0:
                return {
                    "success": False,
                    "error": f"Git clone failed: {result.stderr}",
                }
                
            # Get commit hash
            commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=str(work_dir),
                capture_output=True,
                text=True,
            )
            
            commit_hash = commit_result.stdout.strip() if commit_result.returncode == 0 else None
            
            return {
                "success": True,
                "message": f"Cloned to {work_dir}",
                "path": str(work_dir),
                "commit_hash": commit_hash,
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def _analyze_project(self, project_path: Path) -> Dict[str, Any]:
        """Analyze the project."""
        project_info = await self.analyzer.run(project_path)
        
        return {
            "success": True,
            "message": f"Detected {project_info.project_type.value} / {project_info.framework.value}",
            "project_info": project_info,
        }
    
    async def _generate_configs(self, project_info) -> Dict[str, Any]:
        """Generate missing configs."""
        result = await self.config_generator.run(project_info)
        
        runtime_config = result.runtime_config.to_dict() if result.runtime_config else {}
        
        return {
            "success": result.success,
            "message": f"Generated {len(result.configs)} config files",
            "configs": [c.to_dict() for c in result.configs],
            "runtime_config": runtime_config,
        }
    
    async def _build_image(
        self,
        project_info,
        image_name: str,
        commit_hash: str = None,
    ) -> Dict[str, Any]:
        """Build Docker image."""
        result = await self.build_agent.run(
            project_info=project_info,
            image_name=image_name,
            commit_hash=commit_hash,
        )
        
        return {
            "success": result.success,
            "message": f"Image: {result.image_url}" if result.success else "Build failed",
            "error": result.errors[0] if result.errors else None,
            "build_result": result,
        }
    
    async def _deploy_service(
        self,
        service_name: str,
        image_url: str,
        runtime_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deploy to Cloud Run."""
        deploy_config = DeploymentConfig(
            port=runtime_config.get("port", self.config.port),
            cpu=self.config.cpu,
            memory=self.config.memory,
            min_instances=self.config.min_instances,
            max_instances=self.config.max_instances,
            env_vars={**self.config.env_vars, **runtime_config.get("env_vars", {})},
        )
        
        result = await self.deploy_agent.run(
            service_name=service_name,
            image_url=image_url,
            config=deploy_config,
        )
        
        return {
            "success": result.success,
            "message": f"URL: {result.service_url}" if result.success else "Deploy failed",
            "error": result.errors[0] if result.errors else None,
            "deploy_result": result,
        }
    
    async def _health_check(
        self,
        service_url: str,
        health_endpoint: str,
    ) -> Dict[str, Any]:
        """Run health check."""
        result = await self.health_agent.run(
            service_url=service_url,
            health_endpoint=health_endpoint,
        )
        
        return {
            "success": result.healthy,
            "message": "Service healthy" if result.healthy else "Service unhealthy",
            "error": result.errors[0] if result.errors else None,
            "health_result": result.to_dict(),
        }
    
    async def _rollback(
        self,
        service_name: str,
        current_revision: str,
        target_revision: str,
    ) -> Dict[str, Any]:
        """Rollback to previous revision."""
        result = await self.rollback_agent.run(
            service_name=service_name,
            current_revision=current_revision,
            target_revision=target_revision,
        )
        
        return {
            "success": result.success,
            "message": f"Rolled back to {result.rolled_back_to}" if result.success else "Rollback failed",
            "error": result.errors[0] if result.errors else None,
            "rollback_result": result.to_dict(),
        }
    
    async def _finalize_report(
        self,
        report: PipelineReport,
        pipeline_logger: PipelineLogger,
    ) -> PipelineReport:
        """Finalize the pipeline report."""
        report.finished_at = datetime.now()
        report.total_duration_seconds = (report.finished_at - report.started_at).total_seconds()
        
        # Log pipeline completion
        await pipeline_logger.complete_pipeline(
            success=(report.status == PipelineStatus.SUCCESS),
            service_url=report.service_url,
            total_duration=report.total_duration_seconds,
        )
        
        # Print summary
        self.logger.info("")
        self.logger.info("=" * 70)
        self.logger.info("PIPELINE SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Status: {report.status.value}")
        self.logger.info(f"Duration: {report.total_duration_seconds:.1f}s")
        
        if report.service_url:
            self.logger.info(f"Service URL: {report.service_url}")
        if report.image_url:
            self.logger.info(f"Image: {report.image_url}")
            
        if report.errors:
            self.logger.info(f"Errors: {len(report.errors)}")
            for error in report.errors:
                self.logger.error(f"  - {error}")
                
        self.logger.info("=" * 70)
        
        return report
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check prerequisites for the orchestrator."""
        return {
            "project_id": self.config.project_id,
            "region": self.config.region,
            "gemini_available": self.gemini is not None,
            "agents": {
                "validator": self.validator.check_prerequisites(),
                "build": self.build_agent.check_prerequisites(),
                "deploy": self.deploy_agent.check_prerequisites(),
            },
        }


# Convenience function
async def deploy_from_github(
    repo_url: str,
    branch: str = "devpilot-tested",
    security_status: str = "PASS",
    qa_status: str = "PASS",
    project_id: str = None,
    region: str = None,
) -> PipelineReport:
    """
    Deploy a GitHub repository to Cloud Run.
    
    Args:
        repo_url: GitHub repository URL
        branch: Branch to deploy
        security_status: Security stage status
        qa_status: QA stage status
        project_id: GCP project ID
        region: GCP region
        
    Returns:
        PipelineReport with deployment results
    """
    config = DevPilotConfig(
        project_id=project_id,
        region=region or "us-central1",
    )
    
    orchestrator = DevPilotOrchestrator(config=config)
    
    return await orchestrator.run(
        repo_url=repo_url,
        branch=branch,
        security_status=security_status,
        qa_status=qa_status,
    )

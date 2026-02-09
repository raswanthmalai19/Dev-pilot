"""
Cloud Run Deploy Agent - Handles deployment to GCP Cloud Run.

Responsible for:
- Deploying Docker images to Cloud Run
- Configuring resources, scaling, and networking
- Waiting for deployment completion
- Handling deployment failures with retry
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent
from ..models.project import ProjectInfo
from ..core.cloud_run_client import (
    CloudRunClient,
    CloudRunResult,
    ServiceConfig,
    ServiceStatus,
)
from ..core.gemini_client import GeminiClient
from ..core.logger import get_logger


@dataclass
class DeploymentAttempt:
    """Record of a deployment attempt."""
    attempt_number: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    success: bool = False
    revision_name: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "attempt_number": self.attempt_number,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "success": self.success,
            "revision_name": self.revision_name,
            "error": self.error,
        }


@dataclass
class DeploymentConfig:
    """Configuration for deployment."""
    # Container settings
    port: int = 8080
    
    # Resources (default: small for MVP)
    cpu: str = "1"
    memory: str = "512Mi"
    
    # Scaling
    min_instances: int = 0
    max_instances: int = 10
    
    # Access
    allow_unauthenticated: bool = True
    
    # Environment
    env_vars: Dict[str, str] = field(default_factory=dict)
    
    # Timeout
    timeout_seconds: int = 300


@dataclass
class CloudRunDeployResult:
    """Result of Cloud Run deployment."""
    success: bool
    service_name: Optional[str] = None
    service_url: Optional[str] = None
    revision_name: Optional[str] = None
    previous_revision: Optional[str] = None
    attempts: List[DeploymentAttempt] = field(default_factory=list)
    total_duration_seconds: float = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "service_name": self.service_name,
            "service_url": self.service_url,
            "revision_name": self.revision_name,
            "previous_revision": self.previous_revision,
            "attempts": [a.to_dict() for a in self.attempts],
            "total_duration_seconds": self.total_duration_seconds,
            "errors": self.errors,
        }


class CloudRunDeployAgent(BaseAgent):
    """
    Cloud Run Deploy Agent for deploying containers to GCP Cloud Run.
    
    Features:
    - Deploys Docker images to Cloud Run
    - Configures resources, scaling, networking
    - Enables public access
    - Handles retries on failure
    - Tracks revision history for rollback
    
    Usage:
        agent = CloudRunDeployAgent(project_id="my-project")
        result = await agent.run(
            service_name="my-app",
            image_url="gcr.io/my-project/my-app:v1",
            config=DeploymentConfig(port=8080),
        )
        
        if result.success:
            print(f"Deployed: {result.service_url}")
    """
    
    MAX_RETRIES = 1  # Retry once as per requirements
    
    def __init__(
        self,
        working_dir: Path = None,
        gemini_client: GeminiClient = None,
        project_id: str = None,
        region: str = None,
    ):
        """
        Initialize the Cloud Run Deploy Agent.
        
        Args:
            working_dir: Working directory
            gemini_client: Gemini client
            project_id: GCP project ID
            region: GCP region
        """
        super().__init__(working_dir, gemini_client)
        self.cloud_run = CloudRunClient(project_id=project_id, region=region)
        self.logger = get_logger("CloudRunDeployAgent")
        
    def _get_system_instruction(self) -> str:
        """Get system instruction for the agent."""
        return """You are an expert at Cloud Run deployments and troubleshooting.

When presented with a deployment error, analyze the root cause and suggest fixes:
1. Image pull errors
2. Resource limit issues
3. Port configuration problems
4. Environment variable issues
5. Permission/IAM problems

Provide actionable fixes for Cloud Run deployment issues."""
    
    async def run(
        self,
        service_name: str,
        image_url: str,
        config: DeploymentConfig = None,
        project_info: ProjectInfo = None,
    ) -> CloudRunDeployResult:
        """
        Deploy a Docker image to Cloud Run.
        
        Args:
            service_name: Name for the Cloud Run service
            image_url: Full URL to the Docker image
            config: Deployment configuration
            project_info: Optional project info for additional context
            
        Returns:
            CloudRunDeployResult with deployment status
        """
        result = CloudRunDeployResult(success=False, service_name=service_name)
        started_at = datetime.now()
        config = config or DeploymentConfig()
        
        self.logger.info("=" * 60)
        self.logger.info("CLOUD RUN DEPLOY AGENT")
        self.logger.info("=" * 60)
        self.logger.info(f"Service: {service_name}")
        self.logger.info(f"Image: {image_url}")
        self.logger.info(f"Port: {config.port}")
        self.logger.info(f"Resources: {config.cpu} CPU, {config.memory} memory")
        
        # Check for existing service and get previous revision
        try:
            existing = await self.cloud_run.get_service_status(service_name)
            if existing.success and existing.revision_name:
                result.previous_revision = existing.revision_name
                self.logger.info(f"Previous revision: {result.previous_revision}")
        except Exception:
            self.logger.info("No previous deployment found")
            
        # Build service config
        service_config = ServiceConfig(
            image_url=image_url,
            port=config.port,
            cpu=config.cpu,
            memory=config.memory,
            min_instances=config.min_instances,
            max_instances=config.max_instances,
            timeout_seconds=config.timeout_seconds,
            env_vars=config.env_vars,
            allow_unauthenticated=config.allow_unauthenticated,
        )
        
        # Deploy with retry logic
        attempt_number = 0
        last_error = None
        
        while attempt_number <= self.MAX_RETRIES:
            attempt_number += 1
            attempt = DeploymentAttempt(
                attempt_number=attempt_number,
                started_at=datetime.now(),
            )
            
            self.logger.info(f"Deployment attempt {attempt_number}/{self.MAX_RETRIES + 1}")
            
            try:
                deploy_result = await self.cloud_run.deploy_service(
                    service_name=service_name,
                    config=service_config,
                    wait_for_ready=True,
                    timeout_seconds=600,
                )
                
                attempt.finished_at = datetime.now()
                
                if deploy_result.success:
                    attempt.success = True
                    attempt.revision_name = deploy_result.revision_name
                    result.success = True
                    result.service_url = deploy_result.service_url
                    result.revision_name = deploy_result.revision_name
                    result.attempts.append(attempt)
                    
                    self.logger.info(f"✅ Deployment succeeded!")
                    self.logger.info(f"URL: {result.service_url}")
                    self.logger.info(f"Revision: {result.revision_name}")
                    break
                else:
                    last_error = deploy_result.errors[0] if deploy_result.errors else "Unknown error"
                    attempt.error = last_error
                    result.attempts.append(attempt)
                    
                    self.logger.error(f"❌ Deployment failed: {last_error}")
                    
            except Exception as e:
                attempt.finished_at = datetime.now()
                attempt.error = str(e)
                result.attempts.append(attempt)
                last_error = str(e)
                self.logger.error(f"Deployment exception: {e}")
                
        # Final result
        result.total_duration_seconds = (datetime.now() - started_at).total_seconds()
        
        if not result.success:
            result.errors.append(f"Deployment failed after {attempt_number} attempts: {last_error}")
            self.logger.error(f"❌ DEPLOYMENT FAILED after {attempt_number} attempts")
        else:
            self.logger.info(f"✅ DEPLOYMENT COMPLETED in {result.total_duration_seconds:.1f}s")
            
        self.logger.info("=" * 60)
        
        return result
    
    async def get_service_status(self, service_name: str) -> CloudRunResult:
        """Get the current status of a service."""
        return await self.cloud_run.get_service_status(service_name)
    
    async def rollback(
        self,
        service_name: str,
        target_revision: str = None,
    ) -> CloudRunDeployResult:
        """
        Rollback to a previous revision.
        
        Args:
            service_name: Name of the service
            target_revision: Specific revision to rollback to
            
        Returns:
            CloudRunDeployResult with rollback status
        """
        result = CloudRunDeployResult(success=False, service_name=service_name)
        started_at = datetime.now()
        
        self.logger.info(f"Rolling back {service_name}...")
        
        rollback_result = await self.cloud_run.rollback_revision(
            service_name=service_name,
            target_revision=target_revision,
        )
        
        result.total_duration_seconds = (datetime.now() - started_at).total_seconds()
        
        if rollback_result.success:
            result.success = True
            result.service_url = rollback_result.service_url
            result.revision_name = rollback_result.revision_name
            self.logger.info(f"✅ Rollback succeeded: {result.revision_name}")
        else:
            result.errors = rollback_result.errors
            self.logger.error(f"❌ Rollback failed: {rollback_result.errors}")
            
        return result
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check prerequisites for the agent."""
        return {
            "cloud_run": self.cloud_run.check_prerequisites(),
            "gemini_available": self.gemini is not None,
        }


# Convenience function
async def deploy_to_cloud_run(
    service_name: str,
    image_url: str,
    port: int = 8080,
    project_id: str = None,
    region: str = None,
    env_vars: Dict[str, str] = None,
) -> CloudRunDeployResult:
    """
    Deploy a container to Cloud Run.
    
    Args:
        service_name: Name for the service
        image_url: Full image URL
        port: Container port
        project_id: GCP project ID
        region: GCP region
        env_vars: Environment variables
        
    Returns:
        CloudRunDeployResult with deployment status
    """
    agent = CloudRunDeployAgent(project_id=project_id, region=region)
    
    config = DeploymentConfig(
        port=port,
        env_vars=env_vars or {},
    )
    
    return await agent.run(service_name, image_url, config)

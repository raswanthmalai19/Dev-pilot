"""
Rollback Agent - Handles automatic rollback on deployment failures.

Responsible for:
- Rolling back to previous revision
- Verifying rollback success
- Logging rollback actions
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent
from ..core.cloud_run_client import CloudRunClient
from ..core.logger import get_logger


@dataclass
class RollbackResult:
    """Result of a rollback operation."""
    success: bool
    service_name: str
    rolled_back_from: Optional[str] = None
    rolled_back_to: Optional[str] = None
    service_url: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "service_name": self.service_name,
            "rolled_back_from": self.rolled_back_from,
            "rolled_back_to": self.rolled_back_to,
            "service_url": self.service_url,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
        }


class RollbackAgent(BaseAgent):
    """
    Rollback Agent for automatic rollback on deployment failures.
    
    Features:
    - Rolls back Cloud Run services to previous revision
    - Verifies rollback success
    - Logs all rollback actions
    
    Usage:
        agent = RollbackAgent(project_id="my-project")
        result = await agent.run(
            service_name="my-app",
            current_revision="my-app-00002-xyz",
            target_revision="my-app-00001-abc",  # optional
        )
        
        if result.success:
            print(f"Rolled back to: {result.rolled_back_to}")
    """
    
    def __init__(
        self,
        working_dir=None,
        gemini_client=None,
        project_id: str = None,
        region: str = None,
    ):
        """
        Initialize the Rollback Agent.
        
        Args:
            working_dir: Working directory
            gemini_client: Gemini client
            project_id: GCP project ID
            region: GCP region
        """
        super().__init__(working_dir, gemini_client)
        self.cloud_run = CloudRunClient(project_id=project_id, region=region)
        self.logger = get_logger("RollbackAgent")
        
    def _get_system_instruction(self) -> str:
        """Get system instruction for the agent."""
        return "You are an expert at managing service rollbacks and version control."
    
    async def run(
        self,
        service_name: str,
        current_revision: str = None,
        target_revision: str = None,
        verify_health: bool = True,
    ) -> RollbackResult:
        """
        Rollback a Cloud Run service to a previous revision.
        
        Args:
            service_name: Name of the service
            current_revision: Current (failing) revision name
            target_revision: Target revision to rollback to (auto-detect if None)
            verify_health: Whether to verify health after rollback
            
        Returns:
            RollbackResult with rollback status
        """
        result = RollbackResult(
            success=False,
            service_name=service_name,
            rolled_back_from=current_revision,
        )
        result.started_at = datetime.now()
        
        self.logger.info("=" * 60)
        self.logger.info("ROLLBACK AGENT")
        self.logger.info("=" * 60)
        self.logger.info(f"Service: {service_name}")
        self.logger.info(f"Current revision: {current_revision or 'auto-detect'}")
        self.logger.info(f"Target revision: {target_revision or 'previous'}")
        
        try:
            # Get available revisions if target not specified
            if not target_revision:
                revisions = await self.cloud_run.list_revisions(service_name, limit=5)
                
                if len(revisions) < 2:
                    result.errors.append("No previous revision available for rollback")
                    self.logger.error("No previous revision available")
                    result.finished_at = datetime.now()
                    result.duration_seconds = (result.finished_at - result.started_at).total_seconds()
                    return result
                    
                # Find previous revision (skip current)
                for rev in revisions:
                    if current_revision and rev.name == current_revision:
                        continue
                    target_revision = rev.name
                    break
                    
                if not target_revision:
                    target_revision = revisions[1].name  # Second most recent
                    
                self.logger.info(f"Auto-selected target: {target_revision}")
            
            # Perform rollback
            self.logger.info(f"Rolling back to: {target_revision}")
            
            rollback_result = await self.cloud_run.rollback_revision(
                service_name=service_name,
                target_revision=target_revision,
            )
            
            if rollback_result.success:
                result.success = True
                result.rolled_back_to = target_revision
                result.service_url = rollback_result.service_url
                
                self.logger.info(f"✅ Rollback successful!")
                self.logger.info(f"Now running: {target_revision}")
                self.logger.info(f"URL: {result.service_url}")
                
                # Verify health if requested
                if verify_health and result.service_url:
                    await self._verify_rollback_health(result.service_url)
            else:
                result.errors = rollback_result.errors
                self.logger.error(f"❌ Rollback failed: {rollback_result.errors}")
                
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Rollback exception: {e}")
            
        result.finished_at = datetime.now()
        result.duration_seconds = (result.finished_at - result.started_at).total_seconds()
        
        if result.success:
            self.logger.info(f"✅ ROLLBACK COMPLETED in {result.duration_seconds:.1f}s")
        else:
            self.logger.error(f"❌ ROLLBACK FAILED")
            
        self.logger.info("=" * 60)
        
        return result
    
    async def _verify_rollback_health(self, service_url: str) -> bool:
        """Verify health after rollback."""
        try:
            import httpx
            
            health_url = service_url.rstrip("/") + "/health"
            
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(health_url)
                
            if response.status_code in [200, 201, 204]:
                self.logger.info(f"Rollback health check passed (HTTP {response.status_code})")
                return True
            else:
                self.logger.warning(f"Rollback health check returned {response.status_code}")
                return False
                
        except Exception as e:
            self.logger.warning(f"Rollback health check failed: {e}")
            return False
    
    async def get_available_revisions(
        self,
        service_name: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Get available revisions for a service."""
        revisions = await self.cloud_run.list_revisions(service_name, limit=limit)
        return [rev.to_dict() for rev in revisions]
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check prerequisites for the agent."""
        return {
            "cloud_run": self.cloud_run.check_prerequisites(),
        }


# Convenience function
async def rollback_service(
    service_name: str,
    target_revision: str = None,
    project_id: str = None,
    region: str = None,
) -> RollbackResult:
    """
    Rollback a Cloud Run service.
    
    Args:
        service_name: Name of the service
        target_revision: Target revision (auto-detect if None)
        project_id: GCP project ID
        region: GCP region
        
    Returns:
        RollbackResult with rollback status
    """
    agent = RollbackAgent(project_id=project_id, region=region)
    return await agent.run(service_name, target_revision=target_revision)

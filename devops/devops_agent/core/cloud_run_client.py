"""
Cloud Run Client - Native GCP SDK integration for serverless deployment.

Provides:
- Deploy new revisions
- Configure resources (CPU, memory, scaling)
- Manage traffic splitting
- Rollback to previous revisions
- Get service URL and status
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from ..core.logger import get_logger
from ..config import get_config


class ServiceStatus(Enum):
    """Cloud Run service status."""
    UNKNOWN = "UNKNOWN"
    DEPLOYING = "DEPLOYING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class RevisionInfo:
    """Cloud Run revision information."""
    name: str
    service_name: str
    image_url: str
    created_at: Optional[datetime] = None
    traffic_percent: int = 0
    status: ServiceStatus = ServiceStatus.UNKNOWN
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "service_name": self.service_name,
            "image_url": self.image_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "traffic_percent": self.traffic_percent,
            "status": self.status.value,
        }


@dataclass
class ServiceConfig:
    """Cloud Run service configuration."""
    # Container settings
    image_url: str
    port: int = 8080
    
    # Resources
    cpu: str = "1"
    memory: str = "512Mi"
    
    # Scaling
    min_instances: int = 0
    max_instances: int = 10
    
    # Timeout and concurrency
    timeout_seconds: int = 300
    max_concurrent_requests: int = 80
    
    # Environment
    env_vars: Dict[str, str] = field(default_factory=dict)
    secrets: List[str] = field(default_factory=list)
    
    # Access
    allow_unauthenticated: bool = True
    ingress: str = "all"  # all, internal, internal-and-cloud-load-balancing
    
    # Labels
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class CloudRunResult:
    """Result of a Cloud Run operation."""
    success: bool
    service_name: Optional[str] = None
    service_url: Optional[str] = None
    revision_name: Optional[str] = None
    status: ServiceStatus = ServiceStatus.UNKNOWN
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "service_name": self.service_name,
            "service_url": self.service_url,
            "revision_name": self.revision_name,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "errors": self.errors,
        }


class CloudRunClient:
    """
    GCP Cloud Run client for serverless deployment management.
    
    Usage:
        client = CloudRunClient(project_id="my-project", region="us-central1")
        
        # Deploy a new service
        result = await client.deploy_service(
            service_name="my-app",
            config=ServiceConfig(image_url="gcr.io/my-project/my-app:v1"),
        )
        
        if result.success:
            print(f"Service deployed: {result.service_url}")
            
        # Rollback to previous revision
        await client.rollback_revision("my-app", "my-app-00001-abc")
    """
    
    def __init__(
        self,
        project_id: str = None,
        region: str = None,
    ):
        """
        Initialize Cloud Run client.
        
        Args:
            project_id: GCP project ID
            region: GCP region
        """
        self.config = get_config()
        self.project_id = project_id or self.config.gcp.project_id
        self.region = region or self.config.gcp.region
        self.logger = get_logger("CloudRunClient")
        self._client = None
        
    def _get_client(self):
        """Get or create Cloud Run client."""
        if self._client is None:
            try:
                from google.cloud import run_v2
                self._client = run_v2.ServicesClient()
            except ImportError:
                self.logger.error("google-cloud-run not installed")
                raise ImportError("google-cloud-run package required")
        return self._client
    
    def _get_revisions_client(self):
        """Get Cloud Run revisions client."""
        from google.cloud import run_v2
        return run_v2.RevisionsClient()
    
    def _get_parent_path(self) -> str:
        """Get the parent path for services."""
        return f"projects/{self.project_id}/locations/{self.region}"
    
    def _get_service_path(self, service_name: str) -> str:
        """Get the full service path."""
        return f"{self._get_parent_path()}/services/{service_name}"
    
    async def deploy_service(
        self,
        service_name: str,
        config: ServiceConfig,
        wait_for_ready: bool = True,
        timeout_seconds: int = 600,
    ) -> CloudRunResult:
        """
        Deploy a new service or update an existing one.
        
        Args:
            service_name: Name of the service
            config: Service configuration
            wait_for_ready: Wait for deployment to complete
            timeout_seconds: Timeout for waiting
            
        Returns:
            CloudRunResult with deployment status
        """
        from google.cloud import run_v2
        from google.api_core import exceptions
        
        result = CloudRunResult(success=False, service_name=service_name)
        result.started_at = datetime.now()
        
        try:
            client = self._get_client()
            
            self.logger.info(f"Deploying service: {service_name}")
            self.logger.info(f"Image: {config.image_url}")
            
            # Build the service specification
            service = run_v2.Service(
                template=run_v2.RevisionTemplate(
                    containers=[
                        run_v2.Container(
                            image=config.image_url,
                            ports=[run_v2.ContainerPort(container_port=config.port)],
                            resources=run_v2.ResourceRequirements(
                                limits={
                                    "cpu": config.cpu,
                                    "memory": config.memory,
                                },
                            ),
                            env=[
                                run_v2.EnvVar(name=k, value=v)
                                for k, v in config.env_vars.items()
                            ],
                        ),
                    ],
                    scaling=run_v2.RevisionScaling(
                        min_instance_count=config.min_instances,
                        max_instance_count=config.max_instances,
                    ),
                    timeout=f"{config.timeout_seconds}s",
                    max_instance_request_concurrency=config.max_concurrent_requests,
                ),
                ingress=self._parse_ingress(config.ingress),
                labels=config.labels,
            )
            
            # Check if service exists
            try:
                existing_service = client.get_service(name=self._get_service_path(service_name))
                # Update existing service
                service.name = existing_service.name
                operation = client.update_service(service=service)
                self.logger.info(f"Updating existing service: {service_name}")
            except exceptions.NotFound:
                # Create new service
                operation = client.create_service(
                    parent=self._get_parent_path(),
                    service_id=service_name,
                    service=service,
                )
                self.logger.info(f"Creating new service: {service_name}")
            
            # Wait for operation to complete
            if wait_for_ready:
                deployed_service = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: operation.result(timeout=timeout_seconds)
                )
                
                result.success = True
                result.service_url = deployed_service.uri
                result.status = ServiceStatus.READY
                
                # Get the latest revision name
                if deployed_service.latest_ready_revision:
                    result.revision_name = deployed_service.latest_ready_revision.split("/")[-1]
                    
                self.logger.info(f"Service deployed: {result.service_url}")
                if result.revision_name:
                    self.logger.info(f"Revision: {result.revision_name}")
            else:
                result.status = ServiceStatus.DEPLOYING
                result.success = True
                result.logs.append("Deployment started, not waiting for completion")
                
            # Set IAM policy for public access if needed
            if config.allow_unauthenticated:
                await self._set_public_access(service_name)
                
        except Exception as e:
            result.errors.append(str(e))
            result.status = ServiceStatus.FAILED
            self.logger.error(f"Deployment failed: {e}")
            
        result.finished_at = datetime.now()
        if result.started_at:
            result.duration_seconds = (result.finished_at - result.started_at).total_seconds()
            
        return result
    
    async def _set_public_access(self, service_name: str) -> bool:
        """Set IAM policy to allow unauthenticated access."""
        try:
            from google.cloud import run_v2
            from google.iam.v1 import policy_pb2, iam_policy_pb2
            
            client = self._get_client()
            
            # Get current policy
            policy = client.get_iam_policy(
                request=iam_policy_pb2.GetIamPolicyRequest(
                    resource=self._get_service_path(service_name)
                )
            )
            
            # Add allUsers as invoker
            binding = policy_pb2.Binding(
                role="roles/run.invoker",
                members=["allUsers"],
            )
            
            # Check if binding already exists
            has_binding = any(
                b.role == "roles/run.invoker" and "allUsers" in b.members
                for b in policy.bindings
            )
            
            if not has_binding:
                policy.bindings.append(binding)
                client.set_iam_policy(
                    request=iam_policy_pb2.SetIamPolicyRequest(
                        resource=self._get_service_path(service_name),
                        policy=policy,
                    )
                )
                self.logger.info(f"Enabled public access for {service_name}")
                
            return True
            
        except Exception as e:
            self.logger.warning(f"Failed to set public access: {e}")
            return False
    
    def _parse_ingress(self, ingress: str):
        """Parse ingress string to Cloud Run enum."""
        from google.cloud import run_v2
        
        ingress_map = {
            "all": run_v2.IngressTraffic.INGRESS_TRAFFIC_ALL,
            "internal": run_v2.IngressTraffic.INGRESS_TRAFFIC_INTERNAL_ONLY,
            "internal-and-cloud-load-balancing": run_v2.IngressTraffic.INGRESS_TRAFFIC_INTERNAL_LOAD_BALANCER,
        }
        return ingress_map.get(ingress, run_v2.IngressTraffic.INGRESS_TRAFFIC_ALL)
    
    async def get_service_status(self, service_name: str) -> CloudRunResult:
        """
        Get the current status of a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            CloudRunResult with current status
        """
        result = CloudRunResult(success=False, service_name=service_name)
        
        try:
            client = self._get_client()
            service = client.get_service(name=self._get_service_path(service_name))
            
            result.success = True
            result.service_url = service.uri
            result.status = ServiceStatus.READY
            
            if service.latest_ready_revision:
                result.revision_name = service.latest_ready_revision.split("/")[-1]
                
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Failed to get service status: {e}")
            
        return result
    
    async def get_service_url(self, service_name: str) -> Optional[str]:
        """
        Get the public URL of a service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Service URL or None if not found
        """
        try:
            client = self._get_client()
            service = client.get_service(name=self._get_service_path(service_name))
            return service.uri
        except Exception as e:
            self.logger.error(f"Failed to get service URL: {e}")
            return None
    
    async def list_revisions(
        self,
        service_name: str,
        limit: int = 10,
    ) -> List[RevisionInfo]:
        """
        List revisions for a service.
        
        Args:
            service_name: Name of the service
            limit: Maximum number of revisions
            
        Returns:
            List of RevisionInfo objects
        """
        revisions = []
        
        try:
            client = self._get_revisions_client()
            
            # List revisions
            request = {
                "parent": self._get_parent_path(),
            }
            
            for revision in client.list_revisions(request=request):
                # Filter by service name
                if service_name not in revision.service:
                    continue
                    
                if len(revisions) >= limit:
                    break
                    
                revisions.append(RevisionInfo(
                    name=revision.name.split("/")[-1],
                    service_name=service_name,
                    image_url=revision.containers[0].image if revision.containers else "",
                    created_at=revision.create_time.ToDatetime() if hasattr(revision, 'create_time') else None,
                ))
                
        except Exception as e:
            self.logger.error(f"Failed to list revisions: {e}")
            
        return revisions
    
    async def rollback_revision(
        self,
        service_name: str,
        target_revision: str = None,
    ) -> CloudRunResult:
        """
        Rollback to a previous revision.
        
        Args:
            service_name: Name of the service
            target_revision: Specific revision to rollback to, or None for previous
            
        Returns:
            CloudRunResult with rollback status
        """
        from google.cloud import run_v2
        
        result = CloudRunResult(success=False, service_name=service_name)
        result.started_at = datetime.now()
        
        try:
            client = self._get_client()
            
            # Get current service
            service = client.get_service(name=self._get_service_path(service_name))
            
            if not target_revision:
                # Get previous revision
                revisions = await self.list_revisions(service_name, limit=5)
                if len(revisions) < 2:
                    result.errors.append("No previous revision available for rollback")
                    return result
                    
                # Skip the current revision
                current_revision = service.latest_ready_revision.split("/")[-1]
                for rev in revisions:
                    if rev.name != current_revision:
                        target_revision = rev.name
                        break
                        
                if not target_revision:
                    result.errors.append("Could not find a suitable revision for rollback")
                    return result
            
            self.logger.info(f"Rolling back {service_name} to revision {target_revision}")
            
            # Update traffic to point to target revision
            service.traffic = [
                run_v2.TrafficTarget(
                    revision=f"{self._get_parent_path()}/revisions/{target_revision}",
                    percent=100,
                    type_=run_v2.TrafficTargetAllocationType.TRAFFIC_TARGET_ALLOCATION_TYPE_REVISION,
                ),
            ]
            
            operation = client.update_service(service=service)
            
            # Wait for rollback to complete
            rolled_back_service = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: operation.result(timeout=300)
            )
            
            result.success = True
            result.service_url = rolled_back_service.uri
            result.revision_name = target_revision
            result.status = ServiceStatus.READY
            
            self.logger.info(f"Rollback successful: {result.service_url}")
            
        except Exception as e:
            result.errors.append(str(e))
            result.status = ServiceStatus.FAILED
            self.logger.error(f"Rollback failed: {e}")
            
        result.finished_at = datetime.now()
        if result.started_at:
            result.duration_seconds = (result.finished_at - result.started_at).total_seconds()
            
        return result
    
    async def delete_service(self, service_name: str) -> bool:
        """
        Delete a Cloud Run service.
        
        Args:
            service_name: Name of the service
            
        Returns:
            True if deleted successfully
        """
        try:
            client = self._get_client()
            operation = client.delete_service(name=self._get_service_path(service_name))
            
            # Wait for deletion
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: operation.result(timeout=300)
            )
            
            self.logger.info(f"Service {service_name} deleted")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to delete service: {e}")
            return False
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check if prerequisites are met."""
        prerequisites = {
            "project_id": bool(self.project_id),
            "region": bool(self.region),
            "sdk_installed": False,
            "authenticated": False,
        }
        
        try:
            from google.cloud import run_v2
            prerequisites["sdk_installed"] = True
        except ImportError:
            pass
            
        try:
            self._get_client()
            prerequisites["authenticated"] = True
        except Exception:
            pass
            
        return prerequisites


# Convenience function
async def deploy_to_cloud_run(
    service_name: str,
    image_url: str,
    project_id: str = None,
    region: str = None,
    port: int = 8080,
    env_vars: Dict[str, str] = None,
) -> CloudRunResult:
    """
    Deploy a container to Cloud Run.
    
    Args:
        service_name: Name of the service
        image_url: Docker image URL
        project_id: GCP project ID
        region: GCP region
        port: Container port
        env_vars: Environment variables
        
    Returns:
        CloudRunResult with deployment status
    """
    client = CloudRunClient(project_id=project_id, region=region)
    
    config = ServiceConfig(
        image_url=image_url,
        port=port,
        env_vars=env_vars or {},
    )
    
    return await client.deploy_service(service_name, config)

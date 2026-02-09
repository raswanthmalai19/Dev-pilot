"""
Deployment configuration models for DevOps Automation Agent.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime


class DeploymentStatus(Enum):
    """Status of a deployment."""
    PENDING = "pending"
    DEPLOYING = "deploying"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CloudProvider(Enum):
    """Supported cloud providers."""
    GCP = "gcp"
    AWS = "aws"
    AZURE = "azure"
    LOCAL = "local"


class DeploymentTarget(Enum):
    """Deployment target types."""
    CLOUD_RUN = "cloud_run"
    KUBERNETES = "kubernetes"
    APP_ENGINE = "app_engine"
    ECS = "ecs"
    LOCAL_DOCKER = "local_docker"


@dataclass
class ContainerConfig:
    """Docker container configuration."""
    image_name: str
    image_tag: str = "latest"
    registry_url: Optional[str] = None
    
    # Build settings
    dockerfile_path: str = "Dockerfile"
    build_context: str = "."
    build_args: Dict[str, str] = field(default_factory=dict)
    
    # Runtime settings
    port: int = 8080
    env_vars: Dict[str, str] = field(default_factory=dict)
    secrets: List[str] = field(default_factory=list)
    
    # Resources
    memory: str = "512Mi"
    cpu: str = "1"
    min_instances: int = 0
    max_instances: int = 10
    
    @property
    def full_image_name(self) -> str:
        """Get full image name with registry."""
        if self.registry_url:
            return f"{self.registry_url}/{self.image_name}:{self.image_tag}"
        return f"{self.image_name}:{self.image_tag}"


@dataclass
class DeploymentConfig:
    """Configuration for deployment."""
    # Target
    provider: CloudProvider = CloudProvider.GCP
    target: DeploymentTarget = DeploymentTarget.CLOUD_RUN
    environment: str = "production"
    
    # GCP specific
    project_id: Optional[str] = None
    region: str = "us-central1"
    service_name: Optional[str] = None
    
    # Container
    container: ContainerConfig = None
    
    # Networking
    allow_unauthenticated: bool = True
    vpc_connector: Optional[str] = None
    ingress: str = "all"
    
    # Features
    enable_http2: bool = True
    enable_health_check: bool = True
    health_check_path: str = "/health"
    
    # Terraform
    terraform_backend: Optional[str] = None
    terraform_workspace: str = "default"


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""
    status: DeploymentStatus
    
    # URLs and endpoints
    service_url: Optional[str] = None
    health_check_url: Optional[str] = None
    
    # Container details
    image_digest: Optional[str] = None
    image_url: Optional[str] = None
    
    # Timing
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    
    # Terraform outputs
    terraform_outputs: Dict[str, Any] = field(default_factory=dict)
    
    # Logs and errors
    logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    # Generated files
    generated_files: Dict[str, str] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "service_url": self.service_url,
            "image_url": self.image_url,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "terraform_outputs": self.terraform_outputs,
            "errors": self.errors,
        }

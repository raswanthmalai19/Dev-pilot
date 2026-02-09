"""Core module initialization."""

from .gemini_client import GeminiClient
from .executor import CommandExecutor
from .file_manager import FileManager
from .logger import get_logger, setup_logging
from .error_recovery import (
    ErrorAnalyzer,
    FixGenerator,
    RecoveryLoop,
    SelfHealingExecutor,
    ErrorCategory,
    FixAction,
)
from .docker_client import (
    DockerClient,
    DockerBuildResult,
    DockerPushResult,
    build_and_push,
)
from .terraform_client import (
    TerraformClient,
    TerraformPlan,
    TerraformApplyResult,
    deploy_infrastructure,
)
from .health_checker import (
    HealthChecker,
    HealthCheckResult,
    DeploymentVerifier,
    verify_deployment,
)
from .security import (
    InputValidator,
    SecretsMasker,
    SecurityError,
    validate_path,
    validate_command,
    mask_secrets,
)
from .secrets_manager import (
    SecretsManager,
    get_secrets_manager,
    get_secret,
    set_secret,
)

# Dev Pilot GCP Native Clients
from .cloud_build_client import (
    CloudBuildClient,
    CloudBuildResult,
    BuildStatus as CloudBuildStatus,
    build_docker_image,
)
from .artifact_registry_client import (
    ArtifactRegistryClient,
    ArtifactRegistryResult,
    DockerImage,
    RepositoryInfo,
)
from .cloud_run_client import (
    CloudRunClient,
    CloudRunResult,
    ServiceConfig,
    RevisionInfo,
    ServiceStatus,
    deploy_to_cloud_run,
)
from .cloud_logging_client import (
    CloudLoggingClient,
    PipelineLogger,
    LogSeverity,
    LogEntry,
    DeploymentLogEntry,
)
from .deployment_status import (
    DeploymentStatusManager,
    DeploymentPhase,
    StatusUpdate,
    create_console_status_manager,
)


__all__ = [
    # Original
    "GeminiClient",
    "CommandExecutor", 
    "FileManager",
    "get_logger",
    "setup_logging",
    # Error recovery
    "ErrorAnalyzer",
    "FixGenerator",
    "RecoveryLoop",
    "SelfHealingExecutor",
    "ErrorCategory",
    "FixAction",
    # Docker
    "DockerClient",
    "DockerBuildResult",
    "DockerPushResult",
    "build_and_push",
    # Terraform
    "TerraformClient",
    "TerraformPlan",
    "TerraformApplyResult",
    "deploy_infrastructure",
    # Health check
    "HealthChecker",
    "HealthCheckResult",
    "DeploymentVerifier",
    "verify_deployment",
    # Security
    "InputValidator",
    "SecretsMasker",
    "SecurityError",
    "validate_path",
    "validate_command",
    "mask_secrets",
    # Secrets management
    "SecretsManager",
    "get_secrets_manager",
    "get_secret",
    "set_secret",
    # Dev Pilot - Cloud Build
    "CloudBuildClient",
    "CloudBuildResult",
    "CloudBuildStatus",
    "build_docker_image",
    # Dev Pilot - Artifact Registry
    "ArtifactRegistryClient",
    "ArtifactRegistryResult",
    "DockerImage",
    "RepositoryInfo",
    # Dev Pilot - Cloud Run
    "CloudRunClient",
    "CloudRunResult",
    "ServiceConfig",
    "RevisionInfo",
    "ServiceStatus",
    "deploy_to_cloud_run",
    # Dev Pilot - Cloud Logging
    "CloudLoggingClient",
    "PipelineLogger",
    "LogSeverity",
    "LogEntry",
    "DeploymentLogEntry",
    # Dev Pilot - Deployment Status
    "DeploymentStatusManager",
    "DeploymentPhase",
    "StatusUpdate",
    "create_console_status_manager",
]



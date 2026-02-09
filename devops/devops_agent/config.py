"""
Configuration management for DevOps Automation Agent.
Handles all environment variables and settings.
"""

import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class GeminiConfig:
    """Configuration for Gemini API."""
    api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    model_name: str = "models/gemini-2.0-flash"
    temperature: float = 0.7
    max_output_tokens: int = 8192


@dataclass
class GCPConfig:
    """Configuration for Google Cloud Platform."""
    project_id: str = field(default_factory=lambda: os.getenv("GCP_PROJECT_ID", ""))
    region: str = field(default_factory=lambda: os.getenv("GCP_REGION", "us-central1"))
    artifact_registry: str = field(default_factory=lambda: os.getenv("GCP_ARTIFACT_REGISTRY", ""))
    service_account_key: Optional[str] = field(default_factory=lambda: os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))


@dataclass
class DockerConfig:
    """Configuration for Docker operations."""
    registry_url: str = field(default_factory=lambda: os.getenv("DOCKER_REGISTRY", ""))
    username: str = field(default_factory=lambda: os.getenv("DOCKER_USERNAME", ""))
    password: str = field(default_factory=lambda: os.getenv("DOCKER_PASSWORD", ""))
    default_platform: str = "linux/amd64"


@dataclass
class GitHubConfig:
    """Configuration for GitHub integration."""
    token: str = field(default_factory=lambda: os.getenv("GITHUB_TOKEN", ""))
    default_branch: str = "main"


@dataclass
class DevPilotConfig:
    """Configuration for Dev Pilot autonomous deployment."""
    approved_branches: list = field(default_factory=lambda: os.getenv("DEVPILOT_APPROVED_BRANCHES", "main,devpilot-tested,production").split(","))
    auto_rollback: bool = field(default_factory=lambda: os.getenv("DEVPILOT_AUTO_ROLLBACK", "true").lower() == "true")
    strict_mode: bool = field(default_factory=lambda: os.getenv("DEVPILOT_STRICT_MODE", "true").lower() == "true")
    max_retries: int = field(default_factory=lambda: int(os.getenv("DEVPILOT_MAX_RETRIES", "2")))
    webhook_url: str = field(default_factory=lambda: os.getenv("WEBHOOK_URL", ""))


@dataclass
class Config:
    """Main configuration container."""
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    gcp: GCPConfig = field(default_factory=GCPConfig)
    docker: DockerConfig = field(default_factory=DockerConfig)
    github: GitHubConfig = field(default_factory=GitHubConfig)
    devpilot: DevPilotConfig = field(default_factory=DevPilotConfig)
    
    # Paths
    workspace_dir: Path = field(default_factory=lambda: Path(os.getenv("WORKSPACE_DIR", "/tmp/devops_agent")))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("OUTPUT_DIR", "/tmp/devops_output")))
    
    # Agent settings
    max_retries: int = 3
    timeout_seconds: int = 300
    verbose: bool = field(default_factory=lambda: os.getenv("VERBOSE", "false").lower() == "true")
    
    def __post_init__(self):
        """Ensure directories exist."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        if not self.gemini.api_key:
            issues.append("GEMINI_API_KEY is not set")
        
        return issues
    
    @classmethod
    def from_env(cls) -> "Config":
        """Create configuration from environment variables."""
        return cls()


# Global config instance
config = Config.from_env()


def get_config() -> Config:
    """Get the global configuration instance."""
    return config

"""
Cloud Build Agent - Orchestrates Docker builds using GCP Cloud Build.

Responsible for:
- Submitting builds to Cloud Build
- Streaming build logs
- Handling build failures with retry and auto-fix
- Version tagging (timestamp/commit hash)
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent
from ..models.project import ProjectInfo
from ..core.cloud_build_client import CloudBuildClient, CloudBuildResult
from ..core.artifact_registry_client import ArtifactRegistryClient
from ..core.gemini_client import GeminiClient
from ..core.logger import get_logger


@dataclass
class BuildAttempt:
    """Record of a build attempt."""
    attempt_number: int
    started_at: datetime
    finished_at: Optional[datetime] = None
    success: bool = False
    build_id: Optional[str] = None
    error: Optional[str] = None
    fix_applied: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "attempt_number": self.attempt_number,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "success": self.success,
            "build_id": self.build_id,
            "error": self.error,
            "fix_applied": self.fix_applied,
        }


@dataclass
class CloudBuildAgentResult:
    """Result of the Cloud Build Agent."""
    success: bool
    image_url: Optional[str] = None
    image_tag: Optional[str] = None
    image_digest: Optional[str] = None
    build_id: Optional[str] = None
    logs_url: Optional[str] = None
    attempts: List[BuildAttempt] = field(default_factory=list)
    total_duration_seconds: float = 0
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "image_url": self.image_url,
            "image_tag": self.image_tag,
            "image_digest": self.image_digest,
            "build_id": self.build_id,
            "logs_url": self.logs_url,
            "attempts": [a.to_dict() for a in self.attempts],
            "total_duration_seconds": self.total_duration_seconds,
            "errors": self.errors,
        }


class CloudBuildAgent(BaseAgent):
    """
    Cloud Build Agent for automated Docker image building.
    
    Features:
    - Submits builds to GCP Cloud Build
    - Ensures Artifact Registry repository exists
    - Handles retries with auto-fix on failure
    - Version tags using timestamp or commit hash
    
    Usage:
        agent = CloudBuildAgent(project_id="my-project")
        result = await agent.run(
            project_info=project_info,
            image_name="my-app",
            image_tag="v1.0.0",
        )
        
        if result.success:
            print(f"Image built: {result.image_url}")
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
        Initialize the Cloud Build Agent.
        
        Args:
            working_dir: Working directory
            gemini_client: Gemini client for auto-fix
            project_id: GCP project ID
            region: GCP region
        """
        super().__init__(working_dir, gemini_client)
        self.cloud_build = CloudBuildClient(project_id=project_id, region=region)
        self.artifact_registry = ArtifactRegistryClient(project_id=project_id, region=region)
        self.logger = get_logger("CloudBuildAgent")
        
    def _get_system_instruction(self) -> str:
        """Get system instruction for the agent."""
        return """You are an expert at analyzing Docker build failures and suggesting fixes.

When presented with a build error, analyze the root cause and suggest specific fixes:
1. Missing dependencies
2. Incorrect base images
3. Build command errors
4. Permission issues
5. Network/timeout issues

Provide actionable fixes that can be automatically applied."""
    
    async def run(
        self,
        project_info: ProjectInfo,
        image_name: str = None,
        image_tag: str = None,
        commit_hash: str = None,
        dockerfile_path: str = "Dockerfile",
        build_args: Dict[str, str] = None,
        on_log: callable = None,
    ) -> CloudBuildAgentResult:
        """
        Build a Docker image using Cloud Build.
        
        Args:
            project_info: Analyzed project info
            image_name: Name for the image (default: project name)
            image_tag: Tag for the image (default: timestamp)
            commit_hash: Optional commit hash for tagging
            dockerfile_path: Path to Dockerfile relative to source
            build_args: Docker build arguments
            on_log: Callback for streaming logs
            
        Returns:
            CloudBuildAgentResult with build status
        """
        result = CloudBuildAgentResult(success=False)
        started_at = datetime.now()
        
        # Set defaults
        image_name = image_name or project_info.name.lower().replace(" ", "-")
        image_tag = image_tag or self._generate_version_tag(commit_hash)
        result.image_tag = image_tag
        
        self.logger.info("=" * 60)
        self.logger.info("CLOUD BUILD AGENT")
        self.logger.info("=" * 60)
        self.logger.info(f"Project: {project_info.name}")
        self.logger.info(f"Image: {image_name}:{image_tag}")
        
        # 1. Ensure Artifact Registry repository exists
        self.logger.info("Ensuring Artifact Registry repository...")
        registry_result = await self.artifact_registry.ensure_repository(
            repository_id=image_name,
            description=f"Docker repository for {project_info.name}",
        )
        
        if not registry_result.success:
            result.errors.append(f"Failed to create repository: {registry_result.errors}")
            self.logger.error(f"Repository creation failed: {registry_result.errors}")
            return result
            
        self.logger.info(f"Repository ready: {registry_result.message}")
        
        # 2. Submit build with retry logic
        attempt_number = 0
        last_error = None
        
        while attempt_number <= self.MAX_RETRIES:
            attempt_number += 1
            attempt = BuildAttempt(
                attempt_number=attempt_number,
                started_at=datetime.now(),
            )
            
            self.logger.info(f"Build attempt {attempt_number}/{self.MAX_RETRIES + 1}")
            
            try:
                build_result = await self.cloud_build.submit_build(
                    source_path=project_info.path,
                    image_name=image_name,
                    image_tag=image_tag,
                    dockerfile_path=dockerfile_path,
                    build_args=build_args,
                    on_log=on_log,
                )
                
                attempt.finished_at = datetime.now()
                attempt.build_id = build_result.build_id
                
                if build_result.success:
                    attempt.success = True
                    result.success = True
                    result.image_url = build_result.image_url
                    result.image_digest = build_result.image_digest
                    result.build_id = build_result.build_id
                    result.logs_url = build_result.logs_url
                    result.attempts.append(attempt)
                    
                    self.logger.info(f"✅ Build succeeded!")
                    self.logger.info(f"Image: {result.image_url}")
                    break
                else:
                    last_error = build_result.errors[0] if build_result.errors else "Unknown error"
                    attempt.error = last_error
                    result.attempts.append(attempt)
                    
                    self.logger.error(f"❌ Build failed: {last_error}")
                    
                    # Try auto-fix if we have retries left
                    if attempt_number <= self.MAX_RETRIES and self.gemini:
                        fix = await self._try_auto_fix(
                            project_info,
                            last_error,
                            build_result.logs,
                        )
                        if fix:
                            attempt.fix_applied = fix
                            self.logger.info(f"Applied fix: {fix}")
                            
            except Exception as e:
                attempt.finished_at = datetime.now()
                attempt.error = str(e)
                result.attempts.append(attempt)
                last_error = str(e)
                self.logger.error(f"Build exception: {e}")
                
        # Final result
        result.total_duration_seconds = (datetime.now() - started_at).total_seconds()
        
        if not result.success:
            result.errors.append(f"Build failed after {attempt_number} attempts: {last_error}")
            self.logger.error(f"❌ BUILD FAILED after {attempt_number} attempts")
        else:
            self.logger.info(f"✅ BUILD COMPLETED in {result.total_duration_seconds:.1f}s")
            
        self.logger.info("=" * 60)
        
        return result
    
    def _generate_version_tag(self, commit_hash: str = None) -> str:
        """Generate a version tag."""
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        
        if commit_hash:
            short_hash = commit_hash[:8]
            return f"{timestamp}-{short_hash}"
        return timestamp
    
    async def _try_auto_fix(
        self,
        project_info: ProjectInfo,
        error: str,
        logs: List[str] = None,
    ) -> Optional[str]:
        """Try to auto-fix a build error using Gemini."""
        if not self.gemini:
            return None
            
        self.logger.info("Attempting auto-fix with Gemini...")
        
        # Read Dockerfile
        dockerfile_path = project_info.path / "Dockerfile"
        dockerfile_content = ""
        if dockerfile_path.exists():
            dockerfile_content = dockerfile_path.read_text()
            
        # Build prompt
        log_context = "\n".join(logs[-50:]) if logs else "No logs available"
        
        prompt = f"""A Docker build failed with this error:

ERROR: {error}

BUILD LOGS (last 50 lines):
{log_context}

DOCKERFILE:
{dockerfile_content}

PROJECT TYPE: {project_info.project_type.value}
FRAMEWORK: {project_info.framework.value}

Analyze the error and provide a SPECIFIC fix. If it requires modifying the Dockerfile,
provide the complete updated Dockerfile content.

Respond in JSON format:
{{"fix_type": "dockerfile|dependency|config", "description": "what to fix", "content": "new content if applicable"}}

Only respond with valid JSON, no explanation."""

        try:
            response = await self.gemini.generate(prompt, enable_tools=False)
            
            import json
            response_text = response.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()
                
            fix = json.loads(response_text)
            
            # Apply the fix
            if fix.get("fix_type") == "dockerfile" and fix.get("content"):
                dockerfile_path.write_text(fix["content"])
                return f"Updated Dockerfile: {fix.get('description', 'auto-fix applied')}"
                
            return fix.get("description")
            
        except Exception as e:
            self.logger.warning(f"Auto-fix failed: {e}")
            return None
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check prerequisites for the agent."""
        return {
            "cloud_build": self.cloud_build.check_prerequisites(),
            "artifact_registry": self.artifact_registry.check_prerequisites(),
            "gemini_available": self.gemini is not None,
        }


# Convenience function
async def build_with_cloud_build(
    project_path: Path,
    image_name: str,
    image_tag: str = None,
    project_id: str = None,
    region: str = None,
) -> CloudBuildAgentResult:
    """
    Build a Docker image using Cloud Build.
    
    Args:
        project_path: Path to project
        image_name: Name for the image
        image_tag: Tag for the image
        project_id: GCP project ID
        region: GCP region
        
    Returns:
        CloudBuildAgentResult with build status
    """
    from .project_analyzer import ProjectAnalyzer
    
    # Analyze project
    analyzer = ProjectAnalyzer()
    project_info = await analyzer.run(project_path)
    
    # Build
    agent = CloudBuildAgent(project_id=project_id, region=region)
    return await agent.run(project_info, image_name, image_tag)

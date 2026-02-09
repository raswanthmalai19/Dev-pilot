"""
Docker Client - Real Docker SDK integration for building and pushing images.

Provides:
- Multi-stage build support
- Streaming build logs
- Registry authentication
- Image scanning
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from ..core.logger import get_logger


@dataclass
class BuildProgress:
    """Progress of a Docker build."""
    step: int
    total_steps: int
    message: str
    stream: str = ""


@dataclass
class DockerBuildResult:
    """Result of a Docker build operation."""
    success: bool
    image_id: Optional[str] = None
    image_tag: Optional[str] = None
    build_logs: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "image_id": self.image_id,
            "image_tag": self.image_tag,
            "errors": self.errors,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class DockerPushResult:
    """Result of a Docker push operation."""
    success: bool
    digest: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0


class DockerClient:
    """
    Docker SDK wrapper for building and pushing images.
    
    Uses the Docker SDK (docker-py) for proper API integration,
    with fallback to CLI for edge cases.
    """
    
    def __init__(self):
        self.logger = get_logger("DockerClient")
        self._client = None
        self._use_cli = False
    
    async def initialize(self) -> bool:
        """Initialize Docker client."""
        try:
            import docker
            self._client = docker.from_env()
            # Test connection
            self._client.ping()
            self.logger.info("Docker SDK initialized successfully")
            return True
        except ImportError:
            self.logger.warning("Docker SDK not installed, falling back to CLI")
            self._use_cli = True
            return await self._check_docker_cli()
        except Exception as e:
            self.logger.warning(f"Docker SDK connection failed: {e}, falling back to CLI")
            self._use_cli = True
            return await self._check_docker_cli()
    
    async def _check_docker_cli(self) -> bool:
        """Check if Docker CLI is available."""
        from ..core.executor import CommandExecutor
        executor = CommandExecutor()
        result = await executor.run("docker version", timeout=10)
        return result.success
    
    async def build(
        self,
        path: Path,
        tag: str,
        dockerfile: str = "Dockerfile",
        build_args: Dict[str, str] = None,
        target: Optional[str] = None,
        no_cache: bool = False,
        pull: bool = True,
        platform: Optional[str] = None,
        on_progress: Callable[[BuildProgress], None] = None,
    ) -> DockerBuildResult:
        """
        Build a Docker image.
        
        Args:
            path: Path to build context
            tag: Image tag (e.g., "myapp:latest")
            dockerfile: Dockerfile name
            build_args: Build arguments
            target: Multi-stage build target
            no_cache: Disable layer caching
            pull: Pull base image before build
            platform: Target platform (e.g., "linux/amd64")
            on_progress: Callback for build progress
            
        Returns:
            DockerBuildResult with image details
        """
        result = DockerBuildResult(success=False)
        self.logger.info(f"Building image: {tag}")
        
        try:
            if self._use_cli:
                return await self._build_cli(
                    path, tag, dockerfile, build_args, 
                    target, no_cache, pull, platform, on_progress
                )
            
            return await self._build_sdk(
                path, tag, dockerfile, build_args,
                target, no_cache, pull, platform, on_progress
            )
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Build failed: {e}")
        
        result.finished_at = datetime.now()
        result.duration_seconds = (
            result.finished_at - result.started_at
        ).total_seconds()
        return result
    
    async def _build_sdk(
        self,
        path: Path,
        tag: str,
        dockerfile: str,
        build_args: Dict[str, str],
        target: Optional[str],
        no_cache: bool,
        pull: bool,
        platform: Optional[str],
        on_progress: Callable,
    ) -> DockerBuildResult:
        """Build using Docker SDK."""
        result = DockerBuildResult(success=False)
        
        # Run in thread pool since docker-py is synchronous
        loop = asyncio.get_event_loop()
        
        def do_build():
            build_kwargs = {
                "path": str(path),
                "tag": tag,
                "dockerfile": dockerfile,
                "buildargs": build_args or {},
                "nocache": no_cache,
                "pull": pull,
                "rm": True,  # Remove intermediate containers
                "decode": True,  # Decode JSON logs
            }
            
            if target:
                build_kwargs["target"] = target
            if platform:
                build_kwargs["platform"] = platform
            
            logs = []
            image = None
            
            for chunk in self._client.api.build(**build_kwargs):
                if isinstance(chunk, dict):
                    if "stream" in chunk:
                        log = chunk["stream"].strip()
                        if log:
                            logs.append(log)
                            self.logger.debug(log)
                            if on_progress:
                                # Parse step info
                                progress = BuildProgress(
                                    step=len(logs),
                                    total_steps=0,
                                    message=log,
                                    stream=chunk["stream"],
                                )
                                on_progress(progress)
                    
                    if "error" in chunk:
                        raise Exception(chunk["error"])
                    
                    if "aux" in chunk and "ID" in chunk["aux"]:
                        image = chunk["aux"]["ID"]
            
            return image, logs
        
        try:
            image_id, logs = await loop.run_in_executor(None, do_build)
            
            result.success = True
            result.image_id = image_id
            result.image_tag = tag
            result.build_logs = logs
            self.logger.info(f"Build succeeded: {tag}")
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Build failed: {e}")
        
        result.finished_at = datetime.now()
        result.duration_seconds = (
            result.finished_at - result.started_at
        ).total_seconds()
        return result
    
    async def _build_cli(
        self,
        path: Path,
        tag: str,
        dockerfile: str,
        build_args: Dict[str, str],
        target: Optional[str],
        no_cache: bool,
        pull: bool,
        platform: Optional[str],
        on_progress: Callable,
    ) -> DockerBuildResult:
        """Build using Docker CLI."""
        from ..core.executor import CommandExecutor
        
        result = DockerBuildResult(success=False)
        executor = CommandExecutor(working_dir=path)
        
        # Build command
        cmd_parts = ["docker", "build"]
        
        cmd_parts.extend(["-t", tag])
        cmd_parts.extend(["-f", dockerfile])
        
        if build_args:
            for key, value in build_args.items():
                cmd_parts.extend(["--build-arg", f"{key}={value}"])
        
        if target:
            cmd_parts.extend(["--target", target])
        
        if no_cache:
            cmd_parts.append("--no-cache")
        
        if pull:
            cmd_parts.append("--pull")
        
        if platform:
            cmd_parts.extend(["--platform", platform])
        
        cmd_parts.append(".")
        
        cmd = " ".join(cmd_parts)
        self.logger.info(f"Running: {cmd}")
        
        # Run with streaming
        logs = []
        
        def capture_output(line: str):
            logs.append(line)
            if on_progress:
                on_progress(BuildProgress(
                    step=len(logs),
                    total_steps=0,
                    message=line.strip(),
                    stream=line,
                ))
        
        exec_result = await executor.run(
            cmd,
            timeout=900,  # 15 minute timeout
            stream_output=True,
            on_output=capture_output,
        )
        
        result.success = exec_result.success
        result.image_tag = tag
        result.build_logs = logs
        
        if not exec_result.success:
            result.errors.append(exec_result.stderr or "Build failed")
        
        result.finished_at = datetime.now()
        result.duration_seconds = (
            result.finished_at - result.started_at
        ).total_seconds()
        
        return result
    
    async def push(
        self,
        tag: str,
        registry: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ) -> DockerPushResult:
        """
        Push an image to a registry.
        
        Args:
            tag: Image tag to push
            registry: Registry URL (optional, uses Docker Hub if not specified)
            username: Registry username
            password: Registry password
            
        Returns:
            DockerPushResult with push details
        """
        result = DockerPushResult(success=False)
        self.logger.info(f"Pushing image: {tag}")
        
        start_time = datetime.now()
        
        try:
            if self._use_cli:
                return await self._push_cli(tag, registry, username, password)
            
            # Login if credentials provided
            if username and password:
                auth_config = {"username": username, "password": password}
                if registry:
                    self._client.login(
                        username=username,
                        password=password,
                        registry=registry,
                    )
            else:
                auth_config = None
            
            # Push
            loop = asyncio.get_event_loop()
            
            def do_push():
                for line in self._client.images.push(tag, stream=True, decode=True):
                    if "error" in line:
                        raise Exception(line["error"])
                    if "digest" in line:
                        return line.get("digest")
                return None
            
            digest = await loop.run_in_executor(None, do_push)
            
            result.success = True
            result.digest = digest
            self.logger.info(f"Push succeeded: {tag}")
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Push failed: {e}")
        
        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result
    
    async def _push_cli(
        self,
        tag: str,
        registry: Optional[str],
        username: Optional[str],
        password: Optional[str],
    ) -> DockerPushResult:
        """Push using Docker CLI."""
        from ..core.executor import CommandExecutor
        
        result = DockerPushResult(success=False)
        executor = CommandExecutor()
        start_time = datetime.now()
        
        # Login if credentials provided
        if username and password:
            login_cmd = f"docker login"
            if registry:
                login_cmd += f" {registry}"
            login_cmd += f" -u {username} -p {password}"
            
            login_result = await executor.run(login_cmd, timeout=30)
            if not login_result.success:
                result.errors.append("Docker login failed")
                return result
        
        # Push
        push_result = await executor.run(f"docker push {tag}", timeout=600)
        
        result.success = push_result.success
        if not push_result.success:
            result.errors.append(push_result.stderr or "Push failed")
        
        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        return result
    
    async def tag(self, source: str, target: str) -> bool:
        """Tag an image."""
        try:
            if self._use_cli:
                from ..core.executor import CommandExecutor
                executor = CommandExecutor()
                result = await executor.run(f"docker tag {source} {target}", timeout=30)
                return result.success
            
            image = self._client.images.get(source)
            image.tag(target)
            return True
        except Exception as e:
            self.logger.error(f"Tag failed: {e}")
            return False
    
    async def scan(self, tag: str) -> Dict[str, Any]:
        """
        Scan an image for vulnerabilities.
        
        Uses Trivy if available, falls back to Docker Scout.
        """
        from ..core.executor import CommandExecutor
        executor = CommandExecutor()
        
        # Try Trivy first
        trivy_result = await executor.run(
            f"trivy image --format json {tag}",
            timeout=300,
        )
        
        if trivy_result.success:
            try:
                return json.loads(trivy_result.stdout)
            except json.JSONDecodeError:
                pass
        
        # Fall back to Docker Scout
        scout_result = await executor.run(
            f"docker scout cves {tag} --format json",
            timeout=300,
        )
        
        if scout_result.success:
            try:
                return json.loads(scout_result.stdout)
            except json.JSONDecodeError:
                pass
        
        return {"error": "No scanner available", "vulnerabilities": []}
    
    async def cleanup(self, image_tag: str = None, prune: bool = False):
        """Clean up Docker resources."""
        try:
            if prune:
                if self._use_cli:
                    from ..core.executor import CommandExecutor
                    executor = CommandExecutor()
                    await executor.run("docker system prune -f", timeout=60)
                else:
                    self._client.containers.prune()
                    self._client.images.prune()
            
            if image_tag and not self._use_cli:
                try:
                    self._client.images.remove(image_tag, force=True)
                except Exception:
                    pass
                    
        except Exception as e:
            self.logger.warning(f"Cleanup error: {e}")


# Convenience function
async def build_and_push(
    path: Path,
    tag: str,
    push: bool = False,
    registry: str = None,
    **kwargs
) -> DockerBuildResult:
    """
    Build and optionally push a Docker image.
    
    Args:
        path: Build context path
        tag: Image tag
        push: Whether to push after build
        registry: Registry URL for push
        **kwargs: Additional build arguments
        
    Returns:
        DockerBuildResult
    """
    client = DockerClient()
    await client.initialize()
    
    result = await client.build(path, tag, **kwargs)
    
    if result.success and push:
        push_result = await client.push(tag, registry=registry)
        if not push_result.success:
            result.errors.extend(push_result.errors)
    
    return result

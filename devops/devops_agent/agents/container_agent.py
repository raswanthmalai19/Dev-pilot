"""
Container Agent - Handles Docker containerization.
Generates Dockerfiles and builds container images.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable
from datetime import datetime

from rich.progress import Progress, SpinnerColumn, TextColumn

from .base_agent import BaseAgent
from ..models.project import ProjectInfo, ProjectType, Framework
from ..models.deployment import ContainerConfig, DeploymentResult, DeploymentStatus
from ..core.docker_client import DockerClient, DockerBuildResult, BuildProgress


# Dockerfile templates for each project type
DOCKERFILE_TEMPLATES = {
    ProjectType.PYTHON: '''# Build stage
FROM python:{{ python_version }}-slim as builder

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:{{ python_version }}-slim

WORKDIR /app

# Create non-root user
RUN useradd --create-home --shell /bin/bash appuser

# Copy dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application
COPY --chown=appuser:appuser . .

USER appuser

EXPOSE {{ port }}

{% if health_endpoint %}
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:{{ port }}{{ health_endpoint }} || exit 1
{% endif %}

CMD [{{ start_command }}]
''',

    ProjectType.NODEJS: '''# Build stage
FROM node:{{ node_version }}-alpine as builder

WORKDIR /app

# Copy package files
COPY package*.json ./
{% if package_manager == "yarn" %}
COPY yarn.lock ./
{% elif package_manager == "pnpm" %}
COPY pnpm-lock.yaml ./
{% endif %}

# Install dependencies
{% if package_manager == "npm" %}
RUN npm ci --only=production
{% elif package_manager == "yarn" %}
RUN yarn install --frozen-lockfile --production
{% elif package_manager == "pnpm" %}
RUN npm install -g pnpm && pnpm install --frozen-lockfile --prod
{% endif %}

# Production stage
FROM node:{{ node_version }}-alpine

WORKDIR /app

# Create non-root user
RUN addgroup -g 1001 -S appgroup && adduser -u 1001 -S appuser -G appgroup

# Copy dependencies and app
COPY --from=builder --chown=appuser:appgroup /app/node_modules ./node_modules
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE {{ port }}

{% if health_endpoint %}
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD wget -q --spider http://localhost:{{ port }}{{ health_endpoint }} || exit 1
{% endif %}

CMD ["node", "{{ entry_point }}"]
''',

    ProjectType.GO: '''# Build stage
FROM golang:{{ go_version }}-alpine as builder

WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./
RUN go mod download

# Copy source and build
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main .

# Production stage
FROM alpine:latest

WORKDIR /app

# Add ca-certificates and create non-root user
RUN apk --no-cache add ca-certificates && \\
    addgroup -g 1001 -S appgroup && \\
    adduser -u 1001 -S appuser -G appgroup

COPY --from=builder --chown=appuser:appgroup /app/main .

USER appuser

EXPOSE {{ port }}

{% if health_endpoint %}
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD wget -q --spider http://localhost:{{ port }}{{ health_endpoint }} || exit 1
{% endif %}

CMD ["./main"]
''',

    ProjectType.RUST: '''# Build stage
FROM rust:{{ rust_version }} as builder

WORKDIR /app

# Copy manifests
COPY Cargo.toml Cargo.lock ./

# Create dummy source to cache dependencies
RUN mkdir src && echo "fn main() {}" > src/main.rs
RUN cargo build --release
RUN rm -rf src

# Copy real source and build
COPY src ./src
RUN cargo build --release

# Production stage
FROM debian:bookworm-slim

WORKDIR /app

# Install runtime dependencies and create user
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && \\
    rm -rf /var/lib/apt/lists/* && \\
    useradd --create-home --shell /bin/bash appuser

COPY --from=builder --chown=appuser:appuser /app/target/release/{{ app_name }} .

USER appuser

EXPOSE {{ port }}

CMD ["./{{ app_name }}"]
''',
}

# Default .dockerignore content
DOCKERIGNORE_TEMPLATE = '''# Git
.git
.gitignore

# IDE
.idea
.vscode
*.swp
*.swo

# Environment
.env
.env.*
!.env.example

# Dependencies
node_modules
__pycache__
*.pyc
.venv
venv
target/debug

# Build artifacts
dist
build
*.egg-info

# Tests
tests
test
*_test.go
*_test.py

# Documentation
docs
*.md
!README.md

# Docker
Dockerfile*
docker-compose*
.docker

# Misc
.DS_Store
*.log
'''


class ContainerAgent(BaseAgent):
    """
    Handles Docker containerization:
    - Generate optimized Dockerfiles
    - Create .dockerignore
    - Build container images
    - Push to registry
    """
    
    def __init__(self, working_dir: Path = None, gemini_client=None):
        super().__init__("ContainerAgent", working_dir, gemini_client)
        self.docker = DockerClient()
    
    def _get_system_instruction(self) -> str:
        return """You are a Docker expert. You create optimized, secure Dockerfiles
with multi-stage builds, proper caching, and security best practices.
Always use specific version tags, run as non-root, and minimize image size."""
    
    async def run(
        self, 
        project_info: ProjectInfo,
        config: ContainerConfig = None,
        push_to_registry: bool = False,
        build_and_push: bool = True,  # NEW: Actually build the image
        on_progress: Callable[[BuildProgress], None] = None,
    ) -> DeploymentResult:
        """
        Containerize the project.
        
        Args:
            project_info: Analyzed project information
            config: Container configuration
            push_to_registry: Whether to push to registry
            build_and_push: Whether to actually build (vs just generate files)
            on_progress: Callback for build progress (streaming logs)
            
        Returns:
            DeploymentResult with image details
        """
        config = config or self._create_default_config(project_info)
        result = DeploymentResult(status=DeploymentStatus.DEPLOYING)
        
        try:
            # Step 1: Generate Dockerfile
            self.log_step("Generating Dockerfile", 1)
            dockerfile = await self._generate_dockerfile(project_info)
            dockerfile_path = project_info.path / "Dockerfile"
            await self.file_manager.write_file(dockerfile_path, dockerfile)
            result.generated_files["Dockerfile"] = dockerfile
            
            # Step 2: Generate .dockerignore
            self.log_step("Generating .dockerignore", 2)
            dockerignore = self._generate_dockerignore(project_info)
            dockerignore_path = project_info.path / ".dockerignore"
            await self.file_manager.write_file(dockerignore_path, dockerignore)
            result.generated_files[".dockerignore"] = dockerignore
            
            # Step 3: Build image (using Docker SDK if available)
            if build_and_push:
                self.log_step(f"Building image: {config.full_image_name}", 3)
                
                # Initialize Docker client
                docker_available = await self.docker.initialize()
                if not docker_available:
                    self.logger.warning("Docker not available, skipping build")
                    result.warnings.append("Docker not available, only files generated")
                else:
                    build_result = await self._build_image_with_sdk(
                        project_info, config, on_progress
                    )
                    
                    if not build_result.success:
                        result.status = DeploymentStatus.FAILED
                        result.errors.extend(build_result.errors)
                        return self._finalize_result(result)
                    
                    result.image_url = config.full_image_name
                    
                    # Step 4: Push to registry (optional)
                    if push_to_registry and config.registry_url:
                        self.log_step("Pushing to registry", 4)
                        push_result = await self.docker.push(
                            tag=config.full_image_name,
                            registry=config.registry_url,
                            username=config.registry_username,
                            password=config.registry_password,
                        )
                        
                        if not push_result.success:
                            result.status = DeploymentStatus.FAILED
                            result.errors.extend(push_result.errors)
                            return self._finalize_result(result)
                        
                        result.registry_path = config.full_image_name
            
            result.status = DeploymentStatus.SUCCESS
            self.log_success(f"Containerization complete: {config.full_image_name}")
            
        except Exception as e:
            result.status = DeploymentStatus.FAILED
            result.errors.append(str(e))
            self.log_error(f"Containerization failed: {e}", e)
        
        return self._finalize_result(result)
    
    async def _build_image_with_sdk(
        self,
        project_info: ProjectInfo,
        config: ContainerConfig,
        on_progress: Callable[[BuildProgress], None] = None,
    ) -> DockerBuildResult:
        """Build image using Docker SDK with streaming logs."""
        return await self.docker.build(
            path=project_info.path,
            tag=config.full_image_name,
            dockerfile="Dockerfile",
            build_args=config.build_args,
            no_cache=False,
            pull=True,
            on_progress=on_progress or (lambda p: self.logger.debug(p.message)),
        )
    
    def _create_default_config(self, project_info: ProjectInfo) -> ContainerConfig:
        """Create default container configuration."""
        image_name = project_info.name.lower().replace(" ", "-").replace("_", "-")
        
        return ContainerConfig(
            image_name=image_name,
            image_tag="latest",
            port=project_info.port,
        )

    
    async def _generate_dockerfile(self, project_info: ProjectInfo) -> str:
        """Generate an optimized Dockerfile."""
        # Try template first
        template = DOCKERFILE_TEMPLATES.get(project_info.project_type)
        
        if template:
            context = self._get_template_context(project_info)
            return self.file_manager.render_template(template, context)
        
        # Fall back to Gemini generation
        return await self._gemini_generate_dockerfile(project_info)
    
    def _get_template_context(self, project_info: ProjectInfo) -> Dict[str, Any]:
        """Build template context from project info."""
        # Default versions
        versions = {
            ProjectType.PYTHON: "3.11",
            ProjectType.NODEJS: "20",
            ProjectType.GO: "1.21",
            ProjectType.RUST: "1.75",
        }
        
        # Parse start command for CMD
        start_cmd = project_info.start_command or ""
        if start_cmd:
            # Convert to JSON array format for CMD
            parts = start_cmd.split()
            start_cmd_json = ", ".join(f'"{p}"' for p in parts)
        else:
            start_cmd_json = '"python", "main.py"'
        
        return {
            "python_version": project_info.language_version or versions.get(ProjectType.PYTHON),
            "node_version": project_info.language_version or versions.get(ProjectType.NODEJS),
            "go_version": project_info.language_version or versions.get(ProjectType.GO),
            "rust_version": versions.get(ProjectType.RUST),
            "port": project_info.port,
            "entry_point": project_info.entry_point or project_info.main_file or "index.js",
            "start_command": start_cmd_json,
            "health_endpoint": project_info.health_endpoint,
            "package_manager": project_info.package_manager or "npm",
            "app_name": project_info.name,
        }
    
    async def _gemini_generate_dockerfile(self, project_info: ProjectInfo) -> str:
        """Use Gemini to generate a Dockerfile for unsupported project types."""
        return await self.gemini.generate_dockerfile(project_info.to_dict())
    
    def _generate_dockerignore(self, project_info: ProjectInfo) -> str:
        """Generate .dockerignore file."""
        ignore = DOCKERIGNORE_TEMPLATE
        
        # Add project-specific ignores
        if project_info.project_type == ProjectType.PYTHON:
            ignore += "\n*.egg\n*.egg-info/\n.pytest_cache/\n"
        elif project_info.project_type == ProjectType.NODEJS:
            ignore += "\ncoverage/\n.next/\n.nuxt/\n"
        elif project_info.project_type == ProjectType.GO:
            ignore += "\n*.exe\n*.test\n"
        
        return ignore
    
    async def _build_image(
        self, 
        project_info: ProjectInfo, 
        config: ContainerConfig
    ) -> bool:
        """Build Docker image."""
        self.executor.working_dir = project_info.path
        
        # Build command
        build_args = " ".join(
            f"--build-arg {k}={v}" 
            for k, v in config.build_args.items()
        )
        
        cmd = f"docker build -t {config.full_image_name} {build_args} ."
        
        result = await self.executor.run(
            cmd,
            timeout=600,  # 10 minute timeout for builds
            stream_output=True,
            on_output=lambda x: self.logger.debug(x.strip()),
        )
        
        if not result.success:
            self.logger.error(f"Build failed: {result.stderr}")
        
        return result.success
    
    async def _push_image(self, config: ContainerConfig) -> bool:
        """Push image to registry."""
        cmd = f"docker push {config.full_image_name}"
        
        result = await self.executor.run(cmd, timeout=300)
        
        if not result.success:
            self.logger.error(f"Push failed: {result.stderr}")
        
        return result.success
    
    async def check_prerequisites(self) -> Dict[str, bool]:
        """Check if Docker is available."""
        docker_available = await self.executor.check_tool_exists("docker")
        docker_version = await self.executor.get_tool_version("docker")
        
        return {
            "docker": docker_available,
            "docker_version": docker_version,
        }
    
    def _finalize_result(self, result: DeploymentResult) -> DeploymentResult:
        """Finalize the result with timing."""
        result.finished_at = datetime.now()
        result.duration_seconds = (
            result.finished_at - result.started_at
        ).total_seconds()
        return result

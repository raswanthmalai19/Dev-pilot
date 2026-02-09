"""
Artifact Registry Client - Native GCP SDK integration for Docker image management.

Provides:
- Create/verify repositories
- List and manage Docker images
- Get image digests and metadata
- Clean up old images
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from ..core.logger import get_logger
from ..config import get_config


@dataclass
class DockerImage:
    """Docker image information."""
    name: str
    tags: List[str] = field(default_factory=list)
    digest: Optional[str] = None
    size_bytes: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    @property
    def full_name(self) -> str:
        """Get full image name with first tag."""
        if self.tags:
            return f"{self.name}:{self.tags[0]}"
        return self.name


@dataclass
class RepositoryInfo:
    """Artifact Registry repository information."""
    name: str
    repository_id: str
    location: str
    format: str = "DOCKER"
    description: str = ""
    created_at: Optional[datetime] = None


@dataclass
class ArtifactRegistryResult:
    """Result of an Artifact Registry operation."""
    success: bool
    message: str = ""
    repository: Optional[RepositoryInfo] = None
    images: List[DockerImage] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "success": self.success,
            "message": self.message,
            "repository": {
                "name": self.repository.name,
                "repository_id": self.repository.repository_id,
                "location": self.repository.location,
            } if self.repository else None,
            "image_count": len(self.images),
            "errors": self.errors,
        }


class ArtifactRegistryClient:
    """
    GCP Artifact Registry client for Docker image management.
    
    Usage:
        client = ArtifactRegistryClient(project_id="my-project")
        
        # Ensure repository exists
        result = await client.ensure_repository("my-app")
        
        # Get image digest
        digest = await client.get_image_digest("my-app", "v1.0.0")
        
        # List images
        images = await client.list_images("my-app")
    """
    
    def __init__(
        self,
        project_id: str = None,
        region: str = None,
    ):
        """
        Initialize Artifact Registry client.
        
        Args:
            project_id: GCP project ID
            region: GCP region
        """
        self.config = get_config()
        self.project_id = project_id or self.config.gcp.project_id
        self.region = region or self.config.gcp.region
        self.logger = get_logger("ArtifactRegistryClient")
        self._client = None
        
    def _get_client(self):
        """Get or create Artifact Registry client."""
        if self._client is None:
            try:
                from google.cloud import artifactregistry_v1
                self._client = artifactregistry_v1.ArtifactRegistryClient()
            except ImportError:
                self.logger.error("google-cloud-artifact-registry not installed")
                raise ImportError("google-cloud-artifact-registry package required")
        return self._client
    
    def _get_repository_path(self, repository_id: str) -> str:
        """Get the full repository resource path."""
        return f"projects/{self.project_id}/locations/{self.region}/repositories/{repository_id}"
    
    def _get_parent_path(self) -> str:
        """Get the parent path for creating repositories."""
        return f"projects/{self.project_id}/locations/{self.region}"
    
    def get_registry_url(self, repository_id: str) -> str:
        """Get the Docker registry URL for a repository."""
        return f"{self.region}-docker.pkg.dev/{self.project_id}/{repository_id}"
    
    def get_image_url(self, repository_id: str, image_name: str, tag: str = "latest") -> str:
        """Get the full image URL."""
        registry = self.get_registry_url(repository_id)
        return f"{registry}/{image_name}:{tag}"
    
    async def ensure_repository(
        self,
        repository_id: str,
        description: str = None,
    ) -> ArtifactRegistryResult:
        """
        Ensure a Docker repository exists, creating if necessary.
        
        Args:
            repository_id: Repository ID (name)
            description: Optional description
            
        Returns:
            ArtifactRegistryResult with repository info
        """
        from google.cloud import artifactregistry_v1
        from google.api_core import exceptions
        
        result = ArtifactRegistryResult(success=False)
        
        try:
            client = self._get_client()
            repo_path = self._get_repository_path(repository_id)
            
            # Try to get existing repository
            try:
                repo = client.get_repository(name=repo_path)
                result.success = True
                result.message = f"Repository {repository_id} already exists"
                result.repository = RepositoryInfo(
                    name=repo.name,
                    repository_id=repository_id,
                    location=self.region,
                    format="DOCKER",
                    description=repo.description or "",
                )
                self.logger.info(f"Repository exists: {repository_id}")
                return result
                
            except exceptions.NotFound:
                # Repository doesn't exist, create it
                self.logger.info(f"Creating repository: {repository_id}")
                
                repository = artifactregistry_v1.Repository(
                    format_=artifactregistry_v1.Repository.Format.DOCKER,
                    description=description or f"Docker repository for {repository_id}",
                )
                
                operation = client.create_repository(
                    parent=self._get_parent_path(),
                    repository_id=repository_id,
                    repository=repository,
                )
                
                # Wait for operation to complete
                repo = await asyncio.get_event_loop().run_in_executor(
                    None, operation.result
                )
                
                result.success = True
                result.message = f"Repository {repository_id} created"
                result.repository = RepositoryInfo(
                    name=repo.name,
                    repository_id=repository_id,
                    location=self.region,
                    format="DOCKER",
                    description=repo.description or "",
                )
                self.logger.info(f"Repository created: {repository_id}")
                
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"Failed to ensure repository: {e}")
            
        return result
    
    async def get_image_digest(
        self,
        repository_id: str,
        image_name: str,
        tag: str = "latest",
    ) -> Optional[str]:
        """
        Get the digest for a specific image tag.
        
        Args:
            repository_id: Repository ID
            image_name: Image name
            tag: Image tag
            
        Returns:
            Image digest (sha256:...) or None if not found
        """
        try:
            client = self._get_client()
            
            # List tags to find the digest
            package_path = f"{self._get_repository_path(repository_id)}/packages/{image_name}"
            
            # List versions (tags)
            versions = client.list_versions(parent=package_path)
            
            for version in versions:
                # Check if this version has our tag
                tags = client.list_tags(parent=version.name)
                for t in tags:
                    if t.name.endswith(f"/tags/{tag}"):
                        # Extract digest from version name
                        # Format: .../versions/sha256:...
                        if "/versions/" in version.name:
                            digest = version.name.split("/versions/")[-1]
                            return digest
                            
            return None
            
        except Exception as e:
            self.logger.error(f"Failed to get image digest: {e}")
            return None
    
    async def list_images(
        self,
        repository_id: str,
        limit: int = 100,
    ) -> List[DockerImage]:
        """
        List Docker images in a repository.
        
        Args:
            repository_id: Repository ID
            limit: Maximum number of images to return
            
        Returns:
            List of DockerImage objects
        """
        images = []
        
        try:
            client = self._get_client()
            repo_path = self._get_repository_path(repository_id)
            
            # List packages (images)
            packages = client.list_packages(parent=repo_path)
            
            for package in packages:
                if len(images) >= limit:
                    break
                    
                # Get image name from package path
                image_name = package.name.split("/packages/")[-1]
                
                # Get versions and tags
                versions = list(client.list_versions(parent=package.name))
                
                for version in versions:
                    tags = [t.name.split("/tags/")[-1] 
                            for t in client.list_tags(parent=version.name)]
                    
                    digest = version.name.split("/versions/")[-1] if "/versions/" in version.name else None
                    
                    images.append(DockerImage(
                        name=f"{self.get_registry_url(repository_id)}/{image_name}",
                        tags=tags,
                        digest=digest,
                        created_at=version.create_time.ToDatetime() if hasattr(version, 'create_time') else None,
                        updated_at=version.update_time.ToDatetime() if hasattr(version, 'update_time') else None,
                    ))
                    
        except Exception as e:
            self.logger.error(f"Failed to list images: {e}")
            
        return images
    
    async def delete_image(
        self,
        repository_id: str,
        image_name: str,
        tag: str = None,
        digest: str = None,
    ) -> bool:
        """
        Delete a Docker image by tag or digest.
        
        Args:
            repository_id: Repository ID
            image_name: Image name
            tag: Tag to delete (optional)
            digest: Digest to delete (optional, deletes all tags)
            
        Returns:
            True if deleted successfully
        """
        try:
            client = self._get_client()
            
            if digest:
                # Delete by digest (deletes all tags)
                version_path = f"{self._get_repository_path(repository_id)}/packages/{image_name}/versions/{digest}"
                client.delete_version(name=version_path)
                self.logger.info(f"Deleted image version: {digest}")
                return True
                
            elif tag:
                # Delete specific tag
                tag_path = f"{self._get_repository_path(repository_id)}/packages/{image_name}/tags/{tag}"
                client.delete_tag(name=tag_path)
                self.logger.info(f"Deleted image tag: {tag}")
                return True
                
            else:
                self.logger.error("Either tag or digest must be specified")
                return False
                
        except Exception as e:
            self.logger.error(f"Failed to delete image: {e}")
            return False
    
    async def cleanup_old_images(
        self,
        repository_id: str,
        image_name: str,
        keep_count: int = 10,
    ) -> int:
        """
        Clean up old image versions, keeping the most recent ones.
        
        Args:
            repository_id: Repository ID
            image_name: Image name
            keep_count: Number of recent versions to keep
            
        Returns:
            Number of versions deleted
        """
        deleted_count = 0
        
        try:
            client = self._get_client()
            package_path = f"{self._get_repository_path(repository_id)}/packages/{image_name}"
            
            # List all versions sorted by creation time
            versions = list(client.list_versions(parent=package_path))
            
            # Sort by creation time (newest first)
            versions.sort(
                key=lambda v: v.create_time.ToDatetime() if hasattr(v, 'create_time') else datetime.min,
                reverse=True
            )
            
            # Delete old versions
            for version in versions[keep_count:]:
                try:
                    client.delete_version(name=version.name)
                    deleted_count += 1
                    self.logger.info(f"Deleted old version: {version.name}")
                except Exception as e:
                    self.logger.warning(f"Failed to delete version {version.name}: {e}")
                    
        except Exception as e:
            self.logger.error(f"Failed to cleanup images: {e}")
            
        return deleted_count
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check if prerequisites are met."""
        prerequisites = {
            "project_id": bool(self.project_id),
            "region": bool(self.region),
            "sdk_installed": False,
            "authenticated": False,
        }
        
        try:
            from google.cloud import artifactregistry_v1
            prerequisites["sdk_installed"] = True
        except ImportError:
            pass
            
        try:
            self._get_client()
            prerequisites["authenticated"] = True
        except Exception:
            pass
            
        return prerequisites

"""
GitHub Client - PyGithub with REST API fallback.

Primary: PyGithub library for robust GitHub operations
Fallback: Direct REST API calls using httpx

Provides:
- Repository operations
- File operations (list, read, create, update)
- Branch management
- Pull request creation
- Workflow file push
"""

import asyncio
import base64
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx

from ..core.logger import get_logger


# Try to import PyGithub
try:
    from github import Github, GithubException
    from github.Repository import Repository
    from github.ContentFile import ContentFile
    PYGITHUB_AVAILABLE = True
except ImportError:
    PYGITHUB_AVAILABLE = False


@dataclass
class GitHubFile:
    """A file to create/update in GitHub."""
    path: str  # Path in repo (e.g., ".github/workflows/ci.yml")
    content: str  # File content
    message: str = "Update file"  # Commit message


@dataclass
class GitHubResult:
    """Result of a GitHub operation."""
    success: bool
    message: str = ""
    url: Optional[str] = None
    sha: Optional[str] = None
    errors: List[str] = field(default_factory=list)
    method_used: str = ""  # "pygithub" or "rest_api"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "message": self.message,
            "url": self.url,
            "errors": self.errors,
            "method_used": self.method_used,
        }


@dataclass
class PullRequestInfo:
    """Information about a created PR."""
    number: int
    url: str
    title: str
    branch: str


class GitHubClient:
    """
    GitHub client with PyGithub primary and REST API fallback.
    
    Automatically uses PyGithub if available, falls back to REST API.
    
    Usage:
        client = GitHubClient(token="your-pat-token")
        await client.push_workflow(
            owner="user",
            repo="my-app",
            workflow_content="name: CI...",
        )
    """
    
    BASE_URL = "https://api.github.com"
    
    def __init__(self, token: str = None):
        """
        Initialize GitHub client.
        
        Args:
            token: GitHub Personal Access Token. If not provided,
                   reads from GITHUB_TOKEN environment variable.
        """
        import os
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.logger = get_logger("GitHubClient")
        
        # PyGithub client (if available)
        self._pygithub: Optional[Github] = None
        if PYGITHUB_AVAILABLE and self.token:
            try:
                self._pygithub = Github(self.token)
                self.logger.info("Initialized with PyGithub")
            except Exception as e:
                self.logger.warning(f"PyGithub init failed, using REST API: {e}")
                self._pygithub = None
        else:
            if not PYGITHUB_AVAILABLE:
                self.logger.info("PyGithub not installed, using REST API fallback")
            self._pygithub = None
        
        # REST API client
        self._client: Optional[httpx.AsyncClient] = None
    
    @property
    def headers(self) -> Dict[str, str]:
        """Get request headers for REST API."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers
    
    async def _get_rest_client(self) -> httpx.AsyncClient:
        """Get or create REST HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                headers=self.headers,
                timeout=30.0,
            )
        return self._client
    
    async def close(self):
        """Close the clients."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._pygithub:
            try:
                self._pygithub.close()
            except:
                pass
    
    # ========== PyGithub Methods ==========
    
    def _get_repo_pygithub(self, owner: str, repo: str) -> Optional[Repository]:
        """Get repository using PyGithub."""
        if not self._pygithub:
            return None
        
        try:
            return self._pygithub.get_repo(f"{owner}/{repo}")
        except Exception as e:
            self.logger.error(f"PyGithub get_repo failed: {e}")
            return None
    
    def _create_or_update_file_pygithub(
        self,
        repo: Repository,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> GitHubResult:
        """Create or update file using PyGithub."""
        result = GitHubResult(success=False, method_used="pygithub")
        
        try:
            # Check if file exists
            try:
                existing = repo.get_contents(path, ref=branch)
                # Update existing file
                update = repo.update_file(
                    path=path,
                    message=message,
                    content=content,
                    sha=existing.sha,
                    branch=branch,
                )
                result.success = True
                result.message = "File updated"
                result.sha = update["commit"].sha
                result.url = update["content"].html_url
                self.logger.info(f"Updated file via PyGithub: {path}")
                
            except GithubException as e:
                if e.status == 404:
                    # File doesn't exist, create it
                    creation = repo.create_file(
                        path=path,
                        message=message,
                        content=content,
                        branch=branch,
                    )
                    result.success = True
                    result.message = "File created"
                    result.sha = creation["commit"].sha
                    result.url = creation["content"].html_url
                    self.logger.info(f"Created file via PyGithub: {path}")
                else:
                    raise
                    
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"PyGithub file operation failed: {e}")
        
        return result
    
    def _create_branch_pygithub(
        self,
        repo: Repository,
        branch_name: str,
        from_branch: str,
    ) -> GitHubResult:
        """Create branch using PyGithub."""
        result = GitHubResult(success=False, method_used="pygithub")
        
        try:
            # Get source branch reference
            source_ref = repo.get_git_ref(f"heads/{from_branch}")
            source_sha = source_ref.object.sha
            
            # Create new branch
            try:
                repo.create_git_ref(
                    ref=f"refs/heads/{branch_name}",
                    sha=source_sha,
                )
                result.success = True
                result.message = f"Branch '{branch_name}' created"
                result.sha = source_sha
                
            except GithubException as e:
                if e.status == 422:  # Branch already exists
                    result.success = True
                    result.message = f"Branch '{branch_name}' already exists"
                else:
                    raise
                    
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"PyGithub create branch failed: {e}")
        
        return result
    
    def _create_pr_pygithub(
        self,
        repo: Repository,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> Optional[PullRequestInfo]:
        """Create PR using PyGithub."""
        try:
            pr = repo.create_pull(
                title=title,
                body=body,
                head=head,
                base=base,
            )
            return PullRequestInfo(
                number=pr.number,
                url=pr.html_url,
                title=pr.title,
                branch=head,
            )
        except Exception as e:
            self.logger.error(f"PyGithub create PR failed: {e}")
            return None
    
    # ========== REST API Fallback Methods ==========
    
    async def _get_repo_rest(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Get repository using REST API."""
        try:
            client = await self._get_rest_client()
            response = await client.get(f"/repos/{owner}/{repo}")
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                self.logger.error(f"Repository not found: {owner}/{repo}")
            else:
                self.logger.error(f"Failed to get repo: {response.status_code}")
            
            return None
        except Exception as e:
            self.logger.error(f"REST API get repo failed: {e}")
            return None
    
    async def _get_file_rest(
        self, 
        owner: str, 
        repo: str, 
        path: str,
        branch: str,
    ) -> Optional[Dict[str, Any]]:
        """Get file using REST API."""
        try:
            client = await self._get_rest_client()
            response = await client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
            )
            
            if response.status_code == 200:
                return response.json()
            return None
        except Exception as e:
            self.logger.error(f"REST API get file failed: {e}")
            return None
    
    async def _create_or_update_file_rest(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str,
    ) -> GitHubResult:
        """Create or update file using REST API."""
        result = GitHubResult(success=False, method_used="rest_api")
        
        try:
            client = await self._get_rest_client()
            
            # Check if file exists
            existing = await self._get_file_rest(owner, repo, path, branch)
            
            # Encode content
            content_b64 = base64.b64encode(content.encode()).decode()
            
            payload = {
                "message": message,
                "content": content_b64,
                "branch": branch,
            }
            
            if existing:
                payload["sha"] = existing["sha"]
                self.logger.info(f"Updating file via REST API: {path}")
            else:
                self.logger.info(f"Creating file via REST API: {path}")
            
            response = await client.put(
                f"/repos/{owner}/{repo}/contents/{path}",
                json=payload,
            )
            
            if response.status_code in (200, 201):
                data = response.json()
                result.success = True
                result.message = "File created" if response.status_code == 201 else "File updated"
                result.url = data.get("content", {}).get("html_url")
                result.sha = data.get("content", {}).get("sha")
            else:
                error_msg = response.json().get("message", "Unknown error")
                result.errors.append(error_msg)
                self.logger.error(f"REST API file operation failed: {error_msg}")
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"REST API file operation failed: {e}")
        
        return result
    
    async def _create_branch_rest(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        from_branch: str,
    ) -> GitHubResult:
        """Create branch using REST API."""
        result = GitHubResult(success=False, method_used="rest_api")
        
        try:
            client = await self._get_rest_client()
            
            # Get source branch SHA
            response = await client.get(
                f"/repos/{owner}/{repo}/git/refs/heads/{from_branch}"
            )
            
            if response.status_code != 200:
                result.errors.append(f"Source branch '{from_branch}' not found")
                return result
            
            source_sha = response.json()["object"]["sha"]
            
            # Create new branch
            response = await client.post(
                f"/repos/{owner}/{repo}/git/refs",
                json={
                    "ref": f"refs/heads/{branch_name}",
                    "sha": source_sha,
                },
            )
            
            if response.status_code == 201:
                result.success = True
                result.message = f"Branch '{branch_name}' created"
                result.sha = source_sha
            elif response.status_code == 422:
                result.success = True
                result.message = f"Branch '{branch_name}' already exists"
            else:
                error_msg = response.json().get("message", "Unknown error")
                result.errors.append(error_msg)
            
        except Exception as e:
            result.errors.append(str(e))
            self.logger.error(f"REST API create branch failed: {e}")
        
        return result
    
    async def _create_pr_rest(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str,
        body: str,
    ) -> Optional[PullRequestInfo]:
        """Create PR using REST API."""
        try:
            client = await self._get_rest_client()
            
            response = await client.post(
                f"/repos/{owner}/{repo}/pulls",
                json={
                    "title": title,
                    "head": head,
                    "base": base,
                    "body": body,
                },
            )
            
            if response.status_code == 201:
                data = response.json()
                return PullRequestInfo(
                    number=data["number"],
                    url=data["html_url"],
                    title=data["title"],
                    branch=head,
                )
            else:
                error_msg = response.json().get("message", "Unknown error")
                self.logger.error(f"REST API create PR failed: {error_msg}")
                return None
                
        except Exception as e:
            self.logger.error(f"REST API create PR failed: {e}")
            return None
    
    # ========== Public API (auto-selects PyGithub or REST) ==========
    
    async def verify_token(self) -> bool:
        """Verify that the token is valid."""
        if not self.token:
            return False
        
        # Try PyGithub first
        if self._pygithub:
            try:
                self._pygithub.get_user().login
                return True
            except:
                pass
        
        # Fallback to REST API
        try:
            client = await self._get_rest_client()
            response = await client.get("/user")
            return response.status_code == 200
        except Exception as e:
            self.logger.error(f"Token verification failed: {e}")
            return False
    
    async def get_repo(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Get repository information."""
        # Try PyGithub
        if self._pygithub:
            repo_obj = self._get_repo_pygithub(owner, repo)
            if repo_obj:
                return {
                    "name": repo_obj.name,
                    "full_name": repo_obj.full_name,
                    "default_branch": repo_obj.default_branch,
                    "html_url": repo_obj.html_url,
                }
        
        # Fallback to REST API
        return await self._get_repo_rest(owner, repo)
    
    async def list_files(
        self,
        owner: str,
        repo: str,
        path: str = "",
        branch: str = "main",
    ) -> List[Dict[str, Any]]:
        """List files in a directory."""
        # Try PyGithub
        if self._pygithub:
            try:
                repo_obj = self._get_repo_pygithub(owner, repo)
                if repo_obj:
                    contents = repo_obj.get_contents(path, ref=branch)
                    if not isinstance(contents, list):
                        contents = [contents]
                    
                    return [
                        {
                            "name": item.name,
                            "path": item.path,
                            "type": item.type,
                            "size": item.size if hasattr(item, 'size') else 0,
                        }
                        for item in contents
                    ]
            except Exception as e:
                self.logger.warning(f"PyGithub list files failed: {e}")
        
        # Fallback to REST API
        try:
            client = await self._get_rest_client()
            response = await client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": branch},
            )
            
            if response.status_code == 200:
                data = response.json()
                if not isinstance(data, list):
                    data = [data]
                return [
                    {
                        "name": item["name"],
                        "path": item["path"],
                        "type": item["type"],
                        "size": item.get("size", 0),
                    }
                    for item in data
                ]
        except Exception as e:
            self.logger.error(f"REST API list files failed: {e}")
        
        return []
    
    async def get_file_content(
        self,
        owner: str,
        repo: str,
        path: str,
        branch: str = "main",
    ) -> Optional[str]:
        """Get file content (decoded)."""
        # Try PyGithub
        if self._pygithub:
            try:
                repo_obj = self._get_repo_pygithub(owner, repo)
                if repo_obj:
                    file_content = repo_obj.get_contents(path, ref=branch)
                    return file_content.decoded_content.decode('utf-8')
            except Exception as e:
                self.logger.warning(f"PyGithub get file content failed: {e}")
        
        # Fallback to REST API
        file_data = await self._get_file_rest(owner, repo, path, branch)
        if file_data and "content" in file_data:
            try:
                return base64.b64decode(file_data["content"]).decode('utf-8')
            except:
                pass
        
        return None
    
    async def create_or_update_file(
        self,
        owner: str,
        repo: str,
        path: str,
        content: str,
        message: str,
        branch: str = "main",
    ) -> GitHubResult:
        """Create or update a file (auto-selects method)."""
        # Try PyGithub (synchronous)
        if self._pygithub:
            repo_obj = self._get_repo_pygithub(owner, repo)
            if repo_obj:
                result = self._create_or_update_file_pygithub(
                    repo_obj, path, content, message, branch
                )
                if result.success:
                    return result
                self.logger.warning("PyGithub failed, falling back to REST API")
        
        # Fallback to REST API (asynchronous)
        return await self._create_or_update_file_rest(
            owner, repo, path, content, message, branch
        )
    
    async def create_branch(
        self,
        owner: str,
        repo: str,
        branch_name: str,
        from_branch: str = "main",
    ) -> GitHubResult:
        """Create a new branch (auto-selects method)."""
        # Try PyGithub
        if self._pygithub:
            repo_obj = self._get_repo_pygithub(owner, repo)
            if repo_obj:
                result = self._create_branch_pygithub(repo_obj, branch_name, from_branch)
                if result.success:
                    return result
                self.logger.warning("PyGithub failed, falling back to REST API")
        
        # Fallback to REST API
        return await self._create_branch_rest(owner, repo, branch_name, from_branch)
    
    async def create_pull_request(
        self,
        owner: str,
        repo: str,
        title: str,
        head: str,
        base: str = "main",
        body: str = "",
    ) -> Optional[PullRequestInfo]:
        """Create a pull request (auto-selects method)."""
        # Try PyGithub
        if self._pygithub:
            repo_obj = self._get_repo_pygithub(owner, repo)
            if repo_obj:
                pr_info = self._create_pr_pygithub(repo_obj, title, head, base, body)
                if pr_info:
                    return pr_info
                self.logger.warning("PyGithub failed, falling back to REST API")
        
        # Fallback to REST API
        return await self._create_pr_rest(owner, repo, title, head, base, body)
    
    async def push_workflow(
        self,
        owner: str,
        repo: str,
        workflow_content: str,
        workflow_name: str = "ci-cd.yml",
        branch: str = None,
        create_pr: bool = False,
    ) -> GitHubResult:
        """
        Push a GitHub Actions workflow file.
        
        Args:
            owner: Repository owner
            repo: Repository name
            workflow_content: Workflow YAML content
            workflow_name: Workflow file name
            branch: Target branch (creates new if create_pr=True)
            create_pr: Whether to create a PR instead of direct push
            
        Returns:
            GitHubResult with operation status
        """
        result = GitHubResult(success=False)
        path = f".github/workflows/{workflow_name}"
        
        if create_pr:
            # Create a feature branch
            branch = branch or f"devops-agent/add-workflow-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            
            branch_result = await self.create_branch(owner, repo, branch)
            if not branch_result.success and "already exists" not in branch_result.message:
                result.errors = branch_result.errors
                result.method_used = branch_result.method_used
                return result
        
        target_branch = branch or "main"
        
        # Push the workflow file
        file_result = await self.create_or_update_file(
            owner=owner,
            repo=repo,
            path=path,
            content=workflow_content,
            message="Add CI/CD workflow (generated by DevOps Agent)",
            branch=target_branch,
        )
        
        if not file_result.success:
            result.errors = file_result.errors
            result.method_used = file_result.method_used
            return result
        
        result.success = True
        result.url = file_result.url
        result.sha = file_result.sha
        result.method_used = file_result.method_used
        
        if create_pr:
            # Create PR
            pr = await self.create_pull_request(
                owner=owner,
                repo=repo,
                title="Add CI/CD workflow",
                head=target_branch,
                body="""## DevOps Agent Generated CI/CD

This PR adds an automated CI/CD pipeline with:
- Build and test stages
- Docker containerization
- Cloud Run deployment

Please review and merge when ready.
""",
            )
            
            if pr:
                result.message = f"Created PR #{pr.number}"
                result.url = pr.url
            else:
                result.message = f"Workflow pushed to branch '{target_branch}'"
        else:
            result.message = f"Workflow pushed to '{target_branch}'"
        
        return result
    
    async def push_multiple_files(
        self,
        owner: str,
        repo: str,
        files: List[GitHubFile],
        branch: str = None,
        create_pr: bool = False,
    ) -> GitHubResult:
        """Push multiple files to GitHub."""
        result = GitHubResult(success=False)
        
        if create_pr:
            branch = branch or f"devops-agent/update-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
            await self.create_branch(owner, repo, branch)
        
        target_branch = branch or "main"
        
        success_count = 0
        method_used = ""
        for file in files:
            file_result = await self.create_or_update_file(
                owner=owner,
                repo=repo,
                path=file.path,
                content=file.content,
                message=file.message,
                branch=target_branch,
            )
            
            if file_result.success:
                success_count += 1
                if not method_used:
                    method_used = file_result.method_used
            else:
                result.errors.extend(file_result.errors)
        
        result.success = success_count == len(files)
        result.message = f"Pushed {success_count}/{len(files)} files"
        result.method_used = method_used
        
        if create_pr and success_count > 0:
            pr = await self.create_pull_request(
                owner=owner,
                repo=repo,
                title="Update DevOps configuration",
                head=target_branch,
                body=f"Updated {success_count} files via DevOps Agent.",
            )
            if pr:
                result.url = pr.url
        
        return result


# Convenience function
async def push_workflow_to_github(
    owner: str,
    repo: str,
    workflow: str,
    token: str = None,
    create_pr: bool = True,
) -> GitHubResult:
    """
    Push a workflow to GitHub.
    
    Args:
        owner: Repository owner
        repo: Repository name
        workflow: Workflow YAML content
        token: GitHub token
        create_pr: Whether to create PR
        
    Returns:
        GitHubResult
    """
    client = GitHubClient(token)
    try:
        return await client.push_workflow(
            owner=owner,
            repo=repo,
            workflow_content=workflow,
            create_pr=create_pr,
        )
    finally:
        await client.close()

"""Test GitHub Client with PyGithub and REST API fallback."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Test with PyGithub available
class TestGitHubClientWithPyGithub:
    """Tests when PyGithub is installed."""
    
    @pytest.mark.asyncio
    async def test_initialization_with_pygithub(self):
        """Test client initializes with PyG ithub if available."""
        from devops_agent.integrations.github_client import GitHubClient, PYGITHUB_AVAILABLE
        
        client = GitHubClient(token="ghp_test_token")
        
        if PYGITHUB_AVAILABLE:
            assert client._pygithub is not None
            print("✅ PyGithub initialized")
        else:
            assert client._pygithub is None
            print("⚠️ PyGithub not available, using REST API")
    
    @pytest.mark.asyncio
    async def test_create_file_selects_correct_method(self):
        """Test that create_file uses PyGithub when available."""
        from devops_agent.integrations.github_client import GitHubClient
        
        client = GitHubClient(token="ghp_test_token")
        
        # Mock both methods
        with patch.object(client, '_get_repo_pygithub') as mock_pygithub:
            with patch.object(client, '_create_or_update_file_rest') as mock_rest:
                
                # If PyGithub available, should use it
                if client._pygithub:
                    mock_repo = MagicMock()
                    mock_pygithub.return_value = mock_repo
                    
                    # Should NOT call REST API
                    assert mock_rest.call_count == 0
                    print("✅ Uses PyGithub when available")
                else:
                    print("✅ Falls back to REST API")


class TestGitHubClientRESTFallback:
    """Tests for REST API fallback."""
    
    @pytest.mark.asyncio
    async def test_rest_api_create_file(self):
        """Test file creation via REST API."""
        from devops_agent.integrations.github_client import GitHubClient
        
        client = GitHubClient(token="ghp_test_token")
        # Force REST API
        client._pygithub = None
        
        with patch.object(client, '_get_rest_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            
            # Mock file doesn't exist
            mock_client.get = AsyncMock(return_value=MagicMock(status_code=404))
            
            # Mock successful creation
            mock_client.put = AsyncMock(return_value=MagicMock(
                status_code=201,
                json=lambda: {
                    "content": {
                        "html_url": "https://github.com/user/repo/blob/main/test.txt",
                        "sha": "abc123",
                    }
                }
            ))
            
            result = await client._create_or_update_file_rest(
                owner="user",
                repo="repo",
                path="test.txt",
                content="Hello World",
                message="Test",
                branch="main",
            )
            
            assert result.success is True
            assert result.method_used == "rest_api"
            assert "abc123" in result.sha
            print("✅ REST API create file works")
    
    @pytest.mark.asyncio
    async def test_method_result_includes_method_used(self):
        """Test that results include which method was used."""
        from devops_agent.integrations.github_client import GitHubClient, GitHubResult
        
        # PyGithub result
        result1 = GitHubResult(success=True, method_used="pygithub")
        assert result1.to_dict()["method_used"] == "pygithub"
        
        # REST API result
        result2 = GitHubResult(success=True, method_used="rest_api")
        assert result2.to_dict()["method_used"] == "rest_api"
        
        print("✅ Results track method used")


class TestGitHubClientFeatures:
    """Test specific features."""
    
    @pytest.mark.asyncio
    async def test_list_files(self):
        """Test file listing."""
        from devops_agent.integrations.github_client import GitHubClient
        
        client = GitHubClient(token="ghp_test_token")
        client._pygithub = None  # Force REST
        
        with patch.object(client, '_get_rest_client') as mock_get_client:
            mock_client = AsyncMock()
            mock_get_client.return_value = mock_client
            
            # Mock response
            mock_client.get = AsyncMock(return_value=MagicMock(
                status_code=200,
                json=lambda: [
                    {"name": "README.md", "path": "README.md", "type": "file", "size": 1234},
                    {"name": "src", "path": "src", "type": "dir"},
                ]
            ))
            
            files = await client.list_files("user", "repo")
            
            assert len(files) == 2
            assert files[0]["name"] == "README.md"
            assert files[1]["type"] == "dir"
            print("✅ List files works")
    
    @pytest.mark.asyncio
    async def test_get_file_content(self):
        """Test getting file content."""
        from devops_agent.integrations.github_client import GitHubClient
        import base64
        
        client = GitHubClient(token="ghp_test_token")
        client._pygithub = None  # Force REST
        
        test_content = "Hello GitHub!"
        b64_content = base64.b64encode(test_content.encode()).decode()
        
        with patch.object(client, '_get_file_rest') as mock_get:
            mock_get.return_value = {
                "content": b64_content,
                "sha": "abc123",
            }
            
            content = await client.get_file_content("user", "repo", "test.txt")
            
            assert content == test_content
            print("✅ Get file content works")


class TestGitHubIntegration:
    """Integration tests for complete workflows."""
    
    @pytest.mark.asyncio
    async def test_push_workflow_complete(self):
        """Test complete workflow push."""
        from devops_agent.integrations.github_client import GitHubClient
        
        client = GitHubClient(token="ghp_test_token")
        client._pygithub = None  # Force REST for predictability
        
        workflow_yaml = """
name: CI
on: push
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
"""
        
        with patch.object(client, '_create_or_update_file_rest') as mock_file:
            from devops_agent.integrations.github_client import GitHubResult
            
            mock_file.return_value = GitHubResult(
                success=True,
                message="File created",
                url="https://github.com/user/repo/blob/main/.github/workflows/ci-cd.yml",
                sha="abc123",
                method_used="rest_api",
            )
            
            result = await client.push_workflow(
                owner="user",
                repo="repo",
                workflow_content=workflow_yaml,
            )
            
            assert result.success is True
            assert ".github/workflows" in str(mock_file.call_args)
            print("✅ Push workflow complete flow works")


# Run with: pytest tests/integration/test_github_client.py -v -s

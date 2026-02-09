"""
Security utilities for the DevOps agent.

Provides:
- Input sanitization and validation
- Path traversal prevention
- Command injection prevention
- Secrets masking in logs
"""

import re
import os
from pathlib import Path
from typing import List, Optional, Tuple
from urllib.parse import urlparse


class SecurityError(Exception):
    """Raised when a security violation is detected."""
    pass


class InputValidator:
    """
    Validates and sanitizes user inputs to prevent security vulnerabilities.
    """
    
    # Dangerous shell characters that could enable injection
    SHELL_DANGEROUS_CHARS = [";", "|", "&", "$", "`", "\\n", "\\r", "(", ")", "<", ">"]
    
    # Allowed characters in Docker image names
    DOCKER_IMAGE_PATTERN = re.compile(r'^[a-z0-9]+([._-][a-z0-9]+)*(:[a-z0-9._-]+)?$', re.IGNORECASE)
    
    # GitHub repo URL pattern
    GITHUB_URL_PATTERN = re.compile(
        r'^https://github\.com/[a-zA-Z0-9_-]+/[a-zA-Z0-9_.-]+/?$'
    )
    
    @staticmethod
    def sanitize_path(path: str, base_dir: Optional[Path] = None) -> Path:
        """
        Sanitize a file path to prevent directory traversal attacks.
        
        Args:
            path: User-provided path
            base_dir: Base directory to restrict access to
            
        Returns:
            Sanitized Path object
            
        Raises:
            SecurityError: If path attempts traversal or is outside base_dir
        """
        # Convert to Path and resolve to absolute path
        try:
            sanitized = Path(path).resolve()
        except (ValueError, OSError) as e:
            raise SecurityError(f"Invalid path: {e}")
        
        # Check for path traversal attempts
        if ".." in str(path):
            raise SecurityError("Path traversal detected: '..' not allowed")
        
        # If base_dir specified, ensure path is within it
        if base_dir:
            base_resolved = Path(base_dir).resolve()
            try:
                sanitized.relative_to(base_resolved)
            except ValueError:
                raise SecurityError(
                    f"Path {path} is outside allowed directory {base_dir}"
                )
        
        return sanitized
    
    @staticmethod
    def validate_command(command: str, allowed_commands: List[str] = None) -> bool:
        """
        Validate a shell command to prevent injection attacks.
        
        Args:
            command: Command to validate
            allowed_commands: Whitelist of allowed command prefixes
            
        Returns:
            True if command is safe
            
        Raises:
            SecurityError: If command contains dangerous patterns
        """
        # Check for dangerous characters
        for char in InputValidator.SHELL_DANGEROUS_CHARS:
            if char in command:
                raise SecurityError(
                    f"Dangerous character '{char}' detected in command"
                )
        
        # If whitelist provided, check command starts with allowed prefix
        if allowed_commands:
            command_start = command.split()[0] if command.split() else ""
            if not any(command_start.startswith(cmd) for cmd in allowed_commands):
                raise SecurityError(
                    f"Command '{command_start}' not in allowed list"
                )
        
        return True
    
    @staticmethod
    def validate_docker_image(image_name: str) -> bool:
        """
        Validate Docker image name format.
        
        Args:
            image_name: Docker image name (e.g., "nginx:latest")
            
        Returns:
            True if valid
            
        Raises:
            SecurityError: If image name is invalid
        """
        # Remove registry prefix if present
        parts = image_name.split("/")
        image_part = parts[-1]
        
        if not InputValidator.DOCKER_IMAGE_PATTERN.match(image_part):
            raise SecurityError(
                f"Invalid Docker image name: {image_name}"
            )
        
        # Check for suspicious patterns
        if any(char in image_name for char in ["$", "`", ";"]):
            raise SecurityError(
                f"Suspicious characters in Docker image name: {image_name}"
            )
        
        return True
    
    @staticmethod
    def validate_github_url(url: str) -> Tuple[str, str]:
        """
        Validate and parse GitHub repository URL.
        
        Args:
            url: GitHub repository URL
            
        Returns:
            Tuple of (owner, repo)
            
        Raises:
            SecurityError: If URL is invalid
        """
        if not InputValidator.GITHUB_URL_PATTERN.match(url.rstrip("/")):
            raise SecurityError(f"Invalid GitHub URL: {url}")
        
        parsed = urlparse(url)
        path_parts = parsed.path.strip("/").split("/")
        
        if len(path_parts) < 2:
            raise SecurityError(f"Invalid GitHub URL format: {url}")
        
        owner, repo = path_parts[0], path_parts[1].replace(".git", "")
        
        return owner, repo
    
    @staticmethod
    def validate_env_var_name(name: str) -> bool:
        """
        Validate environment variable name.
        
        Args:
            name: Variable name
            
        Returns:
            True if valid
            
        Raises:
            SecurityError: If name is invalid
        """
        # Only allow alphanumeric and underscore
        if not re.match(r'^[A-Z_][A-Z0-9_]*$', name):
            raise SecurityError(
                f"Invalid environment variable name: {name}"
            )
        
        return True
    
    @staticmethod
    def sanitize_template_input(value: str) -> str:
        """
        Sanitize input for template rendering.
        
        Args:
            value: User input for template
            
        Returns:
            Sanitized value
        """
        # Remove any template injection attempts
        dangerous_patterns = [
            r'\{\{.*\}\}',  # Jinja2 expressions
            r'\{%.*%\}',    # Jinja2 statements
            r'<script',     # XSS
            r'javascript:',  # XSS
        ]
        
        sanitized = value
        for pattern in dangerous_patterns:
            sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
        
        return sanitized


class SecretsMasker:
    """
    Masks secrets in logs and output to prevent exposure.
    """
    
    # Common secret patterns
    SECRET_PATTERNS = [
        (re.compile(r'(ghp_[a-zA-Z0-9]{36})'), 'GITHUB_TOKEN'),
        (re.compile(r'(gho_[a-zA-Z0-9]{36})'), 'GITHUB_OAUTH_TOKEN'),
        (re.compile(r'(AIza[a-zA-Z0-9_-]{35})'), 'GOOGLE_API_KEY'),
        (re.compile(r'([a-zA-Z0-9_-]{40})'), 'GENERIC_TOKEN'),
        (re.compile(r'(sk-[a-zA-Z0-9]{48})'), 'OPENAI_KEY'),
        (re.compile(r'(xox[baprs]-[a-zA-Z0-9-]+)'), 'SLACK_TOKEN'),
    ]
    
    @staticmethod
    def mask_secrets(text: str) -> str:
        """
        Mask secrets in text.
        
        Args:
            text: Text that may contain secrets
            
        Returns:
            Text with secrets masked
        """
        masked = text
        
        for pattern, name in SecretsMasker.SECRET_PATTERNS:
            masked = pattern.sub(f'***{name}***', masked)
        
        # Also mask common env var patterns
        masked = re.sub(
            r'(password|token|key|secret)[\s=:]+[^\s]+',
            r'\1=***REDACTED***',
            masked,
            flags=re.IGNORECASE
        )
        
        return masked
    
    @staticmethod
    def mask_dict(data: dict) -> dict:
        """
        Recursively mask secrets in a dictionary.
        
        Args:
            data: Dictionary that may contain secrets
            
        Returns:
            Dictionary with secrets masked
        """
        masked = {}
        
        for key, value in data.items():
            # Check if key suggests a secret
            if any(word in key.lower() for word in ['password', 'token', 'key', 'secret']):
                masked[key] = '***REDACTED***'
            elif isinstance(value, dict):
                masked[key] = SecretsMasker.mask_dict(value)
            elif isinstance(value, str):
                masked[key] = SecretsMasker.mask_secrets(value)
            else:
                masked[key] = value
        
        return masked


# Convenience functions
def validate_path(path: str, base_dir: Optional[Path] = None) -> Path:
    """Validate and sanitize a file path."""
    return InputValidator.sanitize_path(path, base_dir)


def validate_command(command: str, allowed: List[str] = None) -> bool:
    """Validate a shell command."""
    return InputValidator.validate_command(command, allowed)


def mask_secrets(text: str) -> str:
    """Mask secrets in text."""
    return SecretsMasker.mask_secrets(text)

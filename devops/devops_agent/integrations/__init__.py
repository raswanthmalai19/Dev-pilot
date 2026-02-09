"""Integrations module for external services."""

from .github_client import GitHubClient
from .security_hook import SecurityHook, SecurityResult, Vulnerability

__all__ = [
    "GitHubClient",
    "SecurityHook",
    "SecurityResult",
    "Vulnerability",
]

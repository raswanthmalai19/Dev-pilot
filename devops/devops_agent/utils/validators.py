"""Input validation utilities."""

from pathlib import Path
from typing import List, Optional

from ..config import Config


def validate_project_path(path: str | Path) -> tuple[bool, Optional[str]]:
    """
    Validate that a project path exists and is a directory.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    path = Path(path)
    
    if not path.exists():
        return False, f"Path does not exist: {path}"
    
    if not path.is_dir():
        return False, f"Path is not a directory: {path}"
    
    # Check for at least some files
    files = list(path.iterdir())
    if not files:
        return False, f"Directory is empty: {path}"
    
    return True, None


def validate_config(config: Config) -> List[str]:
    """
    Validate configuration and return list of issues.
    
    Returns:
        List of validation errors (empty if valid)
    """
    issues = []
    
    # Check Gemini API key
    if not config.gemini.api_key:
        issues.append("GEMINI_API_KEY environment variable is required")
    
    # Check GCP config if needed
    if config.gcp.project_id == "":
        issues.append("GCP_PROJECT_ID is recommended for cloud deployments")
    
    return issues


def validate_env_vars(required: List[str]) -> List[str]:
    """
    Check if required environment variables are set.
    
    Returns:
        List of missing environment variables
    """
    import os
    
    missing = []
    for var in required:
        if not os.getenv(var):
            missing.append(var)
    
    return missing

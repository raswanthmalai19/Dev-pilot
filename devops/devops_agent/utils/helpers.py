"""Helper utilities."""

import re
import uuid
from typing import Optional


def slugify(text: str, max_length: int = 63) -> str:
    """
    Convert text to a URL/resource-safe slug.
    
    Args:
        text: Text to convert
        max_length: Maximum length (GCP resources have 63 char limit)
        
    Returns:
        Slugified text
    """
    # Convert to lowercase
    slug = text.lower()
    
    # Replace spaces and underscores with hyphens
    slug = slug.replace(" ", "-").replace("_", "-")
    
    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    
    # Truncate to max length
    if len(slug) > max_length:
        slug = slug[:max_length].rstrip('-')
    
    return slug or "unnamed"


def generate_id(prefix: str = "", length: int = 8) -> str:
    """
    Generate a unique identifier.
    
    Args:
        prefix: Optional prefix for the ID
        length: Length of the random portion
        
    Returns:
        Unique identifier string
    """
    random_part = str(uuid.uuid4()).replace("-", "")[:length]
    
    if prefix:
        return f"{prefix}-{random_part}"
    return random_part


def format_duration(seconds: float) -> str:
    """Format duration in human-readable format."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate text to maximum length with suffix."""
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix

"""
Project data models for DevOps Automation Agent.
Defines project metadata and detection results.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from pathlib import Path


class ProjectType(Enum):
    """Supported project types."""
    PYTHON = "python"
    NODEJS = "nodejs"
    GO = "go"
    JAVA = "java"
    RUST = "rust"
    DOTNET = "dotnet"
    STATIC = "static"  # Static HTML/CSS/JS
    UNKNOWN = "unknown"


class Framework(Enum):
    """Detected frameworks."""
    # Python
    FLASK = "flask"
    FASTAPI = "fastapi"
    DJANGO = "django"
    STREAMLIT = "streamlit"
    
    # Node.js
    EXPRESS = "express"
    NEXTJS = "nextjs"
    NESTJS = "nestjs"
    REACT = "react"
    VUE = "vue"
    
    # Go
    GIN = "gin"
    ECHO = "echo"
    FIBER = "fiber"
    
    # Java
    SPRING = "spring"
    SPRING_BOOT = "spring-boot"
    QUARKUS = "quarkus"
    
    # Rust
    ACTIX = "actix"
    AXUM = "axum"
    ROCKET = "rocket"
    
    # .NET
    ASPNET = "aspnet"
    ASPNET_CORE = "aspnet-core"
    
    # None
    NONE = "none"


@dataclass
class Dependency:
    """A project dependency."""
    name: str
    version: Optional[str] = None
    dev: bool = False


@dataclass
class ProjectInfo:
    """
    Complete information about a detected project.
    Populated by the ProjectAnalyzer agent.
    """
    # Basic info
    name: str
    path: Path
    project_type: ProjectType
    
    # Framework and language details  
    framework: Framework = Framework.NONE
    language_version: Optional[str] = None
    
    # Entry points and configuration
    entry_point: Optional[str] = None
    main_file: Optional[str] = None
    config_files: List[str] = field(default_factory=list)
    
    # Dependencies
    dependencies: List[Dependency] = field(default_factory=list)
    package_manager: Optional[str] = None
    
    # Web service details
    port: int = 8080
    is_web_service: bool = False
    health_endpoint: Optional[str] = None
    
    # Build requirements
    build_command: Optional[str] = None
    start_command: Optional[str] = None
    test_command: Optional[str] = None
    
    # Environment
    env_file: Optional[str] = None
    required_env_vars: List[str] = field(default_factory=list)
    
    # Files
    files: List[str] = field(default_factory=list)
    total_file_count: int = 0
    
    # Additional metadata from Gemini analysis
    gemini_analysis: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "name": self.name,
            "path": str(self.path),
            "project_type": self.project_type.value,
            "framework": self.framework.value,
            "language_version": self.language_version,
            "entry_point": self.entry_point,
            "main_file": self.main_file,
            "port": self.port,
            "is_web_service": self.is_web_service,
            "health_endpoint": self.health_endpoint,
            "build_command": self.build_command,
            "start_command": self.start_command,
            "test_command": self.test_command,
            "package_manager": self.package_manager,
            "dependencies": [{"name": d.name, "version": d.version} for d in self.dependencies[:20]],
            "required_env_vars": self.required_env_vars,
            "total_file_count": self.total_file_count,
        }


# Signature files for project detection
PROJECT_SIGNATURES: Dict[ProjectType, List[str]] = {
    ProjectType.PYTHON: [
        "requirements.txt",
        "pyproject.toml", 
        "setup.py",
        "Pipfile",
        "poetry.lock",
        "setup.cfg",
    ],
    ProjectType.NODEJS: [
        "package.json",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
    ],
    ProjectType.GO: [
        "go.mod",
        "go.sum",
    ],
    ProjectType.JAVA: [
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "settings.gradle",
    ],
    ProjectType.RUST: [
        "Cargo.toml",
        "Cargo.lock",
    ],
    ProjectType.DOTNET: [
        "*.csproj",
        "*.sln",
        "*.fsproj",
    ],
    ProjectType.STATIC: [
        "index.html",
    ],
}


# Framework detection patterns
FRAMEWORK_SIGNATURES: Dict[Framework, Dict[str, Any]] = {
    # Python
    Framework.FLASK: {"files": [], "deps": ["flask"]},
    Framework.FASTAPI: {"files": [], "deps": ["fastapi"]},
    Framework.DJANGO: {"files": ["manage.py"], "deps": ["django"]},
    Framework.STREAMLIT: {"files": [], "deps": ["streamlit"]},
    
    # Node.js
    Framework.EXPRESS: {"files": [], "deps": ["express"]},
    Framework.NEXTJS: {"files": ["next.config.js", "next.config.mjs"], "deps": ["next"]},
    Framework.NESTJS: {"files": [], "deps": ["@nestjs/core"]},
    Framework.REACT: {"files": [], "deps": ["react", "react-dom"]},
    Framework.VUE: {"files": ["vue.config.js"], "deps": ["vue"]},
    
    # Go
    Framework.GIN: {"files": [], "deps": ["github.com/gin-gonic/gin"]},
    Framework.ECHO: {"files": [], "deps": ["github.com/labstack/echo"]},
    Framework.FIBER: {"files": [], "deps": ["github.com/gofiber/fiber"]},
    
    # Java
    Framework.SPRING: {"files": [], "deps": ["spring-core"]},
    Framework.SPRING_BOOT: {"files": [], "deps": ["spring-boot"]},
    Framework.QUARKUS: {"files": [], "deps": ["quarkus"]},
    
    # Rust
    Framework.ACTIX: {"files": [], "deps": ["actix-web"]},
    Framework.AXUM: {"files": [], "deps": ["axum"]},
    Framework.ROCKET: {"files": [], "deps": ["rocket"]},
}

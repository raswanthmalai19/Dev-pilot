"""Tests for the Project Analyzer agent."""

import pytest
from pathlib import Path
from devops_agent.models.project import ProjectType, Framework


class TestProjectTypeDetection:
    """Test project type detection logic."""
    
    def test_python_signatures(self):
        """Test Python project detection signatures."""
        from devops_agent.models.project import PROJECT_SIGNATURES
        
        python_sigs = PROJECT_SIGNATURES[ProjectType.PYTHON]
        assert "requirements.txt" in python_sigs
        assert "pyproject.toml" in python_sigs
        assert "setup.py" in python_sigs
    
    def test_nodejs_signatures(self):
        """Test Node.js project detection signatures."""
        from devops_agent.models.project import PROJECT_SIGNATURES
        
        nodejs_sigs = PROJECT_SIGNATURES[ProjectType.NODEJS]
        assert "package.json" in nodejs_sigs
    
    def test_go_signatures(self):
        """Test Go project detection signatures."""
        from devops_agent.models.project import PROJECT_SIGNATURES
        
        go_sigs = PROJECT_SIGNATURES[ProjectType.GO]
        assert "go.mod" in go_sigs


class TestFrameworkDetection:
    """Test framework detection logic."""
    
    def test_flask_signature(self):
        """Test Flask framework detection."""
        from devops_agent.models.project import FRAMEWORK_SIGNATURES
        
        flask_sig = FRAMEWORK_SIGNATURES[Framework.FLASK]
        assert "flask" in flask_sig["deps"]
    
    def test_fastapi_signature(self):
        """Test FastAPI framework detection."""
        from devops_agent.models.project import FRAMEWORK_SIGNATURES
        
        fastapi_sig = FRAMEWORK_SIGNATURES[Framework.FASTAPI]
        assert "fastapi" in fastapi_sig["deps"]


class TestProjectInfo:
    """Test ProjectInfo data model."""
    
    def test_project_info_creation(self):
        """Test creating a ProjectInfo instance."""
        from devops_agent.models.project import ProjectInfo
        
        info = ProjectInfo(
            name="test-project",
            path=Path("/tmp/test"),
            project_type=ProjectType.PYTHON,
        )
        
        assert info.name == "test-project"
        assert info.project_type == ProjectType.PYTHON
        assert info.framework == Framework.NONE
        assert info.port == 8080
    
    def test_project_info_to_dict(self):
        """Test serializing ProjectInfo to dict."""
        from devops_agent.models.project import ProjectInfo
        
        info = ProjectInfo(
            name="test-project",
            path=Path("/tmp/test"),
            project_type=ProjectType.NODEJS,
            framework=Framework.EXPRESS,
            port=3000,
        )
        
        data = info.to_dict()
        assert data["name"] == "test-project"
        assert data["project_type"] == "nodejs"
        assert data["framework"] == "express"
        assert data["port"] == 3000

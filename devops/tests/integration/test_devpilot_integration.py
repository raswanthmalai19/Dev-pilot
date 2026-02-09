"""Integration tests for Dev Pilot pipeline."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
import tempfile
import json


class TestDevPilotPipelineIntegration:
    """Integration tests for the full Dev Pilot pipeline."""
    
    @pytest.fixture
    def sample_python_project(self):
        """Create a sample Python Flask project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            
            # Create requirements.txt
            (project_path / "requirements.txt").write_text(
                "flask==2.0.0\ngunicorn==20.1.0\n"
            )
            
            # Create app.py
            (project_path / "app.py").write_text('''
from flask import Flask, jsonify

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok"})

@app.route("/health")
def health():
    return jsonify({"healthy": True})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
''')
            
            yield project_path
    
    @pytest.fixture
    def sample_nodejs_project(self):
        """Create a sample Node.js Express project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            
            # Create package.json
            package_json = {
                "name": "test-nodejs-app",
                "version": "1.0.0",
                "main": "index.js",
                "scripts": {
                    "start": "node index.js"
                },
                "dependencies": {
                    "express": "^4.18.0"
                }
            }
            (project_path / "package.json").write_text(json.dumps(package_json))
            
            # Create index.js
            (project_path / "index.js").write_text('''
const express = require("express");
const app = express();

app.get("/", (req, res) => res.json({ status: "ok" }));
app.get("/health", (req, res) => res.json({ healthy: true }));

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Listening on port ${PORT}`));
''')
            
            yield project_path
    
    @pytest.mark.asyncio
    async def test_project_analyzer_detects_python(self, sample_python_project):
        """Test ProjectAnalyzer correctly detects Python Flask project."""
        from devops_agent.agents.project_analyzer import ProjectAnalyzer
        from devops_agent.models.project import ProjectType, Framework
        
        analyzer = ProjectAnalyzer()
        result = await analyzer.run(sample_python_project)
        
        assert result.project_type == ProjectType.PYTHON
        assert result.framework == Framework.FLASK
        assert result.port == 5000 or result.port == 8080
    
    @pytest.mark.asyncio
    async def test_project_analyzer_detects_nodejs(self, sample_nodejs_project):
        """Test ProjectAnalyzer correctly detects Node.js Express project."""
        from devops_agent.agents.project_analyzer import ProjectAnalyzer
        from devops_agent.models.project import ProjectType, Framework
        
        analyzer = ProjectAnalyzer()
        result = await analyzer.run(sample_nodejs_project)
        
        assert result.project_type == ProjectType.NODEJS
        assert result.framework == Framework.EXPRESS
    
    @pytest.mark.asyncio
    async def test_config_generator_creates_dockerfile(self, sample_python_project):
        """Test ConfigGenerator creates Dockerfile for project without one."""
        from devops_agent.agents.config_generator import ConfigGenerator
        from devops_agent.agents.project_analyzer import ProjectAnalyzer
        
        analyzer = ProjectAnalyzer()
        project_info = await analyzer.run(sample_python_project)
        
        generator = ConfigGenerator(write_files=False)
        result = await generator.run(project_info)
        
        # Should generate a Dockerfile
        dockerfile_configs = [c for c in result.configs if c.file_type == "dockerfile"]
        assert len(dockerfile_configs) > 0
        
        # Should have sensible content
        dockerfile = dockerfile_configs[0]
        assert "FROM" in dockerfile.content
        assert "python" in dockerfile.content.lower()
    
    @pytest.mark.asyncio
    async def test_precondition_validator_flow(self):
        """Test precondition validation flow."""
        from devops_agent.agents.precondition_validator import (
            PreconditionValidator,
            PipelineInput,
        )
        
        validator = PreconditionValidator()
        
        # Test success case
        success_input = PipelineInput(
            repo_url="https://github.com/user/repo",
            branch="devpilot-tested",
            security_status="PASS",
            qa_status="PASS",
        )
        success_result = await validator.validate(success_input)
        assert success_result.passed is True
        
        # Test failure case
        fail_input = PipelineInput(
            repo_url="https://github.com/user/repo",
            branch="devpilot-tested",
            security_status="FAIL",
            qa_status="PASS",
        )
        fail_result = await validator.validate(fail_input)
        assert fail_result.passed is False


class TestRollbackScenario:
    """Test automatic rollback scenarios."""
    
    @pytest.mark.asyncio
    async def test_rollback_result_structure(self):
        """Test RollbackResult has correct structure."""
        from devops_agent.agents.rollback_agent import RollbackResult
        
        result = RollbackResult(
            success=True,
            service_name="test-service",
            rolled_back_from="rev-2",
            rolled_back_to="rev-1",
            service_url="https://test.run.app",
        )
        
        result_dict = result.to_dict()
        
        assert "success" in result_dict
        assert "service_name" in result_dict
        assert "rolled_back_from" in result_dict
        assert "rolled_back_to" in result_dict


class TestPipelineReporting:
    """Test pipeline reporting and status updates."""
    
    def test_pipeline_report_serialization(self):
        """Test PipelineReport serializes correctly."""
        from devops_agent.agents.devpilot_orchestrator import (
            PipelineReport,
            PipelineStatus,
            StepResult,
            PipelineStep,
        )
        from datetime import datetime
        
        report = PipelineReport(
            deployment_id="dp-test-123",
            status=PipelineStatus.SUCCESS,
            started_at=datetime.now(),
            repo_url="https://github.com/user/repo",
            branch="main",
            service_url="https://service.run.app",
        )
        
        report.steps.append(
            StepResult(
                step=PipelineStep.VALIDATE_PRECONDITIONS,
                success=True,
                started_at=datetime.now(),
                message="Validated",
            )
        )
        
        report_dict = report.to_dict()
        
        assert report_dict["deployment_id"] == "dp-test-123"
        assert report_dict["status"] == "success"
        assert len(report_dict["steps"]) == 1
    
    @pytest.mark.asyncio
    async def test_status_manager_progress(self):
        """Test DeploymentStatusManager tracks progress correctly."""
        from devops_agent.core.deployment_status import (
            DeploymentStatusManager,
            DeploymentPhase,
        )
        
        manager = DeploymentStatusManager("test-deploy")
        
        # Progress should increase through phases
        await manager.start()
        assert manager.current_phase == DeploymentPhase.PENDING
        
        await manager.building("test-image")
        assert manager.current_phase == DeploymentPhase.BUILDING
        assert manager._history[-1].progress_percent == 50
        
        await manager.deploying("test-service")
        assert manager.current_phase == DeploymentPhase.DEPLOYING
        assert manager._history[-1].progress_percent == 80
        
        await manager.success("https://test.run.app")
        assert manager.current_phase == DeploymentPhase.SUCCESS
        assert manager._history[-1].progress_percent == 100


class TestEndToEndMocked:
    """End-to-end tests with mocked GCP services."""
    
    @pytest.mark.asyncio
    async def test_orchestrator_rejects_failed_security(self):
        """Test orchestrator rejects deployment with failed security check."""
        from devops_agent.agents.devpilot_orchestrator import (
            DevPilotOrchestrator,
            DevPilotConfig,
            PipelineStatus,
        )
        
        orchestrator = DevPilotOrchestrator(
            config=DevPilotConfig(project_id="test-project")
        )
        
        # Mock clone to prevent actual git operations
        with patch.object(orchestrator, '_clone_repository') as mock_clone:
            result = await orchestrator.run(
                repo_url="https://github.com/user/repo",
                branch="devpilot-tested",
                security_status="FAIL",  # This should cause rejection
                qa_status="PASS",
            )
        
        assert result.status == PipelineStatus.FAILED
        assert any("Precondition" in e for e in result.errors)


# Run with: pytest tests/integration/test_devpilot_integration.py -v

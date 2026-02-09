"""Unit tests for Dev Pilot agents."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

# Test PreconditionValidator
class TestPreconditionValidator:
    """Tests for PreconditionValidator agent."""
    
    @pytest.mark.asyncio
    async def test_validate_passes_when_all_conditions_met(self):
        """Test validation passes with PASS status."""
        from devops_agent.agents.precondition_validator import (
            PreconditionValidator,
            PipelineInput,
            ValidationStatus,
        )
        
        validator = PreconditionValidator()
        input_data = PipelineInput(
            repo_url="https://github.com/user/repo",
            branch="devpilot-tested",
            security_status="PASS",
            qa_status="PASS",
        )
        
        result = await validator.validate(input_data)
        
        assert result.passed is True
        assert result.status == ValidationStatus.PASSED
        assert len(result.failure_reasons) == 0
    
    @pytest.mark.asyncio
    async def test_validate_fails_when_security_fails(self):
        """Test validation fails with FAIL security status."""
        from devops_agent.agents.precondition_validator import (
            PreconditionValidator,
            PipelineInput,
            ValidationStatus,
            FailureReason,
        )
        
        validator = PreconditionValidator()
        input_data = PipelineInput(
            repo_url="https://github.com/user/repo",
            branch="devpilot-tested",
            security_status="FAIL",
            qa_status="PASS",
        )
        
        result = await validator.validate(input_data)
        
        assert result.passed is False
        assert result.status == ValidationStatus.FAILED
        assert FailureReason.SECURITY_FAILED in result.failure_reasons
    
    @pytest.mark.asyncio
    async def test_validate_fails_when_qa_fails(self):
        """Test validation fails with FAIL QA status."""
        from devops_agent.agents.precondition_validator import (
            PreconditionValidator,
            PipelineInput,
            FailureReason,
        )
        
        validator = PreconditionValidator()
        input_data = PipelineInput(
            repo_url="https://github.com/user/repo",
            branch="devpilot-tested",
            security_status="PASS",
            qa_status="FAIL",
        )
        
        result = await validator.validate(input_data)
        
        assert result.passed is False
        assert FailureReason.QA_FAILED in result.failure_reasons
    
    @pytest.mark.asyncio
    async def test_validate_fails_when_branch_not_approved(self):
        """Test validation fails with unapproved branch."""
        from devops_agent.agents.precondition_validator import (
            PreconditionValidator,
            PipelineInput,
            FailureReason,
        )
        
        validator = PreconditionValidator(
            approved_branches=["devpilot-tested"],
            strict_mode=True,
        )
        input_data = PipelineInput(
            repo_url="https://github.com/user/repo",
            branch="feature-branch",
            security_status="PASS",
            qa_status="PASS",
        )
        
        result = await validator.validate(input_data)
        
        assert result.passed is False
        assert FailureReason.BRANCH_NOT_APPROVED in result.failure_reasons


class TestConfigGenerator:
    """Tests for ConfigGenerator agent."""
    
    @pytest.mark.asyncio
    async def test_detects_missing_dockerfile(self):
        """Test detection of missing Dockerfile."""
        from devops_agent.agents.config_generator import ConfigGenerator
        from devops_agent.models.project import ProjectInfo, ProjectType, Framework
        from pathlib import Path
        import tempfile
        
        # Create temp project without Dockerfile
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)
            (project_path / "requirements.txt").write_text("flask==2.0.0")
            (project_path / "app.py").write_text("from flask import Flask")
            
            project_info = ProjectInfo(
                name="test-app",
                path=project_path,
                project_type=ProjectType.PYTHON,
                framework=Framework.FLASK,
            )
            
            generator = ConfigGenerator(write_files=False)
            result = await generator.run(project_info)
            
            # Should detect Dockerfile is needed
            assert any(
                c.file_type == "dockerfile" 
                for c in result.configs
            )


class TestHealthCheckAgent:
    """Tests for HealthCheckAgent."""
    
    @pytest.mark.asyncio
    async def test_health_check_success(self):
        """Test successful health check."""
        from devops_agent.agents.health_check_agent import HealthCheckAgent
        
        agent = HealthCheckAgent(max_retries=1)
        
        # Mock the HTTP call
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await agent.run(
                service_url="https://example.com",
                health_endpoint="/health",
            )
            
            assert result.healthy is True
    
    @pytest.mark.asyncio
    async def test_health_check_failure(self):
        """Test failed health check."""
        from devops_agent.agents.health_check_agent import HealthCheckAgent
        
        agent = HealthCheckAgent(max_retries=1, retry_delay=0.1)
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )
            
            result = await agent.run(
                service_url="https://example.com",
                health_endpoint="/health",
            )
            
            assert result.healthy is False
            assert result.requires_rollback is True


class TestDeploymentStatus:
    """Tests for DeploymentStatusManager."""
    
    @pytest.mark.asyncio
    async def test_status_update_triggers_callback(self):
        """Test that status updates trigger callbacks."""
        from devops_agent.core.deployment_status import (
            DeploymentStatusManager,
            DeploymentPhase,
        )
        
        manager = DeploymentStatusManager("test-deployment")
        
        received_updates = []
        
        async def callback(update):
            received_updates.append(update)
        
        manager.add_callback(callback)
        
        await manager.update(DeploymentPhase.BUILDING, "Building image")
        
        assert len(received_updates) == 1
        assert received_updates[0].phase == DeploymentPhase.BUILDING
        assert received_updates[0].message == "Building image"
    
    @pytest.mark.asyncio
    async def test_status_history_tracked(self):
        """Test that status history is tracked."""
        from devops_agent.core.deployment_status import (
            DeploymentStatusManager,
            DeploymentPhase,
        )
        
        manager = DeploymentStatusManager("test-deployment")
        
        await manager.start()
        await manager.validating()
        await manager.building("my-image")
        await manager.success("https://example.com")
        
        assert len(manager.history) == 4
        assert manager.current_phase == DeploymentPhase.SUCCESS


class TestRollbackAgent:
    """Tests for RollbackAgent."""
    
    def test_rollback_result_to_dict(self):
        """Test RollbackResult serialization."""
        from devops_agent.agents.rollback_agent import RollbackResult
        
        result = RollbackResult(
            success=True,
            service_name="my-service",
            rolled_back_from="revision-2",
            rolled_back_to="revision-1",
            service_url="https://my-service.run.app",
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["success"] is True
        assert result_dict["service_name"] == "my-service"
        assert result_dict["rolled_back_to"] == "revision-1"


class TestCloudBuildAgent:
    """Tests for CloudBuildAgent."""
    
    def test_version_tag_generation(self):
        """Test version tag generation."""
        from devops_agent.agents.cloud_build_agent import CloudBuildAgent
        
        agent = CloudBuildAgent(project_id="test-project")
        
        # Test without commit hash
        tag = agent._generate_version_tag()
        assert len(tag) > 0
        assert "-" in tag  # Should be YYYYMMDD-HHMMSS format
        
        # Test with commit hash
        tag_with_hash = agent._generate_version_tag("abc12345def67890")
        assert "abc12345" in tag_with_hash


class TestCloudRunDeployAgent:
    """Tests for CloudRunDeployAgent."""
    
    def test_deployment_config_defaults(self):
        """Test DeploymentConfig has sensible defaults."""
        from devops_agent.agents.cloud_run_deploy_agent import DeploymentConfig
        
        config = DeploymentConfig()
        
        assert config.port == 8080
        assert config.cpu == "1"
        assert config.memory == "512Mi"
        assert config.min_instances == 0
        assert config.max_instances == 10
        assert config.allow_unauthenticated is True


class TestDevPilotOrchestrator:
    """Tests for DevPilotOrchestrator."""
    
    def test_config_defaults(self):
        """Test DevPilotConfig defaults."""
        from devops_agent.agents.devpilot_orchestrator import DevPilotConfig
        
        config = DevPilotConfig()
        
        assert config.region == "us-central1"
        assert config.port == 8080
        assert config.auto_rollback is True
        assert config.strict_validation is True
    
    def test_pipeline_status_enum(self):
        """Test PipelineStatus enum values."""
        from devops_agent.agents.devpilot_orchestrator import PipelineStatus
        
        assert PipelineStatus.PENDING.value == "pending"
        assert PipelineStatus.SUCCESS.value == "success"
        assert PipelineStatus.ROLLED_BACK.value == "rolled_back"
    
    def test_step_result_to_dict(self):
        """Test StepResult serialization."""
        from devops_agent.agents.devpilot_orchestrator import (
            StepResult,
            PipelineStep,
        )
        
        result = StepResult(
            step=PipelineStep.BUILD_IMAGE,
            success=True,
            started_at=datetime.now(),
            message="Build successful",
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["step"] == "build_image"
        assert result_dict["success"] is True


# Run with: pytest tests/unit/test_devpilot_agents.py -v

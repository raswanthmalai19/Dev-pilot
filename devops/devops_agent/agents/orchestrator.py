"""
Deployment Orchestrator - Master agent that coordinates the entire pipeline.
"""

import uuid
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .base_agent import BaseAgent
from .project_analyzer import ProjectAnalyzer
from .build_agent import BuildAgent
from .container_agent import ContainerAgent
from .cicd_agent import CICDAgent
from .infra_agent import InfraAgent

from ..models.project import ProjectInfo
from ..models.build_config import BuildResult, BuildStatus
from ..models.deployment import DeploymentResult, DeploymentStatus, ContainerConfig
from ..models.report import PipelineReport, PipelineStatus, Stage, StageResult


class DeploymentOrchestrator(BaseAgent):
    """
    Master orchestrator that coordinates all agents through the pipeline:
    1. Analyze project
    2. Build project
    3. Containerize
    4. Generate CI/CD
    5. Generate infrastructure
    6. Deploy (optional)
    """
    
    def __init__(self, working_dir: Path = None, gemini_client=None):
        super().__init__("Orchestrator", working_dir, gemini_client)
        
        # Initialize sub-agents
        self.analyzer = ProjectAnalyzer(working_dir, gemini_client)
        self.builder = BuildAgent(working_dir, gemini_client)
        self.containerizer = ContainerAgent(working_dir, gemini_client)
        self.cicd = CICDAgent(working_dir, gemini_client)
        self.infra = InfraAgent(working_dir, gemini_client)
    
    def _get_system_instruction(self) -> str:
        return """You are the master DevOps orchestrator. You coordinate multiple 
specialized agents to analyze, build, containerize, and deploy projects. 
Provide clear status updates and handle errors gracefully."""
    
    async def run(
        self,
        project_path: str | Path,
        run_build: bool = True,
        run_tests: bool = False,
        push_container: bool = False,
        deploy: bool = False,
        security_result: Dict[str, Any] = None,
    ) -> PipelineReport:
        """
        Execute the complete DevOps pipeline.
        
        Args:
            project_path: Path to the project directory
            run_build: Whether to actually run the build (vs just generate configs)
            run_tests: Whether to run tests during build
            push_container: Whether to push container to registry
            deploy: Whether to deploy to cloud
            security_result: Result from security agent (integration point)
            
        Returns:
            PipelineReport with complete results
        """
        project_path = Path(project_path)
        pipeline_id = str(uuid.uuid4())[:8]
        
        # Initialize report
        report = PipelineReport(
            pipeline_id=pipeline_id,
            project_name=project_path.name,
            status=PipelineStatus.FAILED,  # Will update on success
        )
        
        self.log_step(f"Starting pipeline {pipeline_id}", 1)
        
        try:
            # Check if security scan passed (if provided)
            if security_result:
                report.security_scan_passed = security_result.get("passed", True)
                if not report.security_scan_passed:
                    self.log_error("Security scan failed - aborting pipeline")
                    report.recommendations.append(
                        "Fix security vulnerabilities before deployment"
                    )
                    return self._finalize_report(report)
            
            # Stage 1: Analyze
            self.log_step("Stage 1: Analyzing project", 2)
            project_info = await self._run_analysis(project_path, report)
            
            if not project_info:
                return self._finalize_report(report)
            
            report.project_type = project_info.project_type.value
            report.framework = project_info.framework.value
            
            # Stage 2: Build (optional)
            if run_build:
                self.log_step("Stage 2: Building project", 3)
                build_result = await self._run_build(project_info, run_tests, report)
                
                if not build_result.success:
                    self.log_error("Build failed - continuing with config generation")
            else:
                self._skip_stage(report, Stage.BUILD, "Build skipped by configuration")
            
            # Stage 3: Containerize
            self.log_step("Stage 3: Containerizing", 4)
            container_result = await self._run_containerize(
                project_info, push_container, report
            )
            
            if container_result:
                report.container_image = container_result.image_url
            
            # Stage 4: Generate CI/CD
            self.log_step("Stage 4: Generating CI/CD pipeline", 5)
            cicd_result = await self._run_cicd(project_info, report)
            
            # Stage 5: Generate Infrastructure
            self.log_step("Stage 5: Generating infrastructure", 6)
            infra_result = await self._run_infra(project_info, report)
            
            # Stage 6: Deploy (optional)
            if deploy and container_result and container_result.image_url:
                self.log_step("Stage 6: Deploying", 7)
                deploy_result = await self._run_deploy(project_info, container_result, report)
                
                if deploy_result:
                    report.deployment_url = deploy_result.service_url
            else:
                self._skip_stage(
                    report, Stage.DEPLOY, 
                    "Deployment skipped - use terraform apply for manual deployment"
                )
            
            # Determine final status
            report.status = self._determine_status(report)
            
            # Add recommendations
            self._add_recommendations(report, project_info)
            
            self.log_success(f"Pipeline {pipeline_id} completed with status: {report.status.value}")
            
        except Exception as e:
            self.log_error(f"Pipeline failed: {e}", e)
            report.status = PipelineStatus.FAILED
        
        return self._finalize_report(report)
    
    async def _run_analysis(
        self, 
        project_path: Path, 
        report: PipelineReport
    ) -> Optional[ProjectInfo]:
        """Run project analysis stage."""
        stage_result = StageResult(stage=Stage.ANALYSIS, success=False)
        
        try:
            project_info = await self.analyzer.run(project_path)
            
            stage_result.success = True
            stage_result.message = f"Detected {project_info.project_type.value} project"
            stage_result.outputs = project_info.to_dict()
            
            self.log_success(f"Analysis complete: {project_info.project_type.value}/{project_info.framework.value}")
            
            report.add_stage_result(self._finalize_stage(stage_result))
            return project_info
            
        except Exception as e:
            stage_result.errors.append(str(e))
            stage_result.message = "Project analysis failed"
            report.add_stage_result(self._finalize_stage(stage_result))
            return None
    
    async def _run_build(
        self, 
        project_info: ProjectInfo, 
        run_tests: bool,
        report: PipelineReport
    ) -> BuildResult:
        """Run build stage."""
        stage_result = StageResult(stage=Stage.BUILD, success=False)
        
        try:
            build_result = await self.builder.run(
                project_info, 
                run_tests=run_tests
            )
            
            stage_result.success = build_result.status == BuildStatus.SUCCESS
            stage_result.message = f"Build {build_result.status.value}"
            stage_result.outputs = build_result.to_dict()
            
            if build_result.errors:
                stage_result.errors = build_result.errors
            if build_result.warnings:
                stage_result.warnings = build_result.warnings
            
            report.add_stage_result(self._finalize_stage(stage_result))
            return build_result
            
        except Exception as e:
            stage_result.errors.append(str(e))
            report.add_stage_result(self._finalize_stage(stage_result))
            return BuildResult(status=BuildStatus.FAILED)
    
    async def _run_containerize(
        self, 
        project_info: ProjectInfo,
        push: bool,
        report: PipelineReport
    ) -> Optional[DeploymentResult]:
        """Run containerization stage."""
        stage_result = StageResult(stage=Stage.CONTAINERIZE, success=False)
        
        try:
            container_result = await self.containerizer.run(
                project_info,
                push_to_registry=push
            )
            
            stage_result.success = container_result.status == DeploymentStatus.SUCCESS
            stage_result.message = f"Container {container_result.status.value}"
            stage_result.files_generated = list(container_result.generated_files.keys())
            
            if container_result.errors:
                stage_result.errors = container_result.errors
            
            # Store generated files in report
            report.generated_files.update(container_result.generated_files)
            
            report.add_stage_result(self._finalize_stage(stage_result))
            return container_result
            
        except Exception as e:
            stage_result.errors.append(str(e))
            report.add_stage_result(self._finalize_stage(stage_result))
            return None
    
    async def _run_cicd(
        self, 
        project_info: ProjectInfo,
        report: PipelineReport
    ) -> Optional[Dict[str, Any]]:
        """Run CI/CD generation stage."""
        stage_result = StageResult(stage=Stage.CICD, success=False)
        
        try:
            cicd_result = await self.cicd.run(project_info)
            
            stage_result.success = cicd_result.get("success", False)
            stage_result.message = "CI/CD pipeline generated"
            stage_result.files_generated = list(cicd_result.get("files", {}).keys())
            
            # Store generated files
            report.generated_files.update(cicd_result.get("files", {}))
            
            report.add_stage_result(self._finalize_stage(stage_result))
            return cicd_result
            
        except Exception as e:
            stage_result.errors.append(str(e))
            report.add_stage_result(self._finalize_stage(stage_result))
            return None
    
    async def _run_infra(
        self, 
        project_info: ProjectInfo,
        report: PipelineReport
    ) -> Optional[Dict[str, Any]]:
        """Run infrastructure generation stage."""
        stage_result = StageResult(stage=Stage.INFRASTRUCTURE, success=False)
        
        try:
            infra_result = await self.infra.run(project_info)
            
            stage_result.success = infra_result.get("success", False)
            stage_result.message = "Terraform configuration generated"
            stage_result.files_generated = list(infra_result.get("files", {}).keys())
            stage_result.outputs["terraform_commands"] = infra_result.get("terraform_commands", [])
            
            # Store generated files
            report.generated_files.update(infra_result.get("files", {}))
            
            report.add_stage_result(self._finalize_stage(stage_result))
            return infra_result
            
        except Exception as e:
            stage_result.errors.append(str(e))
            report.add_stage_result(self._finalize_stage(stage_result))
            return None
    
    async def _run_deploy(
        self, 
        project_info: ProjectInfo,
        container_result: DeploymentResult,
        report: PipelineReport
    ) -> Optional[DeploymentResult]:
        """Run deployment stage."""
        stage_result = StageResult(stage=Stage.DEPLOY, success=False)
        
        try:
            # For now, deployment is via Terraform in CI/CD
            # This would integrate with actual cloud deployment
            stage_result.success = False
            stage_result.message = "Deployment requires terraform apply"
            stage_result.outputs["instructions"] = [
                "cd terraform",
                "terraform init",
                "terraform apply",
            ]
            
            report.add_stage_result(self._finalize_stage(stage_result))
            return None
            
        except Exception as e:
            stage_result.errors.append(str(e))
            report.add_stage_result(self._finalize_stage(stage_result))
            return None
    
    def _skip_stage(self, report: PipelineReport, stage: Stage, message: str) -> None:
        """Mark a stage as skipped."""
        stage_result = StageResult(
            stage=stage,
            success=True,
            message=message,
        )
        stage_result.finished_at = datetime.now()
        report.add_stage_result(stage_result)
    
    def _finalize_stage(self, stage_result: StageResult) -> StageResult:
        """Finalize a stage result with timing."""
        stage_result.finished_at = datetime.now()
        stage_result.duration_seconds = (
            stage_result.finished_at - stage_result.started_at
        ).total_seconds()
        return stage_result
    
    def _finalize_report(self, report: PipelineReport) -> PipelineReport:
        """Finalize the pipeline report."""
        report.finished_at = datetime.now()
        report.duration_seconds = (
            report.finished_at - report.started_at
        ).total_seconds()
        return report
    
    def _determine_status(self, report: PipelineReport) -> PipelineStatus:
        """Determine overall pipeline status."""
        critical_stages = [Stage.ANALYSIS, Stage.CONTAINERIZE]
        
        # Check critical stages
        for stage in critical_stages:
            if stage in report.stages and not report.stages[stage].success:
                return PipelineStatus.FAILED
        
        # Check if all stages succeeded
        all_success = all(
            result.success for result in report.stages.values()
        )
        
        if all_success:
            return PipelineStatus.SUCCESS
        else:
            return PipelineStatus.PARTIAL
    
    def _add_recommendations(self, report: PipelineReport, project_info: ProjectInfo) -> None:
        """Add recommendations based on analysis."""
        recommendations = []
        
        # Health check recommendation
        if not project_info.health_endpoint:
            recommendations.append(
                "Add a /health endpoint for better monitoring and load balancer health checks"
            )
        
        # Test recommendation
        if not project_info.test_command:
            recommendations.append(
                "Add automated tests to improve code quality and deployment confidence"
            )
        
        # Environment variables
        if project_info.required_env_vars:
            recommendations.append(
                f"Configure these environment variables: {', '.join(project_info.required_env_vars)}"
            )
        
        # Next steps
        recommendations.append(
            "Review generated CI/CD workflow and Terraform configuration before applying"
        )
        recommendations.append(
            "Set up required GitHub secrets as documented in .github/SECRETS.md"
        )
        
        report.recommendations = recommendations


# Convenience function for direct usage
async def deploy_project(
    project_path: str | Path,
    run_build: bool = False,
    security_result: Dict[str, Any] = None,
) -> PipelineReport:
    """
    Deploy a project using the DevOps Automation pipeline.
    
    Args:
        project_path: Path to the project
        run_build: Whether to run actual build
        security_result: Optional security scan result
        
    Returns:
        PipelineReport with all results
    """
    orchestrator = DeploymentOrchestrator()
    return await orchestrator.run(
        project_path=project_path,
        run_build=run_build,
        security_result=security_result,
    )

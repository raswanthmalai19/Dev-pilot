"""
Build Agent - Handles project building and dependency installation.
"""

from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime

from .base_agent import BaseAgent
from ..models.project import ProjectInfo, ProjectType
from ..models.build_config import BuildConfig, BuildResult, BuildStatus
from ..core.error_recovery import SelfHealingExecutor, RecoveryResult


class BuildAgent(BaseAgent):
    """
    Handles the build phase:
    - Install dependencies
    - Execute build commands
    - Run tests (optional)
    - Auto-fix failures (when enabled)
    """
    
    def __init__(self, working_dir: Path = None, gemini_client=None):
        super().__init__("BuildAgent", working_dir, gemini_client)
        self.self_healing = SelfHealingExecutor(gemini_client, self.executor)
    
    def _get_system_instruction(self) -> str:
        return """You are an expert in building software projects. 
You understand build systems for Python, Node.js, Go, Java, Rust, and more.
Help diagnose build failures and suggest fixes."""
    
    async def run(
        self, 
        project_info: ProjectInfo,
        config: BuildConfig = None,
        run_tests: bool = False,
        auto_fix: bool = True,  # NEW: Enable self-healing
    ) -> BuildResult:
        """
        Build the project.
        
        Args:
            project_info: Analyzed project information
            config: Build configuration (uses defaults if not provided)
            run_tests: Whether to run tests after build
            auto_fix: Whether to auto-fix failures using Gemini (default: True)
            
        Returns:
            BuildResult with status and artifacts
        """
        config = config or self._create_default_config(project_info)
        result = BuildResult(status=BuildStatus.RUNNING)
        
        self.log_step("Starting build process", 1)
        
        try:
            # Step 1: Install dependencies (with auto-fix if enabled)
            self.log_step("Installing dependencies", 2)
            if auto_fix:
                install_success, output, recovery = await self._install_with_recovery(
                    project_info, config
                )
                result.recovery_attempts = recovery.total_attempts if recovery else 0
            else:
                install_success = await self._install_dependencies(project_info, config)
            
            if not install_success:
                result.status = BuildStatus.FAILED
                result.install_success = False
                result.errors.append("Dependency installation failed")
                return self._finalize_result(result)
            
            result.install_success = True
            
            # Step 2: Build project (with auto-fix if enabled)
            if config.build_command:
                self.log_step(f"Running build: {config.build_command}", 3)
                if auto_fix:
                    build_success, output, recovery = await self._build_with_recovery(
                        project_info, config
                    )
                else:
                    build_success = await self._run_build(project_info, config)
                
                if not build_success:
                    result.status = BuildStatus.FAILED
                    result.build_success = False
                    result.errors.append("Build failed")
                    return self._finalize_result(result)
            
            result.build_success = True
            
            # Step 3: Run tests (optional)
            if run_tests and config.test_command:
                self.log_step(f"Running tests: {config.test_command}", 4)
                test_result = await self._run_tests(project_info, config)
                result.test_success = test_result["success"]
                result.test_count = test_result.get("total", 0)
                result.test_passed = test_result.get("passed", 0)
                result.test_failed = test_result.get("failed", 0)
                
                if not result.test_success:
                    result.warnings.append("Some tests failed")
            
            result.status = BuildStatus.SUCCESS
            self.log_success("Build completed successfully")
            
        except Exception as e:
            result.status = BuildStatus.FAILED
            result.errors.append(str(e))
            self.log_error(f"Build failed: {e}", e)
        
        return self._finalize_result(result)
    
    async def _install_with_recovery(
        self, 
        project_info: ProjectInfo, 
        config: BuildConfig
    ) -> tuple[bool, str, RecoveryResult]:
        """Install dependencies with auto-recovery."""
        if not config.install_command:
            return True, "", None
        
        self.log_step("Installing with self-healing enabled", 2)
        return await self.self_healing.run_with_recovery(
            command=config.install_command,
            project_path=project_info.path,
            timeout=config.install_timeout,
            env=config.env_vars,
        )
    
    async def _build_with_recovery(
        self, 
        project_info: ProjectInfo, 
        config: BuildConfig
    ) -> tuple[bool, str, RecoveryResult]:
        """Run build with auto-recovery."""
        if not config.build_command:
            return True, "", None
        
        self.log_step("Building with self-healing enabled", 3)
        return await self.self_healing.run_with_recovery(
            command=config.build_command,
            project_path=project_info.path,
            timeout=config.build_timeout,
            env=config.env_vars,
        )
    
    def _create_default_config(self, project_info: ProjectInfo) -> BuildConfig:
        """Create default build configuration from project info."""
        return BuildConfig(
            install_command=self._get_install_command(project_info),
            build_command=project_info.build_command,
            test_command=project_info.test_command,
            working_dir=str(project_info.path),
        )
    
    def _get_install_command(self, project_info: ProjectInfo) -> str:
        """Get the dependency installation command."""
        install_commands = {
            ProjectType.PYTHON: "pip install -r requirements.txt",
            ProjectType.NODEJS: {
                "npm": "npm ci",
                "yarn": "yarn install --frozen-lockfile",
                "pnpm": "pnpm install --frozen-lockfile",
            },
            ProjectType.GO: "go mod download",
            ProjectType.JAVA: {
                "maven": "mvn dependency:resolve",
                "gradle": "./gradlew dependencies",
            },
            ProjectType.RUST: "cargo fetch",
        }
        
        cmd = install_commands.get(project_info.project_type)
        
        if isinstance(cmd, dict):
            return cmd.get(project_info.package_manager, list(cmd.values())[0])
        
        return cmd or "echo 'No dependencies to install'"
    
    async def _install_dependencies(
        self, 
        project_info: ProjectInfo, 
        config: BuildConfig
    ) -> bool:
        """Install project dependencies."""
        if not config.install_command:
            return True
        
        self.executor.working_dir = project_info.path
        result = await self.executor.run(
            config.install_command,
            timeout=config.install_timeout,
            env=config.env_vars,
        )
        
        if not result.success:
            self.logger.error(f"Install failed: {result.stderr}")
        
        return result.success
    
    async def _run_build(
        self, 
        project_info: ProjectInfo, 
        config: BuildConfig
    ) -> bool:
        """Run the build command."""
        if not config.build_command:
            return True
        
        self.executor.working_dir = project_info.path
        result = await self.executor.run(
            config.build_command,
            timeout=config.build_timeout,
            env=config.env_vars,
        )
        
        if not result.success:
            self.logger.error(f"Build failed: {result.stderr}")
            # Try to get Gemini to help diagnose
            await self._diagnose_failure(config.build_command, result.output)
        
        return result.success
    
    async def _run_tests(
        self, 
        project_info: ProjectInfo, 
        config: BuildConfig
    ) -> dict:
        """Run tests and return results."""
        if not config.test_command:
            return {"success": True, "skipped": True}
        
        self.executor.working_dir = project_info.path
        result = await self.executor.run(
            config.test_command,
            timeout=config.test_timeout,
            env=config.env_vars,
        )
        
        return {
            "success": result.success,
            "output": result.output,
        }
    
    async def _diagnose_failure(self, command: str, output: str) -> Optional[str]:
        """Use Gemini to diagnose build failure."""
        try:
            prompt = f"""A build command failed. Analyze and suggest fixes:

Command: {command}
Output (last 2000 chars):
{output[-2000:]}

Provide a brief diagnosis and specific fix."""

            response = await self.gemini.generate(prompt, enable_tools=False)
            self.logger.info(f"Diagnosis: {response[:500]}")
            return response
        except Exception:
            return None
    
    def _finalize_result(self, result: BuildResult) -> BuildResult:
        """Finalize the build result with timing."""
        result.finished_at = datetime.now()
        result.duration_seconds = (
            result.finished_at - result.started_at
        ).total_seconds()
        return result

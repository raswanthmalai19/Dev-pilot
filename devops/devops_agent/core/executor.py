"""
Command execution utility for DevOps Automation Agent.
Handles running shell commands with output capture and error handling.
SECURITY: Includes command injection prevention.
"""

import asyncio
import subprocess
import shlex
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Callable, List
from .logger import AgentLogger
from .security import InputValidator, SecretsMasker


@dataclass
class CommandResult:
    """Result of a command execution."""
    command: str
    return_code: int
    stdout: str
    stderr: str
    success: bool
    duration_seconds: float
    
    @property
    def output(self) -> str:
        """Combined stdout and stderr."""
        return f"{self.stdout}\n{self.stderr}".strip()
    
    def to_dict(self) -> dict:
        """Convert to dictionary with secrets masked."""
        return {
            "command": SecretsMasker.mask_secrets(self.command),
            "return_code": self.return_code,
            "stdout": SecretsMasker.mask_secrets(self.stdout),
            "stderr": SecretsMasker.mask_secrets(self.stderr),
            "success": self.success,
            "duration_seconds": self.duration_seconds,
        }


class CommandExecutor:
    """Executes shell commands with proper error handling and logging."""
    
    def __init__(
        self,
        working_dir: Path = None,
        logger: AgentLogger = None,
        allowed_commands: List[str] = None,
        validate_commands: bool = True,
    ):
        self.working_dir = working_dir or Path.cwd()
        self.logger = logger or AgentLogger("CommandExecutor")
        self.allowed_commands = allowed_commands
        self.validate_commands = validate_commands
    
    async def run(
        self,
        command: str,
        timeout: int = 300,
        env: dict = None,
        capture_output: bool = True,
        stream_output: bool = False,
        on_output: Callable[[str], None] = None,
        skip_validation: bool = False,  # For trusted internal commands only
    ) -> CommandResult:
        """
        Execute a shell command asynchronously.
        
        Args:
            command: The command to execute
            timeout: Maximum execution time in seconds
            env: Additional environment variables
            capture_output: Whether to capture stdout/stderr
            stream_output: Whether to stream output in real-time
            on_output: Callback for real-time output
            skip_validation: Skip security validation (use only for trusted commands)
            
        Returns:
            CommandResult with execution details
        """
        import os
        import time
        
        # SECURITY: Validate command before execution
        if self.validate_commands and not skip_validation:
            try:
                InputValidator.validate_command(command, self.allowed_commands)
            except Exception as e:
                self.logger.error(f"Command validation failed: {e}")
                return CommandResult(
                    command=command,
                    return_code=-1,
                    stdout="",
                    stderr=f"Security validation failed: {e}",
                    success=False,
                    duration_seconds=0,
                )
        
        # Mask secrets in logs
        safe_command = SecretsMasker.mask_secrets(command)
        self.logger.debug(f"Executing: {safe_command}")
        start_time = time.time()
        
        # Prepare environment
        full_env = os.environ.copy()
        if env:
            full_env.update(env)
        
        try:
            if stream_output:
                result = await self._run_streaming(command, timeout, full_env, on_output)
            else:
                result = await self._run_simple(command, timeout, full_env)
            
            duration = time.time() - start_time
            
            cmd_result = CommandResult(
                command=command,
                return_code=result.returncode,
                stdout=result.stdout.decode() if result.stdout else "",
                stderr=result.stderr.decode() if result.stderr else "",
                success=result.returncode == 0,
                duration_seconds=duration,
            )
            
            if cmd_result.success:
                self.logger.debug(f"Command succeeded in {duration:.2f}s")
            else:
                self.logger.warning(f"Command failed with code {result.returncode}")
            
            return cmd_result
            
        except asyncio.TimeoutError:
            duration = time.time() - start_time
            self.logger.error(f"Command timed out after {timeout}s")
            return CommandResult(
                command=command,
                return_code=-1,
                stdout="",
                stderr=f"Command timed out after {timeout} seconds",
                success=False,
                duration_seconds=duration,
            )
        except Exception as e:
            duration = time.time() - start_time
            self.logger.error(f"Command execution failed: {e}", exc=e)
            return CommandResult(
                command=command,
                return_code=-1,
                stdout="",
                stderr=str(e),
                success=False,
                duration_seconds=duration,
            )
    
    async def _run_simple(self, command: str, timeout: int, env: dict) -> subprocess.CompletedProcess:
        """Run command without streaming."""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env=env,
        )
        
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout
        )
        
        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    
    async def _run_streaming(
        self, 
        command: str, 
        timeout: int, 
        env: dict,
        on_output: Callable[[str], None] = None,
    ) -> subprocess.CompletedProcess:
        """Run command with real-time output streaming."""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.working_dir,
            env=env,
        )
        
        stdout_lines = []
        stderr_lines = []
        
        async def read_stream(stream, lines: list, is_stderr: bool = False):
            while True:
                line = await stream.readline()
                if not line:
                    break
                decoded = line.decode()
                lines.append(decoded)
                if on_output:
                    on_output(decoded)
        
        try:
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, stdout_lines),
                    read_stream(process.stderr, stderr_lines, True),
                ),
                timeout=timeout
            )
            await process.wait()
        except asyncio.TimeoutError:
            process.kill()
            raise
        
        return subprocess.CompletedProcess(
            args=command,
            returncode=process.returncode,
            stdout="".join(stdout_lines).encode(),
            stderr="".join(stderr_lines).encode(),
        )
    
    def run_sync(self, command: str, timeout: int = 300, env: dict = None) -> CommandResult:
        """Synchronous wrapper for run()."""
        return asyncio.run(self.run(command, timeout, env))
    
    async def check_tool_exists(self, tool: str) -> bool:
        """Check if a command-line tool is available."""
        result = await self.run(f"which {tool}", timeout=10)
        return result.success
    
    async def get_tool_version(self, tool: str, version_flag: str = "--version") -> Optional[str]:
        """Get the version of a tool."""
        result = await self.run(f"{tool} {version_flag}", timeout=10)
        if result.success:
            return result.stdout.strip().split("\n")[0]
        return None

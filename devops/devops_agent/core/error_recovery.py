"""
Error Recovery System - Self-healing build failures using Gemini AI.

This module provides:
- Error analysis and classification
- AI-powered fix generation
- Retry loop with exponential backoff
"""

import asyncio
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

from ..core.logger import get_logger


class ErrorCategory(Enum):
    """Categories of build errors."""
    DEPENDENCY_MISSING = "dependency_missing"
    DEPENDENCY_VERSION = "dependency_version"
    SYNTAX_ERROR = "syntax_error"
    IMPORT_ERROR = "import_error"
    TYPE_ERROR = "type_error"
    CONFIGURATION = "configuration"
    PERMISSION = "permission"
    NETWORK = "network"
    DOCKER = "docker"
    UNKNOWN = "unknown"


class FixAction(Enum):
    """Types of fix actions."""
    INSTALL_DEPENDENCY = "install_dependency"
    UPDATE_DEPENDENCY = "update_dependency"
    MODIFY_FILE = "modify_file"
    CREATE_FILE = "create_file"
    RUN_COMMAND = "run_command"
    SKIP = "skip"  # Error is transient, just retry


@dataclass
class ErrorInfo:
    """Parsed error information."""
    category: ErrorCategory
    message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    details: str = ""
    raw_output: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category.value,
            "message": self.message,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "details": self.details,
        }


@dataclass
class Fix:
    """A fix to apply."""
    action: FixAction
    description: str
    target: Optional[str] = None  # File path or package name
    content: Optional[str] = None  # New content or command
    confidence: float = 0.8
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "description": self.description,
            "target": self.target,
            "confidence": self.confidence,
        }


@dataclass
class RecoveryAttempt:
    """Record of a recovery attempt."""
    attempt_number: int
    error: ErrorInfo
    fix: Optional[Fix]
    success: bool
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    duration_seconds: float = 0


@dataclass
class RecoveryResult:
    """Result of the entire recovery process."""
    original_error: ErrorInfo
    attempts: List[RecoveryAttempt] = field(default_factory=list)
    final_success: bool = False
    total_attempts: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_error": self.original_error.to_dict(),
            "total_attempts": self.total_attempts,
            "final_success": self.final_success,
            "attempts": [
                {
                    "attempt": a.attempt_number,
                    "fix_applied": a.fix.description if a.fix else None,
                    "success": a.success,
                }
                for a in self.attempts
            ],
        }


class ErrorAnalyzer:
    """Analyzes build errors and classifies them."""
    
    # Common error patterns
    PATTERNS = {
        ErrorCategory.DEPENDENCY_MISSING: [
            r"ModuleNotFoundError: No module named '([^']+)'",
            r"ImportError: No module named '?([^'\"]+)'?",
            r"Cannot find module '([^']+)'",
            r"Module not found: Error: Can't resolve '([^']+)'",
            r"package ([^\s]+) is not in GOROOT",
            r"error\[E0433\]: failed to resolve.*`([^`]+)`",
        ],
        ErrorCategory.DEPENDENCY_VERSION: [
            r"requires ([^>=<\s]+)\s*([><=]+)\s*([\d\.]+)",
            r"version conflict",
            r"peer dependency",
            r"incompatible version",
        ],
        ErrorCategory.SYNTAX_ERROR: [
            r"SyntaxError:",
            r"ParseError:",
            r"Unexpected token",
            r"syntax error",
        ],
        ErrorCategory.IMPORT_ERROR: [
            r"ImportError:",
            r"cannot import name",
        ],
        ErrorCategory.TYPE_ERROR: [
            r"TypeError:",
            r"type error",
            r"expected .+ got .+",
        ],
        ErrorCategory.CONFIGURATION: [
            r"configuration",
            r"config file",
            r"\.env",
            r"environment variable",
        ],
        ErrorCategory.PERMISSION: [
            r"permission denied",
            r"EACCES",
            r"access denied",
        ],
        ErrorCategory.NETWORK: [
            r"ECONNREFUSED",
            r"ETIMEDOUT",
            r"network",
            r"could not resolve",
            r"connection refused",
        ],
        ErrorCategory.DOCKER: [
            r"docker",
            r"container",
            r"image",
            r"Dockerfile",
        ],
    }
    
    def __init__(self):
        self.logger = get_logger("ErrorAnalyzer")
    
    def analyze(self, error_output: str, command: str = "") -> ErrorInfo:
        """Analyze error output and classify it."""
        # Check each pattern category
        for category, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, error_output, re.IGNORECASE | re.MULTILINE)
                if match:
                    return self._create_error_info(category, match, error_output)
        
        # Try to extract file and line info even for unknown errors
        file_match = re.search(r'File "([^"]+)", line (\d+)', error_output)
        file_path = file_match.group(1) if file_match else None
        line_number = int(file_match.group(2)) if file_match else None
        
        # Extract the most relevant error line
        error_lines = [
            line for line in error_output.split("\n")
            if "error" in line.lower() or "Error" in line
        ]
        message = error_lines[0] if error_lines else error_output[:200]
        
        return ErrorInfo(
            category=ErrorCategory.UNKNOWN,
            message=message.strip(),
            file_path=file_path,
            line_number=line_number,
            raw_output=error_output,
        )
    
    def _create_error_info(
        self, 
        category: ErrorCategory, 
        match: re.Match, 
        full_output: str
    ) -> ErrorInfo:
        """Create ErrorInfo from a match."""
        # Try to extract file and line
        file_match = re.search(r'File "([^"]+)", line (\d+)', full_output)
        
        return ErrorInfo(
            category=category,
            message=match.group(0),
            file_path=file_match.group(1) if file_match else None,
            line_number=int(file_match.group(2)) if file_match else None,
            details=match.group(1) if match.lastindex else "",
            raw_output=full_output,
        )


class FixGenerator:
    """Generates fixes using Gemini AI."""
    
    def __init__(self, gemini_client=None):
        self.gemini = gemini_client
        self.logger = get_logger("FixGenerator")
    
    async def generate_fix(
        self, 
        error: ErrorInfo, 
        project_path: Path,
        context: Dict[str, Any] = None,
    ) -> Optional[Fix]:
        """Generate a fix for the given error."""
        # First try rule-based fixes
        rule_fix = self._get_rule_based_fix(error)
        if rule_fix:
            self.logger.info(f"Using rule-based fix: {rule_fix.description}")
            return rule_fix
        
        # Fall back to Gemini
        if self.gemini:
            return await self._get_gemini_fix(error, project_path, context)
        
        return None
    
    def _get_rule_based_fix(self, error: ErrorInfo) -> Optional[Fix]:
        """Get a fix using predefined rules."""
        if error.category == ErrorCategory.DEPENDENCY_MISSING:
            # Extract package name
            pkg_patterns = [
                r"No module named '([^']+)'",
                r"Cannot find module '([^']+)'",
                r"Can't resolve '([^']+)'",
            ]
            
            for pattern in pkg_patterns:
                match = re.search(pattern, error.message)
                if match:
                    pkg_name = match.group(1).split(".")[0]  # Get root package
                    return Fix(
                        action=FixAction.INSTALL_DEPENDENCY,
                        description=f"Install missing package: {pkg_name}",
                        target=pkg_name,
                        confidence=0.9,
                    )
        
        elif error.category == ErrorCategory.PERMISSION:
            return Fix(
                action=FixAction.RUN_COMMAND,
                description="Fix file permissions",
                content="chmod -R 755 .",
                confidence=0.7,
            )
        
        elif error.category == ErrorCategory.NETWORK:
            return Fix(
                action=FixAction.SKIP,
                description="Network error - retry after delay",
                confidence=0.6,
            )
        
        return None
    
    async def _get_gemini_fix(
        self, 
        error: ErrorInfo, 
        project_path: Path,
        context: Dict[str, Any] = None,
    ) -> Optional[Fix]:
        """Use Gemini to generate a fix."""
        prompt = f"""You are a DevOps expert. Analyze this build error and suggest a fix.

Error Category: {error.category.value}
Error Message: {error.message}
File: {error.file_path or 'Unknown'}
Line: {error.line_number or 'Unknown'}

Full Error Output (last 1000 chars):
{error.raw_output[-1000:]}

Additional Context:
{context or 'None'}

Respond in JSON format:
{{
    "action": "install_dependency|update_dependency|modify_file|create_file|run_command|skip",
    "description": "Brief description of the fix",
    "target": "file path or package name",
    "content": "new content or command to run",
    "confidence": 0.0-1.0
}}

Only respond with the JSON, no other text."""

        try:
            response = await self.gemini.generate(prompt, enable_tools=False)
            
            # Parse JSON response
            import json
            # Extract JSON from response
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                fix_data = json.loads(json_match.group())
                return Fix(
                    action=FixAction(fix_data["action"]),
                    description=fix_data["description"],
                    target=fix_data.get("target"),
                    content=fix_data.get("content"),
                    confidence=float(fix_data.get("confidence", 0.7)),
                )
        except Exception as e:
            self.logger.warning(f"Gemini fix generation failed: {e}")
        
        return None


class RecoveryLoop:
    """
    Manages the error recovery loop with retries.
    
    Flow:
    1. Command fails
    2. Analyze error
    3. Generate fix
    4. Apply fix
    5. Retry command
    6. Repeat until success or max retries
    """
    
    def __init__(
        self,
        gemini_client=None,
        max_retries: int = 3,
        base_delay: float = 2.0,
        max_delay: float = 30.0,
    ):
        self.analyzer = ErrorAnalyzer()
        self.fix_generator = FixGenerator(gemini_client)
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.logger = get_logger("RecoveryLoop")
    
    async def run(
        self,
        command_fn: Callable,
        project_path: Path,
        apply_fix_fn: Callable[[Fix], bool] = None,
        context: Dict[str, Any] = None,
    ) -> RecoveryResult:
        """
        Run a command with automatic error recovery.
        
        Args:
            command_fn: Async function that runs the command, returns (success, output)
            project_path: Path to the project
            apply_fix_fn: Function to apply a fix, returns success bool
            context: Additional context for fix generation
            
        Returns:
            RecoveryResult with all attempts
        """
        result = RecoveryResult(
            original_error=ErrorInfo(
                category=ErrorCategory.UNKNOWN,
                message="Pending",
            ),
        )
        
        for attempt in range(1, self.max_retries + 1):
            self.logger.info(f"Attempt {attempt}/{self.max_retries}")
            
            # Run the command
            success, output = await command_fn()
            
            if success:
                result.final_success = True
                result.total_attempts = attempt
                self.logger.info(f"Command succeeded on attempt {attempt}")
                return result
            
            # Analyze the error
            error = self.analyzer.analyze(output)
            if attempt == 1:
                result.original_error = error
            
            self.logger.warning(
                f"Command failed: {error.category.value} - {error.message[:100]}"
            )
            
            # Generate a fix
            fix = await self.fix_generator.generate_fix(error, project_path, context)
            
            # Record the attempt
            attempt_record = RecoveryAttempt(
                attempt_number=attempt,
                error=error,
                fix=fix,
                success=False,
            )
            
            if fix:
                self.logger.info(f"Applying fix: {fix.description}")
                
                # Apply the fix
                if apply_fix_fn:
                    fix_applied = await self._apply_fix(fix, project_path, apply_fix_fn)
                    attempt_record.success = fix_applied
                    
                    if not fix_applied:
                        self.logger.warning("Fix could not be applied")
            else:
                self.logger.warning("No fix could be generated")
            
            attempt_record.finished_at = datetime.now()
            attempt_record.duration_seconds = (
                attempt_record.finished_at - attempt_record.started_at
            ).total_seconds()
            result.attempts.append(attempt_record)
            
            # Wait before retry (exponential backoff)
            if attempt < self.max_retries:
                delay = min(self.base_delay * (2 ** (attempt - 1)), self.max_delay)
                self.logger.info(f"Waiting {delay:.1f}s before retry...")
                await asyncio.sleep(delay)
        
        result.total_attempts = self.max_retries
        self.logger.error(f"All {self.max_retries} attempts failed")
        return result
    
    async def _apply_fix(
        self, 
        fix: Fix, 
        project_path: Path,
        apply_fn: Callable,
    ) -> bool:
        """Apply a fix using the provided function."""
        try:
            return await apply_fn(fix)
        except Exception as e:
            self.logger.error(f"Error applying fix: {e}")
            return False


class SelfHealingExecutor:
    """
    Wrapper that adds self-healing capabilities to command execution.
    
    Usage:
        executor = SelfHealingExecutor(gemini_client)
        result = await executor.run_with_recovery(
            command="pip install -r requirements.txt",
            project_path=Path("./my-project"),
        )
    """
    
    def __init__(self, gemini_client=None, base_executor=None):
        from ..core.executor import CommandExecutor
        
        self.gemini = gemini_client
        self.base_executor = base_executor or CommandExecutor()
        self.recovery_loop = RecoveryLoop(gemini_client)
        self.logger = get_logger("SelfHealingExecutor")
    
    async def run_with_recovery(
        self,
        command: str,
        project_path: Path,
        timeout: int = 300,
        env: Dict[str, str] = None,
    ) -> tuple[bool, str, RecoveryResult]:
        """
        Run a command with automatic error recovery.
        
        Returns:
            Tuple of (success, final_output, recovery_result)
        """
        self.base_executor.working_dir = project_path
        last_output = ""
        
        async def run_command():
            nonlocal last_output
            result = await self.base_executor.run(command, timeout=timeout, env=env)
            last_output = result.output
            return result.success, result.output
        
        async def apply_fix(fix: Fix) -> bool:
            return await self._apply_fix(fix, project_path)
        
        recovery_result = await self.recovery_loop.run(
            command_fn=run_command,
            project_path=project_path,
            apply_fix_fn=apply_fix,
            context={"command": command},
        )
        
        return recovery_result.final_success, last_output, recovery_result
    
    async def _apply_fix(self, fix: Fix, project_path: Path) -> bool:
        """Apply a fix to the project."""
        if fix.action == FixAction.INSTALL_DEPENDENCY:
            # Detect package manager and install
            return await self._install_dependency(fix.target, project_path)
        
        elif fix.action == FixAction.RUN_COMMAND:
            if fix.content:
                result = await self.base_executor.run(fix.content, timeout=60)
                return result.success
        
        elif fix.action == FixAction.MODIFY_FILE:
            if fix.target and fix.content:
                file_path = project_path / fix.target
                file_path.write_text(fix.content)
                return True
        
        elif fix.action == FixAction.CREATE_FILE:
            if fix.target and fix.content:
                file_path = project_path / fix.target
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(fix.content)
                return True
        
        elif fix.action == FixAction.SKIP:
            return True  # Just retry
        
        return False
    
    async def _install_dependency(self, package: str, project_path: Path) -> bool:
        """Install a missing dependency."""
        # Detect project type
        if (project_path / "requirements.txt").exists():
            cmd = f"pip install {package}"
        elif (project_path / "package.json").exists():
            cmd = f"npm install {package}"
        elif (project_path / "go.mod").exists():
            cmd = f"go get {package}"
        elif (project_path / "Cargo.toml").exists():
            cmd = f"cargo add {package}"
        else:
            return False
        
        result = await self.base_executor.run(cmd, timeout=120)
        return result.success

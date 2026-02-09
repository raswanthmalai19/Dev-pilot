"""
Security Hook - Integration interface for security scanning agent.

Provides:
- Webhook receiver for security scan results
- Vulnerability classification
- Pipeline gating logic
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Dict, Any, Optional, Callable

from ..core.logger import get_logger


class Severity(Enum):
    """Vulnerability severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"
    UNKNOWN = "unknown"


@dataclass
class Vulnerability:
    """A security vulnerability."""
    id: str
    title: str
    severity: Severity
    description: str = ""
    package: Optional[str] = None
    version: Optional[str] = None
    fixed_version: Optional[str] = None
    cve: Optional[str] = None
    url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "severity": self.severity.value,
            "description": self.description,
            "package": self.package,
            "version": self.version,
            "fixed_version": self.fixed_version,
            "cve": self.cve,
            "url": self.url,
        }


@dataclass
class SecurityResult:
    """Result of a security scan."""
    passed: bool
    scan_tool: str = "unknown"
    scan_duration: float = 0
    scanned_at: datetime = field(default_factory=datetime.now)
    vulnerabilities: List[Vulnerability] = field(default_factory=list)
    fixes_applied: List[str] = field(default_factory=list)
    summary: Dict[str, int] = field(default_factory=dict)
    raw_output: Optional[str] = None
    
    def __post_init__(self):
        """Calculate summary from vulnerabilities."""
        if not self.summary and self.vulnerabilities:
            self.summary = {
                "critical": sum(1 for v in self.vulnerabilities if v.severity == Severity.CRITICAL),
                "high": sum(1 for v in self.vulnerabilities if v.severity == Severity.HIGH),
                "medium": sum(1 for v in self.vulnerabilities if v.severity == Severity.MEDIUM),
                "low": sum(1 for v in self.vulnerabilities if v.severity == Severity.LOW),
                "total": len(self.vulnerabilities),
            }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "scan_tool": self.scan_tool,
            "scan_duration": self.scan_duration,
            "scanned_at": self.scanned_at.isoformat(),
            "summary": self.summary,
            "vulnerabilities": [v.to_dict() for v in self.vulnerabilities],
            "fixes_applied": self.fixes_applied,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SecurityResult":
        """Create SecurityResult from dictionary."""
        vulnerabilities = []
        for v in data.get("vulnerabilities", []):
            vulnerabilities.append(Vulnerability(
                id=v.get("id", "unknown"),
                title=v.get("title", ""),
                severity=Severity(v.get("severity", "unknown")),
                description=v.get("description", ""),
                package=v.get("package"),
                version=v.get("version"),
                fixed_version=v.get("fixed_version"),
                cve=v.get("cve"),
                url=v.get("url"),
            ))
        
        return cls(
            passed=data.get("passed", False),
            scan_tool=data.get("scan_tool", "unknown"),
            scan_duration=data.get("scan_duration", 0),
            vulnerabilities=vulnerabilities,
            fixes_applied=data.get("fixes_applied", []),
            summary=data.get("summary", {}),
        )


class SecurityPolicy:
    """
    Policy for security gating.
    
    Defines what vulnerabilities block the pipeline.
    """
    
    def __init__(
        self,
        block_on_critical: bool = True,
        block_on_high: bool = True,
        block_on_medium: bool = False,
        max_critical: int = 0,
        max_high: int = 0,
        max_medium: int = 5,
        allowed_cves: List[str] = None,
    ):
        self.block_on_critical = block_on_critical
        self.block_on_high = block_on_high
        self.block_on_medium = block_on_medium
        self.max_critical = max_critical
        self.max_high = max_high
        self.max_medium = max_medium
        self.allowed_cves = set(allowed_cves or [])
    
    def evaluate(self, result: SecurityResult) -> tuple[bool, List[str]]:
        """
        Evaluate security result against policy.
        
        Returns:
            Tuple of (should_pass, reasons_for_failure)
        """
        reasons = []
        
        # Filter out allowed CVEs
        active_vulns = [
            v for v in result.vulnerabilities
            if v.cve not in self.allowed_cves
        ]
        
        # Count by severity
        critical_count = sum(1 for v in active_vulns if v.severity == Severity.CRITICAL)
        high_count = sum(1 for v in active_vulns if v.severity == Severity.HIGH)
        medium_count = sum(1 for v in active_vulns if v.severity == Severity.MEDIUM)
        
        # Check against policy
        if self.block_on_critical and critical_count > self.max_critical:
            reasons.append(
                f"Found {critical_count} critical vulnerabilities (max allowed: {self.max_critical})"
            )
        
        if self.block_on_high and high_count > self.max_high:
            reasons.append(
                f"Found {high_count} high vulnerabilities (max allowed: {self.max_high})"
            )
        
        if self.block_on_medium and medium_count > self.max_medium:
            reasons.append(
                f"Found {medium_count} medium vulnerabilities (max allowed: {self.max_medium})"
            )
        
        should_pass = len(reasons) == 0
        return should_pass, reasons


class SecurityHook:
    """
    Integration hook for security scanning.
    
    This is the interface between the security agent and the DevOps pipeline.
    
    Usage (for teammate's security module):
    
        from devops_agent.integrations import SecurityHook, SecurityResult
        
        # Create hook
        hook = SecurityHook()
        
        # Register listener
        @hook.on_scan_complete
        async def handle_result(result: SecurityResult):
            print(f"Scan complete: {result.passed}")
        
        # Submit security result
        await hook.submit_result(security_result)
        
        # Or use in pipeline
        from devops_agent.agents.orchestrator import deploy_project
        
        report = await deploy_project(
            project_path="./app",
            security_result=security_result.to_dict(),
        )
    """
    
    def __init__(self, policy: SecurityPolicy = None):
        self.policy = policy or SecurityPolicy()
        self.logger = get_logger("SecurityHook")
        self._listeners: List[Callable] = []
        self._last_result: Optional[SecurityResult] = None
    
    def on_scan_complete(self, callback: Callable):
        """
        Decorator to register a callback for scan completion.
        
        The callback receives a SecurityResult.
        """
        self._listeners.append(callback)
        return callback
    
    async def submit_result(self, result: SecurityResult) -> tuple[bool, List[str]]:
        """
        Submit a security scan result.
        
        Args:
            result: The security scan result
            
        Returns:
            Tuple of (should_proceed, failure_reasons)
        """
        self._last_result = result
        self.logger.info(
            f"Security scan received: {result.scan_tool}, "
            f"passed={result.passed}, vulnerabilities={len(result.vulnerabilities)}"
        )
        
        # Evaluate against policy
        should_proceed, reasons = self.policy.evaluate(result)
        
        if not should_proceed:
            self.logger.warning(f"Security policy failed: {reasons}")
        
        # Notify listeners
        for listener in self._listeners:
            try:
                await listener(result)
            except Exception as e:
                self.logger.error(f"Listener error: {e}")
        
        return should_proceed, reasons
    
    def get_last_result(self) -> Optional[SecurityResult]:
        """Get the last submitted security result."""
        return self._last_result
    
    def get_pipeline_context(self) -> Dict[str, Any]:
        """
        Get security context for pipeline report.
        
        Returns data to include in the pipeline report.
        """
        if not self._last_result:
            return {"security_scan": None}
        
        result = self._last_result
        should_proceed, reasons = self.policy.evaluate(result)
        
        return {
            "security_scan": {
                "passed": should_proceed,
                "tool": result.scan_tool,
                "vulnerability_count": len(result.vulnerabilities),
                "summary": result.summary,
                "fixes_applied": result.fixes_applied,
                "failure_reasons": reasons,
            }
        }
    
    def generate_badge(self) -> str:
        """Generate a markdown security badge."""
        if not self._last_result:
            return "![Security](https://img.shields.io/badge/security-not%20scanned-lightgrey)"
        
        result = self._last_result
        should_proceed, _ = self.policy.evaluate(result)
        
        if should_proceed and not result.vulnerabilities:
            color = "brightgreen"
            text = "passing"
        elif should_proceed:
            color = "yellow"
            text = f"{len(result.vulnerabilities)}%20issues"
        else:
            color = "red"
            text = "failing"
        
        return f"![Security](https://img.shields.io/badge/security-{text}-{color})"
    
    def format_report_section(self) -> str:
        """Format security section for reports."""
        if not self._last_result:
            return "## Security\n\n_No security scan performed._\n"
        
        result = self._last_result
        should_proceed, reasons = self.policy.evaluate(result)
        
        lines = [
            "## Security Scan",
            "",
            f"**Scanner:** {result.scan_tool}",
            f"**Status:** {'✅ Passed' if should_proceed else '❌ Failed'}",
            f"**Duration:** {result.scan_duration:.2f}s",
            "",
        ]
        
        if result.summary:
            lines.extend([
                "### Vulnerability Summary",
                "",
                f"| Severity | Count |",
                f"|----------|-------|",
                f"| Critical | {result.summary.get('critical', 0)} |",
                f"| High | {result.summary.get('high', 0)} |",
                f"| Medium | {result.summary.get('medium', 0)} |",
                f"| Low | {result.summary.get('low', 0)} |",
                "",
            ])
        
        if reasons:
            lines.extend([
                "### Policy Violations",
                "",
            ])
            for reason in reasons:
                lines.append(f"- ❌ {reason}")
            lines.append("")
        
        if result.fixes_applied:
            lines.extend([
                "### Auto-Applied Fixes",
                "",
            ])
            for fix in result.fixes_applied:
                lines.append(f"- ✅ {fix}")
            lines.append("")
        
        return "\n".join(lines)


# Factory function for easy integration
def create_security_hook(
    block_on_critical: bool = True,
    block_on_high: bool = True,
    allowed_cves: List[str] = None,
) -> SecurityHook:
    """
    Create a security hook with custom policy.
    
    Args:
        block_on_critical: Block pipeline on critical vulnerabilities
        block_on_high: Block pipeline on high vulnerabilities
        allowed_cves: List of CVEs to ignore
        
    Returns:
        Configured SecurityHook
    """
    policy = SecurityPolicy(
        block_on_critical=block_on_critical,
        block_on_high=block_on_high,
        allowed_cves=allowed_cves,
    )
    return SecurityHook(policy)

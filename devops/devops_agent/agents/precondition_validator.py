"""
Precondition Validator - Critical guardrail agent for Dev Pilot pipeline.

Ensures deployment only proceeds if:
- Security stage: PASS
- QA stage: PASS
- Branch is 'devpilot-tested' (QA approved branch)

This is the FIRST checkpoint in the pipeline and MUST pass before any
deployment actions are taken.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent
from ..core.logger import get_logger


class ValidationStatus(Enum):
    """Validation result status."""
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"  # For optional validations


class ValidationFailureReason(Enum):
    """Reasons for validation failure."""
    SECURITY_FAILED = "security_failed"
    QA_FAILED = "qa_failed"
    INVALID_BRANCH = "invalid_branch"
    MISSING_STATUS = "missing_status"
    INVALID_INPUT = "invalid_input"


@dataclass
class ValidationCheck:
    """A single validation check result."""
    name: str
    status: ValidationStatus
    message: str
    required: bool = True
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "required": self.required,
            "details": self.details,
        }


@dataclass
class ValidationResult:
    """Complete validation result."""
    passed: bool
    timestamp: datetime = field(default_factory=datetime.now)
    checks: List[ValidationCheck] = field(default_factory=list)
    failure_reasons: List[ValidationFailureReason] = field(default_factory=list)
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "passed": self.passed,
            "timestamp": self.timestamp.isoformat(),
            "checks": [c.to_dict() for c in self.checks],
            "failure_reasons": [r.value for r in self.failure_reasons],
            "summary": self.summary,
        }


@dataclass
class PipelineInput:
    """Input from previous pipeline stages."""
    # Repository info
    repo_url: Optional[str] = None
    branch: str = "devpilot-tested"
    commit_hash: Optional[str] = None
    
    # Previous stage statuses
    security_status: Optional[str] = None  # PASS or FAIL
    qa_status: Optional[str] = None  # PASS or FAIL
    
    # Metadata
    security_report_url: Optional[str] = None
    qa_report_url: Optional[str] = None
    triggered_by: str = "manual"
    
    # Optional overrides (for testing only, disabled in production)
    skip_security_check: bool = False
    skip_qa_check: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "repo_url": self.repo_url,
            "branch": self.branch,
            "commit_hash": self.commit_hash,
            "security_status": self.security_status,
            "qa_status": self.qa_status,
            "triggered_by": self.triggered_by,
        }


class PreconditionValidator(BaseAgent):
    """
    Critical guardrail agent that validates preconditions before deployment.
    
    This agent enforces the following rules:
    1. NEVER deploy if SECURITY_STATUS != PASS
    2. NEVER deploy if QA_STATUS != PASS
    3. ONLY deploy from approved branches (default: devpilot-tested)
    
    Usage:
        validator = PreconditionValidator()
        result = await validator.validate(
            PipelineInput(
                repo_url="https://github.com/user/repo",
                branch="devpilot-tested",
                security_status="PASS",
                qa_status="PASS",
            )
        )
        
        if not result.passed:
            print("BLOCKED:", result.summary)
            for reason in result.failure_reasons:
                print(f"  - {reason.value}")
    """
    
    # Default approved branches
    APPROVED_BRANCHES = ["devpilot-tested", "main", "master"]
    
    # Required statuses
    REQUIRED_STATUS = "PASS"
    
    def __init__(
        self,
        working_dir=None,
        gemini_client=None,
        strict_mode: bool = True,
        approved_branches: List[str] = None,
    ):
        """
        Initialize the precondition validator.
        
        Args:
            working_dir: Working directory
            gemini_client: Gemini client (optional, not used for validation)
            strict_mode: If True, skip flags are ignored
            approved_branches: List of approved branch names
        """
        super().__init__(working_dir, gemini_client)
        self.strict_mode = strict_mode
        self.approved_branches = approved_branches or self.APPROVED_BRANCHES
        self.logger = get_logger("PreconditionValidator")
        
    def _get_system_instruction(self) -> str:
        """Get system instruction for the agent."""
        return "You are a security-focused validation agent that ensures all preconditions are met before deployment."
    
    async def run(self, input_data: PipelineInput) -> ValidationResult:
        """
        Alias for validate() to match BaseAgent interface.
        """
        return await self.validate(input_data)
    
    async def validate(self, input_data: PipelineInput) -> ValidationResult:
        """
        Validate all preconditions for deployment.
        
        Args:
            input_data: Pipeline input with status information
            
        Returns:
            ValidationResult with pass/fail status and details
        """
        result = ValidationResult(passed=True)
        
        self.logger.info("=" * 60)
        self.logger.info("PRECONDITION VALIDATION")
        self.logger.info("=" * 60)
        
        # 1. Validate Security Status
        security_check = self._validate_security_status(input_data)
        result.checks.append(security_check)
        if security_check.status == ValidationStatus.FAIL:
            result.passed = False
            result.failure_reasons.append(ValidationFailureReason.SECURITY_FAILED)
            
        # 2. Validate QA Status
        qa_check = self._validate_qa_status(input_data)
        result.checks.append(qa_check)
        if qa_check.status == ValidationStatus.FAIL:
            result.passed = False
            result.failure_reasons.append(ValidationFailureReason.QA_FAILED)
            
        # 3. Validate Branch
        branch_check = self._validate_branch(input_data)
        result.checks.append(branch_check)
        if branch_check.status == ValidationStatus.FAIL:
            result.passed = False
            result.failure_reasons.append(ValidationFailureReason.INVALID_BRANCH)
            
        # 4. Validate Input Completeness
        input_check = self._validate_input(input_data)
        result.checks.append(input_check)
        if input_check.status == ValidationStatus.FAIL:
            result.passed = False
            result.failure_reasons.append(ValidationFailureReason.INVALID_INPUT)
        
        # Build summary
        if result.passed:
            result.summary = "All preconditions passed. Deployment authorized."
            self.logger.info("✅ VALIDATION PASSED - Deployment authorized")
        else:
            failed_checks = [c for c in result.checks if c.status == ValidationStatus.FAIL]
            reasons = ", ".join([r.value for r in result.failure_reasons])
            result.summary = f"Validation failed: {reasons}. Deployment BLOCKED."
            
            self.logger.error("❌ VALIDATION FAILED - Deployment BLOCKED")
            for check in failed_checks:
                self.logger.error(f"   - {check.name}: {check.message}")
                
        self.logger.info("=" * 60)
        
        return result
    
    def _validate_security_status(self, input_data: PipelineInput) -> ValidationCheck:
        """Validate security stage status."""
        check_name = "Security Status"
        
        # Check if skip is allowed (only in non-strict mode)
        if input_data.skip_security_check and not self.strict_mode:
            self.logger.warning("⚠️  Security check SKIPPED (non-strict mode)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.SKIP,
                message="Security check skipped (non-strict mode)",
                required=True,
                details={"skipped": True},
            )
        
        # Missing status
        if not input_data.security_status:
            self.logger.error(f"❌ {check_name}: Missing (required)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message="Security status is missing. Security scan is required.",
                required=True,
                details={"status": None},
            )
        
        # Check status value
        status_upper = input_data.security_status.upper()
        
        if status_upper == self.REQUIRED_STATUS:
            self.logger.info(f"✅ {check_name}: PASS")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.PASS,
                message="Security scan passed",
                required=True,
                details={
                    "status": status_upper,
                    "report_url": input_data.security_report_url,
                },
            )
        else:
            self.logger.error(f"❌ {check_name}: {status_upper} (required: PASS)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message=f"Security scan failed (status: {status_upper})",
                required=True,
                details={
                    "status": status_upper,
                    "report_url": input_data.security_report_url,
                },
            )
    
    def _validate_qa_status(self, input_data: PipelineInput) -> ValidationCheck:
        """Validate QA stage status."""
        check_name = "QA Status"
        
        # Check if skip is allowed (only in non-strict mode)
        if input_data.skip_qa_check and not self.strict_mode:
            self.logger.warning("⚠️  QA check SKIPPED (non-strict mode)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.SKIP,
                message="QA check skipped (non-strict mode)",
                required=True,
                details={"skipped": True},
            )
        
        # Missing status
        if not input_data.qa_status:
            self.logger.error(f"❌ {check_name}: Missing (required)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message="QA status is missing. QA testing is required.",
                required=True,
                details={"status": None},
            )
        
        # Check status value
        status_upper = input_data.qa_status.upper()
        
        if status_upper == self.REQUIRED_STATUS:
            self.logger.info(f"✅ {check_name}: PASS")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.PASS,
                message="QA testing passed",
                required=True,
                details={
                    "status": status_upper,
                    "report_url": input_data.qa_report_url,
                },
            )
        else:
            self.logger.error(f"❌ {check_name}: {status_upper} (required: PASS)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message=f"QA testing failed (status: {status_upper})",
                required=True,
                details={
                    "status": status_upper,
                    "report_url": input_data.qa_report_url,
                },
            )
    
    def _validate_branch(self, input_data: PipelineInput) -> ValidationCheck:
        """Validate branch is approved for deployment."""
        check_name = "Branch Validation"
        
        if not input_data.branch:
            self.logger.error(f"❌ {check_name}: Branch not specified")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message="Branch not specified",
                required=True,
                details={"branch": None},
            )
        
        # Check if branch is in approved list
        if input_data.branch in self.approved_branches:
            self.logger.info(f"✅ {check_name}: {input_data.branch} (approved)")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.PASS,
                message=f"Branch '{input_data.branch}' is approved for deployment",
                required=True,
                details={
                    "branch": input_data.branch,
                    "approved_branches": self.approved_branches,
                },
            )
        else:
            self.logger.error(f"❌ {check_name}: {input_data.branch} not in approved list")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message=f"Branch '{input_data.branch}' is not approved. Approved: {self.approved_branches}",
                required=True,
                details={
                    "branch": input_data.branch,
                    "approved_branches": self.approved_branches,
                },
            )
    
    def _validate_input(self, input_data: PipelineInput) -> ValidationCheck:
        """Validate input data completeness."""
        check_name = "Input Validation"
        
        missing = []
        
        # Check required fields
        if not input_data.repo_url:
            missing.append("repo_url")
            
        if missing:
            self.logger.warning(f"⚠️  {check_name}: Missing fields: {missing}")
            return ValidationCheck(
                name=check_name,
                status=ValidationStatus.FAIL,
                message=f"Missing required fields: {missing}",
                required=True,
                details={"missing_fields": missing},
            )
        
        self.logger.info(f"✅ {check_name}: All required fields present")
        return ValidationCheck(
            name=check_name,
            status=ValidationStatus.PASS,
            message="All required input fields present",
            required=True,
            details={"input": input_data.to_dict()},
        )
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check prerequisites for the validator."""
        return {
            "strict_mode": self.strict_mode,
            "approved_branches": self.approved_branches,
            "ready": True,
        }


# Convenience function
async def validate_preconditions(
    security_status: str,
    qa_status: str,
    branch: str = "devpilot-tested",
    repo_url: str = None,
    strict_mode: bool = True,
) -> ValidationResult:
    """
    Validate deployment preconditions.
    
    Args:
        security_status: Security scan status (PASS/FAIL)
        qa_status: QA test status (PASS/FAIL)
        branch: Branch name
        repo_url: Repository URL
        strict_mode: Enforce all checks
        
    Returns:
        ValidationResult with pass/fail status
    """
    validator = PreconditionValidator(strict_mode=strict_mode)
    
    input_data = PipelineInput(
        repo_url=repo_url,
        branch=branch,
        security_status=security_status,
        qa_status=qa_status,
    )
    
    return await validator.validate(input_data)

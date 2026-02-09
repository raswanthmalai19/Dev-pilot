"""
Terraform Client - CLI wrapper for infrastructure automation.

Provides:
- init/plan/apply/destroy operations
- State management helpers
- Output parsing
- Rollback support
"""

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

from ..core.logger import get_logger
from ..core.executor import CommandExecutor


@dataclass
class TerraformPlan:
    """Result of terraform plan."""
    success: bool
    has_changes: bool = False
    add: int = 0
    change: int = 0
    destroy: int = 0
    plan_file: Optional[str] = None
    output: str = ""
    errors: List[str] = field(default_factory=list)


@dataclass
class TerraformApplyResult:
    """Result of terraform apply."""
    success: bool
    outputs: Dict[str, Any] = field(default_factory=dict)
    resources_created: int = 0
    resources_updated: int = 0
    resources_destroyed: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0


@dataclass
class TerraformState:
    """Terraform state information."""
    exists: bool
    backend: Optional[str] = None
    resources: List[str] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)


class TerraformClient:
    """
    Terraform CLI wrapper for automated infrastructure management.
    
    Usage:
        tf = TerraformClient(working_dir=Path("./terraform"))
        await tf.init()
        plan = await tf.plan()
        if plan.has_changes:
            result = await tf.apply(auto_approve=True)
            print(f"Service URL: {result.outputs.get('service_url')}")
    """
    
    def __init__(
        self,
        working_dir: Path = None,
        var_file: str = None,
        backend_config: Dict[str, str] = None,
    ):
        self.working_dir = working_dir or Path.cwd()
        self.var_file = var_file
        self.backend_config = backend_config or {}
        self.logger = get_logger("TerraformClient")
        self.executor = CommandExecutor(working_dir=self.working_dir)
    
    async def check_installed(self) -> tuple[bool, Optional[str]]:
        """Check if Terraform is installed and return version."""
        result = await self.executor.run("terraform version -json", timeout=10)
        
        if result.success:
            try:
                data = json.loads(result.stdout)
                version = data.get("terraform_version", "unknown")
                return True, version
            except json.JSONDecodeError:
                # Fallback to text parsing
                return True, result.stdout.split("\n")[0]
        
        return False, None
    
    async def init(
        self,
        upgrade: bool = False,
        reconfigure: bool = False,
        on_output: Callable[[str], None] = None,
    ) -> bool:
        """
        Initialize Terraform working directory.
        
        Args:
            upgrade: Upgrade modules and plugins
            reconfigure: Reconfigure backend
            on_output: Callback for streaming output
            
        Returns:
            True if successful
        """
        self.logger.info("Initializing Terraform...")
        
        cmd_parts = ["terraform", "init"]
        
        if upgrade:
            cmd_parts.append("-upgrade")
        
        if reconfigure:
            cmd_parts.append("-reconfigure")
        
        # Add backend config
        for key, value in self.backend_config.items():
            cmd_parts.append(f"-backend-config={key}={value}")
        
        cmd_parts.append("-input=false")
        
        cmd = " ".join(cmd_parts)
        
        result = await self.executor.run(
            cmd,
            timeout=300,
            stream_output=on_output is not None,
            on_output=on_output,
        )
        
        if result.success:
            self.logger.info("Terraform initialized successfully")
        else:
            self.logger.error(f"Terraform init failed: {result.stderr}")
        
        return result.success
    
    async def validate(self) -> tuple[bool, List[str]]:
        """
        Validate Terraform configuration.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        result = await self.executor.run(
            "terraform validate -json",
            timeout=60,
        )
        
        try:
            data = json.loads(result.stdout)
            is_valid = data.get("valid", False)
            errors = [
                diag.get("summary", "")
                for diag in data.get("diagnostics", [])
                if diag.get("severity") == "error"
            ]
            return is_valid, errors
        except json.JSONDecodeError:
            return result.success, [result.stderr] if not result.success else []
    
    async def plan(
        self,
        out_file: str = "tfplan",
        var_overrides: Dict[str, str] = None,
        target: str = None,
        on_output: Callable[[str], None] = None,
    ) -> TerraformPlan:
        """
        Create Terraform plan.
        
        Args:
            out_file: Plan output file
            var_overrides: Variable overrides
            target: Specific resource to target
            on_output: Callback for streaming output
            
        Returns:
            TerraformPlan with changes summary
        """
        self.logger.info("Creating Terraform plan...")
        
        plan = TerraformPlan(success=False, plan_file=out_file)
        
        cmd_parts = ["terraform", "plan", "-input=false"]
        
        if out_file:
            cmd_parts.append(f"-out={out_file}")
        
        if self.var_file:
            cmd_parts.append(f"-var-file={self.var_file}")
        
        if var_overrides:
            for key, value in var_overrides.items():
                cmd_parts.append(f"-var={key}={value}")
        
        if target:
            cmd_parts.append(f"-target={target}")
        
        cmd = " ".join(cmd_parts)
        
        result = await self.executor.run(
            cmd,
            timeout=600,
            stream_output=on_output is not None,
            on_output=on_output,
        )
        
        plan.success = result.success
        plan.output = result.output
        
        if result.success:
            # Parse plan output for changes
            plan.has_changes = "No changes" not in result.stdout
            
            # Try to parse change counts
            import re
            match = re.search(
                r"(\d+) to add, (\d+) to change, (\d+) to destroy",
                result.output
            )
            if match:
                plan.add = int(match.group(1))
                plan.change = int(match.group(2))
                plan.destroy = int(match.group(3))
                plan.has_changes = (plan.add + plan.change + plan.destroy) > 0
            
            self.logger.info(
                f"Plan complete: +{plan.add} ~{plan.change} -{plan.destroy}"
            )
        else:
            plan.errors.append(result.stderr)
            self.logger.error(f"Plan failed: {result.stderr}")
        
        return plan
    
    async def apply(
        self,
        plan_file: str = None,
        auto_approve: bool = False,
        var_overrides: Dict[str, str] = None,
        on_output: Callable[[str], None] = None,
    ) -> TerraformApplyResult:
        """
        Apply Terraform changes.
        
        Args:
            plan_file: Previously created plan file
            auto_approve: Skip approval prompt
            var_overrides: Variable overrides
            on_output: Callback for streaming output
            
        Returns:
            TerraformApplyResult with outputs
        """
        self.logger.info("Applying Terraform changes...")
        
        result = TerraformApplyResult(success=False)
        start_time = datetime.now()
        
        cmd_parts = ["terraform", "apply", "-input=false"]
        
        if auto_approve:
            cmd_parts.append("-auto-approve")
        
        if plan_file:
            cmd_parts.append(plan_file)
        else:
            if self.var_file:
                cmd_parts.append(f"-var-file={self.var_file}")
            
            if var_overrides:
                for key, value in var_overrides.items():
                    cmd_parts.append(f"-var={key}={value}")
        
        cmd = " ".join(cmd_parts)
        
        exec_result = await self.executor.run(
            cmd,
            timeout=1200,  # 20 minute timeout
            stream_output=on_output is not None,
            on_output=on_output,
        )
        
        result.success = exec_result.success
        result.duration_seconds = (datetime.now() - start_time).total_seconds()
        
        if exec_result.success:
            # Get outputs
            result.outputs = await self.get_outputs()
            
            # Parse resource counts
            import re
            match = re.search(
                r"(\d+) added, (\d+) changed, (\d+) destroyed",
                exec_result.output
            )
            if match:
                result.resources_created = int(match.group(1))
                result.resources_updated = int(match.group(2))
                result.resources_destroyed = int(match.group(3))
            
            self.logger.info(
                f"Apply complete: +{result.resources_created} "
                f"~{result.resources_updated} -{result.resources_destroyed}"
            )
        else:
            result.errors.append(exec_result.stderr)
            self.logger.error(f"Apply failed: {exec_result.stderr}")
        
        return result
    
    async def destroy(
        self,
        auto_approve: bool = False,
        target: str = None,
        on_output: Callable[[str], None] = None,
    ) -> bool:
        """
        Destroy Terraform-managed infrastructure.
        
        Args:
            auto_approve: Skip approval prompt
            target: Specific resource to destroy
            on_output: Callback for streaming output
            
        Returns:
            True if successful
        """
        self.logger.warning("Destroying Terraform infrastructure...")
        
        cmd_parts = ["terraform", "destroy", "-input=false"]
        
        if auto_approve:
            cmd_parts.append("-auto-approve")
        
        if self.var_file:
            cmd_parts.append(f"-var-file={self.var_file}")
        
        if target:
            cmd_parts.append(f"-target={target}")
        
        cmd = " ".join(cmd_parts)
        
        result = await self.executor.run(
            cmd,
            timeout=1200,
            stream_output=on_output is not None,
            on_output=on_output,
        )
        
        if result.success:
            self.logger.info("Destroy complete")
        else:
            self.logger.error(f"Destroy failed: {result.stderr}")
        
        return result.success
    
    async def get_outputs(self) -> Dict[str, Any]:
        """Get Terraform outputs."""
        result = await self.executor.run(
            "terraform output -json",
            timeout=30,
        )
        
        if result.success:
            try:
                data = json.loads(result.stdout)
                # Extract just the values
                return {
                    key: info.get("value")
                    for key, info in data.items()
                }
            except json.JSONDecodeError:
                pass
        
        return {}
    
    async def get_state(self) -> TerraformState:
        """Get current Terraform state information."""
        state = TerraformState(exists=False)
        
        # Check if state exists
        result = await self.executor.run(
            "terraform state list",
            timeout=30,
        )
        
        if result.success and result.stdout.strip():
            state.exists = True
            state.resources = result.stdout.strip().split("\n")
            state.outputs = await self.get_outputs()
        
        return state
    
    async def refresh(self) -> bool:
        """Refresh Terraform state."""
        result = await self.executor.run(
            "terraform refresh -input=false",
            timeout=300,
        )
        return result.success
    
    async def import_resource(
        self,
        address: str,
        resource_id: str,
    ) -> bool:
        """
        Import an existing resource into Terraform state.
        
        Args:
            address: Resource address (e.g., "google_cloud_run_service.app")
            resource_id: Resource ID
            
        Returns:
            True if successful
        """
        result = await self.executor.run(
            f"terraform import {address} {resource_id}",
            timeout=120,
        )
        return result.success


# Convenience functions
async def deploy_infrastructure(
    terraform_dir: Path,
    var_file: str = None,
    variables: Dict[str, str] = None,
    auto_approve: bool = True,
) -> TerraformApplyResult:
    """
    Deploy infrastructure using Terraform.
    
    Args:
        terraform_dir: Directory containing Terraform files
        var_file: Variables file
        variables: Variable overrides
        auto_approve: Auto-approve changes
        
    Returns:
        TerraformApplyResult
    """
    tf = TerraformClient(working_dir=terraform_dir, var_file=var_file)
    
    # Initialize
    if not await tf.init():
        return TerraformApplyResult(success=False, errors=["Init failed"])
    
    # Validate
    is_valid, errors = await tf.validate()
    if not is_valid:
        return TerraformApplyResult(success=False, errors=errors)
    
    # Plan
    plan = await tf.plan(var_overrides=variables)
    if not plan.success:
        return TerraformApplyResult(success=False, errors=plan.errors)
    
    if not plan.has_changes:
        return TerraformApplyResult(
            success=True,
            outputs=await tf.get_outputs(),
        )
    
    # Apply
    return await tf.apply(
        plan_file=plan.plan_file,
        auto_approve=auto_approve,
        var_overrides=variables,
    )


async def destroy_infrastructure(
    terraform_dir: Path,
    auto_approve: bool = False,
) -> bool:
    """
    Destroy Terraform-managed infrastructure.
    
    Args:
        terraform_dir: Directory containing Terraform files
        auto_approve: Auto-approve destruction
        
    Returns:
        True if successful
    """
    tf = TerraformClient(working_dir=terraform_dir)
    
    if not await tf.init():
        return False
    
    return await tf.destroy(auto_approve=auto_approve)

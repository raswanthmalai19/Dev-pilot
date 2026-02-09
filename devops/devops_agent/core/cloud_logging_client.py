"""
Cloud Logging Client - Native GCP SDK for pipeline observability.

Provides:
- Write structured logs for each pipeline step
- Query logs for debugging
- Store deployment history
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List

from ..core.logger import get_logger
from ..config import get_config


class LogSeverity(Enum):
    """Log severity levels."""
    DEFAULT = "DEFAULT"
    DEBUG = "DEBUG"
    INFO = "INFO"
    NOTICE = "NOTICE"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    ALERT = "ALERT"
    EMERGENCY = "EMERGENCY"


@dataclass
class LogEntry:
    """A log entry."""
    message: str
    severity: LogSeverity = LogSeverity.INFO
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)
    json_payload: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "message": self.message,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "json_payload": self.json_payload,
        }


@dataclass
class DeploymentLogEntry:
    """Structured deployment log entry."""
    deployment_id: str
    step: str
    status: str
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    duration_seconds: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "deployment_id": self.deployment_id,
            "step": self.step,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
        }


class CloudLoggingClient:
    """
    GCP Cloud Logging client for pipeline observability.
    
    Usage:
        client = CloudLoggingClient(project_id="my-project")
        
        # Log a deployment step
        await client.log_deployment_step(
            deployment_id="deploy-123",
            step="BUILD",
            status="SUCCESS",
            message="Docker image built successfully",
        )
        
        # Query deployment logs
        logs = await client.get_deployment_logs("deploy-123")
    """
    
    # Log names
    DEVPILOT_LOG = "devpilot-pipeline"
    DEPLOYMENT_LOG = "devpilot-deployments"
    
    def __init__(
        self,
        project_id: str = None,
    ):
        """
        Initialize Cloud Logging client.
        
        Args:
            project_id: GCP project ID
        """
        self.config = get_config()
        self.project_id = project_id or self.config.gcp.project_id
        self.local_logger = get_logger("CloudLoggingClient")
        self._client = None
        
    def _get_client(self):
        """Get or create Cloud Logging client."""
        if self._client is None:
            try:
                from google.cloud import logging as cloud_logging
                self._client = cloud_logging.Client(project=self.project_id)
            except ImportError:
                self.local_logger.error("google-cloud-logging not installed")
                raise ImportError("google-cloud-logging package required")
        return self._client
    
    def _get_logger(self, log_name: str):
        """Get a Cloud Logging logger."""
        client = self._get_client()
        return client.logger(log_name)
    
    async def log(
        self,
        message: str,
        severity: LogSeverity = LogSeverity.INFO,
        log_name: str = None,
        labels: Dict[str, str] = None,
        json_payload: Dict[str, Any] = None,
    ) -> bool:
        """
        Write a log entry to Cloud Logging.
        
        Args:
            message: Log message
            severity: Log severity
            log_name: Log name (default: devpilot-pipeline)
            labels: Log labels
            json_payload: Additional JSON data
            
        Returns:
            True if logged successfully
        """
        def _write_log():
            logger = self._get_logger(log_name or self.DEVPILOT_LOG)
            
            if json_payload:
                logger.log_struct(
                    {
                        "message": message,
                        **json_payload,
                    },
                    severity=severity.value,
                    labels=labels,
                )
            else:
                logger.log_text(
                    message,
                    severity=severity.value,
                    labels=labels,
                )
                
        try:
            await asyncio.get_event_loop().run_in_executor(None, _write_log)
            return True
        except Exception as e:
            self.local_logger.warning(f"Failed to write to Cloud Logging: {e}")
            return False
    
    async def log_deployment_step(
        self,
        deployment_id: str,
        step: str,
        status: str,
        message: str,
        duration_seconds: float = 0,
        metadata: Dict[str, Any] = None,
    ) -> bool:
        """
        Log a deployment pipeline step.
        
        Args:
            deployment_id: Unique deployment ID
            step: Pipeline step name (e.g., BUILD, DEPLOY, HEALTH_CHECK)
            status: Step status (e.g., STARTED, SUCCESS, FAILED)
            message: Human-readable message
            duration_seconds: Step duration
            metadata: Additional metadata
            
        Returns:
            True if logged successfully
        """
        severity = LogSeverity.INFO
        if status == "FAILED":
            severity = LogSeverity.ERROR
        elif status == "WARNING":
            severity = LogSeverity.WARNING
            
        entry = DeploymentLogEntry(
            deployment_id=deployment_id,
            step=step,
            status=status,
            message=message,
            duration_seconds=duration_seconds,
            metadata=metadata or {},
        )
        
        return await self.log(
            message=message,
            severity=severity,
            log_name=self.DEPLOYMENT_LOG,
            labels={
                "deployment_id": deployment_id,
                "step": step,
                "status": status,
            },
            json_payload=entry.to_dict(),
        )
    
    async def log_error(
        self,
        deployment_id: str,
        error: str,
        step: str = None,
        stack_trace: str = None,
    ) -> bool:
        """
        Log an error during deployment.
        
        Args:
            deployment_id: Deployment ID
            error: Error message
            step: Optional step where error occurred
            stack_trace: Optional stack trace
            
        Returns:
            True if logged successfully
        """
        return await self.log(
            message=f"Deployment error: {error}",
            severity=LogSeverity.ERROR,
            log_name=self.DEPLOYMENT_LOG,
            labels={
                "deployment_id": deployment_id,
                "step": step or "UNKNOWN",
                "status": "ERROR",
            },
            json_payload={
                "deployment_id": deployment_id,
                "error": error,
                "step": step,
                "stack_trace": stack_trace,
            },
        )
    
    async def get_deployment_logs(
        self,
        deployment_id: str,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Get logs for a specific deployment.
        
        Args:
            deployment_id: Deployment ID
            limit: Maximum number of entries
            
        Returns:
            List of log entries
        """
        def _query_logs():
            client = self._get_client()
            
            filter_str = (
                f'logName="projects/{self.project_id}/logs/{self.DEPLOYMENT_LOG}" '
                f'AND labels.deployment_id="{deployment_id}"'
            )
            
            entries = []
            for entry in client.list_entries(filter_=filter_str, max_results=limit):
                entries.append({
                    "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                    "severity": entry.severity,
                    "message": entry.payload.get("message") if isinstance(entry.payload, dict) else str(entry.payload),
                    "step": entry.labels.get("step"),
                    "status": entry.labels.get("status"),
                    "payload": entry.payload if isinstance(entry.payload, dict) else {},
                })
            return entries
            
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _query_logs)
        except Exception as e:
            self.local_logger.error(f"Failed to query logs: {e}")
            return []
    
    async def get_recent_deployments(
        self,
        hours: int = 24,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get recent deployment summaries.
        
        Args:
            hours: Look back period in hours
            limit: Maximum number of deployments
            
        Returns:
            List of deployment summaries
        """
        def _query_deployments():
            client = self._get_client()
            
            since = (datetime.utcnow() - timedelta(hours=hours)).isoformat() + "Z"
            
            filter_str = (
                f'logName="projects/{self.project_id}/logs/{self.DEPLOYMENT_LOG}" '
                f'AND timestamp>="{since}" '
                f'AND labels.step="PIPELINE_COMPLETE"'
            )
            
            deployments = []
            seen_ids = set()
            
            for entry in client.list_entries(filter_=filter_str, max_results=limit * 2, order_by="timestamp desc"):
                deployment_id = entry.labels.get("deployment_id")
                if deployment_id and deployment_id not in seen_ids:
                    seen_ids.add(deployment_id)
                    
                    payload = entry.payload if isinstance(entry.payload, dict) else {}
                    
                    deployments.append({
                        "deployment_id": deployment_id,
                        "timestamp": entry.timestamp.isoformat() if entry.timestamp else None,
                        "status": entry.labels.get("status"),
                        "service_url": payload.get("service_url"),
                        "duration_seconds": payload.get("duration_seconds"),
                    })
                    
                    if len(deployments) >= limit:
                        break
                        
            return deployments
            
        try:
            return await asyncio.get_event_loop().run_in_executor(None, _query_deployments)
        except Exception as e:
            self.local_logger.error(f"Failed to query deployments: {e}")
            return []
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check if prerequisites are met."""
        prerequisites = {
            "project_id": bool(self.project_id),
            "sdk_installed": False,
            "authenticated": False,
        }
        
        try:
            from google.cloud import logging as cloud_logging
            prerequisites["sdk_installed"] = True
        except ImportError:
            pass
            
        try:
            self._get_client()
            prerequisites["authenticated"] = True
        except Exception:
            pass
            
        return prerequisites


class PipelineLogger:
    """
    Convenience wrapper for logging pipeline operations.
    
    Usage:
        logger = PipelineLogger(deployment_id="deploy-123")
        
        await logger.start_step("BUILD")
        # ... do build ...
        await logger.end_step("BUILD", success=True, message="Build complete")
    """
    
    def __init__(
        self,
        deployment_id: str,
        project_id: str = None,
    ):
        """
        Initialize pipeline logger.
        
        Args:
            deployment_id: Unique deployment ID
            project_id: GCP project ID
        """
        self.deployment_id = deployment_id
        self.cloud_logger = CloudLoggingClient(project_id=project_id)
        self.local_logger = get_logger("PipelineLogger")
        self.step_start_times: Dict[str, datetime] = {}
        
    async def start_step(self, step: str, message: str = None) -> None:
        """Log the start of a pipeline step."""
        self.step_start_times[step] = datetime.now()
        
        msg = message or f"Starting step: {step}"
        self.local_logger.info(f"[{self.deployment_id}] {msg}")
        
        await self.cloud_logger.log_deployment_step(
            deployment_id=self.deployment_id,
            step=step,
            status="STARTED",
            message=msg,
        )
    
    async def end_step(
        self,
        step: str,
        success: bool,
        message: str = None,
        metadata: Dict[str, Any] = None,
    ) -> None:
        """Log the end of a pipeline step."""
        duration = 0
        if step in self.step_start_times:
            duration = (datetime.now() - self.step_start_times[step]).total_seconds()
            
        status = "SUCCESS" if success else "FAILED"
        msg = message or f"Step {step} {status.lower()}"
        
        if success:
            self.local_logger.info(f"[{self.deployment_id}] {msg} ({duration:.1f}s)")
        else:
            self.local_logger.error(f"[{self.deployment_id}] {msg}")
            
        await self.cloud_logger.log_deployment_step(
            deployment_id=self.deployment_id,
            step=step,
            status=status,
            message=msg,
            duration_seconds=duration,
            metadata=metadata,
        )
    
    async def log_error(self, error: str, step: str = None) -> None:
        """Log an error."""
        self.local_logger.error(f"[{self.deployment_id}] Error: {error}")
        await self.cloud_logger.log_error(
            deployment_id=self.deployment_id,
            error=error,
            step=step,
        )
    
    async def complete_pipeline(
        self,
        success: bool,
        service_url: str = None,
        total_duration: float = 0,
    ) -> None:
        """Log pipeline completion."""
        status = "SUCCESS" if success else "FAILED"
        message = f"Pipeline {status.lower()}"
        if service_url:
            message += f": {service_url}"
            
        self.local_logger.info(f"[{self.deployment_id}] {message}")
        
        await self.cloud_logger.log_deployment_step(
            deployment_id=self.deployment_id,
            step="PIPELINE_COMPLETE",
            status=status,
            message=message,
            duration_seconds=total_duration,
            metadata={
                "service_url": service_url,
            },
        )

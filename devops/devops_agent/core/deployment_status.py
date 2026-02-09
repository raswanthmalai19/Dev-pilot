"""
Deployment Status Manager - Real-time deployment status updates.

Provides:
- Status callbacks for pipeline steps
- Webhook notifications
- Event-driven status updates
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Awaitable
import asyncio
import json

from ..core.logger import get_logger


class DeploymentPhase(Enum):
    """Deployment phases."""
    PENDING = "pending"
    VALIDATING = "validating"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    GENERATING_CONFIGS = "generating_configs"
    BUILDING = "building"
    PUSHING = "pushing"
    DEPLOYING = "deploying"
    HEALTH_CHECKING = "health_checking"
    ROLLING_BACK = "rolling_back"
    SUCCESS = "success"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class StatusUpdate:
    """A status update event."""
    deployment_id: str
    phase: DeploymentPhase
    timestamp: datetime
    message: str = ""
    progress_percent: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "deployment_id": self.deployment_id,
            "phase": self.phase.value,
            "timestamp": self.timestamp.isoformat(),
            "message": self.message,
            "progress_percent": self.progress_percent,
            "details": self.details,
            "error": self.error,
        }
    
    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


# Type alias for status callback
StatusCallback = Callable[[StatusUpdate], Awaitable[None]]


class DeploymentStatusManager:
    """
    Manages deployment status updates with callbacks and webhooks.
    
    Usage:
        manager = DeploymentStatusManager(deployment_id="dp-xxx")
        
        # Add callback
        async def on_status(update: StatusUpdate):
            print(f"{update.phase}: {update.message}")
        manager.add_callback(on_status)
        
        # Update status
        await manager.update(DeploymentPhase.BUILDING, "Building Docker image...")
    """
    
    # Phase to progress mapping
    PHASE_PROGRESS = {
        DeploymentPhase.PENDING: 0,
        DeploymentPhase.VALIDATING: 5,
        DeploymentPhase.CLONING: 15,
        DeploymentPhase.ANALYZING: 25,
        DeploymentPhase.GENERATING_CONFIGS: 35,
        DeploymentPhase.BUILDING: 50,
        DeploymentPhase.PUSHING: 65,
        DeploymentPhase.DEPLOYING: 80,
        DeploymentPhase.HEALTH_CHECKING: 90,
        DeploymentPhase.SUCCESS: 100,
        DeploymentPhase.FAILED: 100,
        DeploymentPhase.ROLLING_BACK: 95,
        DeploymentPhase.ROLLED_BACK: 100,
    }
    
    def __init__(
        self,
        deployment_id: str,
        webhook_url: str = None,
    ):
        """
        Initialize status manager.
        
        Args:
            deployment_id: Unique deployment identifier
            webhook_url: Optional webhook URL for HTTP notifications
        """
        self.deployment_id = deployment_id
        self.webhook_url = webhook_url
        self.logger = get_logger("DeploymentStatus")
        
        self._callbacks: List[StatusCallback] = []
        self._history: List[StatusUpdate] = []
        self._current_phase = DeploymentPhase.PENDING
        
    @property
    def current_phase(self) -> DeploymentPhase:
        """Get current deployment phase."""
        return self._current_phase
    
    @property
    def history(self) -> List[StatusUpdate]:
        """Get status history."""
        return self._history.copy()
    
    def add_callback(self, callback: StatusCallback) -> None:
        """Add a status update callback."""
        self._callbacks.append(callback)
        
    def remove_callback(self, callback: StatusCallback) -> None:
        """Remove a status update callback."""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
            
    async def update(
        self,
        phase: DeploymentPhase,
        message: str = "",
        details: Dict[str, Any] = None,
        error: str = None,
    ) -> StatusUpdate:
        """
        Update deployment status.
        
        Args:
            phase: New deployment phase
            message: Status message
            details: Additional details
            error: Error message if failed
            
        Returns:
            StatusUpdate that was sent
        """
        self._current_phase = phase
        
        update = StatusUpdate(
            deployment_id=self.deployment_id,
            phase=phase,
            timestamp=datetime.now(),
            message=message,
            progress_percent=self.PHASE_PROGRESS.get(phase, 0),
            details=details or {},
            error=error,
        )
        
        self._history.append(update)
        
        # Log
        log_msg = f"[{phase.value}] {message}"
        if error:
            self.logger.error(log_msg)
        else:
            self.logger.info(log_msg)
        
        # Notify callbacks
        await self._notify_callbacks(update)
        
        # Send webhook
        if self.webhook_url:
            await self._send_webhook(update)
            
        return update
    
    async def _notify_callbacks(self, update: StatusUpdate) -> None:
        """Notify all registered callbacks."""
        for callback in self._callbacks:
            try:
                await callback(update)
            except Exception as e:
                self.logger.warning(f"Callback error: {e}")
                
    async def _send_webhook(self, update: StatusUpdate) -> None:
        """Send webhook notification."""
        if not self.webhook_url:
            return
            
        try:
            import httpx
            
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.post(
                    self.webhook_url,
                    json=update.to_dict(),
                    headers={"Content-Type": "application/json"},
                )
                
                if response.status_code >= 400:
                    self.logger.warning(
                        f"Webhook failed: {response.status_code}"
                    )
        except Exception as e:
            self.logger.warning(f"Webhook error: {e}")
    
    # Convenience methods for common updates
    async def start(self) -> StatusUpdate:
        """Mark deployment as started."""
        return await self.update(
            DeploymentPhase.PENDING,
            "Deployment started",
        )
    
    async def validating(self, message: str = "Validating preconditions") -> StatusUpdate:
        """Mark validation phase."""
        return await self.update(DeploymentPhase.VALIDATING, message)
    
    async def cloning(self, repo_url: str) -> StatusUpdate:
        """Mark cloning phase."""
        return await self.update(
            DeploymentPhase.CLONING,
            f"Cloning repository",
            details={"repo_url": repo_url},
        )
    
    async def analyzing(self) -> StatusUpdate:
        """Mark analyzing phase."""
        return await self.update(
            DeploymentPhase.ANALYZING,
            "Analyzing project structure",
        )
    
    async def generating_configs(self) -> StatusUpdate:
        """Mark config generation phase."""
        return await self.update(
            DeploymentPhase.GENERATING_CONFIGS,
            "Generating configuration files",
        )
    
    async def building(self, image_name: str) -> StatusUpdate:
        """Mark building phase."""
        return await self.update(
            DeploymentPhase.BUILDING,
            f"Building Docker image: {image_name}",
            details={"image_name": image_name},
        )
    
    async def deploying(self, service_name: str) -> StatusUpdate:
        """Mark deploying phase."""
        return await self.update(
            DeploymentPhase.DEPLOYING,
            f"Deploying to Cloud Run: {service_name}",
            details={"service_name": service_name},
        )
    
    async def health_checking(self, url: str) -> StatusUpdate:
        """Mark health checking phase."""
        return await self.update(
            DeploymentPhase.HEALTH_CHECKING,
            "Running health checks",
            details={"url": url},
        )
    
    async def success(self, service_url: str) -> StatusUpdate:
        """Mark deployment as successful."""
        return await self.update(
            DeploymentPhase.SUCCESS,
            f"Deployment successful!",
            details={"service_url": service_url},
        )
    
    async def failed(self, error: str) -> StatusUpdate:
        """Mark deployment as failed."""
        return await self.update(
            DeploymentPhase.FAILED,
            "Deployment failed",
            error=error,
        )
    
    async def rolling_back(self, reason: str) -> StatusUpdate:
        """Mark rollback phase."""
        return await self.update(
            DeploymentPhase.ROLLING_BACK,
            f"Rolling back: {reason}",
        )
    
    async def rolled_back(self, revision: str) -> StatusUpdate:
        """Mark rolled back."""
        return await self.update(
            DeploymentPhase.ROLLED_BACK,
            f"Rolled back to: {revision}",
            details={"revision": revision},
        )


# Convenience function to create a status manager with console output
def create_console_status_manager(deployment_id: str) -> DeploymentStatusManager:
    """Create a status manager that prints to console."""
    from rich.console import Console
    from rich.panel import Panel
    
    console = Console()
    manager = DeploymentStatusManager(deployment_id)
    
    async def console_callback(update: StatusUpdate):
        phase_emoji = {
            DeploymentPhase.PENDING: "⏳",
            DeploymentPhase.VALIDATING: "🔍",
            DeploymentPhase.CLONING: "📥",
            DeploymentPhase.ANALYZING: "🔬",
            DeploymentPhase.GENERATING_CONFIGS: "⚙️",
            DeploymentPhase.BUILDING: "🔨",
            DeploymentPhase.PUSHING: "📤",
            DeploymentPhase.DEPLOYING: "🚀",
            DeploymentPhase.HEALTH_CHECKING: "💓",
            DeploymentPhase.SUCCESS: "✅",
            DeploymentPhase.FAILED: "❌",
            DeploymentPhase.ROLLING_BACK: "⏪",
            DeploymentPhase.ROLLED_BACK: "🔄",
        }
        
        emoji = phase_emoji.get(update.phase, "▶️")
        console.print(f"  {emoji} [{update.progress_percent:3d}%] {update.message}")
        
    manager.add_callback(console_callback)
    return manager

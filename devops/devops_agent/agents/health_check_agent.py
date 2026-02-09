"""
Health Check Agent - Validates deployment health.

Responsible for:
- Calling service health endpoints
- Verifying HTTP 200 response
- Checking service boot success
- Triggering rollback if unhealthy
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

from .base_agent import BaseAgent
from ..core.health_checker import HealthChecker, HealthCheckResult
from ..core.logger import get_logger


@dataclass
class HealthCheckAttempt:
    """Record of a health check attempt."""
    attempt_number: int
    timestamp: datetime
    success: bool
    status_code: Optional[int] = None
    response_time_ms: float = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "attempt_number": self.attempt_number,
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "error": self.error,
        }


@dataclass
class HealthCheckAgentResult:
    """Result of health check agent."""
    healthy: bool
    service_url: Optional[str] = None
    health_endpoint: Optional[str] = None
    attempts: List[HealthCheckAttempt] = field(default_factory=list)
    total_duration_seconds: float = 0
    requires_rollback: bool = False
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "healthy": self.healthy,
            "service_url": self.service_url,
            "health_endpoint": self.health_endpoint,
            "attempts": [a.to_dict() for a in self.attempts],
            "total_duration_seconds": self.total_duration_seconds,
            "requires_rollback": self.requires_rollback,
            "errors": self.errors,
        }


class HealthCheckAgent(BaseAgent):
    """
    Health Check Agent for validating deployment health.
    
    Features:
    - Performs HTTP health checks
    - Validates response codes
    - Supports custom health endpoints
    - Determines if rollback is needed
    
    Usage:
        agent = HealthCheckAgent()
        result = await agent.run(
            service_url="https://my-app-xxx.run.app",
            health_endpoint="/health",
        )
        
        if not result.healthy:
            print("Service unhealthy, rollback required")
    """
    
    # Default health check configuration
    DEFAULT_HEALTH_ENDPOINT = "/health"
    DEFAULT_MAX_RETRIES = 5
    DEFAULT_RETRY_DELAY = 5.0
    DEFAULT_TIMEOUT = 30.0
    
    def __init__(
        self,
        working_dir=None,
        gemini_client=None,
        max_retries: int = None,
        retry_delay: float = None,
    ):
        """
        Initialize the Health Check Agent.
        
        Args:
            working_dir: Working directory
            gemini_client: Gemini client
            max_retries: Maximum health check retries
            retry_delay: Delay between retries in seconds
        """
        super().__init__(working_dir, gemini_client)
        self.max_retries = max_retries or self.DEFAULT_MAX_RETRIES
        self.retry_delay = retry_delay or self.DEFAULT_RETRY_DELAY
        self.health_checker = HealthChecker()
        self.logger = get_logger("HealthCheckAgent")
        
    def _get_system_instruction(self) -> str:
        """Get system instruction for the agent."""
        return "You are an expert at diagnosing service health issues and deployment problems."
    
    async def run(
        self,
        service_url: str,
        health_endpoint: str = None,
        expected_status_codes: List[int] = None,
        custom_headers: Dict[str, str] = None,
    ) -> HealthCheckAgentResult:
        """
        Perform health check on a deployed service.
        
        Args:
            service_url: Base URL of the service
            health_endpoint: Health check endpoint (default: /health)
            expected_status_codes: Valid status codes (default: [200])
            custom_headers: Headers to include in request
            
        Returns:
            HealthCheckAgentResult with health status
        """
        result = HealthCheckAgentResult(healthy=False)
        result.service_url = service_url
        result.health_endpoint = health_endpoint or self.DEFAULT_HEALTH_ENDPOINT
        started_at = datetime.now()
        
        # Build full health URL
        health_url = service_url.rstrip("/") + result.health_endpoint
        expected_codes = expected_status_codes or [200, 201, 204]
        
        self.logger.info("=" * 60)
        self.logger.info("HEALTH CHECK AGENT")
        self.logger.info("=" * 60)
        self.logger.info(f"Service: {service_url}")
        self.logger.info(f"Health endpoint: {health_url}")
        self.logger.info(f"Max retries: {self.max_retries}")
        
        # Perform health checks with retries
        for attempt_number in range(1, self.max_retries + 1):
            self.logger.info(f"Health check attempt {attempt_number}/{self.max_retries}")
            
            attempt = HealthCheckAttempt(
                attempt_number=attempt_number,
                timestamp=datetime.now(),
                success=False,
            )
            
            try:
                check_result = await self._perform_check(
                    health_url,
                    expected_codes,
                    custom_headers,
                )
                
                attempt.status_code = check_result.get("status_code")
                attempt.response_time_ms = check_result.get("response_time_ms", 0)
                
                if check_result.get("success"):
                    attempt.success = True
                    result.healthy = True
                    result.attempts.append(attempt)
                    
                    self.logger.info(f"✅ Health check passed (HTTP {attempt.status_code})")
                    break
                else:
                    attempt.error = check_result.get("error", "Unexpected status code")
                    result.attempts.append(attempt)
                    
                    self.logger.warning(f"Health check failed: {attempt.error}")
                    
            except Exception as e:
                attempt.error = str(e)
                result.attempts.append(attempt)
                self.logger.warning(f"Health check error: {e}")
                
            # Wait before retry (unless last attempt)
            if attempt_number < self.max_retries:
                import asyncio
                await asyncio.sleep(self.retry_delay)
                
        # Final result
        result.total_duration_seconds = (datetime.now() - started_at).total_seconds()
        
        if result.healthy:
            self.logger.info(f"✅ SERVICE HEALTHY in {result.total_duration_seconds:.1f}s")
        else:
            result.requires_rollback = True
            result.errors.append(f"Service unhealthy after {self.max_retries} attempts")
            self.logger.error(f"❌ SERVICE UNHEALTHY - Rollback required")
            
        self.logger.info("=" * 60)
        
        return result
    
    async def _perform_check(
        self,
        url: str,
        expected_codes: List[int],
        headers: Dict[str, str] = None,
    ) -> Dict[str, Any]:
        """Perform a single health check."""
        import httpx
        import time
        
        try:
            start_time = time.time()
            
            async with httpx.AsyncClient(timeout=self.DEFAULT_TIMEOUT) as client:
                response = await client.get(url, headers=headers or {})
                
            response_time = (time.time() - start_time) * 1000  # Convert to ms
            
            if response.status_code in expected_codes:
                return {
                    "success": True,
                    "status_code": response.status_code,
                    "response_time_ms": response_time,
                }
            else:
                return {
                    "success": False,
                    "status_code": response.status_code,
                    "response_time_ms": response_time,
                    "error": f"Unexpected status code: {response.status_code}",
                }
                
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "Request timeout",
            }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": "Connection failed",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
    
    async def check_multiple_endpoints(
        self,
        service_url: str,
        endpoints: List[str],
    ) -> Dict[str, HealthCheckAgentResult]:
        """Check health of multiple endpoints."""
        results = {}
        
        for endpoint in endpoints:
            result = await self.run(service_url, endpoint)
            results[endpoint] = result
            
        return results
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check prerequisites for the agent."""
        return {
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "ready": True,
        }


# Convenience function
async def verify_deployment_health(
    service_url: str,
    health_endpoint: str = "/health",
    max_retries: int = 5,
) -> HealthCheckAgentResult:
    """
    Verify deployment health.
    
    Args:
        service_url: Service URL
        health_endpoint: Health check endpoint
        max_retries: Maximum retries
        
    Returns:
        HealthCheckAgentResult with health status
    """
    agent = HealthCheckAgent(max_retries=max_retries)
    return await agent.run(service_url, health_endpoint)

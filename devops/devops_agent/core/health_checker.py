"""
Health Checker - Deployment verification via HTTP health checks.

Provides:
- HTTP health check client
- Retry with exponential backoff
- Response validation
- Readiness/liveness probes
"""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any, List

import httpx

from ..core.logger import get_logger


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    healthy: bool
    status_code: Optional[int] = None
    response_time_ms: float = 0
    message: str = ""
    checks_performed: int = 0
    last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "healthy": self.healthy,
            "status_code": self.status_code,
            "response_time_ms": self.response_time_ms,
            "message": self.message,
            "checks_performed": self.checks_performed,
        }


class HealthChecker:
    """
    HTTP health check client with retry and verification.
    
    Usage:
        checker = HealthChecker()
        result = await checker.check(
            url="https://my-service.run.app/health",
            max_retries=5,
        )
        if result.healthy:
            print("Deployment verified!")
    """
    
    def __init__(
        self,
        timeout: float = 10.0,
        expected_status_codes: List[int] = None,
        expected_json_fields: List[str] = None,
    ):
        """
        Initialize health checker.
        
        Args:
            timeout: HTTP request timeout in seconds
            expected_status_codes: Status codes that indicate healthy (default: [200])
            expected_json_fields: JSON fields that must be present in response
        """
        self.timeout = timeout
        self.expected_status_codes = expected_status_codes or [200]
        self.expected_json_fields = expected_json_fields or []
        self.logger = get_logger("HealthChecker")
    
    async def check(
        self,
        url: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
        max_delay: float = 60.0,
        headers: Dict[str, str] = None,
    ) -> HealthCheckResult:
        """
        Perform health check with retries.
        
        Args:
            url: URL to check
            max_retries: Maximum number of retry attempts
            retry_delay: Initial delay between retries (seconds)
            max_delay: Maximum delay between retries
            headers: Additional headers to send
            
        Returns:
            HealthCheckResult
        """
        result = HealthCheckResult(healthy=False)
        
        for attempt in range(1, max_retries + 1):
            result.checks_performed = attempt
            
            self.logger.info(f"Health check attempt {attempt}/{max_retries}: {url}")
            
            try:
                check_result = await self._do_check(url, headers)
                
                if check_result.healthy:
                    self.logger.info(
                        f"Health check passed in {check_result.response_time_ms:.0f}ms"
                    )
                    return check_result
                
                result = check_result
                
            except Exception as e:
                result.last_error = str(e)
                self.logger.warning(f"Health check failed: {e}")
            
            # Wait before retry (exponential backoff)
            if attempt < max_retries:
                delay = min(retry_delay * (2 ** (attempt - 1)), max_delay)
                self.logger.info(f"Retrying in {delay:.1f}s...")
                await asyncio.sleep(delay)
        
        result.message = f"Health check failed after {max_retries} attempts"
        self.logger.error(result.message)
        return result
    
    async def _do_check(
        self,
        url: str,
        headers: Dict[str, str] = None,
    ) -> HealthCheckResult:
        """Perform a single health check."""
        result = HealthCheckResult(healthy=False)
        
        start_time = datetime.now()
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(url, headers=headers or {})
            
            result.status_code = response.status_code
            result.response_time_ms = (
                datetime.now() - start_time
            ).total_seconds() * 1000
            
            # Check status code
            if response.status_code not in self.expected_status_codes:
                result.message = f"Unexpected status code: {response.status_code}"
                return result
            
            # Check JSON fields if specified
            if self.expected_json_fields:
                try:
                    data = response.json()
                    missing = [
                        field for field in self.expected_json_fields
                        if field not in data
                    ]
                    if missing:
                        result.message = f"Missing JSON fields: {missing}"
                        return result
                except Exception:
                    result.message = "Expected JSON response"
                    return result
            
            result.healthy = True
            result.message = "OK"
            return result
    
    async def wait_for_ready(
        self,
        url: str,
        timeout: float = 300,
        poll_interval: float = 5.0,
        headers: Dict[str, str] = None,
    ) -> HealthCheckResult:
        """
        Wait for a service to become ready.
        
        Args:
            url: URL to check
            timeout: Maximum time to wait (seconds)
            poll_interval: Time between checks
            headers: Additional headers
            
        Returns:
            HealthCheckResult when healthy or timeout
        """
        self.logger.info(f"Waiting for service to be ready: {url}")
        
        start_time = datetime.now()
        attempts = 0
        last_result = HealthCheckResult(healthy=False)
        
        while (datetime.now() - start_time).total_seconds() < timeout:
            attempts += 1
            
            try:
                result = await self._do_check(url, headers)
                result.checks_performed = attempts
                
                if result.healthy:
                    self.logger.info(
                        f"Service ready after {attempts} checks "
                        f"({(datetime.now() - start_time).total_seconds():.1f}s)"
                    )
                    return result
                
                last_result = result
                
            except httpx.ConnectError:
                last_result.last_error = "Connection refused"
            except Exception as e:
                last_result.last_error = str(e)
            
            await asyncio.sleep(poll_interval)
        
        last_result.checks_performed = attempts
        last_result.message = f"Timeout after {timeout}s"
        self.logger.error(f"Service not ready after {timeout}s")
        return last_result


class DeploymentVerifier:
    """
    Verifies a deployment is working correctly.
    
    Combines health checks with additional validations.
    """
    
    def __init__(self):
        self.logger = get_logger("DeploymentVerifier")
        self.health_checker = HealthChecker()
    
    async def verify(
        self,
        base_url: str,
        health_path: str = "/health",
        additional_checks: List[Dict[str, Any]] = None,
        max_retries: int = 5,
    ) -> Dict[str, Any]:
        """
        Verify a deployment.
        
        Args:
            base_url: Base URL of the deployed service
            health_path: Health endpoint path
            additional_checks: Additional endpoints to check
            max_retries: Max retries for health check
            
        Returns:
            Verification result dict
        """
        result = {
            "success": False,
            "url": base_url,
            "checks": [],
            "errors": [],
        }
        
        # Primary health check
        health_url = f"{base_url.rstrip('/')}{health_path}"
        self.logger.info(f"Verifying deployment at: {health_url}")
        
        health_result = await self.health_checker.check(
            url=health_url,
            max_retries=max_retries,
        )
        
        result["checks"].append({
            "name": "health",
            "url": health_url,
            "passed": health_result.healthy,
            "response_time_ms": health_result.response_time_ms,
        })
        
        if not health_result.healthy:
            result["errors"].append(
                f"Health check failed: {health_result.last_error or health_result.message}"
            )
            return result
        
        # Additional checks
        all_passed = True
        for check in (additional_checks or []):
            check_url = f"{base_url.rstrip('/')}{check.get('path', '/')}"
            check_result = await self.health_checker.check(
                url=check_url,
                max_retries=1,
            )
            
            result["checks"].append({
                "name": check.get("name", check.get("path")),
                "url": check_url,
                "passed": check_result.healthy,
                "response_time_ms": check_result.response_time_ms,
            })
            
            if not check_result.healthy:
                all_passed = False
                result["errors"].append(
                    f"Check '{check.get('name')}' failed"
                )
        
        result["success"] = all_passed
        
        if result["success"]:
            self.logger.info("Deployment verification passed!")
        else:
            self.logger.warning("Deployment verification failed")
        
        return result


# Convenience function
async def verify_deployment(
    url: str,
    health_path: str = "/health",
    timeout: float = 300,
) -> bool:
    """
    Verify a deployment is healthy.
    
    Args:
        url: Base URL of the service
        health_path: Health endpoint path
        timeout: Maximum time to wait
        
    Returns:
        True if deployment is healthy
    """
    checker = HealthChecker()
    result = await checker.wait_for_ready(
        url=f"{url.rstrip('/')}{health_path}",
        timeout=timeout,
    )
    return result.healthy

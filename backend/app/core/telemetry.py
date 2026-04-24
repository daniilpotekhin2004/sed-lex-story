"""
Telemetry tracking utilities for logging events and requests.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def track_event(
    event_name: str,
    user_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Track an application event for telemetry purposes.
    
    This is a lightweight wrapper that logs events. In production, this could
    be extended to send events to analytics services, metrics systems, etc.
    
    Args:
        event_name: Name of the event (e.g., "generation_job_created")
        user_id: Optional user ID associated with the event
        metadata: Optional dictionary of additional event data
    """
    try:
        log_data = {
            "event": event_name,
            "user_id": user_id,
            **(metadata or {}),
        }
        logger.info(f"Telemetry event: {event_name}", extra=log_data)
    except Exception as e:
        # Never let telemetry break the application
        logger.warning(f"Failed to track event {event_name}: {e}")


def log_request(
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
) -> None:
    """
    Log an HTTP request for monitoring and analytics.
    
    Args:
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP status code
        duration_ms: Request duration in milliseconds
    """
    try:
        logger.info(
            f"{method} {path} {status_code} {duration_ms:.2f}ms",
            extra={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
    except Exception as e:
        # Never let logging break the application
        logger.warning(f"Failed to log request: {e}")

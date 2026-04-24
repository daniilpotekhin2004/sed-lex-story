from __future__ import annotations

import socket
import subprocess
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import anyio
import httpx
from celery import Celery
from kombu.exceptions import OperationalError

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.schemas.ops import ServiceStatus


class OpsService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.compose_file = self._find_compose_file()
        self.compose_available = self.compose_file is not None and self._has_docker()

    def list_services(self) -> List[ServiceStatus]:
        checks = self._run_checks()
        return [checks[key] for key in checks]

    async def control_service(self, service_id: str, action: str) -> Tuple[bool, str, str | None]:
        """
        Control a service via docker-compose.
        
        Root cause: Services not restarting when buttons clicked
        Solution: Proper command execution with error handling and logging
        """
        if not self.compose_available:
            return False, "", "Docker Compose not available. Install docker and ensure docker-compose.yml exists."
        
        if action not in {"start", "restart", "stop"}:
            return False, "", f"Invalid action: {action}. Must be start, restart, or stop."
        
        command = self._build_compose_command(service_id, action)
        if command is None:
            return False, "", f"Service '{service_id}' not found in compose configuration."
        
        # Log the command being executed
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[OPS] Executing: {' '.join(command)}")
        
        result = await self._run_command(command)
        output = (result.stdout or "") + (result.stderr or "")
        
        if result.returncode != 0:
            logger.error(f"[OPS] Command failed with code {result.returncode}: {output}")
            return False, " ".join(command), output.strip() or "Command failed."
        
        logger.info(f"[OPS] Command succeeded: {output}")
        return True, " ".join(command), output.strip() or None

    def _run_checks(self) -> Dict[str, ServiceStatus]:
        now = datetime.now(timezone.utc)
        checks: Dict[str, ServiceStatus] = {}

        backend_url = self._build_backend_url()
        backend_status, backend_details = self._check_http(backend_url, ["/health"])
        checks["backend"] = ServiceStatus(
            id="backend",
            name="Backend API",
            status=backend_status,
            url=backend_url,
            host=urlparse(backend_url).hostname,
            port=urlparse(backend_url).port,
            details=backend_details,
            actions=self._available_actions("backend"),
            controllable=self._can_control("backend"),
            last_checked_at=now,
        )

        redis_host, redis_port = self._parse_host_port(self.settings.redis_url, default_port=6379)
        redis_ok = self._check_socket(redis_host, redis_port)
        checks["redis"] = ServiceStatus(
            id="redis",
            name="Redis",
            status="ok" if redis_ok else "down",
            url=self.settings.redis_url,
            host=redis_host,
            port=redis_port,
            details={"reachable": redis_ok},
            actions=self._available_actions("redis"),
            controllable=self._can_control("redis"),
            last_checked_at=now,
        )

        celery_status, celery_details = self._check_celery(celery_app)
        checks["celery"] = ServiceStatus(
            id="celery",
            name="Celery Worker",
            status=celery_status,
            url=self.settings.redis_url,
            host=redis_host,
            port=redis_port,
            details=celery_details,
            actions=self._available_actions("celery"),
            controllable=self._can_control("celery"),
            last_checked_at=now,
        )

        # Always read SD_API_URL fresh from environment (bypass settings cache)
        import os
        sd_url = os.environ.get("SD_API_URL", "http://localhost:7860").strip().rstrip("/")
        sd_mock = os.environ.get("SD_MOCK_MODE", "false").strip().lower() == "true"
        sd_status, sd_details = self._check_http(sd_url, ["/sdapi/v1/options", "/docs", "/openapi.json"])
        checks["sd"] = ServiceStatus(
            id="sd",
            name="Stable Diffusion",
            status=sd_status,
            url=sd_url,
            host=urlparse(sd_url).hostname,
            port=urlparse(sd_url).port,
            details={"mock_mode": sd_mock, **sd_details},
            actions=self._available_actions("sd"),
            controllable=self._can_control("sd"),
            last_checked_at=now,
        )

        return checks

    def _build_backend_url(self) -> str:
        host = self.settings.backend_host
        if host in {"0.0.0.0", "127.0.0.1"}:
            host = "localhost"
        return f"http://{host}:{self.settings.backend_port}"

    def _check_http(self, base_url: str, paths: List[str]) -> Tuple[str, dict]:
        details = {"checked": [], "status_code": None}
        try:
            with httpx.Client(timeout=1.5) as client:
                for path in paths:
                    url = f"{base_url.rstrip('/')}{path}"
                    details["checked"].append(url)
                    response = client.get(url)
                    details["status_code"] = response.status_code
                    if response.status_code < 500:
                        return "ok", details
        except httpx.HTTPError as exc:
            details["error"] = str(exc)
        return "down", details

    def _check_socket(self, host: str | None, port: int | None) -> bool:
        if not host or not port:
            return False
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            return False

    def _check_celery(self, app: Celery) -> Tuple[str, dict]:
        details = {"workers": [], "reachable": False}
        try:
            inspector = app.control.inspect(timeout=1.0)
            response = inspector.ping() or {}
            details["workers"] = list(response.keys())
            details["reachable"] = True
            if response:
                return "ok", details
            return "degraded", details
        except OperationalError as exc:
            details["error"] = str(exc)
            return "down", details
        except Exception as exc:  # pragma: no cover - defensive
            details["error"] = str(exc)
            return "unknown", details

    def _parse_host_port(self, url: str, default_port: int) -> Tuple[str | None, int | None]:
        parsed = urlparse(url)
        return parsed.hostname, parsed.port or default_port

    def _available_actions(self, service_id: str) -> List[str]:
        if not self._can_control(service_id):
            return []
        return ["start", "restart", "stop"]

    def _can_control(self, service_id: str) -> bool:
        if not self.compose_available:
            return False
        return service_id in self._compose_service_map()

    def _compose_service_map(self) -> Dict[str, str]:
        return {
            "backend": "backend",
            "celery": "worker",
            "redis": "redis",
            "sd": "sd-api",
        }

    def _build_compose_command(self, service_id: str, action: str) -> Optional[List[str]]:
        if not self.compose_available or action not in {"start", "restart", "stop"}:
            return None
        service_name = self._compose_service_map().get(service_id)
        if not service_name:
            return None
        compose_file = str(self.compose_file)
        if action == "start":
            return ["docker", "compose", "-f", compose_file, "up", "-d", service_name]
        if action == "restart":
            return ["docker", "compose", "-f", compose_file, "restart", service_name]
        if action == "stop":
            return ["docker", "compose", "-f", compose_file, "stop", service_name]
        return None

    async def _run_command(self, command: List[str]) -> subprocess.CompletedProcess[str]:
        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(command, capture_output=True, text=True)

        return await anyio.to_thread.run_sync(_run)

    def _find_compose_file(self) -> Optional[Path]:
        current = Path(__file__).resolve()
        for parent in current.parents:
            compose = parent / "docker-compose.yml"
            if compose.exists():
                return compose
        return None

    def _has_docker(self) -> bool:
        return shutil.which("docker") is not None

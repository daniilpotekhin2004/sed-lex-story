from __future__ import annotations

import base64
import datetime as dt
import importlib.util
import json
import logging
import os
import random
import shutil
import time
import uuid
from urllib.parse import urlsplit
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Optional, Union
import requests
import httpx

from app.core.config import get_settings
from app.infra.sd_client import BaseSdClient
from app.infra.workflow_params import WorkflowParams
from app.utils.sd_tokens import extract_lora_tokens, merge_loras
from app.infra.comfy.workflow_manager import WorkflowManager
from app.infra.comfy.workflow_adapter import QwenWorkflowAdapter

from fastapi import HTTPException


class ComfySdClient(BaseSdClient):
    """HTTP client for ComfyUI workflow-based generation (SD 3.5)."""

    # `alwayson_scripts` is supported in a limited, Comfy-native way: we only interpret
    # A1111-style ControlNet/IP-Adapter payloads when used with the mixed workflow set.
    capabilities = {
        "txt2img",
        "img2img",
        "options",
        "models",
        "vae",
        "samplers",
        "schedulers",
        "loras",
        "alwayson_scripts",
    }

    def __init__(self, base_url: str, *, timeout_s: int = 300, headers: Optional[dict] = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.logger = logging.getLogger(__name__)
        self.settings = get_settings()
        self._options_override: dict[str, str] = {}
        self._checkpoint_models_cache: Optional[List[str]] = None
        self._unet_models_cache: Optional[List[str]] = None
        self._vae_cache: Optional[List[str]] = None
        self._sampler_cache: Optional[List[str]] = None
        self._scheduler_cache: Optional[List[str]] = None
        self._lora_cache: Optional[List[str]] = None
        self._object_info_index_cache: Optional[dict] = None
        
        # Root cause: Cloud API doesn't support all object_info queries
        # Solution: Detect cloud API by URL and skip unsupported queries
        self._is_cloud = "cloud.comfy.org" in self.base_url.lower()
        self._headers = headers or {}
        self._workflow_manager = WorkflowManager()
        self._ensure_comfy_input_dir()

    def _ensure_comfy_input_dir(self) -> None:
        input_dir = Path(self.settings.comfyui_path) / "input"
        if input_dir.exists():
            return
        try:
            input_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            self.logger.warning("Failed to create ComfyUI input dir %s: %s", input_dir, exc)

    def _get_object_info_index(self) -> dict:
        if self._object_info_index_cache is None:
            self._object_info_index_cache = self._get_json("/object_info")
        return self._object_info_index_cache

    def _has_node_type(self, node_type: str) -> bool:
        try:
            return node_type in self._get_object_info_index()
        except Exception as exc:
            self.logger.warning("Failed to fetch ComfyUI object_info: %s", exc)
            return False

    def _supports_controlnet_workflow(self) -> bool:
        required = {"IPAdapterApply", "IPAdapterModelLoader", "ControlNetLoader", "ControlNetApplyAdvanced"}
        missing = [node for node in required if not self._has_node_type(node)]
        if missing:
            self.logger.warning("ComfyUI missing nodes for mixed_cn_ipadapter workflow: %s", ", ".join(missing))
            return False
        return True

    def _check_comfyui_connection(self) -> bool:
        """Check if ComfyUI server is accessible."""
        try:
            self._get_json("/object_info")
            return True
        except Exception as exc:
            self.logger.error("ComfyUI connection check failed: %s", exc)
            return False
    
    def _workflow_dir(self) -> Path:
        """Expose ComfyUI workflow directory for custom callers."""
        return self._workflow_manager.get_workflow_dir()
    
    def workflow_dir(self) -> Path:
        """Expose ComfyUI workflow directory for custom callers."""
        return self._workflow_dir()

    def load_workflow(self, path: str, *, output_nodes: Optional[list[str]] = None) -> tuple[dict, list[str]]:
        """Load a workflow file (simple or UI export) and return (workflow, output_nodes)."""
        return self._workflow_manager.load_workflow(path, output_nodes=output_nodes)

    def _load_workflow_template(
        self,
        kind: str,
        *,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> tuple[dict, list[str]]:
        """Load a workflow template using WorkflowManager."""
        return self._workflow_manager.load_workflow_template(
            kind,
            workflow_set=workflow_set,
            workflow_task=workflow_task,
        )

    def _http_client(self) -> httpx.Client:
        return httpx.Client(timeout=self.timeout_s, headers=self._headers, follow_redirects=True)

    def _redact_headers(self, headers: dict) -> dict:
        redacted: dict = {}
        for key, value in (headers or {}).items():
            lowered = str(key).lower()
            if lowered in {"authorization", "x-api-key"}:
                raw = "" if value is None else str(value)
                if lowered == "authorization" and raw.lower().startswith("bearer "):
                    redacted[key] = "Bearer ***"
                elif raw.startswith("comfyui-"):
                    redacted[key] = "comfyui-***"
                else:
                    redacted[key] = "***"
            else:
                redacted[key] = value
        return redacted

    def _redact_payload(self, payload: Optional[dict]) -> Optional[dict]:
        if not isinstance(payload, dict):
            return payload
        redacted = deepcopy(payload)
        extra = redacted.get("extra_data")
        if isinstance(extra, dict) and "api_key_comfy_org" in extra:
            extra["api_key_comfy_org"] = "***"
        return redacted

    def _extract_comfy_api_key(self) -> Optional[str]:
        header_pref = (self.settings.sd_comfy_api_key_header or "X-API-Key").strip()
        prefix = (self.settings.sd_comfy_api_key_prefix or "").strip()

        def _clean(value: Optional[str]) -> Optional[str]:
            if value is None:
                return None
            raw = str(value).strip()
            if not raw:
                return None
            if prefix and raw.startswith(prefix):
                raw = raw[len(prefix):].strip()
            if raw.lower().startswith("bearer "):
                raw = raw[7:].strip()
            return raw or None

        for key, value in (self._headers or {}).items():
            if str(key).lower() == header_pref.lower():
                return _clean(value)
        for key, value in (self._headers or {}).items():
            if str(key).lower() == "x-api-key":
                return _clean(value)
        for key, value in (self._headers or {}).items():
            if str(key).lower() == "authorization":
                return _clean(value)
        return None

    def _truncate_text(self, value: Optional[str], limit: int = 20000) -> Optional[str]:
        if value is None:
            return None
        text = str(value)
        if len(text) <= limit:
            return text
        return text[:limit] + "...(truncated)"

    def _cleanup_request_logs(self, log_dir: Path) -> None:
        try:
            retention_days = max(0, int(self.settings.sd_request_log_retention_days))
            max_mb = max(1, int(self.settings.sd_request_log_max_mb))
        except Exception:
            retention_days = 2
            max_mb = 100

        now = dt.datetime.utcnow()
        if retention_days:
            cutoff = now - dt.timedelta(days=retention_days)
            for path in log_dir.glob("comfy_http_error_*.json"):
                try:
                    mtime = dt.datetime.utcfromtimestamp(path.stat().st_mtime)
                    if mtime < cutoff:
                        path.unlink(missing_ok=True)
                except Exception:
                    continue

        max_bytes = max_mb * 1024 * 1024
        files = []
        total = 0
        for path in log_dir.glob("comfy_http_error_*.json"):
            try:
                stat = path.stat()
                files.append((stat.st_mtime, path, stat.st_size))
                total += stat.st_size
            except Exception:
                continue
        if total <= max_bytes:
            return
        files.sort(key=lambda item: item[0])
        for _, path, size in files:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
            total -= size
            if total <= max_bytes:
                break

    def _log_request_failure(
        self,
        *,
        method: str,
        url: str,
        request_json: Optional[dict] = None,
        request_files: Optional[dict] = None,
        response: Optional[httpx.Response] = None,
        error: Optional[Exception] = None,
    ) -> None:
        log_dir = Path(self.settings.sd_request_log_dir)
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            self.logger.warning("Failed to create request log dir: %s", log_dir)
            return

        payload: dict = {
            "timestamp_utc": dt.datetime.utcnow().isoformat() + "Z",
            "method": method,
            "url": url,
            "base_url": self.base_url,
            "is_cloud": self._is_cloud,
            "request_headers": self._redact_headers(self._headers),
            "request_json": self._redact_payload(request_json),
            "request_files": request_files,
        }

        if response is not None:
            payload["response_status"] = response.status_code
            payload["response_headers"] = response.headers
            payload["response_text"] = self._truncate_text(response.text)
        if error is not None:
            payload["error"] = repr(error)

        filename = f"comfy_http_error_{dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex}.json"
        path = log_dir / filename
        try:
            path.write_text(json.dumps(payload, ensure_ascii=True, indent=2, default=str), encoding="utf-8")
            self._cleanup_request_logs(log_dir)
        except Exception as exc:
            self.logger.warning("Failed to write request log %s: %s", path, exc)

    def _resolve_output_path(self, value: str) -> Path:
        raw = value.strip()
        if not raw:
            return Path(raw)
        if len(raw) >= 2 and raw[1] == ":":
            if os.name != "nt":
                drive = raw[0].lower()
                tail = raw[2:].lstrip("\\/").replace("\\", "/")
                mapped = Path("/mnt") / drive / tail
                if mapped.exists():
                    return mapped
            return Path(raw).expanduser()
        path = Path(raw).expanduser()
        if path.is_absolute():
            return path
        base = self.settings.assets_root_path.parent
        return (base / path).resolve()

    def _get_output_root(self) -> Optional[Path]:
        override = (self.settings.sd_comfy_output_dir or "").strip()
        if override:
            return self._resolve_output_path(override)
        env_override = os.environ.get("COMFYUI_OUTPUT_DIR", "").strip()
        if env_override:
            return self._resolve_output_path(env_override)
        env_path = os.environ.get("COMFYUI_PATH", "").strip()
        if env_path:
            return self._resolve_output_path(env_path) / "output"
        return None

    def _read_output_file(self, filename: str, subfolder: str, image_type: str) -> Optional[bytes]:
        output_root = self._get_output_root()
        if not output_root or not filename:
            return None
        if image_type == "temp" and output_root.name == "output":
            output_root = output_root.parent / "temp"

        candidate = Path(filename)
        if not candidate.is_absolute():
            if subfolder:
                subfolder_path = Path(subfolder)
                if candidate.parts[: len(subfolder_path.parts)] != subfolder_path.parts:
                    candidate = subfolder_path / candidate
            candidate = output_root / candidate

        try:
            resolved_root = output_root.resolve()
            resolved_candidate = candidate.resolve()
        except Exception:
            return None
        if resolved_root not in resolved_candidate.parents and resolved_candidate != resolved_root:
            return None
        if not resolved_candidate.exists():
            return None
        try:
            return resolved_candidate.read_bytes()
        except OSError:
            return None

    def _post_json(self, path: str, payload: dict) -> dict:
        url = f"{self.base_url}{path}"
        redacted_payload = self._redact_payload(payload)
        
        # Full request logging for debugging workflow issues
        self.logger.info("="*80)
        self.logger.info(f"[COMFY API REQUEST] POST {url}")
        self.logger.info("="*80)
        self.logger.info(f"[COMFY API REQUEST] Full payload:\n{json.dumps(redacted_payload, indent=2, default=str)}")
        self.logger.info("="*80)
        
        with self._http_client() as client:
            try:
                response = client.post(url, json=payload)
                response.raise_for_status()
                
                # Full response logging
                response_data = response.json()
                self.logger.info("="*80)
                self.logger.info(f"[COMFY API RESPONSE] POST {url} - Status: {response.status_code}")
                self.logger.info("="*80)
                self.logger.info(f"[COMFY API RESPONSE] Full response:\n{json.dumps(response_data, indent=2, default=str)}")
                self.logger.info("="*80)
                
                return response_data
            except httpx.HTTPStatusError as exc:
                self.logger.error("="*80)
                self.logger.error(f"[COMFY API ERROR] POST {url} - HTTP Error: {exc.response.status_code}")
                self.logger.error("="*80)
                self.logger.error(f"[COMFY API ERROR] Response body:\n{exc.response.text}")
                self.logger.error("="*80)
                self._log_request_failure(
                    method="POST",
                    url=url,
                    request_json=payload,
                    response=exc.response,
                    error=exc,
                )
                raise
            except httpx.RequestError as exc:
                self.logger.error("="*80)
                self.logger.error(f"[COMFY API ERROR] POST {url} - Request Error: {exc}")
                self.logger.error("="*80)
                self._log_request_failure(
                    method="POST",
                    url=url,
                    request_json=payload,
                    response=None,
                    error=exc,
                )
                raise

    def _get_json(self, path: str) -> dict:
        url = f"{self.base_url}{path}"
        
        # Log request
        self.logger.debug(f"[COMFY API] GET {url}")
        
        with self._http_client() as client:
            try:
                response = client.get(url)
                response.raise_for_status()
                
                # Log successful response
                response_data = response.json()
                self.logger.debug(f"[COMFY API] GET {url} - Status: {response.status_code}")
                
                return response_data
            except httpx.HTTPStatusError as exc:
                self.logger.error(f"[COMFY API] GET {url} - HTTP Error: {exc.response.status_code}")
                self.logger.error(f"[COMFY API] Response body: {exc.response.text}")
                self._log_request_failure(
                    method="GET",
                    url=url,
                    response=exc.response,
                    error=exc,
                )
                raise
            except httpx.RequestError as exc:
                self.logger.error(f"[COMFY API] GET {url} - Request Error: {exc}")
                self._log_request_failure(
                    method="GET",
                    url=url,
                    response=None,
                    error=exc,
                )
                raise

    def _get_bytes(self, path: str, params: dict) -> bytes:
        url = f"{self.base_url}{path}"
        with self._http_client() as client:
            try:
                response = client.get(url, params=params)
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                self._log_request_failure(
                    method="GET",
                    url=url,
                    request_json={"params": params},
                    response=exc.response,
                    error=exc,
                )
                raise
            except httpx.RequestError as exc:
                self._log_request_failure(
                    method="GET",
                    url=url,
                    request_json={"params": params},
                    response=None,
                    error=exc,
                )
                raise
            return response.content

    def _get_object_info(self, node: str) -> dict:
        try:
            return self._get_json(f"/object_info/{node}")
        except Exception as exc:
            self.logger.error("ComfyUI object_info %s failed: %s", node, exc)
            # Root cause: ComfyUI server not accessible, causing empty data and 503 errors
            # Solution: Raise proper HTTP exception with clear error message
            raise HTTPException(
                status_code=503,
                detail=f"ComfyUI service unavailable: Cannot fetch {node} information. "
                       f"Please ensure ComfyUI server is running at {self.base_url}"
            )

    def _extract_required_list(self, payload: dict, node: str, key: str) -> List[str]:
        node_info = payload.get(node, {}) if isinstance(payload, dict) else {}
        values = node_info.get("input", {}).get("required", {}).get(key, [])
        if isinstance(values, list) and values and isinstance(values[0], list):
            values = values[0]
        return [str(item).strip() for item in values if isinstance(item, str) and str(item).strip()]

    def _unique(self, items: List[str]) -> List[str]:
        seen = set()
        ordered: List[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    def _workflow_uses_unet_models(self) -> bool:
        for kind in ("txt2img", "img2img"):
            try:
                workflow, _ = self._load_workflow_template(kind)
            except FileNotFoundError:
                self.logger.debug("Workflow template %s not found while detecting model list.", kind)
                continue
            except Exception as exc:
                self.logger.warning("Failed to load %s workflow for model detection: %s", kind, exc)
                continue
            if self._workflow_uses_unet_loader(workflow) or self._is_flux_workflow(workflow) or self._is_qwen_workflow(workflow):
                return True
        return False

    def _get_checkpoint_models(self) -> List[str]:
        if self._checkpoint_models_cache is None:
            # Root cause: Cloud API may not support object_info queries
            # Solution: Try to get models, but return defaults if it fails
            if self._is_cloud:
                # Cloud API: avoid object_info and use a safe default list
                self._checkpoint_models_cache = [
                    "flux1-dev-fp8.safetensors",
                    "sd_xl_base_1.0.safetensors",
                    "sd_xl_refiner_1.0.safetensors",
                ]
            else:
                try:
                    data = self._get_object_info("CheckpointLoaderSimple")
                    values = self._extract_required_list(data, "CheckpointLoaderSimple", "ckpt_name")
                    self._checkpoint_models_cache = self._unique(values)
                except Exception as e:
                    self.logger.warning(f"Failed to get checkpoint models: {e}")
                    self._checkpoint_models_cache = []
        return self._checkpoint_models_cache

    def _get_unet_models(self) -> List[str]:
        if self._unet_models_cache is None:
            # Root cause: Cloud API doesn't have UnetLoaderGGUF node
            # Solution: Return empty list for cloud API
            if self._is_cloud:
                self._unet_models_cache = []
            else:
                data = self._get_object_info("UnetLoaderGGUF")
                values = self._extract_required_list(data, "UnetLoaderGGUF", "unet_name")
                self._unet_models_cache = self._unique(values)
        return self._unet_models_cache

    def _coerce_model_name(self, workflow: dict, model_name: str) -> str:
        if not model_name:
            return model_name
        # Root cause: Previous logic treated all non-Qwen workflows as checkpoint-based,
        # which breaks FLUX GGUF workflows that use UnetLoaderGGUF. Detect UNet loaders.
        model_name_lower = str(model_name).lower()
        uses_unet = (
            self._workflow_uses_unet_loader(workflow)
            or self._is_flux_workflow(workflow)
            or self._is_qwen_workflow(workflow)
            or model_name_lower.endswith(".gguf")
        )
        allowed = self._get_unet_models() if uses_unet else self._get_checkpoint_models()
        if allowed and model_name not in allowed:
            fallback = (
                self.settings.sd_comfy_model if self.settings.sd_comfy_model in allowed else allowed[0]
            )
            if fallback and fallback != model_name:
                workflow_label = "UnetLoaderGGUF" if uses_unet else "CheckpointLoaderSimple"
                self.logger.warning(
                    "Requested model '%s' not available for %s workflow; using '%s' instead.",
                    model_name,
                    workflow_label,
                    fallback,
                )
                return fallback
        return model_name

    def _workflow_uses_unet_loader(self, workflow: dict) -> bool:
        def _scan(node: dict) -> bool:
            class_type = node.get("class_type", "")
            inputs = node.get("inputs", {})
            if class_type in {"UnetLoaderGGUF", "UnetLoaderGGUFAdvanced"}:
                return True
            if "unet_name" in inputs:
                return True
            return False

        if isinstance(workflow, dict):
            for node in workflow.values():
                if isinstance(node, dict) and _scan(node):
                    return True
            raw_nodes = workflow.get("nodes")
            if isinstance(raw_nodes, list):
                for node in raw_nodes:
                    if isinstance(node, dict) and _scan(node):
                        return True
        elif isinstance(workflow, list):
            for node in workflow:
                if isinstance(node, dict) and _scan(node):
                    return True
        return False

    def get_sd_models(self) -> List[dict]:
        use_unet = self._workflow_uses_unet_models()
        models = self._get_unet_models() if use_unet else self._get_checkpoint_models()
        return [{"title": name, "model_name": name} for name in models]

    def get_vae_models(self) -> List[str]:
        if self._is_cloud:
            return []
        if self._vae_cache is None:
            values: List[str] = []
            data = self._get_object_info("CheckpointLoaderSimple")
            values.extend(self._extract_required_list(data, "CheckpointLoaderSimple", "vae_name"))
            if not values:
                data = self._get_object_info("VAELoader")
                values.extend(self._extract_required_list(data, "VAELoader", "vae_name"))
            self._vae_cache = self._unique(values)
        return self._vae_cache

    def get_samplers(self) -> List[dict]:
        if self._is_cloud:
            sampler = (self.settings.sd_comfy_sampler or "euler").strip() or "euler"
            return [{"name": sampler, "aliases": []}]
        if self._sampler_cache is None:
            data = self._get_object_info("KSampler")
            self._sampler_cache = self._extract_required_list(data, "KSampler", "sampler_name")
        return [{"name": name, "aliases": []} for name in self._sampler_cache]

    def get_schedulers(self) -> List[dict]:
        if self._is_cloud:
            scheduler = (self.settings.sd_comfy_scheduler or "normal").strip() or "normal"
            return [{"name": scheduler, "label": scheduler}]
        if self._scheduler_cache is None:
            data = self._get_object_info("KSampler")
            self._scheduler_cache = self._extract_required_list(data, "KSampler", "scheduler")
        return [{"name": name, "label": name} for name in self._scheduler_cache]

    def get_loras(self) -> List[dict]:
        if self._is_cloud:
            return []
        if self._lora_cache is None:
            data = self._get_object_info("LoraLoader")
            self._lora_cache = self._extract_required_list(data, "LoraLoader", "lora_name")
        return [{"name": name, "alias": None, "path": None} for name in self._lora_cache]

    def get_styles(self) -> List[dict]:
        return []

    def refresh_models(self) -> bool:
        self._checkpoint_models_cache = None
        self._unet_models_cache = None
        return True

    def refresh_vae(self) -> bool:
        self._vae_cache = None
        return True

    def refresh_loras(self) -> bool:
        self._lora_cache = None
        return True

    def get_options(self) -> dict:
        return {
            "sd_model_checkpoint": self._options_override.get("sd_model_checkpoint") or self.settings.sd_comfy_model,
            "sd_vae": self._options_override.get("sd_vae") or self.settings.sd_comfy_vae,
            "sampler_name": self._options_override.get("sampler_name") or self.settings.sd_comfy_sampler,
            "scheduler": self._options_override.get("scheduler") or self.settings.sd_comfy_scheduler,
        }

    def set_options(self, options: dict) -> bool:
        if not isinstance(options, dict):
            return False

        def _set(key: str, value: object) -> None:
            if isinstance(value, str):
                cleaned = value.strip()
                if cleaned:
                    self._options_override[key] = cleaned
                    return
            if value in ("", None):
                self._options_override.pop(key, None)

        _set("sd_model_checkpoint", options.get("sd_model_checkpoint") or options.get("model_id") or options.get("model_checkpoint"))
        _set("sd_vae", options.get("sd_vae") or options.get("vae_id") or options.get("vae"))
        _set("sampler_name", options.get("sampler_name") or options.get("sampler"))
        _set("scheduler", options.get("scheduler") or options.get("scheduler_name"))
        return True

    def _upload_image(self, data: Union[bytes, str]) -> str:
        if isinstance(data, str):
            if data.startswith("data:"):
                data = data.split(",", 1)[1]
            data = base64.b64decode(data)

        files = {"image": ("input.png", data, "image/png")}
        url = f"{self.base_url}/upload/image"
        with self._http_client() as client:
            try:
                response = client.post(url, files=files)
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPStatusError as exc:
                self._log_request_failure(
                    method="POST",
                    url=url,
                    request_files={"image": {"filename": "input.png", "content_type": "image/png", "size": len(data)}},
                    response=exc.response,
                    error=exc,
                )
                raise
            except httpx.RequestError as exc:
                self._log_request_failure(
                    method="POST",
                    url=url,
                    request_files={"image": {"filename": "input.png", "content_type": "image/png", "size": len(data)}},
                    response=None,
                    error=exc,
                )
                raise

        name = payload.get("name") or payload.get("filename")
        subfolder = payload.get("subfolder") or ""
        if not name:
            raise RuntimeError("ComfyUI upload returned no filename")
        return f"{subfolder}/{name}" if subfolder else name

    def upload_image(self, data: Union[bytes, str]) -> str:
        """Upload an image to ComfyUI and return the stored filename."""
        return self._upload_image(data)

    def _queue_workflow(self, workflow: dict) -> str:
        # Log workflow being queued with full details
        self.logger.info("="*80)
        self.logger.info("[COMFY WORKFLOW] Queueing workflow")
        self.logger.info("="*80)
        self.logger.info(f"[COMFY WORKFLOW] Workflow JSON:\n{json.dumps(workflow, indent=2, default=str)}")
        
        payload = {"prompt": workflow, "client_id": "lwq-backend"}
        api_key = self._extract_comfy_api_key()
        if api_key:
            extra = payload.setdefault("extra_data", {})
            if isinstance(extra, dict):
                extra.setdefault("api_key_comfy_org", api_key)
        response = self._post_json("/prompt", payload)
        
        prompt_id = response.get("prompt_id") or response.get("id")
        if not prompt_id:
            self.logger.error("[COMFY WORKFLOW] No prompt_id in response!")
            raise RuntimeError("ComfyUI did not return prompt_id")
        
        self.logger.info(f"[COMFY WORKFLOW] Queued successfully - Prompt ID: {prompt_id}")
        self.logger.info("="*80)
        
        return str(prompt_id)

    def _get_history(self, prompt_id: str) -> dict:
        """Fetch execution history for a prompt id, using cloud-specific endpoint when needed."""
        if self._is_cloud:
            return self._get_json(f"/history_v2/{prompt_id}")
        return self._get_json(f"/history/{prompt_id}")

    def _extract_prompt_payload(self, history: dict, prompt_id: str) -> Optional[dict]:
        if not isinstance(history, dict):
            return None
        payload = history.get(prompt_id) or history.get(str(prompt_id))
        if payload is None and ("status" in history or "details" in history):
            # Some cloud responses return task status directly (not keyed by prompt id).
            return history
        return payload

    def _extract_error_payload(self, response: Optional[httpx.Response]) -> Optional[dict]:
        if response is None:
            return None
        try:
            payload = response.json()
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if "status" in payload or "details" in payload or "error" in payload:
            return payload
        return None

    def _moderation_reason(self, payload: dict) -> Optional[str]:
        status_val = payload.get("status")
        details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
        status_str = None
        if isinstance(status_val, dict):
            status_str = status_val.get("status_str") or status_val.get("status")
            if isinstance(status_val.get("details"), dict):
                details = status_val.get("details")
        elif isinstance(status_val, str):
            status_str = status_val

        if not status_str:
            err = payload.get("error")
            if isinstance(err, dict):
                status_str = err.get("status") or err.get("status_str")
                if isinstance(err.get("details"), dict):
                    details = err.get("details")

        if not status_str or "moderat" not in status_str.lower():
            return None

        reasons = (
            details.get("Moderation Reasons")
            or details.get("moderation_reasons")
            or details.get("reasons")
        )
        if isinstance(reasons, (list, tuple)):
            reason_text = ", ".join([str(item) for item in reasons if item])
        else:
            reason_text = str(reasons) if reasons else ""
        return reason_text or "Safety Filter"

    def _extract_node_outputs(self, node_output: object) -> list[dict]:
        if not isinstance(node_output, dict):
            return []
        for key in ("images", "audio", "audios", "files", "gifs", "videos"):
            values = node_output.get(key)
            if not isinstance(values, list):
                continue
            items = [item for item in values if isinstance(item, dict)]
            if items:
                return items
        return []

    def _wait_for_result(self, prompt_id: str, output_nodes: list[str]) -> list[dict]:
        # Root cause: Cloud API jobs take longer to register in history_v2 than local ComfyUI.
        # Polling immediately results in 404 "History not found" errors.
        # Solution: Add initial delay for cloud API to allow job registration.
        if self._is_cloud:
            self.logger.info(f"Cloud API job {prompt_id}: waiting 10s for job registration...")
            time.sleep(10)
        
        # Cloud history registration can be delayed; keep polling until normal timeout.
        timeout = self.timeout_s
        deadline = time.monotonic() + timeout
        last_status = None
        check_interval = 2.0 if self._is_cloud else 1.0
        consecutive_404s = 0
        
        while time.monotonic() < deadline:
            try:
                # Root cause: Cloud API doesn't support /queue endpoint
                # Solution: Skip queue check for cloud API
                if not self._is_cloud:
                    queue = self._get_json("/queue")
                    running = queue.get("queue_running", [])
                    pending = queue.get("queue_pending", [])
                    job_in_queue = any(job[1] == prompt_id for job in running + pending if len(job) > 1)
                else:
                    job_in_queue = True  # Assume cloud jobs are always "in queue" until history shows otherwise
                
                # Check history
                try:
                    history = self._get_history(prompt_id)
                    payload = self._extract_prompt_payload(history, prompt_id)
                    consecutive_404s = 0  # Reset counter on successful response
                except httpx.HTTPStatusError as e:
                    error_payload = self._extract_error_payload(e.response)
                    if error_payload:
                        moderation_reason = self._moderation_reason(error_payload)
                        if moderation_reason:
                            raise RuntimeError(f"content_moderated: {moderation_reason}")
                        if e.response.status_code != 404:
                            status_text = (
                                error_payload.get("status")
                                or error_payload.get("error")
                                or error_payload.get("message")
                            )
                            if status_text:
                                raise RuntimeError(
                                    f"ComfyUI job {prompt_id} failed: {status_text}"
                                )
                    # Root cause: Cloud API returns 404 if job not ready yet
                    # Solution: Treat 404 as "still processing" rather than fatal error
                    if self._is_cloud and e.response.status_code == 404:
                        consecutive_404s += 1
                        if consecutive_404s % 10 == 0:
                            self.logger.warning(
                                f"Cloud API job {prompt_id} still not in history after {consecutive_404s} attempts..."
                            )
                        time.sleep(check_interval)
                        continue
                    raise
                
                if payload:
                    moderation_reason = self._moderation_reason(payload)
                    if moderation_reason:
                        raise RuntimeError(f"content_moderated: {moderation_reason}")

                    status = payload.get("status", {})
                    last_status = status
                    
                    # Check if completed successfully
                    if status.get("completed", False):
                        outputs = payload.get("outputs") or {}
                        for node_id in output_nodes:
                            node_output = outputs.get(str(node_id))
                            node_items = self._extract_node_outputs(node_output)
                            if node_items:
                                return node_items
                        for node_output in outputs.values():
                            node_items = self._extract_node_outputs(node_output)
                            if node_items:
                                return node_items
                    
                    # Check for errors
                    status_str = status.get("status_str") if isinstance(status, dict) else None
                    if isinstance(status, str):
                        status_str = status
                    if "error" in payload or status_str == "error":
                        error_msg = payload.get("error", "Unknown error")
                        raise RuntimeError(f"ComfyUI job {prompt_id} failed: {error_msg}")
                
                # If job not in queue and no history, it may have failed silently
                if not job_in_queue and not payload:
                    # Wait a bit more in case it's just starting
                    if time.monotonic() - (deadline - self.timeout_s) > 10:  # After 10 seconds
                        raise RuntimeError(f"ComfyUI job {prompt_id} disappeared from queue without completing")
                
            except (requests.RequestException, KeyError) as e:
                self.logger.warning(f"Error checking ComfyUI status: {e}")
            
            time.sleep(check_interval)

        raise TimeoutError(f"ComfyUI job {prompt_id} did not finish (status={last_status})")

    def _wait_for_result_multi(self, prompt_id: str, output_nodes: list[str]) -> list[list[dict]]:
        """Wait for completion and return images for each output node in order."""
        # Root cause: Cloud API needs same 404 handling as _wait_for_result
        if self._is_cloud:
            self.logger.info(f"Cloud API job {prompt_id}: waiting 10s for job registration...")
            time.sleep(10)
        
        # Cloud history registration can be delayed; keep polling until normal timeout.
        timeout = self.timeout_s
        deadline = time.monotonic() + timeout
        last_status = None
        check_interval = 2.0 if self._is_cloud else 1.0
        consecutive_404s = 0

        while time.monotonic() < deadline:
            try:
                # Skip queue check for cloud API (not supported)
                if not self._is_cloud:
                    queue = self._get_json("/queue")
                    running = queue.get("queue_running", [])
                    pending = queue.get("queue_pending", [])
                    job_in_queue = any(job[1] == prompt_id for job in running + pending if len(job) > 1)
                else:
                    job_in_queue = True

                # Check history with proper 404 handling
                try:
                    history = self._get_history(prompt_id)
                    payload = self._extract_prompt_payload(history, prompt_id)
                    consecutive_404s = 0  # Reset counter on successful response
                except httpx.HTTPStatusError as e:
                    error_payload = self._extract_error_payload(e.response)
                    if error_payload:
                        moderation_reason = self._moderation_reason(error_payload)
                        if moderation_reason:
                            raise RuntimeError(f"content_moderated: {moderation_reason}")
                        if e.response.status_code != 404:
                            status_text = (
                                error_payload.get("status")
                                or error_payload.get("error")
                                or error_payload.get("message")
                            )
                            if status_text:
                                raise RuntimeError(
                                    f"ComfyUI job {prompt_id} failed: {status_text}"
                                )
                    if self._is_cloud and e.response.status_code == 404:
                        consecutive_404s += 1
                        if consecutive_404s % 10 == 0:
                            self.logger.warning(
                                f"Cloud API job {prompt_id} still not in history after {consecutive_404s} attempts..."
                            )
                        time.sleep(check_interval)
                        continue
                    raise

                if payload:
                    moderation_reason = self._moderation_reason(payload)
                    if moderation_reason:
                        raise RuntimeError(f"content_moderated: {moderation_reason}")

                    status = payload.get("status", {})
                    last_status = status
                    if status.get("completed", False):
                        outputs = payload.get("outputs") or {}
                        if output_nodes:
                            results: list[list[dict]] = []
                            for node_id in output_nodes:
                                node_output = outputs.get(str(node_id))
                                results.append(self._extract_node_outputs(node_output))
                            if any(results):
                                return results
                        for node_output in outputs.values():
                            node_items = self._extract_node_outputs(node_output)
                            if node_items:
                                return [node_items]

                    status_str = status.get("status_str") if isinstance(status, dict) else None
                    if isinstance(status, str):
                        status_str = status
                    if "error" in payload or status_str == "error":
                        error_msg = payload.get("error", "Unknown error")
                        raise RuntimeError(f"ComfyUI job {prompt_id} failed: {error_msg}")

                if not job_in_queue and not payload:
                    if time.monotonic() - (deadline - self.timeout_s) > 10:
                        raise RuntimeError(f"ComfyUI job {prompt_id} disappeared from queue without completing")

            except (httpx.RequestError, KeyError) as e:
                self.logger.warning(f"Error checking ComfyUI status: {e}")

            time.sleep(check_interval)

        raise TimeoutError(f"ComfyUI job {prompt_id} did not finish (status={last_status})")

    def _build_prompt(self, prompt: str, style: Optional[str]) -> str:
        return prompt if style is None else f"{prompt}, style::{style}"

    
    def _apply_qwen_inputs(
        self,
        workflow: dict,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        batch_size: int,
        sampler: str,
        scheduler: str,
    ) -> None:
        """Apply inputs for Qwen GGUF workflow structure"""
        nodes = workflow
        
        # Update positive prompt (node 4)
        if "4" in nodes and nodes["4"]["class_type"] == "TextEncodeQwenImageEditPlus":
            nodes["4"]["inputs"]["prompt"] = prompt
        
        # Update negative prompt (node 5)  
        if "5" in nodes and nodes["5"]["class_type"] == "TextEncodeQwenImageEditPlus":
            nodes["5"]["inputs"]["prompt"] = negative_prompt or "worst quality, low quality, blurry"
        
        # Update dimensions (node 6)
        if "6" in nodes and nodes["6"]["class_type"] == "EmptyLatentImage":
            nodes["6"]["inputs"]["width"] = width
            nodes["6"]["inputs"]["height"] = height
            nodes["6"]["inputs"]["batch_size"] = batch_size
        
        # Update sampler settings (node 7)
        if "7" in nodes and nodes["7"]["class_type"] == "KSampler":
            nodes["7"]["inputs"]["steps"] = steps
            nodes["7"]["inputs"]["cfg"] = cfg_scale
            nodes["7"]["inputs"]["seed"] = seed
            nodes["7"]["inputs"]["sampler_name"] = sampler
            nodes["7"]["inputs"]["scheduler"] = scheduler

    def _is_qwen_workflow(self, workflow: dict) -> bool:
        """Check if workflow uses Qwen-specific nodes (not just GGUF loaders)"""
        # Root cause: Previous logic incorrectly identified FLUX workflows as Qwen
        # because both use UnetLoaderGGUF/CLIPLoaderGGUF. Fixed by checking for
        # Qwen-specific nodes like TextEncodeQwenImageEditPlus.
        for node in workflow.values():
            if isinstance(node, dict):
                class_type = node.get("class_type", "")
                # Only TextEncodeQwenImageEditPlus is truly Qwen-specific
                if class_type == "TextEncodeQwenImageEditPlus":
                    return True
                # Also check for Qwen model names in UNet loaders
                if class_type == "UnetLoaderGGUF":
                    unet_name = node.get("inputs", {}).get("unet_name", "")
                    if "qwen" in unet_name.lower():
                        return True
        return False
    def _is_flux_workflow(self, workflow: dict) -> bool:
        """Check if workflow uses FLUX-specific nodes and models"""
        for node in workflow.values():
            if isinstance(node, dict):
                class_type = node.get("class_type", "")
                inputs = node.get("inputs", {})
                
                # Check for FLUX-specific loaders
                if class_type == "DualCLIPLoader":
                    clip_type = inputs.get("type", "")
                    if clip_type == "flux":
                        return True
                
                # Check for FLUX model names
                if class_type == "UnetLoaderGGUF":
                    unet_name = inputs.get("unet_name", "")
                    if "flux" in unet_name.lower():
                        return True
                
                # Check for FLUX-specific nodes
                if class_type in ["FluxGuidance", "BasicGuider"]:
                    return True
        return False

    def _apply_clip_vae_loaders(
        self,
        workflow: dict,
        *,
        model_name: str,
        vae_name: str,
        clip_name: Optional[str] = None,
        loader_type: str = "standard",
    ) -> None:
        """Apply CLIP/VAE loaders based on model type and explicit specifications."""
        
        # Update model loaders based on loader type
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            
            inputs = node.get("inputs", {})
            class_type = node.get("class_type", "")
            
            # Handle GGUF loaders
            if loader_type == "gguf":
                if class_type == "UnetLoaderGGUF" or "unet_name" in inputs:
                    inputs["unet_name"] = model_name
                elif class_type == "CLIPLoaderGGUF" and clip_name:
                    inputs["clip_name"] = clip_name
                elif class_type == "VaeGGUF" and vae_name:
                    inputs["vae_name"] = vae_name
            
            # Handle standard loaders
            else:
                if class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
                    inputs["ckpt_name"] = model_name
                    if vae_name and "vae_name" in inputs:
                        inputs["vae_name"] = vae_name
                elif class_type == "VAELoader" and vae_name:
                    inputs["vae_name"] = vae_name
                elif class_type == "CLIPLoader" and clip_name:
                    inputs["clip_name"] = clip_name


    def _split_prompt_for_dual_clip(self, prompt: str) -> tuple[str, str]:
        """
        Split prompt into style tags (CLIP-L) and detailed description (T5).
        
        Root cause: FLUX dual text encoding needs separation of style/quality tags
        from detailed character descriptions for optimal results.
        
        Returns: (style_tags, detailed_description)
        """
        # Log the input prompt for debugging
        self.logger.info(f"Splitting prompt (length={len(prompt)}): {prompt[:200]}...")
        
        # Style/quality keywords that should go to CLIP-L (short, technical terms)
        style_keywords = [
            "photorealistic", "detailed", "balanced geometry", "rich textures",
            "balanced lighting", "fine details", "studio lighting", "neutral background",
            "sharp focus", "cinematic", "masterpiece", "best quality", "highly detailed",
            "professional lighting", "8k", "4k", "hdr", "portrait", "close-up",
            "85mm lens", "bokeh", "depth of field", "soft lighting", "dramatic lighting",
            "cinematic mood"
        ]
        
        parts = [p.strip() for p in prompt.split(",")]
        style_parts = []
        description_parts = []
        
        for part in parts:
            part_lower = part.lower()
            # Only classify as style if it's a SHORT phrase with style keywords
            # Long descriptive sentences should always go to t5xxl
            is_short_style = (
                len(part.split()) <= 4 and  # 4 words or less
                any(keyword in part_lower for keyword in style_keywords)
            )
            
            if is_short_style:
                style_parts.append(part)
            else:
                description_parts.append(part)
        
        # If no clear separation, put quality tags in style and rest in description
        if not style_parts:
            style_parts = ["photorealistic, detailed, balanced lighting, sharp focus, cinematic"]
        
        # Always include the full description in t5xxl
        style_text = ", ".join(style_parts)
        description_text = ", ".join(description_parts) if description_parts else prompt
        
        self.logger.info(f"Split result - clip_l: {style_text[:100]}... | t5xxl: {description_text[:100]}...")
        
        return style_text, description_text

    def _apply_common_inputs(
        self,
        workflow: dict,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        batch_size: int,
        sampler: str,
        scheduler: str,
        model_name: str,
        vae_name: str,
        clip_name: Optional[str] = None,
        loader_type: str = "standard",
    ) -> None:
        model_name = self._coerce_model_name(workflow, model_name)

        # Apply CLIP/VAE loaders based on model type
        # clip_name parameter is already available
        loader_type = loader_type
        self._apply_clip_vae_loaders(
            workflow,
            model_name=model_name,
            vae_name=vae_name,
            clip_name=clip_name,
            loader_type=loader_type,
        )

        # Root cause: FLUX workflows with DualCLIPLoader need separate prompts
        # for CLIP-L (style) and T5 (detailed description) for optimal results.
        # Also, CLIPTextEncodeFlux uses separate clip_l/t5xxl inputs.
        has_dual_clip = any(
            node.get("class_type") == "DualCLIPLoader"
            for node in workflow.values()
            if isinstance(node, dict)
        )
        has_flux_encode = any(
            node.get("class_type") == "CLIPTextEncodeFlux"
            for node in workflow.values()
            if isinstance(node, dict)
        )
        style_text: Optional[str] = None
        description_text: Optional[str] = None
        if has_flux_encode or (has_dual_clip and self._is_cloud):
            style_text, description_text = self._split_prompt_for_dual_clip(prompt)
        if has_dual_clip and self._is_cloud and not has_flux_encode:
            prompt_for_encode = style_text or prompt
        else:
            prompt_for_encode = prompt

        def _set_text(node: dict, value: str) -> None:
            inputs = node.setdefault("inputs", {})
            if "text" in inputs:
                inputs["text"] = value
            elif "prompt" in inputs:
                inputs["prompt"] = value
            else:
                inputs["text"] = value

        nodes = workflow
        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            inputs = node.get("inputs", {})
            class_type = node.get("class_type", "")
            if "unet_name" in inputs or class_type in {"UnetLoaderGGUF", "UnetLoaderGGUFAdvanced"}:
                inputs["unet_name"] = model_name
                continue
            if "ckpt_name" in inputs or class_type in {"CheckpointLoaderSimple", "CheckpointLoader"}:
                inputs["ckpt_name"] = model_name
                if vae_name and "vae_name" in inputs:
                    inputs["vae_name"] = vae_name

        if vae_name:
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                if node.get("class_type") == "VAELoader":
                    node_inputs = node.setdefault("inputs", {})
                    if "vae_name" in node_inputs:
                        node_inputs["vae_name"] = vae_name

        if has_flux_encode:
            # Flux workflows: write style/description into CLIPTextEncodeFlux,
            # and treat any CLIPTextEncode nodes as negative prompt holders.
            for node in nodes.values():
                if not isinstance(node, dict):
                    continue
                if node.get("class_type") == "CLIPTextEncodeFlux":
                    inputs = node.setdefault("inputs", {})
                    inputs["clip_l"] = style_text or prompt
                    inputs["t5xxl"] = description_text or prompt
                    if "guidance" in inputs and cfg_scale is not None:
                        inputs["guidance"] = cfg_scale
            if negative_prompt is not None:
                for node in nodes.values():
                    if not isinstance(node, dict):
                        continue
                    if node.get("class_type") == "CLIPTextEncode":
                        _set_text(node, negative_prompt)
        else:
            encode_nodes = []
            for node_id in sorted(nodes.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)):
                node = nodes.get(node_id)
                if not isinstance(node, dict):
                    continue
                class_type = node.get("class_type", "")
                if class_type in {"CLIPTextEncode", "TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"}:
                    encode_nodes.append(node)
            if encode_nodes:
                _set_text(encode_nodes[0], prompt_for_encode)
            if len(encode_nodes) > 1:
                _set_text(encode_nodes[1], negative_prompt or "")

        for node in nodes.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "EmptyLatentImage":
                node_inputs = node.setdefault("inputs", {})
                node_inputs["width"] = width
                node_inputs["height"] = height
                node_inputs["batch_size"] = batch_size
            if node.get("class_type") == "KSampler":
                node_inputs = node.setdefault("inputs", {})
                node_inputs["steps"] = steps
                node_inputs["cfg"] = cfg_scale
                node_inputs["seed"] = seed
                node_inputs["sampler_name"] = sampler
                node_inputs["scheduler"] = scheduler

            # Flux workflows use a different node stack (CustomSampler + FluxGuidance + RandomNoise).
            if node.get("class_type") == "RandomNoise":
                node.setdefault("inputs", {})["noise_seed"] = seed
            if node.get("class_type") == "KSamplerSelect":
                node.setdefault("inputs", {})["sampler_name"] = sampler
            if node.get("class_type") == "FluxGuidance":
                node.setdefault("inputs", {})["guidance"] = cfg_scale
            if node.get("class_type") == "Flux2Scheduler":
                node_inputs = node.setdefault("inputs", {})
                if "steps" in node_inputs:
                    node_inputs["steps"] = steps
                if "width" in node_inputs:
                    node_inputs["width"] = width
                if "height" in node_inputs:
                    node_inputs["height"] = height
            if node.get("class_type") == "EmptyFlux2LatentImage":
                node_inputs = node.setdefault("inputs", {})
                if "width" in node_inputs:
                    node_inputs["width"] = width
                if "height" in node_inputs:
                    node_inputs["height"] = height
                if "batch_size" in node_inputs:
                    node_inputs["batch_size"] = batch_size
            if node.get("class_type") == "FluxKontextProImageNode":
                node_inputs = node.setdefault("inputs", {})
                if "prompt" in node_inputs:
                    node_inputs["prompt"] = prompt_for_encode
                if "guidance" in node_inputs and cfg_scale is not None:
                    node_inputs["guidance"] = cfg_scale
                if "steps" in node_inputs and steps is not None:
                    node_inputs["steps"] = steps
                if "prompt_upsampling" in node_inputs:
                    node_inputs["prompt_upsampling"] = True

    def _apply_prompt_only_for_cloud(
        self,
        workflow: dict,
        *,
        prompt: str,
        cfg_scale: Optional[float],
    ) -> None:
        """For cloud_api workflows, only update prompt-bearing nodes."""
        # Root cause: Cloud API workflows use FluxKontextProImageNode for img2img
        # Solution: Check for FluxKontextProImageNode first, then CLIPTextEncodeFlux for txt2img
        
        # Check for FluxKontextProImageNode (img2img)
        kontext_nodes = [
            node
            for node in workflow.values()
            if isinstance(node, dict) and node.get("class_type") == "FluxKontextProImageNode"
        ]
        if kontext_nodes:
            for node in kontext_nodes:
                inputs = node.setdefault("inputs", {})
                inputs["prompt"] = prompt
                if cfg_scale is not None:
                    inputs["guidance"] = cfg_scale
            return
        
        # Check for CLIPTextEncodeFlux (txt2img)
        # Root cause: cfg_scale was overriding workflow's guidance value
        # Fix: Only update prompts, preserve workflow's guidance setting
        style_text, description_text = self._split_prompt_for_dual_clip(prompt)
        flux_nodes = [
            node
            for node in workflow.values()
            if isinstance(node, dict) and node.get("class_type") == "CLIPTextEncodeFlux"
        ]
        if flux_nodes:
            for node in flux_nodes:
                inputs = node.setdefault("inputs", {})
                inputs["clip_l"] = style_text
                inputs["t5xxl"] = description_text
                # Don't override guidance - workflow JSON has the correct value
            return

        # Fallback: update the first CLIPTextEncode node only.
        for node_id in sorted(
            workflow.keys(), key=lambda value: int(value) if str(value).isdigit() else str(value)
        ):
            node = workflow.get(node_id)
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "CLIPTextEncode":
                inputs = node.setdefault("inputs", {})
                if "text" in inputs:
                    inputs["text"] = prompt
                elif "prompt" in inputs:
                    inputs["prompt"] = prompt
                else:
                    inputs["text"] = prompt
                break

    def _apply_seed_only_for_cloud(self, workflow: dict, seed: Optional[int]) -> None:
        """For cloud_api workflows, only update seed-bearing nodes."""
        if seed is None:
            return
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            if class_type == "KSampler":
                node.setdefault("inputs", {})["seed"] = seed
            elif class_type == "RandomNoise":
                node.setdefault("inputs", {})["noise_seed"] = seed
            elif class_type == "FluxKontextProImageNode":
                node.setdefault("inputs", {})["seed"] = seed

    def _apply_loras(self, workflow: dict, loras: list[dict]) -> None:
        if not loras:
            return

        def _weights(lora: dict) -> tuple[float, float]:
            try:
                weight = float(lora.get("weight", 0.8))
            except Exception:
                weight = 0.8
            clip_weight = lora.get("clip_weight")
            if clip_weight is None:
                clip_weight = lora.get("weight_clip")
            if clip_weight is None:
                clip_weight = lora.get("strength_clip")
            try:
                clip_val = float(clip_weight) if clip_weight is not None else weight
            except Exception:
                clip_val = weight
            return weight, clip_val

        existing = [
            (node_id, node)
            for node_id, node in workflow.items()
            if isinstance(node, dict) and node.get("class_type") == "LoraLoader"
        ]
        existing.sort(key=lambda item: int(item[0]) if str(item[0]).isdigit() else str(item[0]))
        if existing:
            for idx, lora in enumerate(loras):
                if idx >= len(existing):
                    break
                node_id, node = existing[idx]
                name = str(lora.get("name") or "").strip()
                if not name:
                    continue
                weight, clip_weight = _weights(lora)
                inputs = node.setdefault("inputs", {})
                inputs["lora_name"] = name
                inputs["strength_model"] = weight
                inputs["strength_clip"] = clip_weight

            if len(loras) <= len(existing):
                return

        node_ids = [int(node_id) for node_id in workflow.keys() if str(node_id).isdigit()]
        next_id = max(node_ids) + 1 if node_ids else 10

        model_ref: list = ["1", 0]
        clip_ref: list = ["1", 1]
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") == "KSampler":
                model_ref = node.get("inputs", {}).get("model", model_ref)
                break
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in {"CLIPTextEncode", "TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"}:
                clip_ref = node.get("inputs", {}).get("clip", clip_ref)
                break
        if existing:
            last_id = existing[-1][0]
            model_ref = [last_id, 0]
            clip_ref = [last_id, 1]

        for lora in loras[len(existing):]:
            name = str(lora.get("name") or "").strip()
            if not name:
                continue
            weight, clip_weight = _weights(lora)
            node_id = str(next_id)
            workflow[node_id] = {
                "class_type": "LoraLoader",
                "inputs": {
                    "model": model_ref,
                    "clip": clip_ref,
                    "lora_name": name,
                    "strength_model": weight,
                    "strength_clip": clip_weight,
                },
            }
            model_ref = [node_id, 0]
            clip_ref = [node_id, 1]
            next_id += 1

        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            if node.get("class_type") in {"CLIPTextEncode", "TextEncodeQwenImageEdit", "TextEncodeQwenImageEditPlus"}:
                node["inputs"]["clip"] = clip_ref
            if node.get("class_type") == "KSampler":
                node["inputs"]["model"] = model_ref

    def _build_txt2img_workflow(
        self,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        width: int,
        height: int,
        steps: int,
        cfg_scale: float,
        seed: int,
        batch_size: int,
        sampler: str,
        scheduler: str,
        model_name: str,
        vae_name: str,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
        clip_id: Optional[str] = None,
        loader_type: str = "standard",
    ) -> tuple[dict, list[str]]:
        """
        Build txt2img workflow with transparent parameter substitution.
        
        Root cause: Old implementation had scattered parameter overrides.
        Solution: Use WorkflowParams for explicit, traceable substitution.
        """
        template, output_nodes = self._load_workflow_template(
            "txt2img", 
            workflow_set=workflow_set, 
            workflow_task=workflow_task
        )
        
        # Use WorkflowParams for transparent parameter handling
        params = WorkflowParams(template)
        
        # REQUIRED: Always set these
        params.set_prompts(prompt, negative_prompt)
        params.set_seed(seed)
        skip_model_override = (
            self._is_cloud
            and (workflow_set or "").startswith("cloud_api")
            and (workflow_task or "").strip().lower() == "location"
        )
        if not skip_model_override:
            params.set_model(model_name, vae_name)
        
        # Cloud API workflows: minimal substitution (workflow JSON is source of truth)
        if self._is_cloud and (workflow_set or "").startswith("cloud_api"):
            # Only set prompts and seed - everything else from workflow JSON
            # FLUX: guidance stays in JSON (3 for txt2img, 5 for img2img)
            # SDXL: cfg stays in JSON (7.0)
            return params.get_workflow(), output_nodes
        
        # Local workflows: full parameter control
        params.set_dimensions(width, height, batch_size)
        params.set_sampling_params(
            steps=steps,
            cfg=cfg_scale,  # For SDXL/SD1.5 KSampler
            sampler=sampler,
            scheduler=scheduler,
            denoise=1.0  # txt2img always full denoise
        )
        
        # Note: cfg_scale is used for KSampler (SDXL/SD1.5)
        # FLUX workflows ignore cfg_scale and use guidance from JSON
        
        return params.get_workflow(), output_nodes

    def _build_img2img_workflow(
        self,
        *,
        prompt: str,
        negative_prompt: Optional[str],
        steps: int,
        cfg_scale: float,
        seed: int,
        sampler: str,
        scheduler: str,
        model_name: str,
        vae_name: str,
        denoise: float,
        input_image: str,
        input_images_map: Optional[dict[str, str]] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
        clip_id: Optional[str] = None,
        loader_type: str = "standard",
    ) -> tuple[dict, list[str]]:
        """
        Build img2img workflow with transparent parameter substitution.
        
        Root cause: Old implementation had scattered parameter overrides.
        Solution: Use WorkflowParams for explicit, traceable substitution.
        """
        template, output_nodes = self._load_workflow_template(
            "img2img",
            workflow_set=workflow_set,
            workflow_task=workflow_task
        )
        
        # Use WorkflowParams for transparent parameter handling
        params = WorkflowParams(template)
        
        # REQUIRED: Always set these
        params.set_prompts(prompt, negative_prompt)
        params.set_seed(seed)
        skip_model_override = (
            self._is_cloud
            and (workflow_set or "").startswith("cloud_api")
            and (workflow_task or "").strip().lower() == "scene"
            and (
                params._has_node_type("TextEncodeQwenImageEditPlus")
                or params._has_node_type("TextEncodeQwenImageEdit")
            )
        )
        if not skip_model_override:
            params.set_model(model_name, vae_name)
        if input_images_map:
            params.set_input_images(input_images_map)
        else:
            params.set_input_image(input_image)
        
        # Cloud API workflows: minimal substitution
        if self._is_cloud and (workflow_set or "").startswith("cloud_api"):
            # FluxKontextProImageNode handles guidance internally
            # Only set prompts, seed, and input image
            # FLUX: guidance stays in JSON (5 for img2img)
            # SDXL: cfg stays in JSON (7.0)
            if denoise is not None:
                # Keep cloud workflow defaults intact, but allow denoise tuning
                # to preserve image-1 background geometry in scene img2img mode.
                params.set_sampling_params(denoise=denoise)
            return params.get_workflow(), output_nodes
        
        # Local workflows: full parameter control
        params.set_sampling_params(
            steps=steps,
            cfg=cfg_scale,  # For SDXL/SD1.5 KSampler
            sampler=sampler,
            scheduler=scheduler,
            denoise=denoise
        )
        
        # Note: cfg_scale is used for KSampler (SDXL/SD1.5)
        # FLUX workflows ignore cfg_scale and use guidance from JSON
        
        return params.get_workflow(), output_nodes

    def run_workflow(self, workflow: dict, output_nodes: list[str]) -> list[list[bytes]]:
        """Queue a prepared workflow and return bytes per output node."""
        outputs_by_node = self.run_workflow_outputs(workflow, output_nodes)
        return [self._fetch_outputs(outputs) if outputs else [] for outputs in outputs_by_node]

    def run_workflow_outputs(self, workflow: dict, output_nodes: list[str]) -> list[list[dict]]:
        """Queue a prepared workflow and return raw output descriptors per node."""
        prompt_id = self._queue_workflow(workflow)
        return self._wait_for_result_multi(prompt_id, output_nodes)

    def fetch_outputs(self, outputs: list[dict]) -> list[bytes]:
        """Fetch output payloads (images/audio/files) from ComfyUI /view."""
        return self._fetch_outputs(outputs)

    _BLANK_PNG = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+VmO0AAAAASUVORK5CYII="
    )

    def _decode_base64_image(self, value: Optional[str]) -> Optional[bytes]:
        if not value:
            return None
        raw = str(value)
        if "," in raw and raw.strip().startswith("data:"):
            raw = raw.split(",", 1)[1]
        try:
            return base64.b64decode(raw)
        except Exception:
            return None

    def _prepare_control_bundle(self, alwayson_scripts: Optional[dict]) -> dict:
        """Extract a minimal ControlNet/IP-Adapter bundle from A1111-style alwayson_scripts."""
        bundle = {
            "control_image": self._BLANK_PNG,
            "control_net_name": "",
            "control_strength": 0.0,
            "control_start": 0.0,
            "control_end": 1.0,
            "identity_image": self._BLANK_PNG,
            "ipadapter_file": "",
            "ipadapter_weight": 0.0,
            "ip_start": 0.0,
            "ip_end": 1.0,
        }
        if not alwayson_scripts:
            return bundle
        args = (alwayson_scripts.get("controlnet") or {}).get("args") or []
        for unit in args:
            if not isinstance(unit, dict):
                continue
            module = str(unit.get("module") or "")
            img_bytes = self._decode_base64_image(unit.get("image"))
            weight = unit.get("weight")
            try:
                weight_f = float(weight) if weight is not None else None
            except Exception:
                weight_f = None
            if module.lower().startswith("ip-adapter"):
                if img_bytes is not None:
                    bundle["identity_image"] = img_bytes
                bundle["ipadapter_file"] = str(unit.get("model") or bundle["ipadapter_file"])
                if weight_f is not None:
                    bundle["ipadapter_weight"] = weight_f
                bundle["ip_start"] = float(unit.get("guidance_start") or bundle["ip_start"])
                bundle["ip_end"] = float(unit.get("guidance_end") or bundle["ip_end"])
            else:
                if img_bytes is not None:
                    bundle["control_image"] = img_bytes
                bundle["control_net_name"] = str(unit.get("model") or bundle["control_net_name"])
                if weight_f is not None:
                    bundle["control_strength"] = weight_f
                bundle["control_start"] = float(unit.get("guidance_start") or bundle["control_start"])
                bundle["control_end"] = float(unit.get("guidance_end") or bundle["control_end"])
        return bundle

    def _apply_control_bundle(self, workflow: dict, bundle: dict, *, init_image: Optional[str] = None) -> None:
        """Inject ControlNet/IP-Adapter placeholders + strengths into a workflow."""
        for node in workflow.values():
            if not isinstance(node, dict):
                continue
            class_type = node.get("class_type")
            inputs = node.setdefault("inputs", {})
            if class_type == "LoadImage":
                if inputs.get("image") == "__CONTROL_IMAGE__":
                    inputs["image"] = bundle.get("control_upload") or inputs.get("image")
                if inputs.get("image") == "__IDENTITY_IMAGE__":
                    inputs["image"] = bundle.get("identity_upload") or inputs.get("image")
                if init_image and inputs.get("image") in {"__INIT_IMAGE__", "__INPUT_IMAGE__", "", None}:
                    inputs["image"] = init_image
            if class_type == "ControlNetLoader" and bundle.get("control_net_name"):
                inputs["control_net_name"] = bundle["control_net_name"]
            if class_type == "ControlNetApplyAdvanced":
                if "strength" in inputs:
                    inputs["strength"] = float(bundle.get("control_strength") or 0.0)
                if "start_percent" in inputs:
                    inputs["start_percent"] = float(bundle.get("control_start") or 0.0)
                if "end_percent" in inputs:
                    inputs["end_percent"] = float(bundle.get("control_end") or 1.0)
            if class_type == "IPAdapterModelLoader" and bundle.get("ipadapter_file"):
                inputs["ipadapter_file"] = bundle["ipadapter_file"]
            if class_type == "IPAdapterApply":
                if "weight" in inputs:
                    inputs["weight"] = float(bundle.get("ipadapter_weight") or 0.0)
                if "start_at" in inputs:
                    inputs["start_at"] = float(bundle.get("ip_start") or 0.0)
                if "end_at" in inputs:
                    inputs["end_at"] = float(bundle.get("ip_end") or 1.0)

    def generate_images(
        self,
        prompt: str,
        style: str | None,
        num_images: int,
        width: int = 640,
        height: int = 480,
        negative_prompt: str | None = None,
        cfg_scale: float | None = None,
        steps: int | None = None,
        seed: int | None = None,
        sampler: str | None = None,
        scheduler: str | None = None,
        model_id: str | None = None,
        vae_id: str | None = None,
        clip_id: str | None = None,
        loader_type: str = "standard",
        loras: Optional[List[dict]] = None,
        init_images: Optional[List[Union[bytes, str]]] = None,
        denoising_strength: Optional[float] = None,
        alwayson_scripts: Optional[dict] = None,
        override_settings: Optional[dict] = None,
        mask: Optional[Union[bytes, str]] = None,
        mask_blur: Optional[int] = None,
        inpaint_full_res: Optional[bool] = None,
        inpaint_full_res_padding: Optional[int] = None,
        workflow_set: Optional[str] = None,
        workflow_task: Optional[str] = None,
    ) -> List[bytes]:
        if override_settings or mask is not None:
            raise RuntimeError("ComfyUI pipeline does not support override_settings or inpainting")

        allow_controlnet = bool(alwayson_scripts) and "controlnet" in (alwayson_scripts or {})
        if allow_controlnet and not self._supports_controlnet_workflow():
            self.logger.warning("Disabling alwayson_scripts for ComfyUI: required nodes not available.")
            allow_controlnet = False
            alwayson_scripts = None
        workflow_set_final = workflow_set
        control_bundle = None
        if alwayson_scripts and not allow_controlnet:
            raise RuntimeError(
                "ComfyUI pipeline only supports alwayson_scripts=...controlnet...; choose workflow_set=mixed_cn_ipadapter"
            )
        if allow_controlnet:
            if workflow_set_final and workflow_set_final != "custom":
                self.logger.warning(
                    "alwayson_scripts.controlnet detected; using custom workflow (was %s). Note: mixed_cn_ipadapter disabled due to missing IPAdapterApply node",
                    workflow_set_final,
                )
            workflow_set_final = "custom"
            control_bundle = self._prepare_control_bundle(alwayson_scripts)
            control_bundle["control_upload"] = self._upload_image(control_bundle.get("control_image") or self._BLANK_PNG)
            control_bundle["identity_upload"] = self._upload_image(control_bundle.get("identity_image") or self._BLANK_PNG)

        prompt_text = self._build_prompt(prompt, style)
        prompt_text, prompt_loras = extract_lora_tokens(prompt_text)
        merged_loras = merge_loras(prompt_loras, loras)
        # Reasonable defaults when the caller doesn't specify.
        # (Higher-than-before defaults to avoid low-quality "draft" outputs.)
        safe_steps = steps if steps is not None else 34
        safe_cfg = cfg_scale if cfg_scale is not None else 6.0
        sampler = sampler or self._options_override.get("sampler_name") or self.settings.sd_comfy_sampler or "dpmpp_2m"
        scheduler = scheduler or self._options_override.get("scheduler") or self.settings.sd_comfy_scheduler or "karras"
        model_name = model_id or self._options_override.get("sd_model_checkpoint") or self.settings.sd_comfy_model or "sd3.5_large.safetensors"
        vae_name = vae_id or self._options_override.get("sd_vae") or self.settings.sd_comfy_vae or ""
        if self._is_cloud:
            if not workflow_set_final:
                workflow_set_final = "cloud_api"
            elif not str(workflow_set_final).startswith("cloud_api"):
                self.logger.info("Cloud API in use; forcing workflow_set=cloud_api (was %s).", workflow_set_final)
                workflow_set_final = "cloud_api"
            if loader_type == "gguf":
                loader_type = "standard"
            if isinstance(model_name, str) and model_name.lower().endswith(".gguf"):
                fallback_model = self.settings.sd_comfy_model or "flux1-dev-fp8.safetensors"
                if isinstance(fallback_model, str) and fallback_model.lower().endswith(".gguf"):
                    fallback_model = "flux1-dev-fp8.safetensors"
                model_name = fallback_model
            if isinstance(vae_name, str) and any(sep in vae_name for sep in ("\\", "/", ":")):
                vae_name = ""

        if negative_prompt:
            negative_prompt, _ = extract_lora_tokens(negative_prompt)

        if init_images:
            is_scene_cloud_workflow = (
                (workflow_task or "").strip().lower() == "scene"
                and isinstance(workflow_set_final, str)
                and workflow_set_final.startswith("cloud_api")
            )
            uploaded_inputs: list[str] = []
            if is_scene_cloud_workflow:
                # Keep positional mapping (image1=image location, image2/3=character slots).
                # Missing slots are intentionally filled with blank placeholders.
                scene_slots = list(init_images[:3])
                while len(scene_slots) < 3:
                    scene_slots.append(None)
                for image in scene_slots:
                    uploaded_inputs.append(self._upload_image(image if image is not None else self._BLANK_PNG))
            else:
                for image in init_images:
                    if image is None:
                        continue
                    uploaded_inputs.append(self._upload_image(image))
            if not uploaded_inputs:
                raise RuntimeError("No valid init_images provided for img2img workflow")

            denoise = denoising_strength if denoising_strength is not None else 0.5
            results: List[bytes] = []
            for idx in range(max(1, num_images)):
                seed_value = seed + idx if isinstance(seed, int) else random.randint(0, 2**32 - 1)
                input_name = uploaded_inputs[0]
                input_map: Optional[dict[str, str]] = None
                if is_scene_cloud_workflow:
                    # scene_img2img.json expects 3 images:
                    # location_ref.png, character_ref_1.png, character_ref_2.png
                    placeholders = ["location_ref.png", "character_ref_1.png", "character_ref_2.png"]
                    input_map = {placeholder: uploaded_inputs[idx_placeholder] for idx_placeholder, placeholder in enumerate(placeholders)}

                workflow, output_nodes = self._build_img2img_workflow(
                    prompt=prompt_text,
                    negative_prompt=negative_prompt,
                    steps=safe_steps,
                    cfg_scale=safe_cfg,
                    seed=seed_value,
                    sampler=sampler,
                    scheduler=scheduler,
                    model_name=model_name,
                    vae_name=vae_name,
                    denoise=denoise,
                    input_image=input_name,
                    input_images_map=input_map,
                    workflow_set=workflow_set_final,
                    workflow_task=workflow_task,
                )
                if control_bundle:
                    self._apply_control_bundle(workflow, control_bundle, init_image=input_name)
                self._apply_loras(workflow, merged_loras)
                prompt_id = self._queue_workflow(workflow)
                try:
                    images = self._wait_for_result(prompt_id, output_nodes)
                except RuntimeError as exc:
                    if (
                        self._is_cloud
                        and "content_moderated" in str(exc).lower()
                        and workflow_set_final == "cloud_api"
                    ):
                        self.logger.warning(
                            "ComfyUI Cloud moderation for job %s; retrying with denoise fallback workflow.",
                            prompt_id,
                        )
                        fallback_set = "cloud_api_fallback"
                        workflow, output_nodes = self._build_img2img_workflow(
                            prompt=prompt_text,
                            negative_prompt=negative_prompt,
                            steps=safe_steps,
                            cfg_scale=safe_cfg,
                            seed=seed_value,
                            sampler=sampler,
                            scheduler=scheduler,
                            model_name=model_name,
                            vae_name=vae_name,
                            denoise=denoise,
                            input_image=input_name,
                            input_images_map=input_map,
                            workflow_set=fallback_set,
                            workflow_task=workflow_task,
                        )
                        if control_bundle:
                            self._apply_control_bundle(workflow, control_bundle, init_image=input_name)
                        self._apply_loras(workflow, merged_loras)
                        prompt_id = self._queue_workflow(workflow)
                        images = self._wait_for_result(prompt_id, output_nodes)
                    else:
                        raise
                results.extend(self._fetch_images(images))
            return results

        results: List[bytes] = []
        for idx in range(max(1, num_images)):
            seed_value = seed + idx if isinstance(seed, int) else random.randint(0, 2**32 - 1)
            workflow, output_nodes = self._build_txt2img_workflow(
                prompt=prompt_text,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                steps=safe_steps,
                cfg_scale=safe_cfg,
                seed=seed_value,
                batch_size=1,
                sampler=sampler,
                scheduler=scheduler,
                model_name=model_name,
                vae_name=vae_name,
                workflow_set=workflow_set_final,
                workflow_task=workflow_task,
                clip_id=clip_id,
                loader_type=loader_type,
            )
            if control_bundle:
                self._apply_control_bundle(workflow, control_bundle)
            self._apply_loras(workflow, merged_loras)
            prompt_id = self._queue_workflow(workflow)
            images = self._wait_for_result(prompt_id, output_nodes)
            results.extend(self._fetch_images(images))
        return results

    def _fetch_outputs(self, outputs: list[dict]) -> List[bytes]:
        results: List[bytes] = []
        for item in outputs:
            filename = item.get("filename") or item.get("name") or item.get("path") or ""
            if not filename:
                continue
            subfolder = item.get("subfolder", "") or ""
            output_type = item.get("type", "output") or "output"
            params = {"filename": filename, "subfolder": subfolder, "type": output_type}
            try:
                results.append(self._get_bytes("/view", params))
            except Exception as exc:
                local_bytes = self._read_output_file(filename, subfolder, output_type)
                if local_bytes is None:
                    raise
                self.logger.warning("ComfyUI /view failed for %s: %s; using local output file.", filename, exc)
                results.append(local_bytes)
        return results

    def _fetch_images(self, images: list[dict]) -> List[bytes]:
        """Backward-compatible alias for existing image workflows."""
        return self._fetch_outputs(images)

    def execute_workflow_step1(
        self,
        prompt: str,
        negative_prompt: str = "",
        character_id: str = "",
        **kwargs
    ) -> dict:
        """Execute Step 1: Portrait generation using Qwen model stack"""
        
        try:
            # Load Step 1 workflow
            workflow_path = Path("tools/workflows/comfy_workflow_step1_hq_reference.json")
            if not workflow_path.exists():
                raise ValueError(f"Step 1 workflow not found: {workflow_path}")
            
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            # Replace parameter placeholders
            workflow_str = json.dumps(workflow)
            workflow_str = workflow_str.replace("{{prompt}}", prompt)
            workflow_str = workflow_str.replace("{{negative_prompt}}", negative_prompt)
            workflow_str = workflow_str.replace("{{character_id}}", character_id)
            
            # Apply parameter overrides
            workflow = json.loads(workflow_str)
            self._apply_workflow_parameters(workflow, **kwargs)
            
            # Execute workflow
            result = self._execute_comfy_workflow(workflow)
            
            # Extract output URL
            output_url = self._extract_workflow_output(result, character_id, "step1")
            
            return {
                "status": "success",
                "step": 1,
                "output_url": output_url,
                "workflow_result": result,
                "character_id": character_id
            }
            
        except Exception as e:
            self.logger.error(f"Step 1 execution failed: {e}")
            return {
                "status": "error",
                "step": 1,
                "error": str(e),
                "character_id": character_id
            }

    def execute_workflow_step2(
        self,
        reference_image_url: str,
        prompts: dict,
        character_id: str = "",
        use_wildcards: bool = True,
        **kwargs
    ) -> dict:
        """Execute Step 2: Multi-view generation using reference"""
        
        try:
            # Load Step 2 workflow
            workflow_path = Path("tools/workflows/comfy_workflow_step2_multiview_generation.json")
            if not workflow_path.exists():
                raise ValueError(f"Step 2 workflow not found: {workflow_path}")
            
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            # Convert reference URL to local filename
            reference_filename = self._url_to_local_filename(reference_image_url)
            
            # Replace parameter placeholders
            workflow_str = json.dumps(workflow)
            workflow_str = workflow_str.replace("{{reference_image}}", reference_filename)
            workflow_str = workflow_str.replace("{{character_id}}", character_id)
            workflow_str = workflow_str.replace("{{negative_prompt}}", "")
            
            # Replace view-specific prompts
            for view_name, prompt_text in prompts.items():
                placeholder = f"{{{{{view_name}_prompt}}}}"
                workflow_str = workflow_str.replace(placeholder, prompt_text)
            
            # Apply parameter overrides
            workflow = json.loads(workflow_str)
            self._apply_workflow_parameters(workflow, **kwargs)
            
            # Execute workflow
            result = self._execute_comfy_workflow(workflow)
            
            # Extract multiple output URLs
            output_urls = self._extract_multiview_outputs(result, character_id)
            
            return {
                "status": "success",
                "step": 2,
                "reference_url": reference_image_url,
                "output_urls": output_urls,
                "workflow_result": result,
                "character_id": character_id,
                "use_wildcards": use_wildcards
            }
            
        except Exception as e:
            self.logger.error(f"Step 2 execution failed: {e}")
            return {
                "status": "error",
                "step": 2,
                "error": str(e),
                "character_id": character_id,
                "reference_url": reference_image_url
            }

    def execute_workflow_step3(
        self,
        reference_image_url: str,
        scene_prompt: str,
        character_id: str = "",
        **kwargs
    ) -> dict:
        """Execute Step 3: Scene generation using character reference"""
        
        try:
            # Load Step 3 workflow
            workflow_path = Path("tools/workflows/comfy_workflow_step3_scene_generation.json")
            if not workflow_path.exists():
                raise ValueError(f"Step 3 workflow not found: {workflow_path}")
            
            with open(workflow_path, 'r', encoding='utf-8') as f:
                workflow = json.load(f)
            
            # Convert reference URL to local filename
            reference_filename = self._url_to_local_filename(reference_image_url)
            
            # Replace parameter placeholders
            workflow_str = json.dumps(workflow)
            workflow_str = workflow_str.replace("{{reference_image}}", reference_filename)
            workflow_str = workflow_str.replace("{{scene_prompt}}", scene_prompt)
            workflow_str = workflow_str.replace("{{character_id}}", character_id)
            workflow_str = workflow_str.replace("{{negative_prompt}}", "")
            
            # Apply parameter overrides
            workflow = json.loads(workflow_str)
            self._apply_workflow_parameters(workflow, **kwargs)
            
            # Execute workflow
            result = self._execute_comfy_workflow(workflow)
            
            # Extract output URL
            output_url = self._extract_workflow_output(result, character_id, "step3")
            
            return {
                "status": "success",
                "step": 3,
                "reference_url": reference_image_url,
                "output_url": output_url,
                "scene_prompt": scene_prompt,
                "workflow_result": result,
                "character_id": character_id
            }
            
        except Exception as e:
            self.logger.error(f"Step 3 execution failed: {e}")
            return {
                "status": "error",
                "step": 3,
                "error": str(e),
                "character_id": character_id,
                "reference_url": reference_image_url
            }

    def _apply_workflow_parameters(self, workflow: dict, **kwargs) -> None:
        """Apply parameter overrides to workflow nodes"""
        
        nodes = workflow.get('nodes', [])
        
        for node in nodes:
            node_type = node.get('type', '')
            widgets = node.get('widgets_values', [])
            
            # Update KSampler parameters
            if node_type == 'KSampler' and len(widgets) >= 7:
                if 'steps' in kwargs:
                    widgets[2] = kwargs['steps']
                if 'cfg' in kwargs:
                    widgets[3] = kwargs['cfg']
                if 'sampler' in kwargs:
                    widgets[4] = kwargs['sampler']
                if 'scheduler' in kwargs:
                    widgets[5] = kwargs['scheduler']
                if 'denoise' in kwargs:
                    widgets[6] = kwargs['denoise']
            
            # Update image dimensions
            elif node_type == 'EmptyLatentImage' and len(widgets) >= 3:
                if 'width' in kwargs:
                    widgets[0] = kwargs['width']
                if 'height' in kwargs:
                    widgets[1] = kwargs['height']
            
            # Update model loaders
            elif node_type == 'UnetLoaderGGUF' and widgets:
                if 'model' in kwargs:
                    widgets[0] = kwargs['model']
            
            elif node_type == 'CLIPLoaderGGUF' and len(widgets) >= 2:
                if 'clip' in kwargs:
                    widgets[0] = kwargs['clip']
                if 'clip_type' in kwargs:
                    widgets[1] = kwargs['clip_type']
            
            elif node_type == 'LoraLoader' and len(widgets) >= 3:
                if 'lora' in kwargs:
                    widgets[0] = kwargs['lora']
                if 'lora_strength_model' in kwargs:
                    widgets[1] = kwargs['lora_strength_model']
                if 'lora_strength_clip' in kwargs:
                    widgets[2] = kwargs['lora_strength_clip']
            
            elif node_type == 'VAELoader' and widgets:
                if 'vae' in kwargs:
                    widgets[0] = kwargs['vae']

    def _url_to_local_filename(self, url: str) -> str:
        """Convert asset URL to local filename for ComfyUI"""
        
        if not url or not url.startswith('/api/assets/'):
            return url  # Return as-is if not an asset URL
        
        parsed = urlsplit(url)
        rel_path = parsed.path[len("/api/assets/") :].lstrip("/")
        source_path = self.settings.assets_root_path / rel_path
        filename = source_path.name

        if not source_path.exists():
            self.logger.warning("ComfyUI input source missing: %s", source_path)
            return filename or url

        input_dir = Path(self.settings.comfyui_path) / "input"
        try:
            input_dir.mkdir(parents=True, exist_ok=True)
            target_path = input_dir / filename
            if source_path.resolve() != target_path.resolve():
                shutil.copy2(source_path, target_path)
        except Exception as exc:
            self.logger.warning("Failed to prepare ComfyUI input file %s: %s", source_path, exc)

        return filename

    def _extract_workflow_output(self, result: dict, character_id: str, step: str) -> str:
        """Extract single output URL from workflow result"""
        
        if 'images' in result:
            images = result['images']
            if images and len(images) > 0:
                first_image = images[0]
                if isinstance(first_image, dict):
                    return first_image.get('url') or first_image.get('filename')
                return str(first_image)
        
        return None

    def _extract_multiview_outputs(self, result: dict, character_id: str) -> list:
        """Extract multiple output URLs from Step 2 multiview result"""
        
        output_urls = []
        
        if 'images' in result:
            images = result['images']
            for img in images:
                if isinstance(img, dict):
                    url = img.get('url') or img.get('filename')
                else:
                    url = str(img)
                
                if url:
                    output_urls.append(url)
        
        # Ensure we have exactly 3 outputs (front, back, side)
        while len(output_urls) < 3:
            output_urls.append(None)
        
        return output_urls[:3]

    async def _execute_comfy_workflow(self, workflow: dict) -> dict:
        """Execute workflow via ComfyUI API"""
        
        try:
            # Use existing workflow execution method
            output_nodes = self._parse_output_nodes(workflow, "")
            images_by_node = self.run_workflow(workflow, output_nodes)
            
            # Convert to expected format
            return {
                "images": [
                    {"url": f"/api/assets/temp/{i}.png", "filename": f"temp_{i}.png"}
                    for i, images in enumerate(images_by_node)
                    if images
                ]
            }
        except Exception as e:
            self.logger.error(f"ComfyUI workflow execution failed: {e}")
            raise


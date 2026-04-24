from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from app.infra.sd_request_layer import get_sd_layer


ASSET_ORIGIN_GENERATED = "generated"
ASSET_ORIGIN_UPLOADED = "uploaded"

_PROVIDER_LABELS = {
    "a1111": "A1111",
    "comfy": "ComfyUI",
    "comfy_api": "ComfyUI API",
    "poe_api": "Poe Image",
}


def current_sd_provider() -> str:
    client = get_sd_layer().client
    provider = getattr(client, "provider_name", None)
    if isinstance(provider, str) and provider.strip():
        return provider.strip()
    return "a1111"


def provider_label(provider: Optional[str]) -> str:
    key = (provider or "").strip().lower()
    return _PROVIDER_LABELS.get(key, provider or "unknown")


def build_generated_marker(
    *,
    asset_kind: Optional[str] = None,
    slot: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    provider = current_sd_provider()
    marker: dict[str, Any] = {
        "origin": ASSET_ORIGIN_GENERATED,
        "provider": provider,
        "provider_label": provider_label(provider),
        "asset_kind": asset_kind,
        "slot": slot,
        "marked_at": datetime.utcnow().isoformat(),
    }
    if isinstance(extra, dict):
        marker.update({key: value for key, value in extra.items() if value is not None})
    return marker


def build_uploaded_marker(
    *,
    filename: Optional[str] = None,
    asset_kind: Optional[str] = None,
    slot: Optional[str] = None,
    replaced_url: Optional[str] = None,
    extra: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    marker: dict[str, Any] = {
        "origin": ASSET_ORIGIN_UPLOADED,
        "provider": "upload",
        "provider_label": "Upload",
        "asset_kind": asset_kind,
        "slot": slot,
        "filename": filename,
        "replaced_url": replaced_url,
        "marked_at": datetime.utcnow().isoformat(),
    }
    if isinstance(extra, dict):
        marker.update({key: value for key, value in extra.items() if value is not None})
    return marker


def merge_ref_meta(meta: Optional[dict[str, Any]], marker: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(meta) if isinstance(meta, dict) else {}
    result["asset_source"] = marker
    result["asset_origin"] = marker.get("origin")
    result["asset_provider"] = marker.get("provider")
    result["asset_provider_label"] = marker.get("provider_label")
    return result


def upsert_asset_marker(container: Optional[dict[str, Any]], asset_key: str, marker: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(container) if isinstance(container, dict) else {}
    asset_sources = result.get("asset_sources")
    if not isinstance(asset_sources, dict):
        asset_sources = {}
    asset_sources[asset_key] = marker
    result["asset_sources"] = asset_sources
    return result

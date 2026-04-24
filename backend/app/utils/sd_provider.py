from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


_LOCAL_ALIASES = {"", "local", "default", "system"}
_COMFY_API_ALIASES = {
    "comfy_api",
    "comfyui_api",
    "comfy_cloud",
    "comfyui_cloud",
    "comfy_cloud_api",
    "comfyui_cloud_api",
}
_COMFY_ALIASES = {"comfy", "comfyui"}
_A1111_ALIASES = {"a1111", "forge", "webui"}
_POE_API_ALIASES = {"poe", "poe_api", "poe_image", "poe_image_api"}


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def normalize_sd_provider(value: Optional[str]) -> Optional[str]:
    """Normalize provider names.

    Returns None for "local"/empty to indicate default provider.
    """
    cleaned = _clean_optional(value)
    if not cleaned:
        return None
    name = cleaned.lower()
    if name in _LOCAL_ALIASES:
        return None
    if name in _COMFY_API_ALIASES:
        return "comfy_api"
    if name in _COMFY_ALIASES:
        return "comfy"
    if name in _A1111_ALIASES:
        return "a1111"
    if name in _POE_API_ALIASES:
        return "poe_api"
    return name


@dataclass(frozen=True)
class SDProviderOverrides:
    provider: Optional[str] = None
    comfy_api_key: Optional[str] = None
    comfy_url: Optional[str] = None
    poe_api_key: Optional[str] = None
    poe_url: Optional[str] = None
    poe_model: Optional[str] = None

    def normalized(self) -> "SDProviderOverrides":
        return SDProviderOverrides(
            provider=normalize_sd_provider(self.provider),
            comfy_api_key=_clean_optional(self.comfy_api_key),
            comfy_url=_clean_optional(self.comfy_url),
            poe_api_key=_clean_optional(self.poe_api_key),
            poe_url=_clean_optional(self.poe_url),
            poe_model=_clean_optional(self.poe_model),
        )

    def has_overrides(self) -> bool:
        return bool(
            self.provider
            or self.comfy_api_key
            or self.comfy_url
            or self.poe_api_key
            or self.poe_url
            or self.poe_model
        )

    def to_config(self) -> dict:
        data: dict = {}
        if self.provider:
            data["sd_provider"] = self.provider
        if self.comfy_api_key:
            data["sd_comfy_api_key"] = self.comfy_api_key
        if self.comfy_url:
            data["sd_comfy_url"] = self.comfy_url
        if self.poe_api_key:
            data["sd_poe_api_key"] = self.poe_api_key
        if self.poe_url:
            data["sd_poe_api_url"] = self.poe_url
        if self.poe_model:
            data["sd_poe_model"] = self.poe_model
        return data

    @classmethod
    def from_config(cls, config: dict | None) -> "SDProviderOverrides":
        if not isinstance(config, dict):
            return cls()
        return cls(
            provider=config.get("sd_provider"),
            comfy_api_key=config.get("sd_comfy_api_key"),
            comfy_url=config.get("sd_comfy_url"),
            poe_api_key=config.get("sd_poe_api_key"),
            poe_url=config.get("sd_poe_api_url"),
            poe_model=config.get("sd_poe_model"),
        ).normalized()

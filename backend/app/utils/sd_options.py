from __future__ import annotations

from typing import Any, Optional


def _pick_str(options: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = options.get(key)
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
    return None


def extract_sd_option_overrides(options: dict[str, Any] | None) -> dict[str, str]:
    data = options or {}
    overrides: dict[str, str] = {}

    model = _pick_str(data, "sd_model_checkpoint", "model_checkpoint", "model_id", "model")
    if model:
        overrides["model_checkpoint"] = model

    vae = _pick_str(data, "sd_vae", "vae", "vae_id")
    if vae:
        overrides["vae"] = vae

    sampler = _pick_str(data, "sampler_name", "sampler")
    if sampler:
        overrides["sampler"] = sampler

    scheduler = _pick_str(data, "scheduler", "scheduler_name")
    if scheduler:
        overrides["scheduler"] = scheduler

    return overrides

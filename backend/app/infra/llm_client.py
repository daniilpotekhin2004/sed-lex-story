from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import get_settings
from app.infra.ai_backoff import NonRetryableAIError, RetryableAIError


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float
    top_p: float
    frequency_penalty: float
    presence_penalty: float
    max_tokens: int
    timeout: float


class LLMConfigError(RuntimeError):
    pass


def _default_access_dat_path() -> Path:
    return Path(__file__).resolve().parents[3] / "access.dat"


def _read_access_dat(path: Path) -> Optional[Dict[str, Optional[str]]]:
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return None

    if raw.startswith("{"):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        return {
            "api_key": parsed.get("apiKey") or parsed.get("key") or parsed.get("OPENAI_API_KEY"),
            "base_url": parsed.get("baseURL") or parsed.get("baseUrl") or parsed.get("OPENAI_BASE_URL"),
            "model": parsed.get("model") or parsed.get("OPENAI_MODEL"),
        }

    api_key = None
    base_url = None
    model = None
    for line in raw.splitlines():
        if not api_key:
            key_match = re.search(r"sk-[a-zA-Z0-9]+", line)
            if key_match:
                api_key = key_match.group(0)
        if not base_url:
            url_match = re.search(r"https?://\S+", line)
            if url_match:
                base_url = url_match.group(0)
        if not model:
            model_match = re.search(r"model\s*=\s*['\"]?([\w.-]+)['\"]?", line)
            if model_match:
                model = model_match.group(1)
            else:
                fallback = re.search(r"gpt-[\w.-]+", line)
                if fallback:
                    model = fallback.group(0)

    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


def _resolve_llm_config() -> LLMConfig:
    settings = get_settings()

    access_dat_path = Path(
        settings.llm_access_dat_path or os.getenv("ACCESS_DAT_PATH") or _default_access_dat_path()
    )
    access_dat = _read_access_dat(access_dat_path)

    api_key = settings.llm_api_key or (access_dat and access_dat.get("api_key"))
    base_url = settings.llm_base_url or (access_dat and access_dat.get("base_url"))
    model = settings.llm_model or (access_dat and access_dat.get("model"))

    temperature = settings.llm_temperature
    if temperature is None:
        env_temp = os.getenv("TEMPERATURE")
        temperature = float(env_temp) if env_temp else 0.7
    top_p = settings.llm_top_p
    if top_p is None:
        top_p = 0.9
    frequency_penalty = settings.llm_frequency_penalty
    if frequency_penalty is None:
        frequency_penalty = 0.0
    presence_penalty = settings.llm_presence_penalty
    if presence_penalty is None:
        presence_penalty = 0.0

    max_tokens = settings.llm_max_tokens
    if max_tokens is None:
        env_tokens = os.getenv("MAX_TOKENS")
        max_tokens = int(env_tokens) if env_tokens else 800

    base_url = base_url or "https://api.artemox.com/v1"
    model = model or "gpt-4o-mini"

    if not api_key:
        raise LLMConfigError(
            "Missing LLM API key. Set OPENAI_API_KEY or provide access.dat with a key."
        )

    return LLMConfig(
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        model=model,
        temperature=temperature,
        top_p=top_p,
        frequency_penalty=frequency_penalty,
        presence_penalty=presence_penalty,
        max_tokens=max_tokens,
        timeout=settings.llm_timeout_seconds or 30.0,
    )


async def create_chat_completion(
    *,
    messages: List[Dict[str, str]],
    temperature: Optional[float] = None,
    top_p: Optional[float] = None,
    frequency_penalty: Optional[float] = None,
    presence_penalty: Optional[float] = None,
    max_tokens: Optional[int] = None,
    model: Optional[str] = None,
    response_format: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    cfg = _resolve_llm_config()
    payload = {
        "model": model or cfg.model,
        "messages": messages,
        "temperature": cfg.temperature if temperature is None else temperature,
        "top_p": cfg.top_p if top_p is None else top_p,
        "frequency_penalty": cfg.frequency_penalty if frequency_penalty is None else frequency_penalty,
        "presence_penalty": cfg.presence_penalty if presence_penalty is None else presence_penalty,
        "max_tokens": cfg.max_tokens if max_tokens is None else max_tokens,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    url = f"{cfg.base_url}/chat/completions"

    async with httpx.AsyncClient(timeout=cfg.timeout) as client:
        response = await client.post(
            url,
            headers={"Authorization": f"Bearer {cfg.api_key}"},
            json=payload,
        )

    if response.status_code in {429} or 500 <= response.status_code < 600:
        body = (response.text or "").strip()
        if len(body) > 4000:
            body = body[:4000] + f"...<truncated:{len(body) - 4000}>"
        message = f"LLM request failed with {response.status_code}"
        if body:
            message = f"{message}: {body}"
        raise RetryableAIError(
            message,
            status_code=response.status_code,
        )

    if response.status_code >= 400:
        raise NonRetryableAIError(
            f"LLM request failed with {response.status_code}: {response.text}",
            status_code=response.status_code,
        )

    data = response.json()
    if not isinstance(data, dict):
        raise NonRetryableAIError("LLM response is not JSON", status_code=response.status_code)

    return data

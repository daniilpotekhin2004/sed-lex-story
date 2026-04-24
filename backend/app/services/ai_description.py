from __future__ import annotations

from typing import Tuple

import httpx
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.infra.ai_backoff import NonRetryableAIError, RetryableAIError, run_with_backoff
from app.infra.llm_client import LLMConfigError, create_chat_completion
from app.schemas.ai import AIDescriptionRequest, AIDescriptionResponse


class AIDescriptionService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _build_prompts(self, payload: AIDescriptionRequest) -> Tuple[str, str]:
        language = payload.language or "ru"
        tone = payload.tone.strip() if payload.tone else ""
        context = payload.context.strip() if payload.context else ""
        if len(context) > 2000:
            context = context[:2000] + "..."

        system = (
            "You are a narrative assistant for an interactive legal quest platform. "
            f"Write a concise description in {language}. "
            "Use 2-4 sentences, no markdown, no bullet lists."
        )

        user_lines = [
            f"Entity type: {payload.entity_type}",
            f"Name: {payload.name}",
        ]
        if tone:
            user_lines.append(f"Tone: {tone}")
        if context:
            user_lines.append("Context:\n" + context)

        user = "\n".join(user_lines)
        return system, user

    async def generate_description(self, payload: AIDescriptionRequest) -> AIDescriptionResponse:
        system_prompt, user_prompt = self._build_prompts(payload)

        async def _call_llm() -> dict:
            return await create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )

        try:
            response = await run_with_backoff(
                _call_llm,
                retries=self.settings.llm_max_retries,
                base_delay=self.settings.llm_backoff_base,
                max_delay=self.settings.llm_backoff_max,
                retry_on=(RetryableAIError, httpx.RequestError),
            )
        except LLMConfigError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            )
        except RetryableAIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM request failed after retries: {exc}",
            )
        except NonRetryableAIError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"LLM request failed: {exc}",
            )
        except httpx.RequestError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM request error: {exc}",
            )

        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not content:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="LLM returned an empty response",
            )

        return AIDescriptionResponse(
            description=content,
            model=response.get("model"),
            usage=response.get("usage"),
            request_id=response.get("id"),
        )


from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.domain.models import (
    Artifact,
    CharacterPreset,
    Location,
    Project,
    ScenarioGraph,
    SceneNode,
    Edge,
)
from app.infra.ai_backoff import NonRetryableAIError, RetryableAIError, run_with_backoff
from app.infra.llm_client import LLMConfigError, create_chat_completion
from app.schemas.narrative_ai import (
    AISceneDraftRequest,
    AISceneDraftResponse,
    AIScenarioDraftRequest,
    AIScenarioDraftResponse,
    AIScenarioDraftScene,
    AIScenarioDraftEdge,
    NarrativeScriptLine,
)

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> Dict[str, Any]:
    raw = (text or "").strip()
    if not raw:
        return {}
    # 1) direct parse
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    # 2) best-effort: grab first {...}
    match = re.search(r"\{[\s\S]*\}", raw)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _normalize_detail_level(detail: str | None) -> str:
    value = (detail or "standard").strip().lower()
    return value if value in {"narrow", "standard", "detailed"} else "standard"


def _safe_str(value: Any, *, max_len: int = 600) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) > max_len:
        return text[: max_len - 3] + "..."
    return text


def _infer_time_of_day(prev: Optional[str]) -> str:
    prev_norm = (prev or "").strip().lower()
    if prev_norm in {"morning", "day", "afternoon", "evening", "night", "dawn", "dusk"}:
        return prev_norm
    return "day"


def _compute_plot_position(current_index: int, total_target: Optional[int]) -> str:
    if not total_target or total_target <= 1:
        return "unknown"
    # Clamp
    idx = max(1, min(current_index, total_target))
    ratio = idx / float(total_target)
    if ratio <= 0.2:
        return "setup"
    if ratio <= 0.4:
        return "inciting"
    if ratio <= 0.7:
        return "rising_action"
    if ratio <= 0.9:
        return "climax"
    return "resolution"


@dataclass
class _LLMReply:
    payload: Dict[str, Any]
    model: Optional[str]
    usage: Optional[dict]
    request_id: Optional[str]


class NarrativeAIService:
    """Project-aware narrative generation helpers.

    This module focuses on *structured* narrative outputs:
    - every scene has a time_of_day;
    - if sound_mode is enabled, every scene includes a `script` array
      (exposition/thought/dialogue lines) suitable for TTS.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.settings = get_settings()

    async def draft_scenario(self, project_id: str, req: AIScenarioDraftRequest) -> AIScenarioDraftResponse:
        project = await self._load_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        characters = await self._load_project_characters(project_id)
        locations = await self._load_project_locations(project_id)
        artifacts = await self._load_project_artifacts(project_id)
        style_bible = getattr(project, "style_bible", None)

        system_prompt, user_prompt = self._build_scenario_prompt(
            project=project,
            characters=characters,
            locations=locations,
            artifacts=artifacts,
            style_bible=style_bible,
            req=req,
        )

        reply = await self._call_llm(system_prompt, user_prompt, temperature=0.4)
        draft = self._coerce_scenario_draft(reply.payload, req=req)
        draft.model = reply.model
        draft.usage = reply.usage
        draft.request_id = reply.request_id

        if req.persist:
            persisted = await self._persist_scenario_draft(project_id, draft)
            persisted.model = draft.model
            persisted.usage = draft.usage
            persisted.request_id = draft.request_id
            return persisted

        return draft

    async def draft_scene(self, graph_id: str, req: AISceneDraftRequest) -> AISceneDraftResponse:
        graph = await self._load_graph(graph_id)
        if graph is None:
            raise HTTPException(status_code=404, detail="Graph not found")
        project = graph.project
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")

        characters = await self._load_project_characters(project.id)
        locations = await self._load_project_locations(project.id)
        artifacts = await self._load_project_artifacts(project.id)

        previous_scene = None
        if req.previous_scene_id:
            previous_scene = await self.session.get(SceneNode, req.previous_scene_id)
            if previous_scene is None:
                raise HTTPException(status_code=404, detail="Previous scene not found")

        scene_summaries = await self._build_scene_summaries(graph_id)
        system_prompt, user_prompt = self._build_scene_prompt(
            project=project,
            graph=graph,
            characters=characters,
            locations=locations,
            artifacts=artifacts,
            previous_scene=previous_scene,
            scene_summaries=scene_summaries,
            req=req,
        )

        reply = await self._call_llm(system_prompt, user_prompt, temperature=0.5)
        result = self._coerce_scene_draft(reply.payload, req=req)
        result.model = reply.model
        result.usage = reply.usage
        result.request_id = reply.request_id
        return result

    # ------------------------ prompt builders ------------------------

    def _build_scenario_prompt(
        self,
        *,
        project: Project,
        characters: List[CharacterPreset],
        locations: List[Location],
        artifacts: List[Artifact],
        style_bible: Any,
        req: AIScenarioDraftRequest,
    ) -> Tuple[str, str]:
        language = (req.language or "ru").strip()
        detail = _normalize_detail_level(req.detail_level)
        story_outline = _safe_str(getattr(project, "story_outline", None) or project.description or "")
        if req.extra_context:
            story_outline = (story_outline + "\n\n" + _safe_str(req.extra_context, max_len=1200)).strip()

        dialogue_rules = ""
        narrative_rules = ""
        if style_bible is not None:
            try:
                narrative_rules = _safe_str(getattr(style_bible, "narrative_rules", None), max_len=900)
                dialogue_format = getattr(style_bible, "dialogue_format", None)
                if dialogue_format:
                    dialogue_rules = _safe_str(json.dumps(dialogue_format, ensure_ascii=False), max_len=600)
            except Exception:
                pass

        system = (
            "You are a narrative designer for an interactive branching quest platform. "
            "You convert a story outline into a structured scenario graph. "
            "Return ONLY valid JSON. No markdown. "
            f"All string fields MUST be in {language}. "
            "Every scene must specify time_of_day and include a short synopsis. "
            "Decision scenes must include choices.")

        detail_hint = {
            "narrow": "Keep scenes short. 1-2 paragraphs of content.",
            "standard": "Keep content concise but vivid (2-5 paragraphs).",
            "detailed": "Add richer detail (4-8 paragraphs) while staying consistent.",
        }[detail]

        cast_lines = []
        for c in characters[:40]:
            cast_lines.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "role": c.character_type,
                    "description": c.description,
                    "voice_profile": c.voice_profile,
                }
            )
        loc_lines = []
        for l in locations[:40]:
            loc_lines.append({"id": l.id, "name": l.name, "description": l.description})
        art_lines = []
        for a in artifacts[:40]:
            art_lines.append({"id": a.id, "name": a.name, "description": a.description})

        user_payload = {
            "goal": "Draft a branching scenario graph",
            "constraints": {
                "target_scenes": req.target_scenes,
                "max_branching": req.max_branching,
                "detail_level": detail,
                "detail_hint": detail_hint,
                "sound_mode": bool(req.sound_mode),
            },
            "project": {
                "id": project.id,
                "name": project.name,
                "story_outline": story_outline,
            },
            "style_bible": {
                "narrative_rules": narrative_rules or None,
                "dialogue_format": dialogue_rules or None,
            },
            "entities": {
                "characters": cast_lines,
                "locations": loc_lines,
                "artifacts": art_lines,
            },
            "output_schema": {
                "graph_title": "string",
                "graph_description": "string|null",
                "scenes": [
                    {
                        "temp_id": "s1",
                        "scene_type": "story|decision",
                        "order_index": 1,
                        "title": "string",
                        "synopsis": "string",
                        "content": "string",
                        "location_id": "optional location id from list or null",
                        "suggested_character_ids": ["character ids"],
                        "context": {
                            "time_of_day": "morning|day|afternoon|evening|night|dawn|dusk",
                            "time_of_day_note": "string",
                            "render": {"shot": "medium|portrait|establishing|action", "lighting": "time_of_day value", "mood": "tense|calm|heroic|mysterious|romantic|neutral"},
                        },
                        "script": [
                            {"kind": "exposition|thought|dialogue", "text": "string", "speaker_name": "optional", "character_id": "optional"}
                        ],
                        "choices": [
                            {"label": "choice label", "condition": "optional", "to_temp_id": "s2"}
                        ]
                    }
                ],
                "edges": [
                    {"from_temp_id": "s1", "to_temp_id": "s2", "choice_label": "optional", "condition": "optional"}
                ],
            },
            "notes": [
                "Prefer using existing character/location ids when applicable.",
                "If a scene does not change time_of_day, keep it and explain in time_of_day_note.",
                "Ensure the graph has at least 1 decision node when max_branching>1.",
            ],
        }
        # Allow caller to override titles
        if req.graph_title:
            user_payload["graph_title"] = req.graph_title
        if req.graph_description:
            user_payload["graph_description"] = req.graph_description

        user = json.dumps(user_payload, ensure_ascii=False)
        return system, user

    def _build_scene_prompt(
        self,
        *,
        project: Project,
        graph: ScenarioGraph,
        characters: List[CharacterPreset],
        locations: List[Location],
        artifacts: List[Artifact],
        previous_scene: Optional[SceneNode],
        scene_summaries: List[Dict[str, Any]],
        req: AISceneDraftRequest,
    ) -> Tuple[str, str]:
        language = (req.language or "ru").strip()
        detail = _normalize_detail_level(req.detail_level)
        detail_hint = {
            "narrow": "Keep content short and focused (1-2 paragraphs).",
            "standard": "Keep content concise but vivid (2-5 paragraphs).",
            "detailed": "Add richer detail (4-8 paragraphs) while staying consistent.",
        }[detail]

        story_outline = _safe_str(getattr(project, "story_outline", None) or project.description or "", max_len=1800)

        prev_ctx = (previous_scene.context or {}) if previous_scene is not None else {}
        prev_time = None
        if isinstance(prev_ctx, dict):
            prev_time = prev_ctx.get("time_of_day")
        time_hint = _infer_time_of_day(prev_time)

        next_order = 1
        if scene_summaries:
            try:
                next_order = int(scene_summaries[-1].get("order_index") or len(scene_summaries) or 0) + 1
            except Exception:
                next_order = len(scene_summaries) + 1

        plot_pos = _compute_plot_position(next_order, req.target_total_scenes)

        cast_lines = []
        for c in characters[:30]:
            cast_lines.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "role": c.character_type,
                    "description": c.description,
                    "voice_profile": c.voice_profile,
                }
            )
        loc_lines = []
        for l in locations[:30]:
            loc_lines.append({"id": l.id, "name": l.name, "description": l.description})
        art_lines = []
        for a in artifacts[:30]:
            art_lines.append({"id": a.id, "name": a.name, "description": a.description})

        system = (
            "You are a narrative designer for an interactive branching quest platform. "
            "You draft ONE scene in a structured form that can later be rendered to images and optionally voiced. "
            "Return ONLY valid JSON. No markdown. "
            f"All string fields MUST be in {language}. "
            "Every scene must include time_of_day and time_of_day_note. "
            "If sound_mode is true, include a scene script array of lines (exposition/thought/dialogue)."
        )

        user_payload = {
            "goal": "Draft the next scene",
            "constraints": {
                "detail_level": detail,
                "detail_hint": detail_hint,
                "sound_mode": bool(req.sound_mode),
                "include_render_hints": bool(req.include_render_hints),
                "preferred_time_of_day": time_hint,
                "plot_position": plot_pos,
                "next_order_index": next_order,
            },
            "project": {
                "id": project.id,
                "name": project.name,
                "story_outline": story_outline,
            },
            "graph": {
                "id": graph.id,
                "title": graph.title,
                "description": graph.description,
            },
            "previous_scene": {
                "id": previous_scene.id if previous_scene else None,
                "title": previous_scene.title if previous_scene else None,
                "synopsis": previous_scene.synopsis if previous_scene else None,
                "scene_type": previous_scene.scene_type if previous_scene else None,
                "time_of_day": prev_time,
            },
            "existing_scenes_summary": scene_summaries[-12:],
            "entities": {
                "characters": cast_lines,
                "locations": loc_lines,
                "artifacts": art_lines,
            },
            "instruction": (req.instruction or "").strip() or None,
            "output_schema": {
                "title": "string",
                "synopsis": "string",
                "content": "string",
                "scene_type": "story|decision",
                "order_index": "integer",
                "location_id": "optional location id or null",
                "suggested_character_ids": ["character ids"],
                "time_of_day": "morning|day|afternoon|evening|night|dawn|dusk",
                "time_of_day_note": "string",
                "render": {"shot": "medium|portrait|establishing|action", "lighting": "time_of_day value", "mood": "tense|calm|heroic|mysterious|romantic|neutral"},
                "script": [
                    {"kind": "exposition|thought|dialogue", "text": "string", "speaker_name": "optional", "character_id": "optional"}
                ],
                "choices": [
                    {"label": "choice label", "condition": "optional"}
                ],
            },
        }
        user = json.dumps(user_payload, ensure_ascii=False)
        return system, user

    # ------------------------ LLM wrapper ------------------------

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float,
    ) -> _LLMReply:
        async def _call() -> dict:
            return await create_chat_completion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
            )

        try:
            response = await run_with_backoff(
                _call,
                retries=self.settings.llm_max_retries,
                base_delay=self.settings.llm_backoff_base,
                max_delay=self.settings.llm_backoff_max,
                retry_on=(RetryableAIError, httpx.RequestError),
            )
        except LLMConfigError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        except RetryableAIError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"LLM request failed after retries: {exc}",
            )
        except NonRetryableAIError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"LLM request failed: {exc}")
        except httpx.RequestError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"LLM request error: {exc}")

        content = (
            response.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        if not content:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM returned an empty response")

        payload = _extract_json(content)
        if not payload:
            # Provide a hint for debugging without leaking huge content
            logger.warning("LLM returned non-JSON content: %s", content[:500])
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="LLM returned invalid JSON")

        return _LLMReply(
            payload=payload,
            model=response.get("model"),
            usage=response.get("usage"),
            request_id=response.get("id"),
        )

    # ------------------------ coercion / validation ------------------------

    def _coerce_scene_draft(self, data: Dict[str, Any], *, req: AISceneDraftRequest) -> AISceneDraftResponse:
        title = _safe_str(data.get("title") or "Сцена")
        synopsis = _safe_str(data.get("synopsis") or data.get("summary") or "")
        content = _safe_str(data.get("content") or "")

        scene_type = (data.get("scene_type") or "story").strip().lower()
        if scene_type not in {"story", "decision"}:
            scene_type = "story"

        order_index = data.get("order_index")
        try:
            order_index = int(order_index) if order_index is not None else None
        except Exception:
            order_index = None

        location_id = data.get("location_id")
        if location_id is not None:
            location_id = str(location_id).strip() or None

        suggested_character_ids = []
        raw_chars = data.get("suggested_character_ids") or data.get("characters") or []
        if isinstance(raw_chars, list):
            suggested_character_ids = [str(x).strip() for x in raw_chars if str(x).strip()]

        # Base context (if LLM nested fields under "context").
        ctx = data.get("context") if isinstance(data.get("context"), dict) else {}

        # Time-of-day: enforce always
        time_of_day = (data.get("time_of_day") or ctx.get("time_of_day") or "").strip().lower()
        if time_of_day not in {"morning", "day", "afternoon", "evening", "night", "dawn", "dusk"}:
            time_of_day = "day"
        time_of_day_note = _safe_str(data.get("time_of_day_note") or ctx.get("time_of_day_note") or "")
        if not time_of_day_note:
            time_of_day_note = "Время суток сохранено." if time_of_day else "Время суток задано."  # ru fallback

        render = (
            data.get("render")
            if isinstance(data.get("render"), dict)
            else (ctx.get("render") if isinstance(ctx.get("render"), dict) else {})
        )
        # Merge/override context with required time fields
        merged_ctx: Dict[str, Any] = {}
        merged_ctx.update(ctx)
        merged_ctx["time_of_day"] = time_of_day
        merged_ctx["time_of_day_note"] = time_of_day_note
        if req.include_render_hints:
            # Normalize and attach under `render`
            merged_ctx.setdefault("render", {})
            if isinstance(merged_ctx["render"], dict):
                merged_ctx["render"].update(render or {})
                merged_ctx["render"].setdefault("lighting", time_of_day)

        # Script
        script_items: List[NarrativeScriptLine] = []
        raw_script = data.get("script") or ctx.get("script") or []
        if req.sound_mode and isinstance(raw_script, list):
            for item in raw_script[:200]:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("kind") or "dialogue").strip().lower()
                if kind not in {"exposition", "thought", "dialogue"}:
                    kind = "dialogue"
                text = _safe_str(item.get("text") or "")
                if not text:
                    continue
                script_items.append(
                    NarrativeScriptLine(
                        kind=kind,
                        text=text,
                        speaker_name=_safe_str(item.get("speaker_name"), max_len=120) or None,
                        character_id=_safe_str(item.get("character_id"), max_len=64) or None,
                        emotion=_safe_str(item.get("emotion"), max_len=120) or None,
                    )
                )

        choices = []
        raw_choices = data.get("choices") or ctx.get("choices") or []
        if scene_type == "decision" and isinstance(raw_choices, list):
            for ch in raw_choices[:10]:
                if not isinstance(ch, dict):
                    continue
                label = _safe_str(ch.get("label") or ch.get("choice") or "")
                if not label:
                    continue
                choices.append(
                    {
                        "label": label,
                        "condition": _safe_str(ch.get("condition") or "") or None,
                    }
                )

        return AISceneDraftResponse(
            title=title,
            synopsis=synopsis,
            content=content,
            scene_type=scene_type,
            order_index=order_index,
            location_id=location_id,
            suggested_character_ids=suggested_character_ids,
            script=script_items,
            context=merged_ctx,
            choices=choices,
        )

    def _coerce_scenario_draft(self, data: Dict[str, Any], *, req: AIScenarioDraftRequest) -> AIScenarioDraftResponse:
        title = _safe_str(data.get("graph_title") or data.get("title") or req.graph_title or "Сценарий")
        description = _safe_str(data.get("graph_description") or data.get("description") or req.graph_description or "") or None

        raw_scenes = data.get("scenes") or []
        if not isinstance(raw_scenes, list) or not raw_scenes:
            raise HTTPException(status_code=502, detail="LLM did not return scenes")

        scenes: List[AIScenarioDraftScene] = []
        for idx, raw in enumerate(raw_scenes[:req.target_scenes]):
            if not isinstance(raw, dict):
                continue
            temp_id = _safe_str(raw.get("temp_id") or f"s{idx+1}", max_len=20)
            scene_type = (raw.get("scene_type") or "story").strip().lower()
            if scene_type not in {"story", "decision"}:
                scene_type = "story"
            order_index = raw.get("order_index")
            try:
                order_index = int(order_index)
            except Exception:
                order_index = idx + 1

            location_id = raw.get("location_id")
            location_id = str(location_id).strip() if location_id else None

            suggested_character_ids: List[str] = []
            raw_chars = raw.get("suggested_character_ids") or raw.get("characters") or []
            if isinstance(raw_chars, list):
                suggested_character_ids = [str(x).strip() for x in raw_chars if str(x).strip()]

            ctx = raw.get("context") if isinstance(raw.get("context"), dict) else {}
            time_of_day = (ctx.get("time_of_day") or raw.get("time_of_day") or "").strip().lower()
            if time_of_day not in {"morning", "day", "afternoon", "evening", "night", "dawn", "dusk"}:
                time_of_day = "day"
            ctx["time_of_day"] = time_of_day
            note = _safe_str(ctx.get("time_of_day_note") or raw.get("time_of_day_note") or "")
            ctx["time_of_day_note"] = note or "Время суток задано."  # ru fallback

            # Script
            script_items: List[NarrativeScriptLine] = []
            if req.sound_mode:
                raw_script = raw.get("script") or ctx.get("script") or []
                if isinstance(raw_script, list):
                    for item in raw_script[:200]:
                        if not isinstance(item, dict):
                            continue
                        kind = str(item.get("kind") or "dialogue").strip().lower()
                        if kind not in {"exposition", "thought", "dialogue"}:
                            kind = "dialogue"
                        text = _safe_str(item.get("text") or "")
                        if not text:
                            continue
                        script_items.append(
                            NarrativeScriptLine(
                                kind=kind,
                                text=text,
                                speaker_name=_safe_str(item.get("speaker_name"), max_len=120) or None,
                                character_id=_safe_str(item.get("character_id"), max_len=64) or None,
                                emotion=_safe_str(item.get("emotion"), max_len=120) or None,
                            )
                        )

            # Choices
            choices: List[Dict[str, Any]] = []
            raw_choices = raw.get("choices") or ctx.get("choices") or []
            if scene_type == "decision" and isinstance(raw_choices, list):
                for ch in raw_choices[: req.max_branching]:
                    if not isinstance(ch, dict):
                        continue
                    label = _safe_str(ch.get("label") or "")
                    to_temp = _safe_str(ch.get("to_temp_id") or "", max_len=20)
                    if not label or not to_temp:
                        continue
                    choices.append(
                        {
                            "label": label,
                            "condition": _safe_str(ch.get("condition") or "") or None,
                            "to_temp_id": to_temp,
                        }
                    )

            scenes.append(
                AIScenarioDraftScene(
                    temp_id=temp_id,
                    title=_safe_str(raw.get("title") or f"Сцена {order_index}"),
                    synopsis=_safe_str(raw.get("synopsis") or ""),
                    content=_safe_str(raw.get("content") or ""),
                    scene_type=scene_type,
                    order_index=order_index,
                    location_id=location_id,
                    suggested_character_ids=suggested_character_ids,
                    script=script_items,
                    context=ctx,
                    choices=choices,
                )
            )

        # Edges
        edges: List[AIScenarioDraftEdge] = []
        raw_edges = data.get("edges") or []
        if isinstance(raw_edges, list):
            for e in raw_edges[: 200]:
                if not isinstance(e, dict):
                    continue
                fr = _safe_str(e.get("from_temp_id") or e.get("from") or "", max_len=20)
                to = _safe_str(e.get("to_temp_id") or e.get("to") or "", max_len=20)
                if not fr or not to:
                    continue
                edges.append(
                    AIScenarioDraftEdge(
                        from_temp_id=fr,
                        to_temp_id=to,
                        choice_label=_safe_str(e.get("choice_label") or "") or None,
                        condition=_safe_str(e.get("condition") or "") or None,
                    )
                )

        # If edges missing, infer from choices
        if not edges:
            for s in scenes:
                for ch in s.choices:
                    edges.append(
                        AIScenarioDraftEdge(
                            from_temp_id=s.temp_id,
                            to_temp_id=str(ch.get("to_temp_id")),
                            choice_label=str(ch.get("label")),
                            condition=ch.get("condition"),
                        )
                    )

        return AIScenarioDraftResponse(
            graph_title=title,
            graph_description=description,
            scenes=scenes,
            edges=edges,
        )

    # ------------------------ persistence ------------------------

    async def _persist_scenario_draft(self, project_id: str, draft: AIScenarioDraftResponse) -> AIScenarioDraftResponse:
        # Create graph
        graph = ScenarioGraph(
            project_id=project_id,
            title=draft.graph_title,
            description=draft.graph_description,
            root_scene_id=None,
        )
        self.session.add(graph)
        await self.session.flush()

        temp_to_scene: Dict[str, SceneNode] = {}
        # Create scenes
        for s in sorted(draft.scenes, key=lambda x: x.order_index):
            node = SceneNode(
                graph_id=graph.id,
                title=s.title,
                content=s.content,
                synopsis=s.synopsis,
                scene_type=s.scene_type,
                order_index=s.order_index,
                context=self._attach_scene_context_defaults(s.context, script=s.script, choices=s.choices),
                location_id=s.location_id,
            )
            self.session.add(node)
            await self.session.flush()
            temp_to_scene[s.temp_id] = node
            s.scene_id = node.id

        # Set root scene
        if draft.scenes:
            first_scene = min(draft.scenes, key=lambda x: x.order_index)
            root_node = temp_to_scene.get(first_scene.temp_id)
            if root_node is not None:
                graph.root_scene_id = root_node.id
                draft.root_scene_id = root_node.id

        draft.graph_id = graph.id

        # Create edges
        for e in draft.edges:
            frm = temp_to_scene.get(e.from_temp_id)
            to = temp_to_scene.get(e.to_temp_id)
            if not frm or not to:
                continue
            edge = Edge(
                graph_id=graph.id,
                from_scene_id=frm.id,
                to_scene_id=to.id,
                condition=e.condition,
                choice_label=e.choice_label,
                edge_metadata=None,
            )
            self.session.add(edge)
            await self.session.flush()
            e.edge_id = edge.id

        await self.session.commit()
        return draft

    def _attach_scene_context_defaults(
        self,
        ctx: Dict[str, Any],
        *,
        script: List[NarrativeScriptLine],
        choices: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        merged = dict(ctx or {})
        # Store script for TTS consumers
        if script:
            merged["script"] = [line.model_dump(exclude_none=True) for line in script]
        if choices:
            merged["choices"] = choices
        # Stamp
        merged.setdefault("generated_at", datetime.utcnow().isoformat())
        merged.setdefault("generator", "narrative_ai")
        return merged

    # ------------------------ DB loaders ------------------------

    async def _load_project(self, project_id: str) -> Optional[Project]:
        result = await self.session.execute(
            select(Project)
            .options(selectinload(Project.style_bible))
            .where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def _load_graph(self, graph_id: str) -> Optional[ScenarioGraph]:
        result = await self.session.execute(
            select(ScenarioGraph)
            .options(selectinload(ScenarioGraph.project))
            .where(ScenarioGraph.id == graph_id)
        )
        return result.scalar_one_or_none()

    async def _load_project_characters(self, project_id: str) -> List[CharacterPreset]:
        result = await self.session.execute(
            select(CharacterPreset)
            .where(CharacterPreset.project_id == project_id)
            .order_by(CharacterPreset.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _load_project_locations(self, project_id: str) -> List[Location]:
        result = await self.session.execute(
            select(Location)
            .where(Location.project_id == project_id)
            .order_by(Location.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _load_project_artifacts(self, project_id: str) -> List[Artifact]:
        result = await self.session.execute(
            select(Artifact)
            .where(Artifact.project_id == project_id)
            .order_by(Artifact.updated_at.desc())
        )
        return list(result.scalars().all())

    async def _build_scene_summaries(self, graph_id: str) -> List[Dict[str, Any]]:
        result = await self.session.execute(
            select(SceneNode)
            .where(SceneNode.graph_id == graph_id)
            .order_by(SceneNode.order_index.asc().nulls_last(), SceneNode.created_at.asc())
        )
        scenes = list(result.scalars().all())
        summaries: List[Dict[str, Any]] = []
        for s in scenes:
            ctx = s.context or {}
            time_of_day = None
            if isinstance(ctx, dict):
                time_of_day = ctx.get("time_of_day")
            summaries.append(
                {
                    "order_index": s.order_index,
                    "id": s.id,
                    "title": s.title,
                    "synopsis": s.synopsis or _safe_str(s.content, max_len=240),
                    "scene_type": s.scene_type,
                    "time_of_day": time_of_day,
                }
            )
        return summaries

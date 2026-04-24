from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.generation import ImageGenerationService
    from app.services.quests import QuestService

__all__ = ["ImageGenerationService", "QuestService"]


def __getattr__(name: str) -> Any:
    if name == "ImageGenerationService":
        from app.services.generation import ImageGenerationService

        return ImageGenerationService
    if name == "QuestService":
        from app.services.quests import QuestService

        return QuestService
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

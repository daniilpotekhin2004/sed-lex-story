"""app.infra.translator

Prompt translator for Stable Diffusion generation.

The backend allows prompts to be authored in Russian (or other languages) and
translates them to English before sending them to Stable Diffusion.

⚠️ IMPORTANT
Prompts may contain SD *special tokens* (LoRA / LyCORIS / extra networks) in the
form of angle‑bracket blocks, for example:

- `<lora:my_character:0.8>`
- `<lyco:style_pack:0.7>`

A naive full-string translation can corrupt such tokens (e.g. change case,
insert spaces, or strip punctuation). To prevent that, this module protects
all `<...>` blocks before translation and restores them afterwards.

Translation is done via OpenAI API (GPT) for accurate semantic translation,
not transliteration.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Protect any angle-bracket token (covers LoRA, LyCORIS and other SD extra network
# notations used by common UIs).
_SD_TOKEN_REGEX = re.compile(r"<[^>]{1,200}>")
_CYRILLIC_REGEX = re.compile(r"[а-яА-ЯёЁ]")
_NON_ENGLISH_WORD_REGEX = re.compile(r"[а-яА-ЯёЁ\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]+")


def is_cyrillic(text: str) -> bool:
    """Check if text contains Cyrillic characters."""
    return bool(_CYRILLIC_REGEX.search(text or ""))


def count_non_english_words(text: str) -> int:
    """Count words containing non-English characters (Cyrillic, CJK, etc.)."""
    if not text:
        return 0
    matches = _NON_ENGLISH_WORD_REGEX.findall(text)
    return len(matches)


def _protect_sd_tokens(text: str) -> Tuple[str, Dict[str, str]]:
    """Replace SD tokens with placeholders so translation won't corrupt them."""
    if not text:
        return text, {}

    placeholders: Dict[str, str] = {}
    counter = 0

    def _repl(match: re.Match) -> str:
        nonlocal counter
        token = match.group(0)
        key = f"ZXQSDTOKEN{counter}ZXQ"
        counter += 1
        placeholders[key] = token
        return key

    protected = _SD_TOKEN_REGEX.sub(_repl, text)
    return protected, placeholders


def _restore_sd_tokens(text: str, placeholders: Dict[str, str]) -> str:
    """Restore placeholders back to original SD tokens."""
    if not text or not placeholders:
        return text

    # Replace longer keys first (defensive; keys are unique anyway).
    for key in sorted(placeholders.keys(), key=len, reverse=True):
        text = text.replace(key, placeholders[key])
    return text


def _translate_with_openai(text: str) -> Optional[str]:
    """Translate text using OpenAI API."""
    try:
        import httpx
        
        api_key = os.environ.get("OPENAI_API_KEY", "")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        
        if not api_key:
            logger.warning("OPENAI_API_KEY not set, cannot translate")
            return None
        
        # Clean up base URL
        base_url = base_url.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1" if "/v1" not in base_url else base_url
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": model.strip(),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a translator for Stable Diffusion image generation prompts. "
                        "Translate the given text to English. Keep it as a comma-separated list of descriptive tags. "
                        "Do NOT transliterate - provide actual English translations. "
                        "Preserve any special tokens like ZXQSDTOKEN0ZXQ exactly as they are. "
                        "Keep artistic/style terms. Output only the translated prompt, nothing else."
                    )
                },
                {
                    "role": "user", 
                    "content": text
                }
            ],
            "temperature": 0.0,
            "top_p": 1.0,
            "max_tokens": 500,
        }
        
        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        
        translated = data["choices"][0]["message"]["content"].strip()
        logger.info(f"OpenAI translated: '{text[:50]}...' -> '{translated[:50]}...'")
        return translated
        
    except Exception as e:
        logger.error(f"OpenAI translation failed: {e}")
        return None


def translate_prompt(text: str) -> str:
    """Translate prompt to English if needed.

    - Preserves SD special tokens inside `<...>` blocks.
    - Uses OpenAI API for accurate semantic translation.
    - Falls back to dictionary-based translation if OpenAI fails.
    """
    if not text or not any(char.isalpha() for char in text):
        return text
    
    # Check if translation is needed
    if not is_cyrillic(text):
        return text

    protected, placeholders = _protect_sd_tokens(text)

    # Try OpenAI translation first
    translated = _translate_with_openai(protected)
    
    if translated:
        restored = _restore_sd_tokens(translated, placeholders)
        # Check if translation was successful (no Cyrillic remaining)
        if not is_cyrillic(restored):
            return restored
        logger.warning("OpenAI translation incomplete, trying fallback")
    
    # Fallback to dictionary-based translation
    try:
        from deep_translator import GoogleTranslator  # type: ignore

        translator = GoogleTranslator(source="auto", target="en")
        translated = translator.translate(protected)
        if translated:
            restored = _restore_sd_tokens(translated, placeholders)
            if not is_cyrillic(restored):
                logger.info(f"Google translated: '{text[:50]}...' -> '{restored[:50]}...'")
                return restored

    except ImportError:
        logger.debug("deep-translator not installed")
    except Exception as e:
        logger.warning(f"Google translation failed: {e}")

    # Final fallback - dictionary translation
    fallback = _fallback_translate(protected)
    restored = _restore_sd_tokens(fallback, placeholders)
    
    # If still has Cyrillic, log warning but DON'T transliterate
    if is_cyrillic(restored):
        logger.warning(
            f"Translation incomplete, some Russian words remain: '{restored[:100]}...'"
        )
    
    return restored


def _fallback_translate(text: str) -> str:
    """Simple fallback translation for common Russian words.

    The fallback is intentionally small and deterministic.
    """

    # Basic word replacements for common terms
    replacements = {
        # People
        "школьник": "schoolboy",
        "школьница": "schoolgirl",
        "студент": "student",
        "студентка": "female student",
        "мужчина": "man",
        "женщина": "woman",
        "девушка": "girl",
        "парень": "guy",
        "ребенок": "child",
        "дети": "children",
        "человек": "person",
        "люди": "people",
        "юрист": "lawyer",
        "судья": "judge",
        "следователь": "investigator",
        "полицейский": "policeman",
        "врач": "doctor",
        "учитель": "teacher",
        "адвокат": "attorney",
        "прокурор": "prosecutor",
        "свидетель": "witness",
        "подсудимый": "defendant",
        "истец": "plaintiff",
        "ответчик": "respondent",

        # Places
        "столовая": "cafeteria",
        "столовке": "cafeteria",
        "школа": "school",
        "школе": "school",
        "офис": "office",
        "офисе": "office",
        "суд": "court",
        "суде": "court",
        "зал суда": "courtroom",
        "зале суда": "courtroom",
        "комната": "room",
        "комнате": "room",
        "улица": "street",
        "улице": "street",
        "город": "city",
        "городе": "city",
        "дом": "house",
        "доме": "house",
        "квартира": "apartment",
        "квартире": "apartment",
        "кабинет": "office",
        "кабинете": "office",
        "тюрьма": "prison",
        "тюрьме": "prison",
        "камера": "cell",
        "камере": "cell",

        # Actions/States
        "сидит": "sitting",
        "стоит": "standing",
        "идет": "walking",
        "бежит": "running",
        "говорит": "talking",
        "смотрит": "looking",
        "держит": "holding",
        "читает": "reading",
        "пишет": "writing",
        "думает": "thinking",
        "слушает": "listening",
        "выступает": "speaking",
        "допрашивает": "interrogating",

        # Objects
        "документ": "document",
        "документы": "documents",
        "бумага": "paper",
        "бумаги": "papers",
        "книга": "book",
        "книги": "books",
        "телефон": "phone",
        "компьютер": "computer",
        "стол": "table",
        "стул": "chair",
        "окно": "window",
        "дверь": "door",
        "молоток": "gavel",
        "мантия": "robe",
        "наручники": "handcuffs",
        "решетка": "bars",

        # Adjectives
        "красивый": "beautiful",
        "красивая": "beautiful",
        "молодой": "young",
        "молодая": "young",
        "старый": "old",
        "старая": "old",
        "большой": "big",
        "большая": "big",
        "маленький": "small",
        "маленькая": "small",
        "темный": "dark",
        "темная": "dark",
        "светлый": "light",
        "светлая": "light",
        "серьезный": "serious",
        "серьезная": "serious",
        "строгий": "strict",
        "строгая": "strict",

        # Prepositions/Connectors
        "в": "in",
        "на": "on",
        "с": "with",
        "и": "and",
        "или": "or",
        "за": "behind",
        "перед": "in front of",
        "около": "near",
        "рядом": "next to",
        
        # Style terms
        "реалистичный": "realistic",
        "детальный": "detailed",
        "высокое качество": "high quality",
        "профессиональный": "professional",
        "кинематографичный": "cinematic",
        "драматичный": "dramatic",
    }

    result = text
    # Sort by length (longer first) to avoid partial replacements
    for ru, en in sorted(replacements.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(rf"\b{re.escape(ru)}\b", en, result, flags=re.IGNORECASE)

    return result


class PromptTranslator:
    """Translator class for prompt translation with caching."""

    def __init__(self, enabled: bool = True, cache_path: Optional[Path] = None):
        self.enabled = enabled
        self._cache: dict[str, str] = {}
        self._cache_path = cache_path
        self._load_cache()

    def _hash(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return digest

    def _load_cache(self) -> None:
        if not self._cache_path:
            return
        try:
            if self._cache_path.exists():
                data = self._cache_path.read_text(encoding="utf-8")
                payload = json.loads(data)
                if isinstance(payload, dict):
                    self._cache.update({str(k): str(v) for k, v in payload.items()})
        except Exception as exc:
            logger.warning(f"Failed to load translation cache: {exc}")

    def _save_cache(self) -> None:
        if not self._cache_path:
            return
        try:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache, ensure_ascii=True, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to save translation cache: {exc}")

    def translate(self, text: str) -> str:
        """Translate text, using cache if available."""
        if not self.enabled or not text:
            return text

        key = self._hash(text)
        if key in self._cache:
            return self._cache[key]

        translated = translate_prompt(text)
        self._cache[key] = translated
        self._save_cache()
        return translated

    def translate_prompt_and_negative(
        self,
        prompt: str,
        negative_prompt: Optional[str] = None,
    ) -> tuple[str, Optional[str]]:
        """Translate both prompt and negative prompt."""
        translated_prompt = self.translate(prompt)
        translated_negative = self.translate(negative_prompt) if negative_prompt else None
        return translated_prompt, translated_negative
    
    def analyze_prompt(self, text: str) -> dict:
        """Analyze prompt for non-English content.
        
        Returns dict with:
        - non_english_count: number of non-English words
        - needs_translation: whether translation is needed
        - warning: warning message if too many non-English words
        """
        if not text:
            return {
                "non_english_count": 0,
                "needs_translation": False,
                "warning": None,
            }
        
        non_english = count_non_english_words(text)
        needs_translation = is_cyrillic(text)
        
        warning = None
        if non_english > 10:
            warning = (
                f"Prompt contains {non_english} non-English words. "
                "Consider writing in English for better results, or ensure translation is working."
            )
        
        return {
            "non_english_count": non_english,
            "needs_translation": needs_translation,
            "warning": warning,
        }


# Global translator instance
_translator: Optional[PromptTranslator] = None


def get_translator() -> PromptTranslator:
    """Get or create global translator instance."""
    global _translator
    if _translator is None:
        settings = get_settings()
        cache_path = settings.translation_cache_path
        _translator = PromptTranslator(enabled=True, cache_path=cache_path)
    return _translator

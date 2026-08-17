"""Server-side message translation.

TranslationService wraps a provider (OpenAI today, swappable later) with
a content-addressed cache (core.models.TranslationCache) and a fallback
that NEVER lets a translation failure break messaging: on any provider
error, the original text is returned unchanged and the failure is logged.

Usage:
    from core.translation import translation_service
    text, was_translated = translation_service.translate(msg.text, 'en', 'ha')
"""
import hashlib
import logging
from abc import ABC, abstractmethod

from django.conf import settings

logger = logging.getLogger(__name__)


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class TranslationProvider(ABC):
    @abstractmethod
    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Return the translated text. Raise on failure — callers handle fallback."""
        raise NotImplementedError

    @abstractmethod
    def detect_language(self, text: str) -> str:
        """Return an ISO 639-1 language code. Raise on failure — callers handle fallback."""
        raise NotImplementedError


class OpenAITranslationProvider(TranslationProvider):
    """Mirrors the OpenAI usage already established in core.views.AIChatView
    (same client construction, same settings.OPENAI_API_KEY)."""

    MODEL = "gpt-4o-mini"

    def _client(self):
        import openai
        api_key = getattr(settings, "OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        return openai.OpenAI(api_key=api_key)

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        from core.languages import language_name

        client = self._client()
        response = client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Translate the user's message from {language_name(source_language)} "
                        f"to {language_name(target_language)}. Reply with ONLY the translated "
                        "text — no quotes, no explanation, no original text."
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=500,
            temperature=0,
        )
        return (response.choices[0].message.content or "").strip()

    def detect_language(self, text: str) -> str:
        from core.languages import SUPPORTED_LANGUAGE_CODES

        client = self._client()
        response = client.chat.completions.create(
            model=self.MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Identify the language of the user's message. Reply with ONLY its "
                        "ISO 639-1 two-letter code (e.g. en, ha, ar, fr) — nothing else."
                    ),
                },
                {"role": "user", "content": text[:500]},
            ],
            max_tokens=5,
            temperature=0,
        )
        code = (response.choices[0].message.content or "").strip().lower()[:10]
        return code if code in SUPPORTED_LANGUAGE_CODES else ''


class TranslationService:
    def __init__(self, provider: TranslationProvider = None):
        self.provider = provider or OpenAITranslationProvider()

    def translate(self, text: str, source_language: str, target_language: str) -> tuple[str, bool]:
        """Returns (text_to_display, was_translated). Never raises — on any
        failure, falls back to the original text so messaging keeps working."""
        if not text or not text.strip():
            return text, False
        source_language = source_language or 'en'
        if source_language == target_language:
            return text, False

        from core.models import TranslationCache

        text_hash = _hash_text(text)
        cached = TranslationCache.objects.filter(
            source_language=source_language,
            target_language=target_language,
            source_text_hash=text_hash,
        ).first()
        if cached:
            logger.debug("Translation cache hit %s->%s", source_language, target_language)
            return cached.translated_text, True

        logger.debug("Translation cache miss %s->%s", source_language, target_language)
        try:
            translated = self.provider.translate(text, source_language, target_language)
        except Exception:
            logger.exception("Translation failed (%s->%s); falling back to original text",
                              source_language, target_language)
            return text, False

        if not translated:
            return text, False

        TranslationCache.objects.get_or_create(
            source_language=source_language,
            target_language=target_language,
            source_text_hash=text_hash,
            defaults={'source_text': text, 'translated_text': translated},
        )
        return translated, True

    def detect_language(self, text: str) -> str:
        if not text or not text.strip():
            return ''
        try:
            return self.provider.detect_language(text)
        except Exception:
            logger.exception("Language detection failed")
            return ''


translation_service = TranslationService()

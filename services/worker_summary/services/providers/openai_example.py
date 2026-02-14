"""Example OpenAI provider implementation (not functional - for reference only).

This file shows how to implement a new provider for OpenAI's API.
To use this:
1. Install openai SDK: pip install openai
2. Remove the '_example' suffix from filename
3. Add configuration in config.py
4. Register in SummaryService._init_providers()
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

# from openai import AsyncOpenAI  # Uncomment when openai package is installed

from .base import ProviderHealth, SummaryProvider

logger = logging.getLogger(__name__)


class OpenAIProvider(SummaryProvider):
    """OpenAI API provider for summary generation.

    Supports GPT-4, GPT-3.5-turbo, and other chat models.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_concurrency: int = 5,
        temperature: float = 0.2,
        max_tokens: int = 400,
    ):
        """Initialize OpenAI provider.

        Args:
            api_key: OpenAI API key
            model: Model identifier (gpt-4o-mini, gpt-4, etc.)
            max_concurrency: Max concurrent requests
            temperature: Sampling temperature
            max_tokens: Max tokens in response
        """
        self._api_key = api_key
        self._model = model
        self._max_concurrency = max_concurrency
        self._temperature = temperature
        self._max_tokens = max_tokens
        # self._client = AsyncOpenAI(api_key=api_key)  # Uncomment when installed

    @property
    def name(self) -> str:
        return "openai"

    async def health_check(self) -> ProviderHealth:
        """Check OpenAI API availability via models list."""
        try:
            # Uncomment when openai package is installed:
            # models = await self._client.models.list()
            # if not models.data:
            #     return ProviderHealth(healthy=False, error_message="No models available")
            # return ProviderHealth(healthy=True)

            # Placeholder for example
            return ProviderHealth(healthy=False, error_message="OpenAI SDK not installed")
        except Exception as e:
            return ProviderHealth(healthy=False, error_message=str(e))

    async def generate(self, prompt: str) -> Optional[str]:
        """Generate single response via OpenAI Chat API."""
        try:
            # Uncomment when openai package is installed:
            # response = await self._client.chat.completions.create(
            #     model=self._model,
            #     messages=[
            #         {"role": "system", "content": "You are a helpful assistant."},
            #         {"role": "user", "content": prompt}
            #     ],
            #     temperature=self._temperature,
            #     max_tokens=self._max_tokens,
            #     response_format={"type": "json_object"},  # For structured JSON output
            # )
            # return response.choices[0].message.content

            # Placeholder for example
            logger.error("OpenAI SDK not installed - install with: pip install openai")
            return None
        except Exception as e:
            logger.error(
                "OpenAI generation failed",
                extra={"error": str(e)},
                exc_info=True,
            )
            return None

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate multiple responses with controlled concurrency."""
        if not prompts:
            return []

        sem = asyncio.Semaphore(self._max_concurrency)

        async def generate_one(prompt: str) -> Optional[str]:
            async with sem:
                return await self.generate(prompt)

        results = await asyncio.gather(*[generate_one(p) for p in prompts])
        return list(results)


# Configuration example for config.py:
"""
class SummarizationSettings(BaseModel):
    # ... existing fields ...

    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY", "SUMMARIZATION__OPENAI_API_KEY"),
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        validation_alias=AliasChoices("OPENAI_MODEL", "SUMMARIZATION__OPENAI_MODEL"),
    )
    openai_temperature: float = Field(
        default=0.2,
        validation_alias=AliasChoices("OPENAI_TEMPERATURE", "SUMMARIZATION__OPENAI_TEMPERATURE"),
    )
    openai_max_tokens: int = Field(
        default=400,
        validation_alias=AliasChoices("OPENAI_MAX_TOKENS", "SUMMARIZATION__OPENAI_MAX_TOKENS"),
    )
"""

# Factory example (current pattern):
"""
# In ProviderFactory class
def create_openai(self) -> Optional[SummaryProvider]:
    try:
        provider = OpenAIProvider.from_settings(self.settings.openai)
        if provider is None:
            error_msg = "Provider returned None from from_settings()"
            self._errors.append(("openai", error_msg))
            logger.warning("Failed to create OpenAI provider", extra={"error": error_msg})
        return provider
    except Exception as e:
        error_msg = str(e)
        self._errors.append(("openai", error_msg))
        logger.error("Exception creating OpenAI provider", extra={"error": error_msg}, exc_info=True)
        return None
"""

# OpenAI provider from_settings() example:
"""
@classmethod
def from_settings(cls, settings: OpenAIProviderSettings) -> Optional['OpenAIProvider']:
    try:
        if not settings.api_key:
            logger.warning("OpenAI API key not configured")
            return None

        return cls(
            api_key=settings.api_key,
            model=settings.model,
            max_concurrency=5,  # Or from settings if added
            temperature=settings.temperature,
            max_tokens=settings.max_tokens,
        )
    except Exception:
        logger.error("Failed to create OpenAI provider", exc_info=True)
        return None
"""

# Usage example:
"""
# .env file:
ENABLE_SUMMARIZATION=true
SUMMARY_PROVIDERS=huggingface,openai
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o-mini

# The provider chain will:
# 1. Try HuggingFace first
# 2. Fall back to OpenAI if HuggingFace fails
# 3. Use OpenAI for all subsequent chunks in the same article (sticky mode)
"""

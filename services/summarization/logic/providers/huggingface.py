from __future__ import annotations

import asyncio
import logging
from copy import deepcopy
from typing import Any, Dict, List, Optional, Tuple

from huggingface_hub import AsyncInferenceClient
from huggingface_hub.errors import GenerationError
from pydantic import BaseModel, Field

from .base import ProviderHealth, SummaryProvider

logger = logging.getLogger(__name__)


class SummaryLLMOutput(BaseModel):
    """Schema for summary generation output"""

    lede: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)


class HuggingFaceProvider(SummaryProvider):
    """HuggingFace Text Generation Inference (TGI) provider.

    Supports async batching with configurable concurrency limits.
    Implements parameter fallback for TGI compatibility.
    """

    def __init__(
        self,
        base_url: str,
        token: Optional[str] = None,
        grammar: Optional[Dict[str, Any]] = None,
        max_concurrency: int = 0,
    ):
        """Initialize HuggingFace TGI provider.

        Args:
            base_url: TGI endpoint URL (without /v1 suffix)
            token: Optional API token
            grammar: Optional JSON schema grammar for structured output
            max_concurrency: Max concurrent requests (0 = unlimited)
        """
        self._base_url = base_url
        self._token = token
        self._grammar = grammar
        self._max_concurrency = max_concurrency

    @classmethod
    def from_settings(
        cls, settings: "HuggingFaceProviderSettings"
    ) -> Optional["HuggingFaceProvider"]:
        """Create provider from configuration settings.

        Args:
            settings: HuggingFace provider configuration

        Returns:
            Configured provider, or None if configuration invalid
        """
        try:
            base = (settings.api_base or "").strip()
            if base.endswith("/v1"):
                base = base[:-3]
            tgi_url = base or "http://text-generation"

            token = settings.api_key
            if not token or token == "-":
                token = None

            grammar = cls.build_grammar(SummaryLLMOutput)

            return cls(
                base_url=tgi_url,
                token=token,
                grammar=grammar,
                max_concurrency=settings.max_concurrency,
            )
        except Exception as e:
            logger.error(
                "Failed to create HuggingFace provider from settings",
                extra={"error": str(e)},
                exc_info=True,
            )
            return None

    @property
    def name(self) -> str:
        return "huggingface"

    async def health_check(self) -> ProviderHealth:
        """Check TGI endpoint health via minimal generation test."""
        try:
            async with AsyncInferenceClient(
                self._base_url, token=self._token
            ) as client:
                # Minimal test generation
                await client.text_generation("test", max_new_tokens=1)
            return ProviderHealth(healthy=True)
        except Exception as e:
            return ProviderHealth(healthy=False, error_message=str(e))

    async def generate(self, prompt: str) -> Optional[str]:
        """Generate single response with parameter fallback."""
        async with AsyncInferenceClient(self._base_url, token=self._token) as client:
            raw, err = await self._generate_with_variants(client, prompt)
            if raw is None:
                if err:
                    logger.error(
                        "HuggingFace generation failed",
                        extra={"error": str(err)},
                        exc_info=err,
                    )
                return None
            return self._coerce_generated_text(raw)

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Optimized async batching with semaphore-controlled concurrency."""
        if not prompts:
            return []

        async with AsyncInferenceClient(self._base_url, token=self._token) as client:
            limit = self._resolve_concurrency_limit(len(prompts))
            sem = asyncio.Semaphore(limit)

            async def generate_one(prompt: str) -> Optional[str]:
                async with sem:
                    raw, err = await self._generate_with_variants(client, prompt)
                    if raw is None:
                        return None
                    return self._coerce_generated_text(raw)

            results = await asyncio.gather(*[generate_one(p) for p in prompts])
            return list(results)

    def _resolve_concurrency_limit(self, total: int) -> int:
        """Resolve effective concurrency limit."""
        if not self._max_concurrency:
            return total
        try:
            limit = int(self._max_concurrency)
        except (TypeError, ValueError):
            return total
        return max(1, min(limit, total))

    async def _generate_with_variants(
        self, client: AsyncInferenceClient, prompt: str
    ) -> Tuple[Any | None, Exception | None]:
        """Try generation with multiple parameter variants."""
        last_err: Exception | None = None
        for params in self._build_text_generation_variants():
            result, err = await self._try_single_variant(client, prompt, params)
            if result is not None:
                return result, None
            if err is not None:
                last_err = err
        return None, last_err

    async def _try_single_variant(
        self,
        client: AsyncInferenceClient,
        prompt: str,
        params: Dict[str, Any],
    ) -> Tuple[Any | None, Exception | None]:
        """Try single parameter variant with progressive fallback."""
        current = dict(params)
        removed_return_full = False
        removed_grammar = False
        last_err: Exception | None = None

        while True:
            try:
                return await client.text_generation(prompt, **current), None
            except TypeError as exc:
                last_err = exc
                if not removed_return_full and "return_full_text" in current:
                    current = dict(current)
                    current.pop("return_full_text", None)
                    removed_return_full = True
                    continue
                if (
                    not removed_grammar
                    and "grammar" in current
                    and "grammar" in str(exc)
                ):
                    current = dict(current)
                    current.pop("grammar", None)
                    removed_grammar = True
                    continue
                await asyncio.sleep(0.25)
                return None, last_err
            except GenerationError as exc:
                last_err = exc
                await asyncio.sleep(0.25)
                return None, last_err
            except Exception as exc:
                last_err = exc
                await asyncio.sleep(0.25)
                return None, last_err

    def _build_text_generation_variants(self) -> List[Dict[str, Any]]:
        """Build parameter variant list with optional grammar."""
        base_variants: List[Dict[str, Any]] = [
            {
                "temperature": 0.2,
                "top_p": 0.95,
                "do_sample": True,
                "max_new_tokens": 400,
                "return_full_text": False,
            },
            {
                "temperature": 0.0,
                "top_p": 1.0,
                "do_sample": False,
                "max_new_tokens": 300,
                "return_full_text": False,
            },
            {
                "temperature": 0.2,
                "top_p": 0.90,
                "do_sample": True,
                "max_new_tokens": 280,
                "return_full_text": False,
            },
        ]

        variants: List[Dict[str, Any]] = []
        for params in base_variants:
            variant = dict(params)
            if self._grammar:
                variant["grammar"] = self._grammar
            variants.append(variant)
        return variants

    def _coerce_generated_text(self, raw: Any) -> str:
        """Extract text from various TGI response formats."""
        if raw is None:
            return ""
        if isinstance(raw, str):
            return raw
        text = getattr(raw, "generated_text", None)
        if isinstance(text, str):
            return text
        if isinstance(raw, dict):
            for key in ("generated_text", "text", "content"):
                value = raw.get(key)
                if isinstance(value, str):
                    return value
        return str(raw)

    @staticmethod
    def build_grammar(output_schema: type[BaseModel]) -> Optional[Dict[str, Any]]:
        """Build JSON schema grammar for structured output.

        Args:
            output_schema: Pydantic model defining output structure

        Returns:
            Grammar dict for TGI, or None if schema extraction fails
        """
        try:
            schema = deepcopy(output_schema.model_json_schema())
        except Exception:
            return None

        # Ensure schema is explicit about required fields
        required = list(
            dict.fromkeys([*(schema.get("required") or []), "lede", "summary"])
        )
        schema["required"] = required
        schema["additionalProperties"] = False

        properties = schema.setdefault("properties", {})
        if isinstance(properties, dict):
            for field in ("lede", "summary"):
                field_schema = properties.get(field) or {}
                if not isinstance(field_schema, dict):
                    field_schema = {}
                field_schema.setdefault("type", "string")
                field_schema.setdefault("minLength", 1)
                properties[field] = field_schema

        return {"type": "json_schema", "value": schema}

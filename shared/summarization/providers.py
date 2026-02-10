"""LLM Provider abstraction for summary generation."""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class SummaryLLMOutput(BaseModel):
    """Structured output from summary LLM."""

    lede: str = ""
    summary: str = ""


@dataclass
class ProviderHealth:
    """Health status of an LLM provider."""

    healthy: bool
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class SummaryProvider(ABC):
    """Abstract base class for summary LLM providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for identification."""
        pass

    @abstractmethod
    async def generate(self, prompt: str) -> Optional[str]:
        """Generate a response for the given prompt.

        Args:
            prompt: Input prompt

        Returns:
            Generated text, or None if failed
        """
        pass

    @abstractmethod
    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate responses for multiple prompts.

        Args:
            prompts: List of input prompts

        Returns:
            List of generated texts (None for failures)
        """
        pass

    @abstractmethod
    async def check_health(self) -> ProviderHealth:
        """Check if the provider is healthy and responsive.

        Returns:
            Health status
        """
        pass


class ProviderChain:
    """Chain of providers with fallback support.

    Attempts generation using primary provider, falling back to
    secondary providers if primary fails.
    """

    def __init__(
        self,
        providers: List[SummaryProvider],
        max_retries: int = 3,
        session_fail_threshold: int = 5,
    ):
        """Initialize provider chain.

        Args:
            providers: List of providers in priority order
            max_retries: Maximum retries per provider
            session_fail_threshold: Failures before skipping provider for session
        """
        self.providers = providers
        self.max_retries = max_retries
        self.session_fail_threshold = session_fail_threshold
        self._session_failures: Dict[str, int] = {}

    def reset_session(self) -> None:
        """Reset session failure counts (call at start of each article)."""
        self._session_failures = {}

    async def generate(self, prompt: str) -> Optional[str]:
        """Generate using best available provider.

        Args:
            prompt: Input prompt

        Returns:
            Generated text, or None if all providers failed
        """
        for provider in self._get_available_providers():
            for attempt in range(self.max_retries):
                try:
                    result = await provider.generate(prompt)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.warning(
                        f"Provider {provider.name} attempt {attempt + 1} failed: {e}"
                    )

            self._record_failure(provider.name)

        logger.error("All providers failed for generation")
        return None

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate batch using best available provider.

        Args:
            prompts: List of input prompts

        Returns:
            List of generated texts
        """
        for provider in self._get_available_providers():
            for attempt in range(self.max_retries):
                try:
                    results = await provider.generate_batch(prompts)
                    if any(r is not None for r in results):
                        return results
                except Exception as e:
                    logger.warning(
                        f"Provider {provider.name} batch attempt {attempt + 1} failed: {e}"
                    )

            self._record_failure(provider.name)

        logger.error("All providers failed for batch generation")
        return [None] * len(prompts)

    async def check_all_health(self) -> List[tuple[str, ProviderHealth]]:
        """Check health of all providers.

        Returns:
            List of (provider_name, health_status) tuples
        """
        results = []
        for provider in self.providers:
            try:
                health = await provider.check_health()
                results.append((provider.name, health))
            except Exception as e:
                results.append((
                    provider.name,
                    ProviderHealth(healthy=False, error=str(e))
                ))
        return results

    def _get_available_providers(self) -> List[SummaryProvider]:
        """Get providers not disabled for this session."""
        return [
            p for p in self.providers
            if self._session_failures.get(p.name, 0) < self.session_fail_threshold
        ]

    def _record_failure(self, provider_name: str) -> None:
        """Record a failure for a provider."""
        self._session_failures[provider_name] = (
            self._session_failures.get(provider_name, 0) + 1
        )
        if self._session_failures[provider_name] >= self.session_fail_threshold:
            logger.warning(
                f"Provider {provider_name} disabled for session "
                f"(reached {self.session_fail_threshold} failures)"
            )


class HTTPProvider(SummaryProvider):
    """HTTP-based LLM provider for OpenAI-compatible APIs."""

    def __init__(
        self,
        name: str,
        base_url: str,
        api_key: Optional[str] = None,
        model: str = "gpt-3.5-turbo",
        timeout: float = 60.0,
    ):
        """Initialize HTTP provider.

        Args:
            name: Provider name
            base_url: API base URL
            api_key: Optional API key
            model: Model name
            timeout: Request timeout in seconds
        """
        self._name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    async def generate(self, prompt: str) -> Optional[str]:
        """Generate using HTTP API."""
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": 1000,
                    },
                )
                response.raise_for_status()

                result = response.json()
                return result["choices"][0]["message"]["content"]

        except Exception as e:
            logger.error(f"HTTP generation failed: {e}")
            return None

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate batch by making concurrent requests."""
        tasks = [self.generate(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks)

    async def check_health(self) -> ProviderHealth:
        """Check API health."""
        import time

        try:
            import httpx

            start = time.time()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                latency = (time.time() - start) * 1000

                return ProviderHealth(
                    healthy=response.status_code == 200,
                    latency_ms=latency,
                )
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))


class HuggingFaceProvider(SummaryProvider):
    """HuggingFace Text Generation Inference provider."""

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: float = 60.0,
    ):
        """Initialize HuggingFace TGI provider.

        Args:
            base_url: TGI server URL
            api_key: Optional API key
            timeout: Request timeout
        """
        self._name = "huggingface"
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self._name

    async def generate(self, prompt: str) -> Optional[str]:
        """Generate using TGI API."""
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/generate",
                    headers=headers,
                    json={
                        "inputs": prompt,
                        "parameters": {
                            "max_new_tokens": 500,
                            "temperature": 0.3,
                        },
                    },
                )
                response.raise_for_status()

                result = response.json()
                return result.get("generated_text", "")

        except Exception as e:
            logger.error(f"HuggingFace generation failed: {e}")
            return None

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate batch concurrently."""
        tasks = [self.generate(prompt) for prompt in prompts]
        return await asyncio.gather(*tasks)

    async def check_health(self) -> ProviderHealth:
        """Check TGI health."""
        import time

        try:
            import httpx

            start = time.time()
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(f"{self.base_url}/health")
                latency = (time.time() - start) * 1000

                return ProviderHealth(
                    healthy=response.status_code == 200,
                    latency_ms=latency,
                )
        except Exception as e:
            return ProviderHealth(healthy=False, error=str(e))

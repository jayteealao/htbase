from __future__ import annotations

import logging
from typing import List, Optional

from .base import ProviderHealth, SummaryProvider

logger = logging.getLogger(__name__)


class ProviderChain:
    """Manages fallback chain of providers with sticky session support.

    In sticky mode (default), once a provider succeeds, it's reused for the
    entire article processing cycle. This ensures consistency and reduces overhead.

    For batch operations, if any chunks fail with the active provider, only
    the failed chunks are retried with the next provider in the chain.
    """

    def __init__(self, providers: List[SummaryProvider], sticky: bool = True):
        """Initialize provider chain.

        Args:
            providers: Ordered list of providers (first = highest priority)
            sticky: If True, reuse successful provider for entire session
        """
        if not providers:
            raise ValueError("Provider chain requires at least one provider")

        self.providers = providers
        self.sticky = sticky
        self._active_provider: Optional[SummaryProvider] = None
        self._health_cache: dict[str, ProviderHealth] = {}

    def reset_session(self) -> None:
        """Reset sticky provider and health cache.

        Call this at the start of each article processing cycle.
        """
        self._active_provider = None
        self._health_cache.clear()

    async def check_all_health(self) -> List[tuple[str, ProviderHealth]]:
        """Check health of all providers and cache results.

        Returns:
            List of (provider_name, health_status) tuples
        """
        results = []
        for provider in self.providers:
            health = await provider.health_check()
            self._health_cache[provider.name] = health
            results.append((provider.name, health))
            logger.info(
                "Provider health check",
                extra={
                    "provider": provider.name,
                    "healthy": health.healthy,
                    "error": health.error_message,
                },
            )
        return results

    def _get_cached_health(self, provider: SummaryProvider) -> Optional[ProviderHealth]:
        """Get cached health status, if available."""
        return self._health_cache.get(provider.name)

    async def generate(self, prompt: str) -> Optional[str]:
        """Generate using fallback chain with sticky provider support.

        If sticky mode is enabled and a provider has already succeeded in this
        session, that provider is tried first.

        Args:
            prompt: The prompt text to send to the LLM

        Returns:
            Generated text, or None if all providers failed
        """
        # Try sticky provider first
        if self.sticky and self._active_provider:
            health = self._get_cached_health(self._active_provider)
            if health and health.healthy:
                result = await self._active_provider.generate(prompt)
                if result is not None:
                    logger.debug(
                        "Sticky provider succeeded",
                        extra={"provider": self._active_provider.name},
                    )
                    return result
                logger.warning(
                    "Sticky provider failed, falling back to chain",
                    extra={"provider": self._active_provider.name},
                )

        # Try provider chain
        for provider in self.providers:
            # Check health (use cache if available)
            health = self._get_cached_health(provider)
            if health and not health.healthy:
                logger.debug(
                    "Skipping unhealthy provider",
                    extra={"provider": provider.name, "error": health.error_message},
                )
                continue

            logger.debug("Trying provider", extra={"provider": provider.name})
            result = await provider.generate(prompt)
            if result is not None:
                if self.sticky:
                    self._active_provider = provider
                logger.info(
                    "Provider succeeded",
                    extra={"provider": provider.name},
                )
                return result

            logger.warning(
                "Provider failed, trying next",
                extra={"provider": provider.name},
            )

        logger.error("All providers failed for single generation")
        return None

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate batch with intelligent retry of failed chunks.

        In sticky mode, uses the active provider for the entire batch.
        If any chunks fail, retries only those failed chunks with the next
        provider in the chain.

        In non-sticky mode, each prompt independently uses the fallback chain.

        Args:
            prompts: List of prompt texts

        Returns:
            List of generated texts (same length as input), None for failures
        """
        if not prompts:
            return []

        if not self.sticky:
            # Non-sticky: each prompt independently uses fallback chain
            results = []
            for prompt in prompts:
                result = await self.generate(prompt)
                results.append(result)
            return results

        # Sticky mode: try to use same provider for entire batch
        results: List[Optional[str]] = [None] * len(prompts)
        pending_indices = list(range(len(prompts)))

        # Try sticky provider first if available
        providers_to_try = []
        if self._active_provider:
            health = self._get_cached_health(self._active_provider)
            if health and health.healthy:
                providers_to_try.append(self._active_provider)

        # Add remaining providers
        providers_to_try.extend(
            [p for p in self.providers if p != self._active_provider]
        )

        for provider in providers_to_try:
            if not pending_indices:
                break  # All chunks succeeded

            # Check health
            health = self._get_cached_health(provider)
            if health and not health.healthy:
                logger.debug(
                    "Skipping unhealthy provider",
                    extra={"provider": provider.name, "error": health.error_message},
                )
                continue

            # Generate batch for pending chunks only
            pending_prompts = [prompts[i] for i in pending_indices]
            logger.info(
                "Attempting batch generation",
                extra={
                    "provider": provider.name,
                    "chunk_count": len(pending_prompts),
                },
            )

            batch_results = await provider.generate_batch(pending_prompts)

            # Process results and update pending list
            new_pending = []
            for idx, result in zip(pending_indices, batch_results):
                if result is not None:
                    results[idx] = result
                else:
                    new_pending.append(idx)

            success_count = len(pending_indices) - len(new_pending)
            logger.info(
                "Batch generation completed",
                extra={
                    "provider": provider.name,
                    "success_count": success_count,
                    "failure_count": len(new_pending),
                },
            )

            # If any succeeded and we're sticky, lock to this provider
            if success_count > 0 and self.sticky:
                self._active_provider = provider

            pending_indices = new_pending

        if pending_indices:
            logger.error(
                "Some chunks failed with all providers",
                extra={"failed_indices": pending_indices},
            )

        return results

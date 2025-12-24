from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ProviderHealth:
    """Health check result for a provider"""

    healthy: bool
    error_message: Optional[str] = None


class SummaryProvider(ABC):
    """Base class for summary generation providers.

    Providers handle the LLM call (text in -> text out). The SummaryService
    orchestrates chunking, prompt building, and response parsing.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier (e.g., 'huggingface', 'openai')"""
        pass

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check if provider is available and healthy.

        This should be a lightweight check (e.g., ping endpoint, verify credentials).
        Called once per article processing cycle.
        """
        pass

    @abstractmethod
    async def generate(self, prompt: str) -> Optional[str]:
        """Generate a single response.

        Args:
            prompt: The prompt text to send to the LLM

        Returns:
            Generated text, or None if generation failed
        """
        pass

    async def generate_batch(self, prompts: List[str]) -> List[Optional[str]]:
        """Generate multiple responses.

        Default implementation: sequential calls to generate().
        Providers can override for optimized batching/parallelization.

        Args:
            prompts: List of prompt texts

        Returns:
            List with same length as input; None elements indicate failures
        """
        results = []
        for prompt in prompts:
            result = await self.generate(prompt)
            results.append(result)
        return results

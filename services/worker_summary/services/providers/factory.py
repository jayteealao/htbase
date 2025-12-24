"""Provider factory for creating summary providers from configuration."""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Optional

from .base import SummaryProvider
from .huggingface import HuggingFaceProvider

if TYPE_CHECKING:
    from common.core.config import SummarizationSettings

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating summary providers from configuration.

    Handles provider-specific construction logic and error collection.
    """

    def __init__(self, settings: "SummarizationSettings"):
        """Initialize factory with summarization settings.

        Args:
            settings: Summarization configuration containing provider-specific settings
        """
        self.settings = settings
        self._errors: list[tuple[str, str]] = []

    @property
    def errors(self) -> list[tuple[str, str]]:
        """Get list of (provider_name, error_message) tuples from creation attempts."""
        return self._errors.copy()

    def create_huggingface(self) -> Optional[SummaryProvider]:
        """Create HuggingFace TGI provider from configuration.

        Returns:
            Configured HuggingFace provider, or None if creation failed
        """
        try:
            provider = HuggingFaceProvider.from_settings(self.settings.huggingface)
            if provider is None:
                error_msg = "Provider returned None from from_settings()"
                self._errors.append(("huggingface", error_msg))
                logger.warning(
                    "Failed to create HuggingFace provider",
                    extra={"error": error_msg},
                )
            return provider
        except Exception as e:
            error_msg = str(e)
            self._errors.append(("huggingface", error_msg))
            logger.error(
                "Exception creating HuggingFace provider",
                extra={"error": error_msg},
                exc_info=True,
            )
            return None

    def create_openai(self) -> Optional[SummaryProvider]:
        """Create OpenAI provider from configuration.

        Returns:
            Configured OpenAI provider, or None if creation failed
        """
        # Placeholder for OpenAI provider (not yet implemented)
        error_msg = "OpenAI provider not yet implemented"
        self._errors.append(("openai", error_msg))
        logger.warning(
            "OpenAI provider requested but not implemented",
            extra={"settings": self.settings.openai},
        )
        return None

    def create_provider(self, provider_name: str) -> Optional[SummaryProvider]:
        """Create provider by name.

        Args:
            provider_name: Provider identifier (e.g., 'huggingface', 'openai')

        Returns:
            Configured provider, or None if creation failed or unknown provider
        """
        if provider_name == "huggingface":
            return self.create_huggingface()
        elif provider_name == "openai":
            return self.create_openai()
        else:
            error_msg = f"Unknown provider: {provider_name}"
            self._errors.append((provider_name, error_msg))
            logger.error("Unknown provider requested", extra={"provider": provider_name})
            return None

    def create_all_configured(self) -> list[SummaryProvider]:
        """Create all providers listed in settings.providers.

        Returns:
            List of successfully created providers (may be empty)

        Raises:
            ValueError: If no providers could be created
        """
        providers: list[SummaryProvider] = []

        for provider_name in self.settings.providers:
            logger.info(
                "Attempting to create provider",
                extra={"provider": provider_name},
            )
            provider = self.create_provider(provider_name)
            if provider is not None:
                providers.append(provider)
                logger.info(
                    "Successfully created provider",
                    extra={"provider": provider_name},
                )

        if not providers:
            error_summary = "; ".join(
                f"{name}: {msg}" for name, msg in self._errors
            )
            raise ValueError(
                f"Failed to create any providers. Errors: {error_summary}"
            )

        if self._errors:
            logger.warning(
                "Some providers failed to create",
                extra={
                    "success_count": len(providers),
                    "failure_count": len(self._errors),
                    "errors": self._errors,
                },
            )

        return providers

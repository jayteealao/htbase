"""Unit tests for provider chain and fallback logic."""
import pytest
from services.providers import ProviderChain, ProviderHealth, SummaryProvider


class MockProvider(SummaryProvider):
    """Mock provider for testing."""

    def __init__(self, name: str, healthy: bool = True, fail_generate: bool = False):
        self._name = name
        self._healthy = healthy
        self._fail_generate = fail_generate
        self.generate_calls = []
        self.generate_batch_calls = []
        self.health_check_calls = 0

    @property
    def name(self) -> str:
        return self._name

    async def health_check(self) -> ProviderHealth:
        self.health_check_calls += 1
        if self._healthy:
            return ProviderHealth(healthy=True)
        return ProviderHealth(healthy=False, error_message="Mock unhealthy")

    async def generate(self, prompt: str) -> str | None:
        self.generate_calls.append(prompt)
        if self._fail_generate:
            return None
        return f"{self._name}: {prompt[:20]}"


@pytest.mark.asyncio
async def test_provider_chain_single_healthy_provider():
    """Test basic generation with single healthy provider."""
    provider = MockProvider("test")
    chain = ProviderChain([provider], sticky=True)

    result = await chain.generate("test prompt")
    assert result == "test: test prompt"
    assert len(provider.generate_calls) == 1


@pytest.mark.asyncio
async def test_provider_chain_fallback_to_second():
    """Test fallback when first provider fails."""
    provider1 = MockProvider("provider1", fail_generate=True)
    provider2 = MockProvider("provider2")
    chain = ProviderChain([provider1, provider2], sticky=True)

    # Check health first
    await chain.check_all_health()

    result = await chain.generate("test prompt")
    assert result == "provider2: test prompt"
    assert len(provider1.generate_calls) == 1
    assert len(provider2.generate_calls) == 1


@pytest.mark.asyncio
async def test_provider_chain_skip_unhealthy():
    """Test that unhealthy providers are skipped."""
    provider1 = MockProvider("provider1", healthy=False)
    provider2 = MockProvider("provider2")
    chain = ProviderChain([provider1, provider2], sticky=True)

    # Check health first
    await chain.check_all_health()

    result = await chain.generate("test prompt")
    assert result == "provider2: test prompt"
    assert len(provider1.generate_calls) == 0  # Should be skipped
    assert len(provider2.generate_calls) == 1


@pytest.mark.asyncio
async def test_provider_chain_sticky_mode():
    """Test sticky mode reuses successful provider."""
    provider1 = MockProvider("provider1")
    provider2 = MockProvider("provider2")
    chain = ProviderChain([provider1, provider2], sticky=True)

    # First call uses provider1
    result1 = await chain.generate("prompt1")
    assert result1 == "provider1: prompt1"

    # Second call should reuse provider1
    result2 = await chain.generate("prompt2")
    assert result2 == "provider1: prompt2"

    # Both calls should have gone to provider1
    assert len(provider1.generate_calls) == 2
    assert len(provider2.generate_calls) == 0


@pytest.mark.asyncio
async def test_provider_chain_batch_generation():
    """Test batch generation with single provider."""
    provider = MockProvider("test")
    chain = ProviderChain([provider], sticky=True)

    prompts = ["prompt1", "prompt2", "prompt3"]
    results = await chain.generate_batch(prompts)

    assert len(results) == 3
    assert results[0] == "test: prompt1"
    assert results[1] == "test: prompt2"
    assert results[2] == "test: prompt3"


@pytest.mark.asyncio
async def test_provider_chain_batch_partial_retry():
    """Test that failed chunks are retried with next provider."""

    class SelectiveFailProvider(SummaryProvider):
        """Provider that fails on specific prompts."""

        def __init__(self, name: str, fail_on: list[str]):
            self._name = name
            self._fail_on = fail_on

        @property
        def name(self) -> str:
            return self._name

        async def health_check(self) -> ProviderHealth:
            return ProviderHealth(healthy=True)

        async def generate(self, prompt: str) -> str | None:
            if prompt in self._fail_on:
                return None
            return f"{self._name}: {prompt}"

        async def generate_batch(self, prompts: list[str]) -> list[str | None]:
            results = []
            for prompt in prompts:
                if prompt in self._fail_on:
                    results.append(None)
                else:
                    results.append(f"{self._name}: {prompt}")
            return results

    # Provider1 fails on "prompt2"
    provider1 = SelectiveFailProvider("provider1", fail_on=["prompt2"])
    # Provider2 succeeds on everything
    provider2 = MockProvider("provider2")

    chain = ProviderChain([provider1, provider2], sticky=True)
    await chain.check_all_health()

    prompts = ["prompt1", "prompt2", "prompt3"]
    results = await chain.generate_batch(prompts)

    # prompt1 and prompt3 should come from provider1
    # prompt2 should come from provider2 (fallback)
    assert results[0] == "provider1: prompt1"
    assert results[1] == "provider2: prompt2"
    assert results[2] == "provider1: prompt3"


@pytest.mark.asyncio
async def test_provider_chain_reset_session():
    """Test that reset_session clears sticky provider."""
    provider1 = MockProvider("provider1")
    provider2 = MockProvider("provider2")
    chain = ProviderChain([provider1, provider2], sticky=True)

    # First call locks to provider1
    await chain.generate("prompt1")
    assert len(provider1.generate_calls) == 1

    # Second call uses provider1 (sticky)
    await chain.generate("prompt2")
    assert len(provider1.generate_calls) == 2

    # Reset session
    chain.reset_session()

    # Next call should try from beginning of chain again
    await chain.generate("prompt3")
    assert len(provider1.generate_calls) == 3


@pytest.mark.asyncio
async def test_provider_chain_all_fail():
    """Test that None is returned when all providers fail."""
    provider1 = MockProvider("provider1", fail_generate=True)
    provider2 = MockProvider("provider2", fail_generate=True)
    chain = ProviderChain([provider1, provider2], sticky=True)

    await chain.check_all_health()

    result = await chain.generate("test prompt")
    assert result is None

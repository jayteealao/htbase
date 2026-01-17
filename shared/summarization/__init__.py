"""
Shared summarization module for HTBase microservices.

Provides building blocks for summary generation:
- ArticleChunker: Token-aware text splitting for large articles
- PromptBuilder: Editorial-quality prompt templates
- ResponseParser: Structured LLM output extraction
- SummaryProvider & ProviderChain: Multi-provider LLM access with fallback

Note: This module provides reusable components. The actual summarization
orchestration logic lives in services/summarization-worker/app/tasks.py,
which uses these components with Firestore for persistence.
"""

from .chunker import ArticleChunker
from .prompt_builder import PromptBuilder, SummaryInputs
from .response_parser import ResponseParser
from .providers import (
    SummaryLLMOutput,
    SummaryProvider,
    ProviderHealth,
    ProviderChain,
    HTTPProvider,
    HuggingFaceProvider,
)

# Clean exports - only active components
__all__ = [
    "ArticleChunker",
    "PromptBuilder",
    "SummaryInputs",
    "ResponseParser",
    "SummaryLLMOutput",
    "SummaryProvider",
    "ProviderHealth",
    "ProviderChain",
    "HTTPProvider",
    "HuggingFaceProvider",
]

# Historical note: SummaryService and create_summary_service were removed
# in 2026-01-17 as part of Wave 5F cleanup. The legacy SQLAlchemy-based
# service was replaced by direct Firestore usage in:
# services/summarization-worker/app/tasks.py

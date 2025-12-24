"""
Shared summarization module for HTBase microservices.

Provides article chunking, prompt building, response parsing,
and LLM provider abstraction for summary generation.
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
from .service import SummaryService, create_summary_service

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
    "SummaryService",
    "create_summary_service",
]

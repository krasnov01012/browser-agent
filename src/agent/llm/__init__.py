"""Слой LLM. Всё общение с моделями идёт через LLMRouter.

Ничего за пределами этого пакета не импортирует провайдеров напрямую.
"""

from .base import (
    AuthError,
    ImageContent,
    LLMError,
    LLMProvider,
    LLMResponse,
    MalformedResponse,
    Message,
    ModelUnavailable,
    RateLimited,
    ToolCall,
    ToolSpec,
    TransientError,
    Usage,
)
from .budget import Budget, BudgetExceeded
from .router import LLMRouter, build_provider

__all__ = [
    "AuthError",
    "Budget",
    "BudgetExceeded",
    "ImageContent",
    "LLMError",
    "LLMProvider",
    "LLMResponse",
    "LLMRouter",
    "MalformedResponse",
    "Message",
    "ModelUnavailable",
    "RateLimited",
    "ToolCall",
    "ToolSpec",
    "TransientError",
    "Usage",
    "build_provider",
]

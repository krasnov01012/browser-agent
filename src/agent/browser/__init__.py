"""Слой браузера: подключение, снапшоты, ожидание стабилизации."""

from .controller import BrowserController, BrowserUnavailable
from .refs import InvalidRef, RefError, RefRegistry, StaleRef
from .snapshot import Element, PageState, TabInfo, capture, estimate_tokens
from .stability import Stability, wait_until_settled

__all__ = [
    "BrowserController",
    "BrowserUnavailable",
    "Element",
    "InvalidRef",
    "PageState",
    "RefError",
    "RefRegistry",
    "Stability",
    "StaleRef",
    "TabInfo",
    "capture",
    "estimate_tokens",
    "wait_until_settled",
]

"""Инструменты агента — 17 штук общего назначения.

Ни один не знает про конкретный сайт или тип задачи: сценарии агент собирает
из них сам (docs/CONSTRAINTS.md §2.1).
"""

from . import interaction, meta, navigation, reading
from .errors import (
    ActionTimeout,
    BadArguments,
    Covered,
    NavigationFailed,
    NotVisible,
    ToolError,
    ToolFailed,
    UnknownTool,
)
from .registry import Tool, ToolContext, ToolRegistry, ToolResult


def build_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.include(navigation.TOOLS)
    registry.include(interaction.TOOLS)
    registry.include(reading.TOOLS)
    registry.include(meta.TOOLS)
    return registry


__all__ = [
    "ActionTimeout",
    "BadArguments",
    "Covered",
    "NavigationFailed",
    "NotVisible",
    "Tool",
    "ToolContext",
    "ToolError",
    "ToolFailed",
    "ToolRegistry",
    "ToolResult",
    "UnknownTool",
    "build_registry",
]

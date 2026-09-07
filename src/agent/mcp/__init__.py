"""MCP-обёртка: те же инструменты, но для чужой модели (docs/DECISIONS.md ADR-040).

Пакет разделён надвое намеренно. `session.py` не импортирует `mcp` и работает
без установленного extra — в нём жизненный цикл браузера и правила свежести
состояния, то есть то, что можно проверить тестами без живого Chrome.
`server.py` поверх него — только протокол, и он есть лишь при `pip install -e .[mcp]`.

Поэтому здесь реэкспортируется одна сессия: подтягивать `server` из `__init__`
значило бы требовать optional-зависимость от всех, кто просто импортирует пакет.
"""

from .session import LOOP_ONLY_TOOLS, BrowserSession, CallOutcome, mcp_registry

__all__ = [
    "LOOP_ONLY_TOOLS",
    "BrowserSession",
    "CallOutcome",
    "mcp_registry",
]

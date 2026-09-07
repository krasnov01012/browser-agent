"""Общая обвязка тестов.

Тесты здесь не поднимают браузер и не ходят в сеть: проверяется та логика,
которая приняла решение и которую можно сломать рефакторингом, — разбор
состояния, компакция контекста, детектор циклов, привязка аргументов.
Поведение самой страницы измеряется прогоном evals/run.py, это другой уровень.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

if TYPE_CHECKING:
    from agent.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Настройки-заглушка: ключей не содержит и в сеть с ними никто не ходит.

    Нужна там, где объект приходится передать по сигнатуре, — например
    MCP-сессии, которая только раздаёт его фабрикам браузера и роутера.
    """
    # Импорт внутри функции: пакет доступен только после правки sys.path выше.
    from agent.config import Models, Settings

    return Settings(
        provider="zai",
        api_key="test",
        base_url="https://example.test/v1",
        models=Models(navigator="m", extractor="m", vision="m", fallback="m"),
        max_output_tokens=1500,
        max_steps=60,
        max_task_input_tokens=400_000,
        snapshot_token_budget=4000,
        cdp_url="http://127.0.0.1:9222",
        dom_settle_ms=500,
        dom_settle_timeout_ms=8000,
        confirm_destructive=False,
        persist_memory=False,
        ui_host="127.0.0.1",
        ui_port=8000,
        log_dir=ROOT / "runs",
        memory_dir=ROOT / "memory",
    )

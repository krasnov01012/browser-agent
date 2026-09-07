"""Конфигурация из переменных окружения.

Единственное место, где читается .env. Всё остальное получает Settings явно —
никаких os.environ по коду.
"""

from __future__ import annotations

import contextlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _fix_console_encoding() -> None:
    """Консоль Windows по умолчанию cp1251 и падает на кириллице."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, OSError):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError as e:
        raise ValueError(f"{name} должен быть целым числом, получено {raw!r}") from e


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


# Провайдеры с OpenAI-совместимым протоколом: имя -> (env ключа, env базы, база по умолчанию)
OPENAI_COMPATIBLE: dict[str, tuple[str, str, str]] = {
    "zai": ("ZAI_API_KEY", "ZAI_BASE_URL", "https://api.z.ai/api/paas/v4"),
    "gemini": (
        "GEMINI_API_KEY",
        "GEMINI_BASE_URL",
        "https://generativelanguage.googleapis.com/v1beta/openai/",
    ),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
}


@dataclass(frozen=True)
class Models:
    """Модель на каждую роль. Роли разведены, чтобы менять цену точечно."""

    navigator: str
    extractor: str
    vision: str
    fallback: str

    def chain(self, role: str) -> list[str]:
        """Основная модель роли, затем фоллбэк. Дубли отброшены."""
        primary = getattr(self, role, None)
        if primary is None:
            raise ValueError(f"неизвестная роль модели: {role!r}")
        return [primary] if primary == self.fallback else [primary, self.fallback]


@dataclass(frozen=True)
class Settings:
    provider: str
    api_key: str
    base_url: str
    models: Models

    max_output_tokens: int
    max_steps: int
    max_task_input_tokens: int
    snapshot_token_budget: int

    cdp_url: str
    dom_settle_ms: int
    dom_settle_timeout_ms: int

    confirm_destructive: bool
    persist_memory: bool

    ui_host: str
    ui_port: int
    log_dir: Path
    memory_dir: Path

    extra: dict[str, str] = field(default_factory=dict)

    @property
    def is_anthropic(self) -> bool:
        return self.provider == "anthropic"


def load_settings(env_file: Path | None = None) -> Settings:
    _fix_console_encoding()
    # override=True намеренно. Ключ и адрес провайдера — связанная пара, и брать
    # их из разных мест нельзя. У пользователя Claude Code уже держит в окружении
    # свои ANTHROPIC_BASE_URL и ANTHROPIC_AUTH_TOKEN; при override=False ключ
    # брался из .env, а адрес — из окружения, и запрос уходил с чужим ключом не
    # на тот эндпоинт. Конфигурация проекта живёт в .env, окружение её не меняет.
    load_dotenv(env_file or PROJECT_ROOT / ".env", override=True)

    provider = os.getenv("LLM_PROVIDER", "zai").strip().lower()

    if provider == "anthropic":
        api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
        base_url = os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com").strip()
        key_var = "ANTHROPIC_API_KEY"
    elif provider in OPENAI_COMPATIBLE:
        key_var, base_var, base_default = OPENAI_COMPATIBLE[provider]
        api_key = os.getenv(key_var, "").strip()
        base_url = os.getenv(base_var, base_default).strip()
    else:
        known = ", ".join(["anthropic", *OPENAI_COMPATIBLE])
        raise ValueError(f"LLM_PROVIDER={provider!r} не поддерживается. Доступны: {known}")

    if not api_key:
        raise ValueError(f"{key_var} не задан. Скопируйте .env.example в .env и впишите ключ.")

    models = Models(
        navigator=os.getenv("MODEL_NAVIGATOR", "glm-4.6v-flash").strip(),
        extractor=os.getenv("MODEL_EXTRACTOR", "glm-4.5-flash").strip(),
        vision=os.getenv("MODEL_VISION", "glm-4.6v-flash").strip(),
        fallback=os.getenv("MODEL_FALLBACK", "glm-4.5-flash").strip(),
    )

    return Settings(
        provider=provider,
        api_key=api_key,
        base_url=base_url.rstrip("/"),
        models=models,
        # GLM-*-flash — reasoning-модели, часть бюджета уходит в reasoning_content
        max_output_tokens=_int("MAX_OUTPUT_TOKENS", 1500),
        max_steps=_int("MAX_STEPS", 60),
        max_task_input_tokens=_int("MAX_TASK_INPUT_TOKENS", 400_000),
        snapshot_token_budget=_int("SNAPSHOT_TOKEN_BUDGET", 4000),
        # Именно 127.0.0.1, а не localhost: Chrome слушает отладочный порт
        # только на IPv4, а `localhost` на Windows резолвится сначала в ::1 —
        # и Playwright падает с `connect EACCES ::1:9222` при живом браузере.
        cdp_url=os.getenv("CDP_URL", "http://127.0.0.1:9222").strip().rstrip("/"),
        dom_settle_ms=_int("DOM_SETTLE_MS", 500),
        dom_settle_timeout_ms=_int("DOM_SETTLE_TIMEOUT_MS", 8000),
        confirm_destructive=_bool("CONFIRM_DESTRUCTIVE", False),
        persist_memory=_bool("PERSIST_MEMORY", True),
        ui_host=os.getenv("UI_HOST", "127.0.0.1").strip(),
        ui_port=_int("UI_PORT", 8000),
        log_dir=PROJECT_ROOT / os.getenv("LOG_DIR", "runs"),
        memory_dir=PROJECT_ROOT / os.getenv("MEMORY_DIR", "memory"),
    )
